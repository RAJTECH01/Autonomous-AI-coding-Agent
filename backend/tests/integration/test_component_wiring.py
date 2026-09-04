"""Integration tests: real components wired together.

These deliberately avoid test doubles for anything inside the process boundary.
The Git tests drive the **real git binary** inside a real repository, so branch
isolation, protected-branch refusal and commit metadata are verified against git
itself rather than against a recorded command string.
"""

import pytest

from app.application.agent.memory_manager import AgentMemoryManager
from app.application.agent.subagents.analyzer import RequirementAndProjectAnalyzer
from app.application.agent.subagents.planner import PlanningAgent
from app.core.prompts.manager import get_prompt_manager
from app.domain.entities.git import ProtectedBranchError, UnauthorizedPushError
from app.infrastructure.ai_providers.provider_factory import AIProviderFactory
from app.infrastructure.tools.controlled_tool_layer import ControlledToolLayer
from app.infrastructure.vcs.local_git_provider import LocalGitProvider
from app.schemas.prompts import PromptRole, RequirementAnalyzerInput

from tests.support.ai_providers import ScriptedAIProvider, response
from tests.support.factories import PASSING_PROJECT, make_run

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def init_repo(sandbox, sandbox_id):
    """Turn the sandbox workspace into a real git repository with one commit."""
    for command in (
        "git init -b work",
        "git config user.email agent@example.com",
        "git config user.name Agent",
        "git config commit.gpgsign false",
        "git add -A",
        "git -c user.email=agent@example.com -c user.name=Agent commit -m initial",
    ):
        await sandbox.execute_command(sandbox_id, command)


# ------------------------------------------------------------- prompt pipeline
class TestPromptPipeline:
    async def test_real_prompt_templates_load_and_render(self):
        manager = get_prompt_manager()
        rendered, metadata = manager.render_prompt(
            role=PromptRole.REQUIREMENT_ANALYZER,
            inputs=RequirementAnalyzerInput(
                requirement_prompt="Add a multiply helper", project_tree="./calculator.py"
            ),
        )
        assert "Add a multiply helper" in rendered
        assert "calculator.py" in rendered
        assert metadata.content_hash
        assert metadata.version

    async def test_prompt_executions_are_audited(self):
        manager = get_prompt_manager()
        _rendered, metadata = manager.render_prompt(
            role=PromptRole.REQUIREMENT_ANALYZER,
            inputs=RequirementAnalyzerInput(requirement_prompt="x", project_tree="y"),
            user_or_task_id="run-1",
        )
        before = len(manager.audit_records)
        manager.audit_prompt_execution(run_id="run-1", metadata=metadata)
        assert len(manager.audit_records) == before + 1
        assert manager.audit_records[-1].content_hash == metadata.content_hash

    async def test_analyzer_and_planner_share_the_workspace_view(self, project_sandbox):
        sb, sandbox_id = await project_sandbox(PASSING_PROJECT)
        provider = ScriptedAIProvider(
            script=[response(content="Goal: add multiply"), response(content="## Plan\n1. edit calculator.py\n")]
        )

        analyzer = RequirementAndProjectAnalyzer(provider, sb, sandbox_id)
        analysis = await analyzer.analyze("Add a multiply helper", run_id="run-int-1")
        assert "calculator.py" in analysis["file_tree"]

        planner = PlanningAgent(provider)
        plan = await planner.create_plan(
            "Add a multiply helper", analysis["analysis"], file_tree=analysis["file_tree"], run_id="run-int-1"
        )
        assert "calculator.py" in plan
        assert "calculator.py" in provider.prompts()[1], "the planner did not receive the project tree"


# --------------------------------------------------------------- provider wiring
class TestProviderFactory:
    @pytest.mark.parametrize("name", ["anthropic", "openai"])
    async def test_known_providers_either_construct_or_fail_loudly(self, name):
        """Without credentials the factory must raise something actionable rather
        than hand back a half-initialised client that fails later mid-run."""
        try:
            provider = AIProviderFactory.get_provider(name)
        except Exception as exc:
            message = str(exc).lower()
            assert "key" in message or "credential" in message, f"unclear provider error: {exc}"
            return
        assert hasattr(provider, "generate_response")

    async def test_unknown_provider_is_refused_or_defaulted(self):
        try:
            provider = AIProviderFactory.get_provider("definitely-not-a-provider")
        except Exception:
            return  # explicit rejection is the preferred behaviour
        assert hasattr(provider, "generate_response"), "factory returned something unusable"


# ------------------------------------------------------------------- real git
class TestRealGitIntegration:
    async def test_repository_state_is_read_from_a_real_repository(self, project_sandbox, git_binary):
        sb, sandbox_id = await project_sandbox(PASSING_PROJECT)
        await init_repo(sb, sandbox_id)

        provider = LocalGitProvider(sandbox=sb, sandbox_id=sandbox_id)
        state = await provider.get_current_state(workspace_path="")

        assert state.branch_name == "work"
        assert len(state.commit_hash) >= 7
        assert state.is_dirty is False

    async def test_branch_creation_and_commit_round_trip(self, project_sandbox, git_binary):
        sb, sandbox_id = await project_sandbox(PASSING_PROJECT)
        await init_repo(sb, sandbox_id)
        provider = LocalGitProvider(sandbox=sb, sandbox_id=sandbox_id)

        branch = await provider.create_branch(workspace_path="", branch_name="agent/task-1", checkout=True)
        assert branch.success is True
        assert branch.created is True

        await sb.write_file(sandbox_id, "calculator.py", "def add(a, b):\n    return a + b\n\n\ndef multiply(a, b):\n    return a * b\n")

        status = await provider.get_status(workspace_path="")
        assert status.success is True
        assert status.state.is_dirty is True

        commit = await provider.create_commit(
            workspace_path="", message="feat: add multiply", task_id="task-1", run_id="run-1"
        )
        assert commit.success is True, commit.error_message
        assert commit.commit_metadata.branch_name == "agent/task-1"
        assert commit.commit_metadata.message == "feat: add multiply"
        assert "calculator.py" in commit.commit_metadata.files_changed

    async def test_direct_commit_to_a_protected_branch_is_refused(self, project_sandbox, git_binary):
        sb, sandbox_id = await project_sandbox(PASSING_PROJECT)
        for command in (
            "git init -b main",
            "git config user.email agent@example.com",
            "git config user.name Agent",
            "git add -A",
            "git -c user.email=agent@example.com -c user.name=Agent commit -m initial",
        ):
            await sb.execute_command(sandbox_id, command)

        provider = LocalGitProvider(sandbox=sb, sandbox_id=sandbox_id)
        await sb.write_file(sandbox_id, "calculator.py", "# modified\n")

        with pytest.raises(ProtectedBranchError):
            await provider.create_commit(workspace_path="", message="direct to main")

    async def test_creating_a_protected_branch_is_refused(self, project_sandbox, git_binary):
        sb, sandbox_id = await project_sandbox(PASSING_PROJECT)
        await init_repo(sb, sandbox_id)
        provider = LocalGitProvider(sandbox=sb, sandbox_id=sandbox_id)

        with pytest.raises(ProtectedBranchError):
            await provider.create_branch(workspace_path="", branch_name="production")

    async def test_push_without_authorization_never_reaches_git(self, project_sandbox, git_binary):
        sb, sandbox_id = await project_sandbox(PASSING_PROJECT)
        await init_repo(sb, sandbox_id)
        provider = LocalGitProvider(sandbox=sb, sandbox_id=sandbox_id)

        before = len(sb.commands)
        with pytest.raises(UnauthorizedPushError):
            await provider.push_branch(workspace_path="", remote="origin", branch_name="work")

        issued = sb.commands[before:]
        assert not any(command.startswith("git push") for command in issued)

    async def test_refused_push_is_recorded_in_the_audit_trail(self, project_sandbox, git_binary):
        sb, sandbox_id = await project_sandbox(PASSING_PROJECT)
        await init_repo(sb, sandbox_id)
        provider = LocalGitProvider(sandbox=sb, sandbox_id=sandbox_id)

        with pytest.raises(UnauthorizedPushError):
            await provider.push_branch(workspace_path="", remote="origin", branch_name="work")

        records = await provider.get_audit_logs()
        push_records = [record for record in records if record.operation == "git_push"]
        assert push_records
        assert push_records[-1].user_authorized is False
        assert push_records[-1].exit_code == 1

    async def test_diff_reports_real_line_statistics(self, project_sandbox, git_binary):
        sb, sandbox_id = await project_sandbox(PASSING_PROJECT)
        await init_repo(sb, sandbox_id)
        provider = LocalGitProvider(sandbox=sb, sandbox_id=sandbox_id)

        await sb.write_file(sandbox_id, "calculator.py", "def add(a, b):\n    return a + b\n\n\ndef extra():\n    return 1\n")
        diff = await provider.get_diff(workspace_path="")

        assert diff.success is True
        assert "calculator.py" in diff.files_changed
        assert diff.total_additions > 0


# ----------------------------------------------------- tool layer + git tools
class TestGitToolsThroughTheToolLayer:
    async def test_git_status_tool_reports_a_real_branch(self, project_sandbox, git_binary):
        sb, sandbox_id = await project_sandbox(PASSING_PROJECT)
        await init_repo(sb, sandbox_id)

        result = await ControlledToolLayer().execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="get_git_status",
            args={"include_diff": False}, run=make_run(),
        )
        assert result.success is True
        assert "work" in result.output

    async def test_branch_tool_refuses_protected_names(self, project_sandbox, git_binary):
        sb, sandbox_id = await project_sandbox(PASSING_PROJECT)
        await init_repo(sb, sandbox_id)

        result = await ControlledToolLayer().execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="create_git_branch",
            args={"branch_name": "main", "checkout": True}, run=make_run(),
        )
        assert result.success is False
        assert "protected" in (result.error or "").lower()

    async def test_push_tool_refuses_without_confirmation(self, project_sandbox, git_binary):
        sb, sandbox_id = await project_sandbox(PASSING_PROJECT)
        await init_repo(sb, sandbox_id)

        result = await ControlledToolLayer().execute_tool(
            sandbox=sb, sandbox_id=sandbox_id, tool_name="push_git_branch",
            args={"remote": "origin", "branch_name": "work", "confirm_push": False},
            run=make_run(), user_role="project_owner",
        )
        assert result.success is False
        assert "authorization" in (result.error or "").lower()


# --------------------------------------------------------- memory + provider
class TestMemoryProviderLoop:
    async def test_the_provider_receives_the_full_conversation(self):
        memory = AgentMemoryManager()
        memory.set_system_prompt("system rules")
        memory.add_user_message("requirement")
        memory.add_assistant_message("thinking")
        memory.add_tool_response("call-1", "tool output")

        provider = ScriptedAIProvider(script=[response(content="ok")])
        await provider.generate_response(messages=memory.get_messages())

        roles = [message.role for message in provider.calls[0]]
        assert roles[0] == "system"
        assert "assistant" in roles
        assert any("untrusted_tool_output" in message.content for message in provider.calls[0])
