"""Phase 4: ML functions wired into API routes.

Covers:
  - POST /api/trainees duplicate detection (force query param)
  - POST /api/followups/{id}/respond free-text classification
  - GET /api/analytics/trainee/{id}/risk
  - GET /api/analytics/provider/{id}/at-risk-trainees (+ RBAC)
  - regression: /api/ml/* routes, all-role login, trainee scoping
"""
import os

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient
from bson import ObjectId

from conftest import API, CREDS

_benv = dotenv_values("/app/backend/.env")
MONGO_URL = os.environ.get("MONGO_URL") or _benv.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME") or _benv.get("DB_NAME")
if not MONGO_URL or not DB_NAME:
    raise RuntimeError("MONGO_URL/DB_NAME missing from /app/backend/.env")

TEST_NAME = "QA_Dup_Test Kumar"
TEST_PHONE = "9812345678"
TEST_DOB = "1996-04-15"
TEST_DISTRICT = "Pune"


@pytest.fixture(scope="module")
def mongo():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="module")
def created(mongo):
    """Track created trainee ids; cascade-delete trainee/enrollment/followup rows."""
    ids = []
    yield ids
    for tid in ids:
        o = ObjectId(tid)
        mongo.followups.delete_many({"trainee_id": o})
        mongo.enrollments.delete_many({"trainee_id": o})
        mongo.consent_logs.delete_many({"trainee_id": o})
        mongo.trainees.delete_one({"_id": o})
    # safety net: remove any leftover QA_ trainees
    leftovers = list(mongo.trainees.find({"full_name": {"$regex": "^QA_"}}, {"_id": 1}))
    for lo in leftovers:
        mongo.followups.delete_many({"trainee_id": lo["_id"]})
        mongo.enrollments.delete_many({"trainee_id": lo["_id"]})
        mongo.consent_logs.delete_many({"trainee_id": lo["_id"]})
        mongo.trainees.delete_one({"_id": lo["_id"]})


def _payload(name=TEST_NAME):
    return {"full_name": name, "phone_number": TEST_PHONE, "dob": TEST_DOB,
            "gender": "male", "district": TEST_DISTRICT, "state": "Maharashtra",
            "consent": {"given": True, "scope": ["followup"]}}


# ---------------------------------------------------------------------------
# 1. Duplicate detection on trainee creation (ml.identity_matching)
# ---------------------------------------------------------------------------
class TestDuplicateDetection:
    def test_duplicate_flow(self, client, admin_headers, created, mongo):
        # first create -> success
        r1 = client.post(f"{API}/trainees", json=_payload(), headers=admin_headers, timeout=60)
        assert r1.status_code == 200, r1.text[:400]
        d1 = r1.json()
        assert d1["created"] is True, d1
        assert "id" in d1 or "_id" in d1, d1
        first_id = d1.get("id") or d1.get("_id")
        created.append(first_id)
        assert d1["full_name"] == TEST_NAME
        assert "phone_number" not in d1  # encrypted phone must never leak
        assert mongo.trainees.count_documents({"full_name": TEST_NAME}) == 1

        # second identical create WITHOUT force -> requires confirmation, no insert
        r2 = client.post(f"{API}/trainees", json=_payload(), headers=admin_headers, timeout=60)
        assert r2.status_code == 200, r2.text[:400]
        d2 = r2.json()
        assert d2["created"] is False, d2
        assert d2["requires_confirmation"] is True
        assert d2["is_likely_duplicate"] is True
        assert isinstance(d2["possible_matches"], list) and len(d2["possible_matches"]) >= 1
        top = d2["possible_matches"][0]
        assert top["trainee_id"] == first_id
        assert top["similarity_score"] >= 80
        assert top["reasons"], "explainability reasons must be non-empty"
        assert mongo.trainees.count_documents({"full_name": TEST_NAME}) == 1, "no 2nd record on soft-block"

        # third create WITH force=true -> creates
        r3 = client.post(f"{API}/trainees?force=true", json=_payload(), headers=admin_headers, timeout=60)
        assert r3.status_code == 200, r3.text[:400]
        d3 = r3.json()
        assert d3["created"] is True, d3
        second_id = d3.get("id") or d3.get("_id")
        created.append(second_id)
        assert second_id != first_id
        assert mongo.trainees.count_documents({"full_name": TEST_NAME}) == 2

        # GET verifies persistence of the forced record
        g = client.get(f"{API}/trainees/{second_id}", headers=admin_headers, timeout=60)
        assert g.status_code == 200
        assert g.json()["trainee"]["full_name"] == TEST_NAME

    def test_distinct_person_not_blocked(self, client, admin_headers, created, mongo):
        body = _payload("QA_Unique Persona Zephyr")
        body["phone_number"] = "9700000123"
        body["dob"] = "1990-01-02"
        r = client.post(f"{API}/trainees", json=body, headers=admin_headers, timeout=60)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["created"] is True, d
        created.append(d.get("id") or d.get("_id"))


# ---------------------------------------------------------------------------
# 2. Free-text follow-up classification wiring (ml.response_classifier)
# ---------------------------------------------------------------------------
class TestFollowupClassification:
    @pytest.fixture(scope="class")
    def weak_trainee(self, client, admin_headers, created):
        body = _payload("QA_Weak Profile Trainee")
        body["phone_number"] = "9711122233"
        body["dob"] = "1999-07-07"
        r = client.post(f"{API}/trainees?force=true", json=body, headers=admin_headers, timeout=60)
        assert r.status_code == 200, r.text[:400]
        tid = r.json().get("id") or r.json().get("_id")
        created.append(tid)

        progs = client.get(f"{API}/programs", headers=admin_headers, timeout=60)
        assert progs.status_code == 200, progs.text[:300]
        items = progs.json()
        assert isinstance(items, list) and items
        program_id = (items[0].get("id") or items[0].get("_id"))

        enr = client.post(f"{API}/enrollments", headers=admin_headers, timeout=60, json={
            "trainee_id": tid, "program_id": program_id,
            "attendance_percent": 60, "assessment_score": 45,
            "certified": True, "certification_date": "2025-06-01"})
        assert enr.status_code == 200, enr.text[:400]
        eid = enr.json().get("id") or enr.json().get("_id")

        sch = client.post(f"{API}/followups/schedule", json={"enrollment_id": eid},
                          headers=admin_headers, timeout=90)
        assert sch.status_code == 200, sch.text[:400]
        assert sch.json()["followups_created"] == 4, sch.json()

        fus = client.get(f"{API}/followups?trainee_id={tid}", headers=admin_headers, timeout=60)
        assert fus.status_code == 200, fus.text[:300]
        items = fus.json()["items"]
        assert len(items) == 4
        labels = sorted(i["interval_label"] for i in items)
        assert labels == ["12_month", "1_month", "3_month", "6_month"]
        return {"trainee_id": tid, "enrollment_id": eid,
                "followup_ids": [i.get("id") or i.get("_id") for i in items]}

    def test_self_employed_beauty(self, client, admin_headers, weak_trainee, mongo):
        fid = weak_trainee["followup_ids"][0]
        r = client.post(f"{API}/followups/{fid}/respond", headers=admin_headers, timeout=60,
                        json={"channel_used": "whatsapp",
                              "raw_response_text": "I started my own beauty salon earning 18000"})
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        sr = d["structured_response"]
        assert sr["employment_type"] == "self_employed", sr
        assert sr["sector_guess"] == "Beauty & Wellness", sr
        assert d["status"] == "responded"
        stored = mongo.followups.find_one({"_id": ObjectId(fid)})
        assert stored["confidence_score"] == "self_reported", stored.get("confidence_score")
        assert stored["status"] == "responded"
        assert stored["structured_response"]["employment_type"] == "self_employed"

    def test_employed_healthcare(self, client, admin_headers, weak_trainee, mongo):
        fid = weak_trainee["followup_ids"][1]
        r = client.post(f"{API}/followups/{fid}/respond", headers=admin_headers, timeout=60,
                        json={"raw_response_text": "I got a job at a hospital"})
        assert r.status_code == 200, r.text[:400]
        sr = r.json()["structured_response"]
        assert sr["employment_type"] == "employed", sr
        assert sr["sector_guess"] == "Healthcare", sr
        stored = mongo.followups.find_one({"_id": ObjectId(fid)})
        assert stored["confidence_score"] == "self_reported"

    def test_unreachable_and_validation(self, client, admin_headers, weak_trainee, mongo):
        fid = weak_trainee["followup_ids"][2]
        r = client.post(f"{API}/followups/{fid}/respond", headers=admin_headers, timeout=60,
                        json={"unreachable": True})
        assert r.status_code == 200, r.text[:300]
        assert r.json()["status"] == "unreachable"
        assert mongo.followups.find_one({"_id": ObjectId(fid)})["confidence_score"] == "unreachable"

        fid2 = weak_trainee["followup_ids"][3]
        bad = client.post(f"{API}/followups/{fid2}/respond", headers=admin_headers, timeout=60,
                          json={"channel_used": "sms"})
        assert bad.status_code == 400, bad.status_code

    # -----------------------------------------------------------------------
    # 3. Risk scoring for the same weak profile
    # -----------------------------------------------------------------------
    def test_trainee_risk(self, client, admin_headers, weak_trainee):
        tid = weak_trainee["trainee_id"]
        r = client.get(f"{API}/analytics/trainee/{tid}/risk", headers=admin_headers, timeout=60)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        risk = d["risk"]
        assert 0.0 <= risk["risk_score"] <= 1.0, risk
        assert risk["risk_level"] in ("low", "medium", "high")
        assert risk["top_contributing_factors"], risk
        assert risk["basis"]["enrollment_id"] == weak_trainee["enrollment_id"]
        assert risk["risk_level"] == "high", f"weak profile should be high risk: {risk}"

    def test_risk_400_without_enrollment(self, client, admin_headers, created):
        body = _payload("QA_NoEnrollment Person")
        body["phone_number"] = "9722233344"
        body["dob"] = "1994-03-03"
        c = client.post(f"{API}/trainees?force=true", json=body, headers=admin_headers, timeout=60)
        assert c.status_code == 200, c.text[:300]
        tid = c.json().get("id") or c.json().get("_id")
        created.append(tid)
        r = client.get(f"{API}/analytics/trainee/{tid}/risk", headers=admin_headers, timeout=60)
        assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"

    def test_risk_404_unknown_trainee(self, client, admin_headers):
        r = client.get(f"{API}/analytics/trainee/{'0' * 24}/risk", headers=admin_headers, timeout=60)
        assert r.status_code in (400, 404), r.status_code


# ---------------------------------------------------------------------------
# 4. Provider at-risk trainees + RBAC
# ---------------------------------------------------------------------------
class TestAtRiskTrainees:
    @pytest.fixture(scope="class")
    def provider_ctx(self, client):
        email, password = CREDS["provider"]
        r = client.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        pid = (d.get("user") or {}).get("provider_id") or d.get("provider_id")
        assert pid, f"provider_id missing in login response: {d}"
        return {"headers": {"Authorization": f"Bearer {d['access_token']}"}, "provider_id": pid}

    def test_at_risk_high(self, client, provider_ctx):
        pid = provider_ctx["provider_id"]
        r = client.get(f"{API}/analytics/provider/{pid}/at-risk-trainees?level=high",
                       headers=provider_ctx["headers"], timeout=120)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert "count" in d and "at_risk_trainees" in d
        rows = d["at_risk_trainees"]
        assert d["count"] == len(rows) or d["count"] >= len(rows)
        scores = [x["risk_score"] for x in rows]
        assert scores == sorted(scores, reverse=True), "must be sorted by risk_score desc"
        for x in rows:
            assert x["risk_level"] == "high", x
            for k in ("trainee_id", "full_name", "risk_score", "top_contributing_factors", "course_sector"):
                assert k in x, (k, x)
            assert x["top_contributing_factors"], x

    def test_rbac_other_provider_forbidden(self, client, provider_ctx, admin_headers):
        provs = client.get(f"{API}/providers", headers=admin_headers, timeout=60)
        assert provs.status_code == 200, provs.text[:300]
        items = provs.json()
        assert isinstance(items, list)
        others = [p for p in items if (p.get("id") or p.get("_id")) != provider_ctx["provider_id"]]
        assert others, "need >1 provider seeded to test RBAC"
        other_id = others[0].get("id") or others[0].get("_id")
        r = client.get(f"{API}/analytics/provider/{other_id}/at-risk-trainees?level=high",
                       headers=provider_ctx["headers"], timeout=60)
        assert r.status_code == 403, f"{r.status_code} {r.text[:300]}"

    def test_no_auth_rejected(self, client, provider_ctx):
        r = requests.get(f"{API}/analytics/provider/{provider_ctx['provider_id']}/at-risk-trainees",
                         timeout=60)
        assert r.status_code in (401, 403), r.status_code


# ---------------------------------------------------------------------------
# 5. Regression sanity
# ---------------------------------------------------------------------------
class TestRegression:
    def test_all_roles_login(self, client):
        for role, (email, password) in CREDS.items():
            r = client.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=60)
            assert r.status_code == 200, f"{role}: {r.status_code} {r.text[:200]}"
            d = r.json()
            assert isinstance(d.get("access_token"), str) and len(d["access_token"]) > 20
            assert (d.get("user") or {}).get("role", d.get("role")) == role

    def test_ml_routes(self, client, admin_headers):
        h = client.get(f"{API}/ml/health", timeout=60)
        assert h.status_code == 200, h.text[:200]

        m = client.post(f"{API}/ml/match-identity", headers=admin_headers, timeout=60,
                        json={"name": "Ramesh Kumar", "phone_last4": "5678",
                              "dob": "1996-04-15", "district": "Pune"})
        assert m.status_code == 200, m.text[:300]
        assert "possible_matches" in m.json()

        c = client.post(f"{API}/ml/classify-response", timeout=60,
                        json={"raw_text": "I started my own beauty salon earning 18000"})
        assert c.status_code == 200, c.text[:300]

        p = client.post(f"{API}/ml/predict-risk", timeout=60,
                        json={"attendance_percent": 60, "assessment_score": 45,
                              "course_sector": "Beauty & Wellness", "district": "Pune",
                              "gender": "female", "age": 24})
        assert p.status_code == 200, p.text[:300]
        assert 0.0 <= p.json()["risk_score"] <= 1.0

    def test_trainee_scoping(self, client, admin_headers, provider_headers):
        a = client.get(f"{API}/trainees?district=Pune&limit=1000", headers=admin_headers, timeout=60)
        assert a.status_code == 200, a.text[:300]
        admin_total = a.json()["total"]
        assert admin_total > 0, admin_total

        p = client.get(f"{API}/trainees?district=Pune&limit=1000", headers=provider_headers, timeout=60)
        assert p.status_code == 200, p.text[:300]
        prov_total = p.json()["total"]
        assert 0 < prov_total < admin_total, (prov_total, admin_total)
