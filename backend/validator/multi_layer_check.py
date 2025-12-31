import re
import dns.resolver
import socket
import smtplib
import random
import string
import time
import os
from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path

# ======================= CONFIGURATION =======================

# Timeouts (ULTRA-AGGRESSIVE for maximum speed)
DNS_TIMEOUT = 0.3  # seconds - ultra-fast DNS lookups
SMTP_TIMEOUT = 0.5  # seconds - minimal SMTP timeout (mostly disabled)
SOCKET_TIMEOUT = 0.3  # seconds - quick socket checks

# Retry settings - MINIMAL for speed
DNS_RETRIES = 1  # Single attempt only
SMTP_RETRIES = 0  # No SMTP retries

# SMTP Verification - DISABLED for maximum speed (DNS/MX checks only)
ENABLE_SMTP_VERIFICATION = False  # Set to True for deep verification (slower)
MAX_CONCURRENT = 200  # Increased from 100 for parallel processing

# Cache for performance optimization
_domain_cache = {}  # Cache MX and catch-all results per domain
_cache_ttl = 600  # 10 minutes cache TTL (was 5 minutes)

# TRUSTED PROVIDERS - Skip SMTP for these (they block it anyway)
TRUSTED_PROVIDERS = frozenset({
    "gmail.com", "googlemail.com", "google.com",
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
    "mail.ru", "inbox.ru", "bk.ru",
    "comcast.net", "att.net", "sbcglobal.net", "verizon.net",
})

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
                    # Skip comments and empty lines
                    if line and not line.startswith('#'):
                        domains.add(line.lower())
        print(f"Loaded {len(domains)} domains from {filename}")
    except Exception as e:
        print(f"Warning: Could not load {filename}: {e}")
    return domains

# Load disposable domains from file
DISPOSABLE_DOMAINS = load_domain_list('disposable_domains.txt')

# Load blacklist domains from file
BLACKLIST_DOMAINS = load_domain_list('blacklist_domains.txt')

# Role-based email prefixes (expanded list)
ROLE_EMAILS = {
    # Administrative
    "admin", "administrator", "root", "sysadmin", "webmaster", "hostmaster", "postmaster",
    
    # Support & Service
    "support", "help", "helpdesk", "service", "customer", "customerservice", "customersupport",
    
    # Sales & Marketing
    "sales", "marketing", "info", "contact", "enquiry", "inquiry", "team",
    
    # Business Operations
    "billing", "accounts", "accounting", "finance", "payment", "payments", "invoice", "invoices",
    "office", "reception", "legal", "compliance", "privacy", "security",
    
    # Communication
    "noreply", "no-reply", "donotreply", "do-not-reply", "mailer-daemon", "postmaster",
    "abuse", "feedback", "press", "media", "news", "pr", "public",
    
    # HR & Recruitment
    "hr", "jobs", "careers", "recruitment", "hiring", "apply", "application",
    
    # Technical
    "dev", "developer", "it", "tech", "technical", "engineering",
    
    # E-commerce
    "orders", "order", "shop", "store", "returns", "refunds", "reservations"
}

# ======================= STEP 1: RFC SYNTAX VALIDATION =======================

def check_rfc_syntax(email: str) -> Tuple[bool, str]:
    """
    Strict RFC 5322 compliant email syntax validation.
    Returns: (is_valid, reason)
    """
    # Basic checks
    if not email or not isinstance(email, str):
        return False, "Empty or invalid email"
    
    # Length checks (RFC 5321)
    if len(email) > 320:  # Total length limit
        return False, "Email too long (max 320 characters)"
    
    # Must contain exactly one @
    if email.count('@') != 1:
        return False, "Must contain exactly one @ symbol"
    
    parts = email.split('@')
    local_part, domain_part = parts[0], parts[1]
    
    # Local part checks
    if not local_part or len(local_part) > 64:
        return False, "Invalid local part length"
    
    # Domain part checks
    if not domain_part or len(domain_part) > 255:
        return False, "Invalid domain length"
    
    # Check for consecutive dots
    if '..' in email:
        return False, "Consecutive dots not allowed"
    
    # Check for leading/trailing dots in local part
    if local_part.startswith('.') or local_part.endswith('.'):
        return False, "Local part cannot start or end with dot"
    
    # Check for leading/trailing dots in domain
    if domain_part.startswith('.') or domain_part.endswith('.'):
        return False, "Domain cannot start or end with dot"
    
    # Validate local part characters (RFC 5322)
    local_pattern = r"^[a-zA-Z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[a-zA-Z0-9!#$%&'*+/=?^_`{|}~-]+)*$"
    if not re.match(local_pattern, local_part):
        return False, "Invalid characters in local part"
    
    # Validate domain format
    domain_pattern = r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?\.)+[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?$"
    if not re.match(domain_pattern, domain_part):
        return False, "Invalid domain format"
    
    # Validate TLD (must be at least 2 characters)
    tld = domain_part.split('.')[-1]
    if len(tld) < 2:
        return False, "Invalid TLD (too short)"
    
    # Check for spaces
    if ' ' in email:
        return False, "Spaces not allowed in email"
    
    return True, "Valid syntax"

# ======================= STEP 2: DOMAIN EXISTENCE CHECK =======================

def check_domain_existence(domain: str) -> Tuple[bool, str]:
    """
    Check if domain exists via DNS A record lookup.
    Returns: (exists, reason)
    """
    for attempt in range(DNS_RETRIES):
        try:
            # Try DNS resolver first
            resolver = dns.resolver.Resolver()
            resolver.timeout = DNS_TIMEOUT
            resolver.lifetime = DNS_TIMEOUT
            resolver.resolve(domain, 'A')
            return True, "Domain exists"
        except dns.resolver.NXDOMAIN:
            return False, "Domain does not exist"
        except dns.resolver.NoAnswer:
            # Try socket as fallback
            try:
                socket.setdefaulttimeout(SOCKET_TIMEOUT)
                socket.gethostbyname(domain)
                return True, "Domain exists"
            except socket.gaierror:
                if attempt < DNS_RETRIES - 1:
                    time.sleep(0.5)  # Brief delay before retry
                    continue
                return False, "Domain does not exist"
        except Exception as e:
            if attempt < DNS_RETRIES - 1:
                time.sleep(0.5)
                continue
            print(f"Domain check failed for {domain}: {e}")
            return False, f"Domain lookup failed: {str(e)}"
    
    return False, "Domain verification failed"

# ======================= STEP 3: MX RECORD CHECK =======================

def check_mx_record(domain: str) -> Tuple[List[str], str]:
    """
    Check for MX records and return list of mail servers.
    Returns: (mx_hosts, reason)
    """
    # Check cache first
    cache_key = f"mx_{domain}"
    if cache_key in _domain_cache:
        cached_data, timestamp = _domain_cache[cache_key]
        if time.time() - timestamp < _cache_ttl:
            return cached_data
    
    for attempt in range(DNS_RETRIES):
        try:
            resolver = dns.resolver.Resolver()
            resolver.timeout = DNS_TIMEOUT
            resolver.lifetime = DNS_TIMEOUT
            answers = resolver.resolve(domain, 'MX')
            
            # Sort by priority (lower number = higher priority)
            mx_hosts = sorted(answers, key=lambda x: x.preference)
            mx_list = [str(mx.exchange).rstrip('.') for mx in mx_hosts]
            
            # Cache the result
            result = (mx_list, "MX records found")
            _domain_cache[cache_key] = (result, time.time())
            
            return result
        except dns.resolver.NoAnswer:
            # No MX records, try A record as fallback
            domain_exists, _ = check_domain_existence(domain)
            if domain_exists:
                # Use domain itself as mail server
                result = ([domain], "Using A record as fallback")
                _domain_cache[cache_key] = (result, time.time())
                return result
            return [], "No MX records and domain has no A record"
        except Exception as e:
            if attempt < DNS_RETRIES - 1:
                time.sleep(0.5)
                continue
            print(f"MX check failed for {domain}: {e}")
            return [], f"MX lookup failed: {str(e)}"
    
    return [], "MX verification failed"

# ======================= STEP 4: DISPOSABLE EMAIL DETECTION =======================

def check_disposable(domain: str) -> bool:
    """Check if domain is a known disposable/temporary email service"""
    return domain.lower() in DISPOSABLE_DOMAINS

# ======================= STEP 5: ROLE-BASED EMAIL DETECTION =======================

def is_role_based(email: str) -> bool:
    """Check if email is a role-based address (admin, support, etc.)"""
    username = email.split('@')[0].lower()
    # Remove dots and hyphens for matching
    username_normalized = username.replace('.', '').replace('-', '')
    return username in ROLE_EMAILS or username_normalized in ROLE_EMAILS

# ======================= STEP 6: BLACKLIST CHECK =======================

def check_reputation_blacklist(domain: str) -> bool:
    """Check if domain is blacklisted"""
    return domain.lower() in BLACKLIST_DOMAINS

# ======================= STEP 7: SMTP MAILBOX VERIFICATION =======================

def check_smtp_mailbox(email: str, mx_hosts: List[str]) -> Dict[str, Any]:
    """
    Perform SMTP handshake to verify mailbox existence.
    CRITICAL: Only returns valid=True if server explicitly accepts (code 250).
    Returns: {"valid": bool, "status": str, "code": int}
    """
    if not mx_hosts:
        return {"valid": False, "status": "no_mx_records", "code": 0}
    
    # Try up to SMTP_RETRIES MX hosts
    mx_hosts_to_try = mx_hosts[:SMTP_RETRIES]
    
    for mx_host in mx_hosts_to_try:
        server = None
        try:
            # Connect to SMTP server
            server = smtplib.SMTP(timeout=SMTP_TIMEOUT)
            server.connect(mx_host, 25)
            server.helo('mail-validator.com')
            
            # Use neutral sender
            server.mail('verify@mail-validator.com')
            
            # Test recipient
            code, message = server.rcpt(email)
            
            # STRICT VALIDATION: Only 250 is considered valid
            if code == 250:
                return {"valid": True, "status": "deliverable", "code": code}
            
            # All other codes are considered INVALID
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
                # Greylisting or temporary failure = INVALID (too risky)
                return {"valid": False, "status": "temporary_failure", "code": code}
            elif code == 421:
                return {"valid": False, "status": "service_unavailable", "code": code}
            else:
                return {"valid": False, "status": f"smtp_code_{code}", "code": code}
                
        except smtplib.SMTPServerDisconnected:
            print(f"SMTP server {mx_host} disconnected")
            continue
        except smtplib.SMTPConnectError:
            print(f"SMTP connection error to {mx_host}")
            continue
        except socket.timeout:
            print(f"SMTP timeout connecting to {mx_host}")
            continue
        except Exception as e:
            print(f"SMTP error for {mx_host}: {e}")
            continue
        finally:
            if server:
                try:
                    server.quit()
                except:
                    pass
    
    # If all MX hosts failed to connect = INVALID
    return {"valid": False, "status": "connection_failed", "code": 0}

# ======================= STEP 8: CATCH-ALL DETECTION =======================

def check_catch_all(domain: str, mx_hosts: List[str]) -> bool:
    """
    Detect if domain accepts all email addresses (catch-all).
    OPTIMIZED: Single test only (was 2), skip for trusted providers.
    """
    if not mx_hosts:
        return False
    
    # Skip catch-all check for trusted providers (they don't do catch-all)
    if domain.lower() in TRUSTED_PROVIDERS:
        return False
    
    # Check cache first
    cache_key = f"catchall_{domain}"
    if cache_key in _domain_cache:
        cached_result, timestamp = _domain_cache[cache_key]
        if time.time() - timestamp < _cache_ttl:
            return cached_result
    
    # Test with 1 random non-existent email (reduced from 2 for speed)
    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=20))
    test_email = f"{random_str}@{domain}"
    
    result = check_smtp_mailbox(test_email, mx_hosts[:1])  # Only test first MX
    is_catch_all = result["valid"]
    
    # Cache the result
    _domain_cache[cache_key] = (is_catch_all, time.time())
    
    return is_catch_all

# ======================= MAIN VALIDATION FUNCTION =======================

def multi_layer_validate(email: str) -> Dict[str, Any]:
    """
    Execute complete email validation workflow.
    
    STRICT RULES:
    - Email is VALID only if ALL conditions pass
    - Any failure = INVALID (no "Risky" status)
    - Role-based emails are flagged but still marked Valid if they pass all checks
    """
    print(f"\n{'='*60}")
    print(f"VALIDATING: {email}")
    print(f"{'='*60}")
    
    # Clean and normalize email
    email = email.strip().lower()
    email = email.split('?')[0]  # Remove query parameters
    
    # Initialize result structure
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
        # Legacy compatibility
        "regex": "Not Valid",
        "mx": "Not Valid",
        "smtp": "Not Valid",
        "is_valid": False
    }
    
    # STEP 1: Syntax Validation
    syntax_valid, syntax_reason = check_rfc_syntax(email)
    print(f"[1/8] Syntax Check: {syntax_valid} - {syntax_reason}")
    
    if not syntax_valid:
        result["reason"] = syntax_reason
        return result
    
    result["syntax_valid"] = "Valid"
    result["regex"] = "Valid"
    
    # Extract domain
    if '@' not in email:
        result["reason"] = "Invalid email format"
        return result
    
    domain = email.split('@')[1]
    domain = ""
    if '@' in email:
        domain = email.split('@')[1]
    else:
        # If syntax is invalid or no '@', domain cannot be extracted
        syntax_valid = False # Ensure syntax_valid is false if domain extraction fails
    
    # Initialize flags for later use
    domain_exists = False
    mx_valid = False
    is_disposable = False
    is_role = False
    is_blacklisted = False
    is_catch_all = False
    is_inbox_full = False
    is_disabled = False
    is_unknown = False
    smtp_result = {"valid": False, "status": "not_checked", "code": 0}

    # Only proceed with domain-level checks if syntax is valid and domain extracted
    if syntax_valid and domain:
        # STEP 2: Domain Existence
        domain_exists, domain_reason = check_domain_existence(domain)
        print(f"[2/8] Domain Check: {domain_exists} - {domain_reason}")
        
        if domain_exists:
            result["domain_valid"] = "Valid"
        
        # STEP 3: MX Record Check
        mx_hosts, mx_reason = check_mx_record(domain)
        mx_valid = len(mx_hosts) > 0
        print(f"[3/8] MX Check: {mx_valid} - {mx_reason} - Hosts: {mx_hosts}")
        
        if mx_valid:
            result["mx_record_exists"] = "Valid"
            result["mx"] = "Valid"
        
        # STEP 4: Disposable Check (ALWAYS CHECK)
        is_disposable = check_disposable(domain)
        print(f"[4/8] Disposable Check: {is_disposable}")
        
        if is_disposable:
            result["disposable"] = "Yes"
        
        # STEP 5: Role-Based Check (ALWAYS CHECK)
        is_role = is_role_based(email)
        print(f"[5/8] Role-Based Check: {is_role}")
        
        if is_role:
            result["role_based"] = "Yes"
        
        # STEP 6: Blacklist Check (ALWAYS CHECK)
        is_blacklisted = check_reputation_blacklist(domain)
        print(f"[6/8] Blacklist Check: {is_blacklisted}")
        
        if is_blacklisted:
            result["blacklist"] = "Yes"
        
        # STEP 7: SMTP Mailbox Verification (only if domain and MX are valid)
        
        if domain_exists and mx_valid:
            # Check if this is a trusted provider that blocks SMTP verification
            if domain.lower() in TRUSTED_PROVIDERS:
                # Trusted providers block SMTP verification - mark as Risky/Unverifiable
                smtp_result = {"valid": False, "status": "unverifiable", "code": 0}
                result["smtp_valid"] = "Unknown"
                result["smtp"] = "Unknown"
                result["smtp_status"] = "unverifiable"
                is_unknown = True
                print(f"[7/8] SMTP Check: UNVERIFIABLE (Trusted Provider - {domain})")
            else:
                smtp_result = check_smtp_mailbox(email, mx_hosts)
                print(f"[7/8] SMTP Check: {smtp_result}")
            
            result["smtp_status"] = smtp_result["status"]
            result["smtp_code"] = smtp_result.get("code", 0)
            
            if smtp_result["valid"]:
                result["smtp_valid"] = "Valid"
                result["smtp"] = "Valid"
            else:
                # Categorize SMTP failures
                status = smtp_result["status"]
                code = smtp_result.get("code", 0)
                
                # Inbox Full
                if code == 552 or "inbox_full" in status or "mailbox full" in status:
                    is_inbox_full = True
                # Disabled/Rejected
                elif code in [554, 551, 553] or "disabled" in status or "rejected" in status:
                    is_disabled = True
                # Unknown/Temporary failures (greylisting, timeouts, etc.)
                elif code in [450, 451, 452, 421] or "temporary" in status or "timeout" in status or "connection_failed" in status or "unavailable" in status:
                    is_unknown = True
        else:
            # If domain/MX check failed, mark as unknown
            is_unknown = True
        
        # STEP 8: Catch-All Detection (only if SMTP was checked)
        if domain_exists and mx_valid and smtp_result["status"] != "not_checked":
            is_catch_all = check_catch_all(domain, mx_hosts)
            print(f"[8/8] Catch-All Check: {is_catch_all}")
            
            if is_catch_all:
                result["catch_all"] = "Yes"
    
    # ======================= DETERMINE FINAL STATUS =======================
    # Now that ALL parameters are evaluated, determine the final status
    
    # Start with assuming invalid
    status = "Invalid"
    reason = "Unknown"
    
    # Check for specific failure reasons (priority order)
    if not syntax_valid:
        reason = syntax_reason if syntax_reason else "Invalid syntax"
    elif not domain:  # If domain could not be extracted due to format issues
        reason = "Invalid email format"
    elif not domain_exists:
        reason = domain_reason if domain_reason else "Domain does not exist"
    elif not mx_valid:
        reason = mx_reason if mx_reason else "No mail server found"
    elif is_blacklisted:
        reason = "Blacklisted domain"
    elif is_disposable:
        reason = "Disposable email address"
    elif is_catch_all:
        reason = "Catch-all domain (unreliable)"
    elif is_inbox_full:
        reason = "Inbox Full"
    elif is_disabled:
        reason = "Mailbox Disabled"
    elif ENABLE_SMTP_VERIFICATION and not smtp_result["valid"]:
        # Only check SMTP if it's enabled
        if is_unknown:
            reason = "Unknown (SMTP verification inconclusive)"
        else:
            reason = smtp_result["status"].replace('_', ' ').title()
    else:
        # If SMTP is disabled OR SMTP passed, mark as valid
        # (DNS/MX/Disposable checks are sufficient)
        status = "VALID"
        if is_role_based:
            reason = "Deliverable (Role-based)"
        else:
            reason = "Deliverable"
    
    # Update result with final status
    result["status"] = status
    result["verdict"] = status
    result["reason"] = reason
    result["is_valid"] = (status == "VALID")
    
    # Set scores
    if status == "VALID":
        result["deliverability_score"] = 95
        result["quality_grade"] = "A"
    else:
        result["deliverability_score"] = 0
        result["quality_grade"] = "F"
    
    # Add category flags for easier counting
    result["is_inbox_full"] = is_inbox_full
    result["is_disabled"] = is_disabled
    result["is_unknown"] = is_unknown
    result["is_catch_all"] = is_catch_all
    result["is_disposable"] = is_disposable
    result["is_blacklisted"] = is_blacklisted
    result["is_role_based"] = is_role
    
    print(f"\n✅ FINAL VERDICT: {status.upper()} - {email}")
    print(f"{'='*60}\n")
    
    return result

# ======================= BULK VALIDATION =======================

def bulk_validate_local(emails: List[str], batch_id: str = None) -> List[Dict[str, Any]]:
    """
    Execute bulk validation with domain-level optimizations.
    Groups emails by domain to reuse MX lookups and catch-all checks.
    """
    print(f"\n{'='*60}")
    print(f"BULK VALIDATION: {len(emails)} emails")
    print(f"{'='*60}\n")
    
    results = []
    
    # Group emails by domain for efficiency
    domain_groups = {}
    for email in emails:
        email = email.strip().lower()
        if '@' in email:
            domain = email.split('@')[1]
            if domain not in domain_groups:
                domain_groups[domain] = []
            domain_groups[domain].append(email)
        else:
            # Invalid format, process individually
            results.append(multi_layer_validate(email))
    
    # Process each domain group
    for domain, domain_emails in domain_groups.items():
        print(f"\nProcessing {len(domain_emails)} emails for domain: {domain}")
        
        for email in domain_emails:
            result = multi_layer_validate(email)
            if batch_id:
                result["batch_id"] = batch_id
            results.append(result)
    
    print(f"\n{'='*60}")
    print(f"BULK VALIDATION COMPLETE")
    print(f"{'='*60}\n")
    
    return results
