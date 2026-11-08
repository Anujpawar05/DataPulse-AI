
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from fastapi.encoders import jsonable_encoder

from ai_agent.backend.providers.manager import ProviderManager
from ai_agent.backend.rag.prompt_builder import build_sql_prompt
from ai_agent.backend.sql.bigquery_executor import (
    BigQueryExecutor,
    BigQueryExecutionError,
)
from ai_agent.backend.sql.validator import SQLValidationError


router = APIRouter()

provider_manager = ProviderManager()
bigquery_executor = BigQueryExecutor()


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1000)


class AskResponse(BaseModel):
    question: str
    sql: str
    results: list[dict]
    row_count: int
    status: str


def clean_sql_response(response: str) -> str:
    """Remove optional Markdown SQL fences from provider output."""
    response = response.strip()

    if response.startswith("```"):
        response = re.sub(
            r"^```(?:sql)?\s*|\s*```$",
            "",
            response,
            flags=re.IGNORECASE,
        ).strip()

    return response


@router.post("/ask", response_model=AskResponse)
def ask_question(request: AskRequest):
    question = request.question.strip()

    try:
        # 1. Build prompt using retrieved warehouse knowledge.
        prompt = build_sql_prompt(question)

        # 2. Generate SQL using the configured provider manager.
        generated_response = provider_manager.generate_response(prompt)

        # 3. Clean the provider response.
        sql = clean_sql_response(generated_response)

        # 4. Handle clarification responses without executing SQL.
        if sql.upper().startswith("CLARIFICATION:"):
            raise HTTPException(
                status_code=422,
                detail=sql,
            )

        # 5. Validate and execute the read-only query.
        results = bigquery_executor.execute_read_only_query(sql)

        return jsonable_encoder(
            AskResponse(
                question=question,
                sql=sql,
                results=results,
                row_count=len(results),
                status="success",
            )
        )

    except SQLValidationError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Generated SQL was rejected: {exc}",
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc



    except BigQueryExecutionError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    except HTTPException:
        raise

    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail="AI service is currently unavailable.",
        ) from exc
