from unittest.mock import patch

import pytest

from ai_agent.backend.providers.manager import ProviderManager
from ai_agent.backend.providers.exceptions import (
    ProviderUnavailableError,
    ProviderQuotaExceededError,
)


def test_gemini_success():
    manager = ProviderManager()

    with patch(
        "ai_agent.backend.providers.manager.PROVIDER_MAP",
        {"gemini": lambda: MockProvider("Gemini response")},
    ):
        result = manager.generate_response("Test prompt")

    assert result == "Gemini response"


def test_fallback_to_groq():
    manager = ProviderManager()

    with patch(
        "ai_agent.backend.providers.manager.PROVIDER_MAP",
        {
            "gemini": lambda: FailingProvider(),
            "groq": lambda: MockProvider("Groq response"),
        },
    ):
        result = manager.generate_response("Test prompt")

    assert result == "Groq response"


def test_fallback_to_ollama():
    manager = ProviderManager()

    with patch(
        "ai_agent.backend.providers.manager.PROVIDER_MAP",
        {
            "gemini": lambda: FailingProvider(),
            "groq": lambda: FailingProvider(),
            "ollama": lambda: MockProvider("Ollama response"),
        },
    ):
        result = manager.generate_response("Test prompt")

    assert result == "Ollama response"


class MockProvider:
    def __init__(self, response):
        self.response = response

    def generate_response(self, prompt):
        return self.response


class FailingProvider:
    def generate_response(self, prompt):
        raise ProviderUnavailableError("Simulated failure")


def test_quota_error_triggers_fallback():
    manager = ProviderManager()

    with patch(
        "ai_agent.backend.providers.manager.PROVIDER_MAP",
        {
            "gemini": lambda: QuotaFailingProvider(),
            "groq": lambda: MockProvider("Groq response"),
        },
    ):
        result = manager.generate_response("Test prompt")

    assert result == "Groq response"


class QuotaFailingProvider:
    def generate_response(self, prompt):
        raise ProviderQuotaExceededError("Simulated quota exhaustion")


def test_unexpected_error_is_not_silently_hidden():
    manager = ProviderManager()

    with patch(
        "ai_agent.backend.providers.manager.PROVIDER_MAP",
        {"gemini": lambda: UnexpectedFailingProvider()},
    ):
        with pytest.raises(ValueError):
            manager.generate_response("Test prompt")


class UnexpectedFailingProvider:
    def generate_response(self, prompt):
        raise ValueError("Simulated programming error")


def test_missing_api_key_triggers_fallback():
    manager = ProviderManager()

    with patch(
        "ai_agent.backend.providers.manager.PROVIDER_MAP",
        {
            "gemini": lambda: MissingKeyProvider(),
            "groq": lambda: MockProvider("Groq response"),
        },
    ):
        result = manager.generate_response("Test prompt")

    assert result == "Groq response"


class MissingKeyProvider:
    def __init__(self):
        raise ValueError("Gemini API key is not configured.")