"""Shared fixtures for SkillTrace AI backend tests."""
import os

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
_base = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not _base:
    raise RuntimeError("REACT_APP_BACKEND_URL missing from env and /app/frontend/.env")
BASE_URL = _base.rstrip("/")
API = f"{BASE_URL}/api"

CREDS = {
    "super_admin": ("admin@skilltrace.gov.in", "Admin@123"),
    "provider": ("provider@skilltrace.gov.in", "Provider@123"),
    "district_admin": ("district@skilltrace.gov.in", "District@123"),
    "state_admin": ("state@skilltrace.gov.in", "State@123"),
}


@pytest.fixture(scope="session")
def api_url():
    return API


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


def _login(client, role):
    email, password = CREDS[role]
    r = client.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"Login failed for {role}: {r.status_code} {r.text[:300]}")
    token = r.json().get("access_token")
    if not token:
        pytest.fail(f"No access_token in login response for {role}: {r.text[:300]}")
    return token


@pytest.fixture(scope="session")
def tokens(client):
    return {role: _login(client, role) for role in CREDS}


@pytest.fixture(scope="session")
def admin_headers(tokens):
    return {"Authorization": f"Bearer {tokens['super_admin']}"}


@pytest.fixture(scope="session")
def provider_headers(tokens):
    return {"Authorization": f"Bearer {tokens['provider']}"}
