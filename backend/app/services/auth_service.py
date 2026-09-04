import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.db.repositories.user_repository import (
    UserRepository,
    AuthSessionRepository,
    PasswordResetTokenRepository,
    EmailVerificationTokenRepository,
)
from app.infrastructure.db.models.user import (
    UserModel,
    AuthSessionModel,
    PasswordResetTokenModel,
    EmailVerificationTokenModel,
)
from app.infrastructure.db.models.metrics import AuditLogModel
from app.schemas.auth import (
    UserCreate,
    UserLogin,
    TokenResponse,
    UserResponse,
    AuthSessionResponse,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
    MessageResponse,
)
from app.core.security import (
    verify_password,
    get_password_hash,
    generate_opaque_token,
    hash_token,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.core.config import settings
from app.core.exceptions import AuthenticationError, ResourceNotFoundError, DomainError
from app.services.brute_force_service import brute_force_service
from app.services.notifications import SecurityMessage, get_notifier
from app.core.rate_limiter import rate_limiter
from app.core.logging import logger


DEFAULT_USER_ROLE = "user"


def is_expired(dt: datetime) -> bool:
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt <= now


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.user_repo = UserRepository(db)
        self.session_repo = AuthSessionRepository(db)
        self.reset_repo = PasswordResetTokenRepository(db)
        self.verification_repo = EmailVerificationTokenRepository(db)

    async def _write_audit_log(
        self,
        action: str,
        user_id: Optional[uuid.UUID],
        resource_type: str = "user",
        resource_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        audit = AuditLogModel(
            id=uuid.uuid4(),
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id or (str(user_id) if user_id else "unknown"),
            ip_address=ip_address,
            metadata_json=metadata or {},
        )
        self.db.add(audit)

    async def register_user(self, dto: UserCreate, ip_address: Optional[str] = None) -> UserResponse:
        rate_limiter.check_rate_limit(f"register:{ip_address or 'global'}")

        existing = await self.user_repo.get_by_email(dto.email)
        if existing:
            # Deliberately generic: a distinguishable answer here turns /register
            # into an account-enumeration oracle (finding AUTH-06).
            logger.info("Registration attempted for an address that already exists")
            raise DomainError("Registration could not be completed with the details provided.")

        # Self-service registration always creates an unprivileged account. Roles are
        # assigned only through an administrative path (finding AUTH-01).
        user = UserModel(
            id=uuid.uuid4(),
            email=dto.email.lower(),
            password_hash=get_password_hash(dto.password),
            full_name=dto.full_name,
            role=DEFAULT_USER_ROLE,
            is_active=True,
            is_verified=False,
        )

        await self.user_repo.create(user)
        await self._write_audit_log("USER_REGISTERED", user.id, ip_address=ip_address)
        await self.db.flush()

        logger.info("User registered successfully", user_id=str(user.id), email=user.email, role=user.role)
        return UserResponse.model_validate(user)

    async def login_user(
        self,
        dto: UserLogin,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> TokenResponse:
        rate_limiter.check_rate_limit(f"login:{ip_address or 'global'}")

        lockout_key = f"login:{dto.email.lower()}"

        user = await self.user_repo.get_by_email(dto.email)
        # Credentials are verified before the lockout is consulted, so a third party
        # spamming wrong passwords cannot deny service to the account owner
        # (finding AUTH-03). A wrong password past the threshold is still refused.
        if not user or not verify_password(dto.password, user.password_hash):
            brute_force_service.record_failed_attempt(lockout_key)
            await self._write_audit_log("USER_LOGIN_FAILED", user.id if user else None, ip_address=ip_address)
            await self.db.flush()
            brute_force_service.check_lockout(lockout_key)
            raise AuthenticationError("Invalid email or password.")

        if not user.is_active:
            raise AuthenticationError("User account is inactive.")

        brute_force_service.record_successful_login(lockout_key)

        access_token = create_access_token(user.id, role=user.role)
        refresh_token = create_refresh_token(user.id)

        expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        auth_session = AuthSessionModel(
            id=uuid.uuid4(),
            user_id=user.id,
            refresh_token_hash=hash_token(refresh_token),
            ip_address=ip_address,
            user_agent=user_agent,
            expires_at=expires_at,
        )
        self.db.add(auth_session)
        await self._write_audit_log("USER_LOGIN_SUCCESS", user.id, ip_address=ip_address)
        await self.db.flush()

        logger.info("User logged in successfully", user_id=str(user.id))
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            user=UserResponse.model_validate(user),
        )

    async def rotate_refresh_token(self, refresh_token: str, ip_address: Optional[str] = None) -> TokenResponse:
        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise AuthenticationError("Invalid or expired refresh token.")

        user_id_str = payload.get("sub")
        try:
            user_id = uuid.UUID(user_id_str)
        except (ValueError, TypeError):
            raise AuthenticationError("Invalid token subject.")

        user = await self.user_repo.get_by_id(user_id)
        if not user or not user.is_active:
            raise AuthenticationError("User account not found or inactive.")

        token_h = hash_token(refresh_token)
        session = await self.session_repo.get_any_by_token_hash(token_h)

        if not session:
            raise AuthenticationError("Invalid or revoked refresh token.")

        if session.revoked_at is not None:
            # Token Reuse Attack Detected! Revoke ALL active sessions for this user family
            logger.warning(
                "Refresh token reuse detected! Revoking all active sessions for security.",
                user_id=str(user_id)
            )
            await self.revoke_all_sessions(user_id, ip_address=ip_address)
            await self._write_audit_log(
                "TOKEN_REUSE_ATTACK_DETECTED",
                user_id,
                ip_address=ip_address,
                metadata={"action": "all_sessions_revoked"}
            )
            await self.db.commit()
            raise AuthenticationError("Refresh token has been revoked or already used. All active sessions invalidated.")

        if is_expired(session.expires_at):
            session.revoked_at = datetime.now(timezone.utc)
            await self.db.flush()
            raise AuthenticationError("Refresh token has expired.")

        # Revoke current matching old session
        session.revoked_at = datetime.now(timezone.utc)
        await self.db.flush()

        # Issue new token pair
        new_access_token = create_access_token(user.id, role=user.role)
        new_refresh_token = create_refresh_token(user.id)
        new_expires_at = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

        new_auth_session = AuthSessionModel(
            id=uuid.uuid4(),
            user_id=user.id,
            refresh_token_hash=hash_token(new_refresh_token),
            ip_address=ip_address,
            expires_at=new_expires_at,
        )
        self.db.add(new_auth_session)
        await self._write_audit_log("TOKEN_ROTATED", user.id, ip_address=ip_address)
        await self.db.flush()

        logger.info("Refresh token rotated successfully", user_id=str(user.id))
        return TokenResponse(
            access_token=new_access_token,
            refresh_token=new_refresh_token,
            user=UserResponse.model_validate(user),
        )

    async def logout_user(self, refresh_token: str, ip_address: Optional[str] = None):
        payload = decode_token(refresh_token)
        if payload and payload.get("sub"):
            try:
                user_id = uuid.UUID(payload["sub"])
                token_h = hash_token(refresh_token)
                session = await self.session_repo.get_by_token_hash(token_h)
                if session:
                    session.revoked_at = datetime.now(timezone.utc)

                await self._write_audit_log("USER_LOGOUT", user_id, ip_address=ip_address)
                await self.db.flush()
            except Exception as e:
                logger.warning("Logout session revocation error", error=str(e))

    # --- Session Management ---

    async def list_user_sessions(self, user_id: uuid.UUID) -> List[AuthSessionResponse]:
        sessions = await self.session_repo.list_active_user_sessions(user_id)
        return [AuthSessionResponse.model_validate(s) for s in sessions]

    async def revoke_session(self, user_id: uuid.UUID, session_id: uuid.UUID, ip_address: Optional[str] = None):
        session = await self.session_repo.get_by_id(session_id)
        if not session or session.user_id != user_id or session.revoked_at is not None:
            raise ResourceNotFoundError("Session not found or already revoked.")

        session.revoked_at = datetime.now(timezone.utc)
        await self._write_audit_log("SESSION_REVOKED", user_id, resource_id=str(session_id), ip_address=ip_address)
        await self.db.flush()

    async def revoke_all_sessions(
        self,
        user_id: uuid.UUID,
        except_session_id: Optional[uuid.UUID] = None,
        ip_address: Optional[str] = None
    ):
        stmt = (
            update(AuthSessionModel)
            .where(AuthSessionModel.user_id == user_id)
            .where(AuthSessionModel.revoked_at.is_(None))
        )
        if except_session_id:
            stmt = stmt.where(AuthSessionModel.id != except_session_id)

        stmt = stmt.values(revoked_at=datetime.now(timezone.utc))
        await self.db.execute(stmt)
        await self._write_audit_log("ALL_SESSIONS_REVOKED", user_id, ip_address=ip_address)
        await self.db.flush()

    # --- Password Reset Architecture ---

    async def request_password_reset(self, dto: ForgotPasswordRequest, ip_address: Optional[str] = None) -> MessageResponse:
        rate_limiter.check_rate_limit(f"password_reset:{ip_address or 'global'}")

        user = await self.user_repo.get_by_email(dto.email)

        if user and user.is_active:
            opaque_token = generate_opaque_token()
            hashed = hash_token(opaque_token)
            expires_at = datetime.now(timezone.utc) + timedelta(minutes=15)

            reset_record = PasswordResetTokenModel(
                id=uuid.uuid4(),
                user_id=user.id,
                token_hash=hashed,
                expires_at=expires_at,
            )
            self.db.add(reset_record)
            await self._write_audit_log("PASSWORD_RESET_REQUESTED", user.id, ip_address=ip_address)
            await self.db.flush()

            # Delivered out of band only - never in this HTTP response (AUTH-02).
            get_notifier().deliver(
                SecurityMessage(kind="password_reset", email=user.email, token=opaque_token)
            )
            logger.info("Password reset token generated", user_id=str(user.id))

        return MessageResponse(
            message="If an account exists for that email, a password reset link has been dispatched."
        )

    async def confirm_password_reset(self, dto: ResetPasswordRequest, ip_address: Optional[str] = None) -> MessageResponse:
        hashed = hash_token(dto.reset_token)
        reset_record = await self.reset_repo.get_by_token_hash(hashed)

        if not reset_record or is_expired(reset_record.expires_at):
            raise AuthenticationError("Invalid or expired password reset token.")

        user = await self.user_repo.get_by_id(reset_record.user_id)
        if not user or not user.is_active:
            raise AuthenticationError("User account not found or inactive.")

        # Update password
        user.password_hash = get_password_hash(dto.new_password)
        reset_record.used_at = datetime.now(timezone.utc)

        # Invalidate all active sessions for security
        await self.revoke_all_sessions(user.id, ip_address=ip_address)

        await self._write_audit_log("PASSWORD_RESET_COMPLETED", user.id, ip_address=ip_address)
        await self.db.flush()

        logger.info("Password reset completed successfully", user_id=str(user.id))
        return MessageResponse(message="Password has been reset successfully. Please login with your new credentials.")

    # --- Email Verification Architecture ---

    async def request_email_verification(self, user_id: uuid.UUID, ip_address: Optional[str] = None) -> MessageResponse:
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise ResourceNotFoundError("User not found.")

        if user.is_verified:
            return MessageResponse(message="Email address is already verified.")

        opaque_token = generate_opaque_token()
        hashed = hash_token(opaque_token)
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

        verification_record = EmailVerificationTokenModel(
            id=uuid.uuid4(),
            user_id=user.id,
            token_hash=hashed,
            expires_at=expires_at,
        )
        self.db.add(verification_record)
        await self._write_audit_log("EMAIL_VERIFICATION_REQUESTED", user.id, ip_address=ip_address)
        await self.db.flush()

        # Delivered out of band only - never in this HTTP response (AUTH-02).
        get_notifier().deliver(
            SecurityMessage(kind="email_verification", email=user.email, token=opaque_token)
        )
        logger.info("Email verification token generated", user_id=str(user.id))
        return MessageResponse(message="Verification email sent.")

    async def confirm_email_verification(self, dto: VerifyEmailRequest, ip_address: Optional[str] = None) -> MessageResponse:
        hashed = hash_token(dto.verification_token)
        v_record = await self.verification_repo.get_by_token_hash(hashed)

        if not v_record or is_expired(v_record.expires_at):
            raise AuthenticationError("Invalid or expired email verification token.")

        user = await self.user_repo.get_by_id(v_record.user_id)
        if not user:
            raise AuthenticationError("User not found.")

        user.is_verified = True
        v_record.used_at = datetime.now(timezone.utc)

        await self._write_audit_log("EMAIL_VERIFIED", user.id, ip_address=ip_address)
        await self.db.flush()

        logger.info("Email verified successfully", user_id=str(user.id))
        return MessageResponse(message="Email address successfully verified.")
