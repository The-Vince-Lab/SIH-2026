"""Free-text follow-up response classification.

Explainable, two-stage:
  1) keyword/rule-based (ml.text_classifier) — first pass, fully transparent
  2) TF-IDF + LogisticRegression fallback (scikit-learn) trained on ~200
     synthetic labelled phrases — used only when keywords are inconclusive.

classify_response(raw_text) -> {predicted_category, confidence, sector_guess, method}
"""
import random
from pathlib import Path

import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, precision_score, recall_score

from . import text_classifier

ARTIFACT = Path(__file__).parent / "artifacts" / "response_classifier.joblib"

SECTOR_KEYWORDS = {
    "Hospitality": ["bakery", "hotel", "restaurant", "cafe", "kitchen", "chef", "catering"],
    "Beauty & Wellness": ["salon", "parlour", "parlor", "beautician", "spa", "makeup"],
    "Welding": ["welding", "welder", "fabrication"],
    "Retail": ["shop", "store", "retail", "counter", "sales", "mall", "supermarket"],
    "Healthcare": ["hospital", "nurse", "clinic", "pharmacy", "medical", "ward"],
    "IT/ITES": ["computer", "software", "it company", "data entry", "bpo", "call center", "coding"],
    "Automotive": ["garage", "car", "mechanic", "automobile", "bike repair", "motor"],
    "Construction": ["construction", "mason", "site", "building", "contractor"],
    "Apparel": ["tailor", "stitching", "garment", "boutique", "sewing"],
    "Electronics": ["electrician", "electronics", "mobile repair", "wiring", "appliance"],
}


def guess_sector(text: str):
    low = (text or "").lower()
    for sector, kws in SECTOR_KEYWORDS.items():
        if any(kw in low for kw in kws):
            return sector
    return None


# ---------------------------------------------------------------------------
# Synthetic training data (~200 phrases)
# ---------------------------------------------------------------------------
def generate_dataset():
    employed = [
        "I got a job at {p}", "working at a {p} now", "I joined a {p} last month",
        "got hired at {p}", "I am employed at a {p}", "working full time in a {p}",
        "started working at {p}", "placed in a {p} with good salary", "I have a job in {p}",
        "now doing job at {p} earning well",
    ]
    self_emp = [
        "I started my own {p}", "running my own {p} now", "opened a small {p}",
        "I have my own {p} business", "self employed with a {p}", "started a {p} of my own",
        "doing my own business, a {p}", "I run a {p}", "became an entrepreneur with a {p}",
        "my own {p} is doing well",
    ]
    apprentice = [
        "I am doing apprenticeship at a {p}", "working as an apprentice in {p}",
        "on the job trainee at {p}", "doing internship at {p}", "apprentice with stipend at {p}",
        "learning on the job at a {p}", "trainee position at {p}", "intern at a {p}",
    ]
    unemployed = [
        "no job yet", "still searching for work", "unemployed right now",
        "could not find any job", "no openings near my area", "not working currently",
        "looking for a job", "the salary offered was too low so did not join",
        "had to move for family reasons, not working", "no work available here",
        "still jobless after the course", "not placed anywhere yet",
    ]
    places = ["bakery", "shop", "hotel", "salon", "garage", "hospital", "factory",
              "store", "workshop", "company", "boutique", "clinic"]

    rows = []
    def expand(templates, label, n):
        for _ in range(n):
            t = random.choice(templates)
            rows.append(((t.format(p=random.choice(places)) if "{p}" in t else t), label))

    random.seed(7)
    expand(employed, "employed", 60)
    expand(self_emp, "self_employed", 50)
    expand(apprentice, "apprentice", 40)
    expand(unemployed, "unemployed", 60)
    random.shuffle(rows)
    return [r[0] for r in rows], [r[1] for r in rows]


def train() -> dict:
    X, y = generate_dataset()
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)
    pipe = Pipeline([
        ("tfidf", TfidfVectorizer(ngram_range=(1, 2), min_df=1)),
        ("clf", LogisticRegression(max_iter=1000, C=4.0)),
    ])
    pipe.fit(X_tr, y_tr)
    pred = pipe.predict(X_te)
    metrics = {
        "n_samples": len(X), "n_test": len(X_te),
        "accuracy": round(float(accuracy_score(y_te, pred)), 3),
        "precision_macro": round(float(precision_score(y_te, pred, average="macro", zero_division=0)), 3),
        "recall_macro": round(float(recall_score(y_te, pred, average="macro", zero_division=0)), 3),
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(pipe, ARTIFACT)
    return metrics


_MODEL = None


def is_ready() -> bool:
    return ARTIFACT.exists()


def _get_model():
    global _MODEL
    if _MODEL is None:
        if not ARTIFACT.exists():
            train()
        _MODEL = joblib.load(ARTIFACT)
    return _MODEL


def classify_response(raw_text: str) -> dict:
    kw = text_classifier.classify(raw_text)
    sector = guess_sector(raw_text)
    etype = kw["employment_type"]

    if etype != "unknown" and kw["confidence"] in ("high", "medium"):
        conf = 0.9 if kw["confidence"] == "high" else 0.75
        return {"predicted_category": etype, "confidence": conf, "sector_guess": sector,
                "method": "keyword", "matched_keywords": kw["matched_keywords"]}

    # inconclusive -> ML fallback
    try:
        model = _get_model()
        proba = model.predict_proba([raw_text or ""])[0]
        idx = int(proba.argmax())
        return {"predicted_category": str(model.classes_[idx]),
                "confidence": round(float(proba[idx]), 3), "sector_guess": sector,
                "method": "ml_fallback", "matched_keywords": kw["matched_keywords"]}
    except Exception:
        return {"predicted_category": etype if etype != "unknown" else "unemployed",
                "confidence": 0.4, "sector_guess": sector, "method": "keyword_low_confidence",
                "matched_keywords": kw["matched_keywords"]}
