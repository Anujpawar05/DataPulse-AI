import sqlite3
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, List, Any
from contextlib import contextmanager

DEFAULT_DB_DIR = Path(__file__).resolve().parent.parent / "data"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "insights_store.db"


class InsightsStore:
    """Thread-safe SQLite storage manager for DataPulse AI business insights."""

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            self.db_path = DEFAULT_DB_PATH
        else:
            self.db_path = Path(db_path)

        self._ensure_db_dir()
        self.init_db()

    def _ensure_db_dir(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(str(self.db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_db(self):
        """Initialize the insights schema, WAL mode, and indexes."""
        with self._get_connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS business_insights (
                    insight_id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    category TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    headline TEXT NOT NULL,
                    observed_fact TEXT NOT NULL,
                    ai_explanation TEXT NOT NULL,
                    actionable_recommendation TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    observed_value REAL NOT NULL,
                    observed_value_formatted TEXT NOT NULL,
                    baseline_value REAL,
                    baseline_value_formatted TEXT,
                    change_percentage REAL,
                    statistical_score REAL,
                    detection_method TEXT NOT NULL,
                    period_start TEXT NOT NULL,
                    period_end TEXT NOT NULL,
                    warehouse_table TEXT NOT NULL,
                    supporting_sql TEXT NOT NULL,
                    confidence_score REAL NOT NULL,
                    ai_provider_used TEXT NOT NULL,
                    dimension_key TEXT NOT NULL
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_insights_status_severity
                ON business_insights(status, severity, created_at DESC);
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_insights_category
                ON business_insights(category, created_at DESC);
                """
            )

    @staticmethod
    def generate_fingerprint(
        category: str,
        metric_name: str,
        period_start: str,
        period_end: str,
        dimension_key: str,
    ) -> str:
        """Create a stable SHA-256 fingerprint to avoid duplicate records across scans."""
        raw_token = f"{category}|{metric_name}|{period_start}|{period_end}|{dimension_key}"
        return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()[:16]

    def save_insight(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Insert a new insight or update metric values while preserving user review status."""
        fingerprint = self.generate_fingerprint(
            category=item["category"],
            metric_name=item["metric_name"],
            period_start=item["period_start"],
            period_end=item["period_end"],
            dimension_key=item.get("dimension_key", "default"),
        )
        insight_id = f"ins_{fingerprint}"
        now_iso = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT status, created_at FROM business_insights WHERE fingerprint = ?",
                (fingerprint,),
            )
            existing = cursor.fetchone()

            if existing:
                current_status = existing["status"]
                created_at = existing["created_at"]
                cursor.execute(
                    """
                    UPDATE business_insights SET
                        updated_at = ?,
                        severity = ?,
                        headline = ?,
                        observed_fact = ?,
                        ai_explanation = ?,
                        actionable_recommendation = ?,
                        observed_value = ?,
                        observed_value_formatted = ?,
                        baseline_value = ?,
                        baseline_value_formatted = ?,
                        change_percentage = ?,
                        statistical_score = ?,
                        detection_method = ?,
                        supporting_sql = ?,
                        confidence_score = ?,
                        ai_provider_used = ?
                    WHERE fingerprint = ?
                    """,
                    (
                        now_iso,
                        item["severity"],
                        item["headline"],
                        item["observed_fact"],
                        item["ai_explanation"],
                        item["actionable_recommendation"],
                        float(item["observed_value"]),
                        str(item["observed_value_formatted"]),
                        float(item["baseline_value"]) if item.get("baseline_value") is not None else None,
                        str(item.get("baseline_value_formatted", "")) or None,
                        float(item["change_percentage"]) if item.get("change_percentage") is not None else None,
                        float(item["statistical_score"]) if item.get("statistical_score") is not None else None,
                        item.get("detection_method", "Statistical Analysis"),
                        item["supporting_sql"],
                        float(item["confidence_score"]),
                        item.get("ai_provider_used", "rule_fallback"),
                        fingerprint,
                    ),
                )
                final_status = current_status
            else:
                created_at = now_iso
                final_status = item.get("status", "active")
                cursor.execute(
                    """
                    INSERT INTO business_insights (
                        insight_id, fingerprint, created_at, updated_at, category,
                        severity, status, headline, observed_fact, ai_explanation,
                        actionable_recommendation, metric_name, observed_value,
                        observed_value_formatted, baseline_value, baseline_value_formatted,
                        change_percentage, statistical_score, detection_method,
                        period_start, period_end, warehouse_table, supporting_sql,
                        confidence_score, ai_provider_used, dimension_key
                    ) VALUES (
                        ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?,
                        ?, ?, ?, ?,
                        ?, ?, ?
                    )
                    """,
                    (
                        insight_id,
                        fingerprint,
                        created_at,
                        now_iso,
                        item["category"],
                        item["severity"],
                        final_status,
                        item["headline"],
                        item["observed_fact"],
                        item["ai_explanation"],
                        item["actionable_recommendation"],
                        item["metric_name"],
                        float(item["observed_value"]),
                        str(item["observed_value_formatted"]),
                        float(item["baseline_value"]) if item.get("baseline_value") is not None else None,
                        str(item.get("baseline_value_formatted", "")) or None,
                        float(item["change_percentage"]) if item.get("change_percentage") is not None else None,
                        float(item["statistical_score"]) if item.get("statistical_score") is not None else None,
                        item.get("detection_method", "Statistical Analysis"),
                        item["period_start"],
                        item["period_end"],
                        item["warehouse_table"],
                        item["supporting_sql"],
                        float(item["confidence_score"]),
                        item.get("ai_provider_used", "rule_fallback"),
                        item.get("dimension_key", "default"),
                    ),
                )

        return self.get_insight_by_id(insight_id)

    def get_insight_by_id(self, insight_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM business_insights WHERE insight_id = ?", (insight_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_insights(
        self,
        category: Optional[str] = None,
        severity: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM business_insights WHERE 1=1"
        params: List[Any] = []

        if category:
            query += " AND category = ?"
            params.append(category)

        if severity:
            query += " AND severity = ?"
            params.append(severity)

        if status:
            query += " AND status = ?"
            params.append(status)

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(r) for r in rows]

    def update_insight_status(self, insight_id: str, new_status: str) -> Optional[Dict[str, Any]]:
        valid_statuses = {"active", "acknowledged", "dismissed", "resolved"}
        if new_status not in valid_statuses:
            raise ValueError(f"Invalid status '{new_status}'. Allowed: {valid_statuses}")

        now_iso = datetime.now(timezone.utc).isoformat()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE business_insights
                SET status = ?, updated_at = ?
                WHERE insight_id = ?
                """,
                (new_status, now_iso, insight_id),
            )
            if cursor.rowcount == 0:
                return None

        return self.get_insight_by_id(insight_id)

    def count_active_critical(self) -> int:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(1) FROM business_insights WHERE status = 'active' AND severity = 'critical'"
            )
            return cursor.fetchone()[0]

    def clear_all(self):
        """Utility for test fixtures."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM business_insights")
