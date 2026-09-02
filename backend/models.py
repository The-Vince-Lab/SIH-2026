"""Pydantic models for SkillTrace AI. Uses PyObjectId + BaseDocument pattern.

Read from Mongo  -> Model.from_mongo(doc)
Write to Mongo   -> instance.to_mongo()
References between collections are stored as ObjectId, exposed as str.
"""
from __future__ import annotations

from datetime import datetime, date
from typing import Annotated, Any, List, Optional

from bson import ObjectId
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field


def _validate_object_id(v: Any) -> str:
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, str):
        return v
    raise ValueError("Invalid ObjectId")


PyObjectId = Annotated[str, BeforeValidator(_validate_object_id)]


class BaseDocument(BaseModel):
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

    id: Optional[PyObjectId] = Field(default=None, alias="_id")

    @classmethod
    def from_mongo(cls, doc: dict):
        if doc is None:
            return None
        return cls.model_validate(doc)

    def to_mongo(self, exclude_none: bool = True) -> dict:
        data = self.model_dump(by_alias=True, exclude_none=exclude_none)
        if data.get("_id") is None:
            data.pop("_id", None)
        else:
            data["_id"] = ObjectId(data["_id"])
        # Convert reference string ids back to ObjectId
        for key, value in list(data.items()):
            if key.endswith("_id") and key != "_id" and isinstance(value, str) and ObjectId.is_valid(value):
                data[key] = ObjectId(value)
        return data


# ---------------------------------------------------------------------------
# Sub-documents
# ---------------------------------------------------------------------------
class Consent(BaseModel):
    given: bool = False
    timestamp: Optional[datetime] = None
    scope: List[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------
class Trainee(BaseDocument):
    full_name: str
    phone_number: str  # encrypted at rest
    phone_masked: Optional[str] = None
    dob: Optional[str] = None
    gender: Optional[str] = None
    district: str
    state: str
    consent: Consent = Field(default_factory=Consent)
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())


class TrainingProvider(BaseDocument):
    name: str
    district: str
    state: str
    accreditation_id: str


class TrainingProgram(BaseDocument):
    provider_id: PyObjectId
    course_name: str
    sector: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    duration_weeks: int


class Enrollment(BaseDocument):
    trainee_id: PyObjectId
    program_id: PyObjectId
    attendance_percent: float
    assessment_score: float
    certified: bool = False
    certification_date: Optional[str] = None


class Followup(BaseDocument):
    trainee_id: PyObjectId
    enrollment_id: PyObjectId
    interval_label: str  # "1_month"|"3_month"|"6_month"|"12_month"
    scheduled_date: Optional[str] = None
    status: str  # pending|sent|responded|unreachable|escalated_to_field_agent
    channel_used: Optional[str] = None
    raw_response_text: Optional[str] = None
    structured_response: Optional[dict] = None
    confidence_score: str  # verified|self_reported|unreachable
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())


class EmploymentRecord(BaseDocument):
    trainee_id: PyObjectId
    type: str  # employed|self_employed|apprentice|unemployed
    employer_name: Optional[str] = None
    employer_contact: Optional[str] = None
    sector: Optional[str] = None
    wage_bracket: Optional[str] = None
    employer_verified: bool = False
    verification_timestamp: Optional[datetime] = None
    reported_at: datetime = Field(default_factory=lambda: datetime.utcnow())


class NonPlacementReason(BaseDocument):
    trainee_id: PyObjectId
    reason_category: str
    notes: Optional[str] = None
    reported_at: datetime = Field(default_factory=lambda: datetime.utcnow())


class User(BaseDocument):
    name: str
    email: str
    password_hash: str
    role: str  # provider|district_admin|state_admin|super_admin
    provider_id: Optional[PyObjectId] = None
    district: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.utcnow())


class ConsentLog(BaseDocument):
    trainee_id: PyObjectId
    action: str  # granted|scope_updated|revoked
    timestamp: datetime = Field(default_factory=lambda: datetime.utcnow())
    performed_by: str
