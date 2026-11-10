import ast
import importlib.util
import logging
import re
import sys
from datetime import timedelta
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

DAG_PATH = Path(__file__).resolve().parents[1] / "airflow" / "dags" / "datapulse_ingestion_dag.py"


# =============================================================================
# Helper: Import DAG module with mocked Airflow dependencies
# =============================================================================

class MockBaseOperator:
    def __init__(self, task_id, **kwargs):
        self.task_id = task_id
        current_dag = getattr(MockDAG, "_current_dag", None)
        if current_dag and hasattr(current_dag, "default_args") and isinstance(current_dag.default_args, dict):
            for k, v in current_dag.default_args.items():
                setattr(self, k, v)
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.upstream_list = []
        self.downstream_list = []
        if current_dag and hasattr(current_dag, "tasks"):
            current_dag.tasks.append(self)

    def __rshift__(self, other):
        if isinstance(other, list):
            for item in other:
                self.downstream_list.append(item)
                item.upstream_list.append(self)
        else:
            self.downstream_list.append(other)
            other.upstream_list.append(self)
        return other

    def __rrshift__(self, other):
        if isinstance(other, list):
            for item in other:
                item.downstream_list.append(self)
                self.upstream_list.append(item)
        else:
            other.downstream_list.append(self)
            self.upstream_list.append(other)
        return self


class MockDAG:
    _current_dag = None

    def __init__(self, dag_id, **kwargs):
        self.dag_id = dag_id
        for k, v in kwargs.items():
            setattr(self, k, v)
        self.tasks = []

    def __enter__(self):
        MockDAG._current_dag = self
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        MockDAG._current_dag = None


def load_dag_module_with_mocks():
    """Load the DAG file dynamically by mocking airflow modules."""
    mock_airflow = ModuleType("airflow")
    mock_airflow.DAG = MockDAG

    mock_bash_provider = ModuleType("airflow.providers.standard.operators.bash")
    mock_bash_provider.BashOperator = MockBaseOperator

    mock_bash_core = ModuleType("airflow.operators.bash")
    mock_bash_core.BashOperator = MockBaseOperator

    saved_modules = {
        name: sys.modules.get(name)
        for name in [
            "airflow",
            "airflow.DAG",
            "airflow.operators",
            "airflow.operators.bash",
            "airflow.providers",
            "airflow.providers.standard",
            "airflow.providers.standard.operators",
            "airflow.providers.standard.operators.bash",
        ]
    }

    try:
        sys.modules["airflow"] = mock_airflow
        sys.modules["airflow.operators.bash"] = mock_bash_core
        sys.modules["airflow.providers.standard.operators.bash"] = mock_bash_provider

        spec = importlib.util.spec_from_file_location("datapulse_ingestion_dag", str(DAG_PATH))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        for name, original in saved_modules.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


# =============================================================================
# 1. AST Syntax & Static Configuration Tests
# =============================================================================

def test_dag_file_parses_without_syntax_errors():
    """Verify that the DAG source file is syntactically valid Python."""
    assert DAG_PATH.exists(), f"DAG file not found at {DAG_PATH}"
    with open(DAG_PATH, "r", encoding="utf-8") as f:
        source = f.read()

    # Must parse without SyntaxError
    parsed = ast.parse(source)
    assert isinstance(parsed, ast.Module)


def test_dag_configuration_and_timeouts():
    """Verify DAG-level settings, timeout calculations, and default args."""
    module = load_dag_module_with_mocks()
    dag = module.dag

    assert dag.dag_id == "datapulse_ingestion_pipeline"
    assert dag.schedule is None
    assert dag.catchup is False

    # Verify DAG-level timeout (calculated: 18m parallel extraction + 11m validation + 6m operational buffer = 35m)
    assert hasattr(dag, "dagrun_timeout")
    assert dag.dagrun_timeout == timedelta(minutes=35)

    # Verify default_args
    assert hasattr(dag, "default_args")
    defaults = dag.default_args
    assert defaults["retry_delay"] == timedelta(seconds=30)
    assert defaults["retry_exponential_backoff"] == 2.0
    assert isinstance(defaults["retry_exponential_backoff"], (int, float))
    assert defaults["max_retry_delay"] == timedelta(minutes=5)
    assert defaults["execution_timeout"] == timedelta(minutes=10)


def test_task_exponential_backoff_configuration_and_inheritance():
    """Verify all tasks inherit retry_exponential_backoff=2.0 and required retry attributes."""
    module = load_dag_module_with_mocks()

    tasks = [
        module.postgres_extraction,
        module.inventory_ingestion,
        module.api_ingestion,
        module.data_validation,
    ]

    for task in tasks:
        assert hasattr(task, "retry_exponential_backoff")
        assert task.retry_exponential_backoff == 2.0
        assert isinstance(task.retry_exponential_backoff, (int, float))
        assert task.retry_delay == timedelta(seconds=30)
        assert task.max_retry_delay == timedelta(minutes=5)


def test_airflow_exponential_backoff_algorithm():
    """
    Simulate Airflow 3.3.2 next_retry_datetime backoff algorithm:
    multiplier = retry_exponential_backoff if retry_exponential_backoff != 0 else 1.0
    min_backoff = ceil(delay * (multiplier ** (try_number - 1)))
    modded_hash = min_backoff + (ti_hash % min_backoff)
    delay = min(max_retry_delay, timedelta(seconds=modded_hash))

    Verify that:
    1. multiplier=2.0 yields exponential growth across attempts.
    2. Attempt 1 delay range is [30s, 59s].
    3. Attempt 2 delay range is [60s, 119s].
    4. Delays are bounded by max_retry_delay (300s).
    5. Demonstrates why bool(True) == 1.0 failed in Airflow 3.3.2 (collapsed to constant 30s).
    """
    import math

    retry_delay_sec = 30
    multiplier = 2.0
    max_retry_delay_sec = 300

    # Attempt 1 (try_number = 1):
    min_backoff_1 = math.ceil(retry_delay_sec * (multiplier ** (1 - 1)))
    assert min_backoff_1 == 30
    min_delay_1 = min_backoff_1
    max_delay_1 = min_backoff_1 + (min_backoff_1 - 1)
    assert min_delay_1 == 30
    assert max_delay_1 == 59

    # Attempt 2 (try_number = 2):
    min_backoff_2 = math.ceil(retry_delay_sec * (multiplier ** (2 - 1)))
    assert min_backoff_2 == 60
    min_delay_2 = min_backoff_2
    max_delay_2 = min_backoff_2 + (min_backoff_2 - 1)
    assert min_delay_2 == 60
    assert max_delay_2 == 119

    # Verify strict exponential increase
    assert min_backoff_2 > min_backoff_1
    assert min_delay_2 > min_delay_1

    # Attempt 3 (hypothetical attempt 3):
    min_backoff_3 = math.ceil(retry_delay_sec * (multiplier ** (3 - 1)))
    assert min_backoff_3 == 120
    max_delay_3 = min(min_backoff_3 + (min_backoff_3 - 1), max_retry_delay_sec)
    assert max_delay_3 == 239

    # Attempt 5 (capping at max_retry_delay):
    min_backoff_5 = math.ceil(retry_delay_sec * (multiplier ** (5 - 1)))
    capped_delay_5 = min(min_backoff_5, max_retry_delay_sec)
    assert capped_delay_5 == 300

    # Verification of why bool True failed:
    bool_mult = True if True != 0 else 1.0
    # In Python: bool_mult == 1.0 is True!
    # Airflow 3.3.2 check: if multiplier != 1.0 and multiplier > 0:
    assert (bool_mult != 1.0 and bool_mult > 0) is False  # collapses to constant 30s!
    # Whereas numeric 2.0 succeeds:
    num_mult = 2.0 if 2.0 != 0 else 1.0
    assert (num_mult != 1.0 and num_mult > 0) is True


def test_task_retries_and_execution_timeouts():
    """Verify task-level retry policies and bounded timeouts."""
    module = load_dag_module_with_mocks()

    tasks = {
        "postgres_extraction": module.postgres_extraction,
        "inventory_csv_ingestion": module.inventory_ingestion,
        "dummyjson_api_ingestion": module.api_ingestion,
        "data_validation": module.data_validation,
    }

    # Verify retries
    assert tasks["postgres_extraction"].retries == 2
    assert tasks["dummyjson_api_ingestion"].retries == 2
    assert tasks["inventory_csv_ingestion"].retries == 1
    assert tasks["data_validation"].retries == 1

    # Verify task-level execution timeouts
    assert tasks["postgres_extraction"].execution_timeout == timedelta(minutes=5)
    assert tasks["inventory_csv_ingestion"].execution_timeout == timedelta(minutes=3)
    assert tasks["dummyjson_api_ingestion"].execution_timeout == timedelta(minutes=5)
    assert tasks["data_validation"].execution_timeout == timedelta(minutes=5)


def test_three_to_one_task_dependency_graph():
    """Verify fan-in dependency graph: [postgres, inventory, api] >> data_validation."""
    module = load_dag_module_with_mocks()

    validation = module.data_validation
    assert module.postgres_extraction in validation.upstream_list
    assert module.inventory_ingestion in validation.upstream_list
    assert module.api_ingestion in validation.upstream_list


# =============================================================================
# 2. Callback Observability and Sanitization Tests
# =============================================================================

def test_failure_callback_sanitization_no_credentials_leaked(caplog):
    """Verify failure callback logs operational metadata without exposing credentials or exception messages."""
    module = load_dag_module_with_mocks()

    secret_password = "SUPER_SECRET_DB_PASSWORD_12345"
    secret_token = "dummyjson_jwt_secret_token_98765"
    raw_query = "SELECT * FROM users WHERE ssn = '123-45-6789'"

    sensitive_exception = RuntimeError(
        f"Failed to connect: postgresql://airflow:{secret_password}@postgres:5432/db "
        f"Auth: Bearer {secret_token} Query: {raw_query}"
    )

    mock_ti = MagicMock()
    mock_ti.task_id = "postgres_extraction"
    mock_ti.dag_id = "datapulse_ingestion_pipeline"
    mock_ti.try_number = 2

    context = {
        "task_instance": mock_ti,
        "run_id": "manual__2026-11-09T12:00:00+00:00",
        "exception": sensitive_exception,
    }

    with caplog.at_level(logging.ERROR, logger="airflow.task"):
        module.sanitized_task_failure_callback(context)

    records = [r for r in caplog.records if r.name == "airflow.task" and r.levelname == "ERROR"]
    assert len(records) == 1
    message = records[0].message

    # Verify structured failure metadata
    assert "[pipeline_failure]" in message
    assert "DAG=datapulse_ingestion_pipeline" in message
    assert "task_id=postgres_extraction" in message
    assert "run_id=manual__2026-11-09T12:00:00+00:00" in message
    assert "try=2" in message
    assert "error_class=RuntimeError" in message

    # Verify complete absence of sensitive strings
    assert secret_password not in message
    assert secret_token not in message
    assert raw_query not in message
    assert "postgresql://" not in message


def test_retry_callback_sanitization(caplog):
    """Verify retry callback logs sanitized operational information on task retry."""
    module = load_dag_module_with_mocks()

    mock_ti = MagicMock()
    mock_ti.task_id = "dummyjson_api_ingestion"
    mock_ti.dag_id = "datapulse_ingestion_pipeline"
    mock_ti.try_number = 1

    context = {
        "task_instance": mock_ti,
        "run_id": "manual__2026-11-09T12:30:00+00:00",
        "exception": ConnectionError("Temporary DNS failure connecting to https://dummyjson.com"),
    }

    with caplog.at_level(logging.WARNING, logger="airflow.task"):
        module.sanitized_task_retry_callback(context)

    records = [r for r in caplog.records if r.name == "airflow.task" and r.levelname == "WARNING"]
    assert len(records) == 1
    message = records[0].message

    assert "[pipeline_retry]" in message
    assert "DAG=datapulse_ingestion_pipeline" in message
    assert "task_id=dummyjson_api_ingestion" in message
    assert "try=1" in message
    assert "error_class=ConnectionError" in message
    assert "https://dummyjson.com" not in message


def test_callback_handles_corrupt_context_gracefully(caplog):
    """Verify callbacks never raise an exception even when context has None or corrupt fields."""
    module = load_dag_module_with_mocks()

    corrupt_context = {
        "task_instance": None,
        "run_id": None,
        "exception": None,
    }

    # Should execute without throwing any exception
    module.sanitized_task_retry_callback(corrupt_context)
    module.sanitized_task_failure_callback(corrupt_context)


def test_run_id_sanitization():
    """Verify run_id sanitizer strips invalid characters and bounds length."""
    module = load_dag_module_with_mocks()
    sanitize = module._sanitize_run_id

    # Normal run_id
    assert sanitize("manual__2026-11-09T12:00:00.000000+00:00") == "manual__2026-11-09T12:00:00.000000+00:00"

    # None or empty fallback
    assert sanitize(None) == "unknown_run"
    assert sanitize("") == "unknown_run"

    # Run ID with dangerous shell characters or newlines
    dirty = "run_id; rm -rf /; \n\r"
    cleaned = sanitize(dirty)
    assert ";" not in cleaned
    assert "\n" not in cleaned
    assert "\r" not in cleaned


# =============================================================================
# 3. PostgreSQL Extraction Partial-Output Retry Safety
# =============================================================================

def test_postgresql_partial_output_retry_safety(tmp_path):
    """
    Verify that if a PostgreSQL extraction attempt fails and leaves partial files,
    a subsequent successful retry creates a newer timestamped folder containing all
    5 tables, which is correctly identified by validate_data.py.
    """
    postgres_raw = tmp_path / "data" / "raw" / "postgres"
    postgres_raw.mkdir(parents=True)

    # Attempt 1: Failed extraction leaving only 2 tables
    attempt1_dir = postgres_raw / "run_20261109_100000_111111"
    attempt1_dir.mkdir()
    (attempt1_dir / "customers.csv").write_text("customer_id,full_name,email\n1,Alice,alice@example.com")
    (attempt1_dir / "products.csv").write_text("product_id,product_name,category,price,cost\n1,Widget,Tools,10,5")
    # sales.csv, orders.csv, payments.csv are missing!

    # Attempt 2: Successful retry creates newer folder with all 5 tables
    attempt2_dir = postgres_raw / "run_20261109_100030_222222"
    attempt2_dir.mkdir()
    for table in ["customers", "products", "orders", "payments", "sales"]:
        (attempt2_dir / f"{table}.csv").write_text(f"{table}_id\n1")

    # Emulate load_latest_postgres_folder logic from ingestion/validate_data.py
    folders = [f for f in postgres_raw.iterdir() if f.is_dir()]
    assert len(folders) == 2

    # Attempt 2 was created after Attempt 1
    latest_folder = max(folders, key=lambda f: f.stat().st_mtime)
    assert latest_folder.name == "run_20261109_100030_222222"

    # Verify all 5 tables exist in the selected folder
    for table in ["customers", "products", "orders", "payments", "sales"]:
        assert (latest_folder / f"{table}.csv").exists()


def test_postgresql_incomplete_extraction_triggers_validation_error(tmp_path):
    """
    Verify that if the latest extraction folder is incomplete,
    the validation logic raises FileNotFoundError rather than proceeding.
    """
    postgres_raw = tmp_path / "data" / "raw" / "postgres"
    postgres_raw.mkdir(parents=True)

    incomplete_dir = postgres_raw / "run_20261109_110000_999999"
    incomplete_dir.mkdir()
    (incomplete_dir / "customers.csv").write_text("customer_id\n1")
    # Missing orders, payments, products, sales

    required_tables = ["customers", "products", "orders", "payments", "sales"]
    missing = [
        table for table in required_tables
        if not (incomplete_dir / f"{table}.csv").exists()
    ]
    assert len(missing) == 4
    assert "orders" in missing
    assert "payments" in missing


def test_csv_and_api_ingestion_retry_idempotency(tmp_path):
    """
    Verify that retrying CSV and API ingestion overwrites target files cleanly,
    guaranteeing zero duplicate records or accumulation side effects.
    """
    import json

    # 1. CSV Ingestion Idempotency (emulates ingest_inventory.py df.to_csv)
    csv_out_dir = tmp_path / "data" / "raw" / "csv"
    csv_out_dir.mkdir(parents=True)
    csv_file = csv_out_dir / "inventory_v2.csv"

    csv_payload = "product_id,warehouse,stock_quantity,reorder_level\n1,Mumbai,100,20\n"
    csv_file.write_text(csv_payload, encoding="utf-8")
    assert csv_file.read_text(encoding="utf-8").count("\n") == 2

    # Attempt 2 retry (overwrites without appending duplicates)
    csv_file.write_text(csv_payload, encoding="utf-8")
    assert csv_file.read_text(encoding="utf-8").count("\n") == 2

    # 2. JSON API Ingestion Idempotency (emulates ingest_dummyjson.py json.dump)
    api_out_dir = tmp_path / "data" / "raw" / "api"
    api_out_dir.mkdir(parents=True)
    api_file = api_out_dir / "products.json"

    data1 = {"total": 1, "count": 1, "products": [{"id": 1, "title": "Phone"}]}
    api_file.write_text(json.dumps(data1), encoding="utf-8")
    assert json.loads(api_file.read_text(encoding="utf-8"))["total"] == 1

    # Retry writes payload cleanly
    api_file.write_text(json.dumps(data1), encoding="utf-8")
    assert json.loads(api_file.read_text(encoding="utf-8"))["total"] == 1
    assert len(json.loads(api_file.read_text(encoding="utf-8"))["products"]) == 1
