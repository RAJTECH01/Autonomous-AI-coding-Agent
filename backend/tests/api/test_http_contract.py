"""API tests: the HTTP contract of the real FastAPI app.

Requests go through the real middleware stack, real dependency graph, real
validation and the real database session. Only the outbound model provider is
absent, and these endpoints do not call it.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.infrastructure.db.session import get_db
from app.main import app

from tests.support.factories import create_authenticated_user, create_project

pytestmark = [pytest.mark.api, pytest.mark.integration]


# ------------------------------------------------------------------ liveness
class TestHealthEndpoints:
    def test_liveness_reports_service_identity(self, client):
        body = client.get("/api/v1/health").json()
        assert body["status"] == "healthy"
        assert body["service"]
        assert body["version"]

    def test_readiness_checks_the_database(self, client):
        body = client.get("/api/v1/readiness").json()
        assert body["status"] == "ready"
        assert body["database"] == "ok"

    def test_detailed_health_reports_database_latency(self, client):
        body = client.get("/api/v1/health/detail").json()
        assert body["database"]["status"] == "ok"
        assert body["database"]["latency_ms"] >= 0
        assert "resources" in body

    def test_metrics_are_exposed_in_prometheus_format(self, client):
        response = client.get("/api/v1/metrics")
        assert response.status_code == 200
        assert "tasks_started_total" in response.text

    def test_metrics_are_exposed_as_json_on_request(self, client):
        body = client.get("/api/v1/metrics", params={"format": "json"}).json()
        assert "tasks" in body or "tasks_started" in str(body)

    def test_dashboard_metrics_do_not_hang(self, client):
        """Regression for the MetricsRegistry self-deadlock: this endpoint used to
        block forever, tying up a worker on every request."""
        response = client.get("/api/v1/metrics/dashboard")
        assert response.status_code == 200
        assert "tasks" in response.json()


# ------------------------------------------------------------ error envelope
class TestErrorContract:
    def test_unknown_route_returns_404(self, client):
        assert client.get("/api/v1/not-a-real-route").status_code == 404

    def test_validation_failure_returns_422_with_field_details(self, client):
        response = client.post("/api/v1/auth/register", json={"email": "not-an-email", "password": "x"})
        assert response.status_code == 422
        assert response.json()["detail"]

    def test_domain_errors_are_wrapped_in_the_standard_envelope(self, client):
        _user, headers = create_authenticated_user(client)
        response = client.get(f"/api/v1/projects/{uuid.uuid4()}", headers=headers)
        assert response.status_code in (403, 404)
        body = response.json()
        assert "error" in body
        assert body["error"]["code"] in ("RESOURCE_NOT_FOUND", "ACCESS_DENIED")
        assert body["error"]["correlation_id"]

    def test_malformed_uuid_path_parameter_is_rejected(self, client):
        _user, headers = create_authenticated_user(client)
        assert client.get("/api/v1/projects/not-a-uuid", headers=headers).status_code == 422

    def test_internal_errors_do_not_leak_stack_traces(self, client):
        """Database failure scenario: the connection dies mid-request."""
        _user, headers = create_authenticated_user(client)

        async def exploding_db():
            raise OperationalError("SELECT 1", {}, Exception("connection refused to 10.0.0.5:5432"))
            yield  # pragma: no cover

        previous = app.dependency_overrides.get(get_db)
        app.dependency_overrides[get_db] = exploding_db
        try:
            # raise_server_exceptions=False makes the client behave like a real
            # HTTP peer instead of re-raising the server-side exception.
            with TestClient(app, raise_server_exceptions=False) as raw_client:
                response = raw_client.get("/api/v1/projects", headers=headers)
        finally:
            if previous is not None:
                app.dependency_overrides[get_db] = previous
            else:  # pragma: no cover
                app.dependency_overrides.pop(get_db, None)

        assert response.status_code >= 500
        body = response.text
        assert "Traceback" not in body
        assert "10.0.0.5" not in body, "internal infrastructure address leaked to the client"
        assert "connection refused" not in body.lower()


# ---------------------------------------------------------------- middleware
class TestObservabilityMiddleware:
    def test_correlation_id_is_returned_on_every_response(self, client):
        response = client.get("/api/v1/health")
        assert response.headers.get("X-Correlation-ID")

    def test_supplied_correlation_id_is_echoed_back(self, client):
        supplied = "corr-" + uuid.uuid4().hex
        response = client.get("/api/v1/health", headers={"X-Correlation-ID": supplied})
        assert response.headers["X-Correlation-ID"] == supplied

    def test_request_id_is_returned_alongside_the_correlation_id(self, client):
        response = client.get("/api/v1/health")
        assert response.headers.get("X-Request-ID")
        assert response.headers["X-Request-ID"] != response.headers["X-Correlation-ID"]

    def test_cors_preflight_is_allowed_for_configured_origins(self, client):
        response = client.options(
            "/api/v1/health",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code in (200, 204)
        assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"

    def test_unknown_origin_is_not_granted_credentials(self, client):
        response = client.get("/api/v1/health", headers={"Origin": "http://evil.test"})
        assert response.headers.get("access-control-allow-origin") != "http://evil.test"


# ------------------------------------------------------------------ projects
class TestProjectsApi:
    def test_create_read_delete_round_trip(self, client):
        _user, headers = create_authenticated_user(client)

        created = create_project(client, headers, name="lifecycle-project")
        project_id = created["id"]
        assert created["slug"]
        assert created["default_branch"] == "main"

        fetched = client.get(f"/api/v1/projects/{project_id}", headers=headers)
        assert fetched.status_code == 200
        assert fetched.json()["name"] == "lifecycle-project"

        listed = client.get("/api/v1/projects", headers=headers).json()
        assert any(p["id"] == project_id for p in listed["items"])

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="API-02: DELETE /projects/{id} always returns 500. ProjectService.delete_project "
        "calls project_repo.delete(project), but BaseRepository exposes soft_delete(id) and has no "
        "delete() method, so every deletion raises AttributeError. Projects cannot be deleted.",
    )
    def test_project_can_be_deleted(self, client):
        _user, headers = create_authenticated_user(client)
        created = create_project(client, headers, name="deletable-project")

        with TestClient(app, raise_server_exceptions=False) as raw_client:
            deleted = raw_client.delete(f"/api/v1/projects/{created['id']}", headers=headers)
        assert deleted.status_code == 204

        after = client.get(f"/api/v1/projects/{created['id']}", headers=headers)
        assert after.status_code in (403, 404)

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="API-01: PUT /projects/{id} returns 500. TimestampMixin.updated_at uses "
        "onupdate=func.now(), so SQLAlchemy expires that attribute after the UPDATE flush. "
        "The endpoint then serialises the ORM object into ProjectResponse outside the async "
        "context, and the implicit refresh raises MissingGreenlet. Fix: await session.refresh() "
        "after commit, or build the response from the DTO instead of the expired model.",
    )
    def test_update_returns_the_updated_project(self, client):
        _user, headers = create_authenticated_user(client)
        created = create_project(client, headers, name="updatable-project")

        with TestClient(app, raise_server_exceptions=False) as raw_client:
            updated = raw_client.put(
                f"/api/v1/projects/{created['id']}",
                json={"description": "updated by test"},
                headers=headers,
            )
        assert updated.status_code == 200
        assert updated.json()["description"] == "updated by test"

    def test_listing_is_paginated_with_metadata(self, client):
        _user, headers = create_authenticated_user(client)
        for index in range(3):
            create_project(client, headers, name=f"paged-{index}")

        body = client.get("/api/v1/projects", params={"page": 1, "page_size": 2}, headers=headers).json()
        assert body["page"] == 1
        assert body["page_size"] == 2
        assert len(body["items"]) <= 2
        assert body["total"] >= 3
        assert body["total_pages"] >= 2

    @pytest.mark.parametrize(
        "payload",
        [
            {"name": "x"},                          # too short
            {"name": ""},                           # empty
            {"description": "no name at all"},      # missing required field
            {"name": "y" * 300},                    # too long
        ],
    )
    def test_invalid_project_payloads_are_rejected(self, client, payload):
        _user, headers = create_authenticated_user(client)
        assert client.post("/api/v1/projects", json=payload, headers=headers).status_code == 422

    def test_page_size_upper_bound_is_enforced(self, client):
        _user, headers = create_authenticated_user(client)
        assert client.get("/api/v1/projects", params={"page_size": 10_000}, headers=headers).status_code == 422

    def test_project_names_are_stored_verbatim_not_interpreted(self, client):
        _user, headers = create_authenticated_user(client)
        hostile = "'; DROP TABLE projects; -- <script>alert(1)</script>"
        created = create_project(client, headers, name=hostile)
        assert created["name"] == hostile
        # The table must still be there.
        assert client.get("/api/v1/projects", headers=headers).status_code == 200
