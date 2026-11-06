{{ config(materialized='view') }}

SELECT
    customer_id,
    customer_name,
    customer_email,
    city,
    state,

    COUNT(DISTINCT order_id) AS total_orders,

    COUNT(DISTINCT CASE
        WHEN order_status = 'completed' THEN order_id
    END) AS completed_orders,

    COUNT(DISTINCT CASE
        WHEN order_status = 'cancelled' THEN order_id
    END) AS cancelled_orders,

    SUM(net_amount) AS total_revenue,
    SUM(profit) AS total_profit,

    AVG(net_amount) AS average_order_line_value,

    MIN(order_date) AS first_order_date,
    MAX(order_date) AS latest_order_date

FROM {{ ref('int_order_details') }}

GROUP BY
    customer_id,
    customer_name,
    customer_email,
    city,
    state