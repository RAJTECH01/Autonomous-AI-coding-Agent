from typing import Dict, Any, Optional
from app.domain.interfaces.ai_provider import AIProviderInterface, LLMMessage
from app.core.prompts.manager import PromptManager, get_prompt_manager
from app.schemas.prompts import PromptRole, PlannerInput
from app.core.logging import logger


class PlanningAgent:
    def __init__(
        self,
        provider: AIProviderInterface,
        prompt_manager: Optional[PromptManager] = None,
    ):
        self.provider = provider
        self.prompt_manager = prompt_manager or get_prompt_manager()

    async def create_plan(
        self,
        prompt: str,
        analysis: str,
        file_tree: str = "",
        run_id: Optional[str] = None,
    ) -> str:
        logger.info("Running Planning Agent stage")

        inputs = PlannerInput(
            requirement=prompt,
            analysis_summary=analysis,
            file_tree=file_tree,
        )

        rendered_prompt, metadata = self.prompt_manager.render_prompt(
            role=PromptRole.PLANNER,
            inputs=inputs,
            user_or_task_id=run_id,
        )

        messages = [
            LLMMessage(role="system", content="You are a software architect planning agent."),
            LLMMessage(role="user", content=rendered_prompt),
        ]

        response = await self.provider.generate_response(messages=messages, temperature=0.2)
        content = response.content or ""

        try:
            structured = self.prompt_manager.parse_and_validate_output(
                role=PromptRole.PLANNER,
                llm_response_content=content,
            )
            plan_result = structured.plan_markdown
        except Exception:
            plan_result = content

        if run_id:
            self.prompt_manager.audit_prompt_execution(run_id=run_id, metadata=metadata)

        return plan_result
