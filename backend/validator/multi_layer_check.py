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

# Timeouts (AGGRESSIVE optimization for 2000 emails in <30 seconds)
DNS_TIMEOUT = 0.2  # seconds - ultra-fast DNS lookups
SMTP_TIMEOUT = 1.2  # seconds - aggressive but reliable
SOCKET_TIMEOUT = 0.2  # seconds - quick socket checks

# Retry settings - MINIMAL for speed
DNS_RETRIES = 1  # Single attempt only
SMTP_RETRIES = 1  # Single attempt only
MAX_CONCURRENT = 200  # Preserve high concurrency

# SMTP Verification - ENABLED for accuracy (skip free providers for speed)
ENABLE_SMTP_VERIFICATION = True  # Enable for accurate validation

# Cache for performance optimization
_domain_cache = {}  # Cache MX and catch-all results per domain
_cache_ttl = 600  # 10 minutes cache TTL

# FREE EMAIL PROVIDERS - Skip SMTP for these (Reoon/ZeroBounce strategy)
# These providers block SMTP verification anyway
FREE_PROVIDERS = frozenset({
    \"gmail.com\", \"googlemail.com\", \"google.com\",
    \"outlook.com\", \"hotmail.com\", \"live.com\", \"msn.com\", \"outlook.in\",
    \"yahoo.com\", \"yahoo.co.uk\", \"yahoo.co.in\", \"yahoo.in\", \"ymail.com\", \"rocketmail.com\",
    \"icloud.com\", \"me.com\", \"mac.com\",
    \"aol.com\", \"aim.com\",
    \"protonmail.com\", \"proton.me\", \"pm.me\",
    \"zoho.com\", \"zohomail.com\", \"zoho.in\",
    \"fastmail.com\", \"fastmail.fm\",
    \"tutanota.com\", \"tutanota.de\", \"tuta.io\",
    \"gmx.com\", \"gmx.net\", \"gmx.de\",
    \"mail.com\", \"email.com\",
    \"yandex.com\", \"yandex.ru\",
    \"rediffmail.com\",
    \"mail.ru\", \"inbox.ru\", \"bk.ru\",
    \"comcast.net\", \"att.net\", \"sbcglobal.net\", \"verizon.net\",
})

# ======================= LOAD DOMAIN LISTS =======================

def load_domain_list(filename: str) -> set:
    \"\"\"Load domain list from file\"\"\"
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
        print(f\"Loaded {len(domains)} domains from {filename}\")
    except Exception as e:
        print(f\"Warning: Could not load {filename}: {e}\")
    return domains

# Load disposable domains from file
DISPOSABLE_DOMAINS = load_domain_list('disposable_domains.txt')

# Load blacklist domains from file
BLACKLIST_DOMAINS = load_domain_list('blacklist_domains.txt')

# Role-based email prefixes
ROLE_EMAILS = {
    # Administrative
    \"admin\", \"administrator\", \"root\", \"sysadmin\", \"webmaster\", \"hostmaster\", \"postmaster\",
    # Support & Service
    \"support\", \"help\", \"helpdesk\", \"service\", \"customer\", \"customerservice\", \"customersupport\",
    # Sales & Marketing
    \"sales\", \"marketing\", \"info\", \"contact\", \"enquiry\", \"inquiry\", \"team\",
    # Business Operations
    \"billing\", \"accounts\", \"accounting\", \"finance\", \"payment\", \"payments\", \"invoice\", \"invoices\",
    \"office\", \"reception\", \"legal\", \"compliance\", \"privacy\", \"security\",
    # Communication
    \"noreply\", \"no-reply\", \"donotreply\", \"do-not-reply\", \"mailer-daemon\",
    \"abuse\", \"feedback\", \"press\", \"media\", \"news\", \"pr\", \"public\",
    # HR & Recruitment
    \"hr\", \"jobs\", \"careers\", \"recruitment\", \"hiring\", \"apply\", \"application\",
    # Technical
    \"dev\", \"developer\", \"it\", \"tech\", \"technical\", \"engineering\",
    # E-commerce
    \"orders\", \"order\", \"shop\", \"store\", \"returns\", \"refunds\", \"reservations\"
}

# ======================= STEP 1: RFC SYNTAX VALIDATION =======================

def check_rfc_syntax(email: str) -> Tuple[bool, str]:
    \"\"\"
    Strict RFC 5322 compliant email syntax validation.
    Returns: (is_valid, reason)
    \"\"\"
    if not email or not isinstance(email, str):
        return False, \"Empty or invalid email\"
    
    if len(email) > 320:
        return False, \"Email too long (max 320 characters)\"
    
    if email.count('@') != 1:
        return False, \"Must contain exactly one @ symbol\"
    
    parts = email.split('@')
    local_part, domain_part = parts[0], parts[1]
    
    if not local_part or len(local_part) > 64:
        return False, \"Invalid local part length\"
    
    if not domain_part or len(domain_part) > 255:
        return False, \"Invalid domain length\"
    
    if '..' in email:
        return False, \"Consecutive dots not allowed\"
    
    if local_part.startswith('.') or local_part.endswith('.'):
        return False, \"Local part cannot start or end with dot\"
    
    if domain_part.startswith('.') or domain_part.endswith('.'):
        return False, \"Domain cannot start or end with dot\"
    
    local_pattern = r\"^[a-zA-Z0-9!#$%&'*+/=?^_`{|}~-]+(?:\\.[a-zA-Z0-9!#$%&'*+/=?^_`{|}~-]+)*$\"
    if not re.match(local_pattern, local_part):
        return False, \"Invalid characters in local part\"
    
    domain_pattern = r\"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?\\.)+[a-zA-Z0-9](?:[a-zA-Z0-9-]*[a-zA-Z0-9])?$\"
    if not re.match(domain_pattern, domain_part):
        return False, \"Invalid domain format\"
    
    tld = domain_part.split('.')[-1]
    if len(tld) < 2:
        return False, \"Invalid TLD (too short)\"
    
    if ' ' in email:
        return False, \"Spaces not allowed in email\"
    
    return True, \"Valid syntax\"

# ======================= STEP 2: DOMAIN EXISTENCE CHECK =======================

def check_domain_existence(domain: str) -> Tuple[bool, str]:
    \"\"\"Check if domain exists via DNS A record lookup.\"\"\"
    for attempt in range(DNS_RETRIES):
        try:
            resolver = dns.resolver.Resolver()
            resolver.timeout = DNS_TIMEOUT
            resolver.lifetime = DNS_TIMEOUT
            resolver.resolve(domain, 'A')
            return True, \"Domain exists\"
        except dns.resolver.NXDOMAIN:
            return False, \"Domain does not exist\"
        except dns.resolver.NoAnswer:
            try:
                socket.setdefaulttimeout(SOCKET_TIMEOUT)
                socket.gethostbyname(domain)
                return True, \"Domain exists\"
            except socket.gaierror:
                if attempt < DNS_RETRIES - 1:
                    continue
                return False, \"Domain does not exist\"
        except Exception as e:
            if attempt < DNS_RETRIES - 1:
                continue
            return False, f\"Domain lookup failed: {str(e)}\"
    
    return False, \"Domain verification failed\"

# ======================= STEP 3: MX RECORD CHECK =======================

def check_mx_record(domain: str) -> Tuple[List[str], str]:
    \"\"\"
    Check for MX records and return list of mail servers.
    NO FALLBACK to A record as per requirements.
    \"\"\"
    # Check cache first
    cache_key = f\"mx_{domain}\"
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
            
            mx_hosts = sorted(answers, key=lambda x: x.preference)
            mx_list = [str(mx.exchange).rstrip('.') for mx in mx_hosts]
            
            result = (mx_list, \"MX records found\")
            _domain_cache[cache_key] = (result, time.time())
            return result
        except dns.resolver.NoAnswer:
            # NO FALLBACK - as per requirements
            return [], \"No MX records found\"
        except Exception as e:
            if attempt < DNS_RETRIES - 1:
                continue
            return [], f\"MX lookup failed: {str(e)}\"
    
    return [], \"MX verification failed\"

# ======================= STEP 4: DISPOSABLE EMAIL DETECTION =======================

def check_disposable(domain: str) -> bool:
    \"\"\"Check if domain is a known disposable/temporary email service\"\"\"
    return domain.lower() in DISPOSABLE_DOMAINS

# ======================= STEP 5: ROLE-BASED EMAIL DETECTION =======================

def is_role_based(email: str) -> bool:
    \"\"\"Check if email is a role-based address\"\"\"
    username = email.split('@')[0].lower()
    username_normalized = username.replace('.', '').replace('-', '')
    return username in ROLE_EMAILS or username_normalized in ROLE_EMAILS

# ======================= STEP 6: BLACKLIST CHECK =======================

def check_reputation_blacklist(domain: str) -> bool:
    \"\"\"Check if domain is blacklisted\"\"\"
    return domain.lower() in BLACKLIST_DOMAINS

# ======================= STEP 7: SMTP MAILBOX VERIFICATION =======================

def check_smtp_mailbox(email: str, mx_hosts: List[str]) -> Dict[str, Any]:
    \"\"\"
    Perform SMTP handshake to verify mailbox existence.
    Returns: {\"valid\": bool, \"status\": str, \"code\": int, \"has_inbox_full\": bool, \"smtp_timeout\": bool}
    \"\"\"
    if not mx_hosts:
        return {\"valid\": False, \"status\": \"no_mx_records\", \"code\": 0, \"has_inbox_full\": False, \"smtp_timeout\": False}
    
    # Try first MX host only
    mx_host = mx_hosts[0]
    server = None
    
    try:
        server = smtplib.SMTP(timeout=SMTP_TIMEOUT)
        server.connect(mx_host, 25)
        server.helo('mail-validator.com')
        server.mail('verify@mail-validator.com')
        code, message = server.rcpt(email)
        
        # SMTP code interpretation per requirements
        if code == 250:
            return {\"valid\": True, \"status\": \"accepted\", \"code\": code, \"has_inbox_full\": False, \"smtp_timeout\": False}
        elif code in [452, 552]:  # Inbox full / quota
            return {\"valid\": False, \"status\": \"inbox_full\", \"code\": code, \"has_inbox_full\": True, \"smtp_timeout\": False}
        elif code in [450, 451, 421]:  # Temporary / throttled
            return {\"valid\": False, \"status\": \"temporary_failure\", \"code\": code, \"has_inbox_full\": False, \"smtp_timeout\": False}
        elif code in [550, 551, 553]:  # Mailbox not found
            return {\"valid\": False, \"status\": \"mailbox_not_found\", \"code\": code, \"has_inbox_full\": False, \"smtp_timeout\": False}
        else:
            return {\"valid\": False, \"status\": f\"smtp_code_{code}\", \"code\": code, \"has_inbox_full\": False, \"smtp_timeout\": False}
    except socket.timeout:
        return {\"valid\": False, \"status\": \"smtp_timeout\", \"code\": 0, \"has_inbox_full\": False, \"smtp_timeout\": True}
    except Exception as e:
        return {\"valid\": False, \"status\": \"connection_failed\", \"code\": 0, \"has_inbox_full\": False, \"smtp_timeout\": False}
    finally:
        if server:
            try:
                server.quit()
            except:
                pass

# ======================= STEP 8: CATCH-ALL DETECTION =======================

def check_catch_all(domain: str, mx_hosts: List[str]) -> bool:
    \"\"\"
    Detect if domain accepts all email addresses (catch-all).
    Skip for free providers.
    \"\"\"
    if not mx_hosts:
        return False
    
    # Skip catch-all check for free providers
    if domain.lower() in FREE_PROVIDERS:
        return False
    
    # Check cache first
    cache_key = f\"catchall_{domain}\"
    if cache_key in _domain_cache:
        cached_result, timestamp = _domain_cache[cache_key]
        if time.time() - timestamp < _cache_ttl:
            return cached_result
    
    # Test with 1 random non-existent email
    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=20))
    test_email = f\"{random_str}@{domain}\"
    
    result = check_smtp_mailbox(test_email, mx_hosts[:1])
    is_catch_all = result[\"valid\"]
    
    # Cache the result
    _domain_cache[cache_key] = (is_catch_all, time.time())
    
    return is_catch_all

# ======================= RULE-BASED STATUS RESOLUTION =======================

def resolve_final_status(result: Dict[str, Any]) -> Tuple[str, str]:
    \"\"\"
    STRICT RULE-BASED STATUS RESOLUTION (Reoon/ZeroBounce style)
    Returns: (status, reason)
    Statuses: VALID, RISKY, NEUTRAL, INVALID
    
    CRITICAL: Status is determined by RULES, not scores.
    \"\"\"
    # HARD INVALID - immediate disqualification
    if not result.get(\"syntax_valid\"):
        return \"INVALID\", result.get(\"syntax_reason\", \"Invalid syntax\")
    
    if result.get(\"is_disposable\"):
        return \"INVALID\", \"Disposable email address\"
    
    if not result.get(\"mx_exists\"):
        return \"INVALID\", \"No mail server found\"
    
    if result.get(\"smtp_code\") in [550, 551, 553]:
        return \"INVALID\", \"Mailbox does not exist\"
    
    if result.get(\"is_blacklisted\"):
        return \"INVALID\", \"Blacklisted domain\"
    
    # NEVER VALID - always RISKY
    if result.get(\"is_catch_all\"):
        return \"RISKY\", \"Catch-all domain (unverifiable)\"
    
    if result.get(\"has_inbox_full\"):
        return \"RISKY\", \"Inbox full\"
    
    if result.get(\"is_role_based\"):
        return \"RISKY\", \"Role-based address\"
    
    # UNCERTAIN - NEUTRAL status
    if result.get(\"smtp_timeout\"):
        return \"NEUTRAL\", \"SMTP timeout - cannot verify\"
    
    if not result.get(\"can_connect_smtp\") and not result.get(\"is_free_email\"):
        return \"NEUTRAL\", \"SMTP connection failed\"
    
    # DELIVERABLE - HIGH CONFIDENCE ONLY
    # Valid if: SMTP 250 AND not free provider
    if result.get("smtp_code") == 250 and not result.get("is_free_email"):
        return "VALID", "Deliverable"
    
    # Free providers: trusted, mark as VALID if basic checks pass
    if result.get("is_free_email") and result.get("mx_exists"):
        return "VALID", "Deliverable (trusted provider)"
    
    # Default: RISKY if we got here (passed basic checks but unverifiable)
    return "RISKY", "Unverifiable"

# ======================= MAIN VALIDATION FUNCTION =======================

def multi_layer_validate(email: str) -> Dict[str, Any]:
    """
    Execute complete email validation workflow with FAIL-FAST optimization.
    PRODUCTION-GRADE: Reoon/ZeroBounce style - exits immediately on failures.
    Target: 2000 emails in <30 seconds (15ms avg per email)
    """
    print(f"\n{'='*60}")
    print(f"VALIDATING: {email}")
    print(f"{'='*60}")
    
    # Clean and normalize
    email = email.strip().lower()
    
    # Initialize result
    result = {
        "email": email,
        "status": "INVALID",
        "reason": "",
        "syntax_valid": False,
        "syntax_reason": "",
        "domain_valid": False,
        "mx_exists": False,
        "mx_record_exists": "Not Valid",
        "smtp_valid": "Not Valid",
        "smtp_status": "not_checked",
        "smtp_code": 0,
        "smtp_timeout": False,
        "has_inbox_full": False,
        "can_connect_smtp": True,
        "is_role_based": False,
        "is_disposable": False,
        "is_blacklisted": False,
        "is_catch_all": False,
        "is_free_email": False,
        "is_deliverable": False,
        "is_safe_to_send": False,
        "deliverability_score": 0,
        "quality_grade": "F",
        # Legacy fields
        "regex": "Not Valid",
        "mx": "Not Valid",
        "smtp": "Not Valid",
        "role_based": "No",
        "disposable": "No",
        "blacklist": "No",
        "catch_all": "No",
        "is_valid": False
    }
    
    # ========== PHASE 1: INSTANT CHECKS (NO NETWORK, ~1ms) ==========
    # These are FREE and FAST - check upfront to fail fast
    
    # 1. RFC 5322 Syntax (CRITICAL - exit immediately if invalid)
    syntax_valid, syntax_reason = check_rfc_syntax(email)
    result["syntax_valid"] = syntax_valid
    result["syntax_reason"] = syntax_reason
    print(f"[PHASE 1] Syntax: {syntax_valid} - {syntax_reason}")
    
    if not syntax_valid:
        # ⚡ FAIL-FAST: Invalid syntax - EXIT IMMEDIATELY
        status, reason = resolve_final_status(result)
        result["status"] = status
        result["reason"] = reason
        print(f"⚡ FAST EXIT: Invalid syntax")
        return result
    
    result["regex"] = "Valid"
    
    # Extract domain
    domain = email.split('@')[1]
    
    # 2. Disposable Check (CRITICAL - exit immediately if disposable)
    is_disposable = check_disposable(domain)
    result["is_disposable"] = is_disposable
    if is_disposable:
        result["disposable"] = "Yes"
    print(f"[PHASE 1] Disposable: {is_disposable}")
    
    if is_disposable:
        # ⚡ FAIL-FAST: Disposable email - EXIT IMMEDIATELY
        status, reason = resolve_final_status(result)
        result["status"] = status
        result["reason"] = reason
        print(f"⚡ FAST EXIT: Disposable email")
        return result
    
    # 3. Blacklist Check (CRITICAL - check early, exit if blacklisted)
    is_blacklisted = check_reputation_blacklist(domain)
    result["is_blacklisted"] = is_blacklisted
    if is_blacklisted:
        result["blacklist"] = "Yes"
    print(f"[PHASE 1] Blacklisted: {is_blacklisted}")
    
    if is_blacklisted:
        # ⚡ FAIL-FAST: Blacklisted domain - EXIT IMMEDIATELY
        status, reason = resolve_final_status(result)
        result["status"] = status
        result["reason"] = reason
        print(f"⚡ FAST EXIT: Blacklisted domain")
        return result
    
    # 4. Role-Based Detection (INFORMATIONAL - don't exit, just flag)
    is_role = is_role_based(email)
    result["is_role_based"] = is_role
    if is_role:
        result["role_based"] = "Yes"
    print(f"[PHASE 1] Role-based: {is_role}")
    # Note: Don't exit - role-based emails can still be valid
    
    # ========== PHASE 2: FAST DNS CHECKS (~50-200ms, cached) ==========
    
    # 5. Domain Existence (CRITICAL - exit if domain doesn't exist)
    domain_exists, domain_reason = check_domain_existence(domain)
    result["domain_valid"] = domain_exists
    print(f"[PHASE 2] Domain: {domain_exists} - {domain_reason}")
    
    if not domain_exists:
        # ⚡ FAIL-FAST: Domain doesn't exist - EXIT IMMEDIATELY
        status, reason = resolve_final_status(result)
        result["status"] = status
        result["reason"] = reason
        print(f"⚡ FAST EXIT: Domain doesn't exist")
        return result
    
    # 6. MX Record Check (CRITICAL - exit if no MX records)
    mx_hosts, mx_reason = check_mx_record(domain)
    mx_valid = len(mx_hosts) > 0
    result["mx_exists"] = mx_valid
    if mx_valid:
        result["mx_record_exists"] = "Valid"
        result["mx"] = "Valid"
    print(f"[PHASE 2] MX: {mx_valid} - {mx_reason}")
    
    if not mx_valid:
        # ⚡ FAIL-FAST: No MX records - EXIT IMMEDIATELY
        status, reason = resolve_final_status(result)
        result["status"] = status
        result["reason"] = reason
        print(f"⚡ FAST EXIT: No MX records")
        return result
    
    # 7. Provider Classification (decides if we skip SMTP)
    is_free_email = domain.lower() in FREE_PROVIDERS
    result["is_free_email"] = is_free_email
    print(f"[PHASE 2] Free Provider: {is_free_email}")
    
    # ========== PHASE 3: SMTP (ONLY FOR NON-FREE PROVIDERS, ~1-2s) ==========
    # This is EXPENSIVE - only run if all basic checks passed
    
    skip_smtp = False
    
    # Skip SMTP for free providers (they block it anyway)
    if is_free_email:
        skip_smtp = True
        print(f"[PHASE 3] ⚡ SKIP SMTP: Free provider (Gmail/Yahoo/etc)")
    
    if not skip_smtp and ENABLE_SMTP_VERIFICATION:
        print(f"[PHASE 3] Running SMTP check...")
        smtp_result = check_smtp_mailbox(email, mx_hosts)
        
        result["smtp_code"] = smtp_result.get("code", 0)
        result["smtp_status"] = smtp_result.get("status", "not_checked")
        result["smtp_timeout"] = smtp_result.get("smtp_timeout", False)
        result["has_inbox_full"] = smtp_result.get("has_inbox_full", False)
        result["can_connect_smtp"] = smtp_result.get("status") != "connection_failed"
        
        if smtp_result["valid"]:
            result["smtp_valid"] = "Valid"
            result["smtp"] = "Valid"
        
        print(f"[PHASE 3] SMTP Result: {smtp_result}")
        
        # Catch-All Detection (only if SMTP was successful)
        if smtp_result["valid"] or smtp_result.get("code") == 250:
            is_catch_all = check_catch_all(domain, mx_hosts)
            result["is_catch_all"] = is_catch_all
            if is_catch_all:
                result["catch_all"] = "Yes"
            print(f"[PHASE 3] Catch-all: {is_catch_all}")
    else:
        print(f"[PHASE 3] SMTP check skipped")
    
    # ========== FINAL STATUS RESOLUTION (RULE-BASED) ==========
    
    status, reason = resolve_final_status(result)
    result["status"] = status
    result["reason"] = reason
    result["is_valid"] = (status == "VALID")
    result["is_deliverable"] = (status == "VALID")
    result["is_safe_to_send"] = (status == "VALID")
    result["verdict"] = status
    
    # Set scores (informational only - status is rule-based)
    if status == "VALID":
        result["deliverability_score"] = 95
        result["quality_grade"] = "A"
    elif status == "RISKY":
        result["deliverability_score"] = 60
        result["quality_grade"] = "C"
    elif status == "NEUTRAL":
        result["deliverability_score"] = 40
        result["quality_grade"] = "D"
    else:  # INVALID
        result["deliverability_score"] = 0
        result["quality_grade"] = "F"
    
    print(f"\n✅ FINAL: {status} - {reason}")
    print(f"{'='*60}\n")
    
    return result

# ======================= BULK VALIDATION =======================

def bulk_validate_local(emails: List[str], batch_id: str = None) -> List[Dict[str, Any]]:
    """
    Execute bulk validation with CONCURRENT PROCESSING.
    Target: 2000 emails in <30 seconds (15ms avg per email)
    Uses domain-level optimizations and parallel processing.
    """
    import concurrent.futures
    from collections import defaultdict
    
    print(f"\n{'='*60}")
    print(f"BULK VALIDATION: {len(emails)} emails")
    print(f"Target: <30 seconds for 2000 emails")
    print(f"{'='*60}\n")
    
    start_time = time.time()
    results = []
    smtp_check_count = 0
    
    # Clean and deduplicate emails
    unique_emails = list(set([email.strip().lower() for email in emails if email.strip()]))
    print(f"Processing {len(unique_emails)} unique emails (removed {len(emails) - len(unique_emails)} duplicates)")
    
    # Group emails by domain for efficiency
    domain_groups = defaultdict(list)
    for email in unique_emails:
        if '@' in email:
            domain = email.split('@')[1]
            domain_groups[domain].append(email)
        else:
            # Invalid format - validate synchronously
            result = multi_layer_validate(email)
            if batch_id:
                result["batch_id"] = batch_id
            results.append(result)
    
    print(f"Grouped into {len(domain_groups)} domains")
    
    # Process emails concurrently using ThreadPoolExecutor
    def validate_with_batch_id(email):
        result = multi_layer_validate(email)
        if batch_id:
            result["batch_id"] = batch_id
        return result
    
    # Use controlled concurrency - don't overwhelm network
    max_workers = min(50, len(unique_emails))  # Max 50 concurrent threads
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all emails for concurrent validation
        all_domain_emails = []
        for domain, domain_emails in domain_groups.items():
            all_domain_emails.extend(domain_emails)
        
        # Process all emails concurrently
        future_to_email = {executor.submit(validate_with_batch_id, email): email 
                          for email in all_domain_emails}
        
        # Collect results as they complete
        for future in concurrent.futures.as_completed(future_to_email):
            email = future_to_email[future]
            try:
                result = future.result()
                if result.get("smtp_status") not in ["not_checked"]:
                    smtp_check_count += 1
                results.append(result)
            except Exception as e:
                print(f"Error validating {email}: {e}")
                # Create error result
                error_result = {
                    "email": email,
                    "status": "INVALID",
                    "reason": f"Validation error: {str(e)}",
                    "is_valid": False
                }
                if batch_id:
                    error_result["batch_id"] = batch_id
                results.append(error_result)
    
    elapsed = time.time() - start_time
    smtp_usage_pct = (smtp_check_count / max(len(unique_emails), 1)) * 100
    avg_time_ms = (elapsed / max(len(unique_emails), 1)) * 1000
    
    print(f"\n{'='*60}")
    print(f"BULK VALIDATION COMPLETE")
    print(f"Total time: {elapsed:.2f}s")
    print(f"Average: {avg_time_ms:.1f}ms per email")
    print(f"Speed: {len(unique_emails)/elapsed:.1f} emails/second")
    print(f"SMTP Usage: {smtp_check_count}/{len(unique_emails)} ({smtp_usage_pct:.1f}%)")
    print(f"{'='*60}\n")
    
    return results
