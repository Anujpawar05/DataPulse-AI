{{ config(materialized='view') }}

SELECT
    id,
    products,
    CAST(total AS NUMERIC) AS total,
    CAST(discountedTotal AS NUMERIC) AS discounted_total,
    userId AS user_id,
    totalProducts AS total_products,
    totalQuantity AS total_quantity
FROM {{ source('datapulse_raw', 'api_carts') }}