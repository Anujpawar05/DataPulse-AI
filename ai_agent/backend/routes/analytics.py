import time
import threading
from datetime import datetime, timezone, date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from fastapi.encoders import jsonable_encoder

from ai_agent.backend.sql.bigquery_executor import (
    BigQueryExecutor,
    BigQueryExecutionError,
)
from ai_agent.backend.sql.validator import SQLValidationError

router = APIRouter(prefix="/analytics", tags=["analytics"])

bigquery_executor = BigQueryExecutor()

CACHE_TTL_SECONDS = 600  # 10 minutes cache duration
_cache_lock = threading.Lock()
_cache_store = {}  # cache_key -> (cached_data, timestamp)

MIN_WAREHOUSE_DATE = "2025-01-01"
MAX_WAREHOUSE_DATE = "2026-10-31"


class KPISummary(BaseModel):
    total_net_revenue: float
    total_net_revenue_formatted: str
    total_profit: float
    total_profit_formatted: str
    profit_margin_percentage: float
    total_orders: int
    delivered_orders: int
    total_customers: int
    total_products: int
    restock_alerts_count: int


class TrendPeriodItem(BaseModel):
    period: str
    period_label: str
    net_revenue: float
    net_revenue_formatted: str
    total_profit: float
    total_profit_formatted: str
    total_orders: int
    units_sold: int
    profit_margin_percentage: float


class CategoryProfitabilityItem(BaseModel):
    product_category: str
    net_revenue: float
    net_revenue_formatted: str
    total_profit: float
    total_profit_formatted: str
    profit_margin_percentage: float
    total_orders: int = 0


class TopProductItem(BaseModel):
    product_id: int
    product_name: str
    product_category: str
    units_sold: int
    total_revenue: float
    total_revenue_formatted: str
    total_profit: float
    total_profit_formatted: str
    profit_margin_percentage: float


class RestockItem(BaseModel):
    product_id: int
    product_name: str
    product_category: str
    warehouse: str
    stock_quantity: int
    reorder_level: int
    stock_difference: int
    inventory_status: str
    requires_restock: bool


class WarehouseRiskItem(BaseModel):
    warehouse: str
    total_skus: int
    total_units: int
    restock_alerts: int
    low_stock_count: int
    in_stock_count: int
    health_status: str


class InventoryRiskData(BaseModel):
    health_score_percentage: float
    total_skus: int
    critical_alerts_count: int
    warehouse_breakdown: list[WarehouseRiskItem]
    restock_queue: list[RestockItem]
    note: str = "Current Warehouse Snapshot (Real-Time)"


class DateFilterMeta(BaseModel):
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    granularity: str = "monthly"
    min_available_date: str = MIN_WAREHOUSE_DATE
    max_available_date: str = MAX_WAREHOUSE_DATE


class CacheMeta(BaseModel):
    cached: bool
    cached_at: str
    expires_in_seconds: int


class DashboardAnalyticsResponse(BaseModel):
    summary: KPISummary
    revenue_trends: list[TrendPeriodItem] = Field(default_factory=list)
    category_profitability: list[CategoryProfitabilityItem] = Field(default_factory=list)
    top_products: list[TopProductItem] = Field(default_factory=list)
    inventory_risk: Optional[InventoryRiskData] = None
    restock_queue: list[RestockItem] = Field(default_factory=list)
    date_filter: Optional[DateFilterMeta] = None
    cache: CacheMeta


def format_inr(value: float) -> str:
    """Format numeric values with standard Indian numbering units (Crore / Lakh)."""
    abs_val = abs(value)
    if abs_val >= 10_000_000:
        return f"₹{value / 10_000_000:.2f} Cr"
    if abs_val >= 100_000:
        return f"₹{value / 100_000:.2f} L"
    return f"₹{value:,.2f}"


def to_float(val) -> float:
    if val is None:
        return 0.0
    return float(val)


def to_int(val) -> int:
    if val is None:
        return 0
    return int(val)


def validate_and_parse_date(date_str: Optional[str], field_name: str) -> Optional[date]:
    """Strictly validate YYYY-MM-DD format to prevent invalid inputs or SQL injection attempts."""
    if not date_str:
        return None
    date_clean = str(date_str).strip()
    try:
        parsed = datetime.strptime(date_clean, "%Y-%m-%d").date()
        return parsed
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid {field_name} format: '{date_str}'. Expected valid calendar date in YYYY-MM-DD format.",
        )


def build_date_clause(column_name: str, start_dt: Optional[date], end_dt: Optional[date]) -> str:
    """Build a deterministic, parameterized WHERE clause using validated date literals."""
    clauses = []
    if start_dt:
        clauses.append(f"{column_name} >= '{start_dt.isoformat()}'")
    if end_dt:
        clauses.append(f"{column_name} <= '{end_dt.isoformat()}'")
    if clauses:
        return "WHERE " + " AND ".join(clauses)
    return ""


def fetch_warehouse_metrics(
    executor: BigQueryExecutor,
    start_dt: Optional[date],
    end_dt: Optional[date],
    granularity: str = "monthly",
):
    """Execute dedicated queries against approved datapulse_marts tables."""
    # 1. Revenue, profit, and order counts from fct_sales
    sales_date_clause = build_date_clause("order_date", start_dt, end_dt)
    sales_sql = (
        f"SELECT "
        f"ROUND(SUM(net_amount), 2) AS total_net_revenue, "
        f"ROUND(SUM(profit), 2) AS total_profit, "
        f"COUNT(DISTINCT order_id) AS total_orders, "
        f"COUNT(DISTINCT CASE WHEN order_status = 'delivered' THEN order_id END) AS delivered_orders, "
        f"COUNT(DISTINCT customer_id) AS total_customers, "
        f"COUNT(DISTINCT product_id) AS total_products "
        f"FROM winter-sensor-474220-u4.datapulse_marts.fct_sales "
        f"{sales_date_clause}"
    )
    sales_rows = executor.execute_read_only_query(sales_sql)
    sales_data = sales_rows[0] if sales_rows else {}

    net_rev = to_float(sales_data.get("total_net_revenue", 0.0))
    profit = to_float(sales_data.get("total_profit", 0.0))
    margin = round((profit / net_rev * 100), 2) if net_rev > 0 else 0.0
    total_orders = to_int(sales_data.get("total_orders", 0))
    delivered_orders = to_int(sales_data.get("delivered_orders", 0))

    if start_dt or end_dt:
        total_customers = to_int(sales_data.get("total_customers", 0))
        total_products = to_int(sales_data.get("total_products", 0))
    else:
        # Full master catalog dimensions when unconstrained
        cust_sql = "SELECT COUNT(customer_id) AS total_customers FROM winter-sensor-474220-u4.datapulse_marts.dim_customers"
        cust_rows = executor.execute_read_only_query(cust_sql)
        total_customers = to_int(cust_rows[0].get("total_customers", 0)) if cust_rows else 0

        prod_sql = "SELECT COUNT(product_id) AS total_products FROM winter-sensor-474220-u4.datapulse_marts.dim_products"
        prod_rows = executor.execute_read_only_query(prod_sql)
        total_products = to_int(prod_rows[0].get("total_products", 0)) if prod_rows else 0

    # 2. Revenue Trends from fct_daily_sales
    daily_date_clause = build_date_clause("sales_date", start_dt, end_dt)
    if granularity == "daily":
        trends_sql = (
            f"SELECT "
            f"sales_date AS period, "
            f"ROUND(net_revenue, 2) AS net_revenue, "
            f"ROUND(total_profit, 2) AS total_profit, "
            f"total_orders, "
            f"units_sold, "
            f"ROUND(profit_margin_percentage, 2) AS profit_margin_percentage "
            f"FROM winter-sensor-474220-u4.datapulse_marts.fct_daily_sales "
            f"{daily_date_clause} "
            f"ORDER BY period ASC "
            f"LIMIT 1000"
        )
    else:
        # Default: Monthly aggregation
        trends_sql = (
            f"SELECT "
            f"DATE_TRUNC(sales_date, MONTH) AS period, "
            f"ROUND(SUM(net_revenue), 2) AS net_revenue, "
            f"ROUND(SUM(total_profit), 2) AS total_profit, "
            f"SUM(total_orders) AS total_orders, "
            f"SUM(units_sold) AS units_sold, "
            f"ROUND(SAFE_DIVIDE(SUM(total_profit), SUM(net_revenue)) * 100, 2) AS profit_margin_percentage "
            f"FROM winter-sensor-474220-u4.datapulse_marts.fct_daily_sales "
            f"{daily_date_clause} "
            f"GROUP BY period "
            f"ORDER BY period ASC"
        )

    trend_rows = executor.execute_read_only_query(trends_sql)
    revenue_trends = []
    for r in trend_rows:
        period_val = r.get("period")
        if isinstance(period_val, (datetime, date)):
            period_str = period_val.isoformat()
            period_lbl = period_val.strftime("%d %b %Y") if granularity == "daily" else period_val.strftime("%b %Y")
        else:
            period_str = str(period_val)
            period_lbl = period_str

        p_rev = to_float(r.get("net_revenue", 0.0))
        p_profit = to_float(r.get("total_profit", 0.0))
        p_margin = to_float(r.get("profit_margin_percentage", 0.0))

        revenue_trends.append(
            TrendPeriodItem(
                period=period_str,
                period_label=period_lbl,
                net_revenue=p_rev,
                net_revenue_formatted=format_inr(p_rev),
                total_profit=p_profit,
                total_profit_formatted=format_inr(p_profit),
                total_orders=to_int(r.get("total_orders", 0)),
                units_sold=to_int(r.get("units_sold", 0)),
                profit_margin_percentage=round(p_margin, 2),
            )
        )

    # 3. Category Profitability and Comparison
    if start_dt or end_dt:
        cat_sql = (
            f"SELECT "
            f"product_category, "
            f"ROUND(SUM(net_amount), 2) AS net_revenue, "
            f"ROUND(SUM(profit), 2) AS total_profit, "
            f"ROUND(SAFE_DIVIDE(SUM(profit), SUM(net_amount)) * 100, 2) AS profit_margin_percentage, "
            f"COUNT(DISTINCT order_id) AS total_orders "
            f"FROM winter-sensor-474220-u4.datapulse_marts.fct_sales "
            f"{sales_date_clause} "
            f"GROUP BY product_category "
            f"ORDER BY net_revenue DESC"
        )
    else:
        cat_sql = (
            "SELECT "
            "product_category, "
            "net_revenue, "
            "total_profit, "
            "profit_margin_percentage, "
            "total_orders "
            "FROM winter-sensor-474220-u4.datapulse_marts.fct_category_sales "
            "ORDER BY net_revenue DESC"
        )

    cat_rows = executor.execute_read_only_query(cat_sql)
    category_list = []
    for row in cat_rows:
        cat_rev = to_float(row.get("net_revenue", 0.0))
        cat_profit = to_float(row.get("total_profit", 0.0))
        cat_margin = to_float(row.get("profit_margin_percentage", 0.0))
        category_list.append(
            CategoryProfitabilityItem(
                product_category=str(row.get("product_category", "Unknown")),
                net_revenue=cat_rev,
                net_revenue_formatted=format_inr(cat_rev),
                total_profit=cat_profit,
                total_profit_formatted=format_inr(cat_profit),
                profit_margin_percentage=round(cat_margin, 2),
                total_orders=to_int(row.get("total_orders", 0)),
            )
        )

    # 4. Top 10 Products by Revenue
    top_sql = (
        f"SELECT "
        f"product_id, "
        f"product_name, "
        f"product_category, "
        f"SUM(quantity) AS units_sold, "
        f"ROUND(SUM(net_amount), 2) AS total_revenue, "
        f"ROUND(SUM(profit), 2) AS total_profit, "
        f"ROUND(SAFE_DIVIDE(SUM(profit), SUM(net_amount)) * 100, 2) AS profit_margin_percentage "
        f"FROM winter-sensor-474220-u4.datapulse_marts.fct_sales "
        f"{sales_date_clause} "
        f"GROUP BY product_id, product_name, product_category "
        f"ORDER BY total_revenue DESC "
        f"LIMIT 10"
    )
    top_rows = executor.execute_read_only_query(top_sql)
    top_products = []
    for r in top_rows:
        p_rev = to_float(r.get("total_revenue", 0.0))
        p_profit = to_float(r.get("total_profit", 0.0))
        p_margin = to_float(r.get("profit_margin_percentage", 0.0))
        top_products.append(
            TopProductItem(
                product_id=to_int(r.get("product_id", 0)),
                product_name=str(r.get("product_name", "Unknown Product")),
                product_category=str(r.get("product_category", "General")),
                units_sold=to_int(r.get("units_sold", 0)),
                total_revenue=p_rev,
                total_revenue_formatted=format_inr(p_rev),
                total_profit=p_profit,
                total_profit_formatted=format_inr(p_profit),
                profit_margin_percentage=round(p_margin, 2),
            )
        )

    # 5. Inventory Risk Analysis (Current Warehouse Snapshot)
    # Warehouse breakdown
    wh_sql = (
        "SELECT "
        "warehouse, "
        "COUNT(1) AS total_skus, "
        "SUM(stock_quantity) AS total_units, "
        "COUNT(CASE WHEN requires_restock = TRUE THEN 1 END) AS restock_alerts, "
        "COUNT(CASE WHEN inventory_status = 'low_stock' THEN 1 END) AS low_stock_count, "
        "COUNT(CASE WHEN inventory_status = 'in_stock' THEN 1 END) AS in_stock_count "
        "FROM winter-sensor-474220-u4.datapulse_marts.fct_inventory "
        "GROUP BY warehouse "
        "ORDER BY restock_alerts DESC"
    )
    wh_rows = executor.execute_read_only_query(wh_sql)
    warehouse_risk_list = []
    total_inventory_skus = 0
    total_in_stock_skus = 0

    for w in wh_rows:
        skus = to_int(w.get("total_skus", 0))
        units = to_int(w.get("total_units", 0))
        alerts = to_int(w.get("restock_alerts", 0))
        in_stock = to_int(w.get("in_stock_count", 0))
        low_stock = to_int(w.get("low_stock_count", 0))

        total_inventory_skus += skus
        total_in_stock_skus += in_stock

        health = "Normal"
        if alerts >= 2:
            health = "High Risk"
        elif alerts >= 1:
            health = "Moderate Risk"

        warehouse_risk_list.append(
            WarehouseRiskItem(
                warehouse=str(w.get("warehouse", "Unknown")),
                total_skus=skus,
                total_units=units,
                restock_alerts=alerts,
                low_stock_count=low_stock,
                in_stock_count=in_stock,
                health_status=health,
            )
        )

    # Restock queue items
    inv_sql = (
        "SELECT product_id, product_name, product_category, warehouse, "
        "stock_quantity, reorder_level, stock_difference, inventory_status, requires_restock "
        "FROM winter-sensor-474220-u4.datapulse_marts.fct_inventory "
        "ORDER BY requires_restock DESC, stock_quantity ASC"
    )
    inv_rows = executor.execute_read_only_query(inv_sql)
    restock_queue = []
    restock_alerts_count = 0

    for row in inv_rows:
        is_restock = bool(row.get("requires_restock", False))
        if is_restock:
            restock_alerts_count += 1
            restock_queue.append(
                RestockItem(
                    product_id=to_int(row.get("product_id", 0)),
                    product_name=str(row.get("product_name", "Unknown Product")),
                    product_category=str(row.get("product_category", "General")),
                    warehouse=str(row.get("warehouse", "Default WH")),
                    stock_quantity=to_int(row.get("stock_quantity", 0)),
                    reorder_level=to_int(row.get("reorder_level", 0)),
                    stock_difference=to_int(row.get("stock_difference", 0)),
                    inventory_status=str(row.get("inventory_status", "in_stock")),
                    requires_restock=is_restock,
                )
            )

    health_score = (
        round((total_in_stock_skus / total_inventory_skus) * 100, 1)
        if total_inventory_skus > 0
        else 100.0
    )

    inventory_risk = InventoryRiskData(
        health_score_percentage=health_score,
        total_skus=total_inventory_skus,
        critical_alerts_count=restock_alerts_count,
        warehouse_breakdown=warehouse_risk_list,
        restock_queue=restock_queue,
        note="Current Warehouse Snapshot (Real-Time)",
    )

    summary = KPISummary(
        total_net_revenue=net_rev,
        total_net_revenue_formatted=format_inr(net_rev),
        total_profit=profit,
        total_profit_formatted=format_inr(profit),
        profit_margin_percentage=margin,
        total_orders=total_orders,
        delivered_orders=delivered_orders,
        total_customers=total_customers,
        total_products=total_products,
        restock_alerts_count=restock_alerts_count,
    )

    date_filter = DateFilterMeta(
        start_date=start_dt.isoformat() if start_dt else None,
        end_date=end_dt.isoformat() if end_dt else None,
        granularity=granularity,
        min_available_date=MIN_WAREHOUSE_DATE,
        max_available_date=MAX_WAREHOUSE_DATE,
    )

    return summary, revenue_trends, category_list, top_products, inventory_risk, restock_queue, date_filter


@router.get("/dashboard", response_model=DashboardAnalyticsResponse)
def get_dashboard_analytics(
    start_date: Optional[str] = Query(
        default=None,
        description="Filter metrics starting from date (YYYY-MM-DD)",
    ),
    end_date: Optional[str] = Query(
        default=None,
        description="Filter metrics up to date (YYYY-MM-DD)",
    ),
    granularity: str = Query(
        default="monthly",
        pattern="^(daily|monthly)$",
        description="Aggregation granularity for revenue trends ('daily' or 'monthly')",
    ),
    refresh: bool = Query(
        default=False,
        description="Bypass the 600-second cache and fetch fresh data from BigQuery",
    ),
):
    """Retrieve verified business intelligence metrics from BigQuery with in-memory caching and date filtering."""
    # Validate and parse date inputs
    start_dt = validate_and_parse_date(start_date, "start_date")
    end_dt = validate_and_parse_date(end_date, "end_date")

    if start_dt and end_dt and start_dt > end_dt:
        raise HTTPException(
            status_code=422,
            detail=f"start_date ({start_date}) cannot be chronologically after end_date ({end_date}).",
        )

    cache_key = (
        start_dt.isoformat() if start_dt else None,
        end_dt.isoformat() if end_dt else None,
        granularity,
    )

    now = time.time()

    with _cache_lock:
        cached_entry = _cache_store.get(cache_key)
        cache_valid = (
            cached_entry is not None
            and (now - cached_entry["timestamp"]) < CACHE_TTL_SECONDS
            and not refresh
        )

        if cache_valid:
            remaining_ttl = int(CACHE_TTL_SECONDS - (now - cached_entry["timestamp"]))
            payload = cached_entry["payload"]
            return jsonable_encoder(
                DashboardAnalyticsResponse(
                    summary=payload["summary"],
                    revenue_trends=payload["revenue_trends"],
                    category_profitability=payload["category_profitability"],
                    top_products=payload["top_products"],
                    inventory_risk=payload["inventory_risk"],
                    restock_queue=payload["restock_queue"],
                    date_filter=payload["date_filter"],
                    cache=CacheMeta(
                        cached=True,
                        cached_at=payload["cached_at"],
                        expires_in_seconds=max(0, remaining_ttl),
                    ),
                )
            )

        try:
            (
                summary,
                revenue_trends,
                category_list,
                top_products,
                inventory_risk,
                restock_queue,
                date_filter,
            ) = fetch_warehouse_metrics(
                bigquery_executor,
                start_dt,
                end_dt,
                granularity,
            )

            now_iso = datetime.now(timezone.utc).isoformat()
            payload = {
                "summary": summary,
                "revenue_trends": revenue_trends,
                "category_profitability": category_list,
                "top_products": top_products,
                "inventory_risk": inventory_risk,
                "restock_queue": restock_queue,
                "date_filter": date_filter,
                "cached_at": now_iso,
            }

            _cache_store[cache_key] = {
                "payload": payload,
                "timestamp": now,
            }

            return jsonable_encoder(
                DashboardAnalyticsResponse(
                    summary=summary,
                    revenue_trends=revenue_trends,
                    category_profitability=category_list,
                    top_products=top_products,
                    inventory_risk=inventory_risk,
                    restock_queue=restock_queue,
                    date_filter=date_filter,
                    cache=CacheMeta(
                        cached=False,
                        cached_at=now_iso,
                        expires_in_seconds=CACHE_TTL_SECONDS,
                    ),
                )
            )

        except SQLValidationError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"Security validation rejected query: {exc}",
            ) from exc

        except BigQueryExecutionError as exc:
            raise HTTPException(
                status_code=503,
                detail=f"Warehouse execution failed: {exc}",
            ) from exc

        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to retrieve dashboard analytics: {str(exc)}",
            ) from exc
