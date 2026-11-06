import json
import re
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
QUARANTINE = PROCESSED / "quarantine"

PROCESSED.mkdir(parents=True, exist_ok=True)
QUARANTINE.mkdir(parents=True, exist_ok=True)


def save_results(name, valid, invalid):
    valid.to_csv(PROCESSED / f"{name}.csv", index=False)

    quarantine_file = QUARANTINE / f"{name}_invalid.json"

    if invalid:
        pd.DataFrame(invalid).to_json(
            quarantine_file,
            orient="records",
            indent=2
        )
    elif quarantine_file.exists():
        quarantine_file.unlink()

    print(
        f"{name}: {len(valid)} valid, "
        f"{len(invalid)} quarantined"
    )

def validate_table(df, name, required, primary_key):
    invalid = []
    valid = []

    for _, row in df.iterrows():
        reasons = []

        for column in required:
            if pd.isna(row[column]) or str(row[column]).strip() == "":
                reasons.append(f"Missing required field: {column}")

        if pd.notna(row[primary_key]):
            if df[primary_key].duplicated(keep=False).loc[row.name]:
                reasons.append(f"Duplicate primary key: {primary_key}")

        record = row.to_dict()

        if reasons:
            record["_reasons"] = reasons
            invalid.append(record)
        else:
            valid.append(record)

    return pd.DataFrame(valid), invalid


def load_latest_postgres_folder():
    base = RAW / "postgres"

    folders = [
        folder for folder in base.iterdir()
        if folder.is_dir()
    ]

    if not folders:
        raise FileNotFoundError(
            "No PostgreSQL extraction folder found."
        )

    return max(folders, key=lambda folder: folder.stat().st_mtime)


def validate_postgres():
    print("\n--- POSTGRESQL VALIDATION ---")

    folder = load_latest_postgres_folder()

    files = {
        "customers": ["customer_id", "full_name", "email"],
        "products": ["product_id", "product_name", "category", "price", "cost"],
        "orders": ["order_id", "customer_id", "order_date", "order_status"],
        "payments": ["payment_id", "order_id", "payment_method", "amount", "payment_status"],
        "sales": ["sale_id", "order_id", "product_id", "line_number", "quantity", "unit_price", "unit_cost"],
    }

    data = {}

    for name, required in files.items():
        path = folder / f"{name}.csv"

        if not path.exists():
            raise FileNotFoundError(f"Missing file: {path}")

        df = pd.read_csv(path)

        missing = set(required) - set(df.columns)
        if missing:
            raise ValueError(f"{name}.csv missing columns: {missing}")

        data[name] = df

    # Validate primary keys and required fields.
    primary_keys = {
        "customers": "customer_id",
        "products": "product_id",
        "orders": "order_id",
        "payments": "payment_id",
        "sales": "sale_id",
    }

    valid_data = {}
    invalid_data = {}

    for name, df in data.items():
        valid, invalid = validate_table(
            df,
            name,
            files[name],
            primary_keys[name]
        )
        valid_data[name] = valid
        invalid_data[name] = invalid

    # Foreign-key validation against valid parent records.
    relationships = [
        ("orders", "customer_id", "customers", "customer_id"),
        ("payments", "order_id", "orders", "order_id"),
        ("sales", "order_id", "orders", "order_id"),
        ("sales", "product_id", "products", "product_id"),
    ]

    for child, child_col, parent, parent_col in relationships:
        parent_ids = set(valid_data[parent][parent_col].dropna())

        remaining = []

        for _, row in valid_data[child].iterrows():
            record = row.to_dict()

            if row[child_col] not in parent_ids:
                record["_reasons"] = [
                    f"Invalid reference: {child_col} not found in {parent}"
                ]
                invalid_data[child].append(record)
            else:
                remaining.append(record)

        valid_data[child] = pd.DataFrame(
            remaining,
            columns=data[child].columns
        )

    for name in files:
        save_results(name, valid_data[name], invalid_data[name])

    return valid_data


def validate_inventory(product_ids):
    print("\n--- INVENTORY CSV VALIDATION ---")

    path = RAW / "csv" / "inventory_v2.csv"
    df = pd.read_csv(path)

    required = [
        "product_id",
        "warehouse",
        "stock_quantity",
        "reorder_level"
    ]

    if not set(required).issubset(df.columns):
        raise ValueError("Inventory CSV is missing required columns.")

    invalid = []
    valid = []
    seen = set()

    for _, row in df.iterrows():
        reasons = []

        try:
            product_id = int(row["product_id"])
            stock = int(row["stock_quantity"])
            reorder = int(row["reorder_level"])
        except (ValueError, TypeError):
            reasons.append("Invalid integer field")
            product_id = None
            stock = None
            reorder = None

        warehouse = str(row["warehouse"]).strip()

        if product_id is not None:
            if product_id <= 0:
                reasons.append("Product ID must be positive")
            if product_id not in product_ids:
                reasons.append("Product ID not found in PostgreSQL products")
            if (product_id, warehouse) in seen:
                reasons.append("Duplicate product and warehouse combination")
            seen.add((product_id, warehouse))

        if stock is not None and stock < 0:
            reasons.append("Stock quantity cannot be negative")

        if reorder is not None and reorder < 0:
            reasons.append("Reorder level cannot be negative")

        if not warehouse or warehouse.lower() == "nan":
            reasons.append("Warehouse cannot be empty")

        record = row.to_dict()

        if reasons:
            record["_reasons"] = reasons
            invalid.append(record)
        else:
            valid.append(record)

    save_results("inventory", pd.DataFrame(valid), invalid)


def load_api_file(name):
    path = RAW / "api" / f"{name}.json"

    with open(path, encoding="utf-8") as file:
        payload = json.load(file)

    if not isinstance(payload, dict) or name not in payload:
        raise ValueError(f"Invalid JSON structure: {name}.json")

    records = payload[name]

    if not isinstance(records, list):
        raise ValueError(f"{name}.json must contain a list")

    if payload.get("count") != len(records):
        raise ValueError(f"Record count mismatch in {name}.json")

    if payload.get("total") != len(records):
        raise ValueError(f"API total mismatch in {name}.json")

    return records


def validate_api():
    print("\n--- DUMMYJSON API VALIDATION ---")

    products = load_api_file("products")
    users = load_api_file("users")
    carts = load_api_file("carts")

    product_ids = {p["id"] for p in products}
    user_ids = {u["id"] for u in users}

    def check_unique(records, field):
        values = [r.get(field) for r in records]
        return len(values) == len(set(values)) and None not in values

    if not check_unique(products, "id"):
        raise ValueError("Duplicate or missing API product IDs")

    if not check_unique(users, "id"):
        raise ValueError("Duplicate or missing API user IDs")

    if not check_unique(carts, "id"):
        raise ValueError("Duplicate or missing API cart IDs")

    valid_products = []
    invalid_products = []

    for record in products:
        reasons = []

        if not record.get("title") or not record.get("category"):
            reasons.append("Missing product title or category")

        try:
            if float(record["price"]) < 0:
                reasons.append("Negative product price")
            if int(record["stock"]) < 0:
                reasons.append("Negative product stock")
        except (ValueError, TypeError, KeyError):
            reasons.append("Invalid price or stock")

        if reasons:
            invalid_products.append({**record, "_reasons": reasons})
        else:
            valid_products.append(record)

    valid_users = []
    invalid_users = []
    email_pattern = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    for record in users:
        reasons = []

        if not email_pattern.match(str(record.get("email", ""))):
            reasons.append("Invalid email")

        if reasons:
            invalid_users.append({**record, "_reasons": reasons})
        else:
            valid_users.append({
                key: record.get(key)
                for key in [
                    "id", "firstName", "lastName", "email",
                    "username", "age", "gender", "address"
                ]
            })

    valid_carts = []
    invalid_carts = []

    for record in carts:
        reasons = []

        if record.get("userId") not in user_ids:
            reasons.append("Cart user ID not found")

        cart_products = record.get("products")

        if not isinstance(cart_products, list):
            reasons.append("Cart products must be a list")
        else:
            for product in cart_products:
                if product.get("id") not in product_ids:
                    reasons.append("Cart product ID not found")
                    break

                try:
                    if int(product["quantity"]) <= 0:
                        reasons.append("Product quantity must be positive")
                except (ValueError, TypeError, KeyError):
                    reasons.append("Invalid product quantity")

        try:
            if float(record["total"]) < 0:
                reasons.append("Negative cart total")
            if float(record["discountedTotal"]) < 0:
                reasons.append("Negative discounted total")
        except (ValueError, TypeError, KeyError):
            reasons.append("Invalid cart totals")

        if reasons:
            invalid_carts.append({**record, "_reasons": reasons})
        else:
            valid_carts.append(record)

    for name, valid, invalid in [
        ("api_products", valid_products, invalid_products),
        ("api_users", valid_users, invalid_users),
        ("api_carts", valid_carts, invalid_carts),
    ]:
        save_results(name, pd.DataFrame(valid), invalid)

    print("API validation completed.")


def main():
    postgres_data = validate_postgres()

    product_ids = set(
        postgres_data["products"]["product_id"].dropna()
    )

    validate_inventory(product_ids)
    validate_api()

    print("\nDATA VALIDATION PROCESS COMPLETED.")


if __name__ == "__main__":
    main()