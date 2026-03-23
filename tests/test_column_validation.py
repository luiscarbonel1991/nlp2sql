"""Tests for column validation in QueryGenerationService."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from nlp2sql.adapters.regex_query_validator import RegexQueryValidator
from nlp2sql.services.query_service import QueryGenerationService


def _make_table(name: str, columns: list[str]):
    """Create a mock TableInfo-like object."""
    table = MagicMock()
    table.name = name
    table.columns = [{"name": c} for c in columns]
    return table


def _make_service(tables: list) -> QueryGenerationService:
    """Create a service with mocked schema manager and regex query validator."""
    service = object.__new__(QueryGenerationService)
    service.schema_manager = MagicMock()
    service.schema_manager.get_tables = AsyncMock(return_value=tables)
    service.query_validator = RegexQueryValidator()
    return service


TABLES = [
    _make_table(
        "orders",
        [
            "order_id",
            "order_date",
            "customer_id",
            "total_amount",
            "shipping_cost",
            "status",
            "store_name",
        ],
    ),
    _make_table(
        "customers",
        [
            "customer_id",
            "name",
            "email",
            "country",
            "created_at",
        ],
    ),
    _make_table(
        "products",
        [
            "product_id",
            "title",
            "price",
            "category",
            "revenue",
        ],
    ),
]


class TestValidateColumnNames:
    """Tests for _validate_column_names method."""

    @pytest.fixture
    def service(self):
        return _make_service(TABLES)

    @pytest.mark.asyncio
    async def test_valid_columns_no_errors(self, service):
        sql = "SELECT SUM(total_amount) FROM orders WHERE order_date >= '2025-01-01'"
        errors = await service._validate_column_names(sql)
        assert errors == []

    @pytest.mark.asyncio
    async def test_invalid_column_with_close_match(self, service):
        sql = "SELECT SUM(amount) FROM orders"
        errors = await service._validate_column_names(sql)
        assert len(errors) == 1
        assert "amount" in errors[0]
        assert "total_amount" in errors[0]

    @pytest.mark.asyncio
    async def test_column_from_wrong_table_with_close_match(self, service):
        """'cost' is a substring of 'shipping_cost' in orders, so it gets flagged."""
        sql = "SELECT SUM(cost) FROM orders"
        errors = await service._validate_column_names(sql)
        assert len(errors) >= 1
        assert "cost" in errors[0]
        assert "shipping_cost" in errors[0]

    @pytest.mark.asyncio
    async def test_alias_excluded(self, service):
        sql = "SELECT SUM(total_amount) AS total_revenue FROM orders"
        errors = await service._validate_column_names(sql)
        assert errors == []

    @pytest.mark.asyncio
    async def test_cte_names_excluded(self, service):
        sql = """
        WITH monthly_orders AS (
            SELECT order_date, SUM(total_amount) AS total FROM orders GROUP BY order_date
        )
        SELECT * FROM monthly_orders
        """
        errors = await service._validate_column_names(sql)
        assert not any("monthly_orders" in e for e in errors)

    @pytest.mark.asyncio
    async def test_table_alias_excluded(self, service):
        sql = "SELECT o.total_amount FROM orders o WHERE o.order_date >= '2025-01-01'"
        errors = await service._validate_column_names(sql)
        assert errors == []

    @pytest.mark.asyncio
    async def test_short_tokens_excluded(self, service):
        sql = """
        WITH o AS (SELECT order_id, total_amount FROM orders)
        SELECT o.order_id FROM o
        """
        errors = await service._validate_column_names(sql)
        assert not any("'o'" in e for e in errors)

    @pytest.mark.asyncio
    async def test_string_literals_excluded(self, service):
        sql = "SELECT * FROM orders WHERE status = 'completed'"
        errors = await service._validate_column_names(sql)
        assert not any("completed" in e.lower() for e in errors)

    @pytest.mark.asyncio
    async def test_sql_keywords_excluded(self, service):
        sql = "SELECT SUM(total_amount) FROM orders GROUP BY order_date ORDER BY order_date DESC"
        errors = await service._validate_column_names(sql)
        assert errors == []

    @pytest.mark.asyncio
    async def test_per_table_validation(self, service):
        """store_name is only in orders, not in customers."""
        sql = "SELECT store_name FROM customers"
        errors = await service._validate_column_names(sql)
        assert len(errors) >= 1
        assert "customers" in errors[0]

    @pytest.mark.asyncio
    async def test_no_tables_referenced_returns_empty(self, service):
        sql = "SELECT 1"
        errors = await service._validate_column_names(sql)
        assert errors == []

    @pytest.mark.asyncio
    async def test_schema_unavailable_returns_empty(self):
        service = object.__new__(QueryGenerationService)
        service.schema_manager = MagicMock()
        service.schema_manager.get_tables = AsyncMock(side_effect=Exception("no cache"))
        service.query_validator = RegexQueryValidator()
        errors = await service._validate_column_names("SELECT * FROM foo")
        assert errors == []

    @pytest.mark.asyncio
    async def test_multiple_ctes_excluded(self, service):
        sql = """
        WITH jan AS (SELECT store_name, SUM(total_amount) AS total FROM orders GROUP BY store_name),
        feb AS (SELECT store_name, SUM(total_amount) AS total FROM orders GROUP BY store_name)
        SELECT jan.store_name, feb.total - jan.total AS growth
        FROM jan JOIN feb ON jan.store_name = feb.store_name
        """
        errors = await service._validate_column_names(sql)
        assert not any("jan" in e or "feb" in e for e in errors)
        assert not any("growth" in e for e in errors)

    @pytest.mark.asyncio
    async def test_join_validates_both_tables(self, service):
        sql = "SELECT o.total_amount, c.name FROM orders o JOIN customers c ON o.customer_id = c.customer_id"
        errors = await service._validate_column_names(sql)
        assert errors == []

    @pytest.mark.asyncio
    async def test_schema_prefix_stripped(self, service):
        sql = "SELECT total_amount FROM public.orders WHERE order_date >= '2025-01-01'"
        errors = await service._validate_column_names(sql)
        assert errors == []
