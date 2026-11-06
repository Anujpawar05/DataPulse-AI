{{ config(materialized='view') }}

SELECT
    sale_id,
    order_id,
    product_id,
    line_number,
    quantity,
    CAST(unit_price AS NUMERIC) AS unit_price,
    CAST(unit_cost AS NUMERIC) AS unit_cost,
    CAST(discount_amount AS NUMERIC) AS discount_amount
FROM {{ source('datapulse_raw', 'sales') }}