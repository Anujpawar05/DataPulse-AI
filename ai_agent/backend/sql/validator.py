
import sqlglot
from sqlglot import exp
from sqlglot.optimizer.scope import Scope, traverse_scope

PROJECT_ID = "winter-sensor-474220-u4"
DATASET_ID = "datapulse_marts"

ALLOWED_TABLES = {
    "dim_customers",
    "dim_products",
    "fct_category_sales",
    "fct_daily_sales",
    "fct_inventory",
    "fct_payments",
    "fct_sales",
}

ALLOWED_COLUMNS = {
    "dim_customers": {
        "customer_id",
        "customer_name",
        "city",
        "state",
        "total_orders",
        "completed_orders",
        "cancelled_orders",
        "total_revenue",
        "total_profit",
        "average_order_line_value",
        "first_order_date",
        "latest_order_date",
    },
    "dim_products": {
        "product_id",
        "product_name",
        "product_category",
        "price",
        "cost",
        "is_active",
        "created_at",
    },
    "fct_category_sales": {
        "product_category",
        "total_orders",
        "total_sales",
        "total_products",
        "units_sold",
        "gross_revenue",
        "net_revenue",
        "total_cost",
        "total_profit",
        "profit_margin_percentage",
    },
    "fct_daily_sales": {
        "sales_date",
        "total_orders",
        "total_sales",
        "units_sold",
        "gross_revenue",
        "net_revenue",
        "total_cost",
        "total_profit",
        "profit_margin_percentage",
    },
    "fct_inventory": {
        "product_id",
        "product_name",
        "product_category",
        "warehouse",
        "stock_quantity",
        "reorder_level",
        "stock_difference",
        "inventory_status",
        "requires_restock",
    },
    "fct_payments": {
        "payment_id",
        "order_id",
        "customer_id",
        "order_date",
        "order_status",
        "payment_method",
        "payment_amount",
        "payment_status",
        "payment_date",
        "successful_payment_amount",
        "is_successful_payment",
    },
    "fct_sales": {
        "sale_id",
        "order_id",
        "customer_id",
        "customer_name",
        "city",
        "state",
        "order_date",
        "order_status",
        "product_id",
        "product_name",
        "product_category",
        "quantity",
        "unit_price",
        "unit_cost",
        "discount_amount",
        "gross_amount",
        "net_amount",
        "total_cost",
        "profit",
        "profit_margin_percentage",
    },
}

BLOCKED_COLUMNS = {
    "customer_email",
}

MAX_ROWS = 1000


class SQLValidationError(ValueError):
    """Raised when generated SQL violates security rules."""



def validate_column_references(tree):
    for scope in traverse_scope(tree):
        source_columns = {}

        # Build column maps for tables, CTEs, and subqueries.
        for alias, (_, source) in scope.selected_sources.items():
            alias = alias.lower()

            if isinstance(source, exp.Table):
                table_name = source.name.lower()
                columns = ALLOWED_COLUMNS.get(table_name)

                if columns is None:
                    raise SQLValidationError(
                        f"Table '{table_name}' has no approved column schema."
                    )

                source_columns[alias] = columns

            elif hasattr(source, "expression"):
                output_columns = {
                    name.lower()
                    for name in source.expression.named_selects
                    if name != "*"
                }
                source_columns[alias] = output_columns

        # Collect SELECT aliases.
        select_aliases = {
            projection.alias.lower()
            for projection in scope.expression.expressions
            if isinstance(projection, exp.Expression)
            and projection.alias
        }

        # Include columns from QUALIFY explicitly.
        columns_to_validate = list(scope.columns)

      # Explicitly validate columns in QUALIFY and HAVING.
        for clause_name in ("qualify", "having"):
            clause = scope.expression.args.get(clause_name)

            if clause is not None:
                columns_to_validate.extend(
                    clause.find_all(exp.Column)
            )

        for column in columns_to_validate:
            column_name = column.name.lower()

            if column_name in BLOCKED_COLUMNS:
                raise SQLValidationError(
                    f"Access to column '{column.name}' is prohibited."
                )

            if column.is_star:
                continue

            # Handle qualified column references.
            if column.table:
                table_alias = column.table.lower()

                if table_alias not in source_columns:
                    raise SQLValidationError(
                        f"Unknown or unapproved table alias '{column.table}'."
                    )

                if column_name not in source_columns[table_alias]:
                    raise SQLValidationError(
                        f"Column '{column.name}' is not approved "
                        f"for source '{column.table}'."
                    )

            # Handle unqualified column references.
            else:
                # Allow SELECT aliases in ORDER BY, GROUP BY, and HAVING.
                if (
                    column_name in select_aliases
                    and (
                        column.find_ancestor(exp.Order) is not None
                        or column.find_ancestor(exp.Group) is not None
                        or column.find_ancestor(exp.Having) is not None
                    )
                ):
                    continue

                matching_sources = [
                    alias
                    for alias, columns in source_columns.items()
                    if column_name in columns
                ]

                if not matching_sources:
                    raise SQLValidationError(
                        f"Column '{column.name}' is not approved."
                    )

                if len(matching_sources) > 1:
                    raise SQLValidationError(
                        f"Ambiguous column '{column.name}'. "
                        "Use an explicit table alias."
                    )


def validate_sql(query: str) -> str:
    if not query or not query.strip():
        raise SQLValidationError("SQL query cannot be empty.")

    # Parse BigQuery SQL.
    try:
        statements = sqlglot.parse(query, read="bigquery")
    except sqlglot.errors.ParseError as exc:
        raise SQLValidationError(
            "Invalid BigQuery SQL syntax."
        ) from exc

    # Allow exactly one SQL statement.
    if len(statements) != 1 or statements[0] is None:
        raise SQLValidationError(
            "Only one SQL statement is allowed."
        )

    tree = statements[0]

    # Allow SELECT and UNION-based SELECT queries only.
    if not isinstance(tree, (exp.Select, exp.Union)):
        raise SQLValidationError(
            "Only SELECT queries are allowed."
        )

    # Reject restricted operations and commands.
    forbidden_nodes = (
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Drop,
        exp.Create,
        exp.Alter,
        exp.TruncateTable,
        exp.Command,
    )

    for node_type in forbidden_nodes:
        if tree.find(node_type):
            raise SQLValidationError(
                "Query contains a prohibited SQL operation."
            )

   # Identify actual CTE references using SQLGlot scope resolution.
    cte_reference_ids = set()

    for scope in traverse_scope(tree):
        for node, source in scope.selected_sources.values():
            if isinstance(node, exp.Table) and isinstance(source, Scope):
                cte_reference_ids.add(id(node))
    # Reject unsupported BigQuery ML operations.
    if tree.find(exp.Predict):
        raise SQLValidationError(
            "BigQuery ML operations are prohibited."
        )

    # Collect and validate physical table references.
    tables = list(tree.find_all(exp.Table))

    if not tables:
        raise SQLValidationError(
            "Query must reference an approved table."
        )

    for table in tables:

        # Reject table-valued functions and external sources.
        if not isinstance(table.this, exp.Identifier):
            raise SQLValidationError(
                "Table-valued functions and external data sources "
                "are prohibited."
            )

        # Reject TABLESAMPLE.
        if table.args.get("sample") is not None:
            raise SQLValidationError(
                "TABLESAMPLE is prohibited."
            )

        # Reject historical table snapshots.
        if table.args.get("version") is not None:
            raise SQLValidationError(
                "Historical table access is prohibited."
            )

        table_name = table.name.lower()

        # Allow unqualified references to declared CTEs.
        # Allow only references SQLGlot resolves as actual CTE sources.
        if id(table) in cte_reference_ids:
            continue

        # Enforce the approved BigQuery project.
        if table.catalog != PROJECT_ID:
            raise SQLValidationError(
                "Tables must use the approved BigQuery project."
            )

        # Enforce the approved dataset.
        if table.db != DATASET_ID:
            raise SQLValidationError(
                "Tables must use the approved marts dataset."
            )

        # Enforce the approved table allowlist.
        if table_name not in ALLOWED_TABLES:
            raise SQLValidationError(
                f"Table '{table.name}' is not approved."
            )
    validate_column_references(tree)
    # Block explicitly restricted columns.
    for column in tree.find_all(exp.Column):

        if column.name.lower() in BLOCKED_COLUMNS:
            raise SQLValidationError(
                f"Access to column '{column.name}' is prohibited."
            )

    # Prevent wildcard access in all SELECT statements.
    for select in tree.find_all(exp.Select):
        for projection in select.expressions:
            if (
                isinstance(projection, exp.Star)
                or (
                    isinstance(projection, exp.Column)
                    and projection.is_star
                )
            ):
                raise SQLValidationError(
                    "Wildcard selection is prohibited. "
                    "Specify the required columns explicitly."
                )

    # Validate LIMIT clauses in the main query and nested SELECTs.
    query_nodes = list(tree.find_all(exp.Select))

    if isinstance(tree, exp.Select):
        query_nodes.insert(0, tree)

    for node in query_nodes:
        limit = node.args.get("limit")

        if limit is None:
            continue

        limit_expression = limit.expression

        if not isinstance(limit_expression, exp.Literal):
            raise SQLValidationError(
                "LIMIT must be a numeric literal."
            )

        if not limit_expression.is_int:
            raise SQLValidationError(
                "LIMIT must be an integer."
            )

        limit_value = int(limit_expression.this)

        if limit_value > MAX_ROWS:
            raise SQLValidationError(
                f"Maximum allowed LIMIT is {MAX_ROWS}."
            )

    # Apply the default row limit to the outer query.
    if tree.args.get("limit") is None:
        tree = tree.limit(MAX_ROWS)

    return tree.sql(dialect="bigquery")
