"""
High-Performance Async Email Validator

This module provides a complete async-first email validation engine with:
- Async DNS resolution with TTL-based caching
- Connection-pooled async SMTP verification
- Bounded concurrency with semaphores
- Domain-level throttling for major providers
- Micro-timeouts for aggressive cancellation
- Chunked batch processing with back-pressure
- Real-time performance metrics
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
from contextlib import asynccontextmanager

# Import scoring module for ZeroBounce-style scoring
from .scoring import calculate_full_score, calculate_score, get_quality_grade

# ======================= CONFIGURATION =======================

# Timeouts (ultra-aggressive for 10+ emails/sec)
DNS_TIMEOUT = 0.3  # seconds - very fast
SMTP_CONNECT_TIMEOUT = 0.5  # seconds - fast connect
SMTP_RESPONSE_TIMEOUT = 0.3  # seconds - fast response

# Concurrency limits (maximized for extreme performance)
MAX_CONCURRENT_VALIDATIONS = 1000  # Increased semaphore limit
CHUNK_SIZE = 500  # Emails per batch (increased)
MAX_QUEUE_SIZE = 2000  # Back-pressure threshold

# Connection pool settings (optimized for high throughput)
POOL_SIZE_PER_DOMAIN = 15  # Connections per domain (increased)
POOL_MAX_DOMAINS = 150  # Max domains to keep pools for
CONNECTION_TTL = 180  # Seconds before connection expires

# Major providers that BLOCK SMTP verification - trust MX lookup instead
# These providers actively reject/timeout SMTP verification attempts
TRUSTED_PROVIDERS = {
    "gmail.com", "googlemail.com",
    "outlook.com", "hotmail.com", "live.com", "msn.com", "outlook.in",
    "yahoo.com", "yahoo.co.uk", "yahoo.co.in", "yahoo.in", "ymail.com", "rocketmail.com",
    "icloud.com", "me.com", "mac.com",
    "aol.com", "aim.com",
    "protonmail.com", "proton.me", "pm.me",
    "zoho.com", "zohomail.com", "zoho.in",
    "fastmail.com", "fastmail.fm",
    "tutanota.com", "tutanota.de", "tuta.io",
    "gmx.com", "gmx.net", "gmx.de",
    "mail.com", "email.com",
    "yandex.com", "yandex.ru",
    "rediffmail.com",
}

# Domain throttling (requests per second)
DOMAIN_RATE_LIMITS = {
    "gmail.com": 10,
    "googlemail.com": 10,
    "outlook.com": 10,
    "hotmail.com": 10,
    "live.com": 10,
    "yahoo.com": 8,
    "yahoo.co.uk": 8,
    "aol.com": 8,
    "icloud.com": 8,
    "me.com": 8,
}
DEFAULT_RATE_LIMIT = 20  # For other domains

# Top domains to warm-up
TOP_DOMAINS_WARMUP = [
    "gmail.com", "yahoo.com", "outlook.com", "hotmail.com",
    "icloud.com", "aol.com", "live.com", "msn.com"
]

# Cache TTL
MX_CACHE_TTL = 300  # 5 minutes
CATCHALL_CACHE_TTL = 300  # 5 minutes


# ======================= DATA CLASSES =======================

@dataclass
class ValidationMetrics:
    """Track performance metrics per domain"""
    dns_times: List[float] = field(default_factory=list)
    smtp_connect_times: List[float] = field(default_factory=list)
    smtp_response_times: List[float] = field(default_factory=list)
    total_validations: int = 0
    successful_validations: int = 0
    failed_validations: int = 0
    timeouts: int = 0
    
    def avg_dns_time(self) -> float:
        return sum(self.dns_times) / len(self.dns_times) if self.dns_times else 0
    
    def avg_smtp_time(self) -> float:
        times = self.smtp_connect_times + self.smtp_response_times
        return sum(times) / len(times) if times else 0


@dataclass 
class CacheEntry:
    """Cache entry with TTL"""
    value: Any
    expires_at: float
    
    def is_valid(self) -> bool:
        return time.time() < self.expires_at


@dataclass
class PooledConnection:
    """SMTP connection with metadata"""
    connection: aiosmtplib.SMTP
    created_at: float
    domain: str
    in_use: bool = False
    
    def is_expired(self) -> bool:
        return time.time() - self.created_at > CONNECTION_TTL


# ======================= LOAD DOMAIN LISTS =======================

def load_domain_list(filename: str) -> set:
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
    except Exception as e:
        print(f"Warning: Could not load {filename}: {e}")
    return domains


# Load lists at module level
DISPOSABLE_DOMAINS = load_domain_list('disposable_domains.txt')
BLACKLIST_DOMAINS = load_domain_list('blacklist_domains.txt')

# Role-based email prefixes
ROLE_EMAILS = {
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
}


# ======================= MX CACHE =======================

class MXCache:
    """Thread-safe in-memory cache for MX records"""
    
    def __init__(self):
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = asyncio.Lock()
    
    async def get(self, domain: str) -> Optional[List[str]]:
        async with self._lock:
            entry = self._cache.get(domain)
            if entry and entry.is_valid():
                return entry.value
            elif entry:
                del self._cache[domain]
            return None
    
    async def set(self, domain: str, mx_hosts: List[str], ttl: float = MX_CACHE_TTL):
        async with self._lock:
            self._cache[domain] = CacheEntry(
                value=mx_hosts,
                expires_at=time.time() + ttl
            )
    
    async def clear_expired(self):
        async with self._lock:
            now = time.time()
            expired = [k for k, v in self._cache.items() if now >= v.expires_at]
            for k in expired:
                del self._cache[k]
    
    def size(self) -> int:
        return len(self._cache)


# ======================= SMTP CONNECTION POOL =======================

class SMTPConnectionPool:
    """Connection pool for SMTP servers, organized by domain"""
    
    def __init__(self):
        self._pools: Dict[str, List[PooledConnection]] = defaultdict(list)
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._global_lock = asyncio.Lock()
    
    async def get_connection(self, mx_host: str, domain: str) -> Optional[aiosmtplib.SMTP]:
        """Get an available connection from pool or create new one"""
        async with self._locks[domain]:
            pool = self._pools[domain]
            
            # Find available non-expired connection
            for conn in pool:
                if not conn.in_use and not conn.is_expired():
                    conn.in_use = True
                    return conn.connection
            
            # Remove expired connections
            self._pools[domain] = [c for c in pool if not c.is_expired()]
            
            # Create new connection if pool not full
            if len(self._pools[domain]) < POOL_SIZE_PER_DOMAIN:
                try:
                    smtp = aiosmtplib.SMTP(
                        hostname=mx_host,
                        port=25,
                        timeout=SMTP_CONNECT_TIMEOUT
                    )
                    await asyncio.wait_for(
                        smtp.connect(),
                        timeout=SMTP_CONNECT_TIMEOUT
                    )
                    
                    pooled = PooledConnection(
                        connection=smtp,
                        created_at=time.time(),
                        domain=domain,
                        in_use=True
                    )
                    self._pools[domain].append(pooled)
                    return smtp
                except Exception:
                    return None
            
            return None
    
    async def release_connection(self, smtp: aiosmtplib.SMTP, domain: str):
        """Return connection to pool"""
        async with self._locks[domain]:
            for conn in self._pools[domain]:
                if conn.connection is smtp:
                    conn.in_use = False
                    break
    
    async def close_connection(self, smtp: aiosmtplib.SMTP, domain: str):
        """Close and remove connection from pool"""
        async with self._locks[domain]:
            self._pools[domain] = [
                c for c in self._pools[domain] 
                if c.connection is not smtp
            ]
            try:
                await smtp.quit()
            except Exception:
                pass
    
    async def close_all(self):
        """Close all connections"""
        async with self._global_lock:
            for domain, pool in self._pools.items():
                for conn in pool:
                    try:
                        await conn.connection.quit()
                    except Exception:
                        pass
            self._pools.clear()
    
    def stats(self) -> Dict[str, int]:
        return {domain: len(pool) for domain, pool in self._pools.items()}


# ======================= DOMAIN THROTTLER =======================

class DomainThrottler:
    """Rate limiter per domain to prevent IP blocking"""
    
    def __init__(self):
        self._last_request: Dict[str, float] = {}
        self._locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
    
    def _get_interval(self, domain: str) -> float:
        """Get minimum interval between requests for domain"""
        rate = DOMAIN_RATE_LIMITS.get(domain, DEFAULT_RATE_LIMIT)
        return 1.0 / rate
    
    async def acquire(self, domain: str):
        """Wait if necessary before making request to domain"""
        async with self._locks[domain]:
            now = time.time()
            last = self._last_request.get(domain, 0)
            interval = self._get_interval(domain)
            
            wait_time = interval - (now - last)
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            
            self._last_request[domain] = time.time()


# ======================= SYNTAX VALIDATION =======================

def check_rfc_syntax(email: str) -> Tuple[bool, str]:
    """RFC 5322 compliant email syntax validation"""
    if not email or not isinstance(email, str):
        return False, "Empty or invalid email"
    
    if len(email) > 320:
        return False, "Email too long"
    
    if email.count('@') != 1:
        return False, "Must contain exactly one @ symbol"
    
    local_part, domain_part = email.split('@')
    
    if not local_part or len(local_part) > 64:
        return False, "Invalid local part length"
    
    if not domain_part or len(domain_part) > 255:
        return False, "Invalid domain length"
    
    if '..' in email:
        return False, "Consecutive dots not allowed"
    
    if local_part.startswith('.') or local_part.endswith('.'):
        return False, "Local part cannot start or end with dot"
    
    if domain_part.startswith('.') or domain_part.endswith('.'):
        return False, "Domain cannot start or end with dot"
    
    local_pattern = r"^[a-zA-Z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-zA-Z0-9!#$%&'*+/=?^_`{|}~-]+)*$"
    if not re.match(local_pattern, local_part):
        return False, "Invalid characters in local part"
    
    domain_pattern = r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?\.)+[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?$"
    if not re.match(domain_pattern, domain_part):
        return False, "Invalid domain format"
    
    tld = domain_part.split('.')[-1]
    if len(tld) < 2:
        return False, "Invalid TLD"
    
    if ' ' in email:
        return False, "Spaces not allowed"
    
    return True, "Valid syntax"


def check_disposable(domain: str) -> bool:
    """Check if domain is disposable"""
    return domain.lower() in DISPOSABLE_DOMAINS


def check_blacklist(domain: str) -> bool:
    """Check if domain is blacklisted"""
    return domain.lower() in BLACKLIST_DOMAINS


def is_role_based(email: str) -> bool:
    """Check if email is role-based"""
    username = email.split('@')[0].lower()
    username_normalized = username.replace('.', '').replace('-', '')
    return username in ROLE_EMAILS or username_normalized in ROLE_EMAILS


# ======================= ASYNC EMAIL VALIDATOR =======================

class AsyncEmailValidator:
    """
    High-performance async email validator.
    
    Features:
    - Async DNS with caching
    - Connection-pooled SMTP
    - Bounded concurrency
    - Domain throttling
    - Aggressive timeouts
    - Performance metrics
    """
    
    def __init__(self):
        self._mx_cache = MXCache()
        self._catchall_cache: Dict[str, CacheEntry] = {}
        self._connection_pool = SMTPConnectionPool()
        self._throttler = DomainThrottler()
        self._semaphore = asyncio.Semaphore(MAX_CONCURRENT_VALIDATIONS)
        self._metrics: Dict[str, ValidationMetrics] = defaultdict(ValidationMetrics)
        self._dns_resolver: Optional[aiodns.DNSResolver] = None
        self._initialized = False
        self._slow_domains: Set[str] = set()  # Domains that timeout frequently
    
    async def initialize(self):
        """Initialize resolver and warm up caches"""
        if self._initialized:
            return
        
        self._dns_resolver = aiodns.DNSResolver(timeout=DNS_TIMEOUT)
        
        # Warm-up: Pre-resolve MX for top domains
        warmup_tasks = [
            self._warmup_domain(domain) 
            for domain in TOP_DOMAINS_WARMUP
        ]
        await asyncio.gather(*warmup_tasks, return_exceptions=True)
        
        self._initialized = True
        print(f"AsyncEmailValidator initialized. MX cache: {self._mx_cache.size()} domains")
    
    async def _warmup_domain(self, domain: str):
        """Pre-resolve MX records for a domain"""
        try:
            mx_hosts = await self._resolve_mx(domain)
            if mx_hosts:
                print(f"Warmed up: {domain} -> {mx_hosts[0]}")
        except Exception as e:
            print(f"Warmup failed for {domain}: {e}")
    
    async def _resolve_mx(self, domain: str) -> List[str]:
        """Resolve MX records with caching"""
        # Check cache first
        cached = await self._mx_cache.get(domain)
        if cached is not None:
            return cached
        
        start = time.time()
        try:
            result = await asyncio.wait_for(
                self._dns_resolver.query(domain, 'MX'),
                timeout=DNS_TIMEOUT
            )
            # Sort by priority
            mx_hosts = sorted(result, key=lambda x: x.priority)
            mx_list = [str(mx.host).rstrip('.') for mx in mx_hosts]
            
            # Cache result
            await self._mx_cache.set(domain, mx_list)
            
            # Record metrics
            self._metrics[domain].dns_times.append(time.time() - start)
            
            return mx_list
        except asyncio.TimeoutError:
            self._metrics[domain].timeouts += 1
            return []
        except aiodns.error.DNSError:
            return []
        except Exception:
            return []
    
    async def _check_smtp(
        self, 
        email: str, 
        mx_hosts: List[str], 
        domain: str
    ) -> Dict[str, Any]:
        """Perform async SMTP verification with connection pooling"""
        if not mx_hosts:
            return {"valid": False, "status": "no_mx_records", "code": 0}
        
        # Apply throttling
        await self._throttler.acquire(domain)
        
        # Try first 2 MX hosts
        for mx_host in mx_hosts[:2]:
            smtp = None
            try:
                connect_start = time.time()
                
                # Try to get pooled connection
                smtp = await self._connection_pool.get_connection(mx_host, domain)
                
                if smtp is None:
                    # Create new connection without pooling
                    smtp = aiosmtplib.SMTP(
                        hostname=mx_host,
                        port=25,
                        timeout=SMTP_CONNECT_TIMEOUT
                    )
                    await asyncio.wait_for(
                        smtp.connect(),
                        timeout=SMTP_CONNECT_TIMEOUT
                    )
                
                self._metrics[domain].smtp_connect_times.append(time.time() - connect_start)
                
                # HELO
                await asyncio.wait_for(
                    smtp.helo('mail-validator.com'),
                    timeout=SMTP_RESPONSE_TIMEOUT
                )
                
                # MAIL FROM
                await asyncio.wait_for(
                    smtp.mail('verify@mail-validator.com'),
                    timeout=SMTP_RESPONSE_TIMEOUT
                )
                
                # RCPT TO - the actual mailbox check
                response_start = time.time()
                try:
                    response = await asyncio.wait_for(
                        smtp.rcpt(email),
                        timeout=SMTP_RESPONSE_TIMEOUT
                    )
                    code = response[0]
                except aiosmtplib.SMTPRecipientRefused as e:
                    code = e.code
                
                self._metrics[domain].smtp_response_times.append(time.time() - response_start)
                
                # Return connection to pool
                await self._connection_pool.release_connection(smtp, domain)
                
                # Interpret response code
                if code == 250:
                    return {"valid": True, "status": "deliverable", "code": code}
                elif code == 550:
                    return {"valid": False, "status": "mailbox_not_found", "code": code}
                elif code == 551:
                    return {"valid": False, "status": "user_not_local", "code": code}
                elif code == 552:
                    return {"valid": False, "status": "inbox_full", "code": code}
                elif code == 553:
                    return {"valid": False, "status": "mailbox_name_invalid", "code": code}
                elif code == 554:
                    return {"valid": False, "status": "mailbox_disabled", "code": code}
                elif code in [450, 451, 452]:
                    return {"valid": False, "status": "temporary_failure", "code": code}
                elif code == 421:
                    return {"valid": False, "status": "service_unavailable", "code": code}
                else:
                    return {"valid": False, "status": f"smtp_code_{code}", "code": code}
                    
            except asyncio.TimeoutError:
                self._metrics[domain].timeouts += 1
                if smtp:
                    await self._connection_pool.close_connection(smtp, domain)
                continue
            except aiosmtplib.SMTPException:
                if smtp:
                    await self._connection_pool.close_connection(smtp, domain)
                continue
            except Exception:
                if smtp:
                    await self._connection_pool.close_connection(smtp, domain)
                continue
        
        return {"valid": False, "status": "connection_failed", "code": 0}
    
    async def _check_catchall(self, domain: str, mx_hosts: List[str]) -> bool:
        """Check if domain is catch-all (accepts all addresses)"""
        # Check cache
        cache_key = f"catchall_{domain}"
        if cache_key in self._catchall_cache:
            entry = self._catchall_cache[cache_key]
            if entry.is_valid():
                return entry.value
        
        # Test with random non-existent email
        random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=20))
        test_email = f"{random_str}@{domain}"
        
        result = await self._check_smtp(test_email, mx_hosts[:1], domain)
        is_catchall = result["valid"]
        
        # Cache result
        self._catchall_cache[cache_key] = CacheEntry(
            value=is_catchall,
            expires_at=time.time() + CATCHALL_CACHE_TTL
        )
        
        return is_catchall
    
    async def validate_email(self, email: str) -> Dict[str, Any]:
        """Validate a single email address"""
        async with self._semaphore:
            return await self._validate_single(email)
    
    async def _validate_single(self, email: str) -> Dict[str, Any]:
        """Internal validation logic for single email"""
        email = email.strip().lower()
        
        # Initialize result
        result = {
            "email": email,
            "status": "Invalid",
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
            "is_catch_all": False,
            "is_disposable": False,
            "is_blacklisted": False,
            "is_role_based": False,
        }
        
        # Step 1: Syntax validation (instant, no I/O)
        syntax_valid, syntax_reason = check_rfc_syntax(email)
        if not syntax_valid:
            result["reason"] = syntax_reason
            return calculate_full_score(result)
        
        result["syntax_valid"] = "Valid"
        result["regex"] = "Valid"
        
        # Extract domain
        if '@' not in email:
            result["reason"] = "Invalid email format"
            return calculate_full_score(result)
        
        domain = email.split('@')[1]
        
        # Step 2: Quick checks (instant, no I/O)
        is_disposable = check_disposable(domain)
        is_blacklisted = check_blacklist(domain)
        is_role = is_role_based(email)
        
        if is_disposable:
            result["disposable"] = "Yes"
            result["is_disposable"] = True
        if is_blacklisted:
            result["blacklist"] = "Yes"
            result["is_blacklisted"] = True
        if is_role:
            result["role_based"] = "Yes"
            result["is_role_based"] = True
        
        # Step 3: MX lookup (async)
        mx_hosts = await self._resolve_mx(domain)
        
        if not mx_hosts:
            result["status"] = "Unknown"
            result["reason"] = "No mail server found"
            result["is_unknown"] = True
            return calculate_full_score(result)
        
        result["domain_valid"] = "Valid"
        result["mx_record_exists"] = "Valid"
        result["mx"] = "Valid"
        
        # Skip SMTP for known-bad domains - set specific status
        if is_blacklisted:
            result["status"] = "Blacklisted"
            result["reason"] = "Blacklisted domain"
            return calculate_full_score(result)
        
        if is_disposable:
            result["status"] = "Disposable"
            result["reason"] = "Disposable/temporary email"
            return calculate_full_score(result)
        
        # Step 4: SMTP verification (async) - try for ALL domains including trusted
        smtp_result = await self._check_smtp(email, mx_hosts, domain)
        result["smtp_status"] = smtp_result["status"]
        result["smtp_code"] = smtp_result.get("code", 0)
        result["mx_accepts_mail"] = True  # MX exists
        
        # Check if SMTP explicitly rejected the mailbox (definitive invalid)
        smtp_code = smtp_result.get("code", 0)
        smtp_status = smtp_result.get("status", "")
        
        # Definitive rejection codes - mailbox does NOT exist
        if smtp_code in [550, 551, 553] or "mailbox_not_found" in smtp_status:
            result["reason"] = "Mailbox does not exist"
            result["status"] = "Invalid"
            result["smtp"] = "Not Valid"
            self._metrics[domain].total_validations += 1
            self._metrics[domain].failed_validations += 1
            return calculate_full_score(result)
        
        if smtp_result["valid"]:
            # SMTP verification succeeded - mailbox confirmed
            result["smtp_valid"] = "Valid"
            result["smtp"] = "Valid"
            result["is_deliverable"] = True
            result["is_safe_to_send"] = not is_role
            result["status"] = "Role-Based" if is_role else "Valid"
            result["reason"] = "Role-based email" if is_role else "Deliverable"
            result["is_valid"] = True
            self._metrics[domain].total_validations += 1
            self._metrics[domain].successful_validations += 1
            return calculate_full_score(result)
        
        # SMTP failed but not with definitive rejection
        # For TRUSTED PROVIDERS only: mark as "Valid" (Optimistic - they often block SMTP)
        if domain in TRUSTED_PROVIDERS:
            result["status"] = "Role-Based" if is_role else "Valid"
            result["is_valid"] = True
            result["is_deliverable"] = True
            result["is_safe_to_send"] = not is_role
            result["smtp_valid"] = "Unknown"
            result["smtp"] = "Valid"
            result["reason"] = "Role-based email" if is_role else "Valid (Trusted Provider)"
            result["is_unknown"] = False
            self._metrics[domain].total_validations += 1
            self._metrics[domain].successful_validations += 1
            return calculate_full_score(result)
        
        result["verdict"] = result["status"]
        self._metrics[domain].total_validations += 1
        if result["is_valid"]:
            self._metrics[domain].successful_validations += 1
        else:
            self._metrics[domain].failed_validations += 1
        
        return calculate_full_score(result)
    
    async def validate_bulk(
        self, 
        emails: List[str], 
        batch_id: str = None
    ) -> List[Dict[str, Any]]:
        """
        Validate multiple emails with optimal performance.
        
        Features:
        - Chunked processing
        - Bounded concurrency
        - Domain grouping for cache efficiency
        """
        if not self._initialized:
            await self.initialize()
        
        # Remove duplicates while preserving order
        unique_emails = list(dict.fromkeys(email.strip().lower() for email in emails if email.strip()))
        
        # Group by domain for efficiency
        domain_groups: Dict[str, List[str]] = defaultdict(list)
        for email in unique_emails:
            if '@' in email:
                domain = email.split('@')[1]
                domain_groups[domain].append(email)
            else:
                domain_groups['_invalid_'].append(email)
        
        # Pre-resolve MX for all domains concurrently
        domains = [d for d in domain_groups.keys() if d != '_invalid_']
        mx_tasks = [self._resolve_mx(domain) for domain in domains]
        await asyncio.gather(*mx_tasks, return_exceptions=True)
        
        # Process in chunks
        all_results = []
        for i in range(0, len(unique_emails), CHUNK_SIZE):
            chunk = unique_emails[i:i + CHUNK_SIZE]
            
            # Create validation tasks with bounded concurrency
            tasks = [self.validate_email(email) for email in chunk]
            chunk_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Handle exceptions
            for j, result in enumerate(chunk_results):
                if isinstance(result, Exception):
                    all_results.append({
                        "email": chunk[j],
                        "status": "Error",
                        "reason": str(result),
                        "is_valid": False
                    })
                else:
                    if batch_id:
                        result["batch_id"] = batch_id
                    all_results.append(result)
        
        return all_results
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get performance metrics"""
        metrics = {}
        for domain, m in self._metrics.items():
            metrics[domain] = {
                "avg_dns_time": round(m.avg_dns_time() * 1000, 2),  # ms
                "avg_smtp_time": round(m.avg_smtp_time() * 1000, 2),  # ms
                "total_validations": m.total_validations,
                "successful": m.successful_validations,
                "failed": m.failed_validations,
                "timeouts": m.timeouts,
            }
        return metrics
    
    async def cleanup(self):
        """Clean up resources"""
        await self._connection_pool.close_all()
        await self._mx_cache.clear_expired()


# ======================= SINGLETON INSTANCE =======================

_validator_instance: Optional[AsyncEmailValidator] = None

async def get_validator() -> AsyncEmailValidator:
    """Get or create singleton validator instance"""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = AsyncEmailValidator()
        await _validator_instance.initialize()
    return _validator_instance


# ======================= CONVENIENCE FUNCTIONS =======================

async def validate_email_async(email: str) -> Dict[str, Any]:
    """Validate a single email (convenience function)"""
    validator = await get_validator()
    return await validator.validate_email(email)


async def validate_bulk_async(emails: List[str], batch_id: str = None) -> List[Dict[str, Any]]:
    """Validate multiple emails (convenience function)"""
    validator = await get_validator()
    return await validator.validate_bulk(emails, batch_id)
