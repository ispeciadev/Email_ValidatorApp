"""
Scoring Engine
Weighted scoring system for email validation (ZeroBounce/Reoon style)
"""
from typing import Dict, Any, Optional, Tuple

# Scoring weights (total possible: 100)
WEIGHTS = {
    "syntax_valid": 20,      # RFC 5322 compliant
    "mx_exists": 20,         # Has mail server
    "not_disposable": 15,    # Real domain
    "smtp_250": 30,          # Mailbox confirmed
    "catch_all": -10,        # Unverifiable
    "role_account": -5,      # Generic address
    "blacklisted": -100,     # Auto-fail
    "free_provider": 10,     # Trusted provider bonus
    "inbox_full": 10,        # Mailbox exists but full
}

def calculate_score(p1: Dict, p2: Dict, p3: Dict, p4: Dict) -> int:
    """
    Calculate weighted validation score (0-100)
    
    Args:
        p1: Phase 1 results (syntax, disposable, blacklist, role)
        p2: Phase 2 results (DNS, MX)
        p3: Phase 3 results (reputation)
        p4: Phase 4 results (SMTP)
    
    Returns:
        Score between 0-100
    """
    score = 0
    
    # Phase 1 scoring
    if p1:
        if p1.get("syntax_valid"):
            score += WEIGHTS["syntax_valid"]
        if not p1.get("is_disposable"):
            score += WEIGHTS["not_disposable"]
        if p1.get("is_blacklisted"):
            score += WEIGHTS["blacklisted"]  # -100
        if p1.get("is_role"):
            score += WEIGHTS["role_account"]  # -5
    
    # Phase 2 scoring
    if p2:
        if p2.get("mx_exists"):
            score += WEIGHTS["mx_exists"]
    
    # Phase 3 scoring
    if p3:
        if p3.get("is_free_provider"):
            score += WEIGHTS["free_provider"]
    
    # Phase 4 scoring
    if p4:
        smtp_code = p4.get("smtp_code", 0)
        if smtp_code == 250:
            score += WEIGHTS["smtp_250"]
        elif smtp_code in [452, 552]:  # Inbox full
            score += WEIGHTS["inbox_full"]
        
        if p4.get("is_catch_all"):
            score += WEIGHTS["catch_all"]  # -10
    
    # Clamp to 0-100
    return max(0, min(100, score))

def classify_status(
    score: int,
    p1: Optional[Dict],
    p2: Optional[Dict],
    p3: Optional[Dict],
    p4: Optional[Dict]
) -> Tuple[str, str, str]:
    """
    Classify email status based on 30 Dec logic.
    Returns: (status, reason, sub_status)
    
    Statuses (UPPERCASE per 30 Dec):
        - VALID
        - RISKY
        - INVALID
        - NEUTRAL
    """
    # 1. HARD INVALID (immediate disqualification)
    if p1:
        if not p1.get("syntax_valid"):
            reason = p1["failures"][0] if p1.get("failures") else "Invalid syntax"
            return ("INVALID", reason, "invalid_syntax")
        if p1.get("is_disposable"):
            return ("INVALID", "Disposable email address", "disposable")
        if p1.get("is_blacklisted"):
            return ("INVALID", "Blacklisted domain", "blacklisted")
    
    if p2:
        if not p2.get("mx_exists"):
            return ("INVALID", "No mail server found", "no_mx")
            
    # 2. SMTP FAILURES
    if p4:
        smtp_status = p4.get("smtp_status", "not_checked")
        smtp_code = p4.get("smtp_code", 0)
        
        if smtp_code in [550, 551, 553]:
            return ("INVALID", "Mailbox does not exist", "mailbox_not_found")
            
        # NEVER VALID - always RISKY
        if p4.get("is_catch_all"):
            return ("RISKY", "Catch-all domain (unverifiable)", "catch_all")
            
        if smtp_status == "mailbox_full":
            return ("RISKY", "Mailbox full or quota exceeded", "mailbox_full")
            
        # Role account detection (after catch-all/full)
        if p1 and p1.get("is_role"):
            return ("RISKY", "Role-based address", "role_account")
            
        # UNCERTAIN - NEUTRAL
        if smtp_status == "timeout":
            return ("NEUTRAL", "SMTP timeout – server did not respond", "timeout")
            
        if smtp_status == "temporary":
            return ("NEUTRAL", "Temporary failure", "temporary_failure")
            
        if smtp_status == "error":
            return ("NEUTRAL", "SMTP connection failed", "connection_error")
            
        # 3. DELIVERABLE (VALID)
        if smtp_code == 250:
            return ("VALID", "Deliverable", "mailbox_exists")
            
    # 4. FREE PROVIDERS (Trusted)
    if p3 and p3.get("is_free_provider"):
        if p2 and p2.get("mx_exists"):
            if p1 and p1.get("is_role"):
                return ("RISKY", "Role-based address", "role_account")
            return ("VALID", "Deliverable (trusted provider)", "free_provider")
            
    # Default fallback
    if score >= 80:
        return ("VALID", "High probability valid", "high_quality")
    elif score >= 60:
        return ("RISKY", "Passes basic checks but unverifiable", "unverifiable")
    else:
        return ("INVALID", "Validation failed", "unverifiable")
