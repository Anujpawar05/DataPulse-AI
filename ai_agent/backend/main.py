import re
import time
import traceback
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ai_agent.backend.logger import (
    get_logger,
    setup_logger,
    set_current_request_id,
    reset_current_request_id,
)
from ai_agent.backend.health import get_readiness_report
from ai_agent.backend.routes.ask import router as ask_router
from ai_agent.backend.routes.analytics import router as analytics_router

# Initialize centralized application logging
setup_logger()
logger = get_logger("request")

REQUEST_ID_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,36}$")

app = FastAPI(
    title="DataPulse AI",
    description="AI-powered business intelligence assistant",
    version="1.0.0",
)


def _format_safe_traceback(exc: Exception) -> str:
    """
    Format call stack frames (filename, line number, function name)
    without source lines or raw exception message values to prevent
    credential, token, connection string, or SQL parameter leaks in logs.
    """
    tb = exc.__traceback__
    if not tb:
        return ""
    frames = traceback.extract_tb(tb)
    lines = ["Traceback (sanitized, most recent call last):"]
    for frame in frames:
        lines.append(f'  File "{frame.filename}", line {frame.lineno}, in {frame.name}')
    lines.append(f"{type(exc).__name__}: [Internal exception details sanitized]")
    return "\n".join(lines)


# Global unhandled exception handler
@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    start_time = getattr(request.state, "start_time", None)
    duration_str = ""
    if start_time is not None:
        duration_ms = (time.perf_counter() - start_time) * 1000
        duration_str = f" ({duration_ms:.1f}ms)"

    exc_class = type(exc).__name__
    safe_diagnostic = "An unexpected internal error occurred during request processing."

    log_message = (
        f"[{request_id}] Unhandled {exc_class} processing {request.method} {request.url.path}{duration_str}: "
        f"{safe_diagnostic}"
    )

    safe_tb = _format_safe_traceback(exc)
    if safe_tb:
        log_message = f"{log_message}\n{safe_tb}"

    logger.error(log_message)

    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal Server Error",
            "request_id": request_id,
        },
        headers={"X-Request-ID": request_id},
    )


# Request logging middleware
@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    raw_id = request.headers.get("X-Request-ID")
    if raw_id and REQUEST_ID_REGEX.match(raw_id):
        request_id = raw_id
    else:
        request_id = str(uuid.uuid4())

    request.state.request_id = request_id
    request.state.start_time = time.perf_counter()

    token = set_current_request_id(request_id)
    try:
        response = await call_next(request)
    finally:
        reset_current_request_id(token)

    duration_ms = (time.perf_counter() - request.state.start_time) * 1000
    logger.info(
        f"[{request_id}] {request.method} {request.url.path} - {response.status_code} ({duration_ms:.1f}ms)"
    )
    response.headers["X-Request-ID"] = request_id
    return response


# CORS configuration for local frontend development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5500",
        "http://localhost:5500",
        "http://127.0.0.1:8080",
        "http://localhost:8080",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["Content-Type", "Accept", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)


@app.get("/")
def root():
    return {
        "message": "Welcome to DataPulse AI",
        "status": "running",
        "version": "1.0.0",
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "DataPulse AI Agent",
    }


@app.get("/health/ready")
def readiness_check():
    status_code, report = get_readiness_report()
    return JSONResponse(status_code=status_code, content=report)


app.include_router(ask_router)
app.include_router(analytics_router)
