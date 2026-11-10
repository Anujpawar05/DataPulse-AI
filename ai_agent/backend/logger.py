import contextvars
import logging
import sys
from typing import Optional

from ai_agent.backend.config import LOG_LEVEL

LOGGER_NAME = "ai_agent"
DEFAULT_LOG_FORMAT = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
DEFAULT_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_request_id_ctx: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "request_id", default=None
)


def set_current_request_id(request_id: Optional[str]) -> contextvars.Token:
    """Sets the request ID in the current execution context."""
    return _request_id_ctx.set(request_id)


def reset_current_request_id(token: contextvars.Token) -> None:
    """Resets the request ID in the current execution context."""
    _request_id_ctx.reset(token)


def get_current_request_id(default: str = "-") -> str:
    """Returns the active request ID, or the default fallback if unset."""
    val = _request_id_ctx.get()
    return val if val else default


# Aliases for caller convenience
set_request_id = set_current_request_id
reset_request_id = reset_current_request_id
get_request_id = get_current_request_id


def setup_logger(name: str = LOGGER_NAME, level: Optional[str] = None) -> logging.Logger:
    """
    Configures and returns a dedicated application logger.
    Outputs to sys.stdout with timestamp, level, logger name, and message.
    Prevents duplicate handlers on repeated calls.
    """
    logger = logging.getLogger(name)
    target_level = level or LOG_LEVEL
    log_level = getattr(logging, target_level.upper(), logging.INFO)
    logger.setLevel(log_level)

    # Avoid adding duplicate handlers if already configured
    has_stdout_handler = any(
        isinstance(h, logging.StreamHandler) and getattr(h, "stream", None) == sys.stdout
        for h in logger.handlers
    )

    if not has_stdout_handler:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(logging.DEBUG)  # Let logger.setLevel control filtering
        formatter = logging.Formatter(
            fmt=DEFAULT_LOG_FORMAT,
            datefmt=DEFAULT_DATE_FORMAT,
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    # Prevent bubbling up to the root logger to avoid duplicate log entries
    logger.propagate = False
    return logger


def get_logger(child_name: Optional[str] = None) -> logging.Logger:
    """
    Retrieves the application logger or a namespaced child logger under 'ai_agent'.
    """
    setup_logger()
    if child_name:
        return logging.getLogger(f"{LOGGER_NAME}.{child_name}")
    return logging.getLogger(LOGGER_NAME)
