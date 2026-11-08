# DataPulse AI — Business Glossary

## Sales Metrics

### Total Revenue
The total net sales amount generated from completed sales.
Source: fct_sales.net_amount
Calculation: SUM(net_amount)

### Total Profit
The total profit generated from sales.
Source: fct_sales.profit
Calculation: SUM(profit)

### Profit Margin
The percentage of revenue retained as profit.
Calculation: (Total Profit / Total Revenue) × 100

### Average Order Value (AOV)
The average revenue generated per distinct order.
Calculation: Total Revenue / Total Orders

### Total Orders
The number of distinct orders represented in the sales fact table.
Source: fct_sales.order_id
Calculation: DISTINCTCOUNT(order_id)

### Total Units Sold
The total quantity of products sold.
Source: fct_sales.quantity
Calculation: SUM(quantity)

## Customer Metrics

### Total Customers
The number of distinct customers represented in sales.
Source: fct_sales.customer_id
Calculation: DISTINCTCOUNT(customer_id)

## Inventory Metrics

### Inventory Status
The inventory position of products based on available stock. Valid values: 'in_stock', 'low_stock', 'out_of_stock'.
Source: fct_inventory.inventory_status

### Low Stock Products
Products identified as low in stock or needing replenishment.
Condition: inventory_status = 'low_stock' OR requires_restock = TRUE OR stock_quantity <= reorder_level
Source: fct_inventory

### Out of Stock Products
Products with zero stock remaining.
Condition: inventory_status = 'out_of_stock' OR stock_quantity = 0
Source: fct_inventory

### Reorder Level
The minimum quantity threshold before a restock is triggered.
Source: fct_inventory.reorder_level

### Restock Requirement
Flag indicating whether restocking is necessary.
Source: fct_inventory.requires_restock

## Query Rules

- Use the approved analytics dataset only.
- Use existing model definitions and column names.
- Do not invent metrics or database columns.
- Ask for clarification when a business question is ambiguous.
- Do not expose private customer information.
