{{ config(materialized='view') }}

SELECT
    sale_id,
    order_id,
    customer_id,
    customer_name,
    city,
    state,
    order_date,
    order_status,

    product_id,
    product_name,
    product_category,

    quantity,
    unit_price,
    unit_cost,
    discount_amount,

    gross_amount,
    net_amount,
    total_cost,
    profit,

    SAFE_DIVIDE(
        profit,
        net_amount
    ) * 100 AS profit_margin_percentage

FROM {{ ref('int_order_details') }}