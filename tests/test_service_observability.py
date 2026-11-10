import asyncio
import logging
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from ai_agent.backend.main import app
from ai_agent.backend.logger import (
    get_logger,
    set_current_request_id,
    reset_current_request_id,
    get_current_request_id,
)
from ai_agent.backend.providers.manager import ProviderManager
from ai_agent.backend.providers.exceptions import (
    ProviderUnavailableError,
    ProviderQuotaExceededError,
)
from ai_agent.backend.analytics.insights_generator import GroundedInsightsGenerator
from ai_agent.backend.analytics.insights_store import InsightsStore
from ai_agent.backend.sql.bigquery_executor import (
    BigQueryExecutor,
    BigQueryExecutionError,
)
from google.api_core.exceptions import BadRequest, Forbidden, GoogleAPICallError


VALID_SQL = """
SELECT SUM(net_amount) AS total_revenue
FROM `winter-sensor-474220-u4.datapulse_marts.fct_sales`
"""


class MockProvider:
    def __init__(self, response: str = "Mocked LLM answer"):
        self.response = response

    def generate_response(self, prompt: str) -> str:
        return self.response


class FailingProvider:
    def __init__(self, exc: Exception = None):
        self.exc = exc or ProviderUnavailableError("Simulated failure")

    def generate_response(self, prompt: str) -> str:
        raise self.exc


# =============================================================================
# 1. Provider Attempt, Success, Fallback, and Exhaustion Logging
# =============================================================================

def test_provider_attempt_and_success_events(caplog):
    """Verify provider attempts and successful completions are logged with timing."""
    manager = ProviderManager()

    with caplog.at_level(logging.INFO, logger="ai_agent.providers"):
        with patch(
            "ai_agent.backend.providers.manager.PROVIDER_MAP",
            {"gemini": lambda: MockProvider("Gemini success")},
        ):
            token = set_current_request_id("test-req-prov-1")
            try:
                res = manager.generate_response("What is net sales?")
            finally:
                reset_current_request_id(token)

    assert res == "Gemini success"

    records = [r for r in caplog.records if r.name == "ai_agent.providers"]
    assert any("AI provider attempt 1/3: gemini" in r.message for r in records)
    assert any("AI provider gemini succeeded" in r.message and "ms)" in r.message for r in records)
    assert any("[test-req-prov-1]" in r.message for r in records)


def test_provider_fallback_chain_events(caplog):
    """Verify failures log warning with error class and next fallback provider."""
    manager = ProviderManager()

    with caplog.at_level(logging.WARNING, logger="ai_agent.providers"):
        with patch(
            "ai_agent.backend.providers.manager.PROVIDER_MAP",
            {
                "gemini": lambda: FailingProvider(ProviderQuotaExceededError("Quota exhausted")),
                "groq": lambda: MockProvider("Groq success"),
                "ollama": lambda: MockProvider("Ollama fallback"),
            },
        ):
            token = set_current_request_id("test-req-fallback-2")
            try:
                res = manager.generate_response("Analyze churn")
            finally:
                reset_current_request_id(token)

    assert res == "Groq success"

    records = [r for r in caplog.records if r.name == "ai_agent.providers"]
    fallback_records = [r for r in records if r.levelname == "WARNING"]
    assert len(fallback_records) >= 1
    fallback_msg = fallback_records[0].message
    assert "AI provider gemini failed (ProviderQuotaExceededError)" in fallback_msg
    assert "initiating fallback to groq" in fallback_msg
    assert "[test-req-fallback-2]" in fallback_msg


def test_providers_exhaustion_events(caplog):
    """Verify error log is emitted when all providers in fallback chain fail."""
    manager = ProviderManager()

    with caplog.at_level(logging.ERROR, logger="ai_agent.providers"):
        with patch(
            "ai_agent.backend.providers.manager.PROVIDER_MAP",
            {
                "gemini": lambda: FailingProvider(ProviderUnavailableError("Gemini down")),
                "groq": lambda: FailingProvider(ProviderUnavailableError("Groq down")),
                "ollama": lambda: FailingProvider(ProviderUnavailableError("Ollama down")),
            },
        ):
            token = set_current_request_id("test-req-exhaust-3")
            try:
                with pytest.raises(RuntimeError) as exc_info:
                    manager.generate_response("Question")
            finally:
                reset_current_request_id(token)

    assert "All AI providers are currently unavailable" in str(exc_info.value)

    error_records = [
        r for r in caplog.records
        if r.name == "ai_agent.providers" and r.levelname == "ERROR"
    ]
    assert len(error_records) == 1
    assert "All AI providers exhausted (3 attempted: gemini, groq, ollama)" in error_records[0].message
    assert "[test-req-exhaust-3]" in error_records[0].message


def test_prompt_and_credential_leakage_prevention(caplog):
    """Verify prompts, API keys, and sensitive tokens are never emitted to provider logs."""
    manager = ProviderManager()
    secret_marker = "SUPER_SECRET_PROMPT_PAYLOAD_987654321"
    credential_marker = "AIzaSy_FAKE_CREDENTIAL_TOKEN_XYZ123"

    with caplog.at_level(logging.DEBUG, logger="ai_agent.providers"):
        with patch(
            "ai_agent.backend.providers.manager.PROVIDER_MAP",
            {
                "gemini": lambda: FailingProvider(ProviderUnavailableError(f"Leaked? {credential_marker}")),
                "groq": lambda: MockProvider("Groq completed"),
            },
        ):
            manager.generate_response(secret_marker)

    for record in caplog.records:
        assert secret_marker not in record.message
        assert credential_marker not in record.message


# =============================================================================
# 2. Deterministic Narrative Fallback Logging
# =============================================================================

def test_insights_generator_logs_deterministic_fallback(tmp_path, caplog):
    """Verify deterministic rule fallback activation is logged with sanitized details."""
    store = InsightsStore(db_path=tmp_path / "obs_insights.db")
    generator = GroundedInsightsGenerator(store=store)

    fact = {
        "category": "revenue_trend",
        "severity": "critical",
        "headline": "Severe Revenue Contraction",
        "observed_fact": "Revenue decreased by 40% vs baseline",
        "metric_name": "net_revenue",
        "observed_value": 30000.0,
        "observed_value_formatted": "₹30,000.00",
        "baseline_value": 50000.0,
        "baseline_value_formatted": "₹50,000.00",
        "change_percentage": -40.0,
        "statistical_score": -3.5,
        "detection_method": "Z-score",
        "period_start": "2026-10-01",
        "period_end": "2026-10-01",
        "warehouse_table": "fct_daily_sales",
        "supporting_sql": "SELECT 1",
        "confidence_score": 0.95,
        "dimension_key": "rev_drop_2026-10-01",
    }

    with caplog.at_level(logging.WARNING, logger="ai_agent.analytics"):
        with patch.object(
            generator.provider_manager,
            "generate_response",
            side_effect=RuntimeError("Simulated LLM failure"),
        ):
            token = set_current_request_id("test-insights-trace-4")
            try:
                insights = generator.process_and_persist_facts([fact], force_llm=True)
            finally:
                reset_current_request_id(token)

    assert len(insights) == 1
    assert insights[0]["ai_provider_used"] == "rule_fallback"

    analytics_records = [
        r for r in caplog.records
        if r.name == "ai_agent.analytics" and r.levelname == "WARNING"
    ]
    assert len(analytics_records) == 1
    msg = analytics_records[0].message
    assert "LLM narrative generation failed (RuntimeError)" in msg
    assert "activating deterministic rule fallback for 1 facts" in msg
    assert "[test-insights-trace-4]" in msg
    # Verify sensitive observed fact details are not in log message
    assert "Revenue decreased by 40%" not in msg


# =============================================================================
# 3. BigQuery Executor Metric Capture and Sanitized Failure Logging
# =============================================================================

def test_bigquery_success_metrics_logged(caplog):
    """Verify execution duration, job ID, rows, and billed bytes are logged on query success."""
    mock_client = MagicMock()
    mock_job = MagicMock()
    mock_job.job_id = "bq_job_success_998877"
    mock_job.total_bytes_billed = 10485760  # 10 MB
    mock_job.total_bytes_processed = 20971520  # 20 MB
    mock_job.slot_millis = 145

    mock_row = MagicMock()
    mock_row.items.return_value = [("total_revenue", 99999.0)]
    mock_job.result.return_value = [mock_row]
    mock_client.query.return_value = mock_job

    executor = BigQueryExecutor(client=mock_client)

    with caplog.at_level(logging.INFO, logger="ai_agent.bigquery"):
        token = set_current_request_id("test-bq-success-5")
        try:
            results = executor.execute_read_only_query(VALID_SQL)
        finally:
            reset_current_request_id(token)

    assert results == [{"total_revenue": 99999.0}]

    bq_records = [
        r for r in caplog.records
        if r.name == "ai_agent.bigquery" and r.levelname == "INFO"
    ]
    assert len(bq_records) == 1
    msg = bq_records[0].message
    assert "BigQuery query completed" in msg
    assert "job_id=bq_job_success_998877" in msg
    assert "rows=1" in msg
    assert "bytes_billed=10485760" in msg
    assert "bytes_processed=20971520" in msg
    assert "slot_ms=145" in msg
    assert "[test-bq-success-5]" in msg


@pytest.mark.parametrize(
    "api_exception, expected_error_class",
    [
        (TimeoutError("Client timeout"), "TimeoutError"),
        (BadRequest("Syntax error in query"), "BadRequest"),
        (Forbidden("IAM permission denied"), "Forbidden"),
        (GoogleAPICallError("Internal BQ error"), "GoogleAPICallError"),
    ],
)
def test_bigquery_failure_sanitization_and_job_id_logged(api_exception, expected_error_class, caplog):
    """Verify BigQuery failures log sanitized exception class and job ID without raw queries."""
    mock_client = MagicMock()
    mock_job = MagicMock()
    mock_job.job_id = "bq_job_failed_123"
    mock_job.result.side_effect = api_exception
    mock_client.query.return_value = mock_job

    executor = BigQueryExecutor(client=mock_client)

    with caplog.at_level(logging.ERROR, logger="ai_agent.bigquery"):
        token = set_current_request_id("test-bq-fail-6")
        try:
            with pytest.raises(BigQueryExecutionError):
                executor.execute_read_only_query(VALID_SQL)
        finally:
            reset_current_request_id(token)

    error_records = [
        r for r in caplog.records
        if r.name == "ai_agent.bigquery" and r.levelname == "ERROR"
    ]
    assert len(error_records) == 1
    msg = error_records[0].message
    assert f"error={expected_error_class}" in msg
    assert "job_id=bq_job_failed_123" in msg
    assert "[test-bq-fail-6]" in msg
    # Verify raw SQL is not in log message
    assert "winter-sensor-474220-u4" not in msg


# =============================================================================
# 4. End-to-End Request ID Correlation and Concurrency Isolation
# =============================================================================

def test_end_to_end_request_id_correlation(caplog):
    """Verify request ID provided via header propagates seamlessly into service logs."""
    client = TestClient(app, raise_server_exceptions=False)
    custom_trace_id = "trace-e2e-correlation-777"

    mock_job = MagicMock()
    mock_job.job_id = "job-e2e-12345"
    mock_job.total_bytes_billed = 512
    mock_job.total_bytes_processed = 1024
    mock_job.slot_millis = 10
    mock_row = MagicMock()
    mock_row.items.return_value = [("total_revenue", 500.0)]
    mock_job.result.return_value = [mock_row]

    with caplog.at_level(logging.INFO):
        with patch(
            "ai_agent.backend.routes.ask.provider_manager.generate_response",
            return_value="SELECT SUM(net_amount) AS total_revenue FROM `winter-sensor-474220-u4.datapulse_marts.fct_sales`",
        ), patch(
            "ai_agent.backend.routes.ask.bigquery_executor.client.query",
            return_value=mock_job,
        ):
            response = client.post(
                "/ask",
                json={"question": "What is total revenue?"},
                headers={"X-Request-ID": custom_trace_id},
            )

    assert response.status_code == 200
    assert response.headers["x-request-id"] == custom_trace_id

    # Verify bigquery service log contains the incoming request ID
    bq_records = [
        r for r in caplog.records
        if r.name == "ai_agent.bigquery" and custom_trace_id in r.message
    ]
    assert len(bq_records) >= 1
    assert f"[{custom_trace_id}]" in bq_records[0].message


def test_concurrent_request_id_isolation():
    """Verify concurrent requests retain separate isolated request IDs via ContextVar."""
    async def main():
        async def worker(req_id: str, delay: float):
            token = set_current_request_id(req_id)
            try:
                await asyncio.sleep(delay)
                current = get_current_request_id()
                return current
            finally:
                reset_current_request_id(token)

        # Launch two workers concurrently with different delays
        task1 = asyncio.create_task(worker("worker-req-alpha", 0.02))
        task2 = asyncio.create_task(worker("worker-req-beta", 0.01))

        return await asyncio.gather(task1, task2)

    res1, res2 = asyncio.run(main())

    assert res1 == "worker-req-alpha"
    assert res2 == "worker-req-beta"


def test_concurrent_http_requests_request_id_isolation(caplog):
    """
    Verify concurrent HTTP requests using FastAPI TestClient maintain strict
    request ID isolation with zero cross-request header or log leakage.
    """
    from concurrent.futures import ThreadPoolExecutor

    client = TestClient(app, raise_server_exceptions=False)
    num_requests = 10
    request_ids = [f"concurrent-trace-{i:03d}" for i in range(num_requests)]

    def make_request(req_id: str):
        resp = client.get("/health", headers={"X-Request-ID": req_id})
        return req_id, resp.status_code, resp.headers.get("x-request-id")

    with caplog.at_level(logging.INFO, logger="ai_agent.request"):
        with ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(make_request, request_ids))

    for expected_id, status_code, returned_id in results:
        assert status_code == 200
        assert returned_id == expected_id, f"Expected {expected_id}, but got {returned_id}"

    # Verify each request ID appears in the captured request logs exactly once
    for req_id in request_ids:
        matching_logs = [
            r for r in caplog.records
            if r.name == "ai_agent.request" and f"[{req_id}]" in r.message
        ]
        assert len(matching_logs) == 1
        assert "GET /health - 200" in matching_logs[0].message



def test_service_logging_outside_http_request(caplog):
    """Verify service logging gracefully defaults to [-] when invoked outside an HTTP context."""
    # Ensure no contextvar is active
    assert get_current_request_id() == "-"

    manager = ProviderManager()
    with caplog.at_level(logging.INFO, logger="ai_agent.providers"):
        with patch(
            "ai_agent.backend.providers.manager.PROVIDER_MAP",
            {"gemini": lambda: MockProvider("Response outside HTTP")},
        ):
            res = manager.generate_response("Question outside HTTP")

    assert res == "Response outside HTTP"
    records = [r for r in caplog.records if r.name == "ai_agent.providers"]
    assert any("[-] AI provider attempt 1/3: gemini" in r.message for r in records)
    assert any("[-] AI provider gemini succeeded" in r.message for r in records)


def test_logging_preserves_underlying_behavior():
    """Verify adding observability does not alter functional outputs or error propagation."""
    manager = ProviderManager()
    with patch(
        "ai_agent.backend.providers.manager.PROVIDER_MAP",
        {"gemini": lambda: MockProvider("Exact Output")},
    ):
        result = manager.generate_response("Test prompt")
    assert result == "Exact Output"

    mock_client = MagicMock()
    mock_job = MagicMock()
    mock_job.job_id = "test-job-id"
    mock_row = MagicMock()
    mock_row.items.return_value = [("metric", 42)]
    mock_job.result.return_value = [mock_row]
    mock_client.query.return_value = mock_job

    executor = BigQueryExecutor(client=mock_client)
    rows = executor.execute_read_only_query(VALID_SQL)
    assert rows == [{"metric": 42}]
