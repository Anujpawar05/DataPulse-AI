from abc import ABC, abstractmethod


class BaseLLMProvider(ABC):

    @abstractmethod
    def generate_response(self, prompt: str) -> str:
        """Generate a response from the supplied prompt."""
        raise NotImplementedError