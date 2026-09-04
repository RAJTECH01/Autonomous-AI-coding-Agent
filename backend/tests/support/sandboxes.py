"""Sandbox implementations for tests.

``InProcessSandbox`` is the workhorse: it satisfies ``SandboxInterface`` using a
**real temporary directory**, real file I/O, the **production** containment
policy (``SandboxSecurityPolicy.validate_workspace_relative_path``), and real
subprocesses for ``python``/``pytest``/``git``. Only the container boundary is
absent, which keeps the tests portable while still exercising genuine
filesystem and interpreter behaviour.

Every command string is recorded verbatim so injection tests can assert on what
would have been handed to ``sh -c``.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from typing import Dict, List, Optional

from app.core.config import settings
from app.core.exceptions import SandboxExecutionError
from app.domain.interfaces.sandbox import CommandResult, SandboxInterface
from app.infrastructure.sandbox.policy import SandboxSecurityPolicy, SecurityPolicyError

from tests.support.shell import ShellSyntaxError, split_segments


class InProcessSandbox(SandboxInterface):
    """Realistic, portable sandbox backed by a real temp directory."""

    def __init__(self, allow_real_subprocess: bool = True):
        self._sandboxes: Dict[str, str] = {}
        self.commands: List[str] = []
        self.segments: List[List[List[str]]] = []
        self.allow_real_subprocess = allow_real_subprocess
        self.destroyed: List[str] = []

    # ---------------------------------------------------------------- helpers
    @property
    def last_command(self) -> str:
        assert self.commands, "no command has been executed"
        return self.commands[-1]

    def workdir(self, sandbox_id: str) -> str:
        return self._sandboxes[sandbox_id]

    def extra_segments(self, command: str) -> List[List[str]]:
        """Command segments beyond the first - i.e. successful injection."""
        try:
            return split_segments(command)[1:]
        except ShellSyntaxError:
            return [["<unbalanced-quoting>"]]

    # ------------------------------------------------------------- lifecycle
    async def create_sandbox(
        self,
        session_id: str,
        workspace_path: str = "",
        runtime: str = "python",
        env_vars: Optional[Dict[str, str]] = None,
    ) -> str:
        sandbox_id = f"sb_{session_id}_{uuid.uuid4().hex[:8]}"
        workdir = tempfile.mkdtemp(prefix="test_sb_")
        if workspace_path and os.path.isdir(workspace_path):
            shutil.copytree(workspace_path, workdir, dirs_exist_ok=True)
        self._sandboxes[sandbox_id] = workdir
        return sandbox_id

    async def destroy_sandbox(self, sandbox_id: str) -> bool:
        workdir = self._sandboxes.pop(sandbox_id, None)
        if workdir is None:
            return False
        shutil.rmtree(workdir, ignore_errors=True)
        self.destroyed.append(sandbox_id)
        return True

    # --------------------------------------------------------------- file I/O
    def _resolve(self, sandbox_id: str, file_path: str) -> str:
        if sandbox_id not in self._sandboxes:
            raise SandboxExecutionError(f"Sandbox '{sandbox_id}' not found")
        try:
            # Production policy on purpose: escapes that pass here pass in prod.
            return SandboxSecurityPolicy.validate_workspace_relative_path(
                self._sandboxes[sandbox_id], file_path
            )
        except SecurityPolicyError as exc:
            raise SandboxExecutionError(str(exc)) from exc

    async def read_file(self, sandbox_id: str, file_path: str) -> str:
        abs_path = self._resolve(sandbox_id, file_path)
        if not os.path.exists(abs_path):
            raise SandboxExecutionError(f"File not found: '{file_path}'")
        with open(abs_path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read()

    async def write_file(self, sandbox_id: str, file_path: str, content: str) -> bool:
        abs_path = self._resolve(sandbox_id, file_path)
        parent = os.path.dirname(abs_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as handle:
            handle.write(content)
        return True

    # -------------------------------------------------------------- execution
    async def execute_command(
        self,
        sandbox_id: str,
        command: str,
        timeout_seconds: int = 120,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> CommandResult:
        if sandbox_id not in self._sandboxes:
            raise SandboxExecutionError(f"Sandbox '{sandbox_id}' not found")

        self.commands.append(command)
        started = time.time()
        cwd = self._sandboxes[sandbox_id]

        try:
            segments = split_segments(command)
        except ShellSyntaxError as exc:
            self.segments.append([])
            return self._result(command, 2, "", str(exc), started)

        self.segments.append(segments)

        exit_code, stdout, stderr = 0, "", ""
        for segment in segments:
            if not segment:
                continue
            exit_code, out, err = self._run_segment(segment, cwd)
            stdout += out
            stderr += err
            if segment[0] == "cd" and exit_code == 0 and len(segment) > 1:
                candidate = segment[1] if os.path.isabs(segment[1]) else os.path.join(cwd, segment[1])
                if os.path.isdir(candidate):
                    cwd = candidate

        # Same truncation contract as the production adapter.
        stdout, trunc_out = SandboxSecurityPolicy.truncate_output(
            stdout, max_bytes=settings.SANDBOX_MAX_OUTPUT_BYTES
        )
        stderr, trunc_err = SandboxSecurityPolicy.truncate_output(
            stderr, max_bytes=settings.SANDBOX_MAX_OUTPUT_BYTES
        )
        return self._result(command, exit_code, stdout, stderr, started, trunc_out or trunc_err)

    def _result(self, command, exit_code, stdout, stderr, started, truncated=False) -> CommandResult:
        return CommandResult(
            command=command,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=int((time.time() - started) * 1000),
            truncated=truncated,
        )

    # A deliberately small command set: enough for the real tools, and anything
    # unknown returns 127 exactly like a shell would.
    def _run_segment(self, argv: List[str], cwd: str):
        program, args = argv[0], argv[1:]
        handler = getattr(self, f"_cmd_{program.replace('-', '_')}", None)
        if handler is None:
            return 127, "", f"sh: 1: {program}: not found\n"
        return handler(args, cwd)

    # -- builtins ---------------------------------------------------------
    def _cmd_cd(self, args, cwd):
        target = args[0] if args else cwd
        path = target if os.path.isabs(target) else os.path.join(cwd, target)
        return (0, "", "") if os.path.isdir(path) else (1, "", f"cd: {target}: No such directory\n")

    def _cmd_true(self, args, cwd):
        return 0, "", ""

    def _cmd_false(self, args, cwd):
        return 1, "", ""

    def _cmd_echo(self, args, cwd):
        return 0, " ".join(args) + "\n", ""

    def _cmd_test(self, args, cwd):
        if len(args) >= 2 and args[0] in ("-f", "-d", "-e"):
            path = os.path.join(cwd, args[1])
            checks = {"-f": os.path.isfile, "-d": os.path.isdir, "-e": os.path.exists}
            return (0 if checks[args[0]](path) else 1), "", ""
        return 1, "", ""

    def _cmd_ls(self, args, cwd):
        targets = [a for a in args if not a.startswith("-")] or ["."]
        out, code = "", 0
        for target in targets:
            path = os.path.join(cwd, target)
            if os.path.isdir(path):
                out += "\n".join(sorted(os.listdir(path))) + "\n"
            elif os.path.isfile(path):
                out += target + "\n"
            else:
                code = 2
        return code, out, "" if code == 0 else f"ls: cannot access\n"

    def _cmd_mkdir(self, args, cwd):
        for target in [a for a in args if not a.startswith("-")]:
            os.makedirs(os.path.join(cwd, target), exist_ok=True)
        return 0, "", ""

    def _cmd_rm(self, args, cwd):
        flags = [a for a in args if a.startswith("-")]
        recursive = any("r" in f for f in flags)
        force = any("f" in f for f in flags)
        code, err = 0, ""
        for target in [a for a in args if not a.startswith("-")]:
            path = os.path.join(cwd, target)
            if os.path.isdir(path) and recursive:
                shutil.rmtree(path, ignore_errors=True)
            elif os.path.isfile(path) or os.path.islink(path):
                os.remove(path)
            elif not force:
                code, err = 1, err + f"rm: cannot remove '{target}': No such file or directory\n"
        return code, "", err

    def _cmd_cat(self, args, cwd):
        out, code, err = "", 0, ""
        for target in [a for a in args if not a.startswith("-")]:
            path = os.path.join(cwd, target)
            try:
                with open(path, "r", encoding="utf-8", errors="replace") as handle:
                    out += handle.read()
            except OSError:
                code, err = 1, err + f"cat: {target}: No such file or directory\n"
        return code, out, err

    def _cmd_find(self, args, cwd):
        root = args[0] if args and not args[0].startswith("-") else "."
        max_depth = None
        if "-maxdepth" in args:
            try:
                max_depth = int(args[args.index("-maxdepth") + 1])
            except (IndexError, ValueError):
                max_depth = None
        base = os.path.join(cwd, root)
        if not os.path.exists(base):
            return 1, "", f"find: '{root}': No such file or directory\n"

        found = [root]
        for dirpath, dirnames, filenames in os.walk(base):
            rel = os.path.relpath(dirpath, base)
            depth = 0 if rel == "." else len(rel.split(os.sep))
            if max_depth is not None and depth >= max_depth:
                dirnames[:] = []
                continue
            for name in sorted(dirnames) + sorted(filenames):
                entry = os.path.join(root, "" if rel == "." else rel, name)
                found.append(entry.replace(os.sep, "/"))
        return 0, "\n".join(found) + "\n", ""

    def _cmd_grep(self, args, cwd):
        include = None
        positional = []
        for arg in args:
            if arg.startswith("--include="):
                include = arg.split("=", 1)[1]
            elif not arg.startswith("-"):
                positional.append(arg)
        if not positional:
            return 2, "", "grep: no pattern\n"
        pattern = positional[0]
        root = os.path.join(cwd, positional[1] if len(positional) > 1 else ".")

        import fnmatch

        matches = []
        for dirpath, _dirnames, filenames in os.walk(root):
            for name in filenames:
                if include and not fnmatch.fnmatch(name, include):
                    continue
                path = os.path.join(dirpath, name)
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as handle:
                        for lineno, line in enumerate(handle, start=1):
                            if pattern in line:
                                rel = os.path.relpath(path, cwd).replace(os.sep, "/")
                                matches.append(f"{rel}:{lineno}:{line.rstrip()}")
                except OSError:
                    continue
        return (0 if matches else 1), ("\n".join(matches) + "\n" if matches else ""), ""

    def _cmd_tree(self, args, cwd):
        # `tree` is genuinely absent from slim images; the tools must fall back.
        return 127, "", "sh: 1: tree: not found\n"

    # -- real subprocesses -------------------------------------------------
    def _subprocess(self, argv, cwd, timeout=60):
        if not self.allow_real_subprocess:
            return 127, "", "subprocess execution disabled in this sandbox\n"
        try:
            proc = subprocess.run(
                argv, cwd=cwd, capture_output=True, text=True, timeout=timeout,
            )
            return proc.returncode, proc.stdout, proc.stderr
        except FileNotFoundError:
            return 127, "", f"sh: 1: {argv[0]}: not found\n"
        except subprocess.TimeoutExpired:
            return 124, "", "timeout\n"

    def _cmd_python(self, args, cwd):
        return self._subprocess([sys.executable, *args], cwd)

    def _cmd_python3(self, args, cwd):
        return self._cmd_python(args, cwd)

    def _cmd_pytest(self, args, cwd):
        return self._subprocess([sys.executable, "-m", "pytest", *args], cwd)

    def _cmd_git(self, args, cwd):
        return self._subprocess(["git", *args], cwd)

    def _cmd_npx(self, args, cwd):
        return 127, "", "sh: 1: npx: not found\n"

    def _cmd_npm(self, args, cwd):
        return 127, "", "sh: 1: npm: not found\n"


class RecordingSandbox(InProcessSandbox):
    """Records commands but never executes anything.

    Used where the assertion is about the *command string* (injection, quoting)
    and executing it would be pointless or unsafe.
    """

    def __init__(self, exit_code: int = 0, stdout: str = "", stderr: str = ""):
        super().__init__(allow_real_subprocess=False)
        self._exit_code = exit_code
        self._stdout = stdout
        self._stderr = stderr

    async def execute_command(
        self,
        sandbox_id: str,
        command: str,
        timeout_seconds: int = 120,
        env_vars: Optional[Dict[str, str]] = None,
    ) -> CommandResult:
        self.commands.append(command)
        try:
            self.segments.append(split_segments(command))
        except ShellSyntaxError:
            self.segments.append([])
        return CommandResult(
            command=command,
            exit_code=self._exit_code,
            stdout=self._stdout,
            stderr=self._stderr,
            duration_ms=1,
        )


class FailingSandbox(InProcessSandbox):
    """Every operation raises - models a dead container / unreachable daemon."""

    def __init__(self, message: str = "Container initialization failed: daemon unreachable"):
        super().__init__(allow_real_subprocess=False)
        self.message = message

    async def create_sandbox(self, session_id: str, workspace_path: str = "", runtime: str = "python", env_vars=None) -> str:
        raise SandboxExecutionError(self.message)

    async def execute_command(self, sandbox_id: str, command: str, timeout_seconds: int = 120, env_vars=None) -> CommandResult:
        self.commands.append(command)
        raise SandboxExecutionError(self.message)

    async def read_file(self, sandbox_id: str, file_path: str) -> str:
        raise SandboxExecutionError(self.message)

    async def write_file(self, sandbox_id: str, file_path: str, content: str) -> bool:
        raise SandboxExecutionError(self.message)


class FlakySandbox(InProcessSandbox):
    """Fails the first ``fail_times`` commands, then behaves normally."""

    def __init__(self, fail_times: int = 2):
        super().__init__(allow_real_subprocess=True)
        self.fail_times = fail_times
        self.attempts = 0

    async def execute_command(self, sandbox_id: str, command: str, timeout_seconds: int = 120, env_vars=None) -> CommandResult:
        self.attempts += 1
        if self.attempts <= self.fail_times:
            self.commands.append(command)
            raise SandboxExecutionError(f"transient container error (attempt {self.attempts})")
        return await super().execute_command(sandbox_id, command, timeout_seconds, env_vars)


class HangingSandbox(InProcessSandbox):
    """Sleeps longer than any caller's timeout - drives timeout handling."""

    def __init__(self, delay_seconds: float = 5.0):
        super().__init__(allow_real_subprocess=False)
        self.delay_seconds = delay_seconds

    async def execute_command(self, sandbox_id: str, command: str, timeout_seconds: int = 120, env_vars=None) -> CommandResult:
        self.commands.append(command)
        await asyncio.sleep(self.delay_seconds)
        return CommandResult(command=command, exit_code=0, stdout="", stderr="", duration_ms=0)
