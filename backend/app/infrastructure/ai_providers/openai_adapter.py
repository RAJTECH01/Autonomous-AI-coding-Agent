from typing import List, Dict, Any, Optional, AsyncIterator
import openai
from app.domain.interfaces.ai_provider import AIProviderInterface, LLMMessage, LLMResponse
from app.core.config import settings
from app.core.logging import logger


class OpenAIProviderAdapter(AIProviderInterface):
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.OPENAI_API_KEY
        self.client = openai.AsyncOpenAI(api_key=self.api_key)

    async def generate_response(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        selected_model = model or "gpt-4o"
        
        formatted_messages = []
        for msg in messages:
            item = {"role": msg.role, "content": msg.content}
            if msg.tool_calls:
                item["tool_calls"] = msg.tool_calls
            if msg.tool_call_id:
                item["tool_call_id"] = msg.tool_call_id
            formatted_messages.append(item)

        kwargs: Dict[str, Any] = {
            "model": selected_model,
            "messages": formatted_messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools:
            kwargs["tools"] = tools

        logger.info("OpenAI request", model=selected_model, message_count=len(messages))
        response = await self.client.chat.completions.create(**kwargs)
        choice = response.choices[0]
        
        tool_calls_data = []
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                tool_calls_data.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments
                    }
                })

        usage = response.usage
        return LLMResponse(
            content=choice.message.content or "",
            tool_calls=tool_calls_data,
            finish_reason=choice.finish_reason or "stop",
            prompt_tokens=usage.prompt_tokens if usage else 0,
            completion_tokens=usage.completion_tokens if usage else 0,
            total_tokens=usage.total_tokens if usage else 0,
        )

    async def stream_response(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> AsyncIterator[str]:
        selected_model = model or "gpt-4o"
        formatted_messages = [{"role": m.role, "content": m.content} for m in messages]

        stream = await self.client.chat.completions.create(
            model=selected_model,
            messages=formatted_messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )

        async for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
