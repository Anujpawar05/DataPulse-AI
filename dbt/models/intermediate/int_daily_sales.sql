{{ config(materialized='view') }}

SELECT
    DATE(order_date) AS sales_date,

    COUNT(DISTINCT order_id) AS total_orders,
    COUNT(DISTINCT sale_id) AS total_sales,
    SUM(quantity) AS units_sold,

    SUM(gross_amount) AS gross_revenue,
    SUM(net_amount) AS net_revenue,
    SUM(total_cost) AS total_cost,
    SUM(profit) AS total_profit

FROM {{ ref('int_order_details') }}

GROUP BY DATE(order_date)