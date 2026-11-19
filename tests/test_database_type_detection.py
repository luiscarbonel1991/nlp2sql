"""The database type comes from the URL scheme, the same way in every entry point.

Measured on 0.2.0rc21: connect("mysql://...") built a PostgreSQL repository, because
connect() treated every URL that did not mention Redshift as PostgreSQL.
"""

from collections.abc import Iterator

import click
import pytest
from click.testing import CliRunner

import nlp2sql
from nlp2sql import DatabaseType, ProviderConfig
from nlp2sql.adapters.postgres_repository import PostgreSQLRepository
from nlp2sql.adapters.redshift_adapter import RedshiftRepository
from nlp2sql.cli import cli, validate_database_url
from nlp2sql.factories import RepositoryFactory

OPENAI = ProviderConfig(provider="openai", api_key="sk-test")


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("mysql://user:pass@localhost:3306/shop", DatabaseType.MYSQL),
        ("mysql+pymysql://user:pass@localhost:3306/shop", DatabaseType.MYSQL),
        ("mariadb://user:pass@localhost:3306/shop", DatabaseType.MYSQL),
        ("MariaDB://user:pass@localhost/shop", DatabaseType.MYSQL),
        ("postgresql://user:pass@cluster.abc.us-east-1.redshift.amazonaws.com:5439/dev", DatabaseType.REDSHIFT),
        ("postgres://user:pass@wg.123.us-east-1.redshift-serverless.amazonaws.com:5439/dev", DatabaseType.REDSHIFT),
        # "redshift" outside the host says nothing about the server
        ("postgresql://redshift_reader:redshift@localhost:5432/redshift_copy", DatabaseType.POSTGRES),
        ("postgresql://user:pass@localhost:5432/db", DatabaseType.POSTGRES),
    ],
)
def test_detects_the_type_from_scheme_and_host(url: str, expected: DatabaseType) -> None:
    assert RepositoryFactory.detect_database_type(url) is expected


@pytest.fixture
def sqlite_repository_registered() -> Iterator[None]:
    RepositoryFactory.register(DatabaseType.SQLITE, PostgreSQLRepository)
    yield
    RepositoryFactory.unregister(DatabaseType.SQLITE)


def test_supported_schemes_are_those_with_a_repository() -> None:
    schemes = RepositoryFactory.supported_url_schemes()

    assert {"postgresql", "postgres", "redshift", "mysql", "mysql+pymysql", "mariadb"} <= set(schemes)
    assert "oracle" not in schemes
    assert "sqlite" not in schemes


@pytest.mark.usefixtures("sqlite_repository_registered")
def test_registering_a_repository_makes_its_schemes_supported() -> None:
    assert "sqlite" in RepositoryFactory.supported_url_schemes()
    assert RepositoryFactory.unsupported_url_reason("sqlite:///path/to/shop.db") is None


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        ("oracle://user:s3cret@localhost:1521/db", "unsupported scheme 'oracle'"),
        ("user:s3cret@localhost/db", "missing scheme://"),
        ("POSTGRESQL://user:s3cret@localhost/db", None),
    ],
)
def test_unsupported_url_reason_never_shows_the_url(url: str, reason: str | None) -> None:
    assert RepositoryFactory.unsupported_url_reason(url) == reason


def test_create_query_service_does_not_build_postgres_for_another_database() -> None:
    with pytest.raises(NotImplementedError, match="'oracle' not supported"):
        nlp2sql.create_query_service("oracle://user:pass@localhost:1521/db", provider_config=OPENAI)


@pytest.mark.asyncio
async def test_connect_does_not_build_postgres_for_another_database() -> None:
    with pytest.raises(NotImplementedError, match="'oracle' not supported"):
        await nlp2sql.connect("oracle://user:pass@localhost:1521/db", provider=OPENAI)


def test_create_query_service_detects_redshift_without_a_database_type() -> None:
    service = nlp2sql.create_query_service("redshift://user:pass@cluster.example.com:5439/dev", provider_config=OPENAI)

    assert isinstance(service.schema_repository, RedshiftRepository)


def test_redshift_reads_a_postgres_url() -> None:
    repository = RedshiftRepository("postgres://reader:pass@cluster.abc.redshift.amazonaws.com:5439/dev")

    assert repository._connection_params["user"] == "reader"
    assert repository._connection_params["host"] == "cluster.abc.redshift.amazonaws.com"
    assert repository._connection_params["database"] == "dev"


def test_cli_rejects_a_database_without_a_repository_and_hides_the_url() -> None:
    result = CliRunner().invoke(cli, ["inspect", "--database-url", "oracle://user:s3cret@localhost:1521/db"])

    assert result.exit_code == 1
    assert "unsupported scheme 'oracle'" in result.output
    assert "s3cret" not in result.output


def test_cli_accepts_a_scheme_in_any_case() -> None:
    url = "POSTGRESQL://user:pass@localhost:5432/db"

    assert validate_database_url(click.Context(cli), None, url) == url
