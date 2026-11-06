{{ config(materialized='view') }}

SELECT
    o.order_id,
    o.customer_id,
    c.full_name AS customer_name,
    c.email AS customer_email,
    c.city,
    c.state,
    o.order_date,
    o.order_status,
    s.sale_id,
    s.product_id,
    p.product_name,
    p.category AS product_category,
    s.quantity,
    s.unit_price,
    s.unit_cost,
    s.discount_amount,

    (s.quantity * s.unit_price) AS gross_amount,

    (s.quantity * s.unit_price - s.discount_amount) AS net_amount,

    (s.quantity * s.unit_cost) AS total_cost,

    (
        s.quantity * s.unit_price
        - s.discount_amount
        - s.quantity * s.unit_cost
    ) AS profit

FROM {{ ref('stg_orders') }} o

INNER JOIN {{ ref('stg_customers') }} c
    ON o.customer_id = c.customer_id

INNER JOIN {{ ref('stg_sales') }} s
    ON o.order_id = s.order_id

INNER JOIN {{ ref('stg_products') }} p
    ON s.product_id = p.product_id