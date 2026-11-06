{{ config(materialized='view') }}

SELECT
    product_id,
    TRIM(product_name) AS product_name,
    TRIM(category) AS product_category,
    price,
    cost,
    is_active,
    created_at

FROM {{ ref('stg_products') }}