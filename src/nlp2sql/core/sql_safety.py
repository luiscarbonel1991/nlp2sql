"""SQL safety constants and utilities — pure business logic, no external dependencies."""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import pairwise
from typing import NamedTuple

# SQL patterns that are not allowed for security (read-only enforcement).
# Checked on the query's code only: literals, quoted names and comments are left out.
DANGEROUS_SQL_PATTERNS = [
    r"\bINSERT\b",
    r"\bUPDATE\b",
    r"\bDELETE\b",
    r"\bDROP\b",
    r"\bTRUNCATE\b",
    r"\bALTER\b",
    r"\bCREATE\b",
    r"\bGRANT\b",
    r"\bREVOKE\b",
    r"\bEXEC\b",
    r"\bEXECUTE\b",
    r"\bCALL\b",
    r"\bSET\b",
    r"\bCOPY\b",
    r"\bUNLOAD\b",
    r"\bVACUUM\b",
    # SELECT ... INTO creates a table
    r"\bINTO\b",
]

# Functions that run SQL on another connection or from a string the check cannot see
# into, or that have effects outside the transaction. A quoted name ("pg_sleep") counts.
DANGEROUS_SQL_FUNCTIONS = [
    "dblink",
    "dblink_exec",
    "dblink_send_query",
    "pg_terminate_backend",
    "pg_cancel_backend",
    "pg_reload_conf",
    "pg_read_file",
    "pg_read_binary_file",
    "lo_import",
    "lo_export",
    "set_config",
    "setval",
    "nextval",
    "pg_sleep",
    "query_to_xml",
    "query_to_xml_and_xmlschema",
    "query_to_xmlschema",
    "ts_stat",
]

# MySQL and MariaDB, on top of the lists above
MYSQL_DANGEROUS_SQL_PATTERNS = [
    # SELECT ... INTO OUTFILE / DUMPFILE writes a file on the database server
    r"\bOUTFILE\b",
    r"\bDUMPFILE\b",
    # MariaDB: NEXT VALUE FOR seq advances a sequence
    r"\bNEXT\s+VALUE\b",
]

MYSQL_DANGEROUS_SQL_FUNCTIONS = [
    "load_file",
    "sleep",
    "benchmark",
    "get_lock",
    "release_lock",
    "release_all_locks",
    "is_free_lock",
    "is_used_lock",
    "master_pos_wait",
    "source_pos_wait",
    "master_gtid_wait",
    "wait_for_executed_gtid_set",
    "wait_until_sql_thread_after_gtids",
    "lastval",
    "sys_exec",
    "sys_eval",
]

ALLOWED_QUERY_PREFIXES = ("SELECT", "WITH", "EXPLAIN")

MAX_QUERY_ROWS = 1000
DEFAULT_QUERY_ROWS = 100

# PostgreSQL's whitespace. Other Unicode spaces are identifier characters to it.
_WHITESPACE = " \t\n\r\f\v"
_LINE_END = re.compile(r"[\r\n]")
_NUMBER = re.compile(r"(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_DOLLAR_QUOTE = re.compile(r"\$(?:[A-Za-z_\u0080-\U0010ffff][A-Za-z0-9_\u0080-\U0010ffff]*)?\$")


@dataclass(frozen=True)
class _Dialect:
    """How a server splits a query into literals, names, comments and code."""

    patterns: tuple[str, ...]
    functions: frozenset[str]
    # $tag$...$tag$ is a string literal. Where it is not, its content is code.
    dollar_quotes: bool = True
    # "..." can be a string with backslash escapes (MySQL) or a name (ANSI_QUOTES)
    double_quoted_strings: bool = False
    backtick_names: bool = False
    hash_comments: bool = False
    # MySQL: -- starts a comment only before whitespace, so 5--1 is 5 - (-1)
    dash_comment_needs_space: bool = False
    # /*! ... */ and /*M! ... */ are run as code, /*+ ... */ can change session settings
    comments_that_run: tuple[str, ...] = ()
    # CHARACTER SET names an encoding (CAST(x AS CHAR CHARACTER SET utf8mb4)); it sets nothing
    character_set_clause: bool = False


_POSTGRES = _Dialect(patterns=tuple(DANGEROUS_SQL_PATTERNS), functions=frozenset(DANGEROUS_SQL_FUNCTIONS))
_MYSQL = _Dialect(
    patterns=(*DANGEROUS_SQL_PATTERNS, *MYSQL_DANGEROUS_SQL_PATTERNS),
    functions=frozenset(DANGEROUS_SQL_FUNCTIONS) | frozenset(MYSQL_DANGEROUS_SQL_FUNCTIONS),
    dollar_quotes=False,
    double_quoted_strings=True,
    backtick_names=True,
    hash_comments=True,
    dash_comment_needs_space=True,
    comments_that_run=("/*!", "/*M!", "/*+"),
    character_set_clause=True,
)


def _dialect_of(dialect: object) -> _Dialect:
    """Rules for a DatabaseType or its name. Anything but MySQL is read as PostgreSQL."""
    name = getattr(dialect, "value", dialect)
    return _MYSQL if isinstance(name, str) and name.lower() in ("mysql", "mariadb") else _POSTGRES


class _Token(NamedTuple):
    kind: str  # word, number, symbol, string, identifier or comment
    text: str  # for an identifier, its name without the quotes
    start: int
    end: int


class _UnreadableQueryError(ValueError):
    """The check cannot be sure where a literal or comment ends the way the server would."""


def _is_word_start(ch: str) -> bool:
    # Like PostgreSQL: a letter, an underscore or any non-ASCII character
    return ch == "_" or not ch.isascii() or ch.isalpha()


def _is_digit(ch: str) -> bool:
    return ch.isascii() and ch.isdigit()


def _is_word_char(ch: str) -> bool:
    return _is_word_start(ch) or _is_digit(ch) or ch == "$"


def _quote_end(sql: str, start: int, *, backslash_escapes: bool) -> int | None:
    quote = sql[start]
    i = start + 1
    while i < len(sql):
        if backslash_escapes and sql[i] == "\\":
            i += 2
        elif sql[i] == quote:
            if not sql.startswith(quote, i + 1):
                return i + 1
            i += 2  # '' is a quote inside the literal
        else:
            i += 1
    return None


def _string_end(sql: str, start: int) -> int:
    # Whether a backslash escapes the next character depends on the server and its settings
    # (standard_conforming_strings, E'' strings, Redshift, MySQL's NO_BACKSLASH_ESCAPES and,
    # for "...", ANSI_QUOTES). A literal whose end depends on
    # that could hide code from the check, so it must end in the same place either way.
    plain = _quote_end(sql, start, backslash_escapes=False)
    escaped = _quote_end(sql, start, backslash_escapes=True)
    if plain is None and escaped is None:
        raise _UnreadableQueryError("Query has an unterminated string literal")
    if plain != escaped:
        raise _UnreadableQueryError("String literal with a backslash before a quote is ambiguous; escape quotes as ''")
    return plain


def _literal_end(sql: str, start: int, dialect: _Dialect) -> int | None:
    """End of the '...' or $tag$...$tag$ literal at ``start``, or None if none starts there."""
    if sql[start] == "'":
        return _string_end(sql, start)
    dollar = _DOLLAR_QUOTE.match(sql, start) if dialect.dollar_quotes else None
    if not dollar:
        return None
    close = sql.find(dollar.group(), dollar.end())
    if close == -1:
        raise _UnreadableQueryError("Query has an unterminated dollar-quoted string")
    return close + len(dollar.group())


def _starts_line_comment(sql: str, start: int, dialect: _Dialect) -> bool:
    if dialect.hash_comments and sql[start] == "#":
        return True
    if not sql.startswith("--", start):
        return False
    after = sql[start + 2 : start + 3]
    return not dialect.dash_comment_needs_space or after == "" or after in _WHITESPACE or ord(after) < 32  # noqa: PLR2004


def _comment_end(sql: str, start: int, dialect: _Dialect) -> int | None:
    """End of the line or /* */ comment at ``start``, or None if none starts there."""
    if _starts_line_comment(sql, start, dialect):
        line_end = _LINE_END.search(sql, start)
        return line_end.start() if line_end else len(sql)
    if not sql.startswith("/*", start):
        return None
    if sql.startswith(dialect.comments_that_run, start):
        raise _UnreadableQueryError("Comments that the server runs (/*! */, /*M! */, /*+ */) are not allowed")
    close = sql.find("*/", start + 2)
    if close == -1:
        raise _UnreadableQueryError("Query has an unterminated comment")
    # PostgreSQL nests comments, other servers end at the first */
    if "/*" in sql[start + 2 : close]:
        raise _UnreadableQueryError("Nested comments are not allowed")
    return close + 2


def _quoted_name_end(sql: str, start: int) -> int:
    end = _quote_end(sql, start, backslash_escapes=False)
    if end is None:
        raise _UnreadableQueryError("Query has an unterminated quoted identifier")
    return end


def _name_token(sql: str, start: int, dialect: _Dialect) -> _Token | None:
    """The "name" or `name` at ``start``, or None if none starts there."""
    quote = sql[start]
    if quote == '"':
        # Where "..." can also be a string, it must end in the same place read either way.
        # It stays a name for the check, so "sleep"(1) is still a call.
        end = _string_end(sql, start) if dialect.double_quoted_strings else _quoted_name_end(sql, start)
    elif quote == "`" and dialect.backtick_names:
        end = _quoted_name_end(sql, start)
    else:
        return None
    return _Token("identifier", sql[start + 1 : end - 1].replace(quote * 2, quote), start, end)


def _word_end(sql: str, start: int) -> int:
    end = start + 1
    while end < len(sql) and _is_word_char(sql[end]):
        end += 1
    # U&"d\0061ta" spells a name with escapes the check would have to decode
    if sql[start:end].upper() == "U" and sql.startswith('&"', end):
        raise _UnreadableQueryError("Unicode-escaped identifiers are not allowed")
    return end


def _tokenize(sql: str, dialect: _Dialect = _POSTGRES) -> list[_Token]:
    """Split a query the way the server's lexer does, as far as the safety check needs.

    Raises:
        _UnreadableQueryError: A literal, quoted name or comment is unterminated or could
            be read differently by another server.
    """
    tokens: list[_Token] = []
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch in _WHITESPACE:
            i += 1
            continue
        if (end := _comment_end(sql, i, dialect)) is not None:
            token = _Token("comment", sql[i:end], i, end)
        elif (end := _literal_end(sql, i, dialect)) is not None:
            token = _Token("string", sql[i:end], i, end)
        elif (name := _name_token(sql, i, dialect)) is not None:
            token = name
        elif _is_digit(ch) or (ch == "." and _is_digit(sql[i + 1 : i + 2])):
            # A number ends where a word starts: in "1INTO", INTO is a keyword
            end = _NUMBER.match(sql, i).end()
            token = _Token("number", sql[i:end], i, end)
        elif _is_word_start(ch):
            end = _word_end(sql, i)
            token = _Token("word", sql[i:end], i, end)
        else:
            token = _Token("symbol", ch, i, i + 1)
        tokens.append(token)
        i = token.end
    return tokens


def _is_character_set(previous: _Token | None, token: _Token) -> bool:
    return (
        token.kind == "word"
        and token.text.upper() == "SET"
        and previous is not None
        and previous.kind == "word"
        and previous.text.upper() == "CHARACTER"
    )


def _code_text(code: list[_Token], dialect: _Dialect) -> str:
    """The code with literals as '' and quoted names as "", so 'please DELETE my account' is data."""
    parts = []
    for previous, token in zip([None, *code], code, strict=False):
        if token.kind == "string":
            parts.append("''")
        elif token.kind == "identifier":
            parts.append('""')
        elif not (dialect.character_set_clause and _is_character_set(previous, token)):
            parts.append(token.text)
    return " ".join(parts)


def is_safe_query(sql: str, *, dialect: object = None) -> tuple[bool, str]:
    """Check if a SQL query is safe to execute (read-only).

    The query is split into tokens first, so keywords, function names and semicolons
    inside string literals ('...', E'...', $$...$$), quoted names and comments do not count,
    and nothing a literal could hide is missed. Queries the check cannot read the way
    every supported server would are rejected.

    Args:
        sql: The SQL query to validate.
        dialect: The DatabaseType of the server, or its name. MySQL and MariaDB read
            quotes, comments and ``$`` differently, and have their own functions to
            prohibit. Anything else, and None, is read as PostgreSQL.

    Returns:
        Tuple of (is_safe, error_message).
    """
    rules = _dialect_of(dialect)
    try:
        tokens = _tokenize(sql, rules)
    except _UnreadableQueryError as exc:
        return False, str(exc)
    code = [token for token in tokens if token.kind != "comment"]

    if not code or code[0].kind != "word" or code[0].text.upper() not in ALLOWED_QUERY_PREFIXES:
        return False, "Only SELECT, WITH, or EXPLAIN queries are allowed"

    code_text = _code_text(code, rules)
    for pattern in rules.patterns:
        if re.search(pattern, code_text, re.IGNORECASE):
            return False, "Query contains prohibited operation"

    for current, following in pairwise(code):
        is_call = current.kind in ("word", "identifier") and following.kind == "symbol" and following.text == "("
        if is_call and current.text.lower() in rules.functions:
            return False, f"Query calls prohibited function {current.text.lower()}()"

    # Check for multiple statements (SQL injection protection); a trailing ; is fine
    while code and code[-1].kind == "symbol" and code[-1].text == ";":
        code.pop()
    if any(token.kind == "symbol" and token.text == ";" for token in code):
        return False, "Multiple SQL statements are not allowed"

    return True, ""


def apply_row_limit(sql: str, limit: int, *, dialect: object = None) -> str:
    """Ensure query has a row limit applied.

    Args:
        sql: The SQL query.
        limit: Maximum rows to return.
        dialect: The DatabaseType of the server, or its name, as in is_safe_query.

    Returns:
        SQL with LIMIT clause applied.
    """
    limit = min(limit, MAX_QUERY_ROWS)

    try:
        tokens = _tokenize(sql, _dialect_of(dialect))
    except _UnreadableQueryError:
        # is_safe_query rejects these; a new line keeps a trailing comment from hiding the limit
        return f"{sql.rstrip().rstrip(';')}\nLIMIT {limit}"
    code = [token for token in tokens if token.kind != "comment"]

    # LIMIT inside a literal ('%LIMIT%'), a quoted name or a comment is not a clause
    if any(token.kind == "word" and token.text.upper() == "LIMIT" for token in code):
        return sql

    while code and code[-1].kind == "symbol" and code[-1].text == ";":
        code.pop()
    # Cut after the last token, so a trailing semicolon or -- comment cannot swallow the LIMIT
    end = code[-1].end if code else 0
    return f"{sql[:end]} LIMIT {limit}"
