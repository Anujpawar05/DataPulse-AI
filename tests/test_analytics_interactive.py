import pytest
from datetime import date
from decimal import Decimal
from fastapi.testclient import TestClient

from ai_agent.backend.main import app
from ai_agent.backend.routes import analytics
from ai_agent.backend.sql.bigquery_executor import BigQueryExecutionError
from ai_agent.backend.sql.validator import SQLValidationError

client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_cache():
    """Ensure in-memory cache is reset between tests."""
    with analytics._cache_lock:
        if hasattr(analytics, "_cache_store"):
            analytics._cache_store.clear()
        if hasattr(analytics, "_cached_data"):
            analytics._cached_data = None
            analytics._cached_timestamp = 0.0


def test_invalid_date_formats_rejected():
    """Verify non-ISO or invalid dates are rejected with HTTP 422."""
    invalid_cases = [
        {"start_date": "2026/01/01"},
        {"end_date": "2026-13-01"},
        {"start_date": "01-01-2026"},
        {"start_date": "2026-02-31"},
        {"start_date": "2026-01-01' OR '1'='1"},
        {"end_date": "; DROP TABLE fct_sales; --"},
    ]
    for params in invalid_cases:
        res = client.get("/analytics/dashboard", params=params)
        assert res.status_code == 422, f"Expected 422 for params {params}, got {res.status_code}"
        assert "Invalid" in res.json()["detail"] or "validation error" in res.json()["detail"].lower()


def test_start_date_after_end_date_rejected():
    """Verify start_date > end_date returns HTTP 422."""
    res = client.get(
        "/analytics/dashboard",
        params={"start_date": "2026-08-01", "end_date": "2026-02-01"},
    )
    assert res.status_code == 422
    assert "cannot be chronologically after" in res.json()["detail"]


def test_invalid_granularity_rejected():
    """Verify granularity must be 'daily' or 'monthly'."""
    res = client.get("/analytics/dashboard", params={"granularity": "yearly"})
    assert res.status_code == 422

    res2 = client.get("/analytics/dashboard", params={"granularity": "hourly"})
    assert res2.status_code == 422


def test_daily_trends_and_date_filtering(monkeypatch):
    """Verify daily granularity queries and date clauses are applied."""
    executed_queries = []

    def mock_query(sql):
        executed_queries.append(sql)
        if "fct_daily_sales" in sql:
            return [
                {
                    "period": date(2026, 1, 1),
                    "net_revenue": Decimal("150000.00"),
                    "total_profit": Decimal("45000.00"),
                    "total_orders": 12,
                    "units_sold": 15,
                    "profit_margin_percentage": Decimal("30.00"),
                },
                {
                    "period": date(2026, 1, 2),
                    "net_revenue": Decimal("220000.00"),
                    "total_profit": Decimal("66000.00"),
                    "total_orders": 18,
                    "units_sold": 22,
                    "profit_margin_percentage": Decimal("30.00"),
                },
            ]
        elif "fct_sales" in sql and "GROUP BY product_category" in sql:
            return [
                {
                    "product_category": "Electronics",
                    "net_revenue": Decimal("370000.00"),
                    "total_profit": Decimal("111000.00"),
                    "profit_margin_percentage": Decimal("30.00"),
                    "total_orders": 30,
                }
            ]
        elif "fct_sales" in sql and "GROUP BY product_id" in sql:
            return [
                {
                    "product_id": 101,
                    "product_name": "Pro Smartphone",
                    "product_category": "Electronics",
                    "units_sold": 37,
                    "total_revenue": Decimal("370000.00"),
                    "total_profit": Decimal("111000.00"),
                    "profit_margin_percentage": Decimal("30.00"),
                }
            ]
        elif "fct_sales" in sql:
            return [{
                "total_net_revenue": Decimal("370000.00"),
                "total_profit": Decimal("111000.00"),
                "total_orders": 30,
                "delivered_orders": 25,
                "total_customers": 28,
                "total_products": 1,
            }]
        elif "fct_inventory" in sql and "GROUP BY warehouse" in sql:
            return [{
                "warehouse": "Mumbai",
                "total_skus": 10,
                "total_units": 450,
                "restock_alerts": 1,
                "low_stock_count": 1,
                "in_stock_count": 9,
            }]
        elif "fct_inventory" in sql:
            return [{
                "product_id": 101,
                "product_name": "Pro Smartphone",
                "product_category": "Electronics",
                "warehouse": "Mumbai",
                "stock_quantity": 5,
                "reorder_level": 20,
                "stock_difference": -15,
                "inventory_status": "low_stock",
                "requires_restock": True,
            }]
        return []

    monkeypatch.setattr(analytics.bigquery_executor, "execute_read_only_query", mock_query)

    res = client.get(
        "/analytics/dashboard",
        params={"start_date": "2026-01-01", "end_date": "2026-01-02", "granularity": "daily"},
    )
    assert res.status_code == 200
    data = res.json()

    # Verify date filters reflected in meta
    assert data["date_filter"]["start_date"] == "2026-01-01"
    assert data["date_filter"]["end_date"] == "2026-01-02"
    assert data["date_filter"]["granularity"] == "daily"

    # Verify query where clauses
    assert any("order_date >= '2026-01-01' AND order_date <= '2026-01-02'" in q for q in executed_queries)
    assert any("sales_date >= '2026-01-01' AND sales_date <= '2026-01-02'" in q for q in executed_queries)

    # Verify daily trends formatted
    trends = data["revenue_trends"]
    assert len(trends) == 2
    assert trends[0]["period"] == "2026-01-01"
    assert trends[0]["period_label"] == "01 Jan 2026"
    assert trends[0]["net_revenue"] == 150000.0
    assert trends[0]["net_revenue_formatted"] == "₹1.50 L"


def test_top_products_and_category_comparison_sorting(monkeypatch):
    """Verify categories and products are correctly sorted descending by revenue."""
    def mock_query(sql):
        if "fct_category_sales" in sql or ("fct_sales" in sql and "GROUP BY product_category" in sql):
            return [
                {
                    "product_category": "Electronics",
                    "net_revenue": Decimal("5000000.00"),
                    "total_profit": Decimal("1500000.00"),
                    "profit_margin_percentage": Decimal("30.00"),
                    "total_orders": 120,
                },
                {
                    "product_category": "Fashion",
                    "net_revenue": Decimal("2000000.00"),
                    "total_profit": Decimal("500000.00"),
                    "profit_margin_percentage": Decimal("25.00"),
                    "total_orders": 80,
                },
            ]
        elif "fct_sales" in sql and "GROUP BY product_id" in sql:
            return [
                {
                    "product_id": 1,
                    "product_name": "Premium Laptop",
                    "product_category": "Electronics",
                    "units_sold": 50,
                    "total_revenue": Decimal("3500000.00"),
                    "total_profit": Decimal("1050000.00"),
                    "profit_margin_percentage": Decimal("30.00"),
                },
                {
                    "product_id": 2,
                    "product_name": "Wireless Headphones",
                    "product_category": "Electronics",
                    "units_sold": 150,
                    "total_revenue": Decimal("1500000.00"),
                    "total_profit": Decimal("450000.00"),
                    "profit_margin_percentage": Decimal("30.00"),
                },
            ]
        elif "fct_sales" in sql:
            return [{
                "total_net_revenue": Decimal("5000000.00"),
                "total_profit": Decimal("1500000.00"),
                "total_orders": 200,
                "delivered_orders": 180,
            }]
        elif "dim_customers" in sql:
            return [{"total_customers": 150}]
        elif "dim_products" in sql:
            return [{"total_products": 20}]
        elif "fct_daily_sales" in sql:
            return []
        elif "fct_inventory" in sql:
            return []
        return []

    monkeypatch.setattr(analytics.bigquery_executor, "execute_read_only_query", mock_query)

    res = client.get("/analytics/dashboard")
    assert res.status_code == 200
    data = res.json()

    # Category profitability order
    cats = data["category_profitability"]
    assert len(cats) == 2
    assert cats[0]["net_revenue"] > cats[1]["net_revenue"]
    assert cats[0]["product_category"] == "Electronics"
    assert cats[0]["net_revenue_formatted"] == "₹50.00 L"

    # Top products ranking
    prods = data["top_products"]
    assert len(prods) == 2
    assert prods[0]["total_revenue"] > prods[1]["total_revenue"]
    assert prods[0]["product_name"] == "Premium Laptop"
    assert prods[0]["total_revenue_formatted"] == "₹35.00 L"


def test_inventory_risk_warehouse_breakdown(monkeypatch):
    """Verify inventory risk analysis, warehouse health status, and score percentage."""
    def mock_query(sql):
        if "fct_inventory" in sql and "GROUP BY warehouse" in sql:
            return [
                {
                    "warehouse": "Mumbai",
                    "total_skus": 10,
                    "total_units": 500,
                    "restock_alerts": 2,
                    "low_stock_count": 2,
                    "in_stock_count": 8,
                },
                {
                    "warehouse": "Pune",
                    "total_skus": 10,
                    "total_units": 450,
                    "restock_alerts": 1,
                    "low_stock_count": 1,
                    "in_stock_count": 9,
                },
                {
                    "warehouse": "Nagpur",
                    "total_skus": 10,
                    "total_units": 600,
                    "restock_alerts": 0,
                    "low_stock_count": 0,
                    "in_stock_count": 10,
                },
            ]
        elif "fct_inventory" in sql:
            return [
                {
                    "product_id": 1,
                    "product_name": "Product A",
                    "product_category": "Electronics",
                    "warehouse": "Mumbai",
                    "stock_quantity": 5,
                    "reorder_level": 20,
                    "stock_difference": -15,
                    "inventory_status": "low_stock",
                    "requires_restock": True,
                },
                {
                    "product_id": 2,
                    "product_name": "Product B",
                    "product_category": "Home & Kitchen",
                    "warehouse": "Mumbai",
                    "stock_quantity": 8,
                    "reorder_level": 20,
                    "stock_difference": -12,
                    "inventory_status": "low_stock",
                    "requires_restock": True,
                },
                {
                    "product_id": 3,
                    "product_name": "Product C",
                    "product_category": "Beauty",
                    "warehouse": "Pune",
                    "stock_quantity": 10,
                    "reorder_level": 25,
                    "stock_difference": -15,
                    "inventory_status": "low_stock",
                    "requires_restock": True,
                },
            ]
        elif "fct_sales" in sql:
            return [{"total_net_revenue": Decimal("100"), "total_profit": Decimal("10"), "total_orders": 1, "delivered_orders": 1}]
        elif "dim_customers" in sql:
            return [{"total_customers": 1}]
        elif "dim_products" in sql:
            return [{"total_products": 3}]
        elif "fct_category_sales" in sql or "fct_daily_sales" in sql:
            return []
        return []

    monkeypatch.setattr(analytics.bigquery_executor, "execute_read_only_query", mock_query)

    res = client.get("/analytics/dashboard")
    assert res.status_code == 200
    data = res.json()

    inv_risk = data["inventory_risk"]
    assert inv_risk is not None
    assert inv_risk["total_skus"] == 30
    assert inv_risk["critical_alerts_count"] == 3
    # 27 in_stock out of 30 = 90.0%
    assert inv_risk["health_score_percentage"] == 90.0

    breakdown = inv_risk["warehouse_breakdown"]
    assert len(breakdown) == 3
    assert breakdown[0]["warehouse"] == "Mumbai"
    assert breakdown[0]["health_status"] == "High Risk"
    assert breakdown[1]["warehouse"] == "Pune"
    assert breakdown[1]["health_status"] == "Moderate Risk"
    assert breakdown[2]["warehouse"] == "Nagpur"
    assert breakdown[2]["health_status"] == "Normal"


def test_parameterized_caching_isolation(monkeypatch):
    """Verify separate cache keys for distinct date/granularity parameters and refresh bypass."""
    query_count = {"count": 0}

    def mock_query(sql):
        query_count["count"] += 1
        if "fct_sales" in sql:
            return [{"total_net_revenue": Decimal("1000"), "total_profit": Decimal("100"), "total_orders": 5, "delivered_orders": 5}]
        elif "dim_customers" in sql:
            return [{"total_customers": 2}]
        elif "dim_products" in sql:
            return [{"total_products": 2}]
        return []

    monkeypatch.setattr(analytics.bigquery_executor, "execute_read_only_query", mock_query)

    # 1. Parameter Set A
    res_a1 = client.get("/analytics/dashboard?start_date=2026-01-01&end_date=2026-06-30")
    assert res_a1.status_code == 200
    assert res_a1.json()["cache"]["cached"] is False
    count_after_a1 = query_count["count"]

    # 2. Same Parameter Set A -> Cache Hit
    res_a2 = client.get("/analytics/dashboard?start_date=2026-01-01&end_date=2026-06-30")
    assert res_a2.status_code == 200
    assert res_a2.json()["cache"]["cached"] is True
    assert query_count["count"] == count_after_a1  # No queries executed

    # 3. Parameter Set B (different dates) -> Cache Miss
    res_b = client.get("/analytics/dashboard?start_date=2025-01-01&end_date=2025-12-31")
    assert res_b.status_code == 200
    assert res_b.json()["cache"]["cached"] is False
    assert query_count["count"] > count_after_a1

    # 4. Parameter Set C (different granularity) -> Cache Miss
    count_after_b = query_count["count"]
    res_c = client.get("/analytics/dashboard?start_date=2026-01-01&end_date=2026-06-30&granularity=daily")
    assert res_c.status_code == 200
    assert res_c.json()["cache"]["cached"] is False
    assert query_count["count"] > count_after_b

    # 5. Parameter Set A with refresh=true -> Cache Bypass
    count_after_c = query_count["count"]
    res_a_refreshed = client.get("/analytics/dashboard?start_date=2026-01-01&end_date=2026-06-30&refresh=true")
    assert res_a_refreshed.status_code == 200
    assert res_a_refreshed.json()["cache"]["cached"] is False
    assert query_count["count"] > count_after_c


def test_empty_results_handled_gracefully(monkeypatch):
    """Verify backend handles empty warehouse result sets without error."""
    monkeypatch.setattr(analytics.bigquery_executor, "execute_read_only_query", lambda sql: [])

    res = client.get("/analytics/dashboard?start_date=2026-01-01&end_date=2026-01-02")
    assert res.status_code == 200
    data = res.json()
    assert data["summary"]["total_net_revenue"] == 0.0
    assert data["summary"]["total_profit"] == 0.0
    assert data["summary"]["profit_margin_percentage"] == 0.0
    assert data["revenue_trends"] == []
    assert data["category_profitability"] == []
    assert data["top_products"] == []
    assert data["restock_queue"] == []
    assert data["inventory_risk"]["health_score_percentage"] == 100.0


def test_backend_security_and_execution_errors(monkeypatch):
    """Verify BigQueryExecutionError (503) and SQLValidationError (400) handling."""
    def fail_bq(sql):
        raise BigQueryExecutionError("Query timeout")

    monkeypatch.setattr(analytics.bigquery_executor, "execute_read_only_query", fail_bq)
    res_bq = client.get("/analytics/dashboard")
    assert res_bq.status_code == 503
    assert "Warehouse execution failed" in res_bq.json()["detail"]

    with analytics._cache_lock:
        analytics._cache_store.clear()

    def fail_val(sql):
        raise SQLValidationError("Table not whitelisted")

    monkeypatch.setattr(analytics.bigquery_executor, "execute_read_only_query", fail_val)
    res_val = client.get("/analytics/dashboard")
    assert res_val.status_code == 400
    assert "Security validation rejected query" in res_val.json()["detail"]

