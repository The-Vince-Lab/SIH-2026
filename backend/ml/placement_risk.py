"""Placement-risk prediction (scikit-learn LogisticRegression).

Explainable: linear model over one-hot categoricals + scaled numerics, so each
prediction exposes signed per-feature contributions to the non-placement log-odds.

Trains on the Phase 1 seeded dataset (features -> whether the trainee ended up
placed). Label = 1 means NON-placed (risk). Unreachable trainees (unknown
outcome) are excluded from training. Model is persisted to disk.
"""
import os
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from bson import ObjectId
from pymongo import MongoClient
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ARTIFACT = Path(__file__).parent / "artifacts" / "placement_risk.joblib"
NUMERIC = ["attendance_percent", "assessment_score", "age"]
CATEGORICAL = ["course_sector", "district", "gender"]
PLACED_TYPES = {"employed", "self_employed", "apprentice"}


def _age_from_dob(dob):
    if not dob:
        return 28
    try:
        from datetime import date
        y, m, d = [int(x) for x in dob.split("-")]
        today = date.today()
        return today.year - y - ((today.month, today.day) < (m, d))
    except Exception:
        return 28


def _load_training_frame():
    client = MongoClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    programs = {p["_id"]: p for p in db.training_programs.find({})}
    trainees = {t["_id"]: t for t in db.trainees.find({})}
    # label per trainee: 1 = unemployed, 0 = placed (skip unknown/unreachable)
    labels = {}
    for er in db.employment_records.find({}):
        labels[er["trainee_id"]] = 0 if er["type"] in PLACED_TYPES else 1

    rows = []
    for e in db.enrollments.find({"certified": True}):
        tid = e["trainee_id"]
        if tid not in labels or tid not in trainees:
            continue
        prog = programs.get(e["program_id"])
        t = trainees[tid]
        rows.append({
            "attendance_percent": e.get("attendance_percent", 0),
            "assessment_score": e.get("assessment_score", 0),
            "age": _age_from_dob(t.get("dob")),
            "course_sector": prog["sector"] if prog else "Unknown",
            "district": t.get("district", "Unknown"),
            "gender": t.get("gender", "Unknown"),
            "label": labels[tid],
        })
    client.close()
    return pd.DataFrame(rows)


def train() -> dict:
    df = _load_training_frame()
    X, y = df[NUMERIC + CATEGORICAL], df["label"]
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.25, random_state=42, stratify=y)

    pre = ColumnTransformer([
        ("num", StandardScaler(), NUMERIC),
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
    ])
    pipe = Pipeline([("pre", pre), ("clf", LogisticRegression(max_iter=1000))])
    pipe.fit(X_tr, y_tr)
    pred = pipe.predict(X_te)

    metrics = {
        "n_train": len(X_tr), "n_test": len(X_te),
        "positive_rate_non_placed": round(float(y.mean()), 3),
        "accuracy": round(float(accuracy_score(y_te, pred)), 3),
        "precision": round(float(precision_score(y_te, pred, zero_division=0)), 3),
        "recall": round(float(recall_score(y_te, pred, zero_division=0)), 3),
    }
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump({"pipeline": pipe, "metrics": metrics}, ARTIFACT)
    return metrics


_BUNDLE = None


def is_ready() -> bool:
    return ARTIFACT.exists()


def _bundle():
    global _BUNDLE
    if _BUNDLE is None:
        if not ARTIFACT.exists():
            train()
        _BUNDLE = joblib.load(ARTIFACT)
    return _BUNDLE


def get_metrics() -> dict:
    return _bundle()["metrics"]


def _readable_factor(feat_name: str, raw: dict) -> str:
    if feat_name.startswith("num__"):
        key = feat_name[5:]
        return {"attendance_percent": f"Low attendance ({raw['attendance_percent']}%)",
                "assessment_score": f"Low assessment score ({raw['assessment_score']})",
                "age": f"Age ({raw['age']})"}.get(key, key)
    if feat_name.startswith("cat__"):
        rest = feat_name[5:]
        for col in CATEGORICAL:
            if rest.startswith(col + "_"):
                val = rest[len(col) + 1:]
                label = {"course_sector": "Sector", "district": "District", "gender": "Gender"}[col]
                return f"{label}: {val}"
    return feat_name


def predict_risk(attendance_percent: float, assessment_score: float, course_sector: str,
                 district: str, gender: str, age: int) -> dict:
    bundle = _bundle()
    pipe = bundle["pipeline"]
    raw = {"attendance_percent": attendance_percent, "assessment_score": assessment_score,
           "age": age, "course_sector": course_sector, "district": district, "gender": gender}
    X = pd.DataFrame([raw])

    risk = float(pipe.predict_proba(X)[0][1])
    level = "low" if risk < 0.34 else ("medium" if risk < 0.67 else "high")

    # per-feature contribution to non-placement log-odds (coef * standardized value)
    pre = pipe.named_steps["pre"]
    clf = pipe.named_steps["clf"]
    transformed = pre.transform(X)
    transformed = transformed.toarray()[0] if hasattr(transformed, "toarray") else np.asarray(transformed)[0]
    names = pre.get_feature_names_out()
    coefs = clf.coef_[0]
    contribs = coefs * transformed
    top_idx = np.argsort(contribs)[::-1]  # most risk-increasing first
    factors = []
    for i in top_idx:
        if contribs[i] <= 0:
            break
        factors.append(_readable_factor(names[i], raw))
        if len(factors) >= 3:
            break
    if not factors:
        factors = ["No strong risk factors; profile resembles placed trainees"]

    return {"risk_score": round(risk, 3), "risk_level": level, "top_contributing_factors": factors}
