
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
