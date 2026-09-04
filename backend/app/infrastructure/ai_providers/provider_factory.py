from typing import Optional
from app.domain.interfaces.ai_provider import AIProviderInterface
from app.infrastructure.ai_providers.openai_adapter import OpenAIProviderAdapter
from app.infrastructure.ai_providers.anthropic_adapter import AnthropicProviderAdapter
from app.core.config import settings
from app.core.exceptions import ConfigurationError


class AIProviderFactory:
    @staticmethod
    def get_provider(provider_name: Optional[str] = None) -> AIProviderInterface:
        provider = (provider_name or settings.DEFAULT_AI_PROVIDER).lower()

        if provider == "openai":
            return OpenAIProviderAdapter()
        elif provider == "anthropic":
            return AnthropicProviderAdapter()
        else:
            # Fallback / Default
            return AnthropicProviderAdapter()
