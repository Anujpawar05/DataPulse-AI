import re

from ai_agent.backend.rag.knowledge_loader import load_knowledge_base


TABLE_INTENTS = [
    (["inventory", "stock", "restock", "reorder"], "fct_inventory"),
    (["payment", "payments", "transaction"], "fct_payments"),
    (["daily", "day-by-day"], "fct_daily_sales"),
    (["category", "categories"], "fct_category_sales"),
    (["sales", "revenue", "profit", "orders"], "fct_sales"),
    (["customer", "customers", "client"], "dim_customers"),
    (["product", "products"], "dim_products"),
]


def retrieve_relevant_knowledge(question: str, top_k: int = 3) -> str:
    knowledge = load_knowledge_base()
    question_lower = question.lower()

    # Identify the relevant warehouse table.
    selected_table = None

    for keywords, table in TABLE_INTENTS:
        if any(
            re.search(rf"\b{re.escape(keyword)}\b", question_lower)
            for keyword in keywords
        ):
            selected_table = table
            break

    if not selected_table:
        return "No matching warehouse table found. Clarification is required."

    # Extract the complete table section from the schema.
    sections = re.split(
        r"(?=^## \d+\. )",
        knowledge,
        flags=re.MULTILINE,
    )

    for section in sections:
        heading = section.splitlines()[0].strip()

        if heading.endswith(selected_table):
            return section.strip()

    return f"Schema definition not found for {selected_table}."