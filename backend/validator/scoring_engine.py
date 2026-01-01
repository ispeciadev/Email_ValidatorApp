"""
Scoring Engine (Render Optimized)
Implements score-based classification to avoid 'UNKNOWN' results.
"""
from typing import Dict, Any, Optional, Tuple

# Industry-Standard Final Statuses (Optimized for Render)
STATUS_VALID = "valid"
STATUS_INVALID = "invalid"
STATUS_RISKY = "risky"

def classify_status_reoon(
    p1: Dict,
    p2: Dict,
    p3: Dict,
    p4: Dict
) -> Tuple[str, str, int]:
    """
    Score-Based Classification Logic (Render Optimized)
    
    Hard-Fail Rules (Result in INVALID, Score 0):
    - RFC syntax invalid
    - Domain does not exist / No MX records
    - Disposable domain
    - Blacklisted domain
    - Explicit SMTP 550 user not found
    
    Score-Based Classification:
    - Score >= 80: VALID
    - Score 50-79: RISKY
    - Score < 50: INVALID
    """
    
    score = 0
    reason = "undetermined"

    # --- PHASE 1: HARD FAIL CHECKS (Score 0) ---
    
    # 1. Syntax
    if not p1 or not p1.get("syntax_valid"):
        return (STATUS_INVALID, p1.get("failures", ["syntax_error"])[0] if p1 else "syntax_error", 0)
        
    # 2. DNS/MX
    if not p2 or not p2.get("mx_exists"):
        return (STATUS_INVALID, "dns_error", 0)
        
    # 3. Reputation (Hard Fail per requirements)
    if p1.get("is_disposable"):
        return (STATUS_INVALID, "disposable", 0)
        
    if p1.get("is_blacklisted"):
        return (STATUS_INVALID, "blacklisted", 0)

    # 4. Explicit SMTP 550 (Hard Fail)
    smtp_code = p4.get("smtp_code", 0) if p4 else 0
    smtp_status = p4.get("smtp_status", "not_checked") if p4 else "not_checked"
    
    if smtp_code == 550 or smtp_status == "invalid":
        return (STATUS_INVALID, "mailbox_not_found", 0)

    # --- PHASE 2: SCORING (Weak Signals) ---
    
    # Base points for passing basic checks (Syntax + MX pass)
    # Refined: 70 is the starting point (RISKY threshold)
    score = 70
    reason = "deliverable"
    
    # Role account penalty
    if p1.get("is_role"):
        score -= 5
        reason = "role_based"

    # Catch-all penalty
    if p4 and p4.get("is_catch_all"):
        score -= 10
        reason = "catch_all"

    # Mailbox Full penalty
    if smtp_status == "mailbox_full" or smtp_code in [452, 552]:
        score -= 30
        reason = "mailbox_full"

    # SMTP Success bonus (Crucial for VALID status)
    # Passing 70 (RISKY) + 25 (BONUS) = 95 (VALID)
    if smtp_code == 250:
        score += 25
        reason = "deliverable"

    # SMTP Timeout/Error/Blocked (Weak Signal - No Penalty)
    # If Render blocks SMTP, we stay at the base score of 70 (RISKY).
    # This correctly identifies that we couldn't verify the mailbox.

    # Cap score at 100
    score = min(max(score, 0), 100)

    # --- PHASE 3: FINAL CLASSIFICATION ---
    
    if score >= 80:
        return (STATUS_VALID, reason, score)
    elif score >= 50:
        return (STATUS_RISKY, reason, score)
    else:
        return (STATUS_INVALID, reason, score)

def calculate_score_reoon(status: str) -> int:
    """Note: Score calculation is now internal to classify_status_reoon.
    This function remains for backward compatibility.
    """
    if status == STATUS_VALID: return 98
    if status == STATUS_RISKY: return 65
    return 0
