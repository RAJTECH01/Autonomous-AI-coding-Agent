from typing import List, Dict, Any, Optional, AsyncIterator
import anthropic
from app.domain.interfaces.ai_provider import AIProviderInterface, LLMMessage, LLMResponse
from app.core.config import settings
from app.core.logging import logger


class AnthropicProviderAdapter(AIProviderInterface):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.ANTHROPIC_API_KEY
        self.client = anthropic.AsyncAnthropic(api_key=self.api_key)

    async def generate_response(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        selected_model = model or "claude-3-5-sonnet-20241022"
        
        system_prompt = ""
        formatted_messages = []
        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            else:
                formatted_messages.append({
                    "role": "user" if msg.role == "user" else "assistant",
                    "content": msg.content
                })

        kwargs: Dict[str, Any] = {
            "model": selected_model,
            "messages": formatted_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        logger.info("Anthropic request", model=selected_model, message_count=len(formatted_messages))
        response = await self.client.messages.create(**kwargs)
        
        content_text = ""
        tool_calls = []
        for block in response.content:
            if block.type == "text":
                content_text += block.text
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": block.input
                    }
                })

        return LLMResponse(
            content=content_text,
            tool_calls=tool_calls,
            finish_reason=response.stop_reason or "stop",
            prompt_tokens=response.usage.input_tokens,
            completion_tokens=response.usage.output_tokens,
            total_tokens=response.usage.input_tokens + response.usage.output_tokens,
        )

    async def stream_response(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        selected_model = model or "claude-3-5-sonnet-20241022"
        system_prompt = ""
        formatted_messages = []
        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
            else:
                formatted_messages.append({
                    "role": "user" if msg.role == "user" else "assistant",
                    "content": msg.content
                })

        kwargs: Dict[str, Any] = {
            "model": selected_model,
            "messages": formatted_messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        async with self.client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                yield text
