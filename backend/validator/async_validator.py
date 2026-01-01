import asyncio
import time
from typing import Dict, Any, List, Optional
from email_validator import validate_email as validate_email_syntax, EmailNotValidError

from .dns_cache import DNSCache
from .smtp_pool import SMTPConnectionPool

from pathlib import Path

# Global Instances & Concurrency Control
dns_cache = DNSCache()
smtp_pools: Dict[str, SMTPConnectionPool] = {}
smtp_semaphore = asyncio.Semaphore(150)  # Max concurrent SMTP checks
worker_semaphore = asyncio.Semaphore(500) # Max total concurrent validation tasks
MAX_CONNECTIONS_PER_DOMAIN = 3
TOTAL_EMAIL_TIMEOUT = 12.0 # Max time for a single email validation

# Constants (Architect Intelligence)
FREE_PROVIDERS = {
    "gmail.com", "googlemail.com", "google.com",
    "outlook.com", "hotmail.com", "live.com", "msn.com",
    "yahoo.com", "yahoo.co.uk", "yahoo.co.in", "ymail.com",
    "icloud.com", "me.com", "mac.com", "aol.com"
}

ROLE_ACCOUNTS = {
    "admin", "support", "help", "info", "sales", "contact", "billing", "hr", "dev",
    "webmaster", "postmaster", "hostmaster", "root", "sysadmin"
}

def load_domain_list(filename: str) -> set:
    """Load domain list from file (O(1) lookup)"""
    filepath = Path(__file__).parent / filename
    domains = set()
    try:
        if filepath.exists():
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip().lower()
                    if line and not line.startswith('#'):
                        domains.add(line)
    except Exception: pass
    return domains

# These are O(1) lookups for disposal and blacklist checks
DISPOSABLE_DOMAINS = load_domain_list('disposable_domains.txt')
BLACKLIST_DOMAINS = load_domain_list('blacklist_domains.txt')

# Provider behavior table (Principal Architect Constraints)
PROVIDER_RULES = {
    "google": {
        "smtp_check": False,
        "catch_all": False,
        "default_status": "unknown"
    },
    "microsoft": {
        "smtp_check": False,
        "catch_all": False,
        "default_status": "unknown"
    },
    "yahoo": {
        "smtp_check": False,
        "catch_all": False,
        "default_status": "unknown"
    },
    "custom": {
        "smtp_check": True,
        "catch_all": True
    }
}

# Mapping provider strings to rule keys
PROVIDER_MAPPING = {
    "gmail.com": "google", "googlemail.com": "google", "google.com": "google",
    "outlook.com": "microsoft", "hotmail.com": "microsoft", "live.com": "microsoft", "msn.com": "microsoft",
    "yahoo.com": "yahoo", "yahoo.co.uk": "yahoo", "yahoo.co.in": "yahoo", "ymail.com": "yahoo"
}

# ======================= PHASE 1: SYNTAX (ABSOLUTE) =======================

def phase_1_syntax(email: str) -> Dict[str, Any]:
    """
    Phase 1: RFC Syntax (FAIL FAST)
    Rejected if: spaces, double dots, missing parts, multi-@, invalid TLD
    """
    result = {
        "syntax_valid": False,
        "email": email,
        "status": "invalid",
        "reason": "syntax_error",
        "is_disposable": False,
        "is_blacklisted": False,
        "is_role": False,
        "failures": []
    }
    
    if not email: return result

    # 1. Basic Structure
    if ' ' in email:
        result["failures"].append("spaces_detected")
        return result
        
    if email.count('@') != 1:
        result["failures"].append("multi_at_symbol")
        return result
        
    local_part, domain = email.split('@')

    # 2. Local Part Checks
    if not local_part:
        result["failures"].append("empty_local_part")
        return result
        
    if '..' in local_part or local_part.startswith('.') or local_part.endswith('.'):
        result["failures"].append("local_part_dot_error")
        return result

    # 3. Domain Checks
    if not domain or '.' not in domain:
        result["failures"].append("invalid_domain_structure")
        return result
        
    if '..' in domain or domain.startswith('.') or domain.endswith('.'):
        result["failures"].append("domain_dot_error")
        return result
        
    tld = domain.split('.')[-1]
    if len(tld) < 2 or len(tld) > 63:
        result["failures"].append("invalid_tld_length")
        return result

    # 4. Strict email-validator check
    try:
        # Use allow_smtputf8=False for maximum compatibility
        validate_email_syntax(email, check_deliverability=False, allow_smtputf8=False)
        result["syntax_valid"] = True
        result.pop("status") # Will be computed later
        result.pop("reason")
    except EmailNotValidError as e:
        result["failures"].append(f"rfc_violation: {str(e)}")
        return result

    # --- BELOW ONLY IF SYNTAX VALID ---
    domain_lower = domain.lower()
    
    # Disposable Domain Check (O(1))
    if domain_lower in DISPOSABLE_DOMAINS:
        result["is_disposable"] = True
        
    # Blacklist Check (O(1))
    if domain_lower in BLACKLIST_DOMAINS:
        result["is_blacklisted"] = True
        
    # Role-based check
    local_normalized = local_part.lower().replace('.', '').replace('-', '')
    if local_normalized in ROLE_ACCOUNTS:
        result["is_role"] = True
        
    return result

# ======================= PHASE 2: DOMAIN & MX =======================

async def phase_2_dns(domain: str) -> Dict[str, Any]:
    """Phase 2: DNS & MX (Async/Cached)"""
    result = {"mx_exists": False, "mx_hosts": [], "provider": "custom"}
    
    mx_data = await dns_cache.get_mx_records(domain)
    if mx_data and mx_data.get("mx_hosts"):
        result["mx_exists"] = True
        result["mx_hosts"] = mx_data["mx_hosts"]
        result["provider_name"] = mx_data["provider"]
    return result

# ======================= PHASE 4: PROVIDER OVERRIDE =======================

def get_provider_rules(domain: str, provider_name: str) -> Dict[str, Any]:
    """Combine domain and provider intelligence to determine behavior"""
    rule_key = PROVIDER_MAPPING.get(domain.lower())
    if not rule_key:
        # Fallback to provider fingerprinting from MX
        if "google" in provider_name.lower(): rule_key = "google"
        elif "microsoft" in provider_name.lower(): rule_key = "microsoft"
        elif "yahoo" in provider_name.lower(): rule_key = "yahoo"
        else: rule_key = "custom"
        
    return PROVIDER_RULES.get(rule_key, PROVIDER_RULES["custom"])

# ======================= MAIN PIPELINE =======================

async def validate_email_async(email: str) -> Dict[str, Any]:
    """Principal Architect Production-Grade Pipeline"""
    start_time = time.time()
    email = email.strip() # Keep original casing for output, but internal compare is lower
    
    # 1. PHASE 1: SYNTAX (ABSOLUTE)
    p1 = phase_1_syntax(email)
    if not p1["syntax_valid"]:
        return format_output_architect(email, p1, None, None, None, (time.time()-start_time)*1000)

    domain = email.split('@')[1].lower()
    
    # 2. PHASE 2: DOMAIN & MX
    p2 = await phase_2_dns(domain)
    if not p2["mx_exists"]:
        return format_output_architect(email, p1, p2, None, None, (time.time()-start_time)*1000)
        
    # 3. PHASE 3: DISPOSABLE / ROLE / BLACKLIST (Already checked in P1 results object)
    p3 = {"is_free_provider": domain in FREE_PROVIDERS}
    
    # 4. PHASE 4: PROVIDER OVERRIDES
    rules = get_provider_rules(domain, p2.get("provider_name", "unknown"))
    
    p4 = {
        "smtp_status": "not_checked",
        "smtp_code": 0,
        "is_catch_all": False
    }
    
    # 5. PHASE 5 & 6: SMTP & CATCH-ALL (Selective)
    if rules["smtp_check"]:
        async with smtp_semaphore:
            if domain not in smtp_pools:
                smtp_pools[domain] = SMTPConnectionPool(domain, p2["mx_hosts"], MAX_CONNECTIONS_PER_DOMAIN)
            
            pool = smtp_pools[domain]
            try:
                smtp_res = await asyncio.wait_for(pool.verify_email(email), timeout=TOTAL_EMAIL_TIMEOUT)
                p4["smtp_code"] = smtp_res.get("code", 0)
                p4["smtp_status"] = smtp_res.get("status", "unknown")
                
                # Phase 6: Catch-all detection
                if p4["smtp_code"] == 250 and rules["catch_all"]:
                    p4["is_catch_all"] = await dns_cache.is_catch_all_domain(domain, pool)
            except Exception as e:
                p4["smtp_status"] = "error"
    else:
        p4["smtp_status"] = "skipped_free_provider"

    exec_ms = (time.time() - start_time) * 1000
    return format_output_architect(email, p1, p2, p3, p4, exec_ms)

# ======================= FINAL RESPONSE OBJECT (EXACT FORMAT) =======================

def format_output_architect(email, p1, p2, p3, p4, ms) -> Dict[str, Any]:
    """ZeroBounce-style output format with status-driven scoring"""
    from .scoring_engine import classify_status_reoon, calculate_score_reoon
    
    status, reason, sub_status = classify_status_reoon(p1, p2, p3, p4)
    score = calculate_score_reoon(status)
    
    # Required Format
    res = {
        "email": email,
        "status": status,      # valid, invalid, unknown, etc.
        "sub_status": reason,  # reason maps to sub_status in ZeroBounce
        "score": score,
        "checks": {
            "syntax": p1["syntax_valid"] if p1 else False,
            "domain": p2["mx_exists"] if p2 else False,
            "mx": p2["mx_exists"] if p2 else False,
            "smtp": p4["smtp_status"] if p4 else "not_checked",
            "catch_all": p4["is_catch_all"] if p4 else False
        },
        "safe_to_send": (status in ["valid", "role", "catch_all"]), # Adjusted safety logic
        "execution_ms": round(ms, 2)
    }
    
    # Legacy & UI Mapping for frontend compatibility
    res.update({
        "is_valid": status == "valid",
        "deliverability_score": score,
        "verdict": status.upper(),
        "is_disposable": p1.get("is_disposable") if p1 else False,
        "is_role_account": p1.get("is_role") if p1 else False,
        "is_free_email": p3.get("is_free_provider") if p3 else False,
        "regex": "Valid" if p1 and p1["syntax_valid"] else "Not Valid",
        "mx_record_exists": "Valid" if p2 and p2["mx_exists"] else "Not Valid",
        "smtp_valid": "Valid" if status == "valid" else "Not Valid",
        "reason": reason,
        "disposable": "Yes" if p1.get("is_disposable") else "No",
        "role_based": "Yes" if p1.get("is_role") else "No",
        "catch_all": "Yes" if p4 and p4.get("is_catch_all") else "No"
    })
    
    return res

async def validate_bulk_async(emails: List[str], batch_id: str = None) -> List[Dict[str, Any]]:
    """Bulk validation using the architect-level pipeline"""
    start_time = time.time()
    unique_emails = list(set([e.strip() for e in emails if e.strip()]))
    
    # Concurrency control
    async def task_wrapper(email):
        async with worker_semaphore:
            return await validate_email_async(email)
            
    tasks = [task_wrapper(email) for email in unique_emails]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    final = []
    for i, res in enumerate(results):
        if isinstance(res, Exception):
            final.append({"email": unique_emails[i], "status": "unknown", "sub_status": "error"})
        else:
            if batch_id: res["batch_id"] = batch_id
            final.append(res)
            
    return final
