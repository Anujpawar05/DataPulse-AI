SELECT
    payment_id,
    order_id,
    customer_id,

    order_date,
    order_status,

    payment_method,
    payment_amount,
    payment_status,
    payment_date,

    successful_payment_amount,

    CASE
        WHEN payment_status = 'completed' THEN 1
        ELSE 0
    END AS is_successful_payment

FROM {{ ref('int_payment_summary') }}