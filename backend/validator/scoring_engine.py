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
) -> Tuple[str, str]:
    """
    Classify email status based on score and validation results
    
    Returns:
        (status, sub_status) tuple
        
    Statuses:
        - valid (90-100): High confidence deliverable
        - risky (70-89): Possibly deliverable, use caution
        - invalid (<70): Do not send
        - unknown: Could not verify (timeout, temp failure)
    
    Sub-statuses match industry standards:
        - mailbox_exists
        - mailbox_not_found
        - catch_all
        - role_account
        - disposable
        - blacklisted
        - timeout
        - temporary
        - no_mx
    """
    # Hard failures (immediate invalid)
    if p1:
        if not p1.get("syntax_valid"):
            return ("invalid", "invalid_syntax")
        if p1.get("is_disposable"):
            return ("invalid", "disposable")
        if p1.get("is_blacklisted"):
            return ("invalid", "blacklisted")
    
    if p2:
        if not p2.get("mx_exists"):
            return ("invalid", "no_mx")
    
    # SMTP-based classification
    if p4:
        smtp_status = p4.get("smtp_status", "not_checked")
        
        # Timeout or error → UNKNOWN
        if smtp_status in ["timeout", "error"]:
            return ("unknown", smtp_status)
        
        # Temporary failure → UNKNOWN (NOT invalid!)
        if smtp_status == "temporary":
            return ("unknown", "temporary")
        
        # Mailbox not found → INVALID
        if smtp_status == "mailbox_not_found":
            return ("invalid", "mailbox_not_found")
        
        # Inbox full → RISKY (mailbox exists but full)
        if smtp_status == "mailbox_full":
            return ("risky", "mailbox_full")
        
        # Catch-all → RISKY (unverifiable)
        if p4.get("is_catch_all"):
            return ("risky", "catch_all")
        
        # 250 OK → check score for final classification
        if smtp_status == "accepted":
            if score >= 90:
                return ("valid", "mailbox_exists")
            elif score >= 70:
                return ("risky", "deliverable_low_score")
            else:
                return ("invalid", "low_quality")
    
    # Free provider without SMTP (trusted)
    if p3 and p3.get("is_free_provider"):
        if p2 and p2.get("mx_exists"):
            if p1 and p1.get("is_role"):
                return ("risky", "role_account")
            return ("valid", "free_provider")
    
    # Role account → RISKY
    if p1 and p1.get("is_role"):
        if score >= 70:
            return ("risky", "role_account")
        else:
            return ("invalid", "role_account")
    
    # Score-based classification (fallback)
    if score >= 90:
        return ("valid", "high_quality")
    elif score >= 70:
        return ("risky", "medium_quality")
    elif score >= 50:
        return ("risky", "low_quality")
    else:
        return ("invalid", "low_score")
