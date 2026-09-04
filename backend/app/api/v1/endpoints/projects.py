import uuid
from typing import List
from fastapi import APIRouter, Depends, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.infrastructure.db.session import get_db
from app.services.project_service import ProjectService
from app.schemas.project import ProjectCreate, ProjectUpdate, ProjectResponse
from app.schemas.auth import UserResponse
from app.schemas.common import PageParams, PaginatedResponse
from app.api.v1.endpoints.auth import get_current_user

router = APIRouter()


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    dto: ProjectCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    project_service = ProjectService(db)
    return await project_service.create_project(user_id=current_user.id, dto=dto)


@router.get("", response_model=PaginatedResponse[ProjectResponse])
async def list_projects(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    project_service = ProjectService(db)
    params = PageParams(page=page, page_size=page_size)
    return await project_service.list_projects(user_id=current_user.id, params=params)


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: uuid.UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    project_service = ProjectService(db)
    return await project_service.get_project_by_id(
        project_id=project_id,
        requesting_user_id=current_user.id,
        requesting_user_role=current_user.role
    )


@router.put("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: uuid.UUID,
    dto: ProjectUpdate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    project_service = ProjectService(db)
    return await project_service.update_project(
        project_id=project_id,
        requesting_user_id=current_user.id,
        dto=dto,
        requesting_user_role=current_user.role
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: uuid.UUID,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    project_service = ProjectService(db)
    await project_service.delete_project(
        project_id=project_id,
        requesting_user_id=current_user.id,
        requesting_user_role=current_user.role
    )
