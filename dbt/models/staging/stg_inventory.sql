{{ config(materialized='view') }}

SELECT
    product_id,
    TRIM(warehouse) AS warehouse,
    stock_quantity,
    reorder_level
FROM {{ source('datapulse_raw', 'inventory') }}