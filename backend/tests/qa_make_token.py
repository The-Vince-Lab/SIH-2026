"""Generate an employer verification token for UI testing of /verify/:token."""
import requests
from dotenv import dotenv_values

BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL")).rstrip("/") + "/api"
s = requests.Session()
r = s.post(f"{BASE}/auth/login", json={"email": "provider@skilltrace.gov.in", "password": "Provider@123"})
s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
pid = r.json()["user"]["provider_id"]
tid = s.get(f"{BASE}/trainees-overview?provider_id={pid}").json()["items"][1]["trainee_id"]

emp = s.post(f"{BASE}/employment", json={
    "trainee_id": tid, "type": "employed", "wage_bracket": "15-25k",
    "employer_name": "QA_Test Employer Pvt Ltd", "sector": "Retail"})
print("employment", emp.status_code)
eid = emp.json().get("id") or emp.json().get("_id")
v = s.post(f"{BASE}/employment/{eid}/request-verification")
print("verification", v.status_code, v.json())
