
from datetime import datetime

from airflow import DAG
from airflow.operators.bash import BashOperator


PROJECT_ROOT = "/opt/datapulse/project"

with DAG(
    dag_id="datapulse_ingestion_pipeline",
    description="Orchestrates DataPulse PostgreSQL, CSV, API ingestion and validation",
    start_date=datetime(2026, 11, 3),
    schedule=None,
    catchup=False,
    tags=["datapulse", "ingestion"],
) as dag:

    postgres_extraction = BashOperator(
        task_id="postgres_extraction",
        bash_command=(
            f"python {PROJECT_ROOT}/ingestion/postgres/extract.py"
        ),
    )

    inventory_ingestion = BashOperator(
        task_id="inventory_csv_ingestion",
        bash_command=(
            f"python {PROJECT_ROOT}/ingestion/csv/ingest_inventory.py"
        ),
    )

    api_ingestion = BashOperator(
        task_id="dummyjson_api_ingestion",
        bash_command=(
            f"python {PROJECT_ROOT}/ingestion/api/ingest_dummyjson.py"
        ),
    )

    data_validation = BashOperator(
        task_id="data_validation",
        bash_command=(
            f"python {PROJECT_ROOT}/ingestion/validate_data.py"
        ),
    )

    [
        postgres_extraction,
        inventory_ingestion,
        api_ingestion,
    ] >> data_validation
