"""Phase 3 ML routes: /api/ml/health, classify-response, predict-risk, match-identity."""
import pytest

from conftest import API


# --- Module: /api/ml/health -------------------------------------------------
class TestMLHealth:
    def test_health_models_ready_and_metrics(self, client):
        r = client.get(f"{API}/ml/health", timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "ok", d
        assert d["models_ready"]["placement_risk"] is True
        assert d["models_ready"]["response_classifier"] is True
        m = d["placement_risk_metrics"]
        for k in ("accuracy", "precision", "recall"):
            assert k in m, f"missing metric {k}"
            assert isinstance(m[k], (int, float))
            assert 0.0 <= float(m[k]) <= 1.0


# --- Module: /api/ml/classify-response (open, no auth) ---------------------
class TestClassifyResponse:
    CASES = [
        ("I got a job at a bakery near my house", "employed", "Hospitality"),
        ("I started my own shop", "self_employed", None),
        ("still searching, no openings", "unemployed", None),
        ("doing apprenticeship at a garage", "apprentice", "Automotive"),
    ]

    @pytest.mark.parametrize("text,expected,sector", CASES)
    def test_classify(self, client, text, expected, sector):
        r = client.post(f"{API}/ml/classify-response", json={"raw_text": text}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert set(["predicted_category", "confidence", "sector_guess", "method"]).issubset(d.keys()), d
        assert d["predicted_category"] == expected, f"{text!r} -> {d}"
        assert isinstance(d["confidence"], float)
        assert 0.0 <= d["confidence"] <= 1.0
        assert isinstance(d["method"], str) and d["method"]
        if sector:
            assert d["sector_guess"] == sector, f"{text!r} sector -> {d['sector_guess']}"

    def test_classify_bakery_sector_is_hospitality(self, client):
        r = client.post(f"{API}/ml/classify-response",
                        json={"raw_text": "I got a job at a bakery near my house"}, timeout=60)
        assert r.json()["sector_guess"] == "Hospitality"

    def test_classify_no_auth_required(self, client):
        r = client.post(f"{API}/ml/classify-response", json={"raw_text": "working at a hotel"}, timeout=60)
        assert r.status_code == 200

    def test_classify_empty_text(self, client):
        r = client.post(f"{API}/ml/classify-response", json={"raw_text": ""}, timeout=60)
        assert r.status_code == 200, r.text
        assert r.json()["predicted_category"] in {"employed", "self_employed", "apprentice", "unemployed"}

    def test_classify_missing_field_validation(self, client):
        r = client.post(f"{API}/ml/classify-response", json={}, timeout=60)
        assert r.status_code == 422


# --- Module: /api/ml/predict-risk (open, no auth) --------------------------
WEAK = {"attendance_percent": 58, "assessment_score": 45, "course_sector": "Construction",
        "district": "Nagpur", "gender": "Male", "age": 38}
STRONG = {"attendance_percent": 96, "assessment_score": 92, "course_sector": "IT/ITES",
          "district": "Pune", "gender": "Female", "age": 23}


class TestPredictRisk:
    def test_weak_profile_high_risk(self, client):
        r = client.post(f"{API}/ml/predict-risk", json=WEAK, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["risk_level"] == "high", d
        assert isinstance(d["risk_score"], float)
        assert d["risk_score"] >= 0.67, d
        assert isinstance(d["top_contributing_factors"], list)
        assert len(d["top_contributing_factors"]) > 0

    def test_strong_profile_low_risk(self, client):
        r = client.post(f"{API}/ml/predict-risk", json=STRONG, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["risk_level"] == "low", d
        assert d["risk_score"] < 0.34, d

    def test_weak_risk_ge_strong_risk(self, client):
        w = client.post(f"{API}/ml/predict-risk", json=WEAK, timeout=60).json()["risk_score"]
        s = client.post(f"{API}/ml/predict-risk", json=STRONG, timeout=60).json()["risk_score"]
        assert w >= s, f"weak {w} < strong {s}"

    def test_unknown_categories_handled(self, client):
        payload = dict(STRONG, course_sector="ZZZ Unknown", district="Atlantis", gender="Other")
        r = client.post(f"{API}/ml/predict-risk", json=payload, timeout=60)
        assert r.status_code == 200, r.text
        assert r.json()["risk_level"] in {"low", "medium", "high"}

    def test_validation_error_on_bad_types(self, client):
        r = client.post(f"{API}/ml/predict-risk", json=dict(WEAK, attendance_percent="abc"), timeout=60)
        assert r.status_code == 422


# --- Module: /api/ml/match-identity (auth required) ------------------------
class TestMatchIdentity:
    def test_requires_auth(self, client):
        r = client.post(f"{API}/ml/match-identity", json={"name": "Someone"}, timeout=60)
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text[:200]}"

    def test_invalid_token_rejected(self, client):
        r = client.post(f"{API}/ml/match-identity", json={"name": "Someone"},
                        headers={"Authorization": "Bearer not.a.token"}, timeout=60)
        assert r.status_code == 401

    def test_duplicate_detected_for_existing_trainee(self, client, admin_headers):
        lst = client.get(f"{API}/trainees?limit=5", headers=admin_headers, timeout=60)
        assert lst.status_code == 200, lst.text
        items = lst.json()["items"]
        assert items, "no seeded trainees found"
        t = items[0]
        last4 = "".join(c for c in (t.get("phone_masked") or "") if c.isdigit())[-4:]
        payload = {"name": t["full_name"], "phone_last4": last4,
                   "dob": t.get("dob"), "district": t.get("district")}
        r = client.post(f"{API}/ml/match-identity", json=payload, headers=admin_headers, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["is_likely_duplicate"] is True, d
        assert d["possible_matches"], d
        top = d["possible_matches"][0]
        assert top["similarity_score"] >= 80, top
        assert isinstance(top["reasons"], list) and top["reasons"]
        assert "_id" not in top

    def test_fake_person_not_duplicate(self, client, admin_headers):
        payload = {"name": "Zyxwvut Qqplmnb", "phone_last4": "0000",
                   "dob": "1901-01-01", "district": "Nowhere"}
        r = client.post(f"{API}/ml/match-identity", json=payload, headers=admin_headers, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["is_likely_duplicate"] is False, d
