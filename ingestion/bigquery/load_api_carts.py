
from pathlib import Path

from google.cloud import bigquery


PROJECT_ID = "winter-sensor-474220-u4"
DATASET_ID = "datapulse_warehouse"
TABLE_ID = "api_carts"
LOCATION = "asia-south1"

ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "data" / "processed" / "api_carts.csv"

SCHEMA = [
    bigquery.SchemaField("id", "INT64"),
    bigquery.SchemaField("products", "STRING"),
    bigquery.SchemaField("total", "NUMERIC"),
    bigquery.SchemaField("discountedTotal", "NUMERIC"),
    bigquery.SchemaField("userId", "INT64"),
    bigquery.SchemaField("totalProducts", "INT64"),
    bigquery.SchemaField("totalQuantity", "INT64"),
]


def main():
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"API carts CSV not found: {CSV_PATH}")

    client = bigquery.Client(project=PROJECT_ID)
    table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

    count_job = client.query(
        f"SELECT COUNT(*) AS total FROM `{table_ref}`",
        location=LOCATION,
    )

    existing_count = next(iter(count_job.result())).total

    if existing_count != 0:
        raise RuntimeError(
            f"API carts table already contains {existing_count} rows. "
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

    if job.output_rows != 208 or table.num_rows != 208:
        raise RuntimeError("API carts row-count verification failed.")

    print("API CARTS LOAD SUCCESSFUL")
    print("Rows loaded:", job.output_rows)
    print("Total table rows:", table.num_rows)


if __name__ == "__main__":
    main()
