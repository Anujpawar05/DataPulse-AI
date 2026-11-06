{{ config(materialized='view') }}

SELECT
    product_category,
    total_orders,
    total_sales,
    total_products,
    units_sold,
    gross_revenue,
    net_revenue,
    total_cost,
    total_profit,
    profit_margin_percentage

FROM {{ ref('int_category_sales') }}
