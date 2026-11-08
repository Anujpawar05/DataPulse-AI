import re
from pathlib import Path
from typing import List, Dict, Optional

from ai_agent.backend.rag.knowledge_loader import load_knowledge_base, KNOWLEDGE_DIR


TABLE_INTENTS = [
    (
        [
            "inventory",
            "inventories",
            "stock",
            "stocks",
            "stocking",
            "restock",
            "restocks",
            "restocked",
            "restocking",
            "reorder",
            "reorders",
            "reordered",
            "reordering",
            "reorder_level",
            "warehouse",
            "warehouses",
            "supply",
            "supplies",
            "stockout",
            "stockouts",
            "shortage",
            "shortages",
            "replenish",
            "replenishing",
            "replenishment",
            "risk",
            "out_of_stock",
            "low_stock",
            "low in stock",
            "low in stocks",
            "low stocks",
            "low stock",
            "stock shortage",
            "out of stock",
            "running out of stock",
            "below reorder level",
            "needs restocking",
            "requiring restock",
            "requires restock",
            "insufficient inventory",
            "inventory quantities",
            "stock level",
            "stock levels",
            "stock quantity",
        ],
        "fct_inventory",
    ),
    (
        [
            "payment",
            "payments",
            "transaction",
            "transactions",
            "payment_method",
            "paid",
        ],
        "fct_payments",
    ),
    (
        [
            "daily",
            "day-by-day",
            "monthly",
            "month",
            "months",
            "month-by-month",
            "trend",
            "trends",
            "timeline",
            "day",
            "days",
            "date",
            "dates",
            "yearly",
            "year",
            "years",
        ],
        "fct_daily_sales",
    ),
    (
        [
            "category",
            "categories",
            "category-wise",
            "category_sales",
        ],
        "fct_category_sales",
    ),
    (
        [
            "sales",
            "sale",
            "selling",
            "sold",
            "bestselling",
            "best-selling",
            "top-selling",
            "revenue",
            "profit",
            "profitability",
            "orders",
            "order",
            "units",
            "quantity",
            "volume",
            "gross",
            "net",
            "margin",
            "discount",
            "aov",
        ],
        "fct_sales",
    ),
    (
        [
            "customer",
            "customers",
            "client",
            "clients",
            "buyer",
            "buyers",
            "user",
            "users",
            "city",
            "cities",
            "state",
            "states",
        ],
        "dim_customers",
    ),
    (
        [
            "product",
            "products",
            "item",
            "items",
            "sku",
            "skus",
            "merchandise",
            "catalog",
        ],
        "dim_products",
    ),
]

SALES_RANKING_WORDS = [
    "top",
    "best",
    "bestselling",
    "best-selling",
    "selling",
    "popular",
    "leading",
    "most",
]


def _parse_warehouse_schema() -> tuple[Dict[str, str], str]:
    """Parse warehouse_schema.md into table schemas and relationships."""
    schema_file = KNOWLEDGE_DIR / "warehouse_schema.md"
    if not schema_file.exists():
        return {}, ""

    text = schema_file.read_text(encoding="utf-8")
    sections = re.split(r"\n(?=## )", text)

    table_map: Dict[str, str] = {}
    relationships_section = ""

    for sec in sections:
        sec_strip = sec.strip()
        first_line = sec_strip.splitlines()[0] if sec_strip else ""

        if first_line.startswith("## Known relationships"):
            relationships_section = sec_strip
        elif re.match(r"^## \d+\. ", first_line):
            table_name = first_line.split()[-1]
            table_map[table_name] = sec_strip

    return table_map, relationships_section


def _parse_business_glossary() -> Dict[str, str]:
    """Parse business_glossary.md into metric category sections."""
    glossary_file = KNOWLEDGE_DIR / "business_glossary.md"
    if not glossary_file.exists():
        return {}

    text = glossary_file.read_text(encoding="utf-8")
    sections = re.split(r"\n(?=## )", text)

    glossary_map: Dict[str, str] = {}
    for sec in sections:
        sec_strip = sec.strip()
        first_line = sec_strip.splitlines()[0] if sec_strip else ""

        if first_line.startswith("## Sales Metrics"):
            glossary_map["sales"] = sec_strip
        elif first_line.startswith("## Customer Metrics"):
            glossary_map["customer"] = sec_strip
        elif first_line.startswith("## Inventory Metrics"):
            glossary_map["inventory"] = sec_strip

    return glossary_map


def retrieve_relevant_knowledge(question: str, top_k: int = 3) -> str:
    question_lower = question.lower()

    # Identify all relevant warehouse tables matching user question.
    matched_tables: List[str] = []

    for keywords, table in TABLE_INTENTS:
        if any(
            re.search(rf"\b{re.escape(keyword)}\b", question_lower)
            for keyword in keywords
        ):
            if table not in matched_tables:
                matched_tables.append(table)
                if len(matched_tables) >= top_k:
                    break

    # If ranking/top products is requested without explicit sales keywords,
    # include fct_sales since dim_products lacks sales and volume metrics,
    # unless inventory was specifically queried.
    if (
        "dim_products" in matched_tables
        and "fct_sales" not in matched_tables
        and "fct_inventory" not in matched_tables
    ):
        if any(
            re.search(rf"\b{re.escape(word)}\b", question_lower)
            for word in SALES_RANKING_WORDS
        ):
            if len(matched_tables) < top_k:
                matched_tables.append("fct_sales")

    if not matched_tables:
        return "No matching warehouse table found. Clarification is required."

    table_map, relationships_section = _parse_warehouse_schema()
    glossary_map = _parse_business_glossary()

    chunks: List[str] = []

    # 1. Add schema for all matched tables
    for tbl in matched_tables:
        if tbl in table_map:
            chunks.append(table_map[tbl])

    # 2. Add relevant relationships between matched tables
    if len(matched_tables) > 1 and relationships_section:
        rel_lines = []
        for line in relationships_section.splitlines():
            if "→" in line or "->" in line:
                tables_in_rel = [t for t in matched_tables if t in line]
                if len(tables_in_rel) >= 2:
                    rel_lines.append(line)
        if rel_lines:
            chunks.append(
                "## Known relationships\n\n"
                "Based on the mart definitions and existing dashboard model:\n\n"
                + "\n".join(rel_lines)
            )

    # 3. Add relevant business glossary metric definitions
    if any(
        t in ("fct_sales", "fct_daily_sales", "fct_category_sales")
        for t in matched_tables
    ) and "sales" in glossary_map:
        chunks.append(glossary_map["sales"])

    if "dim_customers" in matched_tables and "customer" in glossary_map:
        chunks.append(glossary_map["customer"])

    if "fct_inventory" in matched_tables and "inventory" in glossary_map:
        chunks.append(glossary_map["inventory"])

    if not chunks:
        return f"Schema definition not found for {', '.join(matched_tables)}."

    return "\n\n".join(chunks)
