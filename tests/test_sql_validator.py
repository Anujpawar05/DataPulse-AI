import pytest

from ai_agent.backend.sql.validator import (
    validate_sql,
    SQLValidationError,
)


def test_valid_select_query():
    query = """
        SELECT product_name, stock_quantity
        FROM `winter-sensor-474220-u4.datapulse_marts.fct_inventory`
        WHERE requires_restock = TRUE
    """

    result = validate_sql(query)

    assert "fct_inventory" in result
    assert "LIMIT 1000" in result


def test_reject_unapproved_table():
    query = """
        SELECT *
        FROM `winter-sensor-474220-u4.datapulse_marts.unknown_table`
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)


def test_reject_wrong_dataset():
    query = """
        SELECT *
        FROM `winter-sensor-474220-u4.other_dataset.fct_inventory`
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)


def test_reject_delete_query():
    query = """
        DELETE FROM `winter-sensor-474220-u4.datapulse_marts.fct_inventory`
        WHERE product_id = 1
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)


def test_reject_multiple_statements():
    query = """
        SELECT product_id
        FROM `winter-sensor-474220-u4.datapulse_marts.fct_inventory`;

        DROP TABLE `winter-sensor-474220-u4.datapulse_marts.fct_inventory`
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)


def test_reject_customer_email():
    query = """
        SELECT customer_email
        FROM `winter-sensor-474220-u4.datapulse_marts.dim_customers`
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)


def test_reject_limit_above_maximum():
    query = """
        SELECT product_id
        FROM `winter-sensor-474220-u4.datapulse_marts.fct_inventory`
        LIMIT 5000
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_customer_select_star():
    query = """
        SELECT *
        FROM `winter-sensor-474220-u4.datapulse_marts.dim_customers`
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)


def test_reject_customer_alias_wildcard():
    query = """
        SELECT c.*
        FROM `winter-sensor-474220-u4.datapulse_marts.dim_customers` AS c
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_accept_valid_cte():
    query = """
        WITH inventory AS (
            SELECT product_name, stock_quantity
            FROM `winter-sensor-474220-u4.datapulse_marts.fct_inventory`
        )
        SELECT product_name, stock_quantity
        FROM inventory
    """

    result = validate_sql(query)

    assert "fct_inventory" in result
    assert "LIMIT 1000" in result


def test_reject_unapproved_table_inside_cte():
    query = """
        WITH data AS (
            SELECT product_id
            FROM `winter-sensor-474220-u4.datapulse_marts.unknown_table`
        )
        SELECT product_id
        FROM data
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)


def test_reject_unapproved_table_inside_nested_query():
    query = """
        SELECT product_id
        FROM `winter-sensor-474220-u4.datapulse_marts.fct_inventory`
        WHERE product_id IN (
            SELECT product_id
            FROM `winter-sensor-474220-u4.datapulse_marts.unknown_table`
        )
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)


def test_reject_wildcard_inside_nested_query():
    query = """
        SELECT product_id
        FROM `winter-sensor-474220-u4.datapulse_marts.fct_inventory`
        WHERE product_id IN (
            SELECT *
            FROM `winter-sensor-474220-u4.datapulse_marts.dim_products`
        )
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_unqualified_physical_table():
    query = """
        SELECT product_id
        FROM fct_inventory
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_unapproved_table_in_union():
    query = """
        SELECT product_id
        FROM `winter-sensor-474220-u4.datapulse_marts.fct_inventory`

        UNION ALL

        SELECT product_id
        FROM `winter-sensor-474220-u4.datapulse_marts.unknown_table`
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_customer_email_inside_cte():
    query = """
        WITH customer_data AS (
            SELECT customer_email
            FROM `winter-sensor-474220-u4.datapulse_marts.dim_customers`
        )
        SELECT customer_email
        FROM customer_data
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_limit_above_maximum_inside_cte():
    query = """
        WITH inventory AS (
            SELECT product_id
            FROM `winter-sensor-474220-u4.datapulse_marts.fct_inventory`
            LIMIT 5000
        )
        SELECT product_id
        FROM inventory
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_external_query():
    query = """
        SELECT *
        FROM EXTERNAL_QUERY(
            "connection_id",
            "SELECT * FROM users"
        )
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_ml_predict():
    query = """
        SELECT *
        FROM ML.PREDICT(
            MODEL `winter-sensor-474220-u4.datapulse_marts.some_model`,
            TABLE `winter-sensor-474220-u4.datapulse_marts.fct_sales`
        )
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_tablesample():
    query = """
        SELECT product_id
        FROM `winter-sensor-474220-u4.datapulse_marts.fct_sales`
        TABLESAMPLE SYSTEM (10 PERCENT)
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)


def test_reject_historical_table_access():
    query = """
        SELECT product_id
        FROM `winter-sensor-474220-u4.datapulse_marts.fct_sales`
        FOR SYSTEM_TIME AS OF
        TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_unapproved_inventory_column():
    query = """
        SELECT customer_email
        FROM `winter-sensor-474220-u4.datapulse_marts.fct_inventory`
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)


def test_reject_unapproved_column_for_table():
    query = """
        SELECT payment_method
        FROM `winter-sensor-474220-u4.datapulse_marts.fct_inventory`
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)


def test_accept_valid_table_alias():
    query = """
        SELECT i.product_name, i.stock_quantity
        FROM `winter-sensor-474220-u4.datapulse_marts.fct_inventory` AS i
    """

    assert "LIMIT 1000" in validate_sql(query)


def test_accept_valid_join():
    query = """
        SELECT s.product_name, p.price
        FROM `winter-sensor-474220-u4.datapulse_marts.fct_sales` AS s
        JOIN `winter-sensor-474220-u4.datapulse_marts.dim_products` AS p
        ON s.product_id = p.product_id
    """

    assert "LIMIT 1000" in validate_sql(query)

def test_reject_unapproved_column_inside_cte():
    query = """
        WITH inventory AS (
            SELECT payment_method
            FROM `winter-sensor-474220-u4.datapulse_marts.fct_inventory`
        )
        SELECT payment_method
        FROM inventory
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)


def test_reject_unapproved_column_inside_nested_query():
    query = """
        SELECT product_id
        FROM `winter-sensor-474220-u4.datapulse_marts.fct_inventory`
        WHERE product_id IN (
            SELECT payment_method
            FROM `winter-sensor-474220-u4.datapulse_marts.fct_inventory`
        )
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)


def test_reject_unknown_table_alias():
    query = """
        SELECT x.stock_quantity
        FROM `winter-sensor-474220-u4.datapulse_marts.fct_inventory` AS i
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_ambiguous_unqualified_join_column():
    query = """
        SELECT customer_id
        FROM `winter-sensor-474220-u4.datapulse_marts.fct_sales` AS s
        JOIN `winter-sensor-474220-u4.datapulse_marts.dim_customers` AS c
        ON s.customer_id = c.customer_id
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_accept_qualified_duplicate_join_column():
    query = """
        SELECT s.customer_id, c.customer_name
        FROM `winter-sensor-474220-u4.datapulse_marts.fct_sales` AS s
        JOIN `winter-sensor-474220-u4.datapulse_marts.dim_customers` AS c
        ON s.customer_id = c.customer_id
    """

    assert "LIMIT 1000" in validate_sql(query)

def test_reject_unapproved_cte_output_column():
    query = """
        WITH inventory AS (
            SELECT product_name AS safe_name
            FROM `winter-sensor-474220-u4.datapulse_marts.fct_inventory`
        )
        SELECT stock_quantity
        FROM inventory
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_unapproved_subquery_output_column():
    query = """
        SELECT stock_quantity
        FROM (
            SELECT product_name
            FROM `winter-sensor-474220-u4.datapulse_marts.fct_inventory`
        ) AS inventory_data
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_unapproved_nested_column_alias():
    query = """
        SELECT inventory_data.payment_method
        FROM (
            SELECT product_name
            FROM `winter-sensor-474220-u4.datapulse_marts.fct_inventory`
        ) AS inventory_data
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_bigquery_declare_statement():
    query = """
        DECLARE total_count INT64 DEFAULT 0;
        SELECT product_id
        FROM `winter-sensor-474220-u4.datapulse_marts.fct_inventory`
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_execute_immediate():
    query = """
        EXECUTE IMMEDIATE
        'SELECT product_id FROM `winter-sensor-474220-u4.datapulse_marts.fct_inventory`'
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_unnest_table_source():
    query = """
        SELECT item
        FROM UNNEST([1, 2, 3]) AS item
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_generate_array_table_source():
    query = """
        SELECT number
        FROM UNNEST(GENERATE_ARRAY(1, 10)) AS number
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_external_query_with_alias():
    query = """
        SELECT external_data.customer_id
        FROM EXTERNAL_QUERY(
            "connection_id",
            "SELECT customer_id FROM customers"
        ) AS external_data
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_unapproved_pivot_column():
    query = """
        SELECT *
        FROM (
            SELECT product_category, net_amount
            FROM `winter-sensor-474220-u4.datapulse_marts.fct_sales`
        )
        PIVOT (
            SUM(net_amount)
            FOR product_category IN ('Electronics')
        )
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_unapproved_column_in_qualify():
    query = """
        SELECT product_id, product_name
        FROM `winter-sensor-474220-u4.datapulse_marts.fct_inventory`
        QUALIFY payment_method = 'UPI'
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_select_alias_used_as_unauthorized_where_column():
    query = """
        SELECT net_amount AS payment_method
        FROM `winter-sensor-474220-u4.datapulse_marts.fct_sales`
        WHERE payment_method = 'UPI'
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_accept_select_alias_used_in_having():
    query = """
        SELECT SUM(net_amount) AS payment_method
        FROM `winter-sensor-474220-u4.datapulse_marts.fct_sales`
        HAVING payment_method = 100
    """

    result = validate_sql(query)
    assert "HAVING" in result.upper()

def test_accept_select_alias_used_in_group_by():
    query = """
        SELECT product_category AS category, SUM(net_amount) AS revenue
        FROM `winter-sensor-474220-u4.datapulse_marts.fct_sales`
        GROUP BY category
    """

    result = validate_sql(query)
    assert "GROUP BY" in result.upper()

def test_accept_cte_shadowing_approved_table():
    query = """
        WITH fct_sales AS (
            SELECT product_id
            FROM `winter-sensor-474220-u4.datapulse_marts.fct_inventory`
        )
        SELECT product_id
        FROM fct_sales
    """

    result = validate_sql(query)
    assert "fct_sales" in result

def test_reject_cte_outside_its_scope():
    query = """
        SELECT product_id
        FROM fct_sales
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_cte_outside_its_scope():
    query = """
        SELECT product_id
        FROM fct_sales
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_nested_cte_reference_outside_scope():
    query = """
        SELECT product_id
        FROM (
            WITH fct_sales AS (
                SELECT product_id
                FROM `winter-sensor-474220-u4.datapulse_marts.fct_inventory`
            )
            SELECT product_id
            FROM fct_sales
        ) AS nested
        UNION ALL
        SELECT product_id
        FROM fct_sales
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_unauthorized_cte_column_alias():
    query = """
        WITH sales_summary AS (
            SELECT net_amount AS customer_email
            FROM `winter-sensor-474220-u4.datapulse_marts.fct_sales`
        )
        SELECT customer_email
        FROM sales_summary
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_blocked_column_through_nested_ctes():
    query = """
        WITH first_cte AS (
            SELECT net_amount AS customer_email
            FROM `winter-sensor-474220-u4.datapulse_marts.fct_sales`
        ),
        second_cte AS (
            SELECT customer_email
            FROM first_cte
        )
        SELECT customer_email
        FROM second_cte
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_blocked_column_through_nested_subquery():
    query = """
        SELECT customer_email
        FROM (
            SELECT net_amount AS customer_email
            FROM `winter-sensor-474220-u4.datapulse_marts.fct_sales`
        ) AS nested
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_blocked_column_through_join():
    query = """
        SELECT s.sale_id, p.customer_email
        FROM `winter-sensor-474220-u4.datapulse_marts.fct_sales` AS s
        JOIN `winter-sensor-474220-u4.datapulse_marts.fct_payments` AS p
            ON s.order_id = p.order_id
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_unapproved_join_condition_column():
    query = """
        SELECT s.sale_id
        FROM `winter-sensor-474220-u4.datapulse_marts.fct_sales` AS s
        JOIN `winter-sensor-474220-u4.datapulse_marts.fct_inventory` AS i
            ON s.order_id = i.payment_method
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_unapproved_column_in_order_by():
    query = """
        SELECT sale_id
        FROM `winter-sensor-474220-u4.datapulse_marts.fct_sales`
        ORDER BY payment_method
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_unapproved_column_in_group_by():
    query = """
        SELECT COUNT(*) AS total
        FROM `winter-sensor-474220-u4.datapulse_marts.fct_sales`
        GROUP BY payment_method
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)

def test_reject_unapproved_column_in_having():
    query = """
        SELECT SUM(net_amount) AS revenue
        FROM `winter-sensor-474220-u4.datapulse_marts.fct_sales`
        HAVING payment_method = 'UPI'
    """

    with pytest.raises(SQLValidationError):
        validate_sql(query)