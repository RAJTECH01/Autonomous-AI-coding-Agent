from enum import Enum
from typing import Optional
from app.domain.entities.user import UserRole
from app.core.exceptions import AuthorizationError


class ProjectRole(str, Enum):
    OWNER = "owner"
    PROJECT_OWNER = "project owner"
    MAINTAINER = "maintainer"
    MEMBER = "member"
    PROJECT_MEMBER = "project member"
    VIEWER = "viewer"


# Hierarchy for role evaluation
PROJECT_ROLE_HIERARCHY = {
    ProjectRole.OWNER: 40,
    ProjectRole.PROJECT_OWNER: 40,
    ProjectRole.MAINTAINER: 30,
    ProjectRole.MEMBER: 20,
    ProjectRole.PROJECT_MEMBER: 20,
    ProjectRole.VIEWER: 10,
}


class PermissionChecker:
    @staticmethod
    def require_system_admin(user_role: str):
        admin_roles = {UserRole.ADMINISTRATOR, UserRole.ADMIN, "administrator", "admin"}
        if user_role not in admin_roles:
            raise AuthorizationError("System administrator privilege required.")

    @staticmethod
    def check_project_access(
        user_id: str,
        user_role: str,
        project_owner_id: str,
        member_role: Optional[str],
        required_role: ProjectRole = ProjectRole.VIEWER
    ):
        # 1. System administrators bypass project-level restriction
        admin_roles = {UserRole.ADMINISTRATOR, UserRole.ADMIN, "administrator", "admin"}
        if user_role in admin_roles:
            return

        # 2. Project owner always has full permission
        if str(user_id) == str(project_owner_id):
            return

        # 3. Check member role requirement
        if not member_role:
            raise AuthorizationError("Access denied: You are not a member of this project.")

        try:
            user_proj_role = ProjectRole(member_role)
        except ValueError:
            user_proj_role = ProjectRole.VIEWER

        user_level = PROJECT_ROLE_HIERARCHY.get(user_proj_role, 0)
        required_level = PROJECT_ROLE_HIERARCHY.get(required_role, 100)

        if user_level < required_level:
            raise AuthorizationError(f"Access denied: Requires {required_role.value} privilege or higher.")

