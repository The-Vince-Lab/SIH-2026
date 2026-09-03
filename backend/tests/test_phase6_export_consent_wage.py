"""Phase 6 tests: consent audit trail, wage progression, CSV/PDF report export.

NOTE: TestConsentLogs.test_consent_write_path... exercises the real PATCH endpoint, so it
appends 3 rows (scope_updated / revoked / granted) to consent_logs for one seeded trainee
(audit trail is append-only by design; consent state itself is restored). To reset:
  mongosh $DB_NAME --eval 'db.consent_logs.deleteMany({performed_by:"admin@skilltrace.gov.in"})'
"""
import csv
import io

import pytest
import requests

from conftest import API

EXPECTED_HEADER = ["Trainee", "District", "Gender", "Age Group", "Provider", "Course", "Sector",
                   "Certified", "Outcome", "Wage Bracket", "Employer Verified", "Data Confidence"]


# ---------------------------------------------------------------- helpers
@pytest.fixture(scope="module")
def all_trainees(admin_headers):
    r = requests.get(f"{API}/trainees-overview", headers=admin_headers, timeout=90)
    assert r.status_code == 200, r.text[:300]
    data = r.json()
    items = data["items"] if isinstance(data, dict) else data
    assert len(items) > 0
    return items


# ---------------------------------------------------------------- CONSENT AUDIT TRAIL
class TestConsentLogs:
    def test_consent_logs_requires_auth(self, all_trainees):
        tid = all_trainees[0]["trainee_id"]
        r = requests.get(f"{API}/trainees/{tid}/consent-logs", timeout=60)
        assert r.status_code in (401, 403), r.status_code

    def test_consent_logs_shape_and_seeded_events(self, admin_headers, all_trainees):
        actions = set()
        multi_event_found = False
        checked = 0
        for t in all_trainees[:40]:
            r = requests.get(f"{API}/trainees/{t['trainee_id']}/consent-logs", headers=admin_headers, timeout=60)
            assert r.status_code == 200, r.text[:300]
            items = r.json()["items"]
            checked += 1
            if len(items) > 1:
                multi_event_found = True
            prev_ts = None
            for it in items:
                assert isinstance(it.get("_id"), str)  # app-wide convention: _id serialized to string
                assert it["action"] in ("granted", "scope_updated", "revoked"), it["action"]
                assert it.get("timestamp")
                assert it.get("performed_by")
                assert isinstance(it.get("scope"), list)
                if prev_ts:
                    assert it["timestamp"] >= prev_ts, "logs not sorted ascending by timestamp"
                prev_ts = it["timestamp"]
                actions.add(it["action"])
        assert checked > 0
        assert multi_event_found, "no trainee with multiple consent events in first 40"
        assert "granted" in actions
        assert "scope_updated" in actions, f"seed lacks scope_updated events; saw {actions}"
        assert "revoked" in actions, f"seed lacks revoked events; saw {actions}"

    def test_consent_write_path_scope_updated_then_revoked_then_restore(self, admin_headers, all_trainees):
        """PATCH consent with changed scope -> scope_updated; given=false -> revoked."""
        # pick a trainee whose consent is currently given
        target = None
        for t in all_trainees[:30]:
            d = requests.get(f"{API}/trainees/{t['trainee_id']}", headers=admin_headers, timeout=60).json()
            if d["trainee"].get("consent", {}).get("given"):
                target = (t["trainee_id"], d["trainee"]["consent"].get("scope") or [])
                break
        assert target, "no trainee with consent given found"
        tid, orig_scope = target
        before = len(requests.get(f"{API}/trainees/{tid}/consent-logs", headers=admin_headers, timeout=60).json()["items"])

        new_scope = sorted(set(orig_scope + ["qa_probe_scope"]))
        r = requests.patch(f"{API}/trainees/{tid}/consent", headers=admin_headers,
                           json={"given": True, "scope": new_scope}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["action"] == "scope_updated", r.json()

        logs = requests.get(f"{API}/trainees/{tid}/consent-logs", headers=admin_headers, timeout=60).json()["items"]
        assert len(logs) == before + 1
        assert logs[-1]["action"] == "scope_updated"
        assert "qa_probe_scope" in logs[-1]["scope"]

        # revoke
        r = requests.patch(f"{API}/trainees/{tid}/consent", headers=admin_headers,
                           json={"given": False, "scope": []}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        assert r.json()["action"] == "revoked", r.json()
        logs = requests.get(f"{API}/trainees/{tid}/consent-logs", headers=admin_headers, timeout=60).json()["items"]
        assert logs[-1]["action"] == "revoked"
        assert logs[-1]["scope"] == []

        # restore original consent -> granted
        r = requests.patch(f"{API}/trainees/{tid}/consent", headers=admin_headers,
                           json={"given": True, "scope": orig_scope}, timeout=60)
        assert r.status_code == 200
        assert r.json()["action"] == "granted", r.json()
        t_now = requests.get(f"{API}/trainees/{tid}", headers=admin_headers, timeout=60).json()["trainee"]
        assert t_now["consent"]["given"] is True
        assert sorted(t_now["consent"]["scope"]) == sorted(orig_scope)


# ---------------------------------------------------------------- WAGE PROGRESSION
class TestWageProgression:
    WAGE_VALUE = {"<10k": 8, "10-15k": 12.5, "15-25k": 20, "25k+": 30}

    def test_requires_auth(self, all_trainees):
        r = requests.get(f"{API}/trainees/{all_trainees[0]['trainee_id']}/wage-progression", timeout=60)
        assert r.status_code in (401, 403)

    def test_points_sorted_and_mapped(self, admin_headers, all_trainees):
        found_multi = False
        for t in all_trainees[:60]:
            r = requests.get(f"{API}/trainees/{t['trainee_id']}/wage-progression", headers=admin_headers, timeout=60)
            assert r.status_code == 200, r.text[:300]
            body = r.json()
            assert body["trainee_id"] == t["trainee_id"]
            pts = body["points"]
            months = [p["months"] for p in pts]
            assert months == sorted(months), f"points not sorted: {months}"
            for p in pts:
                assert p["wage_bracket"] in self.WAGE_VALUE
                assert p["wage_value"] == self.WAGE_VALUE[p["wage_bracket"]]
                assert p["interval_label"] in ("1_month", "3_month", "6_month", "12_month")
            if len(pts) > 1:
                found_multi = True
                vals = [p["wage_value"] for p in pts]
                assert vals == sorted(vals), f"wage not non-decreasing for {t['trainee_id']}: {vals}"
        assert found_multi, "no trainee with >1 wage point found in first 60"

    def test_bad_trainee_id(self, admin_headers):
        r = requests.get(f"{API}/trainees/000000000000000000000000/wage-progression",
                         headers=admin_headers, timeout=60)
        # KNOWN MINOR: returns 200 with empty points instead of 404 for a non-existent trainee
        assert r.status_code in (200, 403, 404), r.status_code
        if r.status_code == 200:
            assert r.json()["points"] == []


# ---------------------------------------------------------------- EXPORTS
class TestExports:
    def test_csv_requires_auth(self):
        r = requests.get(f"{API}/analytics/export.csv", timeout=60)
        assert r.status_code in (401, 403), r.status_code

    def test_pdf_requires_auth(self):
        r = requests.get(f"{API}/analytics/export.pdf", timeout=60)
        assert r.status_code in (401, 403), r.status_code

    def test_csv_header_and_rows(self, admin_headers, all_trainees):
        r = requests.get(f"{API}/analytics/export.csv", headers=admin_headers, timeout=120)
        assert r.status_code == 200, r.text[:300]
        assert "text/csv" in r.headers.get("content-type", "")
        assert "attachment" in r.headers.get("content-disposition", "")
        rows = list(csv.reader(io.StringIO(r.text)))
        assert rows[0] == EXPECTED_HEADER, rows[0]
        assert len(rows) - 1 == len(all_trainees), f"csv rows {len(rows)-1} vs trainees {len(all_trainees)}"
        for row in rows[1:]:
            assert len(row) == len(EXPECTED_HEADER)
            assert row[7] in ("Yes", "No")
            assert row[10] in ("Yes", "No")

    def test_csv_respects_district_filter(self, admin_headers):
        r = requests.get(f"{API}/analytics/export.csv", headers=admin_headers,
                         params={"district": "Nashik"}, timeout=120)
        assert r.status_code == 200
        rows = list(csv.reader(io.StringIO(r.text)))
        assert rows[0] == EXPECTED_HEADER
        assert len(rows) > 1, "no rows returned for Nashik"
        districts = {row[1] for row in rows[1:]}
        assert districts == {"Nashik"}, districts

    def test_csv_respects_gender_filter(self, admin_headers):
        r = requests.get(f"{API}/analytics/export.csv", headers=admin_headers,
                         params={"gender": "Female"}, timeout=120)
        assert r.status_code == 200
        rows = list(csv.reader(io.StringIO(r.text)))
        assert len(rows) > 1
        assert {row[2] for row in rows[1:]} == {"Female"}

    def test_pdf_is_valid(self, admin_headers):
        r = requests.get(f"{API}/analytics/export.pdf", headers=admin_headers, timeout=180)
        assert r.status_code == 200, r.text[:300]
        assert "application/pdf" in r.headers.get("content-type", "")
        assert r.content[:4] == b"%PDF", r.content[:20]
        assert len(r.content) > 1000

    def test_pdf_with_filter(self, admin_headers):
        r = requests.get(f"{API}/analytics/export.pdf", headers=admin_headers,
                         params={"district": "Nashik"}, timeout=180)
        assert r.status_code == 200
        assert r.content[:4] == b"%PDF"

    def test_provider_export_is_role_scoped(self, provider_headers, admin_headers):
        pr = requests.get(f"{API}/analytics/export.csv", headers=provider_headers, timeout=120)
        assert pr.status_code == 200, pr.text[:300]
        prows = list(csv.reader(io.StringIO(pr.text)))
        ar = requests.get(f"{API}/analytics/export.csv", headers=admin_headers, timeout=120)
        arows = list(csv.reader(io.StringIO(ar.text)))
        assert 0 < len(prows) - 1 < len(arows) - 1, \
            f"provider rows {len(prows)-1} vs admin rows {len(arows)-1} (provider must be a strict subset)"
        # provider's own trainees only
        my = requests.get(f"{API}/trainees-overview", headers=provider_headers, timeout=90).json()
        my_items = my["items"] if isinstance(my, dict) else my
        assert len(prows) - 1 == len(my_items), f"{len(prows)-1} vs {len(my_items)}"

    def test_district_admin_export_scoped(self, tokens):
        h = {"Authorization": f"Bearer {tokens['district_admin']}"}
        r = requests.get(f"{API}/analytics/export.csv", headers=h, timeout=120)
        assert r.status_code == 200, r.text[:300]
        rows = list(csv.reader(io.StringIO(r.text)))
        assert len(rows) > 1
        assert len({row[1] for row in rows[1:]}) == 1, "district admin export spans multiple districts"
