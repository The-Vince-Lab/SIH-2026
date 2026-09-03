"""Phase 8 — re-verification of iteration_7 fixes.

Covers server.py assert_consent() enforcement on write paths:
create_employment, create_non_placement, respond_followup, schedule_followups.
"""
import uuid

import pytest
from conftest import API


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _create_trainee(client, token, name, scope):
    body = {
        "full_name": name,
        "phone_number": "9" + str(uuid.uuid4().int)[:9],
        "dob": "2000-05-10",
        "gender": "Female",
        "district": "Nashik",
        "state": "Maharashtra",
        "consent": {"given": True, "scope": scope},
    }
    r = client.post(f"{API}/trainees?force=true", json=body, headers=_h(token), timeout=60)
    assert r.status_code == 200, f"create_trainee failed: {r.status_code} {r.text[:300]}"
    d = r.json()
    return d.get("_id") or d.get("id")


@pytest.fixture(scope="module")
def pctx(client, tokens):
    token = tokens["provider"]
    me = client.get(f"{API}/auth/me", headers=_h(token), timeout=60)
    assert me.status_code == 200, me.text[:200]
    pid = me.json().get("provider_id")
    progs = client.get(f"{API}/programs", headers=_h(token), timeout=60).json()
    assert progs
    return {"token": token, "provider_id": pid, "program_id": progs[0]["_id"]}


@pytest.fixture(scope="module")
def created_ids():
    return []


@pytest.fixture(scope="module", autouse=True)
def cleanup(created_ids):
    yield
    try:
        import os

        from bson import ObjectId
        from dotenv import dotenv_values
        from pymongo import MongoClient
        env = dotenv_values("/app/backend/.env")
        cli = MongoClient(os.environ.get("MONGO_URL") or env["MONGO_URL"])
        dbx = cli[env["DB_NAME"]]
        oids = [ObjectId(i) for i in created_ids]
        if oids:
            enr = [e["_id"] for e in dbx.enrollments.find({"trainee_id": {"$in": oids}}, {"_id": 1})]
            dbx.trainees.delete_many({"_id": {"$in": oids}})
            dbx.enrollments.delete_many({"trainee_id": {"$in": oids}})
            dbx.employment_records.delete_many({"trainee_id": {"$in": oids}})
            dbx.non_placement_reasons.delete_many({"trainee_id": {"$in": oids}})
            dbx.consent_logs.delete_many({"trainee_id": {"$in": oids}})
            dbx.followups.delete_many({"$or": [{"trainee_id": {"$in": oids}},
                                               {"enrollment_id": {"$in": enr}}]})
        cli.close()
    except Exception as exc:  # pragma: no cover
        print(f"cleanup warning: {exc}")


class TestConsentEnforcedOnWritePaths:
    """Before revoke: writes succeed. After revoke: 403 on all write paths."""

    def test_write_paths_before_and_after_revoke(self, client, pctx, created_ids):
        tok = pctx["token"]
        tid = _create_trainee(client, tok, "QA_Enforce Privacy",
                              ["employment_status", "wage_data", "contact_for_verification"])
        created_ids.append(tid)

        enr = client.post(f"{API}/enrollments", json={
            "trainee_id": tid, "program_id": pctx["program_id"],
            "attendance_percent": 92, "assessment_score": 84, "certified": True,
            "certification_date": "2025-01-15",
        }, headers=_h(tok), timeout=60)
        assert enr.status_code == 200, enr.text[:300]
        enrollment_id = enr.json().get("_id") or enr.json().get("id")

        # --- pre-revoke: employment write succeeds with wage preserved
        emp = client.post(f"{API}/employment", json={
            "trainee_id": tid, "type": "employed", "employer_name": "PreRevoke Corp",
            "sector": "IT-ITeS", "wage_bracket": "15-25k",
        }, headers=_h(tok), timeout=60)
        assert emp.status_code == 200, emp.text[:300]
        assert emp.json()["wage_bracket"] == "15-25k"

        # --- pre-revoke: non-placement reason succeeds
        npr = client.post(f"{API}/non-placement-reason", json={
            "trainee_id": tid, "reason_category": "further_studies", "notes": "QA pre-revoke",
        }, headers=_h(tok), timeout=60)
        assert npr.status_code == 200, npr.text[:300]
        assert npr.json()["reason_category"] == "further_studies"

        # --- pre-revoke: schedule follow-ups creates pending rows for this enrollment
        sch = client.post(f"{API}/followups/schedule", json={"enrollment_id": enrollment_id},
                          headers=_h(tok), timeout=120)
        assert sch.status_code == 200, sch.text[:300]
        assert sch.json()["followups_created"] > 0, sch.json()

        fus = client.get(f"{API}/followups?trainee_id={tid}&status=pending",
                         headers=_h(tok), timeout=120)
        assert fus.status_code == 200, fus.text[:300]
        mine = fus.json()["items"]
        assert mine, "no pending follow-up found for QA trainee"
        fu_id = mine[0].get("_id") or mine[0].get("id")

        # --- pre-revoke: respond succeeds
        resp = client.post(f"{API}/followups/{fu_id}/respond", json={
            "channel_used": "whatsapp",
            "structured_response": {"employment_type": "employed", "wage_bracket": "15-25k"},
        }, headers=_h(tok), timeout=60)
        assert resp.status_code == 200, resp.text[:300]

        # a second pending follow-up for the post-revoke 403 check
        remaining = [f for f in mine if (f.get("_id") or f.get("id")) != fu_id]
        fu_id2 = (remaining[0].get("_id") or remaining[0].get("id")) if remaining else None

        # ------------------------- REVOKE -------------------------
        rev = client.post(f"{API}/trainees/{tid}/revoke-consent", headers=_h(tok), timeout=60)
        assert rev.status_code == 200, rev.text[:300]
        assert rev.json()["anonymized"] is True

        # --- post-revoke: employment must be 403
        emp2 = client.post(f"{API}/employment", json={
            "trainee_id": tid, "type": "employed", "employer_name": "PostRevoke Corp",
            "sector": "IT-ITeS", "wage_bracket": "25k+",
        }, headers=_h(tok), timeout=60)
        assert emp2.status_code == 403, f"expected 403, got {emp2.status_code}: {emp2.text[:300]}"

        # --- post-revoke: non-placement must be 403
        npr2 = client.post(f"{API}/non-placement-reason", json={
            "trainee_id": tid, "reason_category": "migrated", "notes": "QA post-revoke",
        }, headers=_h(tok), timeout=60)
        assert npr2.status_code == 403, f"expected 403, got {npr2.status_code}: {npr2.text[:300]}"

        # --- post-revoke: respond must be 403
        if fu_id2:
            resp2 = client.post(f"{API}/followups/{fu_id2}/respond", json={
                "channel_used": "sms",
                "structured_response": {"employment_type": "employed"},
            }, headers=_h(tok), timeout=60)
            assert resp2.status_code == 403, f"expected 403, got {resp2.status_code}: {resp2.text[:300]}"

        # --- post-revoke: no NEW employment record was persisted (still exactly 1)
        g = client.get(f"{API}/trainees/{tid}", headers=_h(tok), timeout=60)
        assert g.status_code == 200
        employers = [r.get("employer_name") for r in g.json()["employment"]]
        assert "PostRevoke Corp" not in employers, employers

    def test_schedule_skips_revoked_trainees(self, client, pctx, created_ids):
        """A revoked trainee's certified enrollment must not get new pending follow-ups."""
        tok = pctx["token"]
        tid = _create_trainee(client, tok, "QA_EnforceSchedule Privacy",
                              ["employment_status", "contact_for_verification"])
        created_ids.append(tid)
        enr = client.post(f"{API}/enrollments", json={
            "trainee_id": tid, "program_id": pctx["program_id"],
            "attendance_percent": 88, "assessment_score": 75, "certified": True,
            "certification_date": "2025-01-15",
        }, headers=_h(tok), timeout=60)
        assert enr.status_code == 200, enr.text[:300]
        enrollment_id = enr.json().get("_id") or enr.json().get("id")

        rev = client.post(f"{API}/trainees/{tid}/revoke-consent", headers=_h(tok), timeout=60)
        assert rev.status_code == 200, rev.text[:300]

        sch = client.post(f"{API}/followups/schedule", json={"enrollment_id": enrollment_id},
                          headers=_h(tok), timeout=120)
        assert sch.status_code == 200, sch.text[:300]
        assert sch.json()["followups_created"] == 0, \
            f"follow-ups scheduled for revoked trainee: {sch.json()}"

        # full-cycle schedule must also skip it
        sch_all = client.post(f"{API}/followups/schedule", json={}, headers=_h(tok), timeout=180)
        assert sch_all.status_code == 200, sch_all.text[:300]

        fus = client.get(f"{API}/followups?trainee_id={tid}", headers=_h(tok), timeout=120)
        assert fus.status_code == 200
        assert fus.json()["items"] == [], \
            "revoked trainee has follow-ups after schedule cycle"


class TestRevokeRegression:
    def test_revoke_preserves_aggregate_and_logs(self, client, pctx, created_ids):
        tok = pctx["token"]
        tid = _create_trainee(client, tok, "QA_EnforceAgg Privacy", ["employment_status"])
        created_ids.append(tid)
        client.post(f"{API}/enrollments", json={
            "trainee_id": tid, "program_id": pctx["program_id"],
            "attendance_percent": 60, "assessment_score": 55, "certified": False,
        }, headers=_h(tok), timeout=60)
        url = f"{API}/analytics/provider/{pctx['provider_id']}/summary"
        before = client.get(url, headers=_h(tok), timeout=120).json()["summary"]["total_trainees"]

        r = client.post(f"{API}/trainees/{tid}/revoke-consent", headers=_h(tok), timeout=60)
        assert r.status_code == 200, r.text[:300]

        t = client.get(f"{API}/trainees/{tid}", headers=_h(tok), timeout=60).json()["trainee"]
        assert t["full_name"].startswith("Anonymized Trainee #")
        assert t["phone_masked"] == "REDACTED"
        assert t["consent"]["given"] is False and t["consent"]["scope"] == []
        assert t.get("anonymized") is True
        assert "phone_number" not in t

        after = client.get(url, headers=_h(tok), timeout=120).json()["summary"]["total_trainees"]
        assert after >= before, f"aggregate dropped: {before} -> {after}"

        logs = client.get(f"{API}/trainees/{tid}/consent-logs", headers=_h(tok), timeout=60).json()["items"]
        actions = [x["action"] for x in logs]
        assert actions[0] == "granted" and "revoked" in actions, actions
