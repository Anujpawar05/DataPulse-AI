SELECT
    sales_date,
    total_orders,
    total_sales,
    units_sold,
    gross_revenue,
    net_revenue,
    total_cost,
    total_profit,

    SAFE_DIVIDE(
        total_profit,
        net_revenue
    ) * 100 AS profit_margin_percentage

FROM {{ ref('int_daily_sales') }}