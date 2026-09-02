"""SkillTrace AI — database seeding script.

Run:  python seed.py

Creates all collections, applies indexes, and inserts realistic synthetic data:
  - 5 training providers across 3 districts
  - 10 training programs across sectors
  - 150 trainees enrolled across programs
  - Follow-ups + employment/non-placement records with a plausible distribution:
      ~60% employed/self-employed, ~15% unreachable, ~25% not placed
  - System users (one per role) for dashboard login

Idempotent: clears SkillTrace collections before re-seeding.
"""
import os
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from bson import ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient

from security import hash_password, encrypt_phone, mask_phone

load_dotenv(Path(__file__).parent / ".env")
random.seed(42)

client = MongoClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

STATE = "Maharashtra"
DISTRICTS = ["Pune", "Nashik", "Nagpur"]

SECTORS = [
    "Retail", "Welding", "IT/ITES", "Healthcare", "Beauty & Wellness",
    "Automotive", "Construction", "Apparel", "Electronics", "Hospitality",
]

FIRST_NAMES_M = ["Amit", "Rahul", "Suresh", "Vikram", "Ravi", "Sandeep", "Arjun", "Nikhil", "Prakash", "Manoj", "Deepak", "Kunal", "Sachin", "Rohit", "Ganesh"]
FIRST_NAMES_F = ["Priya", "Sunita", "Anjali", "Kavita", "Pooja", "Neha", "Sneha", "Meena", "Divya", "Rekha", "Swati", "Asha", "Komal", "Nisha", "Sonali"]
LAST_NAMES = ["Sharma", "Patil", "Deshmukh", "Kulkarni", "Jadhav", "Pawar", "Gupta", "Shinde", "More", "Chavan", "Kadam", "Joshi", "Naik", "Bhosale", "Gaikwad"]

WAGE_BRACKETS = ["<10k", "10-15k", "15-25k", "25k+"]
NON_PLACEMENT = ["skill_mismatch", "no_local_jobs", "migrated", "family_reasons", "low_wage_offered", "further_studies", "other"]
INTERVALS = [("1_month", 30), ("3_month", 90), ("6_month", 180), ("12_month", 365)]

RESPONSE_TEMPLATES = {
    "employed": [
        "Yes I got a job at {emp}, salary is around {wage} per month.",
        "Working now at {emp}. Happy with the training.",
        "Joined {emp} last month, earning {wage}.",
    ],
    "self_employed": [
        "I started my own small shop, earning about {wage}.",
        "Running my own business now, income is roughly {wage}.",
    ],
    "apprentice": [
        "I am doing apprenticeship at {emp}, stipend {wage}.",
        "Currently an apprentice at {emp}.",
    ],
    "unemployed": [
        "No job yet, no openings near my area.",
        "Still searching, the offered salary was too low.",
        "Had to move for family reasons, not working now.",
    ],
}


def rand_date(start_days_ago: int, end_days_ago: int) -> str:
    d = datetime.now(timezone.utc) - timedelta(days=random.randint(end_days_ago, start_days_ago))
    return d.date().isoformat()


def clear():
    for c in ["trainees", "training_providers", "training_programs", "enrollments",
              "followups", "employment_records", "non_placement_reasons", "users",
              "consent_logs"]:
        db[c].delete_many({})


def ensure_indexes():
    db.users.create_index("email", unique=True)
    db.trainees.create_index("phone_number")
    db.trainees.create_index("district")
    db.enrollments.create_index("trainee_id")
    db.enrollments.create_index("program_id")
    db.followups.create_index("trainee_id")
    db.followups.create_index("enrollment_id")
    db.employment_records.create_index("trainee_id")
    db.non_placement_reasons.create_index("trainee_id")
    db.training_programs.create_index("provider_id")
    db.consent_logs.create_index("trainee_id")


def seed():
    clear()

    # ---- Providers (5 across 3 districts) --------------------------------
    provider_defs = [
        ("Skill India Center Pune", "Pune"),
        ("Pragati Vocational Institute", "Pune"),
        ("Nashik Skill Hub", "Nashik"),
        ("Vidarbha Training Academy", "Nagpur"),
        ("Rojgar Kaushal Kendra", "Nagpur"),
    ]
    providers = []
    for i, (name, dist) in enumerate(provider_defs):
        pid = ObjectId()
        providers.append({"_id": pid, "name": name, "district": dist})
        db.training_providers.insert_one({
            "_id": pid, "name": name, "district": dist, "state": STATE,
            "accreditation_id": f"NSDC-{1000 + i}",
        })

    # ---- Programs (10 across sectors) ------------------------------------
    programs = []
    for i in range(10):
        prov = providers[i % len(providers)]
        sector = SECTORS[i]
        gid = ObjectId()
        start = datetime.now(timezone.utc) - timedelta(days=random.randint(400, 700))
        weeks = random.choice([8, 10, 12, 16])
        end = start + timedelta(weeks=weeks)
        programs.append({"_id": gid, "provider": prov, "sector": sector})
        db.training_programs.insert_one({
            "_id": gid, "provider_id": prov["_id"],
            "course_name": f"{sector} Skills Level {random.choice([1, 2])}",
            "sector": sector, "start_date": start.date().isoformat(),
            "end_date": end.date().isoformat(), "duration_weeks": weeks,
        })

    # ---- Trainees (150) + enrollments + outcomes -------------------------
    outcomes = (["placed"] * 90) + (["unreachable"] * 22) + (["not_placed"] * 38)  # 150
    random.shuffle(outcomes)

    for n in range(150):
        gender = random.choice(["Male", "Female"])
        first = random.choice(FIRST_NAMES_M if gender == "Male" else FIRST_NAMES_F)
        name = f"{first} {random.choice(LAST_NAMES)}"
        district = random.choice(DISTRICTS)
        phone = f"+91{random.randint(70, 99)}{random.randint(10000000, 99999999)}"
        dob = (datetime.now(timezone.utc) - timedelta(days=365 * random.randint(19, 42))).date().isoformat()
        consent_given = random.random() > 0.05
        tid = ObjectId()
        db.trainees.insert_one({
            "_id": tid, "full_name": name, "phone_number": encrypt_phone(phone),
            "phone_masked": mask_phone(phone), "dob": dob, "gender": gender,
            "district": district, "state": STATE,
            "consent": {
                "given": consent_given,
                "timestamp": (datetime.now(timezone.utc) - timedelta(days=random.randint(200, 500))) if consent_given else None,
                "scope": ["employment_status", "wage_data", "contact_for_verification"] if consent_given else [],
            },
            "created_at": datetime.now(timezone.utc) - timedelta(days=random.randint(200, 600)),
        })
        if consent_given:
            db.consent_logs.insert_one({
                "trainee_id": tid, "action": "granted",
                "timestamp": datetime.now(timezone.utc) - timedelta(days=random.randint(200, 500)),
                "performed_by": "system_intake",
            })

        # Enrollment (a few trainees enrolled in 2 programs)
        n_programs = 2 if random.random() < 0.12 else 1
        chosen = random.sample(programs, n_programs)
        outcome = outcomes[n]

        for prog in chosen:
            certified = random.random() > 0.1
            cert_date = rand_date(360, 180) if certified else None
            eid = ObjectId()
            db.enrollments.insert_one({
                "_id": eid, "trainee_id": tid, "program_id": prog["_id"],
                "attendance_percent": round(random.uniform(55, 99), 1),
                "assessment_score": round(random.uniform(40, 98), 1),
                "certified": certified, "certification_date": cert_date,
            })
            if certified:
                _seed_followups(tid, eid, prog, outcome)

        # Employment / non-placement outcome (once per trainee)
        _seed_outcome(tid, chosen[0], outcome)

    # ---- System users (one per role) -------------------------------------
    provider_user_prov = providers[0]
    users = [
        {"name": "Super Admin", "email": os.environ["ADMIN_EMAIL"], "password": os.environ["ADMIN_PASSWORD"], "role": "super_admin", "provider_id": None, "district": None},
        {"name": "Pune Provider", "email": "provider@skilltrace.gov.in", "password": "Provider@123", "role": "provider", "provider_id": provider_user_prov["_id"], "district": provider_user_prov["district"]},
        {"name": "Pune District Officer", "email": "district@skilltrace.gov.in", "password": "District@123", "role": "district_admin", "provider_id": None, "district": "Pune"},
        {"name": "State Officer", "email": "state@skilltrace.gov.in", "password": "State@123", "role": "state_admin", "provider_id": None, "district": None},
    ]
    for u in users:
        db.users.insert_one({
            "name": u["name"], "email": u["email"].lower(),
            "password_hash": hash_password(u["password"]), "role": u["role"],
            "provider_id": u["provider_id"], "district": u["district"],
            "created_at": datetime.now(timezone.utc),
        })

    ensure_indexes()
    _print_summary(users)


def _seed_followups(tid, eid, prog, outcome):
    for label, offset in INTERVALS:
        sched = rand_date(300, 10)
        if outcome == "unreachable":
            status = random.choice(["unreachable", "escalated_to_field_agent", "sent"])
            channel = random.choice(["whatsapp", "sms", "field_agent"])
            conf = "unreachable"
            raw, structured = None, None
        else:
            status = "responded"
            channel = random.choice(["whatsapp", "sms"])
            etype = _outcome_to_emp_type(outcome)
            wage = random.choice(WAGE_BRACKETS)
            emp = f"{prog['sector']} {random.choice(['Enterprises', 'Solutions', 'Works', 'Services'])}"
            raw = random.choice(RESPONSE_TEMPLATES[etype]).format(emp=emp, wage=wage)
            structured = {"employment_type": etype, "wage_bracket": wage, "employer_name": emp if etype != "unemployed" else None}
            conf = "self_reported"
        db.followups.insert_one({
            "trainee_id": tid, "enrollment_id": eid, "interval_label": label,
            "scheduled_date": sched, "status": status, "channel_used": channel,
            "raw_response_text": raw, "structured_response": structured,
            "confidence_score": conf,
            "created_at": datetime.now(timezone.utc) - timedelta(days=random.randint(1, 200)),
        })


def _outcome_to_emp_type(outcome):
    if outcome == "placed":
        return random.choices(["employed", "self_employed", "apprentice"], weights=[70, 20, 10])[0]
    return "unemployed"


def _seed_outcome(tid, prog, outcome):
    if outcome == "placed":
        etype = _outcome_to_emp_type(outcome)
        wage = random.choices(WAGE_BRACKETS, weights=[20, 35, 30, 15])[0]
        verified = random.random() < 0.4
        emp = f"{prog['sector']} {random.choice(['Enterprises', 'Solutions', 'Works', 'Services'])}"
        db.employment_records.insert_one({
            "trainee_id": tid, "type": etype,
            "employer_name": emp if etype != "self_employed" else None,
            "employer_contact": f"+91{random.randint(70, 99)}{random.randint(10000000, 99999999)}" if etype != "self_employed" else None,
            "sector": prog["sector"], "wage_bracket": wage,
            "employer_verified": verified,
            "verification_timestamp": datetime.now(timezone.utc) if verified else None,
            "reported_at": datetime.now(timezone.utc) - timedelta(days=random.randint(1, 180)),
        })
    elif outcome == "not_placed":
        db.employment_records.insert_one({
            "trainee_id": tid, "type": "unemployed", "employer_name": None,
            "employer_contact": None, "sector": prog["sector"], "wage_bracket": None,
            "employer_verified": False, "verification_timestamp": None,
            "reported_at": datetime.now(timezone.utc) - timedelta(days=random.randint(1, 180)),
        })
        db.non_placement_reasons.insert_one({
            "trainee_id": tid,
            "reason_category": random.choices(NON_PLACEMENT, weights=[22, 25, 12, 15, 14, 8, 4])[0],
            "notes": None,
            "reported_at": datetime.now(timezone.utc) - timedelta(days=random.randint(1, 180)),
        })
    # 'unreachable' -> no employment record (unknown outcome, tracked via followups)


def _print_summary(users):
    print("\n=== SkillTrace AI seed complete ===")
    print(f"  providers            : {db.training_providers.count_documents({})}")
    print(f"  programs             : {db.training_programs.count_documents({})}")
    print(f"  trainees             : {db.trainees.count_documents({})}")
    print(f"  enrollments          : {db.enrollments.count_documents({})}")
    print(f"  followups            : {db.followups.count_documents({})}")
    print(f"  employment_records   : {db.employment_records.count_documents({})}")
    print(f"  non_placement_reasons: {db.non_placement_reasons.count_documents({})}")
    print(f"  users                : {db.users.count_documents({})}")
    emp = db.employment_records.count_documents({"type": {"$in": ["employed", "self_employed", "apprentice"]}})
    unemp = db.employment_records.count_documents({"type": "unemployed"})
    print(f"  -> placed records    : {emp}")
    print(f"  -> unemployed records: {unemp}")
    print("\n  Login accounts:")
    for u in users:
        print(f"    [{u['role']}] {u['email']} / {u['password']}")
    print("===================================\n")


if __name__ == "__main__":
    seed()
