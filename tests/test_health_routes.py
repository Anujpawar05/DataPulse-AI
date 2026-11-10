from datetime import datetime
import pytest
from fastapi.testclient import TestClient

from ai_agent.backend.main import app
from ai_agent.backend import health


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=False)


def test_existing_health_liveness_endpoint_unchanged(client):
    """Verify GET /health remains an unchanged, lightweight liveness probe."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.headers.get("content-type") == "application/json"
    assert "x-request-id" in response.headers
    assert response.json() == {
        "status": "healthy",
        "service": "DataPulse AI Agent",
    }


def test_readiness_all_components_healthy(client, monkeypatch):
    """Verify GET /health/ready returns 200 and 'ready' when all components are healthy."""
    monkeypatch.setattr(
        health,
        "check_sqlite_readiness",
        lambda: {"status": "ok", "latency_ms": 0.45, "connected": True, "read_ready": True},
    )
    monkeypatch.setattr(
        health,
        "check_bigquery_readiness",
        lambda: {"status": "ok", "latency_ms": 110.2},
    )
    monkeypatch.setattr(
        health,
        "check_ai_providers_readiness",
        lambda: {
            "status": "ok",
            "active_provider": "gemini",
            "configured_providers": ["gemini", "groq", "ollama"],
            "runtime_verified_providers": ["ollama"],
            "fallback_available": True,
        },
    )

    response = client.get("/health/ready")
    assert response.status_code == 200
    assert "x-request-id" in response.headers

    data = response.json()
    assert data["status"] == "ready"
    assert "timestamp" in data
    # Verify ISO timestamp format
    datetime.fromisoformat(data["timestamp"].replace("Z", "+00:00"))

    comps = data["components"]
    assert comps["sqlite"]["status"] == "ok"
    assert comps["sqlite"]["connected"] is True
    assert comps["sqlite"]["read_ready"] is True
    assert comps["sqlite"]["latency_ms"] == 0.45

    assert comps["bigquery"]["status"] == "ok"
    assert comps["bigquery"]["latency_ms"] == 110.2

    assert comps["ai_providers"]["status"] == "ok"
    assert comps["ai_providers"]["active_provider"] == "gemini"
    assert comps["ai_providers"]["fallback_available"] is True


def test_readiness_ai_degraded_returns_200(client, monkeypatch):
    """Verify backend remains ready (HTTP 200) with status 'degraded' when primary AI is down but secondary is ready."""
    monkeypatch.setattr(
        health,
        "check_sqlite_readiness",
        lambda: {"status": "ok", "latency_ms": 0.3, "connected": True, "read_ready": True},
    )
    monkeypatch.setattr(
        health,
        "check_bigquery_readiness",
        lambda: {"status": "ok", "latency_ms": 105.0},
    )
    monkeypatch.setattr(
        health,
        "check_ai_providers_readiness",
        lambda: {
            "status": "degraded",
            "active_provider": "groq",
            "configured_providers": ["groq", "ollama"],
            "runtime_verified_providers": [],
            "fallback_available": True,
        },
    )

    response = client.get("/health/ready")
    assert response.status_code == 200
    assert "x-request-id" in response.headers

    data = response.json()
    assert data["status"] == "degraded"
    assert data["components"]["sqlite"]["status"] == "ok"
    assert data["components"]["bigquery"]["status"] == "ok"
    assert data["components"]["ai_providers"]["status"] == "degraded"
    assert data["components"]["ai_providers"]["active_provider"] == "groq"


def test_readiness_no_ai_providers_returns_200_degraded(client, monkeypatch):
    """Verify backend returns 200 'degraded' and explicitly marks AI as unavailable when zero AI providers exist."""
    monkeypatch.setattr(
        health,
        "check_sqlite_readiness",
        lambda: {"status": "ok", "latency_ms": 0.3, "connected": True, "read_ready": True},
    )
    monkeypatch.setattr(
        health,
        "check_bigquery_readiness",
        lambda: {"status": "ok", "latency_ms": 95.0},
    )
    monkeypatch.setattr(
        health,
        "check_ai_providers_readiness",
        lambda: {
            "status": "unavailable",
            "active_provider": None,
            "configured_providers": [],
            "runtime_verified_providers": [],
            "fallback_available": False,
            "detail": "No AI providers configured; rule-based fallback active",
        },
    )

    response = client.get("/health/ready")
    assert response.status_code == 200
    assert "x-request-id" in response.headers

    data = response.json()
    assert data["status"] == "degraded"
    assert data["components"]["ai_providers"]["status"] == "unavailable"
    assert data["components"]["ai_providers"]["active_provider"] is None
    assert "rule-based fallback active" in data["components"]["ai_providers"]["detail"]


def test_readiness_sqlite_failure_returns_503(client, monkeypatch):
    """Verify SQLite storage failure marks the backend as unhealthy with HTTP 503."""
    monkeypatch.setattr(
        health,
        "check_sqlite_readiness",
        lambda: {"status": "unavailable", "error": "Database component is unreachable"},
    )
    monkeypatch.setattr(
        health,
        "check_bigquery_readiness",
        lambda: {"status": "ok", "latency_ms": 115.0},
    )
    monkeypatch.setattr(
        health,
        "check_ai_providers_readiness",
        lambda: {
            "status": "ok",
            "active_provider": "gemini",
            "configured_providers": ["gemini"],
            "runtime_verified_providers": [],
            "fallback_available": False,
        },
    )

    response = client.get("/health/ready")
    assert response.status_code == 503
    assert "x-request-id" in response.headers

    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["components"]["sqlite"]["status"] == "unavailable"
    assert data["components"]["sqlite"]["error"] == "Database component is unreachable"


def test_readiness_bigquery_failure_returns_503(client, monkeypatch):
    """Verify BigQuery connectivity failure marks the backend as unhealthy with HTTP 503."""
    monkeypatch.setattr(
        health,
        "check_sqlite_readiness",
        lambda: {"status": "ok", "latency_ms": 0.2, "connected": True, "read_ready": True},
    )
    monkeypatch.setattr(
        health,
        "check_bigquery_readiness",
        lambda: {"status": "unavailable", "error": "Warehouse dataset is unreachable"},
    )
    monkeypatch.setattr(
        health,
        "check_ai_providers_readiness",
        lambda: {
            "status": "ok",
            "active_provider": "gemini",
            "configured_providers": ["gemini"],
            "runtime_verified_providers": [],
            "fallback_available": False,
        },
    )

    response = client.get("/health/ready")
    assert response.status_code == 503
    assert "x-request-id" in response.headers

    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["components"]["bigquery"]["status"] == "unavailable"
    assert data["components"]["bigquery"]["error"] == "Warehouse dataset is unreachable"


def test_readiness_security_sanitization_no_credentials_leaked(client, monkeypatch):
    """Verify raw exception details, connection strings, and credential secrets are strictly sanitized."""
    secret_marker = "SUPER_SECRET_GCP_PRIVATE_KEY_MARKER_99999"

    class FailingBigQueryClient:
        def get_dataset(self, *args, **kwargs):
            raise RuntimeError(f"GCP IAM failure with key: {secret_marker}")

    # Use actual check_bigquery_readiness implementation with failing client
    orig_bq_check = health.check_bigquery_readiness
    monkeypatch.setattr(
        health,
        "check_sqlite_readiness",
        lambda: {"status": "ok", "latency_ms": 0.3, "connected": True, "read_ready": True},
    )
    monkeypatch.setattr(
        health,
        "check_bigquery_readiness",
        lambda: orig_bq_check(client=FailingBigQueryClient()),
    )

    response = client.get("/health/ready")
    assert response.status_code == 503

    # Must never expose secret in response text
    assert secret_marker not in response.text
    assert "GCP IAM failure" not in response.text
    assert "RuntimeError" not in response.text

    # Must contain generic operational error
    data = response.json()
    assert data["components"]["bigquery"]["status"] == "unavailable"
    assert data["components"]["bigquery"]["error"] == "Warehouse dataset is unreachable"


def test_bounded_timeouts_configuration():
    """Verify diagnostic timeouts are positive, bounded, and do not hang indefinitely."""
    assert 0 < health.SQLITE_TIMEOUT_SECONDS <= 5.0
    assert 0 < health.BIGQUERY_TIMEOUT_SECONDS <= 5.0
    assert 0 < health.OLLAMA_TIMEOUT_SECONDS <= 2.0


def test_bigquery_timeout_handled_gracefully():
    """Verify BigQuery timeout returns sanitized failure without uncaught exception."""
    class TimingOutBigQueryClient:
        def get_dataset(self, *args, **kwargs):
            raise TimeoutError("BigQuery metadata API timed out")

    res = health.check_bigquery_readiness(client=TimingOutBigQueryClient())
    assert res["status"] == "unavailable"
    assert res["error"] == "Warehouse dataset is unreachable"
    assert "TimeoutError" not in res["error"]


def test_direct_sqlite_readiness_healthy_and_corrupt(tmp_path):
    """Verify check_sqlite_readiness directly on a healthy database and a corrupt file."""
    # 1. Healthy database
    healthy_file = tmp_path / "healthy.db"
    res_healthy = health.check_sqlite_readiness(db_path=str(healthy_file))
    assert res_healthy["status"] == "ok"
    assert res_healthy["connected"] is True
    assert res_healthy["read_ready"] is True
    assert res_healthy["latency_ms"] >= 0

    # 2. Corrupt / unreadable database
    corrupt_file = tmp_path / "corrupt.db"
    corrupt_file.write_bytes(b"THIS_IS_NOT_A_VALID_SQLITE3_DATABASE_FILE_HEADER")
    res_corrupt = health.check_sqlite_readiness(db_path=str(corrupt_file))
    assert res_corrupt["status"] == "unavailable"
    assert res_corrupt["error"] == "Database component is unreachable"


def test_ai_provider_readiness_ollama_http_200(monkeypatch):
    """Verify check_ai_providers_readiness marks Ollama as runtime-verified when /api/tags returns 200."""
    import requests

    class MockResponse:
        status_code = 200
        def json(self):
            return {"models": [{"name": "llama3.2:latest"}]}

    monkeypatch.setattr(requests, "get", lambda *args, **kwargs: MockResponse())
    monkeypatch.setattr(health.requests, "get", lambda *args, **kwargs: MockResponse())
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")

    res = health.check_ai_providers_readiness(provider_order=["ollama"])
    assert res["active_provider"] == "ollama"
    assert "ollama" in res["configured_providers"]
    assert "ollama" in res["runtime_verified_providers"]
    assert res["status"] == "ok"


def test_ai_provider_readiness_ollama_request_exception_degrades_gracefully(monkeypatch):
    """Verify check_ai_providers_readiness handles requests.RequestException without raising and omits runtime verification."""
    import requests

    def mock_failing_get(*args, **kwargs):
        raise requests.RequestException("Connection refused connecting to http://localhost:11434/api/tags")

    monkeypatch.setattr(requests, "get", mock_failing_get)
    monkeypatch.setattr(health.requests, "get", mock_failing_get)
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")

    res = health.check_ai_providers_readiness(provider_order=["ollama"])
    assert res["active_provider"] == "ollama"
    assert "ollama" in res["configured_providers"]
    assert "ollama" not in res["runtime_verified_providers"]
    assert res["runtime_verified_providers"] == []
