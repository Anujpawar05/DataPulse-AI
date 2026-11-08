from ai_agent.backend.config import (
    AI_PRIMARY_PROVIDER,
    AI_SECONDARY_PROVIDER,
    AI_LOCAL_PROVIDER,
)

from ai_agent.backend.providers.gemini_provider import GeminiProvider
from ai_agent.backend.providers.groq_provider import GroqProvider
from ai_agent.backend.providers.ollama_provider import OllamaProvider
from ai_agent.backend.providers.exceptions import ProviderUnavailableError

PROVIDER_MAP = {
    "gemini": GeminiProvider,
    "groq": GroqProvider,
    "ollama": OllamaProvider,
}


class ProviderManager:

    def __init__(self):
        self.provider_order = [
            AI_PRIMARY_PROVIDER,
            AI_SECONDARY_PROVIDER,
            AI_LOCAL_PROVIDER,
        ]

    def generate_response(self, prompt: str) -> str:
        errors = []

        for provider_name in self.provider_order:
            provider_class = PROVIDER_MAP.get(provider_name)

            if provider_class is None:
                errors.append(f"{provider_name}: unsupported provider")
                continue

            try:
                provider = provider_class()
            except ValueError as exc:
                errors.append(f"{provider_name}: {type(exc).__name__}")
                continue

            try:
                return provider.generate_response(prompt)

            except ProviderUnavailableError as exc:
                errors.append(f"{provider_name}: {type(exc).__name__}")
                continue
        raise RuntimeError(
            "All AI providers are currently unavailable. "
            + "; ".join(errors)
        )