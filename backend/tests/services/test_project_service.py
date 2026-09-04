import uuid
from app.services.project_service import ProjectService
from app.schemas.project import ProjectCreate


def test_project_service_slug_generation():
    service = ProjectService(db=None)
    assert service._generate_slug("My Autonomous Project!") == "my-autonomous-project"
    assert service._generate_slug("FastAPI Backend Agent v1.0") == "fastapi-backend-agent-v10"
