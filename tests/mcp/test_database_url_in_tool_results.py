"""No MCP tool result repeats a connection URL with its password.

A tool result goes to the model and stays in the client's history. Measured before this
test existed, on 56 failing calls (14 URLs, by URL and by alias, explore_schema and
run_sql): 18 results held the password. explore_schema() repeated the URL it was given,
and a password with an unencoded "/" came back in "Port could not be cast to integer
value as '...'", also when the caller only knew the alias.

The server runs in a child process with a stand-in for the mcp SDK, which CI does not
install, and because importing the server configures logging for the whole process.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# Stands for the password: no tool result may hold it
MARKER = "S3cretMarker"
SCENARIOS = 16

CHILD = r"""
import asyncio
import json
import os
import sys
import types


class FastMCP:
    def __init__(self, name):
        self.name = name

    def tool(self):
        return lambda function: function


sys.modules["mcp.server.fastmcp"] = types.SimpleNamespace(FastMCP=FastMCP)

from mcp_server import server

SECRET = os.environ["TEST_SECRET"]
URL = f"postgresql://reader:{SECRET}@db.example.com:5432/shop"
NO_SCHEME = f"reader:{SECRET}@db.example.com:5432/shop"
SLASH_IN_PASSWORD = f"postgresql://reader:{SECRET}/x@db.example.com:5432/shop"
results = {}


class Repository:
    # A driver or a wrapper that quotes the URL it could not use
    schema_name = "public"
    fails = False

    def _check(self):
        if self.fails:
            raise RuntimeError(f"could not connect with {URL}")

    async def get_tables(self):
        self._check()
        return []

    async def execute_query(self, sql, limit):
        self._check()
        return {"results": [], "columns": [], "row_count": 0, "execution_time_ms": 1.0}


class Service:
    async def generate_sql(self, question, database_type):
        return {"sql": "SELECT 1"}


async def main():
    # 1. Before any repository exists: text that is not a URL, and a URL that cannot be read
    results["no scheme / explore_schema"] = await server.explore_schema(database=NO_SCHEME)
    results["no scheme / run_sql"] = await server.run_sql("SELECT 1", database=NO_SCHEME)
    results["no scheme / ask_database"] = await server.ask_database("How many?", database=NO_SCHEME)
    results["no scheme / explain_sql"] = await server.explain_sql("SELECT 1", database=NO_SCHEME)
    results["slash in password / explore_schema"] = await server.explore_schema(database=SLASH_IN_PASSWORD)
    results["slash in password / run_sql"] = await server.run_sql("SELECT 1", database=SLASH_IN_PASSWORD)
    os.environ["NLP2SQL_PROD_DB_URL"] = SLASH_IN_PASSWORD
    results["slash in password / alias / explore_schema"] = await server.explore_schema(database="prod")
    results["slash in password / alias / run_sql"] = await server.run_sql("SELECT 1", database="prod")

    # 2. A repository that works: explore_schema names the database it listed
    repository = Repository()

    async def get_repository(database_url, schema_name="public"):
        return repository

    async def get_cached_service(database_url, database_type, provider=None, schema_name="public"):
        return Service()

    server._get_repository = get_repository
    server._get_cached_service = get_cached_service
    os.environ["NLP2SQL_PROD_DB_URL"] = URL
    results["listed / url"] = await server.explore_schema(database=URL)
    results["listed / alias"] = await server.explore_schema(database="prod")

    # 3. A repository whose error quotes the URL
    repository.fails = True
    for how, database in (("url", URL), ("alias", "prod")):
        results[f"error quotes the url / {how} / explore_schema"] = await server.explore_schema(database=database)
        results[f"error quotes the url / {how} / run_sql"] = await server.run_sql("SELECT 1", database=database)
        results[f"error quotes the url / {how} / ask_database"] = await server.ask_database(
            "How many?", database=database, execute=True
        )

    print(json.dumps(results))


asyncio.run(main())
"""


@pytest.fixture(scope="module")
def results(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    # No provider key and no .env in the working directory: no scenario may reach a provider
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("NLP2SQL_") and not name.endswith("_API_KEY")
    }
    environment["PYTHONPATH"] = os.pathsep.join([str(ROOT), str(ROOT / "src")])
    environment["TEST_SECRET"] = MARKER
    child = subprocess.run(  # noqa: S603 (this file's own script)
        [sys.executable, "-c", CHILD],
        capture_output=True,
        text=True,
        env=environment,
        cwd=tmp_path_factory.mktemp("mcp_server"),
        check=False,
    )
    assert child.returncode == 0, child.stderr[-2000:]
    assert MARKER not in child.stderr, "the server logged the password"
    return json.loads(child.stdout.strip().splitlines()[-1])


def test_every_scenario_ran(results: dict[str, str]) -> None:
    assert len(results) == SCENARIOS


def test_no_tool_result_holds_the_password(results: dict[str, str]) -> None:
    assert [name for name, result in results.items() if MARKER in result] == []


def test_explore_schema_names_the_database_without_the_password(results: dict[str, str]) -> None:
    assert json.loads(results["listed / url"])["database"] == "postgresql://reader:***@db.example.com:5432/shop"
    assert json.loads(results["listed / alias"])["database"] == "prod"


@pytest.mark.parametrize("tool", ["explore_schema", "run_sql", "ask_database", "explain_sql"])
def test_text_that_is_not_a_url_comes_back_masked(results: dict[str, str], tool: str) -> None:
    error = json.loads(results[f"no scheme / {tool}"])["error"]

    assert "Invalid database: 'reader:***@db.example.com:5432/shop'" in error


@pytest.mark.parametrize("how", ["slash in password", "slash in password / alias"])
@pytest.mark.parametrize("tool", ["explore_schema", "run_sql"])
def test_a_url_that_cannot_be_read_says_how_to_write_it(results: dict[str, str], how: str, tool: str) -> None:
    error = json.loads(results[f"{how} / {tool}"])

    assert error["error_type"] == "ConfigurationException"
    assert "URL-encoded" in error["error"]


@pytest.mark.parametrize("how", ["url", "alias"])
def test_an_error_that_quotes_the_url_is_masked(results: dict[str, str], how: str) -> None:
    masked = "could not connect with postgresql://reader:***@db.example.com:5432/shop"

    assert masked in json.loads(results[f"error quotes the url / {how} / explore_schema"])["error"]
    assert masked in json.loads(results[f"error quotes the url / {how} / run_sql"])["error"]
    assert masked in json.loads(results[f"error quotes the url / {how} / ask_database"])["execution_error"]
