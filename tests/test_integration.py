import json
from pathlib import Path

import pandas as pd
import pytest


ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"


@pytest.fixture(scope="module")
def postgres_data():
    base = RAW / "postgres"

    folders = [p for p in base.iterdir() if p.is_dir()]
    assert folders, "No PostgreSQL extraction folder found"

    latest = max(folders, key=lambda p: p.stat().st_mtime)

    return {
        name: pd.read_csv(latest / f"{name}.csv")
        for name in ["customers", "products", "orders", "payments", "sales"]
    }


@pytest.fixture(scope="module")
def api_data():
    result = {}

    for name in ["products", "users", "carts"]:
        path = RAW / "api" / f"{name}.json"

        with open(path, encoding="utf-8") as file:
            result[name] = json.load(file)

    return result


def test_postgres_record_counts(postgres_data):
    expected = {
        "customers": 1000,
        "products": 100,
        "orders": 5000,
        "payments": 5000,
        "sales": 5000,
    }

    for name, count in expected.items():
        assert len(postgres_data[name]) == count


def test_postgres_primary_keys_are_unique(postgres_data):
    primary_keys = {
        "customers": "customer_id",
        "products": "product_id",
        "orders": "order_id",
        "payments": "payment_id",
        "sales": "sale_id",
    }

    for name, column in primary_keys.items():
        df = postgres_data[name]

        assert df[column].notna().all()
        assert df[column].is_unique


def test_postgres_foreign_keys(postgres_data):
    customers = set(postgres_data["customers"]["customer_id"])
    products = set(postgres_data["products"]["product_id"])
    orders = set(postgres_data["orders"]["order_id"])

    assert postgres_data["orders"]["customer_id"].isin(customers).all()
    assert postgres_data["payments"]["order_id"].isin(orders).all()
    assert postgres_data["sales"]["order_id"].isin(orders).all()
    assert postgres_data["sales"]["product_id"].isin(products).all()


def test_inventory_data(postgres_data):
    inventory_path = RAW / "csv" / "inventory_v2.csv"
    inventory = pd.read_csv(inventory_path)

    assert len(inventory) == 10

    required = {
        "product_id",
        "warehouse",
        "stock_quantity",
        "reorder_level",
    }

    assert required.issubset(inventory.columns)
    assert inventory["product_id"].isin(
        postgres_data["products"]["product_id"]
    ).all()

    assert (inventory["stock_quantity"] >= 0).all()
    assert (inventory["reorder_level"] >= 0).all()

    assert not inventory.duplicated(
        subset=["product_id", "warehouse"]
    ).any()


def test_api_record_counts(api_data):
    expected = {
        "products": 194,
        "users": 208,
        "carts": 208,
    }

    for name, count in expected.items():
        payload = api_data[name]

        assert payload["total"] == count
        assert payload["count"] == count
        assert len(payload[name]) == count


def test_api_ids_are_unique(api_data):
    for name in ["products", "users", "carts"]:
        records = api_data[name][name]
        ids = [record["id"] for record in records]

        assert len(ids) == len(set(ids))
        assert None not in ids


def test_api_cart_relationships(api_data):
    product_ids = {
        product["id"]
        for product in api_data["products"]["products"]
    }

    user_ids = {
        user["id"]
        for user in api_data["users"]["users"]
    }

    for cart in api_data["carts"]["carts"]:
        assert cart["userId"] in user_ids

        for product in cart["products"]:
            assert product["id"] in product_ids
            assert product["quantity"] > 0


def test_api_user_privacy_whitelist(api_data):
    allowed_fields = {
        "id",
        "firstName",
        "lastName",
        "email",
        "username",
        "age",
        "gender",
        "address",
    }

    for user in api_data["users"]["users"]:
        assert set(user.keys()).issubset(allowed_fields)


def test_processed_files_exist():
    expected_files = [
        "customers.csv",
        "products.csv",
        "orders.csv",
        "payments.csv",
        "sales.csv",
        "inventory.csv",
        "api_products.csv",
        "api_users.csv",
        "api_carts.csv",
    ]

    for filename in expected_files:
        assert (PROCESSED / filename).is_file(), (
            f"Missing processed file: {filename}"
        )


def test_processed_record_counts():
    expected = {
        "customers.csv": 1000,
        "products.csv": 100,
        "orders.csv": 5000,
        "payments.csv": 5000,
        "sales.csv": 5000,
        "inventory.csv": 10,
        "api_products.csv": 194,
        "api_users.csv": 208,
        "api_carts.csv": 208,
    }

    for filename, count in expected.items():
        df = pd.read_csv(PROCESSED / filename)
        assert len(df) == count, f"Unexpected row count in {filename}"