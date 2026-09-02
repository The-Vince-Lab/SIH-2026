"""Security utilities: password hashing (bcrypt) and phone encryption (Fernet)."""
import os
import base64
import hashlib
import bcrypt
from cryptography.fernet import Fernet


def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))


def _fernet() -> Fernet:
    """Derive a valid Fernet key from the configured secret."""
    raw = os.environ["PHONE_ENCRYPTION_KEY"].encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(key)


def encrypt_phone(phone: str) -> str:
    return _fernet().encrypt(phone.encode("utf-8")).decode("utf-8")


def decrypt_phone(token: str) -> str:
    return _fernet().decrypt(token.encode("utf-8")).decode("utf-8")


def mask_phone(phone: str) -> str:
    """Return a display-safe masked phone, e.g. +91-XXXXXX8821."""
    digits = "".join(c for c in phone if c.isdigit())
    return f"XXXXXX{digits[-4:]}" if len(digits) >= 4 else "XXXX"
