"""Standalone unit tests for the ML modules. Run: python -m ml.tests_ml"""
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from ml import identity_matching, response_classifier, placement_risk  # noqa: E402


def test_identity_matching():
    records = [
        {"_id": "1", "full_name": "Rahul Sharma", "phone_masked": "XXXXXX8821", "dob": "1998-05-10", "district": "Pune"},
        {"_id": "2", "full_name": "Priya Patil", "phone_masked": "XXXXXX1234", "dob": "1995-02-20", "district": "Nashik"},
    ]
    # same person, name reordered + phone + dob match -> duplicate
    r = identity_matching.match_identity("Sharma Rahul", "8821", "1998-05-10", "Pune", records)
    assert r["is_likely_duplicate"] is True, r
    assert r["possible_matches"][0]["name"] == "Rahul Sharma"
    # unrelated person -> no duplicate
    r2 = identity_matching.match_identity("Amit Verma", "0000", "2000-01-01", "Nagpur", records)
    assert r2["is_likely_duplicate"] is False, r2
    print("identity_matching: PASS", r["possible_matches"][0]["similarity_score"])


def test_response_classifier():
    cases = [
        ("I got a job at a bakery near my house", "employed", "Hospitality"),
        ("I started my own tailoring shop", "self_employed", None),
        ("still searching, no openings near my area", "unemployed", None),
        ("doing apprenticeship at a garage", "apprentice", "Automotive"),
    ]
    for text, exp_cat, exp_sector in cases:
        out = response_classifier.classify_response(text)
        assert out["predicted_category"] == exp_cat, (text, out)
        if exp_sector:
            assert out["sector_guess"] == exp_sector, (text, out)
        print(f"classify: {text!r} -> {out['predicted_category']} ({out['method']}, conf={out['confidence']}, sector={out['sector_guess']})")
    print("response_classifier: PASS")


def test_placement_risk():
    high = placement_risk.predict_risk(55, 42, "Construction", "Nagpur", "Male", 39)
    low = placement_risk.predict_risk(96, 92, "IT/ITES", "Pune", "Female", 23)
    assert 0 <= high["risk_score"] <= 1 and 0 <= low["risk_score"] <= 1
    print(f"predict_risk high-profile: {high}")
    print(f"predict_risk low-profile : {low}")
    print(f"model metrics: {placement_risk.get_metrics()}")
    assert high["risk_score"] >= low["risk_score"], "weak profile should be >= strong profile risk"
    print("placement_risk: PASS")


if __name__ == "__main__":
    test_identity_matching()
    test_response_classifier()
    test_placement_risk()
    print("\nALL ML UNIT TESTS PASSED")
