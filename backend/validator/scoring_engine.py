"""
Scoring Engine
Standardized email validation scoring and status classification (ZeroBounce/Reoon compatible)
"""
from typing import Dict, Any, Optional, Tuple

# Industry-Standard Final Statuses (ZeroBounce Style)
STATUS_VALID = "valid"
STATUS_INVALID = "invalid"
STATUS_UNKNOWN = "unknown"
STATUS_CATCH_ALL = "catch_all"
STATUS_ROLE = "role"
STATUS_DISPOSABLE = "disposable"
STATUS_INBOX_FULL = "inbox_full"
STATUS_SPAMTRAP = "spamtrap"
STATUS_DISABLED = "disabled"

# Status to Score mapping (Confidence Only)
STATUS_SCORES = {
    STATUS_VALID: 100,
    STATUS_INBOX_FULL: 75,
    STATUS_CATCH_ALL: 70,
    STATUS_ROLE: 65,
    STATUS_UNKNOWN: 50,
    STATUS_DISPOSABLE: 0,
    STATUS_INVALID: 0,
    STATUS_SPAMTRAP: 0,
    STATUS_DISABLED: 0
}

def classify_status_reoon(
    p1: Dict,
    p2: Dict,
    p3: Dict,
    p4: Dict
) -> Tuple[str, str, str]:
    """
    Principal Architect Implementation: Classification Hierarchy
    Rules:
    1. Syntax is Absolute (FAIL FAST)
    2. Domain/MX existence (REQUIRED)
    3. Disposable/Spamtrap/Blacklist (INVALID/DISPOSABLE)
    4. Provider Overrides (Gmail/Outlook/Yahoo -> UNKNOWN if not confirmed)
    5. SMTP results (VALID/INVALID/INBOX_FULL)
    6. Catch-all detection
    """
    
    # --- PHASE 1: SYNTAX (ABSOLUTE) ---
    if not p1 or not p1.get("syntax_valid"):
        reason = p1.get("failures", ["syntax_error"])[0] if p1 else "syntax_error"
        return (STATUS_INVALID, reason, "syntax_error")
        
    # --- PHASE 2: DOMAIN & MX ---
    if not p2 or not p2.get("mx_exists"):
        return (STATUS_INVALID, "dns_error", "no_mx")
        
    # --- PHASE 3: DISPOSABLE / SPAMTRAP / BLACKLIST ---
    if p1.get("is_disposable"):
        return (STATUS_DISPOSABLE, "disposable", "disposable")
        
    if p1.get("is_blacklisted"):
        return (STATUS_INVALID, "blacklisted", "blacklisted")
        
    # --- PHASE 4: PROVIDER OVERRIDES (GMail, Outlook, etc.) ---
    is_free = p3.get("is_free_provider") if p3 else False
    
    # SMTP result check
    smtp_code = p4.get("smtp_code", 0) if p4 else 0
    smtp_status = p4.get("smtp_status", "not_checked") if p4 else "not_checked"
    
    # If it's a free provider, we skipped SMTP (unless the rules change)
    if is_free and smtp_status == "skipped_free_provider":
        # Free providers are UNKNOWN by default unless confirmed by SMTP (which we skip)
        # Principal Rule 3: Free providers are UNKNOWN unless confirmed (but we skip SMTP)
        # So they stay UNKNOWN
        return (STATUS_UNKNOWN, "free_provider_unconfirmed", "unknown")

    # --- PHASE 5: SMTP RESULTS ---
    if p4:
        if smtp_code == 250:
            # Special check for Catch-all (Phase 6)
            if p4.get("is_catch_all"):
                return (STATUS_CATCH_ALL, "catch_all", "catch_all")
                
            # Role accounts check (as requested moving to status ROLE)
            if p1.get("is_role"):
                return (STATUS_ROLE, "role_based", "role")
                
            return (STATUS_VALID, "deliverable", "mailbox_exists")
            
        if smtp_code in [452, 552] or smtp_status == "mailbox_full":
            return (STATUS_INBOX_FULL, "mailbox_full", "mailbox_full")
            
        if smtp_code in [550, 551, 553]:
            return (STATUS_INVALID, "mailbox_not_found", "mailbox_not_found")
            
        if smtp_status in ["timeout", "temporary", "error"]:
            return (STATUS_UNKNOWN, "smtp_unverifiable", "unknown")

    # Default fallback
    return (STATUS_UNKNOWN, "unverifiable", "unknown")

def calculate_score_reoon(status: str) -> int:
    """Score derived from status, not vice-versa"""
    return STATUS_SCORES.get(status, 0)
