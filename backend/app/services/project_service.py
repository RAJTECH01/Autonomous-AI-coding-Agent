import uuid
import re
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.db.repositories.project_repository import ProjectRepository
from app.infrastructure.db.models.project import ProjectModel, ProjectMemberModel
from app.infrastructure.db.models.user import UserModel
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse
from app.schemas.common import PageParams, PaginatedResponse
from app.core.permissions import PermissionChecker, ProjectRole
from app.core.exceptions import ResourceNotFoundError, AuthorizationError, DomainError


class ProjectService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.project_repo = ProjectRepository(db)

    def _generate_slug(self, name: str) -> str:
        slug = re.sub(r"[^\w\s-]", "", name.lower())
        return re.sub(r"[-\s]+", "-", slug).strip("-")

    async def _verify_access(
        self,
        project: ProjectModel,
        requesting_user_id: uuid.UUID,
        requesting_user_role: str = "user",
        required_role: ProjectRole = ProjectRole.VIEWER
    ):
        stmt = (
            select(ProjectMemberModel)
            .where(ProjectMemberModel.project_id == project.id)
            .where(ProjectMemberModel.user_id == requesting_user_id)
        )
        res = await self.db.execute(stmt)
        member = res.scalar_one_or_none()

        try:
            PermissionChecker.check_project_access(
                user_id=str(requesting_user_id),
                user_role=requesting_user_role,
                project_owner_id=str(project.owner_id),
                member_role=member.role if member else None,
                required_role=required_role
            )
        except AuthorizationError:
            # Answer exactly as if the project did not exist. A 403 here and a 404
            # for an unknown id let an attacker enumerate project ids (AUTHZ-09).
            raise ResourceNotFoundError(f"Project with ID '{project.id}' not found.")
        return member

    async def create_project(self, user_id: uuid.UUID, dto: ProjectCreate) -> ProjectResponse:
        slug = self._generate_slug(dto.name)
        existing = await self.project_repo.get_by_slug(slug)
        if existing:
            slug = f"{slug}-{uuid.uuid4().hex[:6]}"

        project = ProjectModel(
            id=uuid.uuid4(),
            owner_id=user_id,
            name=dto.name,
            slug=slug,
            description=dto.description,
            repository_url=dto.repository_url,
            default_branch=dto.default_branch,
            language_stack=dto.language_stack
        )

        owner_member = ProjectMemberModel(
            id=uuid.uuid4(),
            project_id=project.id,
            user_id=user_id,
            role=ProjectRole.OWNER.value
        )

        await self.project_repo.create(project)
        self.db.add(owner_member)
        await self.db.flush()

        return ProjectResponse.model_validate(project)

    async def get_project_by_id(
        self,
        project_id: uuid.UUID,
        requesting_user_id: uuid.UUID,
        requesting_user_role: str = "user",
        required_role: ProjectRole = ProjectRole.VIEWER
    ) -> ProjectResponse:
        project = await self.project_repo.get_by_id(project_id)
        if not project:
            raise ResourceNotFoundError(f"Project with ID '{project_id}' not found.")

        await self._verify_access(project, requesting_user_id, requesting_user_role, required_role)
        return ProjectResponse.model_validate(project)

    async def list_projects(self, user_id: uuid.UUID, params: PageParams) -> PaginatedResponse[ProjectResponse]:
        items, total = await self.project_repo.list_user_projects(user_id, params)
        responses = [ProjectResponse.model_validate(p) for p in items]
        return PaginatedResponse.create(responses, total, params)

    async def update_project(
        self,
        project_id: uuid.UUID,
        requesting_user_id: uuid.UUID,
        dto: ProjectUpdate,
        requesting_user_role: str = "user"
    ) -> ProjectResponse:
        project = await self.project_repo.get_by_id(project_id)
        if not project:
            raise ResourceNotFoundError(f"Project with ID '{project_id}' not found.")

        await self._verify_access(
            project,
            requesting_user_id,
            requesting_user_role,
            required_role=ProjectRole.MAINTAINER
        )

        if dto.name is not None:
            project.name = dto.name
        if dto.description is not None:
            project.description = dto.description
        if dto.repository_url is not None:
            project.repository_url = dto.repository_url
        if dto.default_branch is not None:
            project.default_branch = dto.default_branch
        if dto.language_stack is not None:
            project.language_stack = dto.language_stack

        await self.db.flush()
        # updated_at carries onupdate=func.now(), so SQLAlchemy expires it after the
        # UPDATE. Refresh inside the async context; serialising the expired attribute
        # later raised MissingGreenlet and returned 500 (finding API-01).
        await self.db.refresh(project)
        return ProjectResponse.model_validate(project)

    async def delete_project(
        self,
        project_id: uuid.UUID,
        requesting_user_id: uuid.UUID,
        requesting_user_role: str = "user"
    ):
        project = await self.project_repo.get_by_id(project_id)
        if not project:
            raise ResourceNotFoundError(f"Project with ID '{project_id}' not found.")

        await self._verify_access(
            project,
            requesting_user_id,
            requesting_user_role,
            required_role=ProjectRole.OWNER
        )

        # BaseRepository exposes soft_delete(id); there is no delete(). Calling the
        # latter raised AttributeError on every request (finding API-02).
        deleted = await self.project_repo.soft_delete(project.id)
        if not deleted:
            raise ResourceNotFoundError(f"Project with ID '{project_id}' not found.")
        await self.db.flush()

    async def add_project_member(
        self,
        project_id: uuid.UUID,
        requesting_user_id: uuid.UUID,
        target_user_id: uuid.UUID,
        role: str = "member",
        requesting_user_role: str = "user"
    ):
        project = await self.project_repo.get_by_id(project_id)
        if not project:
            raise ResourceNotFoundError(f"Project with ID '{project_id}' not found.")

        await self._verify_access(
            project,
            requesting_user_id,
            requesting_user_role,
            required_role=ProjectRole.OWNER
        )

        member = ProjectMemberModel(
            id=uuid.uuid4(),
            project_id=project_id,
            user_id=target_user_id,
            role=role
        )
        self.db.add(member)
        await self.db.flush()
