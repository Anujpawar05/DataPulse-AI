SELECT
    product_id,
    product_name,
    category AS product_category,
    warehouse,

    stock_quantity,
    reorder_level,
    stock_difference,
    inventory_status,

    CASE
        WHEN inventory_status = 'low_stock'
          OR inventory_status = 'out_of_stock'
        THEN TRUE
        ELSE FALSE
    END AS requires_restock

FROM {{ ref('int_inventory_status') }}