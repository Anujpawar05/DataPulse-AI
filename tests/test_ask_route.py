
import pytest
from fastapi.testclient import TestClient

from ai_agent.backend.main import app
from ai_agent.backend.routes import ask
from ai_agent.backend.sql.validator import SQLValidationError
from ai_agent.backend.sql.bigquery_executor import BigQueryExecutionError


client = TestClient(app)


def test_ask_success(monkeypatch):
    monkeypatch.setattr(
        ask,
        "build_sql_prompt",
        lambda question: "Generate SQL",
    )
    monkeypatch.setattr(
        ask.provider_manager,
        "generate_response",
        lambda prompt: (
            "SELECT sales_date, net_revenue "
            "FROM `winter-sensor-474220-u4.datapulse_marts.fct_daily_sales` "
            "LIMIT 5"
        ),
    )
    monkeypatch.setattr(
        ask.bigquery_executor,
        "execute_read_only_query",
        lambda sql: [{"net_revenue": 1000}],
    )

    response = client.post(
        "/ask",
        json={"question": "Show daily revenue"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["row_count"] == 1


def test_ask_rejects_short_question():
    response = client.post(
        "/ask",
        json={"question": "Hi"},
    )

    assert response.status_code == 422


def test_ask_returns_clarification(monkeypatch):
    monkeypatch.setattr(
        ask,
        "build_sql_prompt",
        lambda question: "Generate SQL",
    )
    monkeypatch.setattr(
        ask.provider_manager,
        "generate_response",
        lambda prompt: "CLARIFICATION: Please specify a business metric.",
    )

    response = client.post(
        "/ask",
        json={"question": "Show something"},
    )

    assert response.status_code == 422
    assert "CLARIFICATION" in response.json()["detail"]


def test_ask_handles_sql_validation_error(monkeypatch):
    monkeypatch.setattr(
        ask,
        "build_sql_prompt",
        lambda question: "Generate SQL",
    )
    monkeypatch.setattr(
        ask.provider_manager,
        "generate_response",
        lambda prompt: "DELETE FROM customers",
    )

    def reject_sql(sql):
        raise SQLValidationError("Only SELECT queries are allowed.")

    monkeypatch.setattr(
        ask.bigquery_executor,
        "execute_read_only_query",
        reject_sql,
    )

    response = client.post(
        "/ask",
        json={"question": "Delete customer data"},
    )

    assert response.status_code == 400


def test_ask_handles_bigquery_error(monkeypatch):
    monkeypatch.setattr(
        ask,
        "build_sql_prompt",
        lambda question: "Generate SQL",
    )
    monkeypatch.setattr(
        ask.provider_manager,
        "generate_response",
        lambda prompt: "SELECT 1",
    )
    monkeypatch.setattr(
        ask.bigquery_executor,
        "execute_read_only_query",
        lambda sql: (_ for _ in ()).throw(
            BigQueryExecutionError("BigQuery unavailable")
        ),
    )

    response = client.post(
        "/ask",
        json={"question": "Show daily revenue"},
    )

    assert response.status_code == 503


def test_ask_handles_provider_failure(monkeypatch):
    monkeypatch.setattr(
        ask,
        "build_sql_prompt",
        lambda question: "Generate SQL",
    )
    monkeypatch.setattr(
        ask.provider_manager,
        "generate_response",
        lambda prompt: (_ for _ in ()).throw(
            RuntimeError("All providers unavailable")
        ),
    )

    response = client.post(
        "/ask",
        json={"question": "Show daily revenue"},
    )

    assert response.status_code == 503
