{{ config(materialized='view') }}

SELECT
    payment_id,
    order_id,
    LOWER(TRIM(payment_method)) AS payment_method,
    CAST(amount AS NUMERIC) AS amount,
    LOWER(TRIM(payment_status)) AS payment_status,
    transaction_reference,
    payment_date,
    created_at
FROM {{ source('datapulse_raw', 'payments') }}