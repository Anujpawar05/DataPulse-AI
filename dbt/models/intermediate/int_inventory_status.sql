{{ config(materialized='view') }}

SELECT
    i.product_id,
    p.product_name,
    p.category,
    i.warehouse,
    i.stock_quantity,
    i.reorder_level,

    CASE
        WHEN i.stock_quantity = 0 THEN 'out_of_stock'
        WHEN i.stock_quantity <= i.reorder_level THEN 'low_stock'
        ELSE 'in_stock'
    END AS inventory_status,

    i.stock_quantity - i.reorder_level AS stock_difference

FROM {{ ref('stg_inventory') }} i

INNER JOIN {{ ref('stg_products') }} p
    ON i.product_id = p.product_id