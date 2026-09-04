import uuid
from typing import Generic, TypeVar, Type, Optional, List, Any
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.db.base import Base, SoftDeleteMixin
from app.schemas.common import PageParams

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    def __init__(self, model: Type[ModelType], session: AsyncSession):
        self.model = model
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> Optional[ModelType]:
        stmt = select(self.model).where(self.model.id == id)
        if issubclass(self.model, SoftDeleteMixin):
            stmt = stmt.where(self.model.deleted_at.is_(None))
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_paginated(
        self,
        params: PageParams,
        *filters: Any
    ) -> tuple[List[ModelType], int]:
        stmt = select(self.model)
        count_stmt = select(func.count()).select_from(self.model)

        if issubclass(self.model, SoftDeleteMixin):
            stmt = stmt.where(self.model.deleted_at.is_(None))
            count_stmt = count_stmt.where(self.model.deleted_at.is_(None))

        for f in filters:
            stmt = stmt.where(f)
            count_stmt = count_stmt.where(f)

        stmt = stmt.offset(params.offset).limit(params.page_size)

        total_res = await self.session.execute(count_stmt)
        total = total_res.scalar() or 0

        items_res = await self.session.execute(stmt)
        items = list(items_res.scalars().all())

        return items, total

    async def create(self, entity: ModelType) -> ModelType:
        self.session.add(entity)
        await self.session.flush()
        return entity

    async def update(self, entity: ModelType) -> ModelType:
        await self.session.flush()
        return entity

    async def soft_delete(self, id: uuid.UUID) -> bool:
        if issubclass(self.model, SoftDeleteMixin):
            stmt = (
                update(self.model)
                .where(self.model.id == id)
                .values(deleted_at=func.now())
            )
            res = await self.session.execute(stmt)
            return res.rowcount > 0
        return False
