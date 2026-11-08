import time
import threading
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
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
_cached_data = None
_cached_timestamp = 0.0


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


class CategoryProfitabilityItem(BaseModel):
    product_category: str
    net_revenue: float
    net_revenue_formatted: str
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


class CacheMeta(BaseModel):
    cached: bool
    cached_at: str
    expires_in_seconds: int


class DashboardAnalyticsResponse(BaseModel):
    summary: KPISummary
    category_profitability: list[CategoryProfitabilityItem]
    restock_queue: list[RestockItem]
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
    if isinstance(val, (Decimal, int, str)):
        return float(val)
    return float(val)


def to_int(val) -> int:
    if val is None:
        return 0
    return int(val)


def fetch_warehouse_metrics(executor: BigQueryExecutor):
    """Execute dedicated queries against approved datapulse_marts tables."""
    # 1. Revenue, profit, and order counts from fct_sales
    sales_sql = (
        "SELECT "
        "ROUND(SUM(net_amount), 2) AS total_net_revenue, "
        "ROUND(SUM(profit), 2) AS total_profit, "
        "COUNT(DISTINCT order_id) AS total_orders, "
        "COUNT(DISTINCT CASE WHEN order_status = 'delivered' THEN order_id END) AS delivered_orders "
        "FROM winter-sensor-474220-u4.datapulse_marts.fct_sales"
    )
    sales_rows = executor.execute_read_only_query(sales_sql)
    sales_data = sales_rows[0] if sales_rows else {}

    net_rev = to_float(sales_data.get("total_net_revenue", 0.0))
    profit = to_float(sales_data.get("total_profit", 0.0))
    margin = round((profit / net_rev * 100), 2) if net_rev > 0 else 0.0
    total_orders = to_int(sales_data.get("total_orders", 0))
    delivered_orders = to_int(sales_data.get("delivered_orders", 0))

    # 2. Total customers from dim_customers
    cust_sql = (
        "SELECT COUNT(customer_id) AS total_customers "
        "FROM winter-sensor-474220-u4.datapulse_marts.dim_customers"
    )
    cust_rows = executor.execute_read_only_query(cust_sql)
    total_customers = to_int(cust_rows[0].get("total_customers", 0)) if cust_rows else 0

    # 3. Total products from dim_products
    prod_sql = (
        "SELECT COUNT(product_id) AS total_products "
        "FROM winter-sensor-474220-u4.datapulse_marts.dim_products"
    )
    prod_rows = executor.execute_read_only_query(prod_sql)
    total_products = to_int(prod_rows[0].get("total_products", 0)) if prod_rows else 0

    # 4. Category profitability from fct_category_sales
    cat_sql = (
        "SELECT product_category, net_revenue, total_profit, profit_margin_percentage "
        "FROM winter-sensor-474220-u4.datapulse_marts.fct_category_sales "
        "ORDER BY total_profit DESC"
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
            )
        )

    # 5. Inventory restock requirements from fct_inventory
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

    return summary, category_list, restock_queue


@router.get("/dashboard", response_model=DashboardAnalyticsResponse)
def get_dashboard_analytics(
    refresh: bool = Query(
        default=False,
        description="Bypass the 600-second cache and fetch fresh data from BigQuery",
    )
):
    """Retrieve verified business intelligence metrics from BigQuery with in-memory caching."""
    global _cached_data, _cached_timestamp

    now = time.time()

    with _cache_lock:
        cache_valid = (
            _cached_data is not None
            and (now - _cached_timestamp) < CACHE_TTL_SECONDS
            and not refresh
        )

        if cache_valid:
            remaining_ttl = int(CACHE_TTL_SECONDS - (now - _cached_timestamp))
            return jsonable_encoder(
                DashboardAnalyticsResponse(
                    summary=_cached_data["summary"],
                    category_profitability=_cached_data["category_profitability"],
                    restock_queue=_cached_data["restock_queue"],
                    cache=CacheMeta(
                        cached=True,
                        cached_at=_cached_data["cached_at"],
                        expires_in_seconds=max(0, remaining_ttl),
                    ),
                )
            )

        try:
            summary, category_list, restock_queue = fetch_warehouse_metrics(
                bigquery_executor
            )

            now_iso = datetime.now(timezone.utc).isoformat()
            _cached_data = {
                "summary": summary,
                "category_profitability": category_list,
                "restock_queue": restock_queue,
                "cached_at": now_iso,
            }
            _cached_timestamp = now

            return jsonable_encoder(
                DashboardAnalyticsResponse(
                    summary=summary,
                    category_profitability=category_list,
                    restock_queue=restock_queue,
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

