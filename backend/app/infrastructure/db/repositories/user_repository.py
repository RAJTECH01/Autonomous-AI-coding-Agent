import uuid
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.db.repositories.base import BaseRepository
from app.infrastructure.db.models.user import (
    UserModel,
    AuthSessionModel,
    PasswordResetTokenModel,
    EmailVerificationTokenModel,
)


class UserRepository(BaseRepository[UserModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(UserModel, session)

    async def get_by_email(self, email: str) -> Optional[UserModel]:
        stmt = (
            select(UserModel)
            .where(UserModel.email == email.lower())
            .where(UserModel.deleted_at.is_(None))
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()


class AuthSessionRepository(BaseRepository[AuthSessionModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(AuthSessionModel, session)

    async def get_by_token_hash(self, token_hash: str) -> Optional[AuthSessionModel]:
        stmt = (
            select(AuthSessionModel)
            .where(AuthSessionModel.refresh_token_hash == token_hash)
            .where(AuthSessionModel.revoked_at.is_(None))
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def get_any_by_token_hash(self, token_hash: str) -> Optional[AuthSessionModel]:
        stmt = (
            select(AuthSessionModel)
            .where(AuthSessionModel.refresh_token_hash == token_hash)
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_active_user_sessions(self, user_id: uuid.UUID):
        stmt = (
            select(AuthSessionModel)
            .where(AuthSessionModel.user_id == user_id)
            .where(AuthSessionModel.revoked_at.is_(None))
            .order_by(AuthSessionModel.created_at.desc())
        )
        res = await self.session.execute(stmt)
        return res.scalars().all()


class PasswordResetTokenRepository(BaseRepository[PasswordResetTokenModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(PasswordResetTokenModel, session)

    async def get_by_token_hash(self, token_hash: str) -> Optional[PasswordResetTokenModel]:
        stmt = (
            select(PasswordResetTokenModel)
            .where(PasswordResetTokenModel.token_hash == token_hash)
            .where(PasswordResetTokenModel.used_at.is_(None))
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()


class EmailVerificationTokenRepository(BaseRepository[EmailVerificationTokenModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(EmailVerificationTokenModel, session)

    async def get_by_token_hash(self, token_hash: str) -> Optional[EmailVerificationTokenModel]:
        stmt = (
            select(EmailVerificationTokenModel)
            .where(EmailVerificationTokenModel.token_hash == token_hash)
            .where(EmailVerificationTokenModel.used_at.is_(None))
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

