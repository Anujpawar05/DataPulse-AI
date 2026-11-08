
from ai_agent.backend.rag.retriever import retrieve_relevant_knowledge


def build_sql_prompt(question: str) -> str:
    if not question or not question.strip():
        raise ValueError("Question cannot be empty.")

    context = retrieve_relevant_knowledge(question)

    if context.startswith("No matching warehouse table found"):
        raise ValueError(
            "This question cannot currently be mapped to an approved "
            "warehouse table. Please clarify the business metric."
        )

    if context.startswith("Schema definition not found"):
        raise ValueError("The required schema definition is unavailable.")

    return f"""
You are DataPulse AI, a business data analyst.

Generate one read-only BigQuery SQL query using only the
provided warehouse knowledge.

USER QUESTION:
{question.strip()}

RETRIEVED WAREHOUSE KNOWLEDGE:
{context}

APPROVED DATASET:
winter-sensor-474220-u4.datapulse_marts

STRICT RULES:
1. Use only documented tables and columns.
2. Use fully qualified BigQuery table names.
3. Generate SELECT queries only.
4. Never generate write operations or multiple statements.
5. Never access raw, staging, or intermediate tables.
6. Never invent columns, metrics, or table relationships.
7. Never retrieve customer_email or private customer information.
8. Use SAFE_DIVIDE for division.
9. Keep queries reasonably efficient.
10. If the question cannot be answered from the supplied knowledge,
    return a clarification instead of SQL.

OUTPUT FORMAT:
Return only SQL without Markdown code fences.
If clarification is required, return:
CLARIFICATION: followed by a short explanation.
"""
