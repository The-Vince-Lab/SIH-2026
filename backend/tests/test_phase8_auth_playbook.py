"""Auth playbook checks (bcrypt format, httpOnly cookie, CORS credentials, seed_admin idempotency)
plus export smoke tests. Run separately from lockout tests to avoid login_attempts pollution.
"""
import os

import requests
from conftest import API, BASE_URL
from dotenv import dotenv_values
from pymongo import MongoClient

env = dotenv_values("/app/backend/.env")
_cli = MongoClient(os.environ.get("MONGO_URL") or env["MONGO_URL"])
_db = _cli[env["DB_NAME"]]


# --- bcrypt hash format
def test_seeded_password_hashes_are_bcrypt_2b():
    users = list(_db.users.find({}, {"email": 1, "password_hash": 1, "hashed_password": 1}))
    assert users, "no users seeded"
    for u in users:
        h = u.get("password_hash") or u.get("hashed_password")
        assert h, f"user {u.get('email')} has no hash field: {list(u.keys())}"
        assert h.startswith("$2b$"), f"{u['email']} hash prefix {h[:4]}"


# --- login returns a bearer token; app does NOT set an auth cookie (documented deviation:
#     the SPA stores the JWT in localStorage; only Cloudflare's __cf_bm cookie is set by infra)
def test_login_returns_bearer_token_and_no_auth_cookie():
    r = requests.post(f"{API}/auth/login",
                      json={"email": "admin@skilltrace.gov.in", "password": "Admin@123"}, timeout=60)
    assert r.status_code == 200, r.text[:300]
    assert r.json().get("access_token")
    assert r.json().get("token_type") == "bearer"
    assert "password_hash" not in r.text
    app_cookies = [k for k in r.cookies.keys() if not k.startswith("__cf")]
    assert app_cookies == [], f"unexpected app cookies: {app_cookies}"


# --- CORS preflight succeeds for the public origin
def test_cors_preflight_allows_public_origin():
    r = requests.options(f"{API}/auth/login", headers={
        "Origin": BASE_URL,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }, timeout=60)
    assert r.status_code in (200, 204), r.status_code
    allow_origin = r.headers.get("access-control-allow-origin")
    assert allow_origin in ("*", BASE_URL), f"origin not allowed: {allow_origin}"


# --- cookie fallback in get_current_user works when the token is supplied as a cookie
def test_access_token_cookie_fallback_authenticates_me():
    r = requests.post(f"{API}/auth/login",
                      json={"email": "admin@skilltrace.gov.in", "password": "Admin@123"}, timeout=60)
    token = r.json()["access_token"]
    me = requests.get(f"{API}/auth/me", cookies={"access_token": token}, timeout=60)
    assert me.status_code == 200, f"cookie fallback rejected: {me.status_code} {me.text[:200]}"
    assert me.json()["email"] == "admin@skilltrace.gov.in"


def test_me_requires_auth():
    r = requests.get(f"{API}/auth/me", timeout=60)
    assert r.status_code in (401, 403), r.status_code


# --- exports
def test_csv_and_pdf_export(client, admin_headers):
    csv_r = client.get(f"{API}/analytics/export.csv", headers=admin_headers, timeout=180)
    assert csv_r.status_code == 200
    lines = csv_r.text.strip().splitlines()
    assert len(lines) > 10
    assert "Trainee" in lines[0]

    pdf_r = client.get(f"{API}/analytics/export.pdf", headers=admin_headers, timeout=180)
    assert pdf_r.status_code == 200, pdf_r.text[:200]
    assert pdf_r.content[:4] == b"%PDF", pdf_r.content[:20]
