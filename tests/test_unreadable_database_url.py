"""A connection URL that cannot be read is refused without repeating any of it.

Measured on main: PostgreSQLRepository("postgresql://user:pa/ss@host/db") raised urllib's
"Port could not be cast to integer value as 'pa'". A password with an unencoded / ? or #
is a common mistake, and that message showed the start of it wherever the error went: a
log, the terminal, an MCP tool result.
"""

import traceback
from collections.abc import Callable

import pytest

from nlp2sql.adapters.mysql_repository import parse_mysql_url
from nlp2sql.adapters.postgres_repository import PostgreSQLRepository
from nlp2sql.exceptions import ConfigurationException

# Stands for the password: no error may hold it
MARKER = "S3cretMarker"
UNREADABLE = [
    f"reader:{MARKER}/x@db.example.com:5432/shop",
    f"reader:{MARKER}?x@db.example.com:5432/shop",
    f"reader:{MARKER}#x@db.example.com:5432/shop",
    f"reader:{MARKER}@db.example.com:port/shop",
    f"reader:{MARKER}@db.example.com:99999999/shop",
    f"reader:{MARKER}@[db.example.com/shop",
]
READERS: list[tuple[str, Callable[[str], object]]] = [
    ("postgresql", PostgreSQLRepository),
    ("postgres", PostgreSQLRepository),
    ("mysql", parse_mysql_url),
    ("mariadb", parse_mysql_url),
]


@pytest.mark.parametrize(("scheme", "read"), READERS)
@pytest.mark.parametrize("rest", UNREADABLE)
def test_the_error_names_no_part_of_the_url(scheme: str, read: Callable[[str], object], rest: str) -> None:
    with pytest.raises(ConfigurationException) as raised:
        read(f"{scheme}://{rest}")

    assert "URL-encoded" in str(raised.value)
    # The traceback too: a chained ValueError would show what the message hides
    assert MARKER not in "".join(traceback.format_exception(raised.value))


@pytest.mark.parametrize(("scheme", "read"), READERS)
def test_an_encoded_password_is_read(scheme: str, read: Callable[[str], object]) -> None:
    built = read(f"{scheme}://reader:pa%2Fss%3Fw%23rd@db.example.com/shop")

    params = built if isinstance(built, dict) else built._connection_params
    assert params["password"] == "pa/ss?w#rd"  # noqa: S105 (the test value)
    assert params["host"] == "db.example.com"
