"""Unit tests: pure decision logic, no I/O.

These are the cheap, fast layer. Anything that needs a filesystem, a database or
an event loop belongs in tests/integration or the category suites.
"""

import threading

import pytest

from app.core.approval.policy_engine import ApprovalPolicyEngine
from app.core.metrics import MetricsRegistry
from app.core.permissions import PermissionChecker, ProjectRole
from app.core.rate_limiter import RateLimiter, RateLimitExceededError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_opaque_token,
    get_password_hash,
    hash_token,
    verify_password,
)
from app.infrastructure.sandbox.policy import SandboxSecurityPolicy, SecurityPolicyError
from app.infrastructure.tools.path_validator import PathSecurityError, PathValidator
from app.infrastructure.vcs.local_git_provider import LocalGitProvider

pytestmark = pytest.mark.unit


# --------------------------------------------------------------- path policy
class TestPathValidator:
    @pytest.mark.parametrize(
        "path",
        [
            "src/app.py",
            "tests/test_app.py",
            "./README.md",
            "deep/nested/dir/module.py",
        ],
    )
    def test_accepts_ordinary_workspace_paths(self, path):
        assert PathValidator.validate_workspace_path(path)

    @pytest.mark.parametrize(
        "path",
        [
            "../../../etc/passwd",
            "src/../../secret",
            "..",
            "a/b/../../../c",
        ],
    )
    def test_rejects_parent_traversal(self, path):
        with pytest.raises(PathSecurityError, match="traversal"):
            PathValidator.validate_workspace_path(path)

    @pytest.mark.parametrize(
        "path",
        ["/etc/passwd", "/proc/self/environ", "/root/.bashrc", "C:\\Windows\\System32\\cmd.exe"],
    )
    def test_rejects_system_paths(self, path):
        with pytest.raises(PathSecurityError):
            PathValidator.validate_workspace_path(path)

    @pytest.mark.parametrize("path", [".env", "id_rsa", "credentials.json", "server.pem", "private.key"])
    def test_rejects_secret_files(self, path):
        with pytest.raises(PathSecurityError):
            PathValidator.validate_workspace_path(path)

    @pytest.mark.parametrize("path", ["", "   ", None])
    def test_rejects_empty_path(self, path):
        with pytest.raises(PathSecurityError):
            PathValidator.validate_workspace_path(path)  # type: ignore[arg-type]

    def test_strips_leading_slash_to_keep_paths_inside_workspace(self):
        assert PathValidator.validate_workspace_path("/src/app.py") == "src/app.py"


# ------------------------------------------------------------ sandbox policy
class TestSandboxPolicy:
    def test_output_under_limit_is_untouched(self):
        content, truncated = SandboxSecurityPolicy.truncate_output("hello", max_bytes=1024)
        assert content == "hello"
        assert truncated is False

    def test_output_over_limit_is_truncated_and_flagged(self):
        content, truncated = SandboxSecurityPolicy.truncate_output("x" * 5000, max_bytes=1000)
        assert truncated is True
        assert "TRUNCATED" in content
        assert len(content.encode()) < 5000

    def test_empty_output_is_not_flagged(self):
        assert SandboxSecurityPolicy.truncate_output("") == ("", False)

    def test_exact_limit_is_not_truncated(self):
        content, truncated = SandboxSecurityPolicy.truncate_output("y" * 100, max_bytes=100)
        assert truncated is False
        assert content == "y" * 100

    def test_provider_secrets_are_dropped_from_sandbox_environment(self):
        sanitized = SandboxSecurityPolicy.sanitize_environment(
            {
                "OPENAI_API_KEY": "sk-live-secret",
                "ANTHROPIC_API_KEY": "sk-ant-secret",
                "POSTGRES_PASSWORD": "hunter2",
                "AWS_SECRET_ACCESS_KEY": "aws-secret",
                "DATABASE_URL": "postgresql://u:p@host/db",
                "JWT_TOKEN": "eyJ...",
                "SAFE_SETTING": "keep-me",
            }
        )
        leaked = [k for k in sanitized if "KEY" in k.upper() or "PASSWORD" in k.upper() or "TOKEN" in k.upper()]
        assert leaked == []
        assert sanitized["SAFE_SETTING"] == "keep-me"

    def test_container_options_enforce_the_isolation_baseline(self):
        opts = SandboxSecurityPolicy.get_container_security_options()
        assert opts["network_mode"] == "none"
        assert opts["read_only"] is True
        assert opts["cap_drop"] == ["ALL"]
        assert opts["privileged"] is False
        assert "no-new-privileges:true" in opts["security_opt"]
        assert opts["pids_limit"] > 0
        assert opts["mem_limit"].endswith("m")
        assert "noexec" in opts["tmpfs"]["/tmp"]

    def test_workspace_containment_rejects_parent_traversal(self, tmp_path):
        with pytest.raises(SecurityPolicyError):
            SandboxSecurityPolicy.validate_workspace_relative_path(str(tmp_path), "../escape.txt")


# ------------------------------------------------------------ approval policy
class TestApprovalPolicyEngine:
    @pytest.mark.parametrize(
        "plan",
        [
            "Run rm -rf /workspace/build to clean the build directory",
            "Step 2: pip install requests to call the upstream API",
            "Fetch the fixture with curl https://example.test/data.json",
            "Use sudo chmod 777 on the deployment directory",
            "Rework the authentication flow and password hashing",
            "Apply an alembic migration adding a column",
        ],
    )
    def test_destructive_plans_are_flagged_high_risk(self, plan):
        result = ApprovalPolicyEngine().evaluate_plan(plan, target_files=[])
        assert result.is_high_risk is True
        assert result.explanations

    def test_production_config_target_files_are_flagged(self):
        result = ApprovalPolicyEngine().evaluate_plan(
            "Update deployment settings", target_files=["docker-compose.yml"]
        )
        assert result.is_high_risk is True

    def test_ordinary_plan_is_not_flagged(self):
        plan = "Step 1: add a pure helper function to calculator.py. Step 2: add unit tests."
        assert ApprovalPolicyEngine().evaluate_plan(plan, target_files=["calculator.py"]).is_high_risk is False

    @pytest.mark.parametrize(
        "plan",
        [
            "Step 1: run DROP TABLE users; to reset the schema",
            "Delete the production database and recreate it from scratch",
            "Publish the change with git push --force to main",
        ],
    )
    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="POLICY-01: evaluate_plan only matches DB_SCHEMA_KEYWORDS against target_files, "
        "never against plan text, and has no pattern for force-push or database destruction. "
        "Destructive plans expressed in prose pass the high-risk gate.",
    )
    def test_destructive_sql_and_force_push_plans_should_be_flagged(self, plan):
        assert ApprovalPolicyEngine().evaluate_plan(plan, target_files=[]).is_high_risk is True

    def test_tool_call_screening_detects_destructive_arguments(self):
        result = ApprovalPolicyEngine().evaluate_tool_call(
            "execute_command", {"command": "rm -rf /workspace"}
        )
        assert result.is_high_risk is True

    def test_tool_call_screening_detects_auth_file_writes(self):
        result = ApprovalPolicyEngine().evaluate_tool_call(
            "write_file", {"file_path": "app/core/security.py", "content": "..."}
        )
        assert result.is_high_risk is True

    def test_tool_call_screening_passes_ordinary_edits(self):
        result = ApprovalPolicyEngine().evaluate_tool_call(
            "write_file", {"file_path": "calculator.py", "content": "def add(a, b): return a + b"}
        )
        assert result.is_high_risk is False


# ------------------------------------------------------------------- security
class TestPasswordAndTokenPrimitives:
    def test_password_hash_is_salted_and_verifiable(self):
        first = get_password_hash("Str0ng-Passw0rd!42")
        second = get_password_hash("Str0ng-Passw0rd!42")
        assert first != second, "identical hashes mean the salt is missing"
        assert verify_password("Str0ng-Passw0rd!42", first)
        assert not verify_password("wrong", first)

    def test_password_hash_does_not_contain_the_plaintext(self):
        assert "Str0ng-Passw0rd!42" not in get_password_hash("Str0ng-Passw0rd!42")

    def test_access_token_round_trips_subject_and_role(self):
        token = create_access_token("user-123", role="administrator")
        payload = decode_token(token)
        assert payload["sub"] == "user-123"
        assert payload["role"] == "administrator"

    def test_token_types_are_distinguishable(self):
        access = decode_token(create_access_token("u1"))
        refresh = decode_token(create_refresh_token("u1"))
        assert access.get("type") != refresh.get("type")

    def test_tampered_token_is_rejected(self):
        token = create_access_token("user-123")
        head, payload, sig = token.split(".")
        assert decode_token(f"{head}.{payload}.{sig[::-1]}") is None

    def test_garbage_token_is_rejected(self):
        assert decode_token("not-a-jwt") is None

    def test_opaque_tokens_are_unique_and_hashed_deterministically(self):
        a, b = generate_opaque_token(), generate_opaque_token()
        assert a != b
        assert hash_token(a) == hash_token(a)
        assert hash_token(a) != hash_token(b)
        assert a not in hash_token(a)


# --------------------------------------------------------------- rate limiter
class TestRateLimiter:
    def test_allows_up_to_the_limit_then_rejects(self):
        limiter = RateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            limiter.check_rate_limit("client-a")
        with pytest.raises(RateLimitExceededError):
            limiter.check_rate_limit("client-a")

    def test_buckets_are_per_key(self):
        limiter = RateLimiter(max_requests=1, window_seconds=60)
        limiter.check_rate_limit("client-a")
        limiter.check_rate_limit("client-b")  # must not raise

    def test_expired_entries_stop_counting(self, monkeypatch):
        limiter = RateLimiter(max_requests=2, window_seconds=60)
        clock = [1_000.0]
        monkeypatch.setattr("app.core.rate_limiter.time.time", lambda: clock[0])
        limiter.check_rate_limit("k")
        limiter.check_rate_limit("k")
        clock[0] += 61
        limiter.check_rate_limit("k")  # window has rolled over


# ---------------------------------------------------------------- permissions
class TestPermissionChecker:
    def test_system_admin_required(self):
        PermissionChecker.require_system_admin("administrator")
        with pytest.raises(Exception):
            PermissionChecker.require_system_admin("user")

    def test_owner_has_access_to_own_project(self):
        assert PermissionChecker.check_project_access(
            user_id="u1", user_role="user", project_owner_id="u1", member_role=None
        ) in (True, None)

    def test_stranger_is_denied_project_access(self):
        with pytest.raises(Exception):
            PermissionChecker.check_project_access(
                user_id="u2", user_role="user", project_owner_id="u1", member_role=None
            )

    def test_project_role_hierarchy_orders_viewer_below_owner(self):
        assert ProjectRole.VIEWER.value != ProjectRole.OWNER.value


# ------------------------------------------------------------ protected refs
class TestProtectedBranches:
    @pytest.mark.parametrize("branch", ["main", "master", "production", "MAIN", " main "])
    def test_protected_names_are_detected_case_and_space_insensitively(self, branch):
        assert LocalGitProvider().is_protected_branch(branch) is True

    @pytest.mark.parametrize("branch", ["agent/task-1", "feature/x", "", None])
    def test_feature_branches_are_not_protected(self, branch):
        assert LocalGitProvider().is_protected_branch(branch) is False


# -------------------------------------------------------------------- metrics
class TestMetricsRegistry:
    def test_cost_estimation_matches_published_pricing(self):
        metrics = MetricsRegistry()
        cost = metrics.record_model_call(
            provider="anthropic",
            model_name="claude-3-5-sonnet-20241022",
            latency_seconds=1.0,
            prompt_tokens=100_000,
            completion_tokens=20_000,
        )
        assert round(cost, 2) == 0.60
        assert metrics.total_tokens == 120_000

    def test_averages_are_computed_over_completed_and_failed_runs(self):
        metrics = MetricsRegistry()
        metrics.record_task_completed(duration_seconds=10.0, iterations=3)
        metrics.record_task_failed(duration_seconds=20.0, iterations=5)
        assert metrics.average_execution_time == 15.0
        assert metrics.average_iterations == 4.0

    def test_dashboard_summary_does_not_deadlock(self):
        """Regression: the registry held a non-reentrant lock and then read its
        own locked properties, hanging /api/v1/metrics forever."""
        metrics = MetricsRegistry()
        metrics.record_task_started()
        metrics.record_tool_call("read_file", success=True)

        done = threading.Event()
        captured = {}

        def worker():
            captured["summary"] = metrics.get_dashboard_summary()
            captured["prometheus"] = metrics.get_prometheus_exposition()
            done.set()

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        assert done.wait(timeout=5), "get_dashboard_summary deadlocked"
        assert captured["summary"]["tasks"]["started"] == 1
        assert "tasks_started_total 1" in captured["prometheus"]
