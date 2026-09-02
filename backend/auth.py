"""JWT utilities for SkillTrace AI (HS256, Bearer-token based)."""
import os
from datetime import datetime, timezone, timedelta

import jwt

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_MINUTES = 60 * 12  # 12h for demo convenience


def _secret() -> str:
    return os.environ["JWT_SECRET"]


def create_access_token(user: dict) -> str:
    payload = {
        "sub": str(user["_id"]),
        "email": user["email"],
        "role": user["role"],
        "provider_id": str(user["provider_id"]) if user.get("provider_id") else None,
        "district": user.get("district"),
        "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_MINUTES),
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    return jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
