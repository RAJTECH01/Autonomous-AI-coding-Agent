from fastapi import APIRouter
from app.api.v1.endpoints import health, auth, projects, sessions, git, metrics_endpoints

api_router = APIRouter()

api_router.include_router(health.router, tags=["Health & Readiness"])
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(projects.router, prefix="/projects", tags=["Projects"])
api_router.include_router(sessions.router, tags=["Agent Sessions"])
api_router.include_router(git.router, tags=["Git & VCS"])
api_router.include_router(metrics_endpoints.router, tags=["Observability & Metrics"])
