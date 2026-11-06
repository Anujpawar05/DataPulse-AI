
from pathlib import Path

from google.cloud import bigquery

PROJECT_ID = "winter-sensor-474220-u4"
DATASET_ID = "datapulse_warehouse"
TABLE_ID = "payments"
LOCATION = "asia-south1"

ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "data" / "processed" / "payments.csv"

SCHEMA = [
    bigquery.SchemaField("payment_id", "INT64"),
    bigquery.SchemaField("order_id", "INT64"),
    bigquery.SchemaField("payment_method", "STRING"),
    bigquery.SchemaField("amount", "NUMERIC"),
    bigquery.SchemaField("payment_status", "STRING"),
    bigquery.SchemaField("transaction_reference", "STRING"),
    bigquery.SchemaField("payment_date", "TIMESTAMP"),
    bigquery.SchemaField("created_at", "TIMESTAMP"),
]


def main():
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Payments CSV not found: {CSV_PATH}")

    client = bigquery.Client(project=PROJECT_ID)
    table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

    query_job = client.query(
        f"SELECT COUNT(*) AS total FROM `{table_ref}`",
        location=LOCATION,
    )
    existing_count = next(iter(query_job.result())).total

    if existing_count != 0:
        raise RuntimeError(
            f"Payments table already contains {existing_count} rows. "
            "Upload stopped to prevent duplicates."
        )

    config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        schema=SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        max_bad_records=0,
    )

    with CSV_PATH.open("rb") as file:
        job = client.load_table_from_file(
            file,
            table_ref,
            job_config=config,
            location=LOCATION,
        )

    job.result()

    table = client.get_table(table_ref)

    if job.output_rows != 5000 or table.num_rows != 5000:
        raise RuntimeError("Payments row-count verification failed.")

    print("PAYMENTS LOAD SUCCESSFUL")
    print("Rows loaded:", job.output_rows)
    print("Total table rows:", table.num_rows)


if __name__ == "__main__":
    main()
