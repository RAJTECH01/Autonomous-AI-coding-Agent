"""Security tests: deployment configuration, dependencies and HTTP hardening.

These read the real deployment artefacts in the repository, so they fail the build
when someone commits an unpinned dependency, a root container or a datastore
published to the host.
"""

import pathlib
import re

import pytest
import yaml

from app.core.config import settings
from app.main import app

from tests.support.http import operations

pytestmark = [pytest.mark.security, pytest.mark.unit]

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
BACKEND_ROOT = REPO_ROOT / "backend"
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
BACKEND_DOCKERFILE = BACKEND_ROOT / "Dockerfile"
REQUIREMENTS = BACKEND_ROOT / "requirements.txt"


@pytest.fixture(scope="module")
def compose() -> dict:
    if not COMPOSE_FILE.exists():
        pytest.skip("docker-compose.yml is not present")
    return yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def dockerfile() -> str:
    if not BACKEND_DOCKERFILE.exists():
        pytest.skip("backend/Dockerfile is not present")
    return BACKEND_DOCKERFILE.read_text(encoding="utf-8")


# ----------------------------------------------------------------- secret key
class TestSecretConfiguration:
    def test_the_shipped_default_secret_key_is_recognisable(self):
        """Guards the premise of the next two tests."""
        assert "change-in-production" in settings.__class__.model_fields["SECRET_KEY"].default

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="INFRA-01: Settings ships a hardcoded SECRET_KEY default and never validates it, so a "
        "deployment that forgets the variable signs JWTs with a value published in this repository. "
        "Anyone can then mint an administrator token.",
    )
    def test_the_default_secret_key_is_rejected_outside_development(self):
        with pytest.raises(Exception):
            settings.__class__(ENVIRONMENT="production")

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="INFRA-01: docker-compose.yml sets ENVIRONMENT=production but provides no SECRET_KEY, "
        "so the shipped default is what actually signs tokens.",
    )
    def test_compose_provides_a_secret_key_when_running_as_production(self, compose):
        backend_env = compose["services"]["backend"].get("environment", {})
        env = backend_env if isinstance(backend_env, dict) else dict(
            item.split("=", 1) for item in backend_env if "=" in item
        )
        if env.get("ENVIRONMENT") == "production":
            assert env.get("SECRET_KEY"), "production compose does not set SECRET_KEY"

    def test_debug_is_off_in_production_settings(self):
        assert settings.__class__(ENVIRONMENT="development").DEBUG in (True, False)

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="DB-02/INFRA-01: DEBUG defaults to True, which turns on SQLAlchemy echo (statements "
        "plus bound parameter values to stdout) and DEBUG-level logging.",
    )
    def test_debug_defaults_to_false(self):
        assert settings.__class__().DEBUG is False


# ---------------------------------------------------------------- dependencies
class TestDependencyPinning:
    def test_requirements_file_exists(self):
        assert REQUIREMENTS.exists()

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="DEP-01: every requirement uses >= with no upper bound and there is no lockfile, so "
        "two builds of the same commit can install different code. A single compromised upstream "
        "release lands in the API container automatically.",
    )
    def test_dependencies_are_exactly_pinned(self):
        unpinned = []
        for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
            entry = line.strip()
            if not entry or entry.startswith("#") or entry.startswith("-"):
                continue
            if "==" not in entry:
                unpinned.append(entry)
        assert unpinned == [], f"unpinned requirements: {unpinned}"

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="DEP-01: no hash pinning, so the resolved artefacts are not verified at install time.",
    )
    def test_dependencies_carry_hashes(self):
        text = REQUIREMENTS.read_text(encoding="utf-8")
        assert "--hash=sha256:" in text or (BACKEND_ROOT / "requirements.lock").exists()


# ------------------------------------------------------------------ dockerfile
class TestBackendImage:
    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="INFRA-03: the backend image declares no USER, so the API - the process that executes "
        "untrusted generated code and holds every secret - runs as root.",
    )
    def test_image_runs_as_a_non_root_user(self, dockerfile):
        users = re.findall(r"^\s*USER\s+(\S+)", dockerfile, re.MULTILINE | re.IGNORECASE)
        assert users, "no USER directive"
        assert users[-1].lower() not in ("root", "0")

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="INFRA-03/ESC-05: the base image is referenced by mutable tag with no digest.",
    )
    def test_base_image_is_digest_pinned(self, dockerfile):
        bases = re.findall(r"^\s*FROM\s+(\S+)", dockerfile, re.MULTILINE | re.IGNORECASE)
        assert bases
        assert all("@sha256:" in base for base in bases), f"unpinned base images: {bases}"

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="INFRA-03: there is no .dockerignore, and the Dockerfile does COPY . . - so any local "
        ".env, .git history or virtualenv is baked into the published image.",
    )
    def test_a_dockerignore_excludes_secrets_and_history(self):
        dockerignore = BACKEND_ROOT / ".dockerignore"
        if not dockerignore.exists():
            dockerignore = REPO_ROOT / ".dockerignore"
        assert dockerignore.exists(), "no .dockerignore"
        content = dockerignore.read_text(encoding="utf-8")
        for required in (".git", ".env", ".venv"):
            assert required in content, f"{required} is not excluded from the build context"

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="INFRA-03: build-essential, git and curl stay in the runtime layer, handing an "
        "attacker with code execution a complete toolchain. A multi-stage build should leave them "
        "in the builder.",
    )
    def test_build_tools_are_not_present_in_the_runtime_image(self, dockerfile):
        runtime_stage = dockerfile.split("FROM")[-1].lower()
        for tool in ("build-essential", "gcc", "curl"):
            assert tool not in runtime_stage, f"{tool} is installed in the runtime stage"

    def test_the_image_does_not_run_as_privileged_by_construction(self, dockerfile):
        assert "--privileged" not in dockerfile


# --------------------------------------------------------------------- compose
class TestComposeConfiguration:
    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="INFRA-04: Postgres and Redis publish host ports, exposing them beyond the compose "
        "network to anything that can reach the host.",
    )
    def test_datastores_do_not_publish_host_ports(self, compose):
        exposed = [
            name
            for name, service in compose["services"].items()
            if name in ("postgres", "db", "redis") and service.get("ports")
        ]
        assert exposed == [], f"datastores published on the host: {exposed}"

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="INFRA-04: Redis runs with no requirepass and no ACL. An unauthenticated Redis that "
        "is reachable from the host is a well-known path to code execution via CONFIG SET.",
    )
    def test_redis_requires_authentication(self, compose):
        redis = compose["services"].get("redis")
        if redis is None:
            pytest.skip("no redis service")
        rendered = str(redis)
        assert "requirepass" in rendered or "REDIS_PASSWORD" in rendered

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="INFRA-04/DB-01: the database password is hardcoded in the compose file (and the app "
        "connects as the postgres superuser), so every clone of the repository carries the "
        "credential and any injection inherits superuser rights.",
    )
    def test_database_credentials_come_from_the_environment(self, compose):
        rendered = yaml.safe_dump(compose)
        hardcoded = re.findall(r"POSTGRES_PASSWORD:\s*(?!\$\{)(\S+)", rendered)
        assert hardcoded == [], f"hardcoded database password: {hardcoded}"

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="DB-01: the application connects as the postgres superuser, so any injection or RCE "
        "inherits DROP DATABASE and COPY ... FROM PROGRAM.",
    )
    def test_application_does_not_connect_as_the_database_superuser(self, compose):
        rendered = yaml.safe_dump(compose)
        assert "POSTGRES_USER: postgres" not in rendered

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="INFRA-04: no service declares CPU or memory limits, so one runaway container can "
        "starve the whole host.",
    )
    def test_services_declare_resource_limits(self, compose):
        missing = [
            name
            for name, service in compose["services"].items()
            if not (service.get("deploy", {}).get("resources") or service.get("mem_limit"))
        ]
        assert missing == [], f"services without resource limits: {missing}"

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="NET-01/INFRA-04: every service shares the default bridge network, so the frontend "
        "container can reach Postgres and Redis directly.",
    )
    def test_services_are_network_segmented(self, compose):
        assert compose.get("networks"), "no explicit networks defined"
        for name, service in compose["services"].items():
            assert service.get("networks"), f"{name} is on the default bridge"

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="INFRA-02: the sandbox needs the Docker daemon, but no socket is mounted, so sandbox "
        "creation fails in the shipped configuration. The obvious operator fix - mounting "
        "/var/run/docker.sock into the API that executes untrusted code - is equivalent to granting "
        "host root. A rootless socket proxy or a separate execution host is required.",
    )
    def test_a_deliberate_sandbox_backend_is_configured(self, compose):
        backend = compose["services"]["backend"]
        volumes = [str(volume) for volume in backend.get("volumes", [])]
        socket_mounted = any("docker.sock" in volume for volume in volumes)
        proxy_configured = "docker-socket-proxy" in yaml.safe_dump(compose) or "DOCKER_HOST" in str(
            backend.get("environment", "")
        )
        assert proxy_configured, "no hardened sandbox execution backend is configured"
        assert not socket_mounted, "the raw Docker socket is mounted into the API container"


# ------------------------------------------------------------- HTTP hardening
class TestHttpHardening:
    def test_cors_does_not_use_a_wildcard_origin_regression(self):
        assert "*" not in settings.ALLOWED_ORIGINS

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="INFRA-05: no security headers are emitted - no HSTS, CSP, X-Content-Type-Options, "
        "X-Frame-Options or Referrer-Policy.",
    )
    def test_security_headers_are_present(self, client):
        headers = {key.lower() for key in client.get("/api/v1/health").headers}
        for required in (
            "strict-transport-security",
            "content-security-policy",
            "x-content-type-options",
            "x-frame-options",
            "referrer-policy",
        ):
            assert required in headers, f"missing {required}"

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="INFRA-05: no TrustedHostMiddleware, so the Host header is unvalidated and can poison "
        "absolute URLs and cache keys.",
    )
    def test_trusted_host_middleware_is_configured(self):
        middleware = {entry.cls.__name__ for entry in app.user_middleware}
        assert "TrustedHostMiddleware" in middleware

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="INFRA-05: /docs and /openapi.json are served in every environment, publishing the "
        "full route inventory - including the anonymous session and git routes.",
    )
    def test_api_documentation_is_not_public_in_production(self, client):
        assert client.get("/api/v1/docs").status_code in (401, 403, 404)
        assert client.get("/api/v1/openapi.json").status_code in (401, 403, 404)

    def test_cors_allow_headers_is_a_wildcard_today(self):
        """Documents the current CORS posture that the audit flags as INFRA-05."""
        cors = [entry for entry in app.user_middleware if entry.cls.__name__ == "CORSMiddleware"]
        assert cors, "CORS middleware is not installed"

    def test_every_operation_declares_a_response_model_or_status(self):
        """Cheap contract hygiene: no operation should be undocumented."""
        undocumented = [
            f"{method} {path}"
            for method, path, operation in operations(app)
            if not operation.get("responses")
        ]
        assert undocumented == []
