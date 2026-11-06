
from pathlib import Path

from google.cloud import bigquery


PROJECT_ID = "winter-sensor-474220-u4"
DATASET_ID = "datapulse_warehouse"
TABLE_ID = "api_products"
LOCATION = "asia-south1"

ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = ROOT / "data" / "processed" / "api_products.csv"

SCHEMA = [
    bigquery.SchemaField("id", "INT64"),
    bigquery.SchemaField("title", "STRING"),
    bigquery.SchemaField("description", "STRING"),
    bigquery.SchemaField("category", "STRING"),
    bigquery.SchemaField("price", "NUMERIC"),
    bigquery.SchemaField("discountPercentage", "FLOAT64"),
    bigquery.SchemaField("rating", "FLOAT64"),
    bigquery.SchemaField("stock", "INT64"),
    bigquery.SchemaField("tags", "STRING"),
    bigquery.SchemaField("brand", "STRING"),
    bigquery.SchemaField("sku", "STRING"),
    bigquery.SchemaField("weight", "FLOAT64"),
    bigquery.SchemaField("dimensions", "STRING"),
    bigquery.SchemaField("warrantyInformation", "STRING"),
    bigquery.SchemaField("shippingInformation", "STRING"),
    bigquery.SchemaField("availabilityStatus", "STRING"),
    bigquery.SchemaField("reviews", "STRING"),
    bigquery.SchemaField("returnPolicy", "STRING"),
    bigquery.SchemaField("minimumOrderQuantity", "INT64"),
    bigquery.SchemaField("meta", "STRING"),
    bigquery.SchemaField("images", "STRING"),
    bigquery.SchemaField("thumbnail", "STRING"),
]


def main():
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"API products CSV not found: {CSV_PATH}")

    client = bigquery.Client(project=PROJECT_ID)
    table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

    count_job = client.query(
        f"SELECT COUNT(*) AS total FROM `{table_ref}`",
        location=LOCATION,
    )
    existing_count = next(iter(count_job.result())).total

    if existing_count != 0:
        raise RuntimeError(
            f"API products table already contains {existing_count} rows. "
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

    if job.output_rows != 194 or table.num_rows != 194:
        raise RuntimeError("API products row-count verification failed.")

    print("API PRODUCTS LOAD SUCCESSFUL")
    print("Rows loaded:", job.output_rows)
    print("Total table rows:", table.num_rows)


if __name__ == "__main__":
    main()
