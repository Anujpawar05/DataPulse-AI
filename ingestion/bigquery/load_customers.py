
from pathlib import Path

from google.cloud import bigquery


PROJECT_ID = "winter-sensor-474220-u4"
DATASET_ID = "datapulse_warehouse"
TABLE_ID = "customers"
LOCATION = "asia-south1"

ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "data" / "processed" / "customers.csv"

SCHEMA = [
    bigquery.SchemaField("customer_id", "INT64"),
    bigquery.SchemaField("full_name", "STRING"),
    bigquery.SchemaField("email", "STRING"),
    bigquery.SchemaField("city", "STRING"),
    bigquery.SchemaField("state", "STRING"),
    bigquery.SchemaField("country", "STRING"),
    bigquery.SchemaField("registration_date", "DATE"),
    bigquery.SchemaField("created_at", "TIMESTAMP"),
]


def main():
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"Customers CSV not found: {CSV_PATH}")

    client = bigquery.Client(project=PROJECT_ID)
    table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

    count_job = client.query(
        f"SELECT COUNT(*) AS total FROM `{table_ref}`",
        location=LOCATION,
    )
    existing_count = next(iter(count_job.result())).total

    if existing_count != 0:
        raise RuntimeError(
            f"Customers table already contains {existing_count} rows. "
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

    if job.output_rows != 1000 or table.num_rows != 1000:
        raise RuntimeError("Customers row-count verification failed.")

    print("CUSTOMERS LOAD SUCCESSFUL")
    print("Rows loaded:", job.output_rows)
    print("Total table rows:", table.num_rows)


if __name__ == "__main__":
    main()
