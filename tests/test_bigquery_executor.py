
from unittest.mock import MagicMock

import pytest

from ai_agent.backend.sql.bigquery_executor import (
    BigQueryExecutor,
)
from ai_agent.backend.sql.validator import SQLValidationError


VALID_QUERY = """
SELECT SUM(net_amount) AS total_revenue
FROM `winter-sensor-474220-u4.datapulse_marts.fct_sales`
"""


def test_executes_valid_query():
    client = MagicMock()
    job = MagicMock()

    row = MagicMock()
    row.items.return_value = [("total_revenue", 1250)]

    job.result.return_value = [row]
    client.query.return_value = job

    executor = BigQueryExecutor(client=client)

    result = executor.execute_read_only_query(VALID_QUERY)

    assert result == [{"total_revenue": 1250}]
    client.query.assert_called_once()
    job.result.assert_called_once()


def test_rejects_invalid_query_before_execution():
    client = MagicMock()
    executor = BigQueryExecutor(client=client)

    with pytest.raises(SQLValidationError):
        executor.execute_read_only_query(
            "DELETE FROM customers WHERE customer_id = 1"
        )

    client.query.assert_not_called()


def test_applies_execution_limits():
    client = MagicMock()
    job = MagicMock()
    job.result.return_value = []
    client.query.return_value = job

    executor = BigQueryExecutor(client=client)
    executor.execute_read_only_query(VALID_QUERY)

    kwargs = client.query.call_args.kwargs

    assert kwargs["location"] == "asia-south1"
    assert kwargs["job_config"].use_legacy_sql is False
    assert kwargs["job_config"].maximum_bytes_billed == 1_000_000_000
