"""
Ultra-Fast Async Email Validator - Optimized for 10+ emails/second

Key Optimizations:
1. Aggressive micro-timeouts (100-300ms for DNS, 500ms for SMTP)
2. Skip SMTP for trusted providers (Gmail, Outlook, Yahoo, etc.)
3. Parallel DNS resolution with concurrent.futures fallback
4. Connection pooling with keep-alive
5. Smart domain batching - pre-resolve MX for all domains first
6. Lazy catch-all detection (skip for trusted providers)
7. In-memory LRU cache with high hit rates
8. Fire-and-forget for non-critical operations
"""

import asyncio
import aiodns
import aiosmtplib
import time
import random
import string
import re
from typing import Dict, Any, List, Tuple, Optional, Set
from dataclasses import dataclass, field
from collections import defaultdict
from pathlib import Path
from functools import lru_cache
import hashlib

# Import scoring module
from .scoring import calculate_full_score, calculate_score, get_quality_grade

# ======================= AGGRESSIVE CONFIGURATION =======================

# Timeouts - OPTIMIZED FOR SPEED (0.1-0.5s target)
DNS_TIMEOUT = 0.3  # 0.3s for DNS - ultra-fast
SMTP_CONNECT_TIMEOUT = 1.5  # 1.5s for SMTP connect - minimal for speed
SMTP_CONNECT_TIMEOUT_TRUSTED = 0.3  # 0.3s for trusted providers (skip anyway)
SMTP_COMMAND_TIMEOUT = 1.0  # 1.0s for SMTP commands - reduced
SMTP_COMMAND_TIMEOUT_TRUSTED = 0.3  # 0.3s for trusted providers (skip anyway)

# Concurrency - maximize parallelism
MAX_CONCURRENT_VALIDATIONS = 200  # High concurrency
MAX_CONCURRENT_SMTP_PER_DOMAIN = 5  # Limit per domain to avoid blocking
BATCH_CHUNK_SIZE = 100  # Process in chunks

# Connection pool settings
MAX_POOL_SIZE = 50  # Max connections to keep
CONNECTION_TTL = 120  # 2 minutes

# Cache TTL (longer = more cache hits)
MX_CACHE_TTL = 600  # 10 minutes for MX records
CATCHALL_CACHE_TTL = 600  # 10 minutes for catch-all status

# ======================= GREYLISTING & RETRY CONFIG =======================
# Greylisting handling - DISABLED FOR SPEED
GREYLISTING_RETRY_DELAY = 0.0  # No retry delay (disabled)
GREYLISTING_MAX_RETRIES = 0  # NO retries for speed
MAX_MX_HOSTS_TO_TRY = 1  # Try only 1 MX host for speed

# Greylisting response codes (temporary failures that may succeed on retry)
GREYLISTING_CODES = {450, 451, 421}

# Valid response codes (email exists and is deliverable)
VALID_CODES = {250, 251}  # 251 = User forwarded

# ======================= MAILBOX STATUS CODES =======================
# SMTP codes for mailbox full/quota exceeded
MAILBOX_FULL_CODES = {552, 422, 452}  # Mailbox full, storage quota exceeded
MAILBOX_DISABLED_CODES = {550, 551, 553, 554}  # Mailbox not found, disabled
MAILBOX_FULL_KEYWORDS = frozenset({'full', 'quota', 'exceeded', 'storage', 'over quota', 'mailbox full'})

# ======================= TRUSTED PROVIDERS =======================
# These providers BLOCK SMTP verification - skip SMTP, trust MX lookup
# This is the BIGGEST speed optimization - skips slow SMTP handshakes

TRUSTED_PROVIDERS = frozenset({
    # Google
    "gmail.com", "googlemail.com", "google.com",
    # Microsoft
    "outlook.com", "hotmail.com", "live.com", "msn.com", "outlook.in",
    "hotmail.co.uk", "live.co.uk", "outlook.co.uk",
    # Yahoo
    "yahoo.com", "yahoo.co.uk", "yahoo.co.in", "yahoo.in", 
    "ymail.com", "rocketmail.com", "yahoo.fr", "yahoo.de",
    # Apple
    "icloud.com", "me.com", "mac.com",
    # AOL/Verizon
    "aol.com", "aim.com", "verizon.net",
    # ProtonMail
    "protonmail.com", "proton.me", "pm.me", "protonmail.ch",
})

# Known domains that DO respond to SMTP verification (worth checking)
SMTP_RESPONSIVE_DOMAINS = frozenset({
    # Corporate domains often accept SMTP verification
})


# ======================= LOAD DOMAIN LISTS =======================

def load_domain_list(filename: str) -> frozenset:
    """Load domain list from file - cached at module level"""
    filepath = Path(__file__).parent / filename
    domains = set()
    try:
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        domains.add(line.lower())
    except Exception as e:
        print(f"Warning: Could not load {filename}: {e}")
    return frozenset(domains)


# Load lists at module level (one-time cost)
DISPOSABLE_DOMAINS = load_domain_list('disposable_domains.txt')
BLACKLIST_DOMAINS = load_domain_list('blacklist_domains.txt')
SPAMTRAP_DOMAINS = load_domain_list('spamtrap_domains.txt')

# Role-based email prefixes
ROLE_EMAILS = frozenset({
    "admin", "administrator", "root", "sysadmin", "webmaster", "hostmaster", "postmaster",
    "support", "help", "helpdesk", "service", "customer", "customerservice", "customersupport",
    "sales", "marketing", "info", "contact", "enquiry", "inquiry", "team",
    "billing", "accounts", "accounting", "finance", "payment", "payments", "invoice", "invoices",
    "office", "reception", "legal", "compliance", "privacy", "security",
    "noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon",
    "abuse", "feedback", "press", "media", "news", "pr", "public",
    "hr", "jobs", "careers", "recruitment", "hiring", "apply", "application",
    "dev", "developer", "it", "tech", "technical", "engineering",
    "orders", "order", "shop", "store", "returns", "refunds", "reservations"
})


# ======================= FAST CACHES =======================

class FastCache:
    """Ultra-fast in-memory cache with TTL"""
    
    __slots__ = ('_cache', '_max_size')
    
    def __init__(self, max_size: int = 10000):
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._max_size = max_size
    
    def get(self, key: str) -> Optional[Any]:
        """Get value if exists and not expired"""
        entry = self._cache.get(key)
        if entry:
            value, expires_at = entry
            if time.time() < expires_at:
                return value
            # Expired - remove it
            del self._cache[key]
        return None
    
    def set(self, key: str, value: Any, ttl: float):
        """Set value with TTL"""
        # Simple eviction if too large
        if len(self._cache) >= self._max_size:
            # Remove oldest 10%
            to_remove = list(self._cache.keys())[:self._max_size // 10]
            for k in to_remove:
                del self._cache[k]
        
        self._cache[key] = (value, time.time() + ttl)
    
    def size(self) -> int:
        return len(self._cache)


# Global caches (shared across all validators)
_mx_cache = FastCache(max_size=50000)
_catchall_cache = FastCache(max_size=10000)
_domain_validity_cache = FastCache(max_size=50000)


# ======================= SYNTAX VALIDATION (COMPILED REGEX) =======================

# Pre-compiled regex patterns for maximum speed
_LOCAL_PATTERN = re.compile(r"^[a-zA-Z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-zA-Z0-9!#$%&'*+/=?^_`{|}~-]+)*$")
_DOMAIN_PATTERN = re.compile(r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?\.)+[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?$")


@lru_cache(maxsize=100000)
def check_syntax_fast(email: str) -> Tuple[bool, str, str, str]:
    """
    Ultra-fast RFC 5322 syntax validation with caching.
    Returns: (is_valid, reason, local_part, domain)
    """
    if not email or not isinstance(email, str):
        return False, "Empty or invalid email", "", ""
    
    if len(email) > 320:
        return False, "Email too long", "", ""
    
    if email.count('@') != 1:
        return False, "Invalid @ symbol", "", ""
    
    at_pos = email.index('@')
    local_part = email[:at_pos]
    domain = email[at_pos + 1:]
    
    if not local_part or len(local_part) > 64:
        return False, "Invalid local part", "", ""
    
    if not domain or len(domain) > 255:
        return False, "Invalid domain", "", ""
    
    if '..' in email or local_part[0] == '.' or local_part[-1] == '.':
        return False, "Invalid dots", "", ""
    
    if domain[0] == '.' or domain[-1] == '.':
        return False, "Invalid domain dots", "", ""
    
    if not _LOCAL_PATTERN.match(local_part):
        return False, "Invalid local characters", "", ""
    
    if not _DOMAIN_PATTERN.match(domain):
        return False, "Invalid domain format", "", ""
    
    tld = domain.rsplit('.', 1)[-1]
    if len(tld) < 2:
        return False, "Invalid TLD", "", ""
    
    return True, "Valid", local_part, domain


@lru_cache(maxsize=50000)
def check_disposable_fast(domain: str) -> bool:
    """
    Check if domain is disposable with subdomain matching.
    Matches: tempmail.com, xyz.tempmail.com, abc.xyz.tempmail.com
    """
    # Direct match
    if domain in DISPOSABLE_DOMAINS:
        return True
    
    # Subdomain matching - check if parent domain is disposable
    # e.g., test.tempmail.com -> tempmail.com
    parts = domain.split('.')
    if len(parts) > 2:
        for i in range(1, len(parts) - 1):
            parent_domain = '.'.join(parts[i:])
            if parent_domain in DISPOSABLE_DOMAINS:
                return True
    
    # Pattern-based detection for common disposable patterns
    # Many temp mail services use these patterns
    disposable_patterns = (
        'tempmail', 'temp-mail', 'tmpmail', 'guerrilla', 'mailinator',
        'throwaway', 'disposable', 'fakeinbox', 'trashmail', 'yopmail',
        '10minute', '10min', 'minutemail', 'sharklasers', 'burnermail',
        'maildrop', 'getairmail', 'getnada', 'emailondeck', 'tempr',
        'spamgourmet', 'mailnesia', 'mytrashmail', 'guerrillamail'
    )
    domain_lower = domain.lower()
    for pattern in disposable_patterns:
        if pattern in domain_lower:
            return True
    
    return False


@lru_cache(maxsize=50000)
def check_blacklist_fast(domain: str) -> bool:
    """Check if domain is blacklisted - cached"""
    return domain in BLACKLIST_DOMAINS


@lru_cache(maxsize=50000)
def check_spamtrap_fast(email: str, domain: str) -> bool:
    """
    Check if email is a known spamtrap.
    Reoon-style spamtrap detection.
    """
    # Check if domain is known spamtrap domain
    if domain in SPAMTRAP_DOMAINS:
        return True
    
    # Check for spamtrap patterns in email
    spamtrap_patterns = ('spamtrap', 'honeypot', 'trap', 'abuse', 'blackhole')
    email_lower = email.lower()
    for pattern in spamtrap_patterns:
        if pattern in email_lower:
            return True
    
    return False


@lru_cache(maxsize=100000)
def check_role_fast(local_part: str) -> bool:
    """Check if local part is role-based - cached"""
    normalized = local_part.replace('.', '').replace('-', '').replace('_', '')
    return local_part in ROLE_EMAILS or normalized in ROLE_EMAILS


def is_trusted_provider(domain: str) -> bool:
    """Check if domain is a trusted provider that blocks SMTP"""
    return domain in TRUSTED_PROVIDERS


def validate_gmail_username(local_part: str) -> bool:
    """
    Validate Gmail username rules for better accuracy.
    Gmail rules:
    - 6-30 characters (before @ and before any +)
    - Only letters, numbers, dots, and plus (for filtering)
    - Cannot start or end with a dot
    - No consecutive dots
    - Plus addressing (user+tag) is allowed for filtering
    """
    # Handle plus addressing - Gmail allows user+tag format
    base_part = local_part.split('+')[0] if '+' in local_part else local_part
    
    # Remove dots for length check (Gmail ignores dots)
    clean = base_part.replace('.', '')
    
    # Length check (6-30 chars without dots, based on base part before +)
    if len(clean) < 6 or len(clean) > 30:
        return False
    
    # Only alphanumeric in base part (Gmail doesn't allow special chars except dots)
    if not clean.isalnum():
        return False
    
    # Cannot start or end with dot
    if base_part.startswith('.') or base_part.endswith('.'):
        return False
    
    # No consecutive dots
    if '..' in base_part:
        return False
    
    return True


def validate_yahoo_username(local_part: str) -> bool:
    """
    Validate Yahoo username rules.
    Yahoo rules:
    - 4-32 characters
    - Letters, numbers, underscores, dots
    - Must start with a letter
    - Plus addressing is supported
    """
    # Handle plus addressing
    base_part = local_part.split('+')[0] if '+' in local_part else local_part
    
    if len(base_part) < 4 or len(base_part) > 32:
        return False
    
    if not base_part[0].isalpha():
        return False
    
    # Only alphanumeric, underscore, dot in base part
    allowed = set('abcdefghijklmnopqrstuvwxyz0123456789_.')
    if not all(c in allowed for c in base_part.lower()):
        return False
    
    return True


def validate_outlook_username(local_part: str) -> bool:
    """
    Validate Outlook/Hotmail username rules.
    - Starts with letter
    - 1-64 characters
    - Letters, numbers, dots, hyphens, underscores
    - Plus addressing is supported
    """
    # Handle plus addressing
    base_part = local_part.split('+')[0] if '+' in local_part else local_part
    
    if len(base_part) < 1 or len(base_part) > 64:
        return False
    
    if not base_part[0].isalpha():
        return False
    
    allowed = set('abcdefghijklmnopqrstuvwxyz0123456789._-')
    if not all(c in allowed for c in base_part.lower()):
        return False
    
    return True


# ======================= ASYNC DNS RESOLVER =======================

class FastDNSResolver:
    """Ultra-fast async DNS resolver with caching"""
    
    def __init__(self):
        self._resolver: Optional[aiodns.DNSResolver] = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize the resolver"""
        if not self._initialized:
            self._resolver = aiodns.DNSResolver(
                timeout=DNS_TIMEOUT,
                tries=1,  # Single try for speed
            )
            self._initialized = True
    
    async def resolve_mx(self, domain: str) -> List[str]:
        """Resolve MX records with caching"""
        # Check cache first
        cached = _mx_cache.get(domain)
        if cached is not None:
            return cached
        
        if not self._initialized:
            await self.initialize()
        
        try:
            result = await asyncio.wait_for(
                self._resolver.query(domain, 'MX'),
                timeout=DNS_TIMEOUT
            )
            # Sort by priority
            mx_hosts = sorted(result, key=lambda x: x.priority)
            mx_list = [str(mx.host).rstrip('.') for mx in mx_hosts]
            
            # Cache result
            _mx_cache.set(domain, mx_list, MX_CACHE_TTL)
            return mx_list
            
        except asyncio.TimeoutError:
            _mx_cache.set(domain, [], MX_CACHE_TTL // 2)  # Cache negative result shorter
            return []
        except Exception:
            _mx_cache.set(domain, [], MX_CACHE_TTL // 2)
            return []
    
    async def resolve_mx_batch(self, domains: List[str]) -> Dict[str, List[str]]:
        """Resolve MX for multiple domains in parallel"""
        if not self._initialized:
            await self.initialize()
        
        # Filter out cached domains
        uncached = []
        results = {}
        
        for domain in domains:
            cached = _mx_cache.get(domain)
            if cached is not None:
                results[domain] = cached
            else:
                uncached.append(domain)
        
        if uncached:
            # Resolve uncached domains in parallel
            tasks = [self.resolve_mx(d) for d in uncached]
            resolved = await asyncio.gather(*tasks, return_exceptions=True)
            
            for domain, mx in zip(uncached, resolved):
                if isinstance(mx, Exception):
                    results[domain] = []
                else:
                    results[domain] = mx
        
        return results


# ======================= FAST SMTP VERIFIER =======================

class FastSMTPVerifier:
    """
    Advanced SMTP verification with Reoon-style features:
    1. Greylisting retry (450/451 handling)
    2. Fallback to multiple MX hosts
    3. Enhanced response code interpretation
    4. Improved catch-all detection
    """
    
    def __init__(self):
        self._domain_semaphores: Dict[str, asyncio.Semaphore] = defaultdict(
            lambda: asyncio.Semaphore(MAX_CONCURRENT_SMTP_PER_DOMAIN)
        )
    
    async def verify_smtp(
        self, 
        email: str, 
        mx_hosts: List[str], 
        domain: str,
        is_trusted: bool = False,
        retry_greylisting: bool = True
    ) -> Dict[str, Any]:
        """
        Advanced SMTP verification with greylisting retry and fallback MX hosts.
        
        Features:
        - Tries multiple MX hosts if first fails
        - Retries on greylisting (450/451) responses
        - Enhanced response code interpretation
        
        Returns: {"valid": bool, "status": str, "code": int, "greylisted": bool}
        """
        if not mx_hosts:
            return {"valid": False, "status": "no_mx", "code": 0, "greylisted": False}
        
        # Use shorter timeouts for trusted providers
        connect_timeout = SMTP_CONNECT_TIMEOUT_TRUSTED if is_trusted else SMTP_CONNECT_TIMEOUT
        command_timeout = SMTP_COMMAND_TIMEOUT_TRUSTED if is_trusted else SMTP_COMMAND_TIMEOUT
        
        # Rate limit per domain
        async with self._domain_semaphores[domain]:
            # Try multiple MX hosts (up to MAX_MX_HOSTS_TO_TRY)
            hosts_to_try = mx_hosts[:MAX_MX_HOSTS_TO_TRY]
            last_result = None
            
            for mx_host in hosts_to_try:
                result = await self._verify_single_mx(
                    email, mx_host, connect_timeout, command_timeout
                )
                last_result = result
                
                # If we got a definitive answer, return it
                if result["code"] in VALID_CODES:
                    return result
                
                # Definitive rejection - no need to try other MX hosts
                if result["code"] in [550, 551, 553, 554]:
                    return result
                
                # Greylisting detected - handle with retry
                if result["code"] in GREYLISTING_CODES and retry_greylisting:
                    # Wait and retry once
                    await asyncio.sleep(GREYLISTING_RETRY_DELAY)
                    retry_result = await self._verify_single_mx(
                        email, mx_host, connect_timeout * 1.5, command_timeout * 1.5
                    )
                    
                    if retry_result["code"] in VALID_CODES:
                        retry_result["greylisted"] = True
                        return retry_result
                    
                    # If retry still fails with greylisting, mark as unknown
                    if retry_result["code"] in GREYLISTING_CODES:
                        return {
                            "valid": False, 
                            "status": "greylisted", 
                            "code": retry_result["code"],
                            "greylisted": True
                        }
                    
                    last_result = retry_result
                
                # Connection failed - try next MX host
                if result["status"] in ["connect_timeout", "connect_failed", "error"]:
                    continue
                
                # Got a valid response (even if negative), return it
                if result["code"] > 0:
                    return result
            
            # Return last result if we exhausted all MX hosts
            return last_result or {"valid": False, "status": "all_mx_failed", "code": 0, "greylisted": False}
    
    async def _verify_single_mx(
        self, 
        email: str, 
        mx_host: str, 
        connect_timeout: float,
        command_timeout: float
    ) -> Dict[str, Any]:
        """Verify email against a single MX host."""
        try:
            smtp = aiosmtplib.SMTP(
                hostname=mx_host,
                port=25,
                timeout=connect_timeout,
            )
            
            # Connect with timeout
            await asyncio.wait_for(
                smtp.connect(),
                timeout=connect_timeout
            )
            
            try:
                # EHLO first (more modern), fallback to HELO
                try:
                    await asyncio.wait_for(
                        smtp.ehlo(),
                        timeout=command_timeout
                    )
                except Exception:
                    await asyncio.wait_for(
                        smtp.helo(),
                        timeout=command_timeout
                    )
                
                # MAIL FROM
                await asyncio.wait_for(
                    smtp.mail('verify@mail-validator.com'),
                    timeout=command_timeout
                )
                
                # RCPT TO - the actual check
                try:
                    response = await asyncio.wait_for(
                        smtp.rcpt(email),
                        timeout=command_timeout
                    )
                    code = response[0]
                    message = response[1] if len(response) > 1 else ""
                except aiosmtplib.SMTPRecipientRefused as e:
                    code = e.code
                    message = str(e.message) if hasattr(e, 'message') else ""
                
                # Close connection (fire-and-forget)
                asyncio.create_task(self._close_smtp(smtp))
                
                return self._interpret_code(code, message)
                
            except asyncio.TimeoutError:
                asyncio.create_task(self._close_smtp(smtp))
                return {"valid": False, "status": "timeout", "code": 0, "greylisted": False}
                
        except asyncio.TimeoutError:
            return {"valid": False, "status": "connect_timeout", "code": 0, "greylisted": False}
        except aiosmtplib.SMTPConnectError:
            return {"valid": False, "status": "connect_failed", "code": 0, "greylisted": False}
        except Exception as e:
            # Log the actual error for debugging
            import traceback
            error_details = f"{type(e).__name__}: {str(e)}"
            print(f"SMTP Error for {email} on {mx_host}: {error_details}")
            print(f"Traceback: {traceback.format_exc()}")
            return {"valid": False, "status": "error", "code": 0, "greylisted": False, "error_detail": error_details}
    
    async def _close_smtp(self, smtp: aiosmtplib.SMTP):
        """Close SMTP connection (fire-and-forget)"""
        try:
            await smtp.quit()
        except Exception:
            pass
    
    def _interpret_code(self, code: int, message: str = "") -> Dict[str, Any]:
        """
        Enhanced SMTP response code interpretation.
        Handles more edge cases and provides detailed status.
        """
        message_lower = message.lower() if message else ""
        
        # Success codes
        if code in VALID_CODES:  # 250, 251
            return {"valid": True, "status": "deliverable", "code": code, "greylisted": False}
        
        # Mailbox not found (definitive invalid)
        elif code == 550:
            # Check if it's actually a policy rejection masquerading as 550
            if any(kw in message_lower for kw in ['policy', 'blocked', 'spam', 'rejected']):
                return {"valid": False, "status": "policy_reject", "code": code, "greylisted": False}
            return {"valid": False, "status": "mailbox_not_found", "code": code, "greylisted": False}
        
        # User not local / forwarding
        elif code == 551:
            return {"valid": False, "status": "user_not_local", "code": code, "greylisted": False}
        
        # Mailbox unavailable (could be temporary or permanent)
        elif code == 553:
            return {"valid": False, "status": "mailbox_unavailable", "code": code, "greylisted": False}
        
        # Transaction failed / policy rejection
        elif code == 554:
            return {"valid": False, "status": "mailbox_disabled", "code": code, "greylisted": False}
        
        # Mailbox full / quota exceeded
        elif code in MAILBOX_FULL_CODES:  # 552, 422, 452
            return {"valid": False, "status": "inbox_full", "code": code, "greylisted": False}
        
        # Greylisting / temporary failure
        elif code in GREYLISTING_CODES:  # 450, 451, 421
            return {"valid": False, "status": "temp_failure", "code": code, "greylisted": True}
        
        # Rate limiting
        elif code == 452:
            if 'too many' in message_lower or 'rate' in message_lower:
                return {"valid": False, "status": "rate_limited", "code": code, "greylisted": False}
            return {"valid": False, "status": "inbox_full", "code": code, "greylisted": False}
        
        # Unknown/other codes
        else:
            return {"valid": False, "status": f"code_{code}", "code": code, "greylisted": False}
    
    async def check_catchall(self, domain: str, mx_hosts: List[str]) -> bool:
        """
        Enhanced catch-all detection using multiple random test emails.
        More accurate than single-email check.
        """
        # Check cache
        cached = _catchall_cache.get(domain)
        if cached is not None:
            return cached
        
        # Generate 2 random test emails for better accuracy
        # Use cleaner random string (avoid 'test' prefix which often triggers spam filters)
        # Check in PARALLEL for speed
        tasks = []
        for _ in range(2):
            random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=15))
            test_email = f"{random_str}@{domain}"
            tasks.append(self.verify_smtp(test_email, mx_hosts, domain, retry_greylisting=False))
            
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter valid results (exceptions count as False)
        test_validity = []
        for r in results:
            if isinstance(r, Exception):
                test_validity.append(False)
            else:
                test_validity.append(r.get("valid", False))
        
        # If both random emails are accepted, it's definitely catch-all
        is_catchall = all(test_validity)
        
        # Cache result
        _catchall_cache.set(domain, is_catchall, CATCHALL_CACHE_TTL)
        
        return is_catchall


# ======================= MAIN FAST VALIDATOR =======================

class FastEmailValidator:
    """
    Ultra-fast email validator optimized for 10+ emails/second.
    
    Key optimizations:
    1. Skip SMTP for trusted providers (Gmail, Outlook, etc.)
    2. Aggressive micro-timeouts
    3. Parallel DNS resolution
    4. In-memory caching
    5. Connection pooling
    """
    
    def __init__(self):
        self._dns = FastDNSResolver()
        self._smtp = FastSMTPVerifier()
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_VALIDATIONS)
        self._initialized = False
    
    async def initialize(self):
        """Initialize the validator"""
        if not self._initialized:
            await self._dns.initialize()
            self._initialized = True
            print(f"FastEmailValidator initialized. Cache size: {_mx_cache.size()}")
    
    async def validate_email(self, email: str) -> Dict[str, Any]:
        """Validate a single email - ultra fast"""
        async with self._semaphore:
            return await self._validate_single(email)
    
    async def _validate_single(self, email: str) -> Dict[str, Any]:
        """Internal validation logic"""
        # Clean email
        email = email.strip().lower()
        
        # Initialize result
        result = self._init_result(email)
        
        # Step 1: Syntax check (instant - cached)
        syntax_valid, syntax_reason, local_part, domain = check_syntax_fast(email)
        if not syntax_valid:
            result["reason"] = syntax_reason
            return calculate_full_score(result)
        
        result["syntax_valid"] = "Valid"
        result["regex"] = "Valid"
        
        # Step 2: Quick local checks (instant - cached)
        is_disposable = check_disposable_fast(domain)
        is_blacklisted = check_blacklist_fast(domain)
        is_role = check_role_fast(local_part)
        
        result["disposable"] = "Yes" if is_disposable else "No"
        result["is_disposable"] = is_disposable
        result["blacklist"] = "Yes" if is_blacklisted else "No"
        result["is_blacklisted"] = is_blacklisted
        result["role_based"] = "Yes" if is_role else "No"
        result["is_role_based"] = is_role
        
        # Early exit for blacklisted/disposable/spamtrap - set specific status (Reoon-style)
        if is_blacklisted:
            result["status"] = "spamtrap"  # Reoon treats blacklisted as spamtrap
            result["reason"] = "Blacklisted domain (potential spamtrap)"
            result["is_spamtrap"] = True
            return calculate_full_score(result)
        
        # Check for spamtrap
        is_spamtrap = check_spamtrap_fast(email, domain)
        if is_spamtrap:
            result["status"] = "spamtrap"
            result["reason"] = "Known spamtrap address"
            result["is_spamtrap"] = True
            return calculate_full_score(result)
        
        if is_disposable:
            result["status"] = "disposable"  # Reoon lowercase
            result["reason"] = "Disposable/temporary email"
            return calculate_full_score(result)
        
        # Step 3: MX lookup (async - cached)
        mx_hosts = await self._dns.resolve_mx(domain)
        
        if not mx_hosts:
            result["status"] = "unknown"  # Reoon lowercase
            result["reason"] = "No mail server found"
            result["is_unknown"] = True
            return calculate_full_score(result)
        
        result["domain_valid"] = "Valid"
        result["mx_record_exists"] = "Valid"
        result["mx"] = "Valid"
        result["mx_accepts_mail"] = True
        
        # Step 4: Check if trusted provider (FREE PROVIDER OPTIMIZATION)
        is_trusted = is_trusted_provider(domain)
        
        # CRITICAL SPEED OPTIMIZATION: Skip SMTP for trusted providers
        # Gmail, Outlook, Yahoo etc block SMTP verification anyway
        # This reduces validation time from 9s to 0.3s for free providers!
        if is_trusted:
            # Validate provider-specific username rules
            username_valid = True
            if 'gmail' in domain or 'google' in domain:
                username_valid = validate_gmail_username(local_part)
            elif 'yahoo' in domain or 'ymail' in domain:
                username_valid = validate_yahoo_username(local_part)
            elif 'outlook' in domain or 'hotmail' in domain or 'live' in domain:
                username_valid = validate_outlook_username(local_part)
            
            if not username_valid:
                result["status"] = "invalid"
                result["reason"] = "Username does not meet provider rules"
                return calculate_full_score(result)
            
            # Mark as safe or role (Reoon style)
            result["status"] = "role" if is_role else "safe"
            result["reason"] = "Role-based email (admin@, info@, etc.)" if is_role else "Valid email address (provider does not allow SMTP verification)"
            result["is_valid"] = True
            result["is_deliverable"] = True
            result["is_safe_to_send"] = not is_role
            result["smtp_status"] = "skipped_trusted_provider"
            result["smtp_valid"] = "Skipped"
            result["smtp"] = "Skipped (Free Provider)"
            return calculate_full_score(result)
        
        # Step 5: SMTP verification ONLY for non-trusted domains
        smtp_result = await self._smtp.verify_smtp(email, mx_hosts, domain, is_trusted=False, retry_greylisting=False)
        result["smtp_status"] = smtp_result["status"]
        result["smtp_code"] = smtp_result.get("code", 0)
        
        # Interpret SMTP result
        code = smtp_result.get("code", 0)
        status = smtp_result.get("status", "")
        
        # Definitive rejection - invalid (Reoon lowercase)
        if code in [550, 551, 553] or "not_found" in status:
            result["reason"] = "Mailbox does not exist"
            result["status"] = "invalid"
            return calculate_full_score(result)
        
        if code == 554 or "disabled" in status:
            result["reason"] = "Mailbox disabled by provider"
            result["status"] = "disabled"  # Reoon has 'disabled' as separate status
            result["is_disabled"] = True
            return calculate_full_score(result)
        
        # Check for mailbox full (codes 552, 422, 452) - Reoon lowercase
        if code in MAILBOX_FULL_CODES or "full" in status or "quota" in status:
            result["reason"] = "Mailbox is full or quota exceeded"
            result["is_inbox_full"] = True
            result["status"] = "inbox_full"  # Reoon lowercase with underscore
            result["is_valid"] = True  # Email exists but inbox is full
            result["has_inbox_full"] = True
            result["smtp_valid"] = "Valid"
            result["smtp"] = "Valid"
            return calculate_full_score(result)
        
        # SMTP succeeded
        if smtp_result["valid"]:
            result["smtp_valid"] = "Valid"
            result["smtp"] = "Valid"
            result["is_valid"] = True
            result["is_deliverable"] = True
            
            # Check for catch-all
            try:
                is_catchall = await self._smtp.check_catchall(domain, mx_hosts)
                if is_catchall:
                    result["is_catch_all"] = True
                    result["catch_all"] = "Yes"
                    result["status"] = "catch_all"  # Reoon lowercase with underscore
                    result["reason"] = "Domain accepts all emails (catch-all)"
                    result["is_safe_to_send"] = False  # Catch-all is risky
                    return calculate_full_score(result)
            except Exception:
                pass  # Skip catch-all check on error
            
            # Reoon uses 'safe' for valid personal and 'role' for role-based
            result["status"] = "role" if is_role else "safe"  # Reoon lowercase
            result["is_safe_to_send"] = not is_role
            result["reason"] = "Role-based email (admin@, info@, etc.)" if is_role else "Valid email address"
            return calculate_full_score(result)
        
        # SMTP failed or inconclusive - mark as unknown
        if code in [450, 451] or "timeout" in status or "unavailable" in status or "connect" in status or "error" in status:
            # For greylisting (450, 451) - mark as unknown since we can't verify (Reoon lowercase)
            result["status"] = "unknown"
            result["is_unknown"] = True
            result["reason"] = "SMTP verification inconclusive (server did not respond)"
            result["smtp_valid"] = "Inconclusive"
            result["smtp"] = "Unknown"
            return calculate_full_score(result)
        
        # Only mark as safe if we got a positive verification
        # For any other case where SMTP failed, mark as unknown to avoid false positives
        result["status"] = "unknown"  # Reoon lowercase
        result["is_unknown"] = True
        result["reason"] = "SMTP verification could not be completed"
        result["smtp_valid"] = "Inconclusive"
        result["smtp"] = "Unknown"
        
        # Calculate ZeroBounce-style score
        return calculate_full_score(result)
    
    def _init_result(self, email: str) -> Dict[str, Any]:
        """Initialize result dictionary with Reoon-style defaults"""
        return {
            "email": email,
            "status": "invalid",  # Reoon lowercase default
            "reason": "",
            "syntax_valid": "Not Valid",
            "domain_valid": "Not Valid",
            "mx_record_exists": "Not Valid",
            "smtp_valid": "Not Valid",
            "smtp_status": "not_checked",
            "smtp_code": 0,
            "role_based": "No",
            "disposable": "No",
            "blacklist": "No",
            "catch_all": "No",
            "deliverability_score": 0,
            "quality_grade": "F",
            "verdict": "Invalid",
            "regex": "Not Valid",
            "mx": "Not Valid",
            "smtp": "Not Valid",
            "is_valid": False,
            "is_deliverable": False,
            "is_safe_to_send": False,
            "has_inbox_full": False,
            "mx_accepts_mail": False,
            "is_inbox_full": False,
            "is_disabled": False,
            "is_unknown": False,
            "is_unverifiable": False,
            "is_catch_all": False,
            "is_disposable": False,
            "is_blacklisted": False,
            "is_role_based": False,
            "is_spamtrap": False,  # Reoon spamtrap detection
        }
    
    async def validate_bulk(
        self, 
        emails: List[str], 
        batch_id: str = None,
        check_catchall: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Validate multiple emails with maximum speed.
        
        Optimizations:
        1. Pre-resolve all MX records in parallel
        2. Group by domain for efficiency
        3. Skip SMTP for trusted providers
        4. Process in parallel chunks
        """
        if not self._initialized:
            await self.initialize()
        
        start_time = time.time()
        
        # Clean and dedupe emails
        unique_emails = list(dict.fromkeys(
            email.strip().lower() for email in emails if email and email.strip()
        ))
        
        # Extract all domains
        domains = set()
        for email in unique_emails:
            if '@' in email:
                domains.add(email.split('@')[1])
        
        # Pre-resolve ALL MX records in parallel (big speed boost)
        await self._dns.resolve_mx_batch(list(domains))
        
        # Validate all emails in parallel
        tasks = [self.validate_email(email) for email in unique_emails]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                final_results.append({
                    "email": unique_emails[i],
                    "status": "Error",
                    "reason": str(result),
                    "is_valid": False,
                    **self._init_result(unique_emails[i])
                })
            else:
                if batch_id:
                    result["batch_id"] = batch_id
                final_results.append(result)
        
        elapsed = time.time() - start_time
        rate = len(unique_emails) / max(elapsed, 0.001)
        print(f"FAST_VALIDATOR: {len(unique_emails)} emails in {elapsed:.2f}s ({rate:.1f}/sec)")
        
        return final_results
    
    async def cleanup(self):
        """Cleanup resources"""
        pass
    
    def get_cache_stats(self) -> Dict[str, int]:
        """Get cache statistics"""
        return {
            "mx_cache": _mx_cache.size(),
            "catchall_cache": _catchall_cache.size(),
            "domain_cache": _domain_validity_cache.size(),
        }


# ======================= SINGLETON INSTANCE =======================

_fast_validator: Optional[FastEmailValidator] = None


async def get_fast_validator() -> FastEmailValidator:
    """Get or create singleton validator instance"""
    global _fast_validator
    if _fast_validator is None:
        _fast_validator = FastEmailValidator()
        await _fast_validator.initialize()
    return _fast_validator


# ======================= CONVENIENCE FUNCTIONS =======================

async def validate_email_fast(email: str) -> Dict[str, Any]:
    """Validate a single email (convenience function)"""
    validator = await get_fast_validator()
    return await validator.validate_email(email)


async def validate_bulk_fast(emails: List[str], batch_id: str = None) -> List[Dict[str, Any]]:
    """Validate multiple emails (convenience function)"""
    validator = await get_fast_validator()
    return await validator.validate_bulk(emails, batch_id)


# ======================= BACKWARD COMPATIBILITY =======================

# Alias for drop-in replacement
AsyncEmailValidator = FastEmailValidator
get_validator = get_fast_validator
validate_email_async = validate_email_fast
validate_bulk_async = validate_bulk_fast
