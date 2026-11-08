from ai_agent.backend.config import PROJECT_ROOT

KNOWLEDGE_DIR = PROJECT_ROOT / "ai_agent" / "knowledge"

KNOWLEDGE_FILES = [
    KNOWLEDGE_DIR / "business_glossary.md",
    KNOWLEDGE_DIR / "warehouse_schema.md",
]


def load_knowledge_base() -> str:
    documents = []

    for file_path in KNOWLEDGE_FILES:
        if not file_path.exists():
            raise FileNotFoundError(
                f"Knowledge file not found: {file_path}"
            )

        content = file_path.read_text(encoding="utf-8")
        documents.append(
            f"# Knowledge Source: {file_path.name}\n\n{content}"
        )

    return "\n\n".join(documents)