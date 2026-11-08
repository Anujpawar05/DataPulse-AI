from groq import (
    Groq,
    RateLimitError,
    InternalServerError,
    APIConnectionError,
)
from ai_agent.backend.config import GROQ_API_KEY, GROQ_MODEL
from ai_agent.backend.config import GROQ_API_KEY
from ai_agent.backend.providers.base import BaseLLMProvider
from ai_agent.backend.providers.exceptions import (
    ProviderUnavailableError,
    ProviderQuotaExceededError,
)


class GroqProvider(BaseLLMProvider):

    def __init__(self):
        if not GROQ_API_KEY:
            raise ValueError("Groq API key is not configured.")

        self.client = Groq(api_key=GROQ_API_KEY)

    def generate_response(self, prompt: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "user", "content": prompt}
                ],
            )

            return response.choices[0].message.content or ""

        except RateLimitError as exc:
            raise ProviderQuotaExceededError(
                "Groq quota or rate limit exceeded."
            ) from exc

        except (InternalServerError, APIConnectionError) as exc:
            raise ProviderUnavailableError(
                "Groq service is temporarily unavailable."
            ) from exc
