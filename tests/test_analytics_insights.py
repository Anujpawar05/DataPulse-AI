import pytest
import sqlite3
from decimal import Decimal
from datetime import date
from fastapi.testclient import TestClient

from ai_agent.backend.main import app
from ai_agent.backend.routes import analytics
from ai_agent.backend.analytics.insights_store import InsightsStore
from ai_agent.backend.analytics.insights_analyzer import (
    calculate_median,
    calculate_modified_z_scores,
    calculate_moving_averages,
    calculate_rolling_std_bands,
    AnomalyInsightsAnalyzer,
)
from ai_agent.backend.analytics.insights_generator import (
    clean_llm_json_response,
    generate_rule_based_narrative,
    GroundedInsightsGenerator,
)
from ai_agent.backend.sql.bigquery_executor import BigQueryExecutionError
from ai_agent.backend.sql.validator import SQLValidationError

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_insights_db(tmp_path, monkeypatch):
    """Use a temporary SQLite database for test isolation."""
    test_db_path = tmp_path / "test_insights.db"
    test_store = InsightsStore(db_path=test_db_path)
    monkeypatch.setattr(analytics, "insights_store", test_store)
    monkeypatch.setattr(analytics.insights_generator, "store", test_store)
    yield test_store


# =============================================================================
# 1. Statistical Calculation Tests
# =============================================================================

def test_statistical_median_and_z_scores():
    # Odd length
    assert calculate_median([10, 20, 30]) == 20
    # Even length
    assert calculate_median([10, 20, 30, 40]) == 25.0

    # Modified Z-score outlier detection
    normal_series = [100.0] * 20 + [500.0]  # Outlier at end
    z_scores = calculate_modified_z_scores(normal_series)
    assert len(z_scores) == 21
    # Outlier should have high score
    assert z_scores[-1] > 2.5


def test_moving_averages_and_rolling_bands():
    series = [10.0, 20.0, 30.0, 40.0, 50.0]
    sma_3 = calculate_moving_averages(series, window=3)
    assert sma_3[:2] == [None, None]
    assert sma_3[2] == 20.0  # (10+20+30)/3
    assert sma_3[3] == 30.0  # (20+30+40)/3
    assert sma_3[4] == 40.0  # (30+40+50)/3

    bands = calculate_rolling_std_bands(series, window=3, k=2.0)
    assert bands[0]["upper"] is None
    assert bands[2]["upper"] is not None
    assert bands[2]["lower"] is not None
    assert bands[2]["upper"] > bands[2]["sma"] > bands[2]["lower"]


# =============================================================================
# 2. Anomaly Analyzer Fact Extraction
# =============================================================================

def test_analyzer_detects_inventory_dos_and_transfer_feasibility(monkeypatch):
    """Verify inventory analyzer computes Days-of-Supply and validates stock transfer."""
    def mock_query(sql):
        if "fct_inventory" in sql:
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
                    "product_id": 205,
                    "product_name": "Sports Product 005",
                    "product_category": "Sports",
                    "warehouse": "Nagpur",
                    "stock_quantity": 50,
                    "reorder_level": 20,
                    "stock_difference": 30,  # Surplus available
                    "inventory_status": "in_stock",
                    "requires_restock": False,
                },
            ]
        elif "fct_sales" in sql and "SUM(quantity) AS units_sold_30d" in sql:
            return [{"product_id": 205, "units_sold_30d": 30}]  # 1.0 unit/day
        return []

    analyzer = AnomalyInsightsAnalyzer()
    monkeypatch.setattr(analyzer.executor, "execute_read_only_query", mock_query)

    facts = analyzer._detect_inventory_risk_and_dos()
    assert len(facts) == 1
    f = facts[0]
    assert f["category"] == "inventory_risk"
    assert f["severity"] == "critical"
    assert f["observed_value"] == 10.0  # 10 units / 1.0 per day = 10 days
    assert "10.0 Days" in f["observed_value_formatted"]
    assert "transfer viable from Nagpur Hub" in f["observed_fact"]
    assert f["confidence_score"] >= 0.90


def test_analyzer_detects_daily_revenue_crash_and_margin_compression(monkeypatch):
    """Verify daily sales detector flags negative outlier below 30-day band."""
    def mock_query(sql):
        if "fct_daily_sales" in sql:
            # 60 days of ~100k, then sudden crash to 5k on day 60
            rows = []
            for d in range(1, 60):
                rows.append({
                    "sales_date": f"2026-09-{d:02d}" if d <= 30 else f"2026-10-{d-30:02d}",
                    "net_revenue": Decimal("100000.00"),
                    "total_profit": Decimal("35000.00"),
                    "profit_margin_percentage": Decimal("35.00"),
                    "total_orders": 10,
                })
            # Crash day
            rows.append({
                "sales_date": "2026-10-31",
                "net_revenue": Decimal("5000.00"),
                "total_profit": Decimal("500.00"),
                "profit_margin_percentage": Decimal("10.00"),
                "total_orders": 1,
            })
            return rows
        return []

    analyzer = AnomalyInsightsAnalyzer()
    monkeypatch.setattr(analyzer.executor, "execute_read_only_query", mock_query)

    facts = analyzer._detect_daily_sales_anomalies()
    assert len(facts) >= 1
    assert any(f["category"] == "revenue_trend" and f["severity"] == "critical" for f in facts)


# =============================================================================
# 3. Grounded LLM Explainer & Narrative Fallback Tests
# =============================================================================

def test_clean_llm_json_response():
    raw_md = "```json\n[{\"fact_index\": 0, \"headline\": \"Test\"}]\n```"
    assert clean_llm_json_response(raw_md) == '[{"fact_index": 0, "headline": "Test"}]'

    raw_text = "Here is the response:\n[{\"fact_index\": 0}]\nHope it helps!"
    assert clean_llm_json_response(raw_text) == '[{"fact_index": 0}]'


def test_rule_based_narrative_fallback():
    inventory_fact = {
        "category": "inventory_risk",
        "headline": "Stockout Risk",
        "observed_fact": "Current stock is 5 units. Verified stock transfer viable from Mumbai Hub.",
        "observed_value_formatted": "5.0 Days",
        "baseline_value_formatted": "20 units",
    }
    narrative = generate_rule_based_narrative(inventory_fact)
    assert "stock transfer" in narrative["actionable_recommendation"].lower()

    no_transfer_fact = {
        "category": "inventory_risk",
        "headline": "Stockout Risk",
        "observed_fact": "Current stock is 5 units. No source warehouse has surplus.",
        "observed_value_formatted": "5.0 Days",
        "baseline_value_formatted": "20 units",
    }
    narrative2 = generate_rule_based_narrative(no_transfer_fact)
    assert "purchase order" in narrative2["actionable_recommendation"].lower()


def test_generator_graceful_fallback_when_llm_fails(tmp_path):
    store = InsightsStore(db_path=tmp_path / "store.db")
    generator = GroundedInsightsGenerator(store=store)

    fact = {
        "category": "revenue_trend",
        "severity": "critical",
        "headline": "Revenue Drop",
        "observed_fact": "Net revenue dropped 30%",
        "metric_name": "net_revenue",
        "observed_value": 50000.0,
        "observed_value_formatted": "₹50,000.00",
        "baseline_value": 100000.0,
        "baseline_value_formatted": "₹1.00 L",
        "change_percentage": -50.0,
        "statistical_score": -3.2,
        "detection_method": "Z-score",
        "period_start": "2026-10-01",
        "period_end": "2026-10-01",
        "warehouse_table": "fct_daily_sales",
        "supporting_sql": "SELECT 1",
        "confidence_score": 0.95,
        "dimension_key": "rev_drop_2026-10-01",
    }

    # Simulate LLM failure by passing force_llm=False
    results = generator.process_and_persist_facts([fact], force_llm=False)
    assert len(results) == 1
    item = results[0]
    assert item["ai_provider_used"] == "rule_fallback"
    assert len(item["ai_explanation"]) > 10
    assert len(item["actionable_recommendation"]) > 10
    # Immutable values preserved
    assert item["confidence_score"] == 0.95
    assert item["observed_value"] == 50000.0


# =============================================================================
# 4. SQLite Storage, CRUD, and Duplicate Fingerprint Tests
# =============================================================================

def test_sqlite_insights_crud_and_status_transitions(tmp_path):
    store = InsightsStore(db_path=tmp_path / "insights.db")

    item = {
        "category": "profit_margin",
        "severity": "warning",
        "status": "active",
        "headline": "Margin Compression",
        "observed_fact": "Margin fell to 20%",
        "ai_explanation": "Discounting increased.",
        "actionable_recommendation": "Review promotions.",
        "metric_name": "profit_margin_percentage",
        "observed_value": 20.0,
        "observed_value_formatted": "20.0%",
        "baseline_value": 30.0,
        "baseline_value_formatted": "30.0%",
        "change_percentage": -33.3,
        "statistical_score": -10.0,
        "detection_method": "Margin Divergence",
        "period_start": "2026-10-01",
        "period_end": "2026-10-31",
        "warehouse_table": "fct_daily_sales",
        "supporting_sql": "SELECT 1",
        "confidence_score": 0.88,
        "ai_provider_used": "rule_fallback",
        "dimension_key": "margin_oct2026",
    }

    # 1. Create
    saved = store.save_insight(item)
    assert saved is not None
    insight_id = saved["insight_id"]
    assert saved["status"] == "active"

    # 2. Read
    fetched = store.get_insight_by_id(insight_id)
    assert fetched["headline"] == "Margin Compression"

    # 3. Update status (active -> acknowledged)
    updated = store.update_insight_status(insight_id, "acknowledged")
    assert updated["status"] == "acknowledged"

    # 4. Update status (acknowledged -> dismissed)
    dismissed = store.update_insight_status(insight_id, "dismissed")
    assert dismissed["status"] == "dismissed"

    # 5. Invalid status raises ValueError
    with pytest.raises(ValueError):
        store.update_insight_status(insight_id, "invalid_status")


def test_sqlite_duplicate_fingerprint_prevention(tmp_path):
    """Verify scanning the same anomaly repeatedly updates metrics but does not create duplicate rows."""
    store = InsightsStore(db_path=tmp_path / "insights.db")

    item = {
        "category": "inventory_risk",
        "severity": "critical",
        "status": "active",
        "headline": "Stockout Risk",
        "observed_fact": "Stock is 5 units",
        "ai_explanation": "Explain",
        "actionable_recommendation": "Reorder",
        "metric_name": "days_of_supply",
        "observed_value": 5.0,
        "observed_value_formatted": "5.0 Days",
        "period_start": "2026-10-31",
        "period_end": "2026-10-31",
        "warehouse_table": "fct_inventory",
        "supporting_sql": "SELECT 1",
        "confidence_score": 0.95,
        "dimension_key": "p205_pune",
    }

    # Scan 1
    res1 = store.save_insight(item)
    assert len(store.get_insights()) == 1

    # User acknowledges insight
    store.update_insight_status(res1["insight_id"], "acknowledged")

    # Scan 2 (Simulate metric update on re-scan)
    item["observed_value"] = 3.0
    item["observed_value_formatted"] = "3.0 Days"
    res2 = store.save_insight(item)

    # Must still be exactly 1 record, with user status preserved!
    all_insights = store.get_insights()
    assert len(all_insights) == 1
    assert all_insights[0]["insight_id"] == res1["insight_id"]
    assert all_insights[0]["observed_value"] == 3.0
    assert all_insights[0]["status"] == "acknowledged"  # Preserved!


# =============================================================================
# 5. API Endpoints Integration Tests
# =============================================================================

def test_get_insights_filtering(clean_insights_db):
    # Seed 2 items
    clean_insights_db.save_insight({
        "category": "revenue_trend",
        "severity": "critical",
        "status": "active",
        "headline": "Crash",
        "observed_fact": "Fact 1",
        "ai_explanation": "Exp 1",
        "actionable_recommendation": "Rec 1",
        "metric_name": "net_revenue",
        "observed_value": 100.0,
        "observed_value_formatted": "₹100",
        "period_start": "2026-10-01",
        "period_end": "2026-10-01",
        "warehouse_table": "fct_daily_sales",
        "supporting_sql": "SELECT 1",
        "confidence_score": 0.95,
        "dimension_key": "k1",
    })
    clean_insights_db.save_insight({
        "category": "profit_margin",
        "severity": "warning",
        "status": "dismissed",
        "headline": "Margin",
        "observed_fact": "Fact 2",
        "ai_explanation": "Exp 2",
        "actionable_recommendation": "Rec 2",
        "metric_name": "profit_margin",
        "observed_value": 25.0,
        "observed_value_formatted": "25%",
        "period_start": "2026-10-02",
        "period_end": "2026-10-02",
        "warehouse_table": "fct_daily_sales",
        "supporting_sql": "SELECT 2",
        "confidence_score": 0.85,
        "dimension_key": "k2",
    })

    # All
    res = client.get("/analytics/insights")
    assert res.status_code == 200
    assert res.json()["total_insights"] == 2
    assert res.json()["active_critical_count"] == 1

    # Filter by category
    res_cat = client.get("/analytics/insights?category=revenue_trend")
    assert res_cat.status_code == 200
    assert res_cat.json()["total_insights"] == 1

    # Filter by status
    res_stat = client.get("/analytics/insights?status=dismissed")
    assert res_stat.status_code == 200
    assert res_stat.json()["total_insights"] == 1


def test_patch_insight_status_endpoint(clean_insights_db):
    saved = clean_insights_db.save_insight({
        "category": "revenue_trend",
        "severity": "critical",
        "status": "active",
        "headline": "Crash",
        "observed_fact": "Fact 1",
        "ai_explanation": "Exp 1",
        "actionable_recommendation": "Rec 1",
        "metric_name": "net_revenue",
        "observed_value": 100.0,
        "observed_value_formatted": "₹100",
        "period_start": "2026-10-01",
        "period_end": "2026-10-01",
        "warehouse_table": "fct_daily_sales",
        "supporting_sql": "SELECT 1",
        "confidence_score": 0.95,
        "dimension_key": "k1",
    })
    i_id = saved["insight_id"]

    # Valid status transition
    res = client.patch(f"/analytics/insights/{i_id}/status", json={"status": "acknowledged"})
    assert res.status_code == 200
    assert res.json()["status"] == "acknowledged"

    # Nonexistent ID returns 404
    res_404 = client.patch("/analytics/insights/ins_nonexistent/status", json={"status": "dismissed"})
    assert res_404.status_code == 404

    # Invalid status returns 422
    res_422 = client.patch(f"/analytics/insights/{i_id}/status", json={"status": "invalid_choice"})
    assert res_422.status_code == 422


def test_post_generate_insights_endpoint(monkeypatch, clean_insights_db):
    """Test on-demand generation endpoint with mocked BigQuery analyzer."""
    mock_facts = [
        {
            "category": "revenue_trend",
            "severity": "critical",
            "headline": "Mock Revenue Spike",
            "observed_fact": "Net revenue surged 50%",
            "metric_name": "net_revenue",
            "observed_value": 500000.0,
            "observed_value_formatted": "₹5.00 L",
            "baseline_value": 250000.0,
            "baseline_value_formatted": "₹2.50 L",
            "change_percentage": 100.0,
            "statistical_score": 3.5,
            "detection_method": "Z-Score",
            "period_start": "2026-10-15",
            "period_end": "2026-10-15",
            "warehouse_table": "fct_daily_sales",
            "supporting_sql": "SELECT 1",
            "confidence_score": 0.95,
            "dimension_key": "spike_2026-10-15",
        }
    ]

    monkeypatch.setattr(analytics.insights_analyzer, "analyze_warehouse_anomalies", lambda: mock_facts)
    monkeypatch.setattr(
        analytics.insights_generator.provider_manager,
        "generate_response",
        lambda prompt: '[{"fact_index": 0, "headline": "Mock Revenue Spike", "ai_explanation": "Mock explanation", "actionable_recommendation": "Mock rec"}]',
    )

    res = client.post("/analytics/insights/generate")
    assert res.status_code == 200
    data = res.json()
    assert data["total_insights"] >= 1
    assert data["insights"][0]["metric_name"] == "net_revenue"


def test_generate_handles_bigquery_error(monkeypatch):
    def fail():
        raise BigQueryExecutionError("BigQuery timeout")

    monkeypatch.setattr(analytics.insights_analyzer, "analyze_warehouse_anomalies", fail)
    res = client.post("/analytics/insights/generate")
    assert res.status_code == 503
    assert "Warehouse execution failed" in res.json()["detail"]


def test_generate_handles_sql_validation_error(monkeypatch):
    def fail():
        raise SQLValidationError("Unapproved table")

    monkeypatch.setattr(analytics.insights_analyzer, "analyze_warehouse_anomalies", fail)
    res = client.post("/analytics/insights/generate")
    assert res.status_code == 400
    assert "Security validation rejected" in res.json()["detail"]
