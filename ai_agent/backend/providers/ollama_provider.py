import requests
from ai_agent.backend.config import OLLAMA_BASE_URL, OLLAMA_MODEL
from ai_agent.backend.providers.base import BaseLLMProvider
from ai_agent.backend.providers.exceptions import ProviderUnavailableError

class OllamaProvider(BaseLLMProvider):

    def __init__(self, model: str = OLLAMA_MODEL):
        self.model = model
        self.base_url = OLLAMA_BASE_URL.rstrip("/")

    def generate_response(self, prompt: str) -> str:
        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "stream": False,
                },
                timeout=120,
            )

            response.raise_for_status()
            return response.json().get("response", "")

        except requests.RequestException as exc:
            raise ProviderUnavailableError(
                "Ollama is currently unavailable."
            ) from exc