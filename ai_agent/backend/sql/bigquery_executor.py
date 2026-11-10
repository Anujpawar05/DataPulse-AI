
import time
from typing import Any, Optional

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
from ai_agent.backend.logger import get_logger, get_request_id

logger = get_logger("bigquery")


MAX_RESULT_ROWS = 1000


def _extract_job_id(job: Any) -> str:
    """Safely extract the BigQuery job ID string, handling mocks and None."""
    if job is None:
        return "unsubmitted"
    raw_id = getattr(job, "job_id", None)
    if isinstance(raw_id, str) and raw_id:
        return raw_id
    if raw_id is not None and not type(raw_id).__name__.startswith("MagicMock"):
        return str(raw_id)
    return "unknown"


def _extract_int_metric(job: Any, attr_name: str) -> Optional[int]:
    """Safely extract integer metric from job, ignoring MagicMocks or None."""
    if job is None:
        return None
    val = getattr(job, attr_name, None)
    if isinstance(val, int) and not isinstance(val, bool):
        return val
    return None


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
        start_time = time.perf_counter()

        logger.debug(
            f"[{get_request_id()}] BigQuery query submitted (location={BIGQUERY_LOCATION})",
            extra={"event": "bigquery_query_submitted", "location": BIGQUERY_LOCATION},
        )

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
            result_dicts = [dict(row.items()) for row in rows]
            duration_ms = (time.perf_counter() - start_time) * 1000

            job_id = _extract_job_id(job)
            bytes_billed = _extract_int_metric(job, "total_bytes_billed")
            bytes_processed = _extract_int_metric(job, "total_bytes_processed")
            slot_ms = _extract_int_metric(job, "slot_millis")
            row_count = len(result_dicts)

            logger.info(
                f"[{get_request_id()}] BigQuery query completed - job_id={job_id}, rows={row_count}, "
                f"bytes_billed={bytes_billed}, bytes_processed={bytes_processed}, slot_ms={slot_ms} ({duration_ms:.1f}ms)",
                extra={
                    "event": "bigquery_query_success",
                    "job_id": job_id,
                    "rows_returned": row_count,
                    "bytes_billed": bytes_billed,
                    "bytes_processed": bytes_processed,
                    "slot_ms": slot_ms,
                    "duration_ms": duration_ms,
                },
            )
            return result_dicts

        except TimeoutError as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            job_id = _extract_job_id(job)
            logger.error(
                f"[{get_request_id()}] BigQuery query failed - job_id={job_id}, error=TimeoutError ({duration_ms:.1f}ms)",
                extra={
                    "event": "bigquery_query_failed",
                    "job_id": job_id,
                    "error_class": "TimeoutError",
                    "duration_ms": duration_ms,
                },
            )
            if job is not None:
                try:
                    job.cancel()
                except GoogleAPICallError:
                    pass

            raise BigQueryExecutionError(
                "The query exceeded the allowed execution time."
            ) from exc

        except BadRequest as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            job_id = _extract_job_id(job)
            logger.error(
                f"[{get_request_id()}] BigQuery query failed - job_id={job_id}, error=BadRequest ({duration_ms:.1f}ms)",
                extra={
                    "event": "bigquery_query_failed",
                    "job_id": job_id,
                    "error_class": "BadRequest",
                    "duration_ms": duration_ms,
                },
            )
            raise BigQueryExecutionError(
                "BigQuery rejected the SQL query or its execution settings."
            ) from exc

        except Forbidden as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            job_id = _extract_job_id(job)
            logger.error(
                f"[{get_request_id()}] BigQuery query failed - job_id={job_id}, error=Forbidden ({duration_ms:.1f}ms)",
                extra={
                    "event": "bigquery_query_failed",
                    "job_id": job_id,
                    "error_class": "Forbidden",
                    "duration_ms": duration_ms,
                },
            )
            raise BigQueryExecutionError(
                "BigQuery access was denied. Check the account's permissions."
            ) from exc

        except GoogleAPICallError as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            job_id = _extract_job_id(job)
            logger.error(
                f"[{get_request_id()}] BigQuery query failed - job_id={job_id}, error=GoogleAPICallError ({duration_ms:.1f}ms)",
                extra={
                    "event": "bigquery_query_failed",
                    "job_id": job_id,
                    "error_class": "GoogleAPICallError",
                    "duration_ms": duration_ms,
                },
            )
            raise BigQueryExecutionError(
                "BigQuery is temporarily unavailable."
            ) from exc
