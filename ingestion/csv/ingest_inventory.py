import pandas as pd
from pathlib import Path


# Project paths
PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_FILE = PROJECT_ROOT / "data" / "sample" / "inventory_corrected.csv"
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "csv"

REQUIRED_COLUMNS = [
    "product_id",
    "warehouse",
    "stock_quantity",
    "reorder_level"
]


def ingest_inventory():

    print("\n========== INVENTORY CSV INGESTION ==========")

    # Check input file
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"CSV file not found: {INPUT_FILE}")

    # Read CSV
    df = pd.read_csv(INPUT_FILE)

    print("Input rows:", len(df))

    # Validate required columns
    missing_columns = set(REQUIRED_COLUMNS) - set(df.columns)

    if missing_columns:
        raise ValueError(f"Missing columns: {missing_columns}")

    df = df[REQUIRED_COLUMNS].copy()

    # Validate null values
    if df.isnull().any().any():
        raise ValueError("CSV contains missing values.")

    # Validate numeric values
    numeric_columns = ["product_id", "stock_quantity", "reorder_level"]

    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors="raise")

    # Validate integer values
    for column in numeric_columns:
        if not (df[column] % 1 == 0).all():
            raise ValueError(f"{column} must contain integer values.")

        df[column] = df[column].astype("int64")

    # Validate non-negative values
    if (df[["stock_quantity", "reorder_level"]] < 0).any().any():
        raise ValueError("Stock quantity and reorder level cannot be negative.")

    if (df["product_id"] <= 0).any():
        raise ValueError("Product IDs must be positive.")

    # Validate warehouse names
    if not df["warehouse"].astype(str).str.strip().ne("").all():
        raise ValueError("Warehouse names cannot be empty.")

    df["warehouse"] = df["warehouse"].astype(str).str.strip()

    # Validate duplicate product/warehouse combinations
    if df.duplicated(subset=["product_id", "warehouse"]).any():
        raise ValueError("Duplicate product and warehouse combinations found.")

    # Save output
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    output_file = OUTPUT_DIR / "inventory_v2.csv"

    df.to_csv(output_file, index=False, encoding="utf-8")

    # Verify output
    exported_df = pd.read_csv(output_file)

    if len(exported_df) != len(df):
        raise RuntimeError("Input and output row counts do not match.")

    print("Validation: PASSED")
    print("Output rows:", len(exported_df))
    print("Output file:", output_file)
    print("\nCSV INGESTION SUCCESSFUL")


if __name__ == "__main__":
    ingest_inventory()