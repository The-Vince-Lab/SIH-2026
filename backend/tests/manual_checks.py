"""Ad-hoc verification: at-risk payload sample, auth playbook items, leftover data."""
import json
import os

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

fe = dotenv_values("/app/frontend/.env")
be = dotenv_values("/app/backend/.env")
API = (os.environ.get("REACT_APP_BACKEND_URL") or fe["REACT_APP_BACKEND_URL"]).rstrip("/") + "/api"

s = requests.Session()
r = s.post(f"{API}/auth/login", json={"email": "provider@skilltrace.gov.in", "password": "Provider@123"}, timeout=60)
print("provider login:", r.status_code)
print("login body keys:", list(r.json().keys()))
print("set-cookie:", r.headers.get("set-cookie"))
print("session cookies:", s.cookies.get_dict())
d = r.json()
pid = (d.get("user") or {}).get("provider_id") or d.get("provider_id")
h = {"Authorization": f"Bearer {d['access_token']}"}

for lvl in ("high", "medium", "all"):
    ar = s.get(f"{API}/analytics/provider/{pid}/at-risk-trainees?level={lvl}", headers=h, timeout=120)
    body = ar.json()
    print(f"level={lvl} status={ar.status_code} count={body.get('count')}")
    if lvl == "high" and body.get("at_risk_trainees"):
        print("sample row:", json.dumps(body["at_risk_trainees"][0], indent=2)[:600])

# CORS preflight
pf = requests.options(f"{API}/auth/login", timeout=30, headers={
    "Origin": (os.environ.get("REACT_APP_BACKEND_URL") or fe["REACT_APP_BACKEND_URL"]),
    "Access-Control-Request-Method": "POST",
    "Access-Control-Request-Headers": "content-type"})
print("CORS preflight:", pf.status_code, {k: v for k, v in pf.headers.items() if k.lower().startswith("access-control")})

c = MongoClient(be["MONGO_URL"])
db = c[be["DB_NAME"]]
u = db.users.find_one({"email": "admin@skilltrace.gov.in"})
print("admin hash prefix:", (u.get("password_hash") or u.get("hashed_password") or "")[:7])
print("leftover QA_ trainees:", db.trainees.count_documents({"full_name": {"$regex": "^QA_"}}))
print("trainees total:", db.trainees.count_documents({}))
print("login_attempts:", db.login_attempts.count_documents({}))
c.close()
