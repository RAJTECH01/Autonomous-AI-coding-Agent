"""Authorization tests: tenant isolation, role gating and the approval gate.

Route-level assertions inspect the real dependency graph rather than calling the
endpoint, because hitting ``POST /sessions`` would spawn a container and start a
paid agent run. Everything else goes over real HTTP.
"""

import uuid

import pytest

from app.core.exceptions import ToolExecutionError
from app.domain.entities.tool import ToolPermission
from app.infrastructure.tools.controlled_tool_layer import ControlledToolLayer
from app.infrastructure.tools.registry import ToolRegistry
from app.main import app

from tests.support.factories import create_authenticated_user, create_project, make_run
from tests.support.http import route_requires_authentication, unauthenticated_routes

pytestmark = [pytest.mark.authz, pytest.mark.integration]


# ------------------------------------------------------- unauthenticated access
class TestAuthenticationIsRequired:
    @pytest.mark.parametrize(
        "method,path",
        [
            ("GET", "/api/v1/projects"),
            ("POST", "/api/v1/projects"),
            ("GET", "/api/v1/auth/me"),
            ("GET", "/api/v1/auth/sessions"),
        ],
    )
    def test_protected_endpoints_reject_anonymous_callers(self, client, method, path):
        response = client.request(method, path, json={} if method == "POST" else None)
        assert response.status_code in (401, 403)

    def test_project_routes_declare_the_identity_dependency(self):
        for method, path in [
            ("GET", "/api/v1/projects"),
            ("POST", "/api/v1/projects"),
            ("GET", "/api/v1/projects/{project_id}"),
            ("PUT", "/api/v1/projects/{project_id}"),
            ("DELETE", "/api/v1/projects/{project_id}"),
        ]:
            assert route_requires_authentication(app, path, method), f"{method} {path} is anonymous"

    @pytest.mark.security
    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="AUTHZ-01/AUTHZ-06/LEAK-03: sessions.py, git.py and metrics_endpoints.py register no "
        "authentication dependency at all. Anonymous callers can start agent runs, execute Git "
        "operations on the host, read any session transcript and approve high-risk plans.",
    )
    def test_no_agent_or_git_route_is_anonymous(self):
        offenders = unauthenticated_routes(
            app,
            prefixes=["/api/v1/sessions", "/api/v1/git", "/api/v1/metrics"],
        )
        assert offenders == [], f"anonymous routes: {offenders}"

    @pytest.mark.security
    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="AUTHZ-04: the approval routes are anonymous, so whoever submitted a high-risk plan "
        "can approve it themselves - the human-in-the-loop gate is decorative.",
    )
    def test_approval_routes_require_an_authenticated_approver(self):
        for path in [
            "/api/v1/sessions/{session_id}/approve",
            "/api/v1/sessions/{session_id}/reject",
            "/api/v1/sessions/{session_id}/cancel",
        ]:
            assert route_requires_authentication(app, path, "POST"), f"{path} is anonymous"


# ----------------------------------------------------------- tenant isolation
class TestTenantIsolation:
    def test_another_tenants_project_cannot_be_read(self, client):
        _alice, alice_headers = create_authenticated_user(client)
        project = create_project(client, alice_headers, name="alice-secret")

        _bob, bob_headers = create_authenticated_user(client)
        response = client.get(f"/api/v1/projects/{project['id']}", headers=bob_headers)
        assert response.status_code in (403, 404)

    def test_another_tenants_project_cannot_be_updated(self, client):
        _alice, alice_headers = create_authenticated_user(client)
        project = create_project(client, alice_headers, name="alice-owned")

        _bob, bob_headers = create_authenticated_user(client)
        response = client.put(
            f"/api/v1/projects/{project['id']}", json={"name": "hijacked"}, headers=bob_headers
        )
        assert response.status_code in (403, 404)

    def test_another_tenants_project_cannot_be_deleted(self, client):
        _alice, alice_headers = create_authenticated_user(client)
        project = create_project(client, alice_headers, name="alice-owned-2")

        _bob, bob_headers = create_authenticated_user(client)
        response = client.delete(f"/api/v1/projects/{project['id']}", headers=bob_headers)
        assert response.status_code in (403, 404)

    @pytest.mark.security
    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="AUTHZ-09: a project belonging to another tenant returns 403 while a non-existent id "
        "returns 404, so an authenticated attacker can enumerate which project ids exist. Both "
        "cases should return 404.",
    )
    def test_nonexistent_project_is_not_distinguishable_from_a_forbidden_one(self, client):
        _alice, alice_headers = create_authenticated_user(client)
        project = create_project(client, alice_headers, name="alice-owned-3")
        _bob, bob_headers = create_authenticated_user(client)

        forbidden = client.get(f"/api/v1/projects/{project['id']}", headers=bob_headers)
        missing = client.get(f"/api/v1/projects/{uuid.uuid4()}", headers=bob_headers)
        assert forbidden.status_code == missing.status_code

    def test_owner_retains_access_to_their_own_project(self, client):
        _alice, alice_headers = create_authenticated_user(client)
        project = create_project(client, alice_headers, name="alice-access")
        assert client.get(f"/api/v1/projects/{project['id']}", headers=alice_headers).status_code == 200

    @pytest.mark.security
    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="AUTHZ-02: ProjectRepository.list_user_projects discards its owner/member filter, so "
        "GET /api/v1/projects returns every project in the database to every authenticated user.",
    )
    def test_project_listing_is_scoped_to_the_caller(self, client):
        _alice, alice_headers = create_authenticated_user(client)
        create_project(client, alice_headers, name="alice-listing-secret")

        _bob, bob_headers = create_authenticated_user(client)
        body = client.get("/api/v1/projects", headers=bob_headers).json()

        names = [item["name"] for item in body["items"]]
        assert "alice-listing-secret" not in names
        assert body["total"] == 0


# ------------------------------------------------------------------ tool RBAC
class TestToolPermissionEnforcement:
    @pytest.mark.asyncio
    async def test_read_only_role_is_denied_execute_tools(self, sandbox, agent_run):
        sb, sandbox_id = sandbox
        layer = ControlledToolLayer()

        result = await layer.execute_tool(
            sandbox=sb,
            sandbox_id=sandbox_id,
            tool_name="execute_command",
            args={"command": "echo hello"},
            run=agent_run,
            user_role="user",  # ROLE_PERMISSIONS["user"] = READ + WRITE only
        )
        assert result.success is False
        assert "Permission denied" in (result.error or "")

    @pytest.mark.asyncio
    async def test_unknown_role_gets_read_only_by_default(self, sandbox, agent_run):
        sb, sandbox_id = sandbox
        layer = ControlledToolLayer()

        write = await layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="write_file",
            args={"file_path": "a.py", "content": "x"}, run=agent_run, user_role="intern",
        )
        assert write.success is False
        assert "Permission denied" in (write.error or "")

        read = await layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="list_files",
            args={"directory_path": "."}, run=make_run(), user_role="intern",
        )
        assert read.success is True

    @pytest.mark.asyncio
    async def test_privileged_role_may_execute(self, sandbox, agent_run):
        sb, sandbox_id = sandbox
        layer = ControlledToolLayer()
        result = await layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="execute_command",
            args={"command": "echo allowed"}, run=agent_run, user_role="project_owner",
        )
        assert result.success is True
        assert "allowed" in result.output

    def test_permission_validation_rejects_insufficient_roles_directly(self):
        layer = ControlledToolLayer()
        with pytest.raises(ToolExecutionError, match="Permission denied"):
            layer.validate_permission(ToolPermission.ADMIN, user_role="user")

    @pytest.mark.security
    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="AUTHZ-03: validate_permission returns early when user_role is falsy and no caller "
        "in the codebase ever passes user_role, so the whole RBAC matrix is unreachable and every "
        "agent run executes with implicit ADMIN authority.",
    )
    def test_missing_role_fails_closed(self):
        layer = ControlledToolLayer()
        with pytest.raises(ToolExecutionError):
            layer.validate_permission(ToolPermission.EXECUTE, user_role=None)

    @pytest.mark.security
    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="AUTHZ-05: push_git_branch exposes confirm_push in the model-facing JSON schema and "
        "passes it straight through as user_authorized, so the agent supplies its own human "
        "approval for remote pushes.",
    )
    def test_push_authorization_is_not_model_controllable(self):
        schema = ToolRegistry().get_tool("push_git_branch").to_openai_schema()
        properties = schema["function"]["parameters"]["properties"]
        assert "confirm_push" not in properties


# ------------------------------------------------------------- risk gating gap
class TestExecutionTimeRiskGating:
    @pytest.mark.security
    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="AUTHZ-07: ApprovalPolicyEngine.evaluate_tool_call is never invoked anywhere in the "
        "codebase. Only the plan text is screened, so a benign plan followed by a destructive tool "
        "call passes ungated.",
    )
    def test_tool_calls_are_screened_before_execution(self):
        import inspect

        from app.infrastructure.tools import controlled_tool_layer

        source = inspect.getsource(controlled_tool_layer)
        assert "evaluate_tool_call" in source, (
            "the tool layer does not consult the approval policy engine before dispatch"
        )
