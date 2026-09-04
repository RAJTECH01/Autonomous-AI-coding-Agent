import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, status, Request, Response, HTTPException, Cookie, Body
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.db.session import get_db
from app.infrastructure.db.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.schemas.auth import (
    UserCreate,
    UserLogin,
    TokenResponse,
    UserResponse,
    RefreshTokenRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
    AuthSessionResponse,
    MessageResponse,
)
from app.core.config import DEVELOPMENT_ENVIRONMENTS, settings
from app.core.security import decode_token
from app.core.exceptions import AuthenticationError

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

REFRESH_COOKIE_NAME = "refresh_token"
REFRESH_COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    """Attach the refresh cookie with transport protections.

    `Secure` is on everywhere except local development, so the long-lived token is
    not strippable over plaintext HTTP (finding AUTH-04). `SameSite=strict` plus a
    narrow path keeps it off cross-site requests to other endpoints.
    """
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        samesite="strict",
        secure=settings.ENVIRONMENT not in DEVELOPMENT_ENVIRONMENTS,
        path=REFRESH_COOKIE_PATH,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
    )


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> UserResponse:
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        raise AuthenticationError("Invalid or expired access token.")

    user_id_str = payload.get("sub")
    try:
        user_id = uuid.UUID(user_id_str)
    except (ValueError, TypeError):
        raise AuthenticationError("Malformed user token subject.")

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    if not user or not user.is_active:
        raise AuthenticationError("User not found or inactive.")

    return UserResponse.model_validate(user)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(dto: UserCreate, request: Request, db: AsyncSession = Depends(get_db)):
    auth_service = AuthService(db)
    ip_address = request.client.host if request.client else None
    return await auth_service.register_user(dto, ip_address=ip_address)


@router.post("/login", response_model=TokenResponse)
async def login(dto: UserLogin, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    auth_service = AuthService(db)
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("User-Agent")

    result = await auth_service.login_user(dto, ip_address=ip_address, user_agent=user_agent)
    _set_refresh_cookie(response, result.refresh_token)
    return result


@router.post("/refresh", response_model=TokenResponse)
async def refresh_tokens(
    dto: RefreshTokenRequest,
    request: Request,
    response: Response,
    cookie_token: Optional[str] = Cookie(default=None, alias="refresh_token"),
    db: AsyncSession = Depends(get_db)
):
    token_val = dto.refresh_token or cookie_token
    if not token_val:
        raise AuthenticationError("Refresh token missing.")

    auth_service = AuthService(db)
    ip_address = request.client.host if request.client else None
    result = await auth_service.rotate_refresh_token(token_val, ip_address=ip_address)
    _set_refresh_cookie(response, result.refresh_token)
    return result


@router.post("/logout")
async def logout(
    dto: RefreshTokenRequest,
    request: Request,
    response: Response,
    cookie_token: Optional[str] = Cookie(default=None, alias="refresh_token"),
    db: AsyncSession = Depends(get_db)
):
    token_val = dto.refresh_token or cookie_token
    if token_val:
        auth_service = AuthService(db)
        ip_address = request.client.host if request.client else None
        await auth_service.logout_user(token_val, ip_address=ip_address)

    response.delete_cookie(REFRESH_COOKIE_NAME, path=REFRESH_COOKIE_PATH)
    return {"message": "Logged out successfully"}


@router.get("/me", response_model=UserResponse)
async def get_active_user(current_user: UserResponse = Depends(get_current_user)):
    return current_user


# --- Password Reset Endpoints ---

@router.post("/password-reset/request", response_model=MessageResponse)
async def request_password_reset(dto: ForgotPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)):
    auth_service = AuthService(db)
    ip_address = request.client.host if request.client else None
    return await auth_service.request_password_reset(dto, ip_address=ip_address)


@router.post("/password-reset/confirm", response_model=MessageResponse)
async def confirm_password_reset(dto: ResetPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)):
    auth_service = AuthService(db)
    ip_address = request.client.host if request.client else None
    return await auth_service.confirm_password_reset(dto, ip_address=ip_address)


# --- Email Verification Endpoints ---

@router.post("/verify-email/request", response_model=MessageResponse)
async def request_email_verification(
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    auth_service = AuthService(db)
    ip_address = request.client.host if request.client else None
    return await auth_service.request_email_verification(current_user.id, ip_address=ip_address)


@router.post("/verify-email/confirm", response_model=MessageResponse)
async def confirm_email_verification(dto: VerifyEmailRequest, request: Request, db: AsyncSession = Depends(get_db)):
    auth_service = AuthService(db)
    ip_address = request.client.host if request.client else None
    return await auth_service.confirm_email_verification(dto, ip_address=ip_address)


# --- Session Management Endpoints ---

@router.get("/sessions", response_model=List[AuthSessionResponse])
async def list_sessions(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    auth_service = AuthService(db)
    return await auth_service.list_user_sessions(current_user.id)


@router.delete("/sessions/{session_id}")
async def revoke_session(
    session_id: uuid.UUID,
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    auth_service = AuthService(db)
    ip_address = request.client.host if request.client else None
    await auth_service.revoke_session(current_user.id, session_id, ip_address=ip_address)
    return {"message": "Session revoked successfully"}


@router.delete("/sessions")
async def revoke_all_sessions(
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    auth_service = AuthService(db)
    ip_address = request.client.host if request.client else None
    await auth_service.revoke_all_sessions(current_user.id, ip_address=ip_address)
    return {"message": "All sessions revoked successfully"}
