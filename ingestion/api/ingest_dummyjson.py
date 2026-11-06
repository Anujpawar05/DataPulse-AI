import json
import sys
from pathlib import Path

import requests


# Project configuration
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "data" / "raw" / "api"

BASE_URL = "https://dummyjson.com"
BATCH_SIZE = 100

ENDPOINTS = {
    "products": "products",
    "users": "users",
    "carts": "carts"
}

# Approved user fields
USER_FIELDS = [
    "id",
    "firstName",
    "lastName",
    "email",
    "username",
    "age",
    "gender"
]

USER_ADDRESS_FIELDS = [
    "city",
    "state",
    "country"
]


def fetch_all_records(endpoint):
    """Fetch every record using pagination."""

    records = []
    skip = 0
    total = None

    while total is None or skip < total:

        response = requests.get(
            f"{BASE_URL}/{endpoint}",
            params={
                "limit": BATCH_SIZE,
                "skip": skip
            },
            headers={"Accept": "application/json"},
            timeout=30
        )

        response.raise_for_status()
        data = response.json()

        if not isinstance(data, dict):
            raise ValueError(f"Invalid response for {endpoint}")

        if endpoint not in data or not isinstance(data[endpoint], list):
            raise ValueError(f"Missing or invalid '{endpoint}' list")

        if not isinstance(data.get("total"), int):
            raise ValueError(f"Invalid total count for {endpoint}")

        if total is None:
            total = data["total"]

        elif data["total"] != total:
            raise ValueError(f"API total changed during {endpoint} extraction")

        batch = data[endpoint]

        if not batch and skip < total:
            raise RuntimeError(f"Pagination stopped early for {endpoint}")

        records.extend(batch)
        skip += len(batch)

        print(
            f"{endpoint}: fetched {len(records)} / {total}"
        )

    if len(records) != total:
        raise RuntimeError(
            f"Count mismatch for {endpoint}: "
            f"expected {total}, received {len(records)}"
        )

    return records, total


def sanitize_users(users):
    """Keep only approved user fields."""

    sanitized = []

    for user in users:

        clean_user = {
            field: user[field]
            for field in USER_FIELDS
            if field in user
        }

        address = user.get("address", {})

        if isinstance(address, dict):
            clean_address = {
                field: address[field]
                for field in USER_ADDRESS_FIELDS
                if field in address
            }

            clean_user["address"] = clean_address

        sanitized.append(clean_user)

    return sanitized


def validate_records(endpoint, records):
    """Validate record structure and unique IDs."""

    if not records:
        raise ValueError(f"No records received for {endpoint}")

    ids = []

    for record in records:

        if not isinstance(record, dict):
            raise ValueError(f"Invalid record in {endpoint}")

        record_id = record.get("id")

        if not isinstance(record_id, int):
            raise ValueError(f"Invalid ID in {endpoint}")

        ids.append(record_id)

    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate IDs found in {endpoint}")


def save_json(endpoint, records, total):
    """Save records as UTF-8 JSON."""

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    output_file = OUTPUT_DIR / f"{endpoint}.json"

    output_data = {
        "total": total,
        "count": len(records),
        endpoint: records
    }

    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(
            output_data,
            file,
            indent=4,
            ensure_ascii=False
        )

    # Verify saved file
    with open(output_file, "r", encoding="utf-8") as file:
        saved_data = json.load(file)

    if len(saved_data[endpoint]) != total:
        raise RuntimeError(f"Saved record count mismatch: {endpoint}")

    print(f"Saved: {output_file}")
    print(f"Verified records: {len(saved_data[endpoint])}")


def main():

    print("\n========== DUMMYJSON API INGESTION ==========")

    try:
        for endpoint in ENDPOINTS:

            print(f"\nProcessing: {endpoint.upper()}")

            records, total = fetch_all_records(endpoint)

            validate_records(endpoint, records)

            if endpoint == "users":
                records = sanitize_users(records)

                # Verify sensitive fields were excluded.
                forbidden_fields = {
                    "password",
                    "ssn",
                    "ein",
                    "ip",
                    "macAddress"
                }

                for user in records:
                    if forbidden_fields.intersection(user):
                        raise ValueError("Sensitive user field detected")

            save_json(endpoint, records, total)

        print("\n============================================")
        print("DUMMYJSON INGESTION SUCCESSFUL")
        print("All three endpoints processed.")
        print("============================================")

    except (requests.RequestException, ValueError, RuntimeError) as error:
        print("\nINGESTION FAILED")
        print("Error:", error)
        sys.exit(1)


if __name__ == "__main__":
    main()