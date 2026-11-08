from google import genai
from google.genai import errors
from ai_agent.backend.config import GEMINI_API_KEY, GEMINI_MODEL
from ai_agent.backend.config import GEMINI_API_KEY
from ai_agent.backend.providers.base import BaseLLMProvider
from ai_agent.backend.providers.exceptions import (
    ProviderUnavailableError,
    ProviderQuotaExceededError,
)


class GeminiProvider(BaseLLMProvider):

    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError("Gemini API key is not configured.")

        self.client = genai.Client(api_key=GEMINI_API_KEY)

    def generate_response(self, prompt: str) -> str:
        try:
            response = self.client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
            )

            return response.text or ""

        except errors.ClientError as exc:
            if exc.code == 429:
                raise ProviderQuotaExceededError(
                    "Gemini quota or rate limit exceeded."
                ) from exc
            raise

        except errors.ServerError as exc:
            raise ProviderUnavailableError(
                "Gemini service is temporarily unavailable."
            ) from exc