{{ config(materialized='view') }}

SELECT
    product_id,
    product_name,
    product_category,

    COUNT(DISTINCT order_id) AS total_orders,
    COUNT(DISTINCT sale_id) AS total_sales,
    SUM(quantity) AS units_sold,

    SUM(gross_amount) AS gross_revenue,
    SUM(net_amount) AS net_revenue,
    SUM(total_cost) AS total_cost,
    SUM(profit) AS total_profit,

    SAFE_DIVIDE(
        SUM(profit),
        SUM(net_amount)
    ) * 100 AS profit_margin_percentage

FROM {{ ref('int_order_details') }}

GROUP BY
    product_id,
    product_name,
    product_category