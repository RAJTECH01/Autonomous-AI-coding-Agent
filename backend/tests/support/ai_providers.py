"""AI provider test doubles.

The model API is the one boundary we must not cross in CI: it costs money and is
non-deterministic. Everything downstream of the provider (memory, tool layer,
sandbox, state machine, persistence) runs for real against these doubles.

``ScriptedAIProvider`` replays a fixed script of responses, which is how we drive
deterministic scenarios like "the model emits a tool call with a traversal path"
or "the model produces code with a syntax error".
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Sequence, Union

from app.domain.interfaces.ai_provider import AIProviderInterface, LLMMessage, LLMResponse


def tool_call(name: str, arguments: Optional[Dict[str, Any]] = None, call_id: str = "call-1") -> Dict[str, Any]:
    """Build a provider-shaped tool call as the state machine expects it."""
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments or {})},
    }


def response(
    content: str = "",
    tool_calls: Optional[Sequence[Dict[str, Any]]] = None,
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> LLMResponse:
    return LLMResponse(
        content=content,
        tool_calls=list(tool_calls or []),
        finish_reason="tool_calls" if tool_calls else "stop",
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=prompt_tokens + completion_tokens,
    )


class ProviderRateLimitError(Exception):
    """Mirrors a 429 from an upstream model provider."""

    status_code = 429

    def __init__(self, retry_after: int = 30):
        self.retry_after = retry_after
        super().__init__(f"429 Too Many Requests: rate limit exceeded, retry after {retry_after}s")


class ProviderUnavailableError(Exception):
    """Mirrors a 5xx / connection failure from an upstream model provider."""

    status_code = 503

    def __init__(self, message: str = "503 Service Unavailable: upstream model provider is down"):
        super().__init__(message)


class ScriptedAIProvider(AIProviderInterface):
    """Replays a script of responses; records every prompt it was given."""

    def __init__(
        self,
        script: Optional[Sequence[Union[LLMResponse, Exception]]] = None,
        default: Optional[LLMResponse] = None,
        router: Optional[Callable[[List[LLMMessage]], Optional[LLMResponse]]] = None,
    ):
        self.script: List[Union[LLMResponse, Exception]] = list(script or [])
        self.default = default if default is not None else response(content="Done. No further tool calls required.")
        self.router = router
        self.calls: List[List[LLMMessage]] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def prompts(self) -> List[str]:
        return ["\n".join(m.content for m in messages) for messages in self.calls]

    async def generate_response(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        self.calls.append(list(messages))

        if self.router is not None:
            routed = self.router(messages)
            if routed is not None:
                return routed

        if self.script:
            nxt = self.script.pop(0)
            if isinstance(nxt, Exception):
                raise nxt
            return nxt
        return self.default

    async def stream_response(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        result = await self.generate_response(messages, tools, model, temperature, max_tokens)
        for chunk in result.content.split(" "):
            yield chunk + " "


class FailingAIProvider(AIProviderInterface):
    """Always raises - models total provider outage."""

    def __init__(self, error: Optional[Exception] = None):
        self.error = error or ProviderUnavailableError()
        self.call_count = 0

    async def generate_response(self, messages, tools=None, model=None, temperature=0.2, max_tokens=4096):
        self.call_count += 1
        raise self.error

    async def stream_response(self, messages, tools=None, model=None, temperature=0.2, max_tokens=4096):
        self.call_count += 1
        raise self.error
        yield ""  # pragma: no cover


class RateLimitedAIProvider(AIProviderInterface):
    """Raises 429 for the first ``fail_times`` calls, then succeeds."""

    def __init__(self, fail_times: int = 1, success: Optional[LLMResponse] = None):
        self.fail_times = fail_times
        self.success = success or response(content="recovered after rate limit")
        self.call_count = 0

    async def generate_response(self, messages, tools=None, model=None, temperature=0.2, max_tokens=4096):
        self.call_count += 1
        if self.call_count <= self.fail_times:
            raise ProviderRateLimitError()
        return self.success

    async def stream_response(self, messages, tools=None, model=None, temperature=0.2, max_tokens=4096):
        yield (await self.generate_response(messages, tools, model, temperature, max_tokens)).content


class SlowAIProvider(AIProviderInterface):
    """Sleeps before responding - drives execution-time limit handling."""

    def __init__(self, delay_seconds: float = 2.0, result: Optional[LLMResponse] = None):
        self.delay_seconds = delay_seconds
        self.result = result or response(content="slow response")
        self.call_count = 0

    async def generate_response(self, messages, tools=None, model=None, temperature=0.2, max_tokens=4096):
        self.call_count += 1
        await asyncio.sleep(self.delay_seconds)
        return self.result

    async def stream_response(self, messages, tools=None, model=None, temperature=0.2, max_tokens=4096):
        yield (await self.generate_response(messages, tools, model, temperature, max_tokens)).content
