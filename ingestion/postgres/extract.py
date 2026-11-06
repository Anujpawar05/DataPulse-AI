import os
import sys
import csv
from pathlib import Path
from datetime import datetime

import psycopg
from psycopg import sql
from dotenv import load_dotenv


# Project paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_PATH = PROJECT_ROOT / ".env"
OUTPUT_BASE = PROJECT_ROOT / "data" / "raw" / "postgres"

# Load database configuration
load_dotenv(dotenv_path=ENV_PATH)

TABLES = [
    "customers",
    "products",
    "orders",
    "payments",
    "sales"
]


def get_database_connection():
    """Create a PostgreSQL connection using .env settings."""

    required_variables = [
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "DB_USER",
        "DB_PASSWORD"
    ]

    missing = [
        variable for variable in required_variables
        if not os.getenv(variable)
    ]

    if missing:
        raise ValueError(
            f"Missing environment variables: {', '.join(missing)}"
        )

    return psycopg.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        connect_timeout=5
    )


def count_csv_rows(file_path):
    """Count CSV data rows, excluding the header."""

    with open(file_path, "r", encoding="utf-8", newline="") as file:
        reader = csv.reader(file)
        next(reader, None)  # Skip header
        return sum(1 for _ in reader)


def extract_tables():
    """Export PostgreSQL tables to timestamped CSV files."""

    run_timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_directory = OUTPUT_BASE / f"run_{run_timestamp}"
    output_directory.mkdir(parents=True, exist_ok=False)

    print("\n========== DATAPULSE POSTGRESQL EXTRACTION ==========")
    print("Output directory:", output_directory)

    try:
        with get_database_connection() as conn:
            with conn.cursor() as cur:

                # Keep all table exports consistent within one read-only snapshot.
                cur.execute(
                    "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"
                )

                for table in TABLES:
                    print(f"\nExtracting: {table}")

                    # Get source row count.
                    cur.execute(
                        sql.SQL("SELECT COUNT(*) FROM public.{}").format(
                            sql.Identifier(table)
                        )
                    )
                    source_count = cur.fetchone()[0]

                    output_file = output_directory / f"{table}.csv"

                    # Export table using PostgreSQL COPY.
                    copy_query = sql.SQL(
                        "COPY (SELECT * FROM public.{}) "
                        "TO STDOUT WITH (FORMAT CSV, HEADER TRUE, ENCODING 'UTF8')"
                    ).format(sql.Identifier(table))

                    with open(output_file, "wb") as file:
                        with cur.copy(copy_query) as copy:
                            for block in copy:
                                file.write(block)

                    # Verify exported CSV row count.
                    exported_count = count_csv_rows(output_file)

                    print("Source rows:", source_count)
                    print("Exported rows:", exported_count)
                    print("File:", output_file.name)

                    if source_count != exported_count:
                        raise RuntimeError(
                            f"Row count mismatch for {table}: "
                            f"source={source_count}, exported={exported_count}"
                        )

                    print("Validation: PASSED")

        print("\n========== EXTRACTION SUCCESSFUL ==========")
        print("All five tables exported and validated.")
        print("Location:", output_directory)

    except Exception as error:
        print("\nEXTRACTION FAILED")
        print("Error:", error)
        sys.exit(1)


if __name__ == "__main__":
    extract_tables()