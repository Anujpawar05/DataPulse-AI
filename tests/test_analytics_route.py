import pytest
from decimal import Decimal
from fastapi.testclient import TestClient

from ai_agent.backend.main import app
from ai_agent.backend.routes import analytics
from ai_agent.backend.routes.analytics import format_inr
from ai_agent.backend.sql.bigquery_executor import BigQueryExecutionError
from ai_agent.backend.sql.validator import SQLValidationError

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset the analytics in-memory cache before each test."""
    with analytics._cache_lock:
        analytics._cached_data = None
        analytics._cached_timestamp = 0.0


def test_format_inr():
    assert format_inr(475854154.52) == "₹47.59 Cr"
    assert format_inr(149862074.20) == "₹14.99 Cr"
    assert format_inr(550000.0) == "₹5.50 L"
    assert format_inr(12500.50) == "₹12,500.50"


def test_dashboard_analytics_success(monkeypatch):
    call_counts = {"count": 0}

    def mock_query(sql):
        call_counts["count"] += 1
        if "fct_sales" in sql:
            return [{
                "total_net_revenue": Decimal("475854154.52"),
                "total_profit": Decimal("149862074.20"),
                "total_orders": 5000,
                "delivered_orders": 3194,
            }]
        elif "dim_customers" in sql:
            return [{"total_customers": 991}]
        elif "dim_products" in sql:
            return [{"total_products": 100}]
        elif "fct_category_sales" in sql:
            return [
                {
                    "product_category": "Electronics",
                    "net_revenue": Decimal("69013425.61"),
                    "total_profit": Decimal("25127599.37"),
                    "profit_margin_percentage": Decimal("36.41"),
                },
                {
                    "product_category": "Home & Kitchen",
                    "net_revenue": Decimal("66744635.57"),
                    "total_profit": Decimal("23936415.37"),
                    "profit_margin_percentage": Decimal("35.86"),
                },
            ]
        elif "fct_inventory" in sql:
            return [
                {
                    "product_id": 205,
                    "product_name": "Sports Product 005",
                    "product_category": "Sports",
                    "warehouse": "Pune",
                    "stock_quantity": 10,
                    "reorder_level": 20,
                    "stock_difference": -10,
                    "inventory_status": "low_stock",
                    "requires_restock": True,
                },
                {
                    "product_id": 101,
                    "product_name": "Standard Product",
                    "product_category": "General",
                    "warehouse": "Mumbai",
                    "stock_quantity": 50,
                    "reorder_level": 20,
                    "stock_difference": 30,
                    "inventory_status": "in_stock",
                    "requires_restock": False,
                },
            ]
        return []

    monkeypatch.setattr(
        analytics.bigquery_executor,
        "execute_read_only_query",
        mock_query,
    )

    response = client.get("/analytics/dashboard")
    assert response.status_code == 200
    data = response.json()

    # Verify Summary
    summary = data["summary"]
    assert summary["total_net_revenue"] == 475854154.52
    assert summary["total_net_revenue_formatted"] == "₹47.59 Cr"
    assert summary["total_profit"] == 149862074.20
    assert summary["total_profit_formatted"] == "₹14.99 Cr"
    assert summary["profit_margin_percentage"] == 31.49
    assert summary["total_orders"] == 5000
    assert summary["delivered_orders"] == 3194
    assert summary["total_customers"] == 991
    assert summary["total_products"] == 100
    assert summary["restock_alerts_count"] == 1

    # Verify Categories
    assert len(data["category_profitability"]) == 2
    assert data["category_profitability"][0]["product_category"] == "Electronics"
    assert data["category_profitability"][0]["profit_margin_percentage"] == 36.41

    # Verify Restock Queue (only requires_restock == True)
    assert len(data["restock_queue"]) == 1
    assert data["restock_queue"][0]["product_name"] == "Sports Product 005"
    assert data["restock_queue"][0]["warehouse"] == "Pune"

    # Verify Cache meta
    assert data["cache"]["cached"] is False
    assert call_counts["count"] == 5


def test_dashboard_caching_and_manual_refresh(monkeypatch):
    call_counts = {"count": 0}

    def mock_query(sql):
        call_counts["count"] += 1
        if "fct_sales" in sql:
            return [{"total_net_revenue": Decimal("1000"), "total_profit": Decimal("200"), "total_orders": 10, "delivered_orders": 8}]
        elif "dim_customers" in sql:
            return [{"total_customers": 5}]
        elif "dim_products" in sql:
            return [{"total_products": 2}]
        elif "fct_category_sales" in sql:
            return []
        elif "fct_inventory" in sql:
            return []
        return []

    monkeypatch.setattr(
        analytics.bigquery_executor,
        "execute_read_only_query",
        mock_query,
    )

    # 1. First call: executes queries and populates cache
    res1 = client.get("/analytics/dashboard")
    assert res1.status_code == 200
    assert res1.json()["cache"]["cached"] is False
    assert call_counts["count"] == 5

    # 2. Second call: hits cache without executing BigQuery queries
    res2 = client.get("/analytics/dashboard")
    assert res2.status_code == 200
    assert res2.json()["cache"]["cached"] is True
    assert call_counts["count"] == 5  # No additional queries!

    # 3. Third call with ?refresh=true: bypasses cache and fetches fresh data
    res3 = client.get("/analytics/dashboard?refresh=true")
    assert res3.status_code == 200
    assert res3.json()["cache"]["cached"] is False
    assert call_counts["count"] == 10  # 5 fresh queries executed!


def test_dashboard_handles_empty_dataset(monkeypatch):
    monkeypatch.setattr(
        analytics.bigquery_executor,
        "execute_read_only_query",
        lambda sql: [],
    )

    response = client.get("/analytics/dashboard")
    assert response.status_code == 200
    data = response.json()
    assert data["summary"]["total_net_revenue"] == 0.0
    assert data["summary"]["total_orders"] == 0
    assert data["category_profitability"] == []
    assert data["restock_queue"] == []


def test_dashboard_handles_bigquery_error(monkeypatch):
    def reject_query(sql):
        raise BigQueryExecutionError("BigQuery network error")

    monkeypatch.setattr(
        analytics.bigquery_executor,
        "execute_read_only_query",
        reject_query,
    )

    response = client.get("/analytics/dashboard")
    assert response.status_code == 503
    assert "Warehouse execution failed" in response.json()["detail"]


def test_dashboard_handles_sql_validation_error(monkeypatch):
    def reject_query(sql):
        raise SQLValidationError("Forbidden table accessed")

    monkeypatch.setattr(
        analytics.bigquery_executor,
        "execute_read_only_query",
        reject_query,
    )

    response = client.get("/analytics/dashboard")
    assert response.status_code == 400
    assert "Security validation rejected query" in response.json()["detail"]
