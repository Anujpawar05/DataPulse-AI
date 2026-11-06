{{ config(materialized='view') }}

SELECT
    o.customer_id,
    o.order_id,
    o.order_date,
    o.order_status,

    p.payment_id,
    p.payment_method,
    p.amount AS payment_amount,
    p.payment_status,
    p.payment_date,

    CASE
        WHEN p.payment_status = 'completed'
        THEN p.amount
        ELSE 0
    END AS successful_payment_amount

FROM {{ ref('stg_orders') }} o

INNER JOIN {{ ref('stg_payments') }} p
    ON o.order_id = p.order_id