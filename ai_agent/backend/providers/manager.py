import time

from ai_agent.backend.config import (
    AI_PRIMARY_PROVIDER,
    AI_SECONDARY_PROVIDER,
    AI_LOCAL_PROVIDER,
)

from ai_agent.backend.providers.gemini_provider import GeminiProvider
from ai_agent.backend.providers.groq_provider import GroqProvider
from ai_agent.backend.providers.ollama_provider import OllamaProvider
from ai_agent.backend.providers.exceptions import ProviderUnavailableError
from ai_agent.backend.logger import get_logger, get_request_id

logger = get_logger("providers")

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
        total_providers = len(self.provider_order)

        for idx, provider_name in enumerate(self.provider_order):
            provider_class = PROVIDER_MAP.get(provider_name)
            next_provider = (
                self.provider_order[idx + 1]
                if idx + 1 < total_providers
                else "none"
            )

            if provider_class is None:
                errors.append(f"{provider_name}: unsupported provider")
                logger.warning(
                    f"[{get_request_id()}] AI provider {provider_name} is unsupported; initiating fallback to {next_provider}",
                    extra={
                        "event": "provider_fallback",
                        "failed_provider": provider_name,
                        "error_class": "UnsupportedProvider",
                        "next_provider": next_provider,
                    },
                )
                continue

            logger.info(
                f"[{get_request_id()}] AI provider attempt {idx + 1}/{total_providers}: {provider_name}",
                extra={
                    "event": "provider_attempt",
                    "provider": provider_name,
                    "attempt": idx + 1,
                    "total_providers": total_providers,
                },
            )

            try:
                provider = provider_class()
            except ValueError as exc:
                exc_class = type(exc).__name__
                errors.append(f"{provider_name}: {exc_class}")
                logger.warning(
                    f"[{get_request_id()}] AI provider {provider_name} initialization failed ({exc_class}); initiating fallback to {next_provider}",
                    extra={
                        "event": "provider_fallback",
                        "failed_provider": provider_name,
                        "error_class": exc_class,
                        "next_provider": next_provider,
                    },
                )
                continue

            start_time = time.perf_counter()
            try:
                response = provider.generate_response(prompt)
                duration_ms = (time.perf_counter() - start_time) * 1000
                logger.info(
                    f"[{get_request_id()}] AI provider {provider_name} succeeded ({duration_ms:.1f}ms)",
                    extra={
                        "event": "provider_success",
                        "provider": provider_name,
                        "duration_ms": duration_ms,
                    },
                )
                return response

            except ProviderUnavailableError as exc:
                duration_ms = (time.perf_counter() - start_time) * 1000
                exc_class = type(exc).__name__
                errors.append(f"{provider_name}: {exc_class}")
                logger.warning(
                    f"[{get_request_id()}] AI provider {provider_name} failed ({exc_class}) after {duration_ms:.1f}ms; initiating fallback to {next_provider}",
                    extra={
                        "event": "provider_fallback",
                        "failed_provider": provider_name,
                        "error_class": exc_class,
                        "duration_ms": duration_ms,
                        "next_provider": next_provider,
                    },
                )
                continue

        logger.error(
            f"[{get_request_id()}] All AI providers exhausted ({total_providers} attempted: {', '.join(self.provider_order)})",
            extra={
                "event": "providers_exhausted",
                "total_attempted": total_providers,
                "attempted_providers": list(self.provider_order),
            },
        )
        raise RuntimeError(
            "All AI providers are currently unavailable. "
            + "; ".join(errors)
        )