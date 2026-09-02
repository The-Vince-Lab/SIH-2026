"""SkillTrace AI — FastAPI backend (Phase 2).

REST API with JWT auth + role-based access control over the Phase 1 collections.
Roles: provider | district_admin | state_admin | super_admin
"""
import os
import logging
import secrets
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request, Query
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field
from bson import ObjectId
from bson.errors import InvalidId

from auth import create_access_token, decode_token
from security import hash_password, verify_password, encrypt_phone, mask_phone
from db import ensure_indexes
from ml import text_classifier, identity_matching, response_classifier, placement_risk

# ---------------------------------------------------------------------------
# App / DB setup
# ---------------------------------------------------------------------------
client = AsyncIOMotorClient(os.environ["MONGO_URL"], tz_aware=True)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="SkillTrace AI API")
api = APIRouter(prefix="/api")

ADMIN_ROLES = {"district_admin", "state_admin", "super_admin"}
FULL_ACCESS_ROLES = {"state_admin", "super_admin"}
PLACED_TYPES = {"employed", "self_employed", "apprentice"}
WAGE_ORDER = ["<10k", "10-15k", "15-25k", "25k+"]


# ---------------------------------------------------------------------------
# Serialization helper
# ---------------------------------------------------------------------------
def ser(doc):
    if isinstance(doc, list):
        return [ser(d) for d in doc]
    if isinstance(doc, dict):
        return {k: ser(v) for k, v in doc.items()}
    if isinstance(doc, ObjectId):
        return str(doc)
    if isinstance(doc, datetime):
        return doc.isoformat()
    return doc


def oid(value: str) -> ObjectId:
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail="Invalid id format")


# ---------------------------------------------------------------------------
# Auth dependencies
# ---------------------------------------------------------------------------
async def get_current_user(request: Request) -> dict:
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = decode_token(token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    user = await db.users.find_one({"_id": oid(payload["sub"])})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    user["_id"] = str(user["_id"])
    if user.get("provider_id"):
        user["provider_id"] = str(user["provider_id"])
    user.pop("password_hash", None)
    return user


def require_role(*roles: str):
    async def checker(user: dict = Depends(get_current_user)) -> dict:
        if user["role"] not in roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return user
    return checker


# ---------------------------------------------------------------------------
# Scoping helpers
# ---------------------------------------------------------------------------
async def program_ids_for_provider(provider_id: ObjectId) -> List[ObjectId]:
    progs = await db.training_programs.find({"provider_id": provider_id}, {"_id": 1}).to_list(1000)
    return [p["_id"] for p in progs]


async def trainee_ids_for_programs(program_ids: List[ObjectId]) -> List[ObjectId]:
    if not program_ids:
        return []
    ids = await db.enrollments.distinct("trainee_id", {"program_id": {"$in": program_ids}})
    return ids


async def accessible_trainee_ids(user: dict) -> Optional[List[ObjectId]]:
    """None => unrestricted (all trainees). Otherwise the allowed list."""
    if user["role"] in FULL_ACCESS_ROLES:
        return None
    if user["role"] == "provider":
        if not user.get("provider_id"):
            return []
        pids = await program_ids_for_provider(ObjectId(user["provider_id"]))
        return await trainee_ids_for_programs(pids)
    if user["role"] == "district_admin":
        docs = await db.trainees.find({"district": user.get("district")}, {"_id": 1}).to_list(100000)
        return [d["_id"] for d in docs]
    return []


async def assert_trainee_access(user: dict, trainee_id: ObjectId):
    allowed = await accessible_trainee_ids(user)
    if allowed is None:
        return
    if trainee_id not in allowed:
        raise HTTPException(status_code=403, detail="Not authorized for this trainee")


# ===========================================================================
# 1. AUTH
# ===========================================================================
class RegisterBody(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(min_length=6)
    role: str
    provider_id: Optional[str] = None
    district: Optional[str] = None


class LoginBody(BaseModel):
    email: EmailStr
    password: str


@api.post("/auth/register")
async def register(body: RegisterBody, admin: dict = Depends(require_role("super_admin", "state_admin"))):
    if body.role not in {"provider", "district_admin", "state_admin", "super_admin"}:
        raise HTTPException(status_code=400, detail="Invalid role")
    email = body.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="Email already registered")
    doc = {
        "name": body.name, "email": email, "password_hash": hash_password(body.password),
        "role": body.role,
        "provider_id": ObjectId(body.provider_id) if body.provider_id else None,
        "district": body.district, "created_at": datetime.now(timezone.utc),
    }
    res = await db.users.insert_one(doc)
    return {"id": str(res.inserted_id), "email": email, "role": body.role}


async def _check_lockout(identifier: str):
    rec = await db.login_attempts.find_one({"identifier": identifier})
    if rec and rec.get("count", 0) >= 5:
        locked = rec.get("locked_until")
        if locked is not None:
            if locked.tzinfo is None:
                locked = locked.replace(tzinfo=timezone.utc)
            if locked > datetime.now(timezone.utc):
                raise HTTPException(status_code=429, detail="Too many failed attempts. Try again later.")


async def _register_failure(identifier: str):
    now = datetime.now(timezone.utc)
    await db.login_attempts.update_one(
        {"identifier": identifier},
        {"$inc": {"count": 1},
         "$set": {"locked_until": now + timedelta(minutes=15), "expires_at": now + timedelta(minutes=30)}},
        upsert=True,
    )


@api.post("/auth/login")
async def login(body: LoginBody, request: Request):
    email = body.email.lower()
    identifier = email  # proxy-safe: ingress hop IP rotates, so key on email only
    await _check_lockout(identifier)
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(body.password, user["password_hash"]):
        await _register_failure(identifier)
        raise HTTPException(status_code=401, detail="Invalid email or password")
    await db.login_attempts.delete_one({"identifier": identifier})
    token = create_access_token(user)
    return {
        "access_token": token, "token_type": "bearer",
        "user": {"id": str(user["_id"]), "name": user["name"], "email": user["email"],
                 "role": user["role"],
                 "provider_id": str(user["provider_id"]) if user.get("provider_id") else None,
                 "district": user.get("district")},
    }


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user


# ===========================================================================
# 2. TRAINEES + CONSENT
# ===========================================================================
class ConsentBody(BaseModel):
    given: bool = True
    scope: List[str] = Field(default_factory=lambda: ["employment_status", "wage_data", "contact_for_verification"])


class TraineeBody(BaseModel):
    full_name: str
    phone_number: str
    dob: Optional[str] = None
    gender: Optional[str] = None
    district: str
    state: str = "Maharashtra"
    consent: ConsentBody = Field(default_factory=ConsentBody)


@api.post("/trainees")
async def create_trainee(body: TraineeBody, user: dict = Depends(require_role("provider", "district_admin", "state_admin", "super_admin"))):
    now = datetime.now(timezone.utc)
    doc = {
        "full_name": body.full_name, "phone_number": encrypt_phone(body.phone_number),
        "phone_masked": mask_phone(body.phone_number), "dob": body.dob, "gender": body.gender,
        "district": body.district, "state": body.state,
        "consent": {"given": body.consent.given, "timestamp": now if body.consent.given else None,
                    "scope": body.consent.scope if body.consent.given else []},
        "created_at": now,
    }
    res = await db.trainees.insert_one(doc)
    if body.consent.given:
        await db.consent_logs.insert_one({"trainee_id": res.inserted_id, "action": "granted",
                                          "timestamp": now, "performed_by": user["email"]})
    doc["_id"] = res.inserted_id
    doc.pop("phone_number", None)
    return ser(doc)


@api.get("/trainees")
async def list_trainees(
    user: dict = Depends(get_current_user),
    district: Optional[str] = None,
    provider_id: Optional[str] = None,
    program_id: Optional[str] = None,
    limit: int = Query(100, le=1000),
    skip: int = 0,
):
    query = {}
    allowed = await accessible_trainee_ids(user)
    if allowed is not None:
        query["_id"] = {"$in": allowed}
    if program_id:
        tids = await trainee_ids_for_programs([oid(program_id)])
        query["_id"] = {"$in": _intersect(query.get("_id"), tids)}
    if provider_id:
        pids = await program_ids_for_provider(oid(provider_id))
        tids = await trainee_ids_for_programs(pids)
        query["_id"] = {"$in": _intersect(query.get("_id"), tids)}
    if district:
        query["district"] = district
    total = await db.trainees.count_documents(query)
    docs = await db.trainees.find(query, {"phone_number": 0}).skip(skip).limit(limit).to_list(limit)
    return {"total": total, "items": ser(docs)}


def _intersect(existing, new_ids):
    if existing is None:
        return new_ids
    existing_set = set(existing["$in"]) if isinstance(existing, dict) else set(existing)
    return [i for i in new_ids if i in existing_set]


@api.get("/trainees/{trainee_id}")
async def get_trainee(trainee_id: str, user: dict = Depends(get_current_user)):
    tid = oid(trainee_id)
    await assert_trainee_access(user, tid)
    doc = await db.trainees.find_one({"_id": tid}, {"phone_number": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Trainee not found")
    enrollments = await db.enrollments.find({"trainee_id": tid}).to_list(50)
    employment = await db.employment_records.find({"trainee_id": tid}).to_list(50)
    return {"trainee": ser(doc), "enrollments": ser(enrollments), "employment": ser(employment)}


@api.patch("/trainees/{trainee_id}/consent")
async def update_consent(trainee_id: str, body: ConsentBody, user: dict = Depends(get_current_user)):
    tid = oid(trainee_id)
    await assert_trainee_access(user, tid)
    if not await db.trainees.find_one({"_id": tid}):
        raise HTTPException(status_code=404, detail="Trainee not found")
    now = datetime.now(timezone.utc)
    action = "granted" if body.given else "revoked"
    await db.trainees.update_one({"_id": tid}, {"$set": {
        "consent": {"given": body.given, "timestamp": now if body.given else None,
                    "scope": body.scope if body.given else []}}})
    await db.consent_logs.insert_one({"trainee_id": tid, "action": action, "timestamp": now,
                                      "performed_by": user["email"]})
    return {"trainee_id": trainee_id, "consent": {"given": body.given, "scope": body.scope if body.given else []}}


# ===========================================================================
# 3. ENROLLMENTS
# ===========================================================================
class EnrollmentBody(BaseModel):
    trainee_id: str
    program_id: str
    attendance_percent: float = 0
    assessment_score: float = 0
    certified: bool = False
    certification_date: Optional[str] = None


class EnrollmentUpdate(BaseModel):
    attendance_percent: Optional[float] = None
    assessment_score: Optional[float] = None
    certified: Optional[bool] = None
    certification_date: Optional[str] = None


@api.post("/enrollments")
async def create_enrollment(body: EnrollmentBody, user: dict = Depends(require_role("provider", "district_admin", "state_admin", "super_admin"))):
    tid = oid(body.trainee_id)
    await assert_trainee_access(user, tid)
    if not await db.trainees.find_one({"_id": tid}):
        raise HTTPException(status_code=404, detail="Trainee not found")
    if not await db.training_programs.find_one({"_id": oid(body.program_id)}):
        raise HTTPException(status_code=404, detail="Program not found")
    doc = {"trainee_id": tid, "program_id": oid(body.program_id),
           "attendance_percent": body.attendance_percent, "assessment_score": body.assessment_score,
           "certified": body.certified, "certification_date": body.certification_date}
    res = await db.enrollments.insert_one(doc)
    doc["_id"] = res.inserted_id
    return ser(doc)


@api.get("/enrollments/{enrollment_id}")
async def get_enrollment(enrollment_id: str, user: dict = Depends(get_current_user)):
    doc = await db.enrollments.find_one({"_id": oid(enrollment_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    await assert_trainee_access(user, doc["trainee_id"])
    return ser(doc)


@api.patch("/enrollments/{enrollment_id}")
async def update_enrollment(enrollment_id: str, body: EnrollmentUpdate, user: dict = Depends(require_role("provider", "district_admin", "state_admin", "super_admin"))):
    doc = await db.enrollments.find_one({"_id": oid(enrollment_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    await assert_trainee_access(user, doc["trainee_id"])
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if updates:
        await db.enrollments.update_one({"_id": doc["_id"]}, {"$set": updates})
    return ser({**doc, **updates})


# ===========================================================================
# 4. FOLLOW-UPS
# ===========================================================================
INTERVALS = [("1_month", 30), ("3_month", 90), ("6_month", 180), ("12_month", 365)]


class ScheduleBody(BaseModel):
    enrollment_id: Optional[str] = None  # None => run cycle for all certified enrollments


@api.post("/followups/schedule")
async def schedule_followups(body: ScheduleBody, user: dict = Depends(require_role("district_admin", "state_admin", "super_admin", "provider"))):
    query = {"certified": True, "certification_date": {"$ne": None}}
    if body.enrollment_id:
        query = {"_id": oid(body.enrollment_id)}
    enrollments = await db.enrollments.find(query).to_list(100000)
    created = 0
    for e in enrollments:
        if not e.get("certification_date"):
            continue
        try:
            cert = datetime.fromisoformat(e["certification_date"])
        except ValueError:
            continue
        for label, offset in INTERVALS:
            exists = await db.followups.find_one({"enrollment_id": e["_id"], "interval_label": label})
            if exists:
                continue
            await db.followups.insert_one({
                "trainee_id": e["trainee_id"], "enrollment_id": e["_id"], "interval_label": label,
                "scheduled_date": (cert + timedelta(days=offset)).date().isoformat(),
                "status": "pending", "channel_used": None, "raw_response_text": None,
                "structured_response": None, "confidence_score": "unreachable",
                "created_at": datetime.now(timezone.utc),
            })
            created += 1
    return {"followups_created": created, "enrollments_processed": len(enrollments)}


class RespondBody(BaseModel):
    channel_used: str = "whatsapp"
    structured_response: Optional[dict] = None  # e.g. {"employment_type":"employed","wage_bracket":"15-25k"}
    raw_response_text: Optional[str] = None
    unreachable: bool = False


@api.post("/followups/{followup_id}/respond")
async def respond_followup(followup_id: str, body: RespondBody, user: dict = Depends(get_current_user)):
    fu = await db.followups.find_one({"_id": oid(followup_id)})
    if not fu:
        raise HTTPException(status_code=404, detail="Follow-up not found")
    await assert_trainee_access(user, fu["trainee_id"])

    if body.unreachable:
        await db.followups.update_one({"_id": fu["_id"]}, {"$set": {
            "status": "unreachable", "channel_used": body.channel_used, "confidence_score": "unreachable"}})
        return {"followup_id": followup_id, "status": "unreachable"}

    classification = None
    structured = body.structured_response
    if body.raw_response_text and not structured:
        classification = text_classifier.classify(body.raw_response_text)
        structured = {"employment_type": classification["employment_type"],
                      "wage_bracket": classification["wage_bracket"]}
    if structured is None:
        raise HTTPException(status_code=400, detail="Provide structured_response or raw_response_text")

    await db.followups.update_one({"_id": fu["_id"]}, {"$set": {
        "status": "responded", "channel_used": body.channel_used,
        "raw_response_text": body.raw_response_text, "structured_response": structured,
        "confidence_score": "self_reported"}})
    return {"followup_id": followup_id, "status": "responded",
            "structured_response": structured, "classification": classification}


@api.get("/followups")
async def list_followups(user: dict = Depends(get_current_user), trainee_id: Optional[str] = None,
                         status: Optional[str] = None, limit: int = Query(200, le=2000)):
    query = {}
    if trainee_id:
        tid = oid(trainee_id)
        await assert_trainee_access(user, tid)
        query["trainee_id"] = tid
    else:
        allowed = await accessible_trainee_ids(user)
        if allowed is not None:
            query["trainee_id"] = {"$in": allowed}
    if status:
        query["status"] = status
    docs = await db.followups.find(query).limit(limit).to_list(limit)
    return {"total": len(docs), "items": ser(docs)}


# ===========================================================================
# 5. EMPLOYMENT
# ===========================================================================
class EmploymentBody(BaseModel):
    trainee_id: str
    type: str  # employed|self_employed|apprentice|unemployed
    employer_name: Optional[str] = None
    employer_contact: Optional[str] = None
    sector: Optional[str] = None
    wage_bracket: Optional[str] = None


@api.post("/employment")
async def create_employment(body: EmploymentBody, user: dict = Depends(get_current_user)):
    tid = oid(body.trainee_id)
    await assert_trainee_access(user, tid)
    if body.type not in {"employed", "self_employed", "apprentice", "unemployed"}:
        raise HTTPException(status_code=400, detail="Invalid employment type")
    doc = {"trainee_id": tid, "type": body.type, "employer_name": body.employer_name,
           "employer_contact": body.employer_contact, "sector": body.sector,
           "wage_bracket": body.wage_bracket, "employer_verified": False,
           "verification_timestamp": None, "reported_at": datetime.now(timezone.utc)}
    res = await db.employment_records.insert_one(doc)
    doc["_id"] = res.inserted_id
    return ser(doc)


@api.post("/employment/{employment_id}/request-verification")
async def request_verification(employment_id: str, user: dict = Depends(get_current_user)):
    rec = await db.employment_records.find_one({"_id": oid(employment_id)})
    if not rec:
        raise HTTPException(status_code=404, detail="Employment record not found")
    await assert_trainee_access(user, rec["trainee_id"])
    token = secrets.token_urlsafe(24)
    await db.verification_tokens.insert_one({
        "token": token, "employment_id": rec["_id"], "trainee_id": rec["trainee_id"],
        "used": False, "created_at": datetime.now(timezone.utc),
        "expires_at": datetime.now(timezone.utc) + timedelta(days=14),
    })
    base = os.environ.get("REACT_APP_BACKEND_URL", "")
    return {"token": token, "verification_path": f"/verify/{token}",
            "verification_url": f"{base}/verify/{token}" if base else f"/verify/{token}"}


class VerifyBody(BaseModel):
    confirmed: bool
    employer_name: Optional[str] = None


@api.post("/employment/verify/{token}")
async def verify_employment(token: str, body: VerifyBody):
    """PUBLIC — employer clicks link, confirms yes/no. No auth."""
    vt = await db.verification_tokens.find_one({"token": token})
    if not vt:
        raise HTTPException(status_code=404, detail="Invalid verification link")
    if vt.get("used"):
        raise HTTPException(status_code=409, detail="This link has already been used")
    exp = vt.get("expires_at")
    if exp is not None:
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            raise HTTPException(status_code=410, detail="This verification link has expired")
    now = datetime.now(timezone.utc)
    updates = {"employer_verified": bool(body.confirmed),
               "verification_timestamp": now if body.confirmed else None}
    if body.employer_name:
        updates["employer_name"] = body.employer_name
    await db.employment_records.update_one({"_id": vt["employment_id"]}, {"$set": updates})
    await db.verification_tokens.update_one({"_id": vt["_id"]}, {"$set": {"used": True, "used_at": now}})
    return {"employment_id": str(vt["employment_id"]), "employer_verified": bool(body.confirmed)}


@api.get("/employment/verify/{token}")
async def verification_info(token: str):
    """PUBLIC — employer preview before confirming."""
    vt = await db.verification_tokens.find_one({"token": token})
    if not vt:
        raise HTTPException(status_code=404, detail="Invalid verification link")
    rec = await db.employment_records.find_one({"_id": vt["employment_id"]})
    trainee = await db.trainees.find_one({"_id": vt["trainee_id"]}, {"phone_number": 0})
    return {"used": vt.get("used", False),
            "trainee_name": trainee["full_name"] if trainee else None,
            "type": rec["type"] if rec else None,
            "employer_name": rec.get("employer_name") if rec else None,
            "sector": rec.get("sector") if rec else None}


# ===========================================================================
# 6. NON-PLACEMENT REASON
# ===========================================================================
class NonPlacementBody(BaseModel):
    trainee_id: str
    reason_category: str
    notes: Optional[str] = None


@api.post("/non-placement-reason")
async def create_non_placement(body: NonPlacementBody, user: dict = Depends(get_current_user)):
    tid = oid(body.trainee_id)
    await assert_trainee_access(user, tid)
    valid = {"skill_mismatch", "no_local_jobs", "migrated", "family_reasons",
             "low_wage_offered", "further_studies", "other"}
    if body.reason_category not in valid:
        raise HTTPException(status_code=400, detail="Invalid reason category")
    doc = {"trainee_id": tid, "reason_category": body.reason_category, "notes": body.notes,
           "reported_at": datetime.now(timezone.utc)}
    res = await db.non_placement_reasons.insert_one(doc)
    doc["_id"] = res.inserted_id
    return ser(doc)


# ===========================================================================
# 7. ANALYTICS
# ===========================================================================
async def compute_summary(trainee_ids: List[ObjectId]) -> dict:
    if not trainee_ids:
        return {"total_trainees": 0, "certified": 0, "placement_rate": 0,
                "employment_breakdown": {}, "wage_distribution": {}, "verified_count": 0,
                "confidence_breakdown": {}, "reachable_rate": 0}
    tset = {"$in": trainee_ids}
    total = len(trainee_ids)
    certified = await db.enrollments.count_documents({"trainee_id": tset, "certified": True})

    emp = await db.employment_records.aggregate([
        {"$match": {"trainee_id": tset}},
        {"$group": {"_id": "$type", "count": {"$sum": 1}}},
    ]).to_list(20)
    breakdown = {e["_id"]: e["count"] for e in emp}
    placed = sum(v for k, v in breakdown.items() if k in PLACED_TYPES)
    with_record = sum(breakdown.values())
    placement_rate = round(placed / with_record * 100, 1) if with_record else 0

    wage = await db.employment_records.aggregate([
        {"$match": {"trainee_id": tset, "type": {"$in": list(PLACED_TYPES)}, "wage_bracket": {"$ne": None}}},
        {"$group": {"_id": "$wage_bracket", "count": {"$sum": 1}}},
    ]).to_list(20)
    wage_dist = {w: 0 for w in WAGE_ORDER}
    for w in wage:
        wage_dist[w["_id"]] = w["count"]

    verified = await db.employment_records.count_documents({"trainee_id": tset, "employer_verified": True})

    conf = await db.followups.aggregate([
        {"$match": {"trainee_id": tset}},
        {"$group": {"_id": "$confidence_score", "count": {"$sum": 1}}},
    ]).to_list(20)
    conf_breakdown = {c["_id"]: c["count"] for c in conf}

    unreachable = await db.followups.count_documents({"trainee_id": tset, "status": {"$in": ["unreachable", "escalated_to_field_agent"]}})
    total_fu = await db.followups.count_documents({"trainee_id": tset})
    reachable_rate = round((total_fu - unreachable) / total_fu * 100, 1) if total_fu else 0

    return {"total_trainees": total, "certified": certified, "placement_rate": placement_rate,
            "employment_breakdown": breakdown, "wage_distribution": wage_dist,
            "verified_count": verified, "confidence_breakdown": conf_breakdown,
            "reachable_rate": reachable_rate}


def _authorize_provider_view(user: dict, provider_id: str):
    if user["role"] == "provider" and user.get("provider_id") != provider_id:
        raise HTTPException(status_code=403, detail="Providers can only view their own analytics")
    if user["role"] == "district_admin":
        pass  # district admin allowed; scoping handled by data


@api.get("/analytics/provider/{provider_id}/summary")
async def provider_summary(provider_id: str, user: dict = Depends(get_current_user)):
    _authorize_provider_view(user, provider_id)
    provider = await db.training_providers.find_one({"_id": oid(provider_id)})
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    if user["role"] == "district_admin" and provider["district"] != user.get("district"):
        raise HTTPException(status_code=403, detail="Outside your district")
    pids = await program_ids_for_provider(oid(provider_id))
    tids = await trainee_ids_for_programs(pids)
    summary = await compute_summary(tids)
    # per-course mini summary
    courses = []
    for pid in pids:
        prog = await db.training_programs.find_one({"_id": pid})
        ctids = await trainee_ids_for_programs([pid])
        cs = await compute_summary(ctids)
        courses.append({"program_id": str(pid), "course_name": prog["course_name"],
                        "sector": prog["sector"], "placement_rate": cs["placement_rate"],
                        "total_trainees": cs["total_trainees"]})
    return {"provider": ser(provider), "summary": summary, "courses": courses}


@api.get("/analytics/course/{program_id}/summary")
async def course_summary(program_id: str, user: dict = Depends(get_current_user)):
    prog = await db.training_programs.find_one({"_id": oid(program_id)})
    if not prog:
        raise HTTPException(status_code=404, detail="Program not found")
    if user["role"] == "provider" and str(prog["provider_id"]) != user.get("provider_id"):
        raise HTTPException(status_code=403, detail="Not your program")
    tids = await trainee_ids_for_programs([oid(program_id)])
    summary = await compute_summary(tids)
    reasons = await db.non_placement_reasons.aggregate([
        {"$match": {"trainee_id": {"$in": tids}}},
        {"$group": {"_id": "$reason_category", "count": {"$sum": 1}}},
    ]).to_list(20)
    return {"program": ser(prog), "summary": summary,
            "non_placement_reasons": {r["_id"]: r["count"] for r in reasons}}


@api.get("/analytics/district/{district}/summary")
async def district_summary(district: str, user: dict = Depends(require_role("district_admin", "state_admin", "super_admin"))):
    if user["role"] == "district_admin" and user.get("district") != district:
        raise HTTPException(status_code=403, detail="Outside your district")
    docs = await db.trainees.find({"district": district}, {"_id": 1}).to_list(100000)
    tids = [d["_id"] for d in docs]
    summary = await compute_summary(tids)
    providers = await db.training_providers.find({"district": district}).to_list(100)
    prov_rows = []
    for p in providers:
        pids = await program_ids_for_provider(p["_id"])
        ptids = await trainee_ids_for_programs(pids)
        cs = await compute_summary(ptids)
        prov_rows.append({"provider_id": str(p["_id"]), "name": p["name"],
                          "placement_rate": cs["placement_rate"], "total_trainees": cs["total_trainees"]})
    return {"district": district, "summary": summary, "providers": prov_rows}


@api.get("/analytics/demographic-breakdown")
async def demographic_breakdown(user: dict = Depends(get_current_user), filter: str = "gender"):
    if filter not in {"gender", "age_group"}:
        raise HTTPException(status_code=400, detail="filter must be gender or age_group")
    allowed = await accessible_trainee_ids(user)
    match = {} if allowed is None else {"_id": {"$in": allowed}}
    trainees = await db.trainees.find(match, {"gender": 1, "dob": 1}).to_list(100000)

    groups = {}
    now = datetime.now(timezone.utc)
    for t in trainees:
        if filter == "gender":
            key = t.get("gender") or "Unknown"
        else:
            key = "Unknown"
            if t.get("dob"):
                try:
                    age = (now.date() - datetime.fromisoformat(t["dob"]).date()).days // 365
                    key = "18-24" if age < 25 else ("25-34" if age < 35 else "35+")
                except ValueError:
                    pass
        groups.setdefault(key, []).append(t["_id"])

    result = []
    for key, ids in groups.items():
        cs = await compute_summary(ids)
        result.append({"group": key, "total_trainees": len(ids),
                       "placement_rate": cs["placement_rate"],
                       "employment_breakdown": cs["employment_breakdown"]})
    return {"filter": filter, "breakdown": result}


@api.get("/analytics/non-placement-reasons")
async def non_placement_analytics(user: dict = Depends(get_current_user), group_by: str = "course"):
    if group_by not in {"course", "district"}:
        raise HTTPException(status_code=400, detail="group_by must be course or district")
    allowed = await accessible_trainee_ids(user)
    match = {} if allowed is None else {"trainee_id": {"$in": allowed}}
    reasons = await db.non_placement_reasons.find(match).to_list(100000)

    grouped = {}
    if group_by == "district":
        for r in reasons:
            t = await db.trainees.find_one({"_id": r["trainee_id"]}, {"district": 1})
            key = t["district"] if t else "Unknown"
            grouped.setdefault(key, {}).setdefault(r["reason_category"], 0)
            grouped[key][r["reason_category"]] += 1
    else:
        for r in reasons:
            enr = await db.enrollments.find_one({"trainee_id": r["trainee_id"]})
            key = "Unknown"
            if enr:
                prog = await db.training_programs.find_one({"_id": enr["program_id"]}, {"course_name": 1})
                key = prog["course_name"] if prog else "Unknown"
            grouped.setdefault(key, {}).setdefault(r["reason_category"], 0)
            grouped[key][r["reason_category"]] += 1
    return {"group_by": group_by, "data": grouped}


# ---------------------------------------------------------------------------
# Reference data (helpers for building requests / future frontend)
# ---------------------------------------------------------------------------
@api.get("/providers")
async def list_providers(user: dict = Depends(get_current_user)):
    q = {}
    if user["role"] == "district_admin":
        q = {"district": user.get("district")}
    return ser(await db.training_providers.find(q).to_list(100))


@api.get("/programs")
async def list_programs(user: dict = Depends(get_current_user), provider_id: Optional[str] = None):
    q = {}
    if provider_id:
        q["provider_id"] = oid(provider_id)
    elif user["role"] == "provider" and user.get("provider_id"):
        q["provider_id"] = ObjectId(user["provider_id"])
    return ser(await db.training_programs.find(q).to_list(200))


# ===========================================================================
# ML routes (standalone testing via Swagger; same-process import elsewhere)
# ===========================================================================
class MatchIdentityBody(BaseModel):
    name: str
    phone_last4: Optional[str] = None
    dob: Optional[str] = None
    district: Optional[str] = None


@api.post("/ml/match-identity")
async def ml_match_identity(body: MatchIdentityBody, user: dict = Depends(get_current_user)):
    records = await db.trainees.find({}, {"full_name": 1, "phone_masked": 1, "dob": 1, "district": 1}).to_list(100000)
    return identity_matching.match_identity(body.name, body.phone_last4, body.dob, body.district, records)


class ClassifyBody(BaseModel):
    raw_text: str


@api.post("/ml/classify-response")
async def ml_classify(body: ClassifyBody):
    return response_classifier.classify_response(body.raw_text)


class PredictRiskBody(BaseModel):
    attendance_percent: float
    assessment_score: float
    course_sector: str
    district: str
    gender: str
    age: int


@api.post("/ml/predict-risk")
async def ml_predict(body: PredictRiskBody):
    return placement_risk.predict_risk(**body.model_dump())


@api.get("/ml/health")
async def ml_health():
    ready = {"placement_risk": placement_risk.is_ready(),
             "response_classifier": response_classifier.is_ready()}
    out = {"status": "ok" if all(ready.values()) else "degraded", "models_ready": ready}
    if placement_risk.is_ready():
        out["placement_risk_metrics"] = placement_risk.get_metrics()
    return out


@api.get("/")
async def root():
    return {"service": "SkillTrace AI API", "status": "ok"}


# ---------------------------------------------------------------------------
app.include_router(api)
app.add_middleware(
    CORSMiddleware, allow_credentials=False,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"], allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def startup():
    await ensure_indexes(db)
    try:
        if not placement_risk.is_ready():
            placement_risk.train()
        if not response_classifier.is_ready():
            response_classifier.train()
    except Exception as exc:  # pragma: no cover
        logger.warning("ML model warm-up skipped: %s", exc)
    logger.info("SkillTrace AI API started; indexes ensured; ML models ready.")


@app.on_event("shutdown")
async def shutdown():
    client.close()
