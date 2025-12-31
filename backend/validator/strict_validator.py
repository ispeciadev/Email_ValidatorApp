"""
High-Performance Email Validation – Strict SMTP Ruleset

Implements a 4-stage gated validation pipeline:
1. Syntax Check (RFC-5322 safe regex)
2. Domain Exists (DNS A/NS lookup)
3. MX Record Exists
4. SMTP Verification (ONLY if stages 1-3 are VALID)

Key Features:
- Strict SMTP response interpretation (code first, message second)
- Timeout = NEUTRAL (not INVALID)
- Inbox-full = RISKY (never INVALID)
- Max 10 concurrent SMTP connections
- DNS/MX resolution is async and parallel
"""

import asyncio
import aiodns
import aiosmtplib
import re
import time
from typing import Dict, Any, List, Tuple, Optional, Set
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

# Try to import scoring module, fallback to simple scoring if not available
try:
    from .scoring import calculate_full_score
    HAS_SCORING = True
except ImportError:
    HAS_SCORING = False
    def calculate_full_score(result: Dict[str, Any]) -> Dict[str, Any]:
        """Fallback scoring function"""
        return result

# ======================= STRICT CONFIGURATION =======================

# Timeouts (optimized for speed while maintaining accuracy)
CONNECTION_TIMEOUT = 5.0  # seconds - SMTP connection (reduced from 8)
READ_TIMEOUT = 4.0  # seconds - SMTP read (reduced from 6)
DNS_TIMEOUT = 2.0  # seconds - DNS resolution (reduced from 3)
RETRY_COUNT = 0  # NO retries

# Concurrency limits (increased for speed)
MAX_CONCURRENT_SMTP = 25  # Increased from 10 for better throughput
MAX_CONCURRENT_DNS = 100  # DNS can be much higher
MAX_MX_PARALLEL = 2  # Try top 2 MX hosts in parallel

# Sender identity for SMTP
SMTP_HELO_DOMAIN = "mail-validator.com"
SMTP_MAIL_FROM = "verify@mail-validator.com"

# ======================= SMTP RESPONSE CODES (STRICT) =======================

# VALID - email exists and deliverable
VALID_CODES = {250}

# RISKY - inbox full / quota exceeded
RISKY_CODES = {452, 552}

# NEUTRAL - greylisted / throttled / temp fail
NEUTRAL_CODES = {450, 451, 421}

# INVALID - mailbox not found / rejected
INVALID_CODES = {550, 551, 553}

# Inbox full keywords (case-insensitive)
INBOX_FULL_KEYWORDS = frozenset({
    'mailbox full',
    'quota exceeded',
    'over quota',
    'storage exceeded',
    'mailbox is full',
    'user over quota',
    'insufficient storage'
})

# ======================= DOMAIN LISTS =======================

def load_domain_list(filename: str) -> frozenset:
    """Load domain list from file"""
    filepath = Path(__file__).parent / filename
    domains = set()
    try:
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        domains.add(line.lower())
    except Exception:
        pass
    return frozenset(domains)

DISPOSABLE_DOMAINS = load_domain_list('disposable_domains.txt')
BLACKLIST_DOMAINS = load_domain_list('blacklist_domains.txt')

ROLE_PREFIXES = frozenset({
    "admin", "administrator", "root", "postmaster", "hostmaster", "webmaster",
    "support", "help", "info", "contact", "sales", "marketing",
    "billing", "noreply", "no-reply", "donotreply", "abuse", "security",
    "hr", "jobs", "careers", "press", "media", "legal", "compliance"
})

# ======================= RFC 5322 SYNTAX VALIDATION =======================

# Pre-compiled RFC 5322 safe regex patterns
_LOCAL_PATTERN = re.compile(
    r"^[a-zA-Z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-zA-Z0-9!#$%&'*+/=?^_`{|}~-]+)*$"
)
_DOMAIN_PATTERN = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
)


@lru_cache(maxsize=100000)
def validate_syntax(email: str) -> Tuple[str, str, str, str]:
    """
    Stage 1: RFC 5322 syntax validation.
    
    Returns: (status, reason, local_part, domain)
    Status: "valid" or "invalid"
    """
    if not email or not isinstance(email, str):
        return "invalid", "Empty or invalid input", "", ""
    
    email = email.strip()
    
    if len(email) > 320:
        return "invalid", "Email exceeds 320 characters", "", ""
    
    if email.count('@') != 1:
        return "invalid", "Must contain exactly one @ symbol", "", ""
    
    local_part, domain = email.split('@')
    
    if not local_part:
        return "invalid", "Empty local part", "", ""
    
    if len(local_part) > 64:
        return "invalid", "Local part exceeds 64 characters", "", ""
    
    if not domain:
        return "invalid", "Empty domain", "", ""
    
    if len(domain) > 255:
        return "invalid", "Domain exceeds 255 characters", "", ""
    
    # Check for consecutive dots
    if '..' in email:
        return "invalid", "Consecutive dots not allowed", "", ""
    
    # Check local part boundaries
    if local_part.startswith('.') or local_part.endswith('.'):
        return "invalid", "Local part cannot start or end with dot", "", ""
    
    # Check domain boundaries
    if domain.startswith('.') or domain.endswith('.'):
        return "invalid", "Domain cannot start or end with dot", "", ""
    
    if domain.startswith('-') or domain.endswith('-'):
        return "invalid", "Domain cannot start or end with hyphen", "", ""
    
    # Validate local part characters
    if not _LOCAL_PATTERN.match(local_part):
        return "invalid", "Invalid characters in local part", "", ""
    
    # Validate domain format
    if not _DOMAIN_PATTERN.match(domain):
        return "invalid", "Invalid domain format", "", ""
    
    # Check TLD
    tld = domain.rsplit('.', 1)[-1]
    if len(tld) < 2:
        return "invalid", "Invalid TLD", "", ""
    
    return "valid", "Syntax valid", local_part.lower(), domain.lower()


# ======================= DNS RESOLVER =======================

class StrictDNSResolver:
    """
    Async DNS resolver for domain and MX validation.
    Supports parallel resolution with optimized caching.
    """
    
    def __init__(self):
        self._resolver: Optional[aiodns.DNSResolver] = None
        self._mx_cache: Dict[str, Tuple[List[str], float]] = {}
        self._domain_cache: Dict[str, Tuple[bool, float]] = {}
        self._combined_cache: Dict[str, Tuple[Any, float]] = {}  # Combined domain+MX cache
        self._cache_ttl = 600  # 10 minutes (increased for better hit rate)
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_DNS)
    
    async def initialize(self):
        """Initialize the DNS resolver"""
        if self._resolver is None:
            self._resolver = aiodns.DNSResolver(
                timeout=DNS_TIMEOUT,
                tries=1
            )
    
    def _is_cached(self, cache: dict, key: str) -> Optional[Any]:
        """Check if key is cached and not expired"""
        if key in cache:
            value, expires = cache[key]
            if time.time() < expires:
                return value
            del cache[key]
        return None
    
    async def check_domain_and_mx(self, domain: str) -> Tuple[str, str, str, str, List[str]]:
        """
        Combined Stage 2+3: Check domain exists AND resolve MX in parallel.
        
        Returns: (domain_status, domain_reason, mx_status, mx_reason, mx_hosts)
        Much faster than sequential checks.
        """
        await self.initialize()
        
        # Check combined cache first
        cached = self._is_cached(self._combined_cache, domain)
        if cached is not None:
            return cached
        
        async with self._semaphore:
            # Run MX and A record lookups in parallel
            mx_task = self._resolve_mx_internal(domain)
            a_task = self._check_a_record(domain)
            
            mx_result, a_exists = await asyncio.gather(mx_task, a_task, return_exceptions=True)
            
            # Handle exceptions
            if isinstance(mx_result, Exception):
                mx_result = ([], False)
            if isinstance(a_exists, Exception):
                a_exists = False
            
            mx_hosts, mx_found = mx_result
            
            # Domain exists if we found MX or A record
            domain_exists = mx_found or a_exists or bool(mx_hosts)
            
            if not domain_exists:
                result = ("invalid", "Domain does not exist", "invalid", "No MX records", [])
                self._combined_cache[domain] = (result, time.time() + self._cache_ttl)
                return result
            
            if not mx_hosts:
                # Domain exists but no MX - use domain as implicit MX
                if a_exists:
                    mx_hosts = [domain]
                else:
                    result = ("valid", "Domain exists", "invalid", "No MX records", [])
                    self._combined_cache[domain] = (result, time.time() + self._cache_ttl)
                    return result
            
            result = ("valid", "Domain exists", "valid", "MX records found", mx_hosts)
            self._combined_cache[domain] = (result, time.time() + self._cache_ttl)
            return result
    
    async def _check_a_record(self, domain: str) -> bool:
        """Quick A record check"""
        try:
            result = await asyncio.wait_for(
                self._resolver.query(domain, 'A'),
                timeout=DNS_TIMEOUT
            )
            return bool(result)
        except Exception:
            return False
    
    async def _resolve_mx_internal(self, domain: str) -> Tuple[List[str], bool]:
        """Internal MX resolution"""
        try:
            result = await asyncio.wait_for(
                self._resolver.query(domain, 'MX'),
                timeout=DNS_TIMEOUT
            )
            if result:
                mx_sorted = sorted(result, key=lambda x: x.priority)
                mx_hosts = [str(mx.host).rstrip('.') for mx in mx_sorted]
                return mx_hosts, True
            return [], False
        except Exception:
            return [], False
    
    async def check_domain_exists(self, domain: str) -> Tuple[str, str]:
        """
        Stage 2: Check if domain exists via DNS A or NS lookup.
        
        Returns: (status, reason)
        Status: "valid" or "invalid"
        """
        domain_status, domain_reason, _, _, _ = await self.check_domain_and_mx(domain)
        return domain_status, domain_reason
    
    async def resolve_mx(self, domain: str) -> Tuple[str, str, List[str]]:
        """
        Stage 3: Resolve MX records.
        Uses combined cache for speed.
        
        Returns: (status, reason, mx_hosts)
        Status: "valid" or "invalid"
        """
        _, _, mx_status, mx_reason, mx_hosts = await self.check_domain_and_mx(domain)
        return mx_status, mx_reason, mx_hosts
    
    async def resolve_batch(self, domains: List[str]) -> Dict[str, Tuple[str, str, List[str]]]:
        """
        Resolve domain and MX for multiple domains in parallel.
        OPTIMIZED: Uses combined domain+MX resolution.
        
        Returns: {domain: (status, reason, mx_hosts)}
        """
        await self.initialize()
        
        async def resolve_one(domain: str) -> Tuple[str, Tuple[str, str, List[str]]]:
            # Combined domain + MX check (parallel A/MX)
            domain_status, domain_reason, mx_status, mx_reason, mx_hosts = await self.check_domain_and_mx(domain)
            
            if domain_status != "valid":
                return domain, ("invalid", domain_reason, [])
            if mx_status != "valid":
                return domain, ("invalid", mx_reason, [])
            
            return domain, (mx_status, mx_reason, mx_hosts)
        
        # Run all resolutions in parallel with semaphore
        sem = asyncio.Semaphore(MAX_CONCURRENT_DNS)
        
        async def resolve_with_sem(domain: str):
            async with sem:
                return await resolve_one(domain)
        
        tasks = [resolve_with_sem(d) for d in domains]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        output = {}
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                output[domains[i]] = ("invalid", f"Error: {str(result)}", [])
            else:
                domain, data = result
                output[domain] = data
        
        return output


# ======================= STRICT SMTP VERIFIER =======================

class StrictSMTPVerifier:
    """
    Stage 4: SMTP verification with strict response interpretation.
    
    MANDATORY Rules:
    - SMTP code takes precedence over message text
    - Timeout = NEUTRAL (not INVALID)
    - Inbox-full (452/552) = RISKY
    - No retries (retry_count = 0)
    - Try multiple MX hosts in PARALLEL for speed
    """
    
    def __init__(self):
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_SMTP)
    
    async def verify(self, email: str, mx_hosts: List[str]) -> Dict[str, Any]:
        """
        Perform SMTP verification with strict rules.
        Tries multiple MX hosts in PARALLEL for speed.
        
        Returns complete SMTP result with status interpretation.
        """
        if not mx_hosts:
            return {
                "smtp_attempted": False,
                "smtp_code": None,
                "smtp_message": "",
                "status": "INVALID",
                "reason": "No MX hosts available",
                "retry_recommended": False
            }
        
        # Try top MX hosts in parallel for speed
        hosts_to_try = mx_hosts[:MAX_MX_PARALLEL]
        
        async with self._semaphore:
            if len(hosts_to_try) == 1:
                return await self._verify_single_mx(email, hosts_to_try[0])
            
            # Race multiple MX hosts - first definitive result wins
            tasks = [
                asyncio.create_task(self._verify_single_mx(email, host))
                for host in hosts_to_try
            ]
            
            # Wait for first definitive result or all to complete
            best_result = None
            pending = set(tasks)
            
            while pending:
                done, pending = await asyncio.wait(
                    pending, 
                    return_when=asyncio.FIRST_COMPLETED,
                    timeout=CONNECTION_TIMEOUT + READ_TIMEOUT
                )
                
                for task in done:
                    try:
                        result = task.result()
                        # If we got a definitive answer, use it immediately
                        if result["status"] in ("VALID", "INVALID"):
                            # Cancel remaining tasks
                            for p in pending:
                                p.cancel()
                            return result
                        # Keep track of best non-definitive result
                        if best_result is None or result["smtp_code"] is not None:
                            best_result = result
                    except Exception:
                        pass
                
                if not pending:
                    break
            
            # Cancel any remaining tasks
            for task in pending:
                task.cancel()
            
            return best_result or {
                "smtp_attempted": True,
                "smtp_code": None,
                "smtp_message": "",
                "status": "NEUTRAL",
                "reason": "All MX hosts failed",
                "retry_recommended": True
            }
    
    async def _verify_single_mx(self, email: str, mx_host: str) -> Dict[str, Any]:
        """Verify against a single MX host"""
        
        result = {
            "smtp_attempted": True,
            "smtp_code": None,
            "smtp_message": "",
            "status": "NEUTRAL",
            "reason": "SMTP verification pending",
            "retry_recommended": False
        }
        
        try:
            # Create SMTP connection
            smtp = aiosmtplib.SMTP(
                hostname=mx_host,
                port=25,
                timeout=CONNECTION_TIMEOUT
            )
            
            # Stage 1: CONNECT with timeout
            try:
                await asyncio.wait_for(
                    smtp.connect(),
                    timeout=CONNECTION_TIMEOUT
                )
            except asyncio.TimeoutError:
                result["status"] = "NEUTRAL"
                result["reason"] = "SMTP connection timeout – server did not respond"
                result["retry_recommended"] = True
                return result
            
            try:
                # Stage 2: EHLO
                try:
                    await asyncio.wait_for(
                        smtp.ehlo(),
                        timeout=READ_TIMEOUT
                    )
                except Exception:
                    # Fallback to HELO
                    try:
                        await asyncio.wait_for(
                            smtp.helo(),
                            timeout=READ_TIMEOUT
                        )
                    except Exception:
                        pass  # Some servers don't require EHLO/HELO
                
                # Stage 3: MAIL FROM
                await asyncio.wait_for(
                    smtp.mail(SMTP_MAIL_FROM),
                    timeout=READ_TIMEOUT
                )
                
                # Stage 4: RCPT TO (the actual verification)
                try:
                    response = await asyncio.wait_for(
                        smtp.rcpt(email),
                        timeout=READ_TIMEOUT
                    )
                    code = response[0]
                    message = response[1] if len(response) > 1 else ""
                    
                except aiosmtplib.SMTPRecipientRefused as e:
                    code = e.code
                    message = str(e.message) if hasattr(e, 'message') else str(e)
                
                result["smtp_code"] = code
                result["smtp_message"] = message
                
                # Interpret the response (code first, then message)
                result.update(self._interpret_response(code, message))
                
            except asyncio.TimeoutError:
                result["status"] = "NEUTRAL"
                result["reason"] = "SMTP timeout – server did not respond"
                result["retry_recommended"] = True
                
            except aiosmtplib.SMTPSenderRefused as e:
                # Our sender was refused (IP blocked, etc.)
                result["smtp_code"] = e.code
                result["smtp_message"] = str(e.message) if hasattr(e, 'message') else str(e)
                result["status"] = "NEUTRAL"
                result["reason"] = "Sender refused by server (IP reputation issue)"
                result["retry_recommended"] = False
                
            finally:
                # Close connection
                try:
                    await asyncio.wait_for(smtp.quit(), timeout=2.0)
                except Exception:
                    pass
                    
        except asyncio.TimeoutError:
            result["status"] = "NEUTRAL"
            result["reason"] = "SMTP connection timeout – server did not respond"
            result["retry_recommended"] = True
            
        except aiosmtplib.SMTPConnectError:
            result["status"] = "NEUTRAL"
            result["reason"] = "SMTP connection failed"
            result["retry_recommended"] = True
            
        except Exception as e:
            result["status"] = "NEUTRAL"
            result["reason"] = f"SMTP error: {type(e).__name__}"
            result["retry_recommended"] = True
        
        return result
    
    def _interpret_response(self, code: int, message: str) -> Dict[str, Any]:
        """
        STRICT SMTP response interpretation.
        
        Rules (code first, message second):
        - 250 = VALID
        - 452/552 = RISKY (inbox full)
        - 450/451/421 = NEUTRAL (greylisted/throttled/temp fail)
        - 550/551/553 = INVALID
        - Timeout/No response = NEUTRAL
        """
        message_lower = message.lower() if message else ""
        
        # === VALID ===
        if code == 250:
            return {
                "status": "VALID",
                "reason": "Email address is valid and deliverable",
                "retry_recommended": False
            }
        
        # === RISKY (Inbox Full / Quota Exceeded) ===
        if code in RISKY_CODES:  # 452, 552
            return {
                "status": "RISKY",
                "reason": "Mailbox full or quota exceeded",
                "retry_recommended": True
            }
        
        # Also check message for inbox full indicators
        if any(keyword in message_lower for keyword in INBOX_FULL_KEYWORDS):
            return {
                "status": "RISKY",
                "reason": "Mailbox full or quota exceeded",
                "retry_recommended": True
            }
        
        # === NEUTRAL (Greylisted / Throttled / Temp Fail) ===
        if code in NEUTRAL_CODES:  # 450, 451, 421
            reasons = {
                450: "Mailbox unavailable (greylisted or temp fail)",
                451: "Local error in processing (greylisted)",
                421: "Service temporarily unavailable (throttled)"
            }
            return {
                "status": "NEUTRAL",
                "reason": reasons.get(code, "Temporary failure"),
                "retry_recommended": True
            }
        
        # === INVALID (Mailbox Not Found / Rejected) ===
        if code in INVALID_CODES:  # 550, 551, 553
            reasons = {
                550: "Mailbox does not exist",
                551: "User not local",
                553: "Mailbox name invalid"
            }
            return {
                "status": "INVALID",
                "reason": reasons.get(code, "Mailbox rejected"),
                "retry_recommended": False
            }
        
        # 554 - Transaction failed (could be policy or permanent)
        if code == 554:
            return {
                "status": "INVALID",
                "reason": "Mailbox disabled or transaction failed",
                "retry_recommended": False
            }
        
        # Unknown code - treat as NEUTRAL
        return {
            "status": "NEUTRAL",
            "reason": f"Unknown SMTP response code: {code}",
            "retry_recommended": True
        }


# ======================= MAIN STRICT VALIDATOR =======================

class StrictEmailValidator:
    """
    High-Performance Email Validation with Strict SMTP Ruleset.
    
    4-Stage Gated Pipeline:
    1. Syntax Check (RFC-5322)
    2. Domain Exists (DNS A/NS)
    3. MX Record Exists
    4. SMTP Verification (ONLY if 1-3 are VALID)
    
    If any of stages 1-3 fail, SMTP is skipped completely.
    """
    
    def __init__(self):
        self._dns = StrictDNSResolver()
        self._smtp = StrictSMTPVerifier()
        self._initialized = False
    
    async def initialize(self):
        """Initialize the validator"""
        if not self._initialized:
            await self._dns.initialize()
            self._initialized = True
            print("StrictEmailValidator initialized.")
    
    async def validate_email(self, email: str) -> Dict[str, Any]:
        """
        Validate a single email through the 4-stage pipeline.
        
        OPTIMIZED: Combined DNS+MX resolution in parallel for speed.
        
        Returns the strict output schema:
        {
            "email": "user@domain.com",
            "syntax": "valid/invalid",
            "domain": "valid/invalid",
            "mx": "valid/invalid",
            "smtp_attempted": true/false,
            "smtp_code": null/int,
            "status": "VALID/INVALID/RISKY/NEUTRAL",
            "reason": "...",
            "retry_recommended": true/false
        }
        """
        email = email.strip().lower() if email else ""
        
        # Initialize result with strict schema
        result = self._init_result(email)
        
        # ========== STAGE 1: SYNTAX CHECK ==========
        syntax_status, syntax_reason, local_part, domain = validate_syntax(email)
        result["syntax"] = syntax_status
        
        if syntax_status != "valid":
            result["status"] = "INVALID"
            result["reason"] = syntax_reason
            result["smtp_attempted"] = False
            return self._finalize_result(result)
        
        # ========== STAGE 2 & 3: COMBINED DOMAIN + MX CHECK (PARALLEL) ==========
        # This is faster than sequential checks
        domain_status, domain_reason, mx_status, mx_reason, mx_hosts = await self._dns.check_domain_and_mx(domain)
        result["domain"] = domain_status
        result["mx"] = mx_status
        
        if domain_status != "valid":
            result["status"] = "INVALID"
            result["reason"] = domain_reason
            result["smtp_attempted"] = False
            return self._finalize_result(result)
        
        if mx_status != "valid":
            result["status"] = "INVALID"
            result["reason"] = mx_reason
            result["smtp_attempted"] = False
            return self._finalize_result(result)
        
        # ========== STAGE 4: SMTP VERIFICATION ==========
        # Only runs if stages 1-3 are VALID
        smtp_result = await self._smtp.verify(email, mx_hosts)
        
        result["smtp_attempted"] = smtp_result["smtp_attempted"]
        result["smtp_code"] = smtp_result["smtp_code"]
        result["status"] = smtp_result["status"]
        result["reason"] = smtp_result["reason"]
        result["retry_recommended"] = smtp_result["retry_recommended"]
        
        # Add additional metadata
        result["local_part"] = local_part
        result["domain_name"] = domain
        result["mx_hosts"] = mx_hosts
        
        # Check for disposable/role-based (informational flags)
        result["is_disposable"] = domain in DISPOSABLE_DOMAINS
        result["is_blacklisted"] = domain in BLACKLIST_DOMAINS
        result["is_role_based"] = local_part.split('+')[0] in ROLE_PREFIXES
        
        return self._finalize_result(result)
    
    async def validate_bulk(
        self, 
        emails: List[str],
        batch_id: str = None
    ) -> List[Dict[str, Any]]:
        """
        Validate multiple emails with optimal performance.
        
        Performance Rules:
        - DNS + MX resolution is async and parallel
        - SMTP concurrency limit: max 10 at a time
        - Never block pipeline on SMTP
        """
        if not self._initialized:
            await self.initialize()
        
        start_time = time.time()
        
        # Clean and dedupe emails
        unique_emails = list(dict.fromkeys(
            email.strip().lower() for email in emails if email and email.strip()
        ))
        
        # Phase 1: Parallel syntax validation (instant)
        syntax_results = {}
        domains_to_check = set()
        
        for email in unique_emails:
            status, reason, local_part, domain = validate_syntax(email)
            syntax_results[email] = (status, reason, local_part, domain)
            if status == "valid" and domain:
                domains_to_check.add(domain)
        
        # Phase 2: Parallel DNS/MX resolution for all valid domains
        dns_results = await self._dns.resolve_batch(list(domains_to_check))
        
        # Phase 3: SMTP verification (only for emails that passed stages 1-3)
        async def validate_one(email: str) -> Dict[str, Any]:
            result = self._init_result(email)
            
            # Stage 1: Syntax (from cache)
            syntax_status, syntax_reason, local_part, domain = syntax_results[email]
            result["syntax"] = syntax_status
            
            if syntax_status != "valid":
                result["status"] = "INVALID"
                result["reason"] = syntax_reason
                result["smtp_attempted"] = False
                return self._finalize_result(result)
            
            # Stage 2 & 3: Domain/MX (from parallel resolution)
            if domain in dns_results:
                mx_status, mx_reason, mx_hosts = dns_results[domain]
                result["domain"] = "valid" if mx_status == "valid" or mx_hosts else "invalid"
                result["mx"] = mx_status
                
                if mx_status != "valid":
                    result["status"] = "INVALID"
                    result["reason"] = mx_reason
                    result["smtp_attempted"] = False
                    return self._finalize_result(result)
            else:
                result["domain"] = "invalid"
                result["mx"] = "invalid"
                result["status"] = "INVALID"
                result["reason"] = "Domain validation failed"
                result["smtp_attempted"] = False
                return self._finalize_result(result)
            
            # Stage 4: SMTP verification
            smtp_result = await self._smtp.verify(email, mx_hosts)
            
            result["smtp_attempted"] = smtp_result["smtp_attempted"]
            result["smtp_code"] = smtp_result["smtp_code"]
            result["status"] = smtp_result["status"]
            result["reason"] = smtp_result["reason"]
            result["retry_recommended"] = smtp_result["retry_recommended"]
            
            # Metadata
            result["local_part"] = local_part
            result["domain_name"] = domain
            result["mx_hosts"] = mx_hosts
            result["is_disposable"] = domain in DISPOSABLE_DOMAINS
            result["is_blacklisted"] = domain in BLACKLIST_DOMAINS
            result["is_role_based"] = local_part.split('+')[0] in ROLE_PREFIXES
            
            return self._finalize_result(result)
        
        # Run all validations with controlled concurrency
        tasks = [validate_one(email) for email in unique_emails]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                error_result = self._init_result(unique_emails[i])
                error_result["status"] = "NEUTRAL"
                error_result["reason"] = f"Validation error: {str(result)}"
                error_result["retry_recommended"] = True
                final_results.append(self._finalize_result(error_result))
            else:
                if batch_id:
                    result["batch_id"] = batch_id
                final_results.append(result)
        
        elapsed = time.time() - start_time
        rate = len(unique_emails) / max(elapsed, 0.001)
        print(f"STRICT_VALIDATOR: {len(unique_emails)} emails in {elapsed:.2f}s ({rate:.1f}/sec)")
        
        return final_results
    
    def _init_result(self, email: str) -> Dict[str, Any]:
        """Initialize result with strict output schema"""
        return {
            "email": email,
            "syntax": "invalid",
            "domain": "invalid",
            "mx": "invalid",
            "smtp_attempted": False,
            "smtp_code": None,
            "status": "INVALID",
            "reason": "",
            "retry_recommended": False,
            # Additional fields for compatibility
            "local_part": "",
            "domain_name": "",
            "mx_hosts": [],
            "is_disposable": False,
            "is_blacklisted": False,
            "is_role_based": False,
        }
    
    def _finalize_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """
        Finalize result with computed fields for compatibility.
        Maps strict status to legacy format.
        """
        status = result["status"]
        
        # Map to legacy format for backward compatibility
        result["is_valid"] = status == "VALID"
        result["is_deliverable"] = status == "VALID"
        result["is_risky"] = status == "RISKY"
        result["is_neutral"] = status == "NEUTRAL"
        result["is_unknown"] = status == "NEUTRAL"
        result["is_inbox_full"] = status == "RISKY" and "full" in result.get("reason", "").lower()
        
        # Legacy field mappings
        result["syntax_valid"] = "Valid" if result["syntax"] == "valid" else "Not Valid"
        result["domain_valid"] = "Valid" if result["domain"] == "valid" else "Not Valid"
        result["mx_record_exists"] = "Valid" if result["mx"] == "valid" else "Not Valid"
        result["smtp_valid"] = "Valid" if status == "VALID" else ("Unknown" if status == "NEUTRAL" else "Not Valid")
        
        # Status mapping for compatibility
        status_map = {
            "VALID": "safe",
            "INVALID": "invalid",
            "RISKY": "risky",
            "NEUTRAL": "unknown"
        }
        result["status_lowercase"] = status_map.get(status, "unknown")
        
        # Set flags based on additional checks
        if result["is_role_based"]:
            if status == "VALID":
                result["status"] = "VALID"  # Keep VALID but flag as role-based
                result["reason"] = "Valid email (role-based address)"
        
        if result["is_disposable"]:
            result["status"] = "RISKY"
            result["reason"] = "Disposable email domain"
            result["is_risky"] = True
        
        if result["is_blacklisted"]:
            result["status"] = "RISKY"
            result["reason"] = "Blacklisted domain"
            result["is_risky"] = True
        
        # Calculate score (simplified)
        result["deliverability_score"] = self._calculate_score(result)
        result["quality_grade"] = self._get_grade(result["deliverability_score"])
        
        return result
    
    def _calculate_score(self, result: Dict[str, Any]) -> int:
        """Calculate deliverability score (0-100)"""
        score = 0
        
        if result["syntax"] == "valid":
            score += 20
        if result["domain"] == "valid":
            score += 20
        if result["mx"] == "valid":
            score += 20
        
        status = result["status"]
        if status == "VALID":
            score += 40
        elif status == "RISKY":
            score += 20
        elif status == "NEUTRAL":
            score += 10
        
        # Deductions
        if result["is_disposable"]:
            score -= 30
        if result["is_blacklisted"]:
            score -= 40
        if result["is_role_based"]:
            score -= 10
        
        return max(0, min(100, score))
    
    def _get_grade(self, score: int) -> str:
        """Convert score to letter grade"""
        if score >= 90:
            return "A+"
        elif score >= 80:
            return "A"
        elif score >= 70:
            return "B"
        elif score >= 60:
            return "C"
        elif score >= 50:
            return "D"
        else:
            return "F"


# ======================= SINGLETON INSTANCE =======================

_strict_validator: Optional[StrictEmailValidator] = None


async def get_strict_validator() -> StrictEmailValidator:
    """Get or create singleton validator instance"""
    global _strict_validator
    if _strict_validator is None:
        _strict_validator = StrictEmailValidator()
        await _strict_validator.initialize()
    return _strict_validator


# ======================= CONVENIENCE FUNCTIONS =======================

async def validate_email_strict(email: str) -> Dict[str, Any]:
    """Validate a single email with strict rules"""
    validator = await get_strict_validator()
    return await validator.validate_email(email)


async def validate_bulk_strict(emails: List[str], batch_id: str = None) -> List[Dict[str, Any]]:
    """Validate multiple emails with strict rules"""
    validator = await get_strict_validator()
    return await validator.validate_bulk(emails, batch_id)
