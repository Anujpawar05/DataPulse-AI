{{ config(materialized='view') }}

SELECT
    order_id,
    customer_id,
    order_date,
    LOWER(TRIM(order_status)) AS order_status,
    created_at
FROM {{ source('datapulse_raw', 'orders') }}