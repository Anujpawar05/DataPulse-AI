{{ config(materialized='view') }}

SELECT
    product_id,
    TRIM(product_name) AS product_name,
    TRIM(category) AS category,
    CAST(price AS NUMERIC) AS price,
    CAST(cost AS NUMERIC) AS cost,
    is_active,
    created_at
FROM {{ source('datapulse_raw', 'products') }}