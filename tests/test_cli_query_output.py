"""What `nlp2sql query` prints about the validation of the generated SQL."""

from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from nlp2sql.cli import cli


def _query_output(validation: dict) -> str:
    fake_service = MagicMock()
    fake_service.generate_sql = AsyncMock(
        return_value={
            "sql": "SELECT total FROM users",
            "confidence": 0.9,
            "tokens_used": 42,
            "validation": validation,
            "metadata": {},
        }
    )
    with patch("nlp2sql.cli.create_and_initialize_service", new_callable=AsyncMock, return_value=fake_service):
        result = CliRunner().invoke(
            cli,
            [
                "query",
                "--database-url",
                "postgresql://user:pass@localhost:5432/db",
                "--question",
                "What is the total per user?",
                "--api-key",
                "test-key",
            ],
        )
    assert result.exit_code == 0, result.output
    return result.output


def test_a_valid_query_passes() -> None:
    output = _query_output({"is_valid": True, "errors": [], "warnings": []})

    assert "[OK] SQL validation: Passed" in output


def test_an_invalid_query_shows_its_errors() -> None:
    output = _query_output({"is_valid": False, "errors": ["Unknown column: users.total"], "warnings": []})

    assert "[OK] SQL validation: Passed" not in output
    assert "Unknown column: users.total" in output
