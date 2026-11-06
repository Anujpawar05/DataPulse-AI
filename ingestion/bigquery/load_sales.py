
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from google.cloud import bigquery


PROJECT_ID = "winter-sensor-474220-u4"
DATASET_ID = "datapulse_warehouse"
TABLE_ID = "sales"
LOCATION = "asia-south1"

ROOT = Path(__file__).resolve().parents[2]
SOURCE_CSV = ROOT / "data" / "processed" / "sales.csv"
READY_DIR = ROOT / "data" / "processed" / "bigquery_ready"
READY_CSV = READY_DIR / "sales.csv"

INTEGER_COLUMNS = {"sale_id", "order_id", "product_id", "line_number", "quantity"}

SCHEMA = [
    bigquery.SchemaField("sale_id", "INT64"),
    bigquery.SchemaField("order_id", "INT64"),
    bigquery.SchemaField("product_id", "INT64"),
    bigquery.SchemaField("line_number", "INT64"),
    bigquery.SchemaField("quantity", "INT64"),
    bigquery.SchemaField("unit_price", "NUMERIC"),
    bigquery.SchemaField("unit_cost", "NUMERIC"),
    bigquery.SchemaField("discount_amount", "NUMERIC"),
]


def prepare_csv():
    if not SOURCE_CSV.exists():
        raise FileNotFoundError(f"Sales CSV not found: {SOURCE_CSV}")

    READY_DIR.mkdir(parents=True, exist_ok=True)

    with SOURCE_CSV.open("r", newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)

        if reader.fieldnames != [field.name for field in SCHEMA]:
            raise ValueError(f"Unexpected CSV columns: {reader.fieldnames}")

        with READY_CSV.open("w", newline="", encoding="utf-8") as output:
            writer = csv.DictWriter(output, fieldnames=reader.fieldnames)
            writer.writeheader()
            row_count = 0

            for row in reader:
                for column in INTEGER_COLUMNS:
                    try:
                        value = Decimal(row[column].strip())
                    except InvalidOperation as exc:
                        raise ValueError(
                            f"Invalid integer in {column}: {row[column]}"
                        ) from exc

                    if value != value.to_integral_value():
                        raise ValueError(
                            f"Non-integer value in {column}: {row[column]}"
                        )

                    row[column] = str(int(value))

                writer.writerow(row)
                row_count += 1

    return row_count


def main():
    expected_rows = prepare_csv()

    if expected_rows != 5000:
        raise RuntimeError(f"Expected 5000 sales rows, found {expected_rows}")

    client = bigquery.Client(project=PROJECT_ID)
    table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

    count_job = client.query(
        f"SELECT COUNT(*) AS total FROM `{table_ref}`",
        location=LOCATION,
    )
    existing_count = next(iter(count_job.result())).total

    if existing_count != 0:
        raise RuntimeError(
            f"Sales table already contains {existing_count} rows. "
            "Upload stopped to prevent duplicates."
        )

    config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        schema=SCHEMA,
        write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
        max_bad_records=0,
    )

    with READY_CSV.open("rb") as file:
        job = client.load_table_from_file(
            file,
            table_ref,
            job_config=config,
            location=LOCATION,
        )

    job.result()
    table = client.get_table(table_ref)

    if job.output_rows != expected_rows or table.num_rows != expected_rows:
        raise RuntimeError("Sales row-count verification failed.")

    print("SALES LOAD SUCCESSFUL")
    print("Rows prepared:", expected_rows)
    print("Rows loaded:", job.output_rows)
    print("Total table rows:", table.num_rows)


if __name__ == "__main__":
    main()
