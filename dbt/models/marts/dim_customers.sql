SELECT
    customer_id,
    customer_name,
    customer_email,
    city,
    state,

    total_orders,
    completed_orders,
    cancelled_orders,

    total_revenue,
    total_profit,

    average_order_line_value,

    first_order_date,
    latest_order_date

FROM {{ ref('int_customer_orders') }}