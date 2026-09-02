"""Rule-based / keyword classifier for free-text follow-up responses.

Explainable (no ML black-box): returns matched keywords so decisions are auditable.
Used by POST /api/followups/:id/respond when a raw_response_text is provided.
"""
import re

EMPLOYMENT_KEYWORDS = {
    "self_employed": [
        "own shop", "own business", "my shop", "my business", "started my", "self employed",
        "self-employed", "freelance", "startup", "entrepreneur", "running my",
    ],
    "apprentice": [
        "apprentice", "apprenticeship", "trainee", "internship", "intern", "stipend",
    ],
    "employed": [
        "got a job", "working", "joined", "employed", "job at", "salary", "company",
        "works at", "working at", "placed",
    ],
    "unemployed": [
        "no job", "not working", "unemployed", "still searching", "looking for", "no openings",
        "jobless", "no work", "cannot find", "not placed",
    ],
}

# order of precedence when multiple categories match
PRECEDENCE = ["unemployed", "self_employed", "apprentice", "employed"]

WAGE_PATTERNS = [
    (r"25\s*k|25000|30\s*k|30000|35\s*k|40\s*k|above 25", "25k+"),
    (r"15\s*k|15000|18\s*k|20\s*k|20000|15-25|15 to 25", "15-25k"),
    (r"10\s*k|10000|12\s*k|12000|10-15|10 to 15", "10-15k"),
    (r"below 10|less than 10|8\s*k|9\s*k|5\s*k|under 10", "<10k"),
]


def classify(text: str) -> dict:
    """Return {employment_type, wage_bracket, matched_keywords, confidence}."""
    if not text or not text.strip():
        return {"employment_type": "unknown", "wage_bracket": None,
                "matched_keywords": [], "confidence": "low"}

    low = text.lower()
    matched = {}
    for etype, kws in EMPLOYMENT_KEYWORDS.items():
        hits = [kw for kw in kws if kw in low]
        if hits:
            matched[etype] = hits

    employment_type = "unknown"
    for etype in PRECEDENCE:
        if etype in matched:
            employment_type = etype
            break

    wage = None
    for pattern, bracket in WAGE_PATTERNS:
        if re.search(pattern, low):
            wage = bracket
            break

    all_hits = [kw for hits in matched.values() for kw in hits]
    confidence = "high" if len(all_hits) >= 2 else ("medium" if all_hits else "low")

    return {
        "employment_type": employment_type,
        "wage_bracket": wage,
        "matched_keywords": all_hits,
        "confidence": confidence,
    }
