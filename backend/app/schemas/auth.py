from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, ConfigDict


class UserCreate(BaseModel):
    """Self-service registration.

    There is deliberately no `role` field: accepting one let any anonymous caller
    register as an administrator (finding AUTH-01). Roles are assigned only through
    an administrative endpoint. Unknown fields are rejected rather than ignored so
    a client that still sends `role` fails loudly.
    """

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=8, description="Password must be at least 8 characters long")
    full_name: str = Field(min_length=2, max_length=255)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    is_verified: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserResponse


class RefreshTokenRequest(BaseModel):
    refresh_token: Optional[str] = None


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    reset_token: str
    new_password: str = Field(min_length=8, description="New password must be at least 8 characters long")


class VerifyEmailRequest(BaseModel):
    verification_token: str


class AuthSessionResponse(BaseModel):
    id: UUID
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime
    expires_at: datetime
    is_current: bool = False

    model_config = ConfigDict(from_attributes=True)


class MessageResponse(BaseModel):
    """Generic acknowledgement.

    Note the absence of a `token` field: password-reset and email-verification
    tokens are delivered out of band only (finding AUTH-02).
    """

    message: str
    detail: Optional[str] = None

