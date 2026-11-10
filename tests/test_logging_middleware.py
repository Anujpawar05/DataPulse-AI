import logging
import uuid
import pytest
from fastapi.testclient import TestClient

from ai_agent.backend.main import app
from ai_agent.backend.logger import setup_logger, get_logger


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_request_id_generated_when_missing(client):
    """Verify X-Request-ID is generated and returned when none is supplied."""
    response = client.get("/health")
    assert response.status_code == 200
    assert "x-request-id" in response.headers
    req_id = response.headers["x-request-id"]
    # Check that it is a valid UUID
    parsed = uuid.UUID(req_id)
    assert str(parsed) == req_id


def test_valid_incoming_request_id_propagated(client):
    """Verify a valid incoming X-Request-ID is preserved and returned."""
    custom_id = "test-custom-trace_12345"
    response = client.get("/health", headers={"X-Request-ID": custom_id})
    assert response.status_code == 200
    assert response.headers.get("x-request-id") == custom_id


@pytest.mark.parametrize(
    "invalid_id",
    [
        "a" * 37,  # Oversized (> 36 chars)
        "invalid id with spaces",  # Disallowed characters
        "req\ninjected-header",  # Newline injection attempt
        "req\r\ninjected",  # CRLF injection attempt
        "id_with_special!@#$",  # Special characters
        "",  # Empty string
    ],
)
def test_invalid_or_oversized_request_id_replaced(client, invalid_id):
    """Verify invalid or oversized request IDs are safely replaced with a valid UUID."""
    response = client.get("/health", headers={"X-Request-ID": invalid_id})
    assert response.status_code == 200
    req_id = response.headers.get("x-request-id")
    assert req_id != invalid_id
    # Must be a valid UUID
    parsed = uuid.UUID(req_id)
    assert str(parsed) == req_id


def test_request_logging_contains_metadata(client, caplog):
    """Verify request logs contain method, path, status code, and duration in ms."""
    with caplog.at_level(logging.INFO, logger="ai_agent.request"):
        custom_id = "meta-log-test-123"
        response = client.get("/health", headers={"X-Request-ID": custom_id})
        assert response.status_code == 200

    matching_records = [
        r for r in caplog.records
        if r.name == "ai_agent.request" and custom_id in r.message
    ]
    assert len(matching_records) == 1
    record = matching_records[0]
    assert record.levelname == "INFO"
    assert f"[{custom_id}] GET /health - 200" in record.message
    assert "ms)" in record.message


def test_unhandled_exception_sanitized_500_and_logged(client, caplog):
    """Verify unhandled exceptions log the error safely with request ID and return a sanitized 500 response."""
    def mock_crash():
        raise RuntimeError("simulated internal error")

    target_route = None
    orig_call = None
    for route in app.router.routes:
        if getattr(route, "path", None) == "/health":
            target_route = route
            orig_call = route.dependant.call
            route.dependant.call = mock_crash
            break

    assert target_route is not None

    custom_id = "crash-trace-999"
    try:
        with caplog.at_level(logging.ERROR, logger="ai_agent.request"):
            response = client.get("/health", headers={"X-Request-ID": custom_id})
    finally:
        target_route.dependant.call = orig_call

    assert response.status_code == 500
    assert response.headers.get("x-request-id") == custom_id

    body = response.json()
    assert body == {
        "detail": "Internal Server Error",
        "request_id": custom_id,
    }
    # Raw exception message must not be leaked in the response body
    assert "simulated internal error" not in response.text

    # Log record must contain the request ID, method, path, exception class name, duration, and diagnostic message
    error_records = [
        r for r in caplog.records
        if r.name == "ai_agent.request" and custom_id in r.message
    ]
    assert len(error_records) == 1
    err_record = error_records[0]
    assert err_record.levelname == "ERROR"
    assert f"[{custom_id}] Unhandled RuntimeError processing GET /health" in err_record.message
    assert "An unexpected internal error occurred during request processing." in err_record.message
    # Traceback should include useful context (file, line, function) without raw exception message
    assert "mock_crash" in err_record.message
    assert "RuntimeError: [Internal exception details sanitized]" in err_record.message
    # Raw exception message must NOT be in the log message
    assert "simulated internal error" not in err_record.message


def test_simulated_exception_with_secret_marker_not_in_logs(client, caplog):
    """
    Verify simulated exception containing credentials, connection strings, or SQL parameters
    does not leak the secret marker in ordinary log messages or in the traceback.
    """
    secret_marker = "SUPER_SECRET_DB_PASSWORD_XYZ_98765"
    connection_string = f"postgresql://dbadmin:{secret_marker}@10.0.0.5:5432/datapulse"

    def mock_secret_crash():
        raise ConnectionRefusedError(f"Connection failed: {connection_string}")

    target_route = None
    orig_call = None
    for route in app.router.routes:
        if getattr(route, "path", None) == "/health":
            target_route = route
            orig_call = route.dependant.call
            route.dependant.call = mock_secret_crash
            break

    assert target_route is not None

    custom_id = "secret-leak-test-777"
    try:
        with caplog.at_level(logging.ERROR, logger="ai_agent.request"):
            response = client.get("/health", headers={"X-Request-ID": custom_id})
    finally:
        target_route.dependant.call = orig_call

    assert response.status_code == 500
    assert response.headers.get("x-request-id") == custom_id

    # Response must not contain the secret or raw exception details
    assert secret_marker not in response.text
    assert "ConnectionRefusedError" not in response.text
    assert response.json() == {
        "detail": "Internal Server Error",
        "request_id": custom_id,
    }

    # Captured logs must NOT contain the secret marker, connection string, or raw exception message
    assert secret_marker not in caplog.text
    assert "dbadmin" not in caplog.text
    assert "10.0.0.5" not in caplog.text
    assert "Connection failed" not in caplog.text

    # Useful error context must remain available
    err_records = [
        r for r in caplog.records
        if r.name == "ai_agent.request" and custom_id in r.message
    ]
    assert len(err_records) == 1
    err_msg = err_records[0].message
    assert "Unhandled ConnectionRefusedError" in err_msg
    assert "GET /health" in err_msg
    assert "mock_secret_crash" in err_msg
    assert "ConnectionRefusedError: [Internal exception details sanitized]" in err_msg


def test_sensitive_headers_not_logged(client, caplog):
    """Verify sensitive authorization headers, cookies, and tokens are never logged."""
    with caplog.at_level(logging.INFO, logger="ai_agent.request"):
        secret_token = "Bearer sensitive-api-key-xyz-12345"
        secret_cookie = "session_token=secret_cookie_val_9999"
        response = client.get(
            "/health",
            headers={
                "Authorization": secret_token,
                "Cookie": secret_cookie,
                "X-Custom-Secret": "super-confidential",
            },
        )
        assert response.status_code == 200

    log_text = caplog.text
    assert secret_token not in log_text
    assert "sensitive-api-key" not in log_text
    assert secret_cookie not in log_text
    assert "super-confidential" not in log_text


def test_handled_http_errors_preserve_status_and_format(client):
    """Verify handled HTTP errors (e.g. 422, 400) preserve their status codes and response bodies."""
    # POST to /ask with question shorter than min_length=3 triggers 422
    response = client.post(
        "/ask",
        json={"question": "hi"},
        headers={"X-Request-ID": "validation-err-id"},
    )
    assert response.status_code == 422
    assert response.headers.get("x-request-id") == "validation-err-id"
    body = response.json()
    assert "detail" in body


def test_logger_setup_idempotency_and_level_fallback():
    """Verify logger setup avoids duplicate handlers and handles invalid levels gracefully."""
    logger1 = setup_logger("test_app_logger", level="INVALID_LEVEL_NAME")
    # Should fall back to INFO level without crashing
    assert logger1.level == logging.INFO
    handler_count = len(logger1.handlers)

    # Calling setup again should not add duplicate handlers
    logger2 = setup_logger("test_app_logger", level="DEBUG")
    assert len(logger2.handlers) == handler_count
    assert logger2.level == logging.DEBUG
