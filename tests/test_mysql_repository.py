"""The MySQL repository without a server: what it reads from the URL and asks of the driver.

The driver is a fake that records the arguments of connect() and the statements, so these
run where PyMySQL is not installed. tests/test_mysql_repository_against_servers.py runs
the same repository against MySQL and MariaDB.
"""

import sys
from types import SimpleNamespace
from typing import Any

import pytest

from nlp2sql.adapters import mysql_repository
from nlp2sql.adapters.mysql_repository import MySQLRepository, parse_mysql_url
from nlp2sql.core.entities import DatabaseType
from nlp2sql.exceptions import ConfigurationException, SchemaException, SecurityException
from nlp2sql.factories import RepositoryFactory

URL = "mysql://reader:s3cret@db.example.com/shop"


class FakeCursor:
    def __init__(self, driver: "FakeDriver") -> None:
        self.driver = driver
        self.description = (("n",),)
        self._rows: list[dict[str, Any]] = []

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def execute(self, query: str, args: object = None) -> None:
        self.driver.statements.append(query)
        self._rows = [{"version": self.driver.version}] if "VERSION()" in query else [{"n": 1}]

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class FakeDriver:
    """Stands in for the pymysql module."""

    def __init__(self, version: str = "8.4.13") -> None:
        self.version = version
        self.connections: list[dict[str, Any]] = []
        self.statements: list[str] = []
        self.cursors = SimpleNamespace(DictCursor="DictCursor")

    def connect(self, **kwargs: Any) -> SimpleNamespace:  # noqa: ANN401 - mirrors pymysql.connect
        self.connections.append(kwargs)
        return SimpleNamespace(cursor=lambda: FakeCursor(self), close=lambda: None)


@pytest.fixture
def driver(monkeypatch: pytest.MonkeyPatch) -> FakeDriver:
    fake = FakeDriver()
    monkeypatch.setattr(mysql_repository, "_load_driver", lambda: fake)
    return fake


@pytest.mark.parametrize("scheme", ["mysql", "mysql+pymysql", "mariadb", "MySQL"])
def test_reads_host_user_and_database_from_every_mysql_scheme(scheme: str) -> None:
    params = parse_mysql_url(f"{scheme}://reader:p%40ss%2Fword@db.example.com:3307/shop")

    assert params == {
        "host": "db.example.com",
        "port": 3307,
        "user": "reader",
        "password": "p@ss/word",
        "database": "shop",
        "charset": "utf8mb4",
    }


def test_port_defaults_to_3306() -> None:
    assert parse_mysql_url("mysql://reader@db.example.com/shop")["port"] == 3306  # noqa: PLR2004


def test_tls_and_timeout_parameters_reach_the_driver_with_their_types() -> None:
    params = parse_mysql_url(f"{URL}?ssl_ca=/etc/ssl/ca.pem&ssl_verify_identity=true&connect_timeout=5")

    assert params["ssl_ca"] == "/etc/ssl/ca.pem"
    assert params["ssl_verify_identity"] is True
    assert params["connect_timeout"] == 5  # noqa: PLR2004


@pytest.mark.parametrize("parameter", ["local_infile", "init_command", "read_default_file", "client_flag", "sslmode"])
def test_refuses_a_url_parameter_outside_the_list(parameter: str) -> None:
    with pytest.raises(ConfigurationException, match=f"'{parameter}' is not supported") as error:
        parse_mysql_url(f"{URL}?{parameter}=sentinel-value")

    assert "sentinel-value" not in str(error.value)
    assert "s3cret" not in str(error.value)


def test_refuses_a_parameter_value_it_cannot_read_without_repeating_it() -> None:
    with pytest.raises(ConfigurationException, match="'ssl_disabled' has a value") as error:
        parse_mysql_url(f"{URL}?ssl_disabled=sentinel-value")

    assert "sentinel-value" not in str(error.value)


@pytest.mark.parametrize(
    ("schema_name", "database"),
    [("public", "shop"), ("", "shop"), ("analytics", "analytics")],
    ids=["default-is-the-url-database", "empty-is-the-url-database", "another-database"],
)
def test_the_schema_is_a_database(driver: FakeDriver, schema_name: str, database: str) -> None:
    repository = MySQLRepository(URL, schema_name)

    repository._get_connection()

    assert repository.schema_name == database
    assert driver.connections[-1]["database"] == database


def test_a_url_without_a_database_is_refused(driver: FakeDriver) -> None:
    with pytest.raises(ConfigurationException, match="names no database") as error:
        MySQLRepository("mysql://reader:s3cret@db.example.com")

    assert "s3cret" not in str(error.value)


def test_every_connection_is_read_only_and_runs_one_statement(driver: FakeDriver) -> None:
    MySQLRepository(URL)._get_connection()

    connection = driver.connections[-1]
    assert connection["init_command"] == "SET SESSION TRANSACTION READ ONLY"
    assert connection["client_flag"] == 0  # no CLIENT.MULTI_STATEMENTS
    assert connection["local_infile"] is False
    assert connection["autocommit"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("version", "timeout_statement"),
    [
        ("8.4.13", "SET SESSION max_execution_time = 7000"),
        ("11.4.13-MariaDB-ubu2404", "SET SESSION max_statement_time = 7"),
    ],
    ids=["mysql-milliseconds", "mariadb-seconds"],
)
async def test_statement_timeout_uses_the_variable_of_the_server(
    driver: FakeDriver, version: str, timeout_statement: str
) -> None:
    driver.version = version
    repository = MySQLRepository(URL)

    result = await repository.execute_query("SELECT COUNT(*) AS n FROM users", limit=10, timeout_seconds=7)

    assert driver.statements[-2:] == [timeout_statement, "SELECT COUNT(*) AS n FROM users LIMIT 10"]
    # The client gives up a little after the server should have
    assert driver.connections[-1]["read_timeout"] == 12  # noqa: PLR2004
    assert result["results"] == [{"n": 1}]
    assert result["columns"] == ["n"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "sql",
    ["SELECT 1 /*! UNION SELECT 2 */", "SELECT load_file('/etc/passwd')", "SELECT 1 INTO OUTFILE '/tmp/x'"],
    ids=["executable-comment", "load_file", "into-outfile"],
)
async def test_a_query_the_mysql_check_rejects_never_reaches_the_server(driver: FakeDriver, sql: str) -> None:
    repository = MySQLRepository(URL)
    await repository.initialize()
    sent_before = list(driver.statements)

    with pytest.raises(SecurityException, match="Query rejected"):
        await repository.execute_query(sql)

    assert driver.statements == sent_before


def test_missing_driver_says_how_to_install_it(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "pymysql", None)

    with pytest.raises(ImportError, match=r"pip install 'nlp2sql\[mysql\]'"):
        MySQLRepository(URL)


@pytest.mark.asyncio
async def test_sign_in_that_needs_cryptography_says_which_extra_installs_it(driver: FakeDriver) -> None:
    def connect(**kwargs: object) -> None:
        # What PyMySQL raises for MySQL 8's default sign-in over a connection without TLS
        raise RuntimeError("'cryptography' package is required for sha256_password or caching_sha2_password")

    driver.connect = connect

    with pytest.raises(SchemaException, match=r"pip install 'nlp2sql\[mysql\]'"):
        await MySQLRepository(URL).initialize()


@pytest.mark.parametrize("scheme", ["mysql", "mysql+pymysql", "mariadb"])
def test_factory_builds_the_mysql_repository_for_its_schemes(driver: FakeDriver, scheme: str) -> None:
    url = f"{scheme}://reader:s3cret@db.example.com/shop"

    assert RepositoryFactory.unsupported_url_reason(url) is None
    assert RepositoryFactory.is_registered(DatabaseType.MYSQL)
    assert isinstance(RepositoryFactory.create(url), MySQLRepository)
