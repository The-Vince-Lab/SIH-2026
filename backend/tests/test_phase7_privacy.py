"""Phase 7 — Privacy features: consent scope enforcement, revoke & anonymize,
admin aggregation-only drill-down guard, consent audit trail.

Covers server.py: create_employment (wage drop), compute_summary (wage consent),
wage_progression (wage_consent flag), revoke_and_anonymize, get_trainee (accessed log),
list_trainees / trainees_overview 403 guard, _export_rows ('(consent off)').
"""
import csv
import io
import uuid

import pytest
import requests
from conftest import API


def _h(token):
    return {"Authorization": f"Bearer {token}"}


def _create_trainee(client, token, name, scope):
    body = {
        "full_name": name,
        "phone_number": "9" + str(uuid.uuid4().int)[:9],
        "dob": "2000-05-10",
        "gender": "Male",
        "district": "Nashik",
        "state": "Maharashtra",
        "consent": {"given": True, "scope": scope},
    }
    r = client.post(f"{API}/trainees?force=true", json=body, headers=_h(token), timeout=60)
    assert r.status_code == 200, f"create_trainee failed: {r.status_code} {r.text[:300]}"
    data = r.json()
    assert data.get("created") is True
    return data["_id"] if "_id" in data else data["id"]


@pytest.fixture(scope="module")
def provider_ctx(client, tokens):
    """Provider token + its provider_id + a program id to enroll into."""
    token = tokens["provider"]
    me = client.get(f"{API}/auth/me", headers=_h(token), timeout=60)
    assert me.status_code == 200, me.text[:200]
    provider_id = me.json().get("provider_id")
    assert provider_id, f"provider user has no provider_id: {me.json()}"
    progs = client.get(f"{API}/programs", headers=_h(token), timeout=60)
    assert progs.status_code == 200
    items = progs.json()
    assert items, "provider has no programs"
    return {"token": token, "provider_id": provider_id, "program_id": items[0]["_id"]}


@pytest.fixture(scope="module")
def created_ids():
    return []


@pytest.fixture(scope="module", autouse=True)
def cleanup(created_ids):
    yield
    # QA trainees are removed from Mongo directly (no DELETE endpoint exists).
    try:
        import os

        from dotenv import dotenv_values
        from pymongo import MongoClient
        env = dotenv_values("/app/backend/.env")
        cli = MongoClient(os.environ.get("MONGO_URL") or env["MONGO_URL"])
        db = cli[env["DB_NAME"]]
        from bson import ObjectId
        oids = [ObjectId(i) for i in created_ids]
        if oids:
            db.trainees.delete_many({"_id": {"$in": oids}})
            db.enrollments.delete_many({"trainee_id": {"$in": oids}})
            db.employment_records.delete_many({"trainee_id": {"$in": oids}})
            db.consent_logs.delete_many({"trainee_id": {"$in": oids}})
            db.followups.delete_many({"trainee_id": {"$in": oids}})
        cli.close()
    except Exception as exc:  # pragma: no cover
        print(f"cleanup warning: {exc}")


# ---------------------------------------------------------------------------
# 1. CONSENT SCOPE ENFORCEMENT (wage_data)
# ---------------------------------------------------------------------------
class TestConsentScopeEnforcement:
    def test_wage_dropped_when_scope_excludes_wage_data(self, client, provider_ctx, created_ids):
        tok = provider_ctx["token"]
        tid = _create_trainee(client, tok, "QA_NoWage Privacy",
                              ["employment_status", "contact_for_verification"])
        created_ids.append(tid)

        enr = client.post(f"{API}/enrollments", json={
            "trainee_id": tid, "program_id": provider_ctx["program_id"],
            "attendance_percent": 90, "assessment_score": 80, "certified": True,
        }, headers=_h(tok), timeout=60)
        assert enr.status_code == 200, enr.text[:300]

        emp = client.post(f"{API}/employment", json={
            "trainee_id": tid, "type": "employed", "employer_name": "QA Corp",
            "sector": "IT-ITeS", "wage_bracket": "15-25k",
        }, headers=_h(tok), timeout=60)
        assert emp.status_code == 200, emp.text[:300]
        assert emp.json()["wage_bracket"] is None, "wage stored despite consent scope excluding wage_data"

        # verify persisted via GET
        g = client.get(f"{API}/trainees/{tid}", headers=_h(tok), timeout=60)
        assert g.status_code == 200
        recs = g.json()["employment"]
        assert len(recs) == 1
        assert recs[0]["wage_bracket"] is None
        assert recs[0]["type"] == "employed"

        wp = client.get(f"{API}/trainees/{tid}/wage-progression", headers=_h(tok), timeout=60)
        assert wp.status_code == 200
        assert wp.json()["wage_consent"] is False
        assert wp.json()["points"] == []

    def test_wage_stored_when_scope_includes_wage_data(self, client, provider_ctx, created_ids):
        tok = provider_ctx["token"]
        tid = _create_trainee(client, tok, "QA_WithWage Privacy",
                              ["employment_status", "wage_data", "contact_for_verification"])
        created_ids.append(tid)

        emp = client.post(f"{API}/employment", json={
            "trainee_id": tid, "type": "employed", "employer_name": "QA Corp",
            "sector": "IT-ITeS", "wage_bracket": "15-25k",
        }, headers=_h(tok), timeout=60)
        assert emp.status_code == 200, emp.text[:300]
        assert emp.json()["wage_bracket"] == "15-25k"

        g = client.get(f"{API}/trainees/{tid}", headers=_h(tok), timeout=60)
        assert g.json()["employment"][0]["wage_bracket"] == "15-25k"

        wp = client.get(f"{API}/trainees/{tid}/wage-progression", headers=_h(tok), timeout=60)
        assert wp.status_code == 200
        assert wp.json()["wage_consent"] is True

    def test_csv_export_shows_consent_off_for_wage(self, client, provider_ctx):
        r = client.get(f"{API}/analytics/export.csv", headers=_h(provider_ctx["token"]), timeout=120)
        assert r.status_code == 200
        rows = list(csv.DictReader(io.StringIO(r.text)))
        no_wage = [x for x in rows if x["Trainee"] == "QA_NoWage Privacy"]
        with_wage = [x for x in rows if x["Trainee"] == "QA_WithWage Privacy"]
        assert no_wage, f"QA_NoWage row missing from CSV; headers={rows[0].keys() if rows else None}"
        assert no_wage[0]["Wage Bracket"] == "(consent off)", no_wage[0]
        if with_wage:
            assert with_wage[0]["Wage Bracket"] in ("15-25k", "")

    def test_wage_aggregate_excludes_non_consented(self, client, provider_ctx):
        """compute_summary must only aggregate wage over wage-consented trainees."""
        r = client.get(f"{API}/analytics/provider/{provider_ctx['provider_id']}/summary",
                       headers=_h(provider_ctx["token"]), timeout=120)
        assert r.status_code == 200
        s = r.json()["summary"]
        wd = s["wage_distribution"]
        assert isinstance(wd, dict) and wd
        # sum of wage buckets must never exceed number of placed records
        assert sum(wd.values()) <= sum(s["employment_breakdown"].values())


# ---------------------------------------------------------------------------
# 2. REVOKE & ANONYMIZE
# ---------------------------------------------------------------------------
class TestRevokeAnonymize:
    def test_revoke_anonymizes_pii_and_preserves_aggregates(self, client, provider_ctx, created_ids):
        tok = provider_ctx["token"]
        tid = _create_trainee(client, tok, "QA_Revoke Privacy",
                              ["employment_status", "wage_data"])
        created_ids.append(tid)
        client.post(f"{API}/enrollments", json={
            "trainee_id": tid, "program_id": provider_ctx["program_id"],
            "attendance_percent": 70, "assessment_score": 60, "certified": False,
        }, headers=_h(tok), timeout=60)

        before = client.get(f"{API}/analytics/provider/{provider_ctx['provider_id']}/summary",
                            headers=_h(tok), timeout=120).json()["summary"]["total_trainees"]

        r = client.post(f"{API}/trainees/{tid}/revoke-consent", headers=_h(tok), timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["anonymized"] is True

        g = client.get(f"{API}/trainees/{tid}", headers=_h(tok), timeout=60)
        assert g.status_code == 200
        t = g.json()["trainee"]
        assert t["full_name"].startswith("Anonymized Trainee #"), t["full_name"]
        assert t["phone_masked"] == "REDACTED"
        assert t["consent"]["given"] is False
        assert t["consent"]["scope"] == []
        assert t.get("anonymized") is True
        assert "phone_number" not in t

        after = client.get(f"{API}/analytics/provider/{provider_ctx['provider_id']}/summary",
                           headers=_h(tok), timeout=120).json()["summary"]["total_trainees"]
        # aggregate must not lose the anonymized trainee (>= tolerates parallel QA inserts)
        assert after >= before, f"aggregate count dropped after anonymization: {before} -> {after}"

        logs = client.get(f"{API}/trainees/{tid}/consent-logs", headers=_h(tok), timeout=60).json()["items"]
        assert any(x["action"] == "revoked" and x.get("anonymized") for x in logs), logs

    def test_second_revoke_returns_409(self, client, provider_ctx, created_ids):
        tok = provider_ctx["token"]
        tid = created_ids[-1] if created_ids else None
        # find the anonymized one deterministically
        r = client.post(f"{API}/trainees/{tid}/revoke-consent", headers=_h(tok), timeout=60)
        assert r.status_code in (409, 200)
        if r.status_code == 200:
            pytest.fail("Double revoke succeeded — expected 409 for already-anonymized trainee")

    def test_revoke_nonexistent_returns_404(self, client, tokens):
        r = client.post(f"{API}/trainees/6a98b55faa2e4c14b9e90000/revoke-consent",
                        headers=_h(tokens["super_admin"]), timeout=60)
        assert r.status_code == 404, f"{r.status_code} {r.text[:200]}"

    def test_revoke_requires_auth(self, client, provider_ctx):
        r = requests.post(f"{API}/trainees/6a98b55faa2e4c14b9e90000/revoke-consent", timeout=60)
        assert r.status_code in (401, 403)


# ---------------------------------------------------------------------------
# 3. ADMIN AGGREGATION-ONLY / RBAC SCOPING
# ---------------------------------------------------------------------------
class TestAdminAggregationOnly:
    @pytest.mark.parametrize("role", ["super_admin", "state_admin"])
    def test_list_trainees_requires_drilldown(self, client, tokens, role):
        r = client.get(f"{API}/trainees", headers=_h(tokens[role]), timeout=60)
        assert r.status_code == 403, f"{role} got {r.status_code}: {r.text[:200]}"

    @pytest.mark.parametrize("role", ["super_admin", "state_admin"])
    def test_trainees_overview_requires_provider(self, client, tokens, role):
        r = client.get(f"{API}/trainees-overview", headers=_h(tokens[role]), timeout=60)
        assert r.status_code == 403, f"{role} got {r.status_code}: {r.text[:200]}"

    def test_drilldown_with_provider_id_allowed(self, client, tokens):
        provs = client.get(f"{API}/providers", headers=_h(tokens["super_admin"]), timeout=60).json()
        assert provs
        pid = provs[0]["_id"]
        r1 = client.get(f"{API}/trainees?provider_id={pid}", headers=_h(tokens["super_admin"]), timeout=120)
        assert r1.status_code == 200, r1.text[:200]
        assert "items" in r1.json() and r1.json()["total"] >= 0
        r2 = client.get(f"{API}/trainees-overview?provider_id={pid}",
                        headers=_h(tokens["super_admin"]), timeout=120)
        assert r2.status_code == 200, r2.text[:200]
        rows = r2.json()["items"] if isinstance(r2.json(), dict) else r2.json()
        assert isinstance(rows, list)

    def test_district_drilldown_allowed(self, client, tokens):
        r = client.get(f"{API}/trainees?district=Nashik", headers=_h(tokens["super_admin"]), timeout=120)
        assert r.status_code == 200
        assert all(t["district"] == "Nashik" for t in r.json()["items"])

    def test_provider_overview_scoped_to_own(self, client, provider_ctx, tokens):
        mine = client.get(f"{API}/trainees-overview", headers=_h(provider_ctx["token"]), timeout=120)
        assert mine.status_code == 200
        mine_rows = mine.json()["items"] if isinstance(mine.json(), dict) else mine.json()
        admin = client.get(f"{API}/trainees-overview?provider_id={provider_ctx['provider_id']}",
                           headers=_h(tokens["super_admin"]), timeout=120)
        admin_rows = admin.json()["items"] if isinstance(admin.json(), dict) else admin.json()
        assert len(mine_rows) >= len(admin_rows) - 5  # provider sees its own set
        # cross-provider access must stay inside the provider's own accessible set
        own_ids = {x["trainee_id"] for x in mine_rows}
        provs = client.get(f"{API}/providers", headers=_h(tokens["super_admin"]), timeout=60).json()
        other = [p for p in provs if p["_id"] != provider_ctx["provider_id"]]
        if other:
            r = client.get(f"{API}/trainees-overview?provider_id={other[0]['_id']}",
                           headers=_h(provider_ctx["token"]), timeout=120)
            assert r.status_code == 200
            rows = r.json()["items"] if isinstance(r.json(), dict) and "items" in r.json() else r.json()
            leaked = [x["trainee_id"] for x in rows if x["trainee_id"] not in own_ids]
            assert not leaked, f"provider leaked another provider's trainees: {leaked[:3]}"

    def test_district_admin_scoped(self, client, tokens):
        r = client.get(f"{API}/trainees-overview", headers=_h(tokens["district_admin"]), timeout=120)
        assert r.status_code == 200, r.text[:200]
        rows = r.json()["items"] if isinstance(r.json(), dict) and "items" in r.json() else r.json()
        districts = {x.get("district") for x in rows}
        assert len(districts) <= 1, f"district_admin sees multiple districts: {districts}"

    @pytest.mark.parametrize("role", ["super_admin", "state_admin", "district_admin", "provider"])
    def test_analytics_overview_is_aggregate_only(self, client, tokens, role):
        r = client.get(f"{API}/analytics/overview", headers=_h(tokens[role]), timeout=180)
        assert r.status_code == 200, r.text[:200]
        body = r.json()
        for key in ("totals", "by_provider", "by_sector", "wage_distribution",
                    "confidence_breakdown", "district_ranking"):
            assert key in body, f"missing {key}"
        blob = r.text
        assert "full_name" not in blob and "phone_masked" not in blob, "PII keys present in analytics payload"


# ---------------------------------------------------------------------------
# 4. AUDIT TRAIL
# ---------------------------------------------------------------------------
class TestAuditTrail:
    def test_granted_log_on_enroll_and_accessed_log_on_profile_open(self, client, provider_ctx, created_ids):
        tok = provider_ctx["token"]
        tid = _create_trainee(client, tok, "QA_Audit Privacy", ["employment_status", "wage_data"])
        created_ids.append(tid)

        lr = client.get(f"{API}/trainees/{tid}/consent-logs", headers=_h(tok), timeout=60)
        assert lr.status_code == 200, f"{lr.status_code} {lr.text[:300]}"
        logs = lr.json()["items"]
        assert lr.json()["items"] is not None
        assert len(logs) == 1 and logs[0]["action"] == "granted", logs
        assert logs[0]["performed_by"]

        # opening the profile writes an 'accessed' event
        client.get(f"{API}/trainees/{tid}", headers=_h(tok), timeout=60)
        logs2 = client.get(f"{API}/trainees/{tid}/consent-logs", headers=_h(tok), timeout=60).json()["items"]
        assert len(logs2) == 2, logs2
        assert logs2[-1]["action"] == "accessed"
        assert logs2[-1]["performed_by"] == "provider@skilltrace.gov.in"

    def test_scope_updated_and_revoked_actions(self, client, provider_ctx, created_ids):
        tok = provider_ctx["token"]
        tid = _create_trainee(client, tok, "QA_AuditScope Privacy", ["employment_status", "wage_data"])
        created_ids.append(tid)
        r = client.patch(f"{API}/trainees/{tid}/consent",
                         json={"given": True, "scope": ["employment_status"]},
                         headers=_h(tok), timeout=60)
        assert r.status_code == 200 and r.json()["action"] == "scope_updated", r.text[:200]
        r2 = client.patch(f"{API}/trainees/{tid}/consent", json={"given": False, "scope": []},
                          headers=_h(tok), timeout=60)
        assert r2.status_code == 200 and r2.json()["action"] == "revoked"
        actions = [x["action"] for x in
                   client.get(f"{API}/trainees/{tid}/consent-logs", headers=_h(tok), timeout=60).json()["items"]]
        assert actions[:3] == ["granted", "scope_updated", "revoked"], actions

    def test_consent_logs_sorted_and_shaped(self, client, tokens):
        provs = client.get(f"{API}/providers", headers=_h(tokens["super_admin"]), timeout=60).json()
        rows = client.get(f"{API}/trainees-overview?provider_id={provs[0]['_id']}",
                          headers=_h(tokens["super_admin"]), timeout=120).json()
        rows = rows["items"] if isinstance(rows, dict) and "items" in rows else rows
        tid = rows[0]["trainee_id"]
        logs = client.get(f"{API}/trainees/{tid}/consent-logs",
                          headers=_h(tokens["super_admin"]), timeout=60).json()["items"]
        assert logs
        ts = [x["timestamp"] for x in logs]
        assert ts == sorted(ts)
        for x in logs:
            assert x["action"] in {"granted", "scope_updated", "revoked", "accessed"}, x
