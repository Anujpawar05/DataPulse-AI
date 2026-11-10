import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict

from airflow import DAG

try:
    from airflow.providers.standard.operators.bash import BashOperator
except ImportError:
    from airflow.operators.bash import BashOperator

logger = logging.getLogger("airflow.task")

PROJECT_ROOT = "/opt/datapulse/project"

SAFE_RUN_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-\.:\+]+$")


def _sanitize_run_id(raw_run_id: Any) -> str:
    """Sanitize run_id to safe alphanumeric and symbol characters, truncated to 64 chars."""
    if not raw_run_id:
        return "unknown_run"
    str_id = str(raw_run_id)[:64]
    if SAFE_RUN_ID_REGEX.match(str_id):
        return str_id
    return re.sub(r"[^a-zA-Z0-9_\-\.:\+]", "_", str_id)


def _extract_callback_metadata(context: Dict[str, Any]) -> Dict[str, Any]:
    """Safely extract execution context metadata without sensitive values."""
    ti = context.get("task_instance")
    task_id = getattr(ti, "task_id", None) or "unknown_task"
    dag_id = getattr(ti, "dag_id", None) or context.get("dag", None)
    if hasattr(dag_id, "dag_id"):
        dag_id = dag_id.dag_id
    dag_id = str(dag_id or "unknown_dag")

    run_id = _sanitize_run_id(context.get("run_id") or getattr(ti, "run_id", None))
    try_number = getattr(ti, "try_number", None) or 1

    exc = context.get("exception")
    error_class = type(exc).__name__ if exc else "None"

    return {
        "dag_id": dag_id,
        "task_id": task_id,
        "run_id": run_id,
        "try_number": try_number,
        "error_class": error_class,
    }


def sanitized_task_retry_callback(context: Dict[str, Any]) -> None:
    """
    Sanitized callback invoked when a task fails and initiates an automated retry.
    Never logs raw exception messages, commands, credentials, or SQL text.
    """
    try:
        meta = _extract_callback_metadata(context)
        logger.warning(
            f"[pipeline_retry] DAG={meta['dag_id']} run_id={meta['run_id']} "
            f"task_id={meta['task_id']} try={meta['try_number']} error_class={meta['error_class']}"
        )
    except Exception:
        # Callbacks must never alter or disrupt the underlying task lifecycle
        pass


def sanitized_task_failure_callback(context: Dict[str, Any]) -> None:
    """
    Sanitized callback invoked when a task exhausts all retry attempts and fails.
    Never logs raw exception messages, commands, credentials, or SQL text.
    """
    try:
        meta = _extract_callback_metadata(context)
        logger.error(
            f"[pipeline_failure] DAG={meta['dag_id']} run_id={meta['run_id']} "
            f"task_id={meta['task_id']} try={meta['try_number']} error_class={meta['error_class']}"
        )
    except Exception:
        # Callbacks must never alter or disrupt the underlying task lifecycle
        pass


# Base default arguments applied to all tasks
default_args = {
    "owner": "datapulse",
    "depends_on_past": False,
    "retry_delay": timedelta(seconds=30),
    "retry_exponential_backoff": 2.0,
    "max_retry_delay": timedelta(minutes=5),
    "execution_timeout": timedelta(minutes=10),
    "on_retry_callback": sanitized_task_retry_callback,
    "on_failure_callback": sanitized_task_failure_callback,
}

# ==============================================================================
# DAG Timeout Calculation (Worst-Case with Airflow Exponential Backoff & Jitter):
#
# Airflow Backoff Formula:
#   delay = min_backoff + (ti_hash % min_backoff)
#   where min_backoff = ceil(retry_delay * (multiplier ** (try_number - 1)))
#   capped at max_retry_delay (5m = 300s).
#
# Stage 1: Parallel Extraction (max of postgres, api, inventory):
#   - postgres_extraction / dummyjson_api_ingestion:
#       Execution: 3 attempts x 5m timeout = 15m (900s)
#       Retry Delay 1 (after try 1): min_backoff=30s, max jitter=+29s -> up to 59s
#       Retry Delay 2 (after try 2): min_backoff=60s, max jitter=+59s -> up to 119s
#       Total retry wait: 59s + 119s = 178s (~3.0m)
#       Task total: 15m + 3m = 18m (17m 58s)
#   - inventory_csv_ingestion:
#       Execution: 2 attempts x 3m timeout = 6m (360s)
#       Retry Delay 1 (after try 1): up to 59s (~1.0m)
#       Task total: 6m + 1m = 7m
#   Stage 1 parallel duration = max(18m, 18m, 7m) = ~18.0m (17m 58s)
#
# Stage 2: Sequential Validation:
#   - data_validation:
#       Execution: 2 attempts x 5m timeout = 10m (600s)
#       Retry Delay 1 (after try 1): min_backoff=30s, max jitter=+29s -> up to 59s (~1.0m)
#       Stage 2 duration = 10m + 1m = ~11.0m (10m 59s)
#
# Combined Execution + Retry Backoff:
#   17m 58s (Stage 1) + 10m 59s (Stage 2) = 28m 57s (~29.0m)
#
# Operational Buffer:
#   6m 03s buffer for Celery worker dispatch, container process init, and task state transitions.
#
# Total DAG Timeout:
#   28m 57s + 6m 03s = 35 minutes (2100 seconds)
# ==============================================================================
DAG_RUN_TIMEOUT = timedelta(minutes=35)

with DAG(
    dag_id="datapulse_ingestion_pipeline",
    description="Orchestrates DataPulse PostgreSQL, CSV, API ingestion and validation",
    start_date=datetime(2026, 11, 3),
    schedule=None,
    catchup=False,
    default_args=default_args,
    dagrun_timeout=DAG_RUN_TIMEOUT,
    tags=["datapulse", "ingestion"],
) as dag:

    postgres_extraction = BashOperator(
        task_id="postgres_extraction",
        bash_command=f"python {PROJECT_ROOT}/ingestion/postgres/extract.py",
        retries=2,
        execution_timeout=timedelta(minutes=5),
    )

    inventory_ingestion = BashOperator(
        task_id="inventory_csv_ingestion",
        bash_command=f"python {PROJECT_ROOT}/ingestion/csv/ingest_inventory.py",
        retries=1,
        execution_timeout=timedelta(minutes=3),
    )

    api_ingestion = BashOperator(
        task_id="dummyjson_api_ingestion",
        bash_command=f"python {PROJECT_ROOT}/ingestion/api/ingest_dummyjson.py",
        retries=2,
        execution_timeout=timedelta(minutes=5),
    )

    data_validation = BashOperator(
        task_id="data_validation",
        bash_command=f"python {PROJECT_ROOT}/ingestion/validate_data.py",
        retries=1,
        execution_timeout=timedelta(minutes=5),
    )

    [
        postgres_extraction,
        inventory_ingestion,
        api_ingestion,
    ] >> data_validation
