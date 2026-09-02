"""Repro: trainee risk endpoint for a certified trainee shown in provider table."""
import requests
from dotenv import dotenv_values

BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL")).rstrip("/") + "/api"
s = requests.Session()
r = s.post(f"{BASE}/auth/login", json={"email": "provider@skilltrace.gov.in", "password": "Provider@123"})
s.headers.update({"Authorization": f"Bearer {r.json()['access_token']}"})
pid = r.json()["user"]["provider_id"]

ov = s.get(f"{BASE}/trainees-overview?provider_id={pid}").json()["items"]
for it in ov[:5]:
    tid = it["trainee_id"]
    rr = s.get(f"{BASE}/analytics/trainee/{tid}/risk")
    det = s.get(f"{BASE}/trainees/{tid}").json()
    print(it["full_name"], "| certified:", it.get("certified"), "| enrollments:", len(det.get("enrollments", [])),
          "| risk:", rr.status_code, str(rr.json())[:160])
