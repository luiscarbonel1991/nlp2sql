"""Tests for core/database_prompts module."""

from nlp2sql.core.database_prompts import DATABASE_SQL_HINTS, get_database_hint


class TestGetDatabaseHint:
    """Tests for get_database_hint function."""

    def test_returns_hint_for_postgres(self):
        hint = get_database_hint("postgres")
        assert hint
        assert "PostgreSQL" in hint

    def test_returns_hint_for_mysql(self):
        hint = get_database_hint("mysql")
        assert hint
        assert "MySQL" in hint

    def test_returns_hint_for_sqlite(self):
        hint = get_database_hint("sqlite")
        assert hint
        assert "SQLite" in hint

    def test_returns_hint_for_mssql(self):
        hint = get_database_hint("mssql")
        assert hint
        assert "SQL Server" in hint or "T-SQL" in hint

    def test_returns_hint_for_oracle(self):
        hint = get_database_hint("oracle")
        assert hint
        assert "Oracle" in hint

    def test_returns_hint_for_redshift(self):
        hint = get_database_hint("redshift")
        assert hint
        assert "Redshift" in hint

    def test_redshift_contains_critical_rules(self):
        hint = get_database_hint("redshift")
        assert "DATE_TRUNC" in hint
        assert "DATEADD" in hint
        assert "TRUNC" in hint
        assert "LISTAGG" in hint
        assert "DISTINCT ON" in hint
        assert "generate_series" in hint

    def test_unknown_type_returns_empty_string(self):
        assert get_database_hint("unknown_db") == ""
        assert get_database_hint("") == ""

    def test_case_insensitive(self):
        assert get_database_hint("POSTGRES") == get_database_hint("postgres")
        assert get_database_hint("Redshift") == get_database_hint("redshift")
        assert get_database_hint("MySQL") == get_database_hint("mysql")

    def test_all_database_types_have_hints(self):
        expected_types = {"postgres", "mysql", "sqlite", "mssql", "oracle", "redshift"}
        assert set(DATABASE_SQL_HINTS.keys()) == expected_types

    def test_all_hints_are_non_empty_strings(self):
        for db_type, hint in DATABASE_SQL_HINTS.items():
            assert isinstance(hint, str), f"{db_type} hint is not a string"
            assert len(hint) > 20, f"{db_type} hint is too short"
