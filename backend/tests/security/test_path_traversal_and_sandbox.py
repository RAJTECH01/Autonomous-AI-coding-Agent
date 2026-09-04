"""Security tests: path traversal, sandbox escape and container hardening.

The symlink tests do real filesystem work: they create a real link inside a real
workspace and then ask the production containment policy whether the path is
inside the workspace. On Windows, creating symlinks needs privilege, so those
tests skip rather than pass vacuously.
"""

import inspect
import os
import stat

import pytest

from app.core.config import settings
from app.infrastructure.sandbox import docker_sandbox
from app.infrastructure.sandbox.policy import SandboxSecurityPolicy, SecurityPolicyError
from app.infrastructure.sandbox.runtimes import runtime_registry
from app.infrastructure.tools.path_validator import PathSecurityError, PathValidator

pytestmark = [pytest.mark.security, pytest.mark.sandbox]


def can_symlink(tmp_path) -> bool:
    try:
        target = tmp_path / "_symlink_probe_target"
        target.write_text("probe")
        link = tmp_path / "_symlink_probe_link"
        os.symlink(target, link)
        link.unlink()
        return True
    except (OSError, NotImplementedError):
        return False


# --------------------------------------------------------------- path validator
class TestPathValidatorCoverage:
    @pytest.mark.parametrize(
        "path",
        ["../../etc/passwd", "a/../../b", "..", "./../secret"],
    )
    def test_parent_traversal_is_blocked_regression(self, path):
        with pytest.raises(PathSecurityError):
            PathValidator.validate_workspace_path(path)

    @pytest.mark.parametrize("path", ["/etc/shadow", "/proc/self/environ", "/root/.bashrc"])
    def test_system_paths_are_blocked_regression(self, path):
        with pytest.raises(PathSecurityError):
            PathValidator.validate_workspace_path(path)

    @pytest.mark.parametrize("path", [".env", "id_rsa", "key.pem", "credentials.json"])
    def test_known_secret_files_are_blocked_regression(self, path):
        with pytest.raises(PathSecurityError):
            PathValidator.validate_workspace_path(path)

    @pytest.mark.vuln
    @pytest.mark.parametrize(
        "path",
        [
            ".git/hooks/pre-commit",
            ".git/hooks/post-checkout",
            ".github/workflows/ci.yml",
            ".npmrc",
            ".netrc",
            ".git-credentials",
            "secrets.yaml",
            ".env.prod",
            "config/.ssh/authorized_keys",
        ],
    )
    @pytest.mark.xfail(
        strict=True,
        reason="PT-02: the blocklist enumerates a handful of filenames and misses the paths that "
        "actually convert a workspace write into code execution (.git/hooks, CI workflows) or "
        "credential theft (.npmrc, .netrc, .git-credentials, secrets.yaml).",
    )
    def test_execution_and_credential_paths_are_blocked(self, path):
        with pytest.raises(PathSecurityError):
            PathValidator.validate_workspace_path(path)

    @pytest.mark.vuln
    @pytest.mark.parametrize("path", ["a;b.py", "a$(id).py", "a`id`.py", "a|b.py", "a'b.py", "a b;c.py"])
    @pytest.mark.xfail(
        strict=True,
        reason="PT-02/CMD-02: PathValidator permits shell metacharacters, and several tools "
        "interpolate the validated path straight into a shell string.",
    )
    def test_shell_metacharacters_in_paths_are_rejected(self, path):
        with pytest.raises(PathSecurityError):
            PathValidator.validate_workspace_path(path)


# ------------------------------------------------------------- containment
class TestWorkspaceContainment:
    def test_relative_paths_resolve_inside_the_workspace_regression(self, tmp_path):
        resolved = SandboxSecurityPolicy.validate_workspace_relative_path(str(tmp_path), "src/app.py")
        assert resolved.startswith(str(tmp_path))

    def test_parent_traversal_is_refused_regression(self, tmp_path):
        with pytest.raises(SecurityPolicyError):
            SandboxSecurityPolicy.validate_workspace_relative_path(str(tmp_path), "../outside.txt")

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="PT-01: containment is a bare str.startswith() with no separator, so a sibling "
        "directory whose name merely begins with the workspace name passes the check. Concurrent "
        "runs under a shared temp root can read and write each other's workspaces.",
    )
    def test_sibling_directory_with_a_shared_prefix_is_refused(self, tmp_path):
        workspace = tmp_path / "sb_1"
        workspace.mkdir()
        sibling = tmp_path / "sb_1_other_tenant"
        sibling.mkdir()
        (sibling / "stolen.txt").write_text("another tenant's source")

        with pytest.raises(SecurityPolicyError):
            SandboxSecurityPolicy.validate_workspace_relative_path(
                str(workspace), "../sb_1_other_tenant/stolen.txt"
            )

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="ESC-01: os.path.abspath does not resolve symlinks, so a link created inside the "
        "bind-mounted workspace passes containment and the host-side helper follows it out of the "
        "sandbox. This is a sandbox escape that needs no exploit.",
    )
    def test_symlink_out_of_the_workspace_is_refused(self, tmp_path):
        if not can_symlink(tmp_path):
            pytest.skip("creating symlinks requires privilege on this host")

        workspace = tmp_path / "workspace"
        workspace.mkdir()
        outside = tmp_path / "host_secret.txt"
        outside.write_text("host-only secret")
        os.symlink(outside, workspace / "notes.txt")

        with pytest.raises(SecurityPolicyError):
            SandboxSecurityPolicy.validate_workspace_relative_path(str(workspace), "notes.txt")

    @pytest.mark.vuln
    @pytest.mark.asyncio
    @pytest.mark.xfail(
        strict=True,
        reason="ESC-01: the same defect end to end - reading a symlinked workspace file returns "
        "host content through the sandbox interface.",
    )
    async def test_reading_a_symlinked_file_does_not_return_host_content(self, tmp_path, sandbox):
        if not can_symlink(tmp_path):
            pytest.skip("creating symlinks requires privilege on this host")

        sb, sandbox_id = sandbox
        secret = tmp_path / "host_secret.txt"
        secret.write_text("HOST-ONLY-SECRET")
        os.symlink(secret, os.path.join(sb.workdir(sandbox_id), "innocent.txt"))

        content = await sb.read_file(sandbox_id, "innocent.txt")
        assert "HOST-ONLY-SECRET" not in content


# ------------------------------------------------------- container hardening
class TestContainerHardening:
    def test_isolation_baseline_regression(self):
        opts = SandboxSecurityPolicy.get_container_security_options()
        assert opts["network_mode"] == "none"
        assert opts["read_only"] is True
        assert opts["cap_drop"] == ["ALL"]
        assert opts["privileged"] is False
        assert "no-new-privileges:true" in opts["security_opt"]
        assert opts["pids_limit"] > 0
        assert opts["memswap_limit"] == opts["mem_limit"]
        assert "noexec" in opts["tmpfs"]["/tmp"]
        assert "nosuid" in opts["tmpfs"]["/tmp"]

    def test_network_can_only_be_enabled_explicitly_regression(self):
        assert SandboxSecurityPolicy.get_container_security_options(network_enabled=True)["network_mode"] == "bridge"
        source = inspect.getsource(docker_sandbox.DockerSandboxAdapter.create_sandbox)
        assert "network_enabled=False" in source, "sandbox creation no longer forces the network off"

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="ESC-02: no `user` is set, so containers run as uid 0 against a host bind mount. "
        "Any breakout primitive lands as host root and agent-created files are root-owned.",
    )
    def test_containers_do_not_run_as_root(self):
        opts = SandboxSecurityPolicy.get_container_security_options()
        assert opts.get("user") not in (None, "", "0", "root", "0:0")

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="ESC-04: no seccomp or AppArmor profile is requested, so the container gets the "
        "permissive daemon default for a workload that executes untrusted code.",
    )
    def test_a_seccomp_profile_is_applied(self):
        security_opt = SandboxSecurityPolicy.get_container_security_options()["security_opt"]
        assert any("seccomp" in option for option in security_opt)

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="ESC-04: no ulimits and no storage quota, so generated code can exhaust file "
        "descriptors or fill the host filesystem through the bind-mounted workspace.",
    )
    def test_ulimits_and_a_disk_quota_are_set(self):
        opts = SandboxSecurityPolicy.get_container_security_options()
        assert opts.get("ulimits"), "no ulimits (nofile/fsize/nproc/core) requested"
        assert opts.get("storage_opt"), "no per-container storage quota requested"

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="ESC-04: SANDBOX_RUNTIME is configurable (docker | runsc | process) but "
        "create_sandbox never passes runtime= to the Docker API, so a configured gVisor runtime is "
        "silently ignored.",
    )
    def test_the_configured_runtime_reaches_the_docker_api(self):
        source = inspect.getsource(docker_sandbox.DockerSandboxAdapter.create_sandbox)
        assert "runtime=" in source

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="ESC-05: runtime images are referenced by mutable tag with no digest and no "
        "signature verification, so the interpreter that executes untrusted code can change "
        "underneath the platform.",
    )
    def test_runtime_images_are_digest_pinned(self):
        unpinned = [
            runtime.image for runtime in runtime_registry.list_runtimes().values() if "@sha256:" not in runtime.image
        ]
        assert unpinned == [], f"mutable image tags: {unpinned}"

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="ESC-03: SANDBOX_ALLOW_HOST_FALLBACK turns every agent command into direct execution "
        "on the backend host. Settings uses extra='allow' with no production guard, so a stray "
        "environment variable disables the sandbox silently.",
    )
    def test_host_fallback_cannot_be_enabled_in_production(self):
        with pytest.raises(Exception):
            settings.__class__(ENVIRONMENT="production", SANDBOX_ALLOW_HOST_FALLBACK=True)

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="ESC-03: Settings uses extra='allow', so unknown or misspelled environment variables "
        "are accepted silently instead of failing fast.",
    )
    def test_settings_reject_unknown_environment_keys(self):
        assert settings.model_config.get("extra") == "forbid"

    def test_host_fallback_is_disabled_by_default_regression(self):
        assert settings.SANDBOX_ALLOW_HOST_FALLBACK is False


# ----------------------------------------------------- environment isolation
class TestEnvironmentIsolation:
    def test_provider_and_database_secrets_are_dropped_regression(self):
        sanitized = SandboxSecurityPolicy.sanitize_environment(
            {
                "OPENAI_API_KEY": "sk-live",
                "ANTHROPIC_API_KEY": "sk-ant",
                "POSTGRES_PASSWORD": "hunter2",
                "SECRET_KEY": "jwt-signing-key",
                "AWS_SECRET_ACCESS_KEY": "aws",
                "GITHUB_TOKEN": "ghp_x",
            }
        )
        assert "sk-live" not in str(sanitized)
        assert "hunter2" not in str(sanitized)
        assert "ghp_x" not in str(sanitized)

    @pytest.mark.vuln
    @pytest.mark.parametrize(
        "key,value",
        [
            ("PATH", "/attacker/bin"),
            ("LD_PRELOAD", "/workspace/evil.so"),
            ("PYTHONPATH", "/workspace/hijack"),
            ("PYTHONSTARTUP", "/workspace/startup.py"),
            ("NODE_OPTIONS", "--require /workspace/evil.js"),
            ("BASH_ENV", "/workspace/evil.sh"),
        ],
    )
    @pytest.mark.xfail(
        strict=True,
        reason="LEAK-02/ESC-03: sanitize_environment filters by key *name* pattern only, then lets "
        "caller-supplied values overwrite the curated defaults. Loader variables such as PATH, "
        "LD_PRELOAD and PYTHONPATH are not on the sensitive list, so they can be injected to hijack "
        "execution inside the sandbox.",
    )
    def test_loader_variables_cannot_be_overridden(self, key, value):
        sanitized = SandboxSecurityPolicy.sanitize_environment({key: value})
        assert sanitized.get(key) != value

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="LEAK-02: the sanitiser should be an allowlist of permitted variable names rather "
        "than a deny-pattern list, so a secret in an unexpectedly named variable cannot pass.",
    )
    def test_environment_sanitisation_is_allowlist_based(self):
        sanitized = SandboxSecurityPolicy.sanitize_environment({"COMPANY_LICENCE_BLOB": "super-secret-material"})
        assert "COMPANY_LICENCE_BLOB" not in sanitized


# --------------------------------------------------------- workspace handling
class TestWorkspaceFileHandling:
    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="REPO-01: shutil.copytree defaults to symlinks=False, which dereferences links and "
        "copies the *contents* of their targets. A repository containing a link to a host secret "
        "gets that secret copied into the sandbox and then into the model context.",
    )
    def test_workspace_ingest_does_not_dereference_symlinks(self):
        source = inspect.getsource(docker_sandbox.DockerSandboxAdapter.create_sandbox)
        assert "symlinks=True" in source

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="REPO-01/DOS-01: workspace ingest applies no byte, file-count or depth limit, so a "
        "hostile repository can fill the host disk during copy.",
    )
    def test_workspace_ingest_enforces_size_limits(self):
        source = inspect.getsource(docker_sandbox.DockerSandboxAdapter.create_sandbox)
        assert any(token in source for token in ("max_bytes", "max_files", "MAX_WORKSPACE"))

    @pytest.mark.vuln
    @pytest.mark.xfail(
        strict=True,
        reason="FILE-01: workspaces are created with os.makedirs under the shared temp directory "
        "using the default umask and a predictable name, so other local users can read or "
        "pre-create them.",
    )
    def test_workspace_directory_is_private(self):
        source = inspect.getsource(docker_sandbox.DockerSandboxAdapter.create_sandbox)
        assert "mkdtemp" in source or "0o700" in source or "chmod" in source

    @pytest.mark.skipif(os.name == "nt", reason="POSIX permission semantics")
    def test_a_private_temp_directory_is_actually_private(self, tmp_path):
        """Demonstrates the standard the platform should meet."""
        import tempfile

        path = tempfile.mkdtemp(dir=tmp_path)
        os.chmod(path, 0o700)
        mode = stat.S_IMODE(os.stat(path).st_mode)
        assert mode == 0o700
