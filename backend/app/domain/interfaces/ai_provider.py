from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncIterator
from pydantic import BaseModel


class LLMMessage(BaseModel):
    role: str  # system, user, assistant, tool
    content: str
    tool_calls: Optional[List[Dict[str, Any]]] = None
    tool_call_id: Optional[str] = None


class LLMResponse(BaseModel):
    content: str
    tool_calls: List[Dict[str, Any]] = []
    finish_reason: str = "stop"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class AIProviderInterface(ABC):
    @abstractmethod
    async def generate_response(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """Generate a complete response from the AI provider."""
        pass

    @abstractmethod
    async def stream_response(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        """Stream response content tokens as they are generated."""
        pass
