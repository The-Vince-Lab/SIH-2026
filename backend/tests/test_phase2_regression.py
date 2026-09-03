"""Phase 2 regression: auth, trainee scoping, followup respond, employment verification, analytics."""
import uuid

import pytest

from conftest import API, CREDS


# --- Module: AUTH -----------------------------------------------------------
class TestAuth:
    @pytest.mark.parametrize("role", list(CREDS.keys()))
    def test_login_all_seeded_accounts(self, client, role):
        email, password = CREDS[role]
        r = client.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["token_type"] == "bearer"
        assert isinstance(d["access_token"], str) and d["access_token"].count(".") == 2
        assert d["user"]["email"] == email
        assert d["user"]["role"] == role
        assert "password_hash" not in d["user"]

    def test_me_returns_current_user(self, client, admin_headers):
        r = client.get(f"{API}/auth/me", headers=admin_headers, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["role"] == "super_admin"
        assert d["email"] == CREDS["super_admin"][0]
        assert "password_hash" not in d

    def test_me_without_token_401(self, client):
        r = client.get(f"{API}/auth/me", timeout=60)
        assert r.status_code == 401

    def test_invalid_password_401(self, client):
        r = client.post(f"{API}/auth/login",
                        json={"email": CREDS["state_admin"][0], "password": "WrongPass!1"}, timeout=60)
        assert r.status_code == 401
        assert "detail" in r.json()

    def test_brute_force_lockout_after_5_failures(self, client):
        """KNOWN BUG: 6th attempt raises 500 (naive vs aware datetime in _check_lockout);
        also the lockout key uses request.client.host, which differs per ingress hop."""
        email = f"TEST_lock_{uuid.uuid4().hex[:8]}@example.com"
        codes = []
        for _ in range(8):
            r = client.post(f"{API}/auth/login", json={"email": email, "password": "bad"}, timeout=60)
            codes.append(r.status_code)
        assert 500 not in codes, f"login returned 500 after repeated failures: {codes}"
        assert 429 in codes, f"expected a 429 lockout within 8 failed attempts, got {codes}"

    def test_role_enforcement_provider_cannot_register(self, client, provider_headers):
        r = client.post(f"{API}/auth/register", headers=provider_headers, json={
            "name": "TEST X", "email": "TEST_x@example.com", "password": "Passw0rd!", "role": "provider"},
            timeout=60)
        assert r.status_code == 403


# --- Module: TRAINEES + scoping --------------------------------------------
class TestTraineeScoping:
    def test_super_admin_requires_drilldown_then_sees_all(self, client, admin_headers):
        # privacy phase: no raw PII list without drilling into provider/course/district
        bare = client.get(f"{API}/trainees?limit=1", headers=admin_headers, timeout=60)
        assert bare.status_code == 403, bare.text
        r = client.get(f"{API}/trainees?district=Pune&limit=1", headers=admin_headers, timeout=60)
        assert r.status_code == 200, r.text
        assert r.json()["total"] > 0

    def test_provider_sees_subset(self, client, provider_headers, admin_headers):
        p = client.get(f"{API}/trainees?district=Pune&limit=1", headers=provider_headers, timeout=60)
        a = client.get(f"{API}/trainees?district=Pune&limit=1", headers=admin_headers, timeout=60)
        assert p.status_code == 200, p.text
        ptotal, atotal = p.json()["total"], a.json()["total"]
        assert 0 < ptotal < atotal, f"provider {ptotal} vs admin {atotal}"

    def test_district_admin_scoped_to_pune(self, client, tokens):
        h = {"Authorization": f"Bearer {tokens['district_admin']}"}
        r = client.get(f"{API}/trainees?district=Pune&limit=1000", headers=h, timeout=60)
        assert r.status_code == 200, r.text
        items = r.json()["items"]
        assert items
        assert {i["district"] for i in items} == {"Pune"}

    def test_phone_not_leaked_and_no_mongo_id_key(self, client, admin_headers):
        r = client.get(f"{API}/trainees?district=Pune&limit=3", headers=admin_headers, timeout=60)
        for t in r.json()["items"]:
            assert "phone_number" not in t
            assert "_id" in t and isinstance(t["_id"], str)

    def test_get_trainee_detail(self, client, admin_headers):
        tid = client.get(f"{API}/trainees?district=Pune&limit=1", headers=admin_headers, timeout=60).json()["items"][0]["_id"]
        r = client.get(f"{API}/trainees/{tid}", headers=admin_headers, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["trainee"]["_id"] == tid
        assert isinstance(d["enrollments"], list) and isinstance(d["employment"], list)

    def test_bad_id_returns_400(self, client, admin_headers):
        r = client.get(f"{API}/trainees/not-an-id", headers=admin_headers, timeout=60)
        assert r.status_code == 400, r.text

    def test_provider_forbidden_on_foreign_trainee(self, client, admin_headers, provider_headers):
        admin_ids = [t["_id"] for t in client.get(f"{API}/trainees?district=Pune&limit=1000", headers=admin_headers,
                                                  timeout=60).json()["items"]]
        prov_ids = {t["_id"] for t in client.get(f"{API}/trainees?district=Pune&limit=1000", headers=provider_headers,
                                                 timeout=60).json()["items"]}
        foreign = next(i for i in admin_ids if i not in prov_ids)
        r = client.get(f"{API}/trainees/{foreign}", headers=provider_headers, timeout=60)
        assert r.status_code == 403, r.status_code


# --- Module: FOLLOWUPS respond (keyword classification) ---------------------
class TestFollowupRespond:
    def test_respond_with_raw_text_classifies(self, client, admin_headers):
        fus = client.get(f"{API}/followups?status=sent&limit=5", headers=admin_headers, timeout=60)
        assert fus.status_code == 200, fus.text
        items = fus.json()["items"]
        assert items, "no followups with status=sent seeded"
        fid = items[0]["_id"]
        r = client.post(f"{API}/followups/{fid}/respond", headers=admin_headers, timeout=60,
                        json={"channel_used": "whatsapp",
                              "raw_response_text": "I got a job at a company, salary 18k"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "responded"
        assert d["structured_response"]["employment_type"] == "employed", d
        assert d["structured_response"]["wage_bracket"] == "15-25k", d
        assert d["classification"]["matched_keywords"]
        # persistence check
        lst = client.get(f"{API}/followups?limit=2000", headers=admin_headers, timeout=60).json()["items"]
        saved = next(f for f in lst if f["_id"] == fid)
        assert saved["status"] == "responded"
        assert saved["structured_response"]["employment_type"] == "employed"

    def test_respond_requires_payload(self, client, admin_headers):
        items = client.get(f"{API}/followups?status=sent&limit=5", headers=admin_headers,
                           timeout=60).json()["items"]
        assert items
        r = client.post(f"{API}/followups/{items[-1]['_id']}/respond", headers=admin_headers,
                        json={"channel_used": "sms"}, timeout=60)
        assert r.status_code == 400, r.text

    def test_respond_unknown_followup_404(self, client, admin_headers):
        r = client.post(f"{API}/followups/64b7f9e2c0a1b2c3d4e5f6a7/respond", headers=admin_headers,
                        json={"raw_response_text": "no job"}, timeout=60)
        assert r.status_code == 404


# --- Module: EMPLOYMENT + public verification flow -------------------------
class TestEmploymentVerification:
    def test_full_verification_flow_and_token_reuse(self, client, admin_headers):
        tid = client.get(f"{API}/trainees?district=Pune&limit=1", headers=admin_headers, timeout=60).json()["items"][0]["_id"]
        emp = client.post(f"{API}/employment", headers=admin_headers, timeout=60, json={
            "trainee_id": tid, "type": "employed", "employer_name": "TEST_Bakery Pvt Ltd",
            "employer_contact": "9876500011", "sector": "Hospitality", "wage_bracket": "15-25k"})
        assert emp.status_code == 200, emp.text
        e = emp.json()
        assert e["employer_verified"] is False
        eid = e["_id"]

        rv = client.post(f"{API}/employment/{eid}/request-verification", headers=admin_headers, timeout=60)
        assert rv.status_code == 200, rv.text
        token = rv.json()["token"]
        assert token and rv.json()["verification_path"] == f"/verify/{token}"

        # PUBLIC preview (no auth header)
        info = client.get(f"{API}/employment/verify/{token}", timeout=60)
        assert info.status_code == 200, info.text
        assert info.json()["used"] is False
        assert info.json()["type"] == "employed"

        conf = client.post(f"{API}/employment/verify/{token}", timeout=60,
                           json={"confirmed": True, "employer_name": "TEST_Bakery Pvt Ltd"})
        assert conf.status_code == 200, conf.text
        assert conf.json()["employer_verified"] is True

        # persisted on trainee detail
        det = client.get(f"{API}/trainees/{tid}", headers=admin_headers, timeout=60).json()
        rec = next(r for r in det["employment"] if r["_id"] == eid)
        assert rec["employer_verified"] is True
        assert rec["verification_timestamp"]

        # reuse -> 409
        again = client.post(f"{API}/employment/verify/{token}", json={"confirmed": True}, timeout=60)
        assert again.status_code == 409, again.status_code

    def test_invalid_token_404(self, client):
        r = client.post(f"{API}/employment/verify/nope-not-real", json={"confirmed": True}, timeout=60)
        assert r.status_code == 404

    def test_invalid_employment_type_400(self, client, admin_headers):
        tid = client.get(f"{API}/trainees?district=Pune&limit=1", headers=admin_headers, timeout=60).json()["items"][0]["_id"]
        r = client.post(f"{API}/employment", headers=admin_headers,
                        json={"trainee_id": tid, "type": "banana"}, timeout=60)
        assert r.status_code == 400


# --- Module: ANALYTICS smoke ------------------------------------------------
class TestAnalytics:
    def test_district_summary(self, client, admin_headers):
        r = client.get(f"{API}/analytics/district/Pune/summary", headers=admin_headers, timeout=60)
        assert r.status_code == 200, r.text
        assert "placement_rate" in str(r.json())

    def test_demographic_breakdown(self, client, admin_headers):
        r = client.get(f"{API}/analytics/demographic-breakdown?filter=gender",
                       headers=admin_headers, timeout=60)
        assert r.status_code == 200, r.text

    def test_non_placement_reasons(self, client, admin_headers):
        r = client.get(f"{API}/analytics/non-placement-reasons?group_by=course",
                       headers=admin_headers, timeout=60)
        assert r.status_code == 200, r.text

    def test_providers_and_programs(self, client, admin_headers):
        p = client.get(f"{API}/providers", headers=admin_headers, timeout=60)
        g = client.get(f"{API}/programs", headers=admin_headers, timeout=60)
        assert p.status_code == 200 and g.status_code == 200
        assert len(p.json()["items"] if isinstance(p.json(), dict) else p.json()) >= 1

    def test_provider_summary_scoped(self, client, admin_headers):
        provs = client.get(f"{API}/providers", headers=admin_headers, timeout=60).json()
        plist = provs["items"] if isinstance(provs, dict) else provs
        pid = plist[0]["_id"]
        r = client.get(f"{API}/analytics/provider/{pid}/summary", headers=admin_headers, timeout=60)
        assert r.status_code == 200, r.text
