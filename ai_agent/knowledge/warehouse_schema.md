#- Dataset: `datapulse_marts`
- Location: `asia-south1`
- Access: Read-only
- Approved objects: The seven marts listed below

## 1. dim_customers

**Purpose:** Customer-level order and revenue summary.

Columns:
- `customer_id`
- `customer_name`
- `customer_email`
- `city`
- `state`
- `total_orders`
- `completed_orders`
- `cancelled_orders`
- `total_revenue`
- `total_profit`
- `average_order_line_value`
- `first_order_date`
- `latest_order_date`

## 2. dim_products

**Purpose:** Product and category information.

Columns:
- `product_id`
- `product_name`
- `product_category`
- `price`
- `cost`
- `is_active`
- `created_at`

## 3. fct_category_sales

**Purpose:** Aggregated sales performance by product category.

Columns:
- `product_category`
- `total_orders`
- `total_sales`
- `total_products`
- `units_sold`
- `gross_revenue`
- `net_revenue`
- `total_cost`
- `total_profit`
- `profit_margin_percentage`

## 4. fct_daily_sales

**Purpose:** Daily sales and profitability metrics.

Columns:
- `sales_date`
- `total_orders`
- `total_sales`
- `units_sold`
- `gross_revenue`
- `net_revenue`
- `total_cost`
- `total_profit`
- `profit_margin_percentage`

Profit margin calculation:
`SAFE_DIVIDE(total_profit, net_revenue) * 100`

## 5. fct_inventory

**Purpose:** Product stock and replenishment monitoring.

Columns:
- `product_id`
- `product_name`
- `product_category`
- `warehouse`
- `stock_quantity`
- `reorder_level`
- `stock_difference`
- `inventory_status`
- `requires_restock`

`requires_restock` is TRUE when inventory status is `low_stock` or `out_of_stock` (or `stock_quantity <= reorder_level`).

Inventory status values:
- `in_stock`: Normal stock levels (`stock_difference > 0`).
- `low_stock`: Stock is low and below/at reorder level (`stock_difference <= 0`), requiring replenishment.
- `out_of_stock`: Stock is completely exhausted (`stock_quantity = 0`).

## 6. fct_payments

**Purpose:** Payment and order payment-status analysis.

Columns:
- `payment_id`
- `order_id`
- `customer_id`
- `order_date`
- `order_status`
- `payment_method`
- `payment_amount`
- `payment_status`
- `payment_date`
- `successful_payment_amount`
- `is_successful_payment`

`is_successful_payment` is 1 when payment status is `completed`, otherwise 0.

## 7. fct_sales

**Purpose:** Detailed sales transactions and profitability.

Columns:
- `sale_id`
- `order_id`
- `customer_id`
- `customer_name`
- `city`
- `state`
- `order_date`
- `order_status`
- `product_id`
- `product_name`
- `product_category`
- `quantity`
- `unit_price`
- `unit_cost`
- `discount_amount`
- `gross_amount`
- `net_amount`
- `total_cost`
- `profit`
- `profit_margin_percentage`

Profit margin calculation:
`SAFE_DIVIDE(profit, net_amount) * 100`

## Known relationships

Based on the mart definitions and existing dashboard model:

- `dim_customers.customer_id` → `fct_sales.customer_id`
- `dim_customers.customer_id` → `fct_payments.customer_id`
- `dim_products.product_id` → `fct_sales.product_id`
- `dim_products.product_id` → `fct_inventory.product_id`

Other relationships must be verified before use.

## SQL generation rules

1. Fully qualify tables using `winter-sensor-474220-u4.datapulse_marts`.
2. Query only the seven approved marts.
3. Use only columns documented in this file.
4. Use `SAFE_DIVIDE` for division.
5. Never assume undocumented relationships.
6. Do not access raw warehouse tables or staging/intermediate models.
7. Generate read-only SELECT statements only.
8. Never expose customer email addresses or other personal information in answers.
9. If a requested metric or column is not documented, ask for clarification