"""Check that a release tag matches the package version before publishing.

The publish workflows run this before building, so a package is only ever
published from a tag named ``v`` + the ``[project].version`` of pyproject.toml.

Usage: python .github/scripts/verify_release_tag.py v0.2.0rc16
"""

import argparse
import re
import sys
from pathlib import Path
from typing import Optional

import tomllib

TAG_PATTERN = re.compile(r"v\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?")
PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"
SEE_DOCS = "See 'Releasing (maintainers)' in CONTRIBUTING.md."


def fail(message: str) -> int:
    print(f"::error title=Release tag check failed::{message} {SEE_DOCS}")
    return 1


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check that a release tag matches the version in pyproject.toml.")
    parser.add_argument("tag", help="release tag, for example v0.2.0rc16")
    tag = parser.parse_args(argv).tag

    if not TAG_PATTERN.fullmatch(tag):
        return fail(f"'{tag}' is not a release tag: expected vX.Y.Z, optionally followed by aN, bN or rcN.")

    with PYPROJECT.open("rb") as file:
        version = tomllib.load(file)["project"]["version"]
    if tag != f"v{version}":
        return fail(
            f"Tag {tag} does not match the pyproject.toml version ({version}) of the checked-out commit. "
            "Was the release created before the version bump was pushed?"
        )

    print(f"Tag {tag} matches the pyproject.toml version {version}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
