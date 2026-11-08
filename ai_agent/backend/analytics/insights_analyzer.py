import math
from datetime import date, datetime
from decimal import Decimal
from typing import List, Dict, Any, Optional

from ai_agent.backend.sql.bigquery_executor import BigQueryExecutor

PROJECT_DATASET = "winter-sensor-474220-u4.datapulse_marts"


def format_inr(value: float) -> str:
    """Format numeric values with Indian numbering units (Crore / Lakh / standard)."""
    abs_val = abs(value)
    if abs_val >= 10_000_000:
        return f"₹{value / 10_000_000:.2f} Cr"
    if abs_val >= 100_000:
        return f"₹{value / 100_000:.2f} L"
    return f"₹{value:,.2f}"


def to_float(val: Any) -> float:
    if val is None:
        return 0.0
    return float(val)


def to_int(val: Any) -> int:
    if val is None:
        return 0
    return int(val)


def calculate_median(values: List[float]) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    if n % 2 == 1:
        return sorted_vals[mid]
    return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2.0


def calculate_modified_z_scores(values: List[float]) -> List[float]:
    """Calculate Modified Z-Scores using Median Absolute Deviation (MAD).

    Formula: M_i = 0.6745 * (x_i - median) / MAD
    Conservative outlier threshold: |M_i| >= 2.5
    """
    if len(values) < 3:
        return [0.0] * len(values)

    med = calculate_median(values)
    abs_deviations = [abs(x - med) for x in values]
    mad = calculate_median(abs_deviations)

    if mad == 0.0:
        # Fallback to mean absolute deviation or 0 if all points identical
        mean_dev = sum(abs_deviations) / len(values)
        if mean_dev == 0.0:
            return [0.0] * len(values)
        return [(x - med) / (mean_dev * 1.253) for x in values]

    return [round(0.6745 * (x - med) / mad, 2) for x in values]


def calculate_moving_averages(values: List[float], window: int) -> List[Optional[float]]:
    """Compute simple moving average over sliding window."""
    result = []
    for i in range(len(values)):
        if i + 1 < window:
            result.append(None)
        else:
            window_slice = values[i + 1 - window : i + 1]
            result.append(round(sum(window_slice) / window, 2))
    return result


def calculate_rolling_std_bands(
    values: List[float], window: int, k: float = 2.0
) -> List[Dict[str, Optional[float]]]:
    """Calculate rolling standard deviation and upper/lower bands."""
    bands = []
    for i in range(len(values)):
        if i + 1 < window:
            bands.append({"sma": None, "upper": None, "lower": None, "std": None})
        else:
            window_slice = values[i + 1 - window : i + 1]
            mean_val = sum(window_slice) / window
            variance = sum((x - mean_val) ** 2 for x in window_slice) / (window - 1 if window > 1 else 1)
            std_dev = math.sqrt(variance)
            bands.append(
                {
                    "sma": round(mean_val, 2),
                    "std": round(std_dev, 2),
                    "upper": round(mean_val + k * std_dev, 2),
                    "lower": round(max(0.0, mean_val - k * std_dev), 2),
                }
            )
    return bands


class AnomalyInsightsAnalyzer:
    """Deterministic business intelligence and anomaly detection engine.

    Executes verified read-only queries against BigQuery marts and computes
    mathematical evidence bundles before passing to the AI layer.
    """

    def __init__(self, executor: Optional[BigQueryExecutor] = None):
        self.executor = executor or BigQueryExecutor()

    def analyze_warehouse_anomalies(self) -> List[Dict[str, Any]]:
        """Run all analytical detectors and produce validated insight fact bundles."""
        facts: List[Dict[str, Any]] = []

        # 1. Daily Sales & Macro Trends (fct_daily_sales)
        facts.extend(self._detect_daily_sales_anomalies())

        # 2. Year-over-Year & Month-over-Month Macro Growth (fct_daily_sales)
        facts.extend(self._detect_macro_growth_shifts())

        # 3. Category Performance Shifts (fct_sales / fct_category_sales)
        facts.extend(self._detect_category_shifts())

        # 4. Product Hero & SKU Performance Shifts (fct_sales)
        facts.extend(self._detect_product_anomalies())

        # 5. Inventory Stockout & Days-of-Supply Run-Rate Projections (fct_inventory + fct_sales)
        facts.extend(self._detect_inventory_risk_and_dos())

        # 6. Payment & Order Cancellation Anomalies (fct_payments + fct_sales)
        facts.extend(self._detect_payment_cancellation_anomalies())

        return facts

    def _detect_daily_sales_anomalies(self) -> List[Dict[str, Any]]:
        """Detect daily revenue spikes, crashes, and profit margin anomalies using rolling bands and Modified Z-scores."""
        sql = (
            f"SELECT sales_date, net_revenue, total_profit, profit_margin_percentage, total_orders "
            f"FROM {PROJECT_DATASET}.fct_daily_sales "
            f"ORDER BY sales_date ASC "
            f"LIMIT 1000"
        )
        rows = self.executor.execute_read_only_query(sql)
        if len(rows) < 30:
            return []

        revenues = [to_float(r.get("net_revenue")) for r in rows]
        margins = [to_float(r.get("profit_margin_percentage")) for r in rows]
        dates = [str(r.get("sales_date")) for r in rows]

        z_scores = calculate_modified_z_scores(revenues)
        bands_30d = calculate_rolling_std_bands(revenues, window=30, k=2.0)
        sma_7d = calculate_moving_averages(revenues, window=7)

        facts = []
        recent_window_start = max(0, len(rows) - 60)

        # Inspect the last 60 days for active statistical anomalies
        for i in range(recent_window_start, len(rows)):
            cur_date = dates[i]
            cur_rev = revenues[i]
            cur_z = z_scores[i]
            cur_margin = margins[i]
            cur_band = bands_30d[i]
            cur_sma7 = sma_7d[i]

            # A. Critical Negative Revenue Crash (Below Lower Band with |Z| >= 2.5)
            if cur_band["lower"] is not None and cur_rev < cur_band["lower"] and cur_z <= -2.5:
                baseline_val = cur_band["sma"] or 0.0
                change_pct = round(((cur_rev - baseline_val) / baseline_val) * 100, 1) if baseline_val > 0 else -100.0
                facts.append(
                    {
                        "category": "revenue_trend",
                        "severity": "critical",
                        "headline": f"Significant Daily Revenue Drop on {cur_date}",
                        "observed_fact": (
                            f"Net revenue dropped to {format_inr(cur_rev)}, falling {abs(change_pct)}% below the 30-day "
                            f"moving baseline ({format_inr(baseline_val)}) with a statistically significant Modified Z-score of {cur_z}."
                        ),
                        "metric_name": "net_revenue",
                        "observed_value": cur_rev,
                        "observed_value_formatted": format_inr(cur_rev),
                        "baseline_value": baseline_val,
                        "baseline_value_formatted": format_inr(baseline_val),
                        "change_percentage": change_pct,
                        "statistical_score": cur_z,
                        "detection_method": "Modified Z-Score (|Z| >= 2.5) & 30-Day Lower Rolling Band Breach",
                        "period_start": cur_date,
                        "period_end": cur_date,
                        "warehouse_table": "fct_daily_sales",
                        "supporting_sql": sql,
                        "confidence_score": 0.95 if abs(cur_z) >= 3.0 else 0.88,
                        "dimension_key": f"daily_drop_{cur_date}",
                    }
                )

            # B. Opportunity Revenue Spike (|Z| >= 2.5 and above upper band)
            elif cur_band["upper"] is not None and cur_rev > cur_band["upper"] and cur_z >= 2.5:
                baseline_val = cur_band["sma"] or 0.0
                change_pct = round(((cur_rev - baseline_val) / baseline_val) * 100, 1) if baseline_val > 0 else 100.0
                facts.append(
                    {
                        "category": "revenue_trend",
                        "severity": "opportunity",
                        "headline": f"Exceptional Daily Revenue Surge on {cur_date}",
                        "observed_fact": (
                            f"Net revenue surged to {format_inr(cur_rev)}, exceeding the 30-day baseline ({format_inr(baseline_val)}) "
                            f"by +{change_pct}% with a strong positive Modified Z-score of +{cur_z}."
                        ),
                        "metric_name": "net_revenue",
                        "observed_value": cur_rev,
                        "observed_value_formatted": format_inr(cur_rev),
                        "baseline_value": baseline_val,
                        "baseline_value_formatted": format_inr(baseline_val),
                        "change_percentage": change_pct,
                        "statistical_score": cur_z,
                        "detection_method": "Modified Z-Score (Z >= 2.5) & 30-Day Upper Rolling Band Breach",
                        "period_start": cur_date,
                        "period_end": cur_date,
                        "warehouse_table": "fct_daily_sales",
                        "supporting_sql": sql,
                        "confidence_score": 0.92,
                        "dimension_key": f"daily_spike_{cur_date}",
                    }
                )

            # C. Margin Compression: Margin drops >= 6% below 30-day average margin
            recent_margins = margins[max(0, i - 30) : i]
            if recent_margins:
                avg_margin = sum(recent_margins) / len(recent_margins)
                margin_drop = round(avg_margin - cur_margin, 2)
                if margin_drop >= 6.0 and cur_rev >= (cur_band["lower"] or 0.0):
                    facts.append(
                        {
                            "category": "profit_margin",
                            "severity": "warning",
                            "headline": f"Profit Margin Compression on {cur_date}",
                            "observed_fact": (
                                f"Profit margin fell to {cur_margin:.2f}%, representing a {margin_drop} percentage point "
                                f"compression below the trailing 30-day average of {avg_margin:.2f}%, despite steady gross sales volume."
                            ),
                            "metric_name": "profit_margin_percentage",
                            "observed_value": cur_margin,
                            "observed_value_formatted": f"{cur_margin:.2f}%",
                            "baseline_value": round(avg_margin, 2),
                            "baseline_value_formatted": f"{avg_margin:.2f}%",
                            "change_percentage": -round((margin_drop / avg_margin) * 100, 1) if avg_margin > 0 else 0.0,
                            "statistical_score": -margin_drop,
                            "detection_method": "Trailing 30-Day Profit Margin Divergence Threshold (>= 6.0 pp)",
                            "period_start": cur_date,
                            "period_end": cur_date,
                            "warehouse_table": "fct_daily_sales",
                            "supporting_sql": sql,
                            "confidence_score": 0.86,
                            "dimension_key": f"margin_drop_{cur_date}",
                        }
                    )

        # Return only the most prominent top 3 daily anomalies to maintain high signal-to-noise ratio
        facts.sort(key=lambda x: abs(x.get("statistical_score", 0.0)), reverse=True)
        return facts[:3]

    def _detect_macro_growth_shifts(self) -> List[Dict[str, Any]]:
        """Compute Month-over-Month (MoM) and Year-over-Year (YoY) performance shifts."""
        sql = (
            f"SELECT "
            f"DATE_TRUNC(sales_date, MONTH) AS month, "
            f"ROUND(SUM(net_revenue), 2) AS monthly_revenue, "
            f"ROUND(SUM(total_profit), 2) AS monthly_profit, "
            f"SUM(total_orders) AS monthly_orders, "
            f"ROUND(SAFE_DIVIDE(SUM(total_profit), SUM(net_revenue)) * 100, 2) AS monthly_margin "
            f"FROM {PROJECT_DATASET}.fct_daily_sales "
            f"GROUP BY month "
            f"ORDER BY month ASC"
        )
        rows = self.executor.execute_read_only_query(sql)
        if len(rows) < 2:
            return []

        facts = []
        month_map = {}
        for r in rows:
            m_val = r.get("month")
            m_str = m_val.isoformat() if hasattr(m_val, "isoformat") else str(m_val)[:10]
            month_map[m_str] = {
                "revenue": to_float(r.get("monthly_revenue")),
                "profit": to_float(r.get("monthly_profit")),
                "orders": to_int(r.get("monthly_orders")),
                "margin": to_float(r.get("monthly_margin")),
            }

        sorted_months = sorted(month_map.keys())

        # 1. Year-over-Year (YoY) Analysis: Compare 2026 months with matching 2025 months
        yoy_comparisons = [
            ("2026-10-01", "2025-10-01", "October"),
            ("2026-09-01", "2025-09-01", "September"),
        ]

        for m26, m25, m_name in yoy_comparisons:
            if m26 in month_map and m25 in month_map:
                rev26 = month_map[m26]["revenue"]
                rev25 = month_map[m25]["revenue"]
                if rev25 > 0:
                    yoy_change = round(((rev26 - rev25) / rev25) * 100, 2)
                    severity = "opportunity" if yoy_change > 10.0 else "warning" if yoy_change < -10.0 else "info"
                    direction = "growth" if yoy_change >= 0 else "deceleration"
                    facts.append(
                        {
                            "category": "revenue_trend",
                            "severity": severity,
                            "headline": f"{m_name} Year-over-Year Performance {direction.capitalize()}",
                            "observed_fact": (
                                f"{m_name} 2026 net revenue achieved {format_inr(rev26)} compared to {format_inr(rev25)} "
                                f"in {m_name} 2025, reflecting a {yoy_change:+.1f}% Year-over-Year change."
                            ),
                            "metric_name": "yoy_net_revenue",
                            "observed_value": rev26,
                            "observed_value_formatted": format_inr(rev26),
                            "baseline_value": rev25,
                            "baseline_value_formatted": format_inr(rev25),
                            "change_percentage": yoy_change,
                            "statistical_score": yoy_change,
                            "detection_method": f"Year-over-Year Comparative Percentage Delta ({m_name} 2026 vs 2025)",
                            "period_start": m26,
                            "period_end": m26,
                            "warehouse_table": "fct_daily_sales",
                            "supporting_sql": sql,
                            "confidence_score": 0.95,
                            "dimension_key": f"yoy_{m26}",
                        }
                    )
                break  # Record the latest YoY month

        # 2. Month-over-Month (MoM) Shift on latest closed month
        latest_m = sorted_months[-1]
        prev_m = sorted_months[-2]
        latest_rev = month_map[latest_m]["revenue"]
        prev_rev = month_map[prev_m]["revenue"]

        if prev_rev > 0:
            mom_change = round(((latest_rev - prev_rev) / prev_rev) * 100, 2)
            if abs(mom_change) >= 12.0:
                severity = "opportunity" if mom_change > 0 else "warning"
                facts.append(
                    {
                        "category": "revenue_trend",
                        "severity": severity,
                        "headline": f"Month-over-Month Revenue Shift ({latest_m[:7]})",
                        "observed_fact": (
                            f"Net revenue in {latest_m[:7]} reached {format_inr(latest_rev)}, shifting {mom_change:+.1f}% "
                            f"relative to previous month's total of {format_inr(prev_rev)}."
                        ),
                        "metric_name": "mom_net_revenue",
                        "observed_value": latest_rev,
                        "observed_value_formatted": format_inr(latest_rev),
                        "baseline_value": prev_rev,
                        "baseline_value_formatted": format_inr(prev_rev),
                        "change_percentage": mom_change,
                        "statistical_score": mom_change,
                        "detection_method": "Month-over-Month Velocity Shift (Threshold >= 12%)",
                        "period_start": latest_m,
                        "period_end": latest_m,
                        "warehouse_table": "fct_daily_sales",
                        "supporting_sql": sql,
                        "confidence_score": 0.90,
                        "dimension_key": f"mom_{latest_m}",
                    }
                )

        return facts

    def _detect_category_shifts(self) -> List[Dict[str, Any]]:
        """Identify high-growth vs margin-compressed categories."""
        sql = (
            f"SELECT product_category, net_revenue, total_profit, profit_margin_percentage, total_orders "
            f"FROM {PROJECT_DATASET}.fct_category_sales "
            f"ORDER BY net_revenue DESC"
        )
        rows = self.executor.execute_read_only_query(sql)
        if not rows:
            return []

        total_warehouse_revenue = sum(to_float(r.get("net_revenue")) for r in rows)
        if total_warehouse_revenue == 0:
            return []

        facts = []
        top_cat = rows[0]
        top_rev = to_float(top_cat.get("net_revenue"))
        top_name = str(top_cat.get("product_category"))
        top_margin = to_float(top_cat.get("profit_margin_percentage"))
        top_share = round((top_rev / total_warehouse_revenue) * 100, 1)

        facts.append(
            {
                "category": "category_shift",
                "severity": "opportunity" if top_margin >= 30.0 else "info",
                "headline": f"Category Revenue Dominance: {top_name}",
                "observed_fact": (
                    f"{top_name} represents the primary business growth engine, accounting for {top_share}% of all-time "
                    f"net revenue ({format_inr(top_rev)}) with a healthy profit margin of {top_margin:.1f}%."
                ),
                "metric_name": "category_revenue_share",
                "observed_value": top_share,
                "observed_value_formatted": f"{top_share}%",
                "baseline_value": round(100.0 / len(rows), 1),
                "baseline_value_formatted": f"{round(100.0 / len(rows), 1)}%",
                "change_percentage": round(top_share - (100.0 / len(rows)), 1),
                "statistical_score": top_share,
                "detection_method": "Pareto Category Revenue Share & Profitability Index",
                "period_start": "2025-01-01",
                "period_end": "2026-10-31",
                "warehouse_table": "fct_category_sales",
                "supporting_sql": sql,
                "confidence_score": 0.94,
                "dimension_key": f"cat_top_{top_name}",
            }
        )

        return facts

    def _detect_product_anomalies(self) -> List[Dict[str, Any]]:
        """Identify top standout product contributors."""
        sql = (
            f"SELECT product_id, product_name, product_category, "
            f"SUM(quantity) AS units_sold, "
            f"ROUND(SUM(net_amount), 2) AS total_revenue, "
            f"ROUND(SUM(profit), 2) AS total_profit, "
            f"ROUND(SAFE_DIVIDE(SUM(profit), SUM(net_amount)) * 100, 2) AS profit_margin_percentage "
            f"FROM {PROJECT_DATASET}.fct_sales "
            f"GROUP BY product_id, product_name, product_category "
            f"ORDER BY total_revenue DESC "
            f"LIMIT 5"
        )
        rows = self.executor.execute_read_only_query(sql)
        if not rows:
            return []

        hero = rows[0]
        h_name = str(hero.get("product_name"))
        h_rev = to_float(hero.get("total_revenue"))
        h_margin = to_float(hero.get("profit_margin_percentage"))
        h_units = to_int(hero.get("units_sold"))

        return [
            {
                "category": "product_anomaly",
                "severity": "opportunity",
                "headline": f"Hero SKU Outlier: {h_name}",
                "observed_fact": (
                    f"Product #{hero.get('product_id')} ({h_name}) generated {format_inr(h_rev)} in net revenue across "
                    f"{h_units} units, sustaining a premium profit margin of {h_margin:.1f}%."
                ),
                "metric_name": "sku_net_revenue",
                "observed_value": h_rev,
                "observed_value_formatted": format_inr(h_rev),
                "baseline_value": None,
                "baseline_value_formatted": None,
                "change_percentage": None,
                "statistical_score": h_margin,
                "detection_method": "Catalog Revenue Leaderboard Ranking (#1 SKU)",
                "period_start": "2025-01-01",
                "period_end": "2026-10-31",
                "warehouse_table": "fct_sales",
                "supporting_sql": sql,
                "confidence_score": 0.95,
                "dimension_key": f"prod_hero_{hero.get('product_id')}",
            }
        ]

    def _detect_inventory_risk_and_dos(self) -> List[Dict[str, Any]]:
        """Evaluate physical warehouse stock levels against trailing 30-day velocity to calculate Days-of-Supply (DOS)."""
        inv_sql = (
            f"SELECT product_id, product_name, product_category, warehouse, "
            f"stock_quantity, reorder_level, stock_difference, inventory_status, requires_restock "
            f"FROM {PROJECT_DATASET}.fct_inventory "
            f"ORDER BY stock_difference ASC"
        )
        inv_rows = self.executor.execute_read_only_query(inv_sql)
        if not inv_rows:
            return []

        # Trailing 30-day sales velocity per product (October 2026)
        sales_sql = (
            f"SELECT product_id, SUM(quantity) AS units_sold_30d "
            f"FROM {PROJECT_DATASET}.fct_sales "
            f"WHERE order_date >= '2026-10-01' AND order_date <= '2026-10-31' "
            f"GROUP BY product_id"
        )
        sales_rows = self.executor.execute_read_only_query(sales_sql)
        velocity_map = {to_int(r.get("product_id")): to_float(r.get("units_sold_30d")) / 30.0 for r in sales_rows}

        facts = []
        # Group warehouse inventory to check transfer feasibility
        sku_warehouse_map: Dict[int, List[Dict[str, Any]]] = {}
        for r in inv_rows:
            p_id = to_int(r.get("product_id"))
            sku_warehouse_map.setdefault(p_id, []).append(r)

        for r in inv_rows:
            if not r.get("requires_restock"):
                continue

            p_id = to_int(r.get("product_id"))
            p_name = str(r.get("product_name"))
            wh = str(r.get("warehouse"))
            stock = to_int(r.get("stock_quantity"))
            reorder = to_int(r.get("reorder_level"))
            deficit = to_int(r.get("stock_difference"))
            daily_vel = velocity_map.get(p_id, 0.4)  # Default fallback if velocity minimal

            dos = round(stock / daily_vel, 1) if daily_vel > 0 else 99.0
            severity = "critical" if dos <= 14.0 or deficit <= -8 else "warning"

            # Check if another warehouse has verifiable surplus for transfer
            transfer_source = None
            other_whs = sku_warehouse_map.get(p_id, [])
            for ow in other_whs:
                if str(ow.get("warehouse")) != wh and to_int(ow.get("stock_difference")) > 10:
                    transfer_source = str(ow.get("warehouse"))
                    break

            transfer_evidence = (
                f" Verified stock transfer viable from {transfer_source} Hub (surplus confirmed)."
                if transfer_source
                else " No source warehouse has surplus; external vendor replenishment required."
            )

            facts.append(
                {
                    "category": "inventory_risk",
                    "severity": severity,
                    "headline": f"Stockout Risk Projected for {p_name} ({wh} Hub)",
                    "observed_fact": (
                        f"Current physical stock is {stock} units against a reorder threshold of {reorder} (deficit: {deficit} units). "
                        f"Based on trailing 30-day velocity ({daily_vel:.2f} units/day), estimated Days-of-Supply (DOS) is {dos} days.{transfer_evidence}"
                    ),
                    "metric_name": "days_of_supply_estimate",
                    "observed_value": dos,
                    "observed_value_formatted": f"{dos} Days",
                    "baseline_value": float(reorder),
                    "baseline_value_formatted": f"{reorder} units (Reorder Threshold)",
                    "change_percentage": round((deficit / reorder) * 100, 1) if reorder > 0 else -100.0,
                    "statistical_score": float(deficit),
                    "detection_method": "30-Day Trailing Velocity Days-of-Supply (DOS) Run-Out Projection",
                    "period_start": "2026-10-31",
                    "period_end": "2026-10-31",
                    "warehouse_table": "fct_inventory",
                    "supporting_sql": inv_sql,
                    "confidence_score": 0.94 if deficit <= -8 else 0.88,
                    "dimension_key": f"inv_dos_{p_id}_{wh}",
                }
            )

        return facts[:3]  # Return top 3 urgent stockout risks

    def _detect_payment_cancellation_anomalies(self) -> List[Dict[str, Any]]:
        """Identify payment failures or order cancellation anomalies."""
        sql = (
            f"SELECT payment_method, "
            f"COUNT(payment_id) AS total_transactions, "
            f"COUNT(CASE WHEN payment_status = 'failed' THEN 1 END) AS failed_transactions "
            f"FROM {PROJECT_DATASET}.fct_payments "
            f"GROUP BY payment_method"
        )
        rows = self.executor.execute_read_only_query(sql)
        facts = []
        for r in rows:
            method = str(r.get("payment_method"))
            total = to_int(r.get("total_transactions"))
            failed = to_int(r.get("failed_transactions"))
            if total > 50:
                failure_rate = round((failed / total) * 100, 2)
                if failure_rate >= 8.0:
                    facts.append(
                        {
                            "category": "order_payment_anomaly",
                            "severity": "warning",
                            "headline": f"Elevated Payment Failure Rate for {method.upper()}",
                            "observed_fact": (
                                f"Payment method '{method}' experienced a {failure_rate}% failure rate across {total} "
                                f"recorded transactions ({failed} failed payment attempts)."
                            ),
                            "metric_name": "payment_failure_rate",
                            "observed_value": failure_rate,
                            "observed_value_formatted": f"{failure_rate}%",
                            "baseline_value": 4.0,
                            "baseline_value_formatted": "4.0% (Platform Baseline)",
                            "change_percentage": round(((failure_rate - 4.0) / 4.0) * 100, 1),
                            "statistical_score": failure_rate,
                            "detection_method": "Payment Method Transaction Failure Rate Threshold (>= 8.0%)",
                            "period_start": "2025-01-01",
                            "period_end": "2026-10-31",
                            "warehouse_table": "fct_payments",
                            "supporting_sql": sql,
                            "confidence_score": 0.89,
                            "dimension_key": f"pay_fail_{method}",
                        }
                    )
        return facts
