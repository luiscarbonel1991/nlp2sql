"""`nlp2sql setup` must complete the database step (it called the nonexistent click.choice)."""

import pytest
from click.testing import CliRunner

from nlp2sql.cli import cli

# Answers: skip the API key test, configure a database, then the database prompts
SETUP_ANSWERS = "n\ny\n{db_type}\ndb.example.com\n\nanalyst\nsecret\nwarehouse\n"


@pytest.mark.parametrize(
    ("db_type", "expected_url"),
    [
        ("postgresql", "postgresql://analyst:secret@db.example.com:5432/warehouse"),
        ("redshift", "redshift://analyst:secret@db.example.com:5439/warehouse"),
    ],
)
def test_setup_builds_a_connection_string(monkeypatch, db_type, expected_url):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")

    result = CliRunner().invoke(cli, ["setup"], input=SETUP_ANSWERS.format(db_type=db_type))

    assert result.exit_code == 0, result.output
    assert f'export DATABASE_URL="{expected_url}"' in result.output


def test_setup_rejects_databases_without_an_adapter(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")

    result = CliRunner().invoke(cli, ["setup"], input="n\ny\nmysql\npostgresql\n\n\nu\np\nd\n")

    assert result.exit_code == 0, result.output
    assert "mysql" not in result.output.split("Connection string:")[-1]
    assert "postgresql://u:p@localhost:5432/d" in result.output
