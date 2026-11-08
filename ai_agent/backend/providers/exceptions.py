class ProviderUnavailableError(Exception):
    """Raised when a provider is temporarily unavailable."""


class ProviderQuotaExceededError(ProviderUnavailableError):
    """Raised when a provider's quota or rate limit is exceeded."""