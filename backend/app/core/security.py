import uuid
import secrets
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Optional, Any, Union, Dict
from jose import jwt, JWTError
from passlib.context import CryptContext
from app.core.config import settings

# Production-grade password hashing with Argon2id primary and bcrypt/pbkdf2 fallback
pwd_context = CryptContext(schemes=["argon2", "bcrypt", "pbkdf2_sha256"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def generate_opaque_token() -> str:
    """Generates a cryptographically secure random opaque token."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Computes a SHA-256 hash for secure token lookup/storage."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_access_token(
    subject: Union[str, Any],
    role: Optional[str] = None,
    expires_delta: Optional[timedelta] = None,
    claims: Optional[Dict[str, Any]] = None
) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "jti": str(uuid.uuid4()),
        "type": "access"
    }
    if role:
        to_encode["role"] = role
    if claims:
        to_encode.update(claims)

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def create_refresh_token(subject: Union[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "jti": str(uuid.uuid4()),
        "type": "refresh"
    }
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Optional[dict]:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        return None

