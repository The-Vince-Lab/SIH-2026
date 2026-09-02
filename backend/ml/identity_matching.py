"""Fuzzy identity matching across programs (rapidfuzz).

Explainable: pure string/exact comparisons with transparent weighting.
match_identity is a plain importable function (records injectable for unit tests).
"""
from typing import List, Optional

from rapidfuzz import fuzz


def _last4(masked_or_phone: Optional[str]) -> Optional[str]:
    if not masked_or_phone:
        return None
    digits = "".join(c for c in masked_or_phone if c.isdigit())
    return digits[-4:] if len(digits) >= 4 else None


def match_identity(name: str, phone_last4: Optional[str] = None, dob: Optional[str] = None,
                   district: Optional[str] = None, records: Optional[List[dict]] = None) -> dict:
    """Compare a candidate against existing trainee records.

    Scoring (0-100): 60% fuzzy name (token_sort_ratio) + 25 phone_last4 exact
    + 15 dob exact (+ small district tie-break). is_likely_duplicate >= 80.
    """
    records = records or []
    matches = []
    for r in records:
        name_score = fuzz.token_sort_ratio(name or "", r.get("full_name", ""))
        rec_last4 = _last4(r.get("phone_masked") or r.get("phone_number"))
        phone_match = bool(phone_last4 and rec_last4 and phone_last4[-4:] == rec_last4)
        dob_match = bool(dob and r.get("dob") and dob == r.get("dob"))
        district_match = bool(district and r.get("district") and district.lower() == str(r.get("district")).lower())

        score = name_score * 0.6
        if phone_match:
            score += 25
        if dob_match:
            score += 15
        if district_match:
            score += 2
        score = round(min(score, 100.0), 1)

        if score >= 60:
            reasons = []
            reasons.append(f"name {int(name_score)}% similar")
            if phone_match:
                reasons.append("phone last4 match")
            if dob_match:
                reasons.append("DOB match")
            if district_match:
                reasons.append("same district")
            matches.append({
                "trainee_id": str(r.get("_id")),
                "name": r.get("full_name"),
                "district": r.get("district"),
                "similarity_score": score,
                "reasons": reasons,
            })

    matches.sort(key=lambda m: m["similarity_score"], reverse=True)
    is_dup = bool(matches and matches[0]["similarity_score"] >= 80)
    return {"possible_matches": matches[:5], "is_likely_duplicate": is_dup}
