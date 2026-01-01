"""
Production-Grade Async Email Validation Engine
Validates 2,200 emails in <30 seconds with ZeroBounce/Reoon-level accuracy

Key Features:
- Domain-grouped SMTP connections (2-4 per domain, reused)
- Aggressive caching (DNS, catch-all)
- Multi-phase pipeline with fail-fast
- Scoring system (0-100)
- Industry-standard output format
"""
import asyncio
import time
import re
from typing import Dict, Any, List, Tuple, Optional
from collections import defaultdict
from pathlib import Path

# Import async libraries
import aiodns
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
except (ImportError, NotImplementedError):
    # uvloop not available on Windows
    pass

from email_validator import validate_email as validate_email_syntax, EmailNotValidError

# Import our custom modules
from .smtp_pool import SMTPConnectionPool
from .dns_cache import DNSCache
from .scoring_engine import calculate_score, classify_status

# ======================= CONFIGURATION =======================

# Timeouts (strict)
TCP_CONNECT_TIMEOUT = 2.0  # seconds
SMTP_RESPONSE_TIMEOUT = 2.0  # seconds
TOTAL_EMAIL_TIMEOUT = 4.0  # seconds

# Concurrency limits
MAX_ASYNC_WORKERS = 250
MAX_SMTP_SOCKETS = 80
MAX_CONNECTIONS_PER_DOMAIN = 3

# Performance targets
TARGET_EMAILS_PER_SEC = 73  # 2200 emails / 30 seconds

# ======================= LOAD DOMAIN LISTS =======================

def load_domain_set(filename: str) -> set:
    """Load domain list from file into set for O(1) lookup"""
    filepath = Path(__file__).parent / filename
    domains = set()
    try:
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip().lower()
                    if line and not line.startswith('#'):
                        domains.add(line)
        print(f"[INIT] Loaded {len(domains)} domains from {filename}")
    except Exception as e:
        print(f"[WARNING] Could not load {filename}: {e}")
    return frozenset(domains)  # Immutable for thread safety

# Load domain lists
DISPOSABLE_DOMAINS = load_domain_set('disposable_domains.txt')
BLACKLIST_DOMAINS = load_domain_set('blacklist_domains.txt')

# Role-based accounts
ROLE_ACCOUNTS = frozenset({
    'admin', 'administrator', 'root', 'sysadmin', 'webmaster', 'hostmaster', 'postmaster',
    'support', 'help', 'helpdesk', 'service', 'customer', 'customerservice',
    'sales', 'marketing', 'info', 'contact', 'enquiry', 'inquiry', 'team',
    'billing', 'accounts', 'accounting', 'finance', 'payment', 'invoice',
    'office', 'reception', 'legal', 'compliance', 'privacy', 'security',
    'noreply', 'no-reply', 'donotreply', 'do-not-reply', 'mailer-daemon',
    'abuse', 'feedback', 'press', 'media', 'news', 'pr',
    'hr', 'jobs', 'careers', 'recruitment', 'hiring',
    'dev', 'developer', 'it', 'tech', 'technical',
    'orders', 'order', 'shop', 'store', 'returns', 'refunds'
})

# Free email providers (trusted, skip SMTP)
FREE_PROVIDERS = frozenset({
    'gmail.com', 'googlemail.com', 'google.com',
    'outlook.com', 'hotmail.com', 'live.com', 'msn.com',
    'yahoo.com', 'yahoo.co.uk', 'yahoo.co.in', 'ymail.com',
    'icloud.com', 'me.com', 'mac.com',
    'aol.com', 'aim.com',
    'protonmail.com', 'proton.me', 'pm.me',
    'zoho.com', 'zohomail.com',
    'fastmail.com', 'tutanota.com', 'gmx.com', 'mail.com',
    'yandex.com', 'mail.ru', 'rediffmail.com'
})

# Global instances
dns_cache = DNSCache()
smtp_pools: Dict[str, SMTPConnectionPool] = {}

# Semaphores for concurrency control
smtp_semaphore = asyncio.Semaphore(MAX_SMTP_SOCKETS)
worker_semaphore = asyncio.Semaphore(MAX_ASYNC_WORKERS)

# ======================= PHASE 1: SYNTAX & LOCAL RULES =======================

def phase_1_syntax(email: str) -> Dict[str, Any]:
    """
    Phase 1: Instant syntax validation (< 0.1ms)
    FAIL FAST on any syntax error
    """
    result = {
        "phase": 1,
        "email": email,
        "syntax_valid": False,
        "is_disposable": False,
        "is_blacklisted": False,
        "is_role": False,
        "score": 0,
        "failures": []
    }
    
    # Basic format check
    if not email or email.count('@') != 1:
        result["failures"].append("invalid_format")
        return result
    
    local_part, domain = email.split('@')
    
    # Check for double dots (RFC violation)
    if '..' in email:
        result["failures"].append("double_dot")
        return result
    
    # Leading/trailing dots
    if local_part.startswith('.') or local_part.endswith('.'):
        result["failures"].append("local_dot")
        return result
    
    if domain.startswith('.') or domain.endswith('.'):
        result["failures"].append("domain_dot")
        return result
    
    # Use email-validator library (strict RFC 5322)
    try:
        validated = validate_email_syntax(email, check_deliverability=False)
        result["normalized"] = validated.normalized
        result["syntax_valid"] = True
        result["score"] += 20  # +20 for valid syntax
    except EmailNotValidError as e:
        result["failures"].append(f"syntax: {str(e)}")
        return result
    
    # Normalize domain
    domain = domain.lower()
    
    # Disposable check (O(1))
    if domain in DISPOSABLE_DOMAINS:
        result["is_disposable"] = True
        result["failures"].append("disposable")
        result["score"] = 0  # Auto-fail
        return result
    
    # Blacklist check (O(1))
    if domain in BLACKLIST_DOMAINS:
        result["is_blacklisted"] = True
        result["failures"].append("blacklisted")
        result["score"] = -100  # Auto-fail
        return result
    
    # Not disposable bonus
    result["score"] += 15  # +15 for not disposable
    
    # Role account detection (informational, not a failure)
    local_normalized = local_part.lower().replace('.', '').replace('-', '')
    if local_normalized in ROLE_ACCOUNTS:
        result["is_role"] = True
        result["score"] -= 5  # -5 for role account
    
    # Store domain for next phase
    result["domain"] = domain
    result["local_part"] = local_part
    
    return result

# ======================= PHASE 2: DOMAIN INTELLIGENCE =======================

async def phase_2_dns(domain: str) -> Dict[str, Any]:
    """
    Phase 2: Async DNS resolution with caching (2-4s for all domains)
    """
    result = {
        "phase": 2,
        "domain": domain,
        "mx_exists": False,
        "mx_hosts": [],
        "provider": "unknown",
        "score": 0
    }
    
    # Get MX records from cache or resolve
    mx_data = await dns_cache.get_mx_records(domain)
    
    if not mx_data or not mx_data.get("mx_hosts"):
        result["failures"] = ["no_mx"]
        return result
    
    result["mx_exists"] = True
    result["mx_hosts"] = mx_data["mx_hosts"]
    result["provider"] = mx_data["provider"]
    result["score"] += 20  # +20 for MX exists
    
    return result

# ======================= PHASE 3: REPUTATION =======================

def phase_3_reputation(domain: str) -> Dict[str, Any]:
    """
    Phase 3: Reputation checks (no SMTP, instant)
    """
    result = {
        "phase": 3,
        "is_free_provider": domain in FREE_PROVIDERS,
        "score": 0
    }
    
    # Free provider bonus (trusted)
    if result["is_free_provider"]:
        result["score"] += 10  # Bonus for known providers
    
    return result

# ======================= PHASE 4: SMTP VERIFICATION =======================

async def phase_4_smtp(email: str, domain: str, mx_hosts: List[str], is_free_provider: bool) -> Dict[str, Any]:
    """
    Phase 4: SMTP verification with connection pooling
    ONLY for high-confidence emails, NOT free providers
    """
    result = {
        "phase": 4,
        "smtp_checked": False,
        "smtp_code": 0,
        "smtp_status": "not_checked",
        "deliverable": None,
        "is_catch_all": False,
        "score": 0
    }
    
    # Skip SMTP for free providers (they block it)
    if is_free_provider:
        result["smtp_status"] = "skipped_free_provider"
        result["deliverable"] = True  # Trust free providers
        result["score"] += 20  # Bonus for deliverable
        return result
    
    # Get or create SMTP pool for this domain
    if domain not in smtp_pools:
        smtp_pools[domain] = SMTPConnectionPool(
            domain=domain,
            mx_hosts=mx_hosts,
            max_size=MAX_CONNECTIONS_PER_DOMAIN
        )
    
    pool = smtp_pools[domain]
    
    # Verify with SMTP (with semaphore for global limit)
    async with smtp_semaphore:
        try:
            smtp_result = await asyncio.wait_for(
                pool.verify_email(email),
                timeout=TOTAL_EMAIL_TIMEOUT
            )
            
            result["smtp_checked"] = True
            result["smtp_code"] = smtp_result.get("code", 0)
            result["smtp_status"] = smtp_result.get("status", "unknown")
            
            # Interpret SMTP code
            code = result["smtp_code"]
            if code == 250:
                result["deliverable"] = True
                result["score"] += 30  # +30 for SMTP 250
            elif code in [452, 552]:  # Inbox full / quota
                result["deliverable"] = False
                result["smtp_status"] = "mailbox_full"
                result["score"] += 10  # Partial credit (mailbox exists)
            elif code in [450, 451, 421]:  # Temporary / greylisted
                result["deliverable"] = None  # UNKNOWN
                result["smtp_status"] = "temporary"
                result["score"] += 0  # No penalty for temp
            elif code in [550, 551, 553]:  # Not found
                result["deliverable"] = False
                result["smtp_status"] = "mailbox_not_found"
                result["score"] -= 20  # Penalty for not found
            
            # Catch-all detection (if deliverable)
            if result["deliverable"]:
                is_catchall = await dns_cache.is_catch_all_domain(domain, pool)
                if is_catchall:
                    result["is_catch_all"] = True
                    result["score"] -= 10  # -10 for catch-all
                    
        except asyncio.TimeoutError:
            result["smtp_status"] = "timeout"
            result["deliverable"] = None  # UNKNOWN
        except Exception as e:
            result["smtp_status"] = "error"
            result["smtp_error"] = str(e)
            result["deliverable"] = None
    
    return result

# ======================= MAIN VALIDATION FUNCTIONS =======================

async def validate_email_async(email: str) -> Dict[str, Any]:
    """
    Validate single email through all phases
    Returns industry-standard output format
    """
    start_time = time.time()
    
    # Normalize
    email = email.strip().lower()
    
    # Phase 1: Syntax & local rules (instant)
    p1 = phase_1_syntax(email)
    if p1["failures"] or not p1["syntax_valid"]:
        # Early exit
        execution_ms = (time.time() - start_time) * 1000
        return format_output(email, p1, None, None, None, execution_ms)
    
    domain = p1["domain"]
    
    # Phase 2: DNS (async, cached)
    p2 = await phase_2_dns(domain)
    if not p2["mx_exists"]:
        # Early exit
        execution_ms = (time.time() - start_time) * 1000
        return format_output(email, p1, p2, None, None, execution_ms)
    
    # Phase 3: Reputation (instant)
    p3 = phase_3_reputation(domain)
    
    # Phase 4: SMTP (selective, async)
    p4 = await phase_4_smtp(
        email,
        domain,
        p2["mx_hosts"],
        p3["is_free_provider"]
    )
    
    execution_ms = (time.time() - start_time) * 1000
    
    return format_output(email, p1, p2, p3, p4, execution_ms)

async def validate_bulk_async(emails: List[str], batch_id: str = None) -> List[Dict[str, Any]]:
    """
    Validate emails in bulk with domain grouping and concurrency
    Target: 2,200 emails in <30 seconds
    """
    print(f"\n{'='*70}")
    print(f"BULK VALIDATION: {len(emails)} emails")
    print(f"Target: <30 seconds ({TARGET_EMAILS_PER_SEC} emails/sec)")
    print(f"{'='*70}")
    
    start_time = time.time()
    
    # Deduplicate and normalize
    unique_emails = list(set([e.strip().lower() for e in emails if e.strip()]))
    print(f"Processing {len(unique_emails)} unique emails")
    
    # Group by domain for efficiency
    domain_groups = defaultdict(list)
    for email in unique_emails:
        if '@' in email:
            domain = email.split('@')[1]
            domain_groups[domain].append(email)
        else:
            domain_groups["_invalid"].append(email)
    
    print(f"Grouped into {len(domain_groups)} domains")
    
    # Pre-warm DNS cache (all domains at once)
    print("Pre-warming DNS cache...")
    dns_tasks = [dns_cache.get_mx_records(domain) 
                 for domain in domain_groups.keys() if domain != "_invalid"]
    await asyncio.gather(*dns_tasks, return_exceptions=True)
    
    # Validate all emails concurrently (with worker limit)
    print("Validating emails concurrently...")
    async def validate_with_semaphore(email):
        async with worker_semaphore:
            return await validate_email_async(email)
    
    tasks = [validate_with_semaphore(email) for email in unique_emails]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Handle exceptions
    final_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            final_results.append({
                "email": unique_emails[i],
                "status": "invalid",
                "sub_status": "validation_error",
                "error": str(result)
            })
        else:
            if batch_id:
                result["batch_id"] = batch_id
            final_results.append(result)
    
    # Stats
    elapsed = time.time() - start_time
    emails_per_sec = len(unique_emails) / elapsed
    
    # Count statuses
    status_counts = defaultdict(int)
    for r in final_results:
        status_counts[r.get("status", "unknown")] += 1
    
    print(f"\n{'='*70}")
    print(f"BULK VALIDATION COMPLETE")
    print(f"Total time: {elapsed:.2f}s")
    print(f"Speed: {emails_per_sec:.1f} emails/sec")
    print(f"Status breakdown:")
    for status, count in sorted(status_counts.items()):
        pct = (count / len(final_results)) * 100
        print(f"  {status.upper()}: {count} ({pct:.1f}%)")
    print(f"{'='*70}\n")
    
    return final_results

# ======================= OUTPUT FORMATTING =======================

def format_output(
    email: str,
    p1: Optional[Dict],
    p2: Optional[Dict],
    p3: Optional[Dict],
    p4: Optional[Dict],
    execution_ms: float
) -> Dict[str, Any]:
    """
    Format validation result in industry-standard format (ZeroBounce/Reoon style)
    """
    # Calculate total score
    total_score = 0
    if p1:
        total_score += p1.get("score", 0)
    if p2:
        total_score += p2.get("score", 0)
    if p3:
        total_score += p3.get("score", 0)
    if p4:
        total_score += p4.get("score", 0)
    
    # Classify status based on score
    status, sub_status = classify_status(total_score, p1, p2, p3, p4)
    
    # Build output
    output = {
        "email": email,
        "status": status,  # valid | invalid | risky | unknown
        "sub_status": sub_status,  # mailbox_exists | mailbox_not_found | catch_all | etc.
        "score": max(0, min(100, total_score)),  # Clamp 0-100
        "syntax_valid": p1.get("syntax_valid", False) if p1 else False,
        "mx_exists": p2.get("mx_exists", False) if p2 else False,
        "mx_provider": p2.get("provider", "unknown") if p2 else "unknown",
        "is_disposable": p1.get("is_disposable", False) if p1 else False,
        "is_role": p1.get("is_role", False) if p1 else False,
        "is_catch_all": p4.get("is_catch_all", False) if p4 else False,
        "is_free_provider": p3.get("is_free_provider", False) if p3 else False,
        "smtp_code": p4.get("smtp_code", 0) if p4 else 0,
        "smtp_status": p4.get("smtp_status", "not_checked") if p4 else "not_checked",
        "execution_ms": round(execution_ms, 2)
    }
    
    # Legacy compatibility fields
    output["is_valid"] = (status == "valid")
    output["is_deliverable"] = (status == "valid")
    output["deliverability_score"] = output["score"]
    
    return output
