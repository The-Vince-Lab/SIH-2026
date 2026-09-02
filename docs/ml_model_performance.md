# SkillTrace AI — ML Model Performance

All models are intentionally simple and **explainable** (scikit-learn level, no deep
learning), trained on the Phase 1 seeded synthetic dataset. Numbers below are from a
held-out test split (`random_state=42`). Reproduce with:

```
cd /app/backend
python -m ml.train_all      # trains both models, prints metrics
python -m ml.tests_ml       # standalone unit tests for all three modules
```

---

## 1. Placement-Risk Prediction  (`ml/placement_risk.py`)
- **Algorithm:** Logistic Regression (one-hot categoricals + standardized numerics)
- **Why LogReg:** signed per-feature coefficients → each prediction exposes exactly
  which factors pushed risk up/down (defensible & auditable).
- **Target:** `1 = non-placed` (risk). Unreachable trainees (unknown outcome) excluded.
- **Features:** attendance_percent, assessment_score, age, course_sector, district, gender

| Metric | Value |
|--------|-------|
| Train samples | 92 |
| Test samples | 31 |
| Base rate (non-placed) | 0.512 |
| **Accuracy** | **0.774** |
| **Precision** | **0.846** |
| **Recall** | **0.688** |

Example predictions:
- Weak profile (att 55%, score 42, Construction, Male, 39) → `risk_score 0.977`, **high**,
  factors: Low assessment score, Low attendance, Gender.
- Strong profile (att 96%, score 92, IT/ITES, Female, 23) → `risk_score 0.006`, **low**.

Model persisted to `ml/artifacts/placement_risk.joblib` (no retrain per request).

---

## 2. Free-Text Response Classification  (`ml/response_classifier.py`)
- **Stage 1 — keyword/rule-based** (fully transparent, returns matched keywords).
- **Stage 2 — TF-IDF + Logistic Regression** fallback, trained on ~210 synthetic
  labelled phrases, used only when keywords are inconclusive.
- Also returns a `sector_guess` from a sector keyword dictionary.

| Metric | Value |
|--------|-------|
| Samples | 210 |
| Test samples | 53 |
| **Accuracy** | **1.0** |
| **Precision (macro)** | **1.0** |
| **Recall (macro)** | **1.0** |

> Note: 1.0 reflects the clean, well-separated synthetic phrase set; in the live flow
> the transparent keyword stage handles most real responses and the ML model is a
> fallback. Categories: employed / self_employed / apprentice / unemployed.

Model persisted to `ml/artifacts/response_classifier.joblib`.

---

## 3. Identity Matching  (`ml/identity_matching.py`)
- **Algorithm:** `rapidfuzz` `token_sort_ratio` on name + exact match on phone_last4 & dob.
- **Score (0-100):** 60% name similarity + 25 (phone_last4) + 15 (dob) + 2 (district).
- **`is_likely_duplicate`** when top score ≥ 80. Every match returns human-readable
  `reasons` (e.g. "name 100% similar", "phone last4 match", "DOB match").
- No training needed (deterministic); validated via unit tests
  (`Sharma Rahul` + phone + dob → 100.0, duplicate=true).

---

## Summary for the demo
| Feature | Approach | Headline number |
|---------|----------|-----------------|
| Placement risk | Logistic Regression | 77.4% acc / 84.6% prec / 68.8% recall |
| Text classification | Keyword + TF-IDF LogReg | 100% on synthetic test set |
| Identity matching | rapidfuzz fuzzy + exact | Deterministic, explainable score |
