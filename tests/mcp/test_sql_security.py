"""Tests for SQL security validation in repositories."""

from nlp2sql.adapters.postgres_repository import apply_row_limit, is_safe_query


class TestIsSafeQuery:
    """Test SQL safety validation."""

    def test_allows_simple_select(self):
        """Basic SELECT queries should be allowed."""
        is_safe, error = is_safe_query("SELECT * FROM users")
        assert is_safe is True
        assert error == ""

    def test_allows_select_with_where(self):
        """SELECT with WHERE clause should be allowed."""
        is_safe, error = is_safe_query("SELECT id, name FROM users WHERE active = true")
        assert is_safe is True

    def test_allows_select_with_join(self):
        """SELECT with JOIN should be allowed."""
        sql = """
        SELECT u.name, o.total
        FROM users u
        JOIN orders o ON u.id = o.user_id
        WHERE o.status = 'completed'
        """
        is_safe, error = is_safe_query(sql)
        assert is_safe is True

    def test_allows_with_cte(self):
        """WITH (CTE) queries should be allowed."""
        sql = """
        WITH active_users AS (
            SELECT * FROM users WHERE active = true
        )
        SELECT * FROM active_users
        """
        is_safe, error = is_safe_query(sql)
        assert is_safe is True

    def test_allows_explain(self):
        """EXPLAIN queries should be allowed."""
        is_safe, error = is_safe_query("EXPLAIN SELECT * FROM users")
        assert is_safe is True

    def test_allows_explain_analyze(self):
        """EXPLAIN ANALYZE should be allowed."""
        is_safe, error = is_safe_query("EXPLAIN ANALYZE SELECT * FROM users")
        assert is_safe is True

    def test_blocks_insert(self):
        """INSERT queries should be blocked."""
        is_safe, error = is_safe_query("INSERT INTO users (name) VALUES ('test')")
        assert is_safe is False
        assert "prohibited" in error.lower() or "SELECT" in error

    def test_blocks_update(self):
        """UPDATE queries should be blocked."""
        is_safe, error = is_safe_query("UPDATE users SET name = 'test' WHERE id = 1")
        assert is_safe is False

    def test_blocks_delete(self):
        """DELETE queries should be blocked."""
        is_safe, error = is_safe_query("DELETE FROM users WHERE id = 1")
        assert is_safe is False

    def test_blocks_drop_table(self):
        """DROP TABLE should be blocked."""
        is_safe, error = is_safe_query("DROP TABLE users")
        assert is_safe is False

    def test_blocks_drop_database(self):
        """DROP DATABASE should be blocked."""
        is_safe, error = is_safe_query("DROP DATABASE mydb")
        assert is_safe is False

    def test_blocks_truncate(self):
        """TRUNCATE should be blocked."""
        is_safe, error = is_safe_query("TRUNCATE TABLE users")
        assert is_safe is False

    def test_blocks_alter_table(self):
        """ALTER TABLE should be blocked."""
        is_safe, error = is_safe_query("ALTER TABLE users ADD COLUMN email VARCHAR(255)")
        assert is_safe is False

    def test_blocks_create_table(self):
        """CREATE TABLE should be blocked."""
        is_safe, error = is_safe_query("CREATE TABLE test (id INT)")
        assert is_safe is False

    def test_blocks_grant(self):
        """GRANT should be blocked."""
        is_safe, error = is_safe_query("GRANT SELECT ON users TO public")
        assert is_safe is False

    def test_blocks_revoke(self):
        """REVOKE should be blocked."""
        is_safe, error = is_safe_query("REVOKE SELECT ON users FROM public")
        assert is_safe is False

    def test_blocks_multiple_statements(self):
        """Multiple statements (SQL injection) should be blocked."""
        # This query has multiple SELECT statements (no dangerous keywords)
        is_safe, error = is_safe_query("SELECT * FROM users; SELECT * FROM orders;")
        assert is_safe is False
        assert "multiple" in error.lower()

    def test_allows_semicolon_in_string(self):
        """Semicolons inside string literals should be allowed."""
        is_safe, error = is_safe_query("SELECT * FROM users WHERE name = 'test; value'")
        assert is_safe is True

    def test_blocks_hidden_drop_after_select(self):
        """Hidden DROP after valid SELECT should be blocked."""
        is_safe, error = is_safe_query("SELECT * FROM users WHERE id = 1; DROP TABLE users")
        assert is_safe is False

    def test_blocks_insert_disguised_in_subquery(self):
        """INSERT in a comment or subquery context should still be blocked."""
        # This tests that we check the whole query, not just the prefix
        is_safe, error = is_safe_query("SELECT * FROM (INSERT INTO users VALUES (1)) x")
        assert is_safe is False

    def test_case_insensitive_blocking(self):
        """Dangerous keywords should be blocked regardless of case."""
        is_safe, error = is_safe_query("delete FROM users")
        assert is_safe is False

        is_safe, error = is_safe_query("DeLeTe FROM users")
        assert is_safe is False

    def test_blocks_copy(self):
        """COPY command should be blocked."""
        is_safe, error = is_safe_query("COPY users TO '/tmp/users.csv'")
        assert is_safe is False

    def test_allows_aggregate_functions(self):
        """Aggregate functions should be allowed."""
        is_safe, error = is_safe_query("SELECT COUNT(*), AVG(amount) FROM orders")
        assert is_safe is True

    def test_allows_window_functions(self):
        """Window functions should be allowed."""
        sql = "SELECT name, ROW_NUMBER() OVER (ORDER BY created_at) FROM users"
        is_safe, error = is_safe_query(sql)
        assert is_safe is True


class TestApplyRowLimit:
    """Test row limit application."""

    def test_adds_limit_to_simple_query(self):
        """Should add LIMIT to query without one."""
        sql = "SELECT * FROM users"
        result = apply_row_limit(sql, 100)
        assert "LIMIT 100" in result

    def test_preserves_existing_limit(self):
        """Should not modify query that already has LIMIT."""
        sql = "SELECT * FROM users LIMIT 50"
        result = apply_row_limit(sql, 100)
        assert result == sql
        assert "LIMIT 100" not in result

    def test_respects_max_limit(self):
        """Should cap limit at MAX_QUERY_ROWS (1000)."""
        sql = "SELECT * FROM users"
        result = apply_row_limit(sql, 5000)
        assert "LIMIT 1000" in result

    def test_removes_trailing_semicolon(self):
        """Should handle trailing semicolon."""
        sql = "SELECT * FROM users;"
        result = apply_row_limit(sql, 100)
        assert result == "SELECT * FROM users LIMIT 100"

    def test_handles_complex_query(self):
        """Should work with complex queries."""
        sql = """
        SELECT u.name, COUNT(o.id) as order_count
        FROM users u
        LEFT JOIN orders o ON u.id = o.user_id
        GROUP BY u.name
        ORDER BY order_count DESC
        """
        result = apply_row_limit(sql, 50)
        assert "LIMIT 50" in result

    def test_limit_in_string_literal_does_not_bypass(self):
        """LIMIT inside string literal should not bypass the limit."""
        # This is a security test - 'LIMIT' in a string should NOT prevent adding LIMIT
        sql = "SELECT * FROM messages WHERE text LIKE '%LIMIT%'"
        result = apply_row_limit(sql, 100)
        assert "LIMIT 100" in result

    def test_limit_in_single_quoted_string_does_not_bypass(self):
        """LIMIT inside single-quoted string should not bypass."""
        sql = "SELECT * FROM logs WHERE message = 'LIMIT exceeded'"
        result = apply_row_limit(sql, 100)
        assert "LIMIT 100" in result

    def test_limit_in_double_quoted_identifier_does_not_bypass(self):
        """LIMIT inside double-quoted identifier should not bypass."""
        sql = 'SELECT * FROM "LIMIT_table" WHERE id > 0'
        result = apply_row_limit(sql, 100)
        assert "LIMIT 100" in result

    def test_real_limit_clause_is_preserved(self):
        """Real LIMIT clause outside strings should be preserved."""
        sql = "SELECT * FROM messages WHERE text LIKE '%test%' LIMIT 25"
        result = apply_row_limit(sql, 100)
        assert result == sql
        assert "LIMIT 100" not in result

    def test_case_insensitive_limit_detection(self):
        """LIMIT detection should be case-insensitive."""
        sql = "SELECT * FROM users limit 50"
        result = apply_row_limit(sql, 100)
        assert result == sql

        sql2 = "SELECT * FROM users LiMiT 50"
        result2 = apply_row_limit(sql2, 100)
        assert result2 == sql2

    def test_escaped_quotes_in_string_with_limit(self):
        """SQL escaped quotes (doubled) should be handled correctly."""
        # String with escaped quote containing LIMIT should still detect real LIMIT
        sql = "SELECT * FROM users WHERE name = 'O''Reilly' LIMIT 50"
        result = apply_row_limit(sql, 100)
        assert result == sql  # Should not add another LIMIT

    def test_escaped_quotes_without_limit(self):
        """Escaped quotes should not prevent LIMIT from being added."""
        sql = "SELECT * FROM users WHERE name = 'O''Reilly'"
        result = apply_row_limit(sql, 100)
        assert "LIMIT 100" in result

    def test_multiple_escaped_quotes_in_string(self):
        """Multiple escaped quotes in a string should be handled."""
        sql = "SELECT * FROM logs WHERE msg = 'User said: ''Hello'' to me'"
        result = apply_row_limit(sql, 100)
        assert "LIMIT 100" in result

    def test_escaped_quotes_with_limit_keyword_inside(self):
        """LIMIT inside escaped string should not bypass actual LIMIT."""
        sql = "SELECT * FROM msgs WHERE text = 'It''s about LIMIT'"
        result = apply_row_limit(sql, 100)
        assert "LIMIT 100" in result


class TestIsSafeQueryEscapedQuotes:
    """Test SQL safety validation with escaped quotes."""

    def test_escaped_quotes_with_semicolon_inside(self):
        """Semicolon inside escaped string should be allowed."""
        sql = "SELECT * FROM users WHERE name = 'O''Reilly; test'"
        is_safe, error = is_safe_query(sql)
        assert is_safe is True

    def test_escaped_quotes_safe_query(self):
        """Basic query with escaped quotes should be safe."""
        sql = "SELECT * FROM users WHERE name = 'It''s a test'"
        is_safe, error = is_safe_query(sql)
        assert is_safe is True

    def test_real_injection_not_hidden_by_escaped_quotes(self):
        """Real SQL injection should still be detected after escaped quotes."""
        # Multiple SELECT statements (no dangerous keywords, tests semicolon detection)
        sql = "SELECT * FROM users WHERE name = 'test'; SELECT * FROM admins"
        is_safe, error = is_safe_query(sql)
        assert is_safe is False
        assert "multiple" in error.lower()

    def test_dangerous_keyword_after_escaped_quotes(self):
        """Dangerous keywords after escaped quotes should be detected."""
        sql = "SELECT * FROM users WHERE name = 'test'; DELETE FROM users"
        is_safe, error = is_safe_query(sql)
        assert is_safe is False
        assert "prohibited" in error.lower()
