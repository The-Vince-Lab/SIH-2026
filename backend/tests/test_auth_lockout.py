"""FIX VERIFICATION: brute-force lockout on POST /api/auth/login (per-email, 429 not 500)."""
import os
import uuid

import pytest
import requests

from conftest import API, CREDS


def _post_login(client, email, password):
    return client.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=60)


# --- Module: AUTH lockout ---------------------------------------------------
class TestLockoutNonExistentEmail:
    """Hammer a throwaway (non-existent) email: 5x401 then 429, never 500."""

    THROWAWAY = "locktest@skilltrace.gov.in"

    def test_five_failures_then_429(self, client):
        codes = []
        for _ in range(8):
            r = _post_login(client, self.THROWAWAY, "WrongPass!1")
            codes.append(r.status_code)
        print(f"lockout codes for {self.THROWAWAY}: {codes}")
        assert 500 not in codes, f"login 500'd during lockout: {codes}"
        assert codes[:5] == [401] * 5, f"first 5 attempts should be 401, got {codes}"
        assert all(c == 429 for c in codes[5:]), f"attempts 6+ should be 429, got {codes}"
        last = _post_login(client, self.THROWAWAY, "WrongPass!1")
        assert last.status_code == 429
        assert "detail" in last.json()

    def test_unrelated_account_still_logs_in_while_other_locked(self, client):
        """Lockout must be keyed per-email, not global."""
        email, password = CREDS["provider"]
        r = _post_login(client, email, password)
        assert r.status_code == 200, f"unrelated account blocked by another email's lockout: {r.status_code} {r.text[:300]}"
        d = r.json()
        assert d["user"]["email"] == email
        assert d["user"]["role"] == "provider"
        assert isinstance(d["access_token"], str) and d["access_token"].count(".") == 2


class TestLockoutRealAccountValidPassword:
    """A throwaway REAL account: once locked, even the correct password returns 429."""

    email = f"test_lock_{uuid.uuid4().hex[:8]}@skilltrace.gov.in"
    password = "LockMe@123"

    def test_create_throwaway_account(self, client, admin_headers):
        r = client.post(f"{API}/auth/register", headers=admin_headers, json={
            "name": "TEST_Lock User", "email": self.email,
            "password": self.password, "role": "provider"}, timeout=60)
        assert r.status_code in (200, 201), r.text
        ok = _post_login(client, self.email, self.password)
        assert ok.status_code == 200, f"fresh account cannot log in: {ok.text[:300]}"

    def test_valid_password_returns_429_while_locked(self, client):
        codes = [_post_login(client, self.email, "BadPass!1").status_code for _ in range(5)]
        print(f"failure codes: {codes}")
        assert codes == [401] * 5, codes
        r = _post_login(client, self.email, self.password)
        assert r.status_code == 429, f"valid password while locked should be 429, got {r.status_code} {r.text[:300]}"

    def test_cleanup_lockout_and_login_again(self, client):
        """Clearing login_attempts (simulating TTL expiry) restores login."""
        import subprocess
        subprocess.run(
            ["mongosh", os.environ["DB_NAME"], "--quiet", "--eval",
             f'db.login_attempts.deleteMany({{identifier: "{self.email}"}})'],
            check=False, capture_output=True)
        r = _post_login(client, self.email, self.password)
        assert r.status_code == 200, f"login still blocked after clearing attempts: {r.status_code} {r.text[:300]}"
        subprocess.run(["mongosh", os.environ["DB_NAME"], "--quiet", "--eval",
                        f'db.users.deleteMany({{email: "{self.email}"}})'],
                       check=False, capture_output=True)


class TestSeededAccountsStillWork:
    @pytest.mark.parametrize("role", list(CREDS.keys()))
    def test_all_four_accounts_get_jwt(self, client, role):
        email, password = CREDS[role]
        r = _post_login(client, email, password)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["token_type"] == "bearer"
        assert d["user"]["role"] == role
        assert "password_hash" not in d["user"]


class TestLockoutInfra:
    def test_login_attempts_indexes(self):
        import subprocess
        out = subprocess.run(["mongosh", os.environ["DB_NAME"], "--quiet", "--eval",
                              "JSON.stringify(db.login_attempts.getIndexes())"],
                             capture_output=True, text=True).stdout
        print(out)
        assert "identifier" in out, "missing identifier index"
        assert "expireAfterSeconds" in out, "missing TTL index on expires_at"

    def test_bcrypt_hash_format(self):
        import subprocess
        out = subprocess.run(["mongosh", os.environ["DB_NAME"], "--quiet", "--eval",
                              'db.users.findOne({email:"admin@skilltrace.gov.in"}).password_hash'],
                             capture_output=True, text=True).stdout.strip()
        assert out.startswith("$2b$"), f"unexpected hash format: {out[:20]}"

    def test_cors_credentials_config(self):
        """Actual (non-preflight) response must not pair ACAO:* with allow-credentials:true."""
        r = requests.post(f"{API}/auth/login",
                          json={"email": CREDS["provider"][0], "password": CREDS["provider"][1]},
                          headers={"Origin": "https://evil.example.com"}, timeout=60)
        print(dict(r.headers))
        allow_origin = r.headers.get("access-control-allow-origin")
        allow_creds = r.headers.get("access-control-allow-credentials")
        assert not (allow_origin == "*" and allow_creds == "true"), \
            "CORS wildcard origin combined with allow_credentials=true"
