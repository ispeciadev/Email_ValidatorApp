"""
Email Validation Scoring Module - ZeroBounce-Style

Implements industry-standard scoring model:
- Syntax Pass:      +10
- Domain Exists:    +15
- MX Valid:         +20
- Not Disposable:   +10
- Not Role-Based:   +10
- Not Blacklisted:  +15
- SMTP OK:          +30
- Catch-All:        -20

Maximum Score: 110 (normalized to 100)
Minimum Score: 0

Quality Grades:
- A: Score >= 90 (Excellent - safe to send)
- B: Score >= 75 (Good - likely deliverable)
- C: Score >= 60 (Fair - risky)
- D: Score >= 45 (Poor - not recommended)
- F: Score < 45  (Fail - do not send)
"""

from typing import Dict, Any, Tuple


# ======================= SCORING WEIGHTS =======================
# Based on ZeroBounce-style accuracy model

SCORE_WEIGHTS = {
    "syntax": 10,          # RFC 5322 compliant syntax
    "domain_exists": 15,   # Domain has DNS records
    "mx_valid": 20,        # MX records exist
    "not_disposable": 10,  # Not a temporary email
    "not_role_based": 10,  # Not a generic inbox (info@, support@)
    "not_blacklisted": 15, # Domain not in blacklist
    "smtp_verified": 30,   # SMTP handshake successful
}

SCORE_PENALTIES = {
    "catch_all": -20,      # Catch-all domains are risky
    "inbox_full": -10,     # Mailbox full is risky
    "disabled": -30,       # Disabled mailbox
}

# Maximum possible score (before normalization)
MAX_RAW_SCORE = sum(SCORE_WEIGHTS.values())  # 110

# Grade thresholds (normalized 0-100)
GRADE_THRESHOLDS = {
    "A": 90,   # Excellent - safe to send
    "B": 75,   # Good - likely deliverable
    "C": 60,   # Fair - risky
    "D": 45,   # Poor - not recommended
}


# ======================= SCORING FUNCTIONS =======================

def calculate_score(checks: Dict[str, bool]) -> Tuple[int, Dict[str, int]]:
    """
    Calculate deliverability score based on validation checks.
    
    Args:
        checks: Dictionary of boolean check results:
            - syntax_valid: bool
            - domain_exists: bool
            - mx_valid: bool
            - is_disposable: bool
            - is_role_based: bool
            - is_blacklisted: bool
            - smtp_verified: bool
            - is_catch_all: bool
            - is_inbox_full: bool
            - is_disabled: bool
    
    Returns:
        Tuple of (normalized_score: 0-100, breakdown: dict of per-check scores)
    """
    raw_score = 0
    breakdown = {}
    
    # Positive scores
    if checks.get("syntax_valid", False):
        breakdown["syntax"] = SCORE_WEIGHTS["syntax"]
        raw_score += breakdown["syntax"]
    else:
        breakdown["syntax"] = 0
    
    if checks.get("domain_exists", False):
        breakdown["domain"] = SCORE_WEIGHTS["domain_exists"]
        raw_score += breakdown["domain"]
    else:
        breakdown["domain"] = 0
    
    if checks.get("mx_valid", False):
        breakdown["mx"] = SCORE_WEIGHTS["mx_valid"]
        raw_score += breakdown["mx"]
    else:
        breakdown["mx"] = 0
    
    # Negative checks (score if NOT true)
    if not checks.get("is_disposable", False):
        breakdown["disposable"] = SCORE_WEIGHTS["not_disposable"]
        raw_score += breakdown["disposable"]
    else:
        breakdown["disposable"] = 0
    
    if not checks.get("is_role_based", False):
        breakdown["role_based"] = SCORE_WEIGHTS["not_role_based"]
        raw_score += breakdown["role_based"]
    else:
        breakdown["role_based"] = 0
    
    if not checks.get("is_blacklisted", False):
        breakdown["blacklist"] = SCORE_WEIGHTS["not_blacklisted"]
        raw_score += breakdown["blacklist"]
    else:
        breakdown["blacklist"] = 0
    
    # SMTP verification (most important)
    if checks.get("smtp_verified", False):
        breakdown["smtp"] = SCORE_WEIGHTS["smtp_verified"]
        raw_score += breakdown["smtp"]
    else:
        breakdown["smtp"] = 0
    
    # Penalties
    penalty = 0
    if checks.get("is_catch_all", False):
        penalty += SCORE_PENALTIES["catch_all"]
        breakdown["catch_all_penalty"] = SCORE_PENALTIES["catch_all"]
    
    if checks.get("is_inbox_full", False):
        penalty += SCORE_PENALTIES["inbox_full"]
        breakdown["inbox_full_penalty"] = SCORE_PENALTIES["inbox_full"]
    
    if checks.get("is_disabled", False):
        penalty += SCORE_PENALTIES["disabled"]
        breakdown["disabled_penalty"] = SCORE_PENALTIES["disabled"]
    
    raw_score += penalty
    
    # Normalize to 0-100
    normalized_score = max(0, min(100, int((raw_score / MAX_RAW_SCORE) * 100)))
    
    return normalized_score, breakdown


def get_quality_grade(score: int) -> str:
    """
    Get quality grade based on normalized score.
    
    Args:
        score: Normalized score (0-100)
    
    Returns:
        Grade letter (A, B, C, D, or F)
    """
    if score >= GRADE_THRESHOLDS["A"]:
        return "A"
    elif score >= GRADE_THRESHOLDS["B"]:
        return "B"
    elif score >= GRADE_THRESHOLDS["C"]:
        return "C"
    elif score >= GRADE_THRESHOLDS["D"]:
        return "D"
    else:
        return "F"


def get_verdict(score: int, is_valid: bool) -> str:
    """
    Get human-readable verdict based on score and validity.
    
    Returns one of:
        - "VALID" (score >= 70 and is_valid)
        - "RISKY" (score 45-69 or catch-all)
        - "INVALID" (score < 45 or not is_valid)
    """
    if not is_valid:
        return "INVALID"
    
    if score >= 70:
        return "VALID"
    elif score >= 45:
        return "RISKY"
    else:
        return "INVALID"


def calculate_full_score(result: Dict[str, Any]) -> Dict[str, Any]:
    """
    Calculate and add scoring information to a validation result.
    
    This is a convenience function that takes a validation result dict
    and adds scoring fields to it.
    
    Args:
        result: Validation result dictionary
    
    Returns:
        Updated result with scoring fields:
            - deliverability_score: 0-100
            - quality_grade: A-F
            - score_breakdown: dict of per-check scores
            - verdict: VALID/RISKY/INVALID
    """
    checks = {
        "syntax_valid": result.get("syntax_valid") == "Valid",
        "domain_exists": result.get("domain_valid") == "Valid",
        "mx_valid": result.get("mx_record_exists") == "Valid" or result.get("mx") == "Valid",
        "is_disposable": result.get("is_disposable", False),
        "is_role_based": result.get("is_role_based", False),
        "is_blacklisted": result.get("is_blacklisted", False),
        "smtp_verified": result.get("smtp_valid") == "Valid" or result.get("smtp") == "Valid",
        "is_catch_all": result.get("is_catch_all", False),
        "is_inbox_full": result.get("is_inbox_full", False),
        "is_disabled": result.get("is_disabled", False),
    }
    
    score, breakdown = calculate_score(checks)
    grade = get_quality_grade(score)
    is_valid = result.get("is_valid", False) or result.get("status") == "Valid"
    verdict = get_verdict(score, is_valid)
    
    result["deliverability_score"] = score
    result["quality_grade"] = grade
    result["score_breakdown"] = breakdown
    result["verdict"] = verdict
    
    return result
