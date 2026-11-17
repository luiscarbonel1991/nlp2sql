"""The MCP server and the version of the mcp SDK it asks for.

server.py imports FastMCP, which exists only in mcp 1.x: 2.x renamed it to MCPServer, and
the import fails. CI does not install mcp, so this reads the files instead.
"""

import re
from pathlib import Path

import pytest

tomllib = pytest.importorskip("tomllib")

MCP_SERVER = Path(__file__).resolve().parents[2] / "mcp_server"


def _uses_the_1x_api() -> bool:
    return "from mcp.server.fastmcp import FastMCP" in (MCP_SERVER / "server.py").read_text()


def _mcp_requirement() -> str:
    with (MCP_SERVER / "pyproject.toml").open("rb") as file:
        dependencies = tomllib.load(file)["project"]["dependencies"]
    return next(dependency for dependency in dependencies if re.match(r"mcp\b", dependency))


def test_a_server_on_the_1x_api_does_not_accept_mcp_2() -> None:
    if not _uses_the_1x_api():
        pytest.skip("server.py no longer imports FastMCP: the bound can be lifted")

    assert "<2" in _mcp_requirement()


def test_the_readme_installs_what_the_server_runs_with() -> None:
    if not _uses_the_1x_api():
        pytest.skip("server.py no longer imports FastMCP: the bound can be lifted")
    readme = (MCP_SERVER / "README.md").read_text()

    install_lines = [line for line in readme.splitlines() if re.match(r"(pip install|uv add) .*\bmcp\b", line)]

    assert install_lines
    assert all('"mcp<2"' in line for line in install_lines)
