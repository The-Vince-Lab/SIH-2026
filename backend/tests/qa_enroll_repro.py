"""Repro: provider cannot create an enrollment for a brand-new trainee (403)."""
import os
import requests
from dotenv import dotenv_values

BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL")).rstrip("/") + "/api"

s = requests.Session()
r = s.post(f"{BASE}/auth/login", json={"email": "provider@skilltrace.gov.in", "password": "Provider@123"})
tok = r.json()["access_token"]
prov = r.json()["user"]["provider_id"]
s.headers.update({"Authorization": f"Bearer {tok}"})
print("provider_id", prov)

programs = s.get(f"{BASE}/programs").json()
mine = [p for p in programs if str(p.get("provider_id")) == str(prov)]
print("total programs", len(programs), "mine", len(mine), [p["course_name"] for p in mine])

t = s.post(f"{BASE}/trainees", json={
    "full_name": "QA_UI_Repro Person", "phone_number": "+919812345699",
    "dob": "1998-04-15", "gender": "Female", "district": "Pune", "state": "Maharashtra",
    "consent": {"given": True, "scope": ["employment_status"]},
})
print("create trainee", t.status_code, t.json())
tid = t.json().get("id") or t.json().get("_id")

if mine:
    e = s.post(f"{BASE}/enrollments", json={
        "trainee_id": tid, "program_id": mine[0]["_id"],
        "attendance_percent": 80, "assessment_score": 70, "certified": False,
    })
    print("enrollment OWN program ->", e.status_code, e.text[:200])

other = [p for p in programs if str(p.get("provider_id")) != str(prov)]
if other:
    e2 = s.post(f"{BASE}/enrollments", json={
        "trainee_id": tid, "program_id": other[0]["_id"],
        "attendance_percent": 80, "assessment_score": 70, "certified": False,
    })
    print("enrollment OTHER provider program ->", e2.status_code, e2.text[:200])
