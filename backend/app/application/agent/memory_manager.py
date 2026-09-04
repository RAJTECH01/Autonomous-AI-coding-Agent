from typing import List, Dict, Any
from app.domain.interfaces.ai_provider import LLMMessage
from app.core.config import settings


class AgentMemoryManager:
    def __init__(self, max_tokens: int = settings.MAX_CONTEXT_TOKENS):
        self.max_tokens = max_tokens
        self.messages: List[LLMMessage] = []

    def set_system_prompt(self, prompt: str):
        if self.messages and self.messages[0].role == "system":
            self.messages[0] = LLMMessage(role="system", content=prompt)
        else:
            self.messages.insert(0, LLMMessage(role="system", content=prompt))

    def add_user_message(self, content: str):
        self.messages.append(LLMMessage(role="user", content=content))

    def add_assistant_message(self, content: str, tool_calls: List[Dict[str, Any]] = None):
        self.messages.append(LLMMessage(role="assistant", content=content, tool_calls=tool_calls))

    def add_tool_response(self, tool_call_id: str, content: str):
        # Truncate overly long tool outputs (e.g., massive stdout or stack traces) to protect context window
        max_tool_chars = 12000
        if len(content) > max_tool_chars:
            truncated = content[:max_tool_chars] + f"\n... [Output truncated from {len(content)} to {max_tool_chars} characters]"
        else:
            truncated = content
            
        self.messages.append(LLMMessage(
            role="user",
            content=f"<untrusted_tool_output tool_call_id='{tool_call_id}'>\n{truncated}\n</untrusted_tool_output>",
            tool_call_id=tool_call_id
        ))

    def get_messages(self) -> List[LLMMessage]:
        return self.messages
