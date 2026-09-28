"""Every copy of the package version must match pyproject.toml.

The publish workflows only run from a tag named ``v`` + the pyproject.toml
version; these checks extend that guarantee to every other place the version
is written, so a partial bump fails CI instead of shipping mixed versions.
"""

import re
from pathlib import Path
from typing import Any

import pytest

import nlp2sql
from nlp2sql.config.settings import Settings

tomllib = pytest.importorskip("tomllib")

ROOT = Path(__file__).resolve().parents[1]


def _toml(relative_path: str) -> dict[str, Any]:
    with (ROOT / relative_path).open("rb") as file:
        return tomllib.load(file)


def _mcp_server_init_version() -> str:
    source = (ROOT / "mcp_server" / "__init__.py").read_text()
    match = re.search(r'^__version__ = "([^"]+)"', source, re.MULTILINE)
    assert match, "mcp_server/__init__.py does not define __version__"
    return match.group(1)


def _uv_lock_version() -> str:
    packages = _toml("uv.lock")["package"]
    return next(package["version"] for package in packages if package["name"] == "nlp2sql")


EXPECTED = _toml("pyproject.toml")["project"]["version"]

VERSION_COPIES = {
    "src/nlp2sql/__init__.py": lambda: nlp2sql.__version__,
    # The class default, not an instance: Settings has no env prefix, so a VERSION
    # environment variable would override the instance value.
    "src/nlp2sql/config/settings.py": lambda: Settings.model_fields["version"].default,
    "mcp_server/pyproject.toml project.version": lambda: _toml("mcp_server/pyproject.toml")["project"]["version"],
    "mcp_server/pyproject.toml tool.mcp.version": lambda: _toml("mcp_server/pyproject.toml")["tool"]["mcp"]["version"],
    "mcp_server/__init__.py": _mcp_server_init_version,
    "uv.lock": _uv_lock_version,
}


@pytest.mark.parametrize("location", VERSION_COPIES)
def test_version_copy_matches_pyproject(location: str) -> None:
    assert VERSION_COPIES[location]() == EXPECTED, f"{location} is out of sync with pyproject.toml ({EXPECTED})"


def test_changelog_has_a_section_for_the_current_version() -> None:
    changelog = (ROOT / "CHANGELOG.md").read_text()
    assert f"## [{EXPECTED}]" in changelog, f"CHANGELOG.md has no '## [{EXPECTED}]' section"
