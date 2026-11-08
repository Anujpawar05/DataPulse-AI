
from google.cloud import bigquery
from google.api_core.exceptions import (
    BadRequest,
    Forbidden,
    GoogleAPICallError,
)

from ai_agent.backend.config import (
    BIGQUERY_PROJECT_ID,
    BIGQUERY_LOCATION,
    BIGQUERY_QUERY_TIMEOUT_SECONDS,
    BIGQUERY_MAX_BYTES_BILLED,
)

from ai_agent.backend.sql.validator import (
    validate_sql,
    SQLValidationError,
)


MAX_RESULT_ROWS = 1000


class BigQueryExecutionError(RuntimeError):
    """Raised when a BigQuery query cannot be executed safely."""


class BigQueryExecutor:
    def __init__(self, client=None):
        # Client injection also makes the executor easier to test.
        self.client = client or bigquery.Client(
            project=BIGQUERY_PROJECT_ID,
            location=BIGQUERY_LOCATION,
        )

    def execute_read_only_query(self, query: str) -> list[dict]:
        # 1. Validate SQL before submitting it.
        try:
            safe_query = validate_sql(query)
        except SQLValidationError:
            raise

        # 2. Apply execution and cost limits.
        job_config = bigquery.QueryJobConfig(
            use_legacy_sql=False,
            maximum_bytes_billed=BIGQUERY_MAX_BYTES_BILLED,
        )

        job = None

        try:
            # 3. Submit the query.
            job = self.client.query(
                safe_query,
                job_config=job_config,
                location=BIGQUERY_LOCATION,
            )

            # 4. Wait for completion and limit returned rows.
            rows = job.result(
                timeout=BIGQUERY_QUERY_TIMEOUT_SECONDS,
                max_results=MAX_RESULT_ROWS,
            )

            # 5. Convert BigQuery rows into dictionaries.
            return [dict(row.items()) for row in rows]

        except TimeoutError as exc:
            if job is not None:
                try:
                    job.cancel()
                except GoogleAPICallError:
                    pass

            raise BigQueryExecutionError(
                "The query exceeded the allowed execution time."
            ) from exc

        except BadRequest as exc:
            raise BigQueryExecutionError(
                "BigQuery rejected the SQL query or its execution settings."
            ) from exc

        except Forbidden as exc:
            raise BigQueryExecutionError(
                "BigQuery access was denied. Check the account's permissions."
            ) from exc

        except GoogleAPICallError as exc:
            raise BigQueryExecutionError(
                "BigQuery is temporarily unavailable."
            ) from exc
