from typing import Dict, Any, Optional
from app.domain.interfaces.ai_provider import AIProviderInterface, LLMMessage
from app.domain.interfaces.sandbox import SandboxInterface
from app.core.prompts.manager import PromptManager, get_prompt_manager
from app.schemas.prompts import PromptRole, RequirementAnalyzerInput
from app.core.logging import logger


class RequirementAndProjectAnalyzer:
    def __init__(
        self,
        provider: AIProviderInterface,
        sandbox: SandboxInterface,
        sandbox_id: str,
        prompt_manager: Optional[PromptManager] = None,
    ):
        self.provider = provider
        self.sandbox = sandbox
        self.sandbox_id = sandbox_id
        self.prompt_manager = prompt_manager or get_prompt_manager()

    async def analyze(self, prompt: str, run_id: Optional[str] = None) -> Dict[str, Any]:
        logger.info("Running Requirement & Project Analysis stage")

        # List files in workspace sandbox to understand project structure
        try:
            cmd_res = await self.sandbox.execute_command(self.sandbox_id, "find . -maxdepth 3 -not -path '*/.*'")
            project_tree = cmd_res.stdout if cmd_res.exit_code == 0 else "Empty or uninitialized workspace"
        except Exception as e:
            project_tree = f"Could not list workspace files: {str(e)}"

        # Render prompt using versioned PromptManager
        inputs = RequirementAnalyzerInput(
            requirement_prompt=prompt,
            project_tree=project_tree,
        )
        rendered_prompt, metadata = self.prompt_manager.render_prompt(
            role=PromptRole.REQUIREMENT_ANALYZER,
            inputs=inputs,
            user_or_task_id=run_id,
        )

        messages = [
            LLMMessage(role="system", content="You are a senior software architect requirement analyzer."),
            LLMMessage(role="user", content=rendered_prompt),
        ]

        response = await self.provider.generate_response(messages=messages, temperature=0.2)
        content = response.content or ""

        # Validate structured output using PromptManager
        try:
            structured_output = self.prompt_manager.parse_and_validate_output(
                role=PromptRole.REQUIREMENT_ANALYZER,
                llm_response_content=content,
            )
            analysis_text = f"Primary Goal: {structured_output.primary_goal}\nScope: {structured_output.scope_summary}\nRisk: {structured_output.risk_assessment}"
        except Exception as e:
            logger.warning("Could not parse structured output from requirement analyzer; fallback to text", error=str(e))
            analysis_text = content

        if run_id:
            self.prompt_manager.audit_prompt_execution(run_id=run_id, metadata=metadata)

        return {
            "analysis": analysis_text,
            "file_tree": project_tree,
            "prompt_version": metadata.version,
            "prompt_variant": metadata.variant,
            "prompt_hash": metadata.content_hash,
        }
