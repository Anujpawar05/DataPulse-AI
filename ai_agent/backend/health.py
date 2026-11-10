"""
DataPulse AI — Health & Diagnostics Subsystem
Provides independent, isolated readiness probes for SQLite, BigQuery, and AI Providers.
"""

from datetime import datetime, timezone
import os
import sqlite3
import time
from typing import Any, Dict, Optional, Tuple

import requests
from google.cloud import bigquery

from ai_agent.backend.config import (
    BIGQUERY_PROJECT_ID,
    BIGQUERY_DATASET,
    BIGQUERY_LOCATION,
    AI_PRIMARY_PROVIDER,
    AI_SECONDARY_PROVIDER,
    AI_LOCAL_PROVIDER,
    GEMINI_API_KEY,
    GROQ_API_KEY,
    OLLAMA_BASE_URL,
)
from ai_agent.backend.analytics.insights_store import DEFAULT_DB_PATH
from ai_agent.backend.logger import get_logger

logger = get_logger("health")

SQLITE_TIMEOUT_SECONDS = 2.0
BIGQUERY_TIMEOUT_SECONDS = 3.0
OLLAMA_TIMEOUT_SECONDS = 1.0


def check_sqlite_readiness(db_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Verify SQLite connection and lightweight read capability using bounded timeout.
    Does not touch or modify existing insight records, and does not claim write readiness.
    """
    target_path = str(db_path or DEFAULT_DB_PATH)
    start_time = time.perf_counter()
    try:
        conn = sqlite3.connect(target_path, timeout=SQLITE_TIMEOUT_SECONDS)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1;")
            cursor.fetchone()
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            return {
                "status": "ok",
                "latency_ms": round(elapsed_ms, 2),
                "connected": True,
                "read_ready": True,
            }
        finally:
            conn.close()
    except Exception as exc:
        logger.warning(f"SQLite readiness check failed: {type(exc).__name__}")
        return {
            "status": "unavailable",
            "error": "Database component is unreachable",
        }


def check_bigquery_readiness(
    client: Optional[bigquery.Client] = None,
    project_id: Optional[str] = None,
    dataset_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Verify BigQuery connectivity using metadata-only accessibility check (get_dataset).
    Applies bounded timeout, executes no SQL, and incurs zero query processing costs.
    """
    proj = project_id or BIGQUERY_PROJECT_ID
    dataset = dataset_id or BIGQUERY_DATASET
    start_time = time.perf_counter()
    try:
        bq_client = client or bigquery.Client(
            project=proj,
            location=BIGQUERY_LOCATION,
        )
        dataset_ref = f"{proj}.{dataset}"
        bq_client.get_dataset(dataset_ref, timeout=BIGQUERY_TIMEOUT_SECONDS)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        return {
            "status": "ok",
            "latency_ms": round(elapsed_ms, 2),
        }
    except Exception as exc:
        logger.warning(f"BigQuery readiness check failed: {type(exc).__name__}")
        return {
            "status": "unavailable",
            "error": "Warehouse dataset is unreachable",
        }


def check_ai_providers_readiness(
    provider_order: Optional[list] = None,
) -> Dict[str, Any]:
    """
    Inspect configured AI providers and fallback readiness without sending prompts
    or consuming LLM tokens. Distinguishes configuration from runtime verification.
    """
    order = provider_order or [
        AI_PRIMARY_PROVIDER,
        AI_SECONDARY_PROVIDER,
        AI_LOCAL_PROVIDER,
    ]

    configured_providers = []
    runtime_verified = []

    for p in order:
        if p == "gemini":
            if os.getenv("GEMINI_API_KEY", GEMINI_API_KEY):
                configured_providers.append("gemini")
        elif p == "groq":
            if os.getenv("GROQ_API_KEY", GROQ_API_KEY):
                configured_providers.append("groq")
        elif p == "ollama":
            url = os.getenv("OLLAMA_BASE_URL", OLLAMA_BASE_URL)
            if url:
                configured_providers.append("ollama")
                # Lightweight non-token HTTP ping
                try:
                    res = requests.get(
                        f"{url.rstrip('/')}/api/tags",
                        timeout=OLLAMA_TIMEOUT_SECONDS,
                    )
                    if res.status_code == 200:
                        runtime_verified.append("ollama")
                except Exception:
                    pass

    if not configured_providers:
        return {
            "status": "unavailable",
            "active_provider": None,
            "configured_providers": [],
            "runtime_verified_providers": runtime_verified,
            "fallback_available": False,
            "detail": "No AI providers configured; rule-based fallback active",
        }

    active_provider = configured_providers[0]
    is_primary = (active_provider == order[0])

    status = "ok" if (is_primary and len(configured_providers) > 0) else "degraded"

    return {
        "status": status,
        "active_provider": active_provider,
        "configured_providers": configured_providers,
        "runtime_verified_providers": runtime_verified,
        "fallback_available": len(configured_providers) > 1,
    }


def get_readiness_report(
    sqlite_check_fn=None,
    bigquery_check_fn=None,
    ai_check_fn=None,
) -> Tuple[int, Dict[str, Any]]:
    """
    Evaluate overall backend readiness according to readiness policy:
    - SQLite failure: HTTP 503
    - BigQuery failure: HTTP 503
    - AI degradation/unavailability: HTTP 200 with overall status 'degraded' (if DBs healthy)
    - All healthy: HTTP 200 with status 'ready'
    """
    sqlite_res = (sqlite_check_fn or check_sqlite_readiness)()
    bq_res = (bigquery_check_fn or check_bigquery_readiness)()
    ai_res = (ai_check_fn or check_ai_providers_readiness)()

    sqlite_ok = sqlite_res.get("status") == "ok"
    bq_ok = bq_res.get("status") == "ok"
    ai_status = ai_res.get("status", "unavailable")

    timestamp = datetime.now(timezone.utc).isoformat()

    components = {
        "sqlite": sqlite_res,
        "bigquery": bq_res,
        "ai_providers": ai_res,
    }

    if not sqlite_ok or not bq_ok:
        http_status = 503
        overall_status = "unhealthy"
    elif ai_status in ("degraded", "unavailable"):
        http_status = 200
        overall_status = "degraded"
    else:
        http_status = 200
        overall_status = "ready"

    report = {
        "status": overall_status,
        "timestamp": timestamp,
        "components": components,
    }

    return http_status, report
