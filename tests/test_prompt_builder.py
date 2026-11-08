import pytest

from ai_agent.backend.rag.prompt_builder import build_sql_prompt


def test_prompt_contains_user_question():
    question = "Which products are low on stock and need restocking?"
    prompt = build_sql_prompt(question)

    assert question in prompt


def test_prompt_contains_inventory_schema():
    prompt = build_sql_prompt(
        "Which products are low on stock and need restocking?"
    )

    assert "fct_inventory" in prompt
    assert "stock_quantity" in prompt
    assert "reorder_level" in prompt
    assert "requires_restock" in prompt


def test_prompt_uses_approved_marts_dataset():
    prompt = build_sql_prompt("Show daily revenue trends.")

    assert "winter-sensor-474220-u4.datapulse_marts" in prompt
    assert "datapulse_analytics" not in prompt


def test_prompt_contains_sql_safety_rules():
    prompt = build_sql_prompt("Show daily revenue trends.")

    assert "SELECT queries only" in prompt
    assert "fully qualified BigQuery table names" in prompt
    assert "Never generate write operations" in prompt


def test_empty_question_is_rejected():
    with pytest.raises(ValueError):
        build_sql_prompt("   ")


def test_unmatched_question_is_rejected():
    with pytest.raises(ValueError, match="cannot currently be mapped"):
        build_sql_prompt("Explain the history of artificial intelligence.")


def test_top_selling_products_retrieves_sales_and_products_schema():
    prompt = build_sql_prompt("What are the top 3 selling products?")

    # Both schemas must be present
    assert "fct_sales" in prompt
    assert "dim_products" in prompt
    # Sales transaction and volume columns
    assert "quantity" in prompt
    assert "product_name" in prompt
    # Join key relationship
    assert "dim_products.product_id" in prompt and "fct_sales.product_id" in prompt
    # Metric definition
    assert "Total Units Sold" in prompt


def test_highest_revenue_products_retrieves_sales_and_products_schema():
    prompt = build_sql_prompt("Which 5 products generate the highest revenue?")

    assert "fct_sales" in prompt
    assert "dim_products" in prompt
    assert "net_amount" in prompt
    assert "Total Revenue" in prompt


def test_customers_most_orders_retrieves_customers_and_sales_schema():
    prompt = build_sql_prompt("Which customers have placed the most orders?")

    assert "dim_customers" in prompt
    assert "customer_name" in prompt
    assert "total_orders" in prompt
