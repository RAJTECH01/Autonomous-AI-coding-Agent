import uuid
from typing import Optional, List
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.db.repositories.base import BaseRepository
from app.infrastructure.db.models.project import ProjectModel, ProjectMemberModel
from app.schemas.common import PageParams


class ProjectRepository(BaseRepository[ProjectModel]):
    def __init__(self, session: AsyncSession):
        super().__init__(ProjectModel, session)

    async def get_by_slug(self, slug: str) -> Optional[ProjectModel]:
        stmt = (
            select(ProjectModel)
            .where(ProjectModel.slug == slug)
            .where(ProjectModel.deleted_at.is_(None))
        )
        res = await self.session.execute(stmt)
        return res.scalar_one_or_none()

    async def list_user_projects(
        self,
        user_id: uuid.UUID,
        params: PageParams
    ) -> tuple[List[ProjectModel], int]:
        """Projects the caller owns or is a member of.

        The tenant predicate is applied to both the page query and the count. The
        previous implementation built this filter and then discarded it, calling
        list_paginated with only a deleted_at predicate, so every user received
        every project in the database (finding AUTHZ-02).
        """
        visible_to_caller = or_(
            ProjectModel.owner_id == user_id,
            ProjectModel.id.in_(
                select(ProjectMemberModel.project_id).where(ProjectMemberModel.user_id == user_id)
            ),
        )

        stmt = (
            select(ProjectModel)
            .where(visible_to_caller)
            .where(ProjectModel.deleted_at.is_(None))
            .order_by(ProjectModel.created_at.desc())
            .offset(params.offset)
            .limit(params.page_size)
        )
        count_stmt = (
            select(func.count())
            .select_from(ProjectModel)
            .where(visible_to_caller)
            .where(ProjectModel.deleted_at.is_(None))
        )

        total = (await self.session.execute(count_stmt)).scalar() or 0
        items = list((await self.session.execute(stmt)).scalars().all())
        return items, total
