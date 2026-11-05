"""SQL safety constants and utilities — pure business logic, no external dependencies."""

import re
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

ALLOWED_QUERY_PREFIXES = ("SELECT", "WITH", "EXPLAIN")

MAX_QUERY_ROWS = 1000
DEFAULT_QUERY_ROWS = 100

# PostgreSQL's whitespace. Other Unicode spaces are identifier characters to it.
_WHITESPACE = " \t\n\r\f\v"
_LINE_END = re.compile(r"[\r\n]")
_NUMBER = re.compile(r"(?:[0-9]+\.?[0-9]*|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_DOLLAR_QUOTE = re.compile(r"\$(?:[A-Za-z_\u0080-\U0010ffff][A-Za-z0-9_\u0080-\U0010ffff]*)?\$")


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
    i = start + 1
    while i < len(sql):
        if backslash_escapes and sql[i] == "\\":
            i += 2
        elif sql[i] == "'":
            if not sql.startswith("'", i + 1):
                return i + 1
            i += 2  # '' is a quote inside the literal
        else:
            i += 1
    return None


def _string_end(sql: str, start: int) -> int:
    # Whether a backslash escapes the next character depends on the server and its settings
    # (standard_conforming_strings, E'' strings, Redshift). A literal whose end depends on
    # that could hide code from the check, so it must end in the same place either way.
    plain = _quote_end(sql, start, backslash_escapes=False)
    escaped = _quote_end(sql, start, backslash_escapes=True)
    if plain is None and escaped is None:
        raise _UnreadableQueryError("Query has an unterminated string literal")
    if plain != escaped:
        raise _UnreadableQueryError("String literal with a backslash before a quote is ambiguous; escape quotes as ''")
    return plain


def _literal_end(sql: str, start: int) -> int | None:
    """End of the '...' or $tag$...$tag$ literal at ``start``, or None if none starts there."""
    if sql[start] == "'":
        return _string_end(sql, start)
    dollar = _DOLLAR_QUOTE.match(sql, start)
    if not dollar:
        return None
    close = sql.find(dollar.group(), dollar.end())
    if close == -1:
        raise _UnreadableQueryError("Query has an unterminated dollar-quoted string")
    return close + len(dollar.group())


def _comment_end(sql: str, start: int) -> int | None:
    """End of the -- or /* */ comment at ``start``, or None if none starts there."""
    if sql.startswith("--", start):
        line_end = _LINE_END.search(sql, start)
        return line_end.start() if line_end else len(sql)
    if not sql.startswith("/*", start):
        return None
    close = sql.find("*/", start + 2)
    if close == -1:
        raise _UnreadableQueryError("Query has an unterminated comment")
    # PostgreSQL nests comments, other servers end at the first */
    if "/*" in sql[start + 2 : close]:
        raise _UnreadableQueryError("Nested comments are not allowed")
    return close + 2


def _quoted_name_end(sql: str, start: int) -> int:
    end = start + 1
    while True:
        end = sql.find('"', end)
        if end == -1:
            raise _UnreadableQueryError("Query has an unterminated quoted identifier")
        if not sql.startswith('"', end + 1):
            return end + 1
        end += 2  # "" is a quote inside the name


def _word_end(sql: str, start: int) -> int:
    end = start + 1
    while end < len(sql) and _is_word_char(sql[end]):
        end += 1
    # U&"d\0061ta" spells a name with escapes the check would have to decode
    if sql[start:end].upper() == "U" and sql.startswith('&"', end):
        raise _UnreadableQueryError("Unicode-escaped identifiers are not allowed")
    return end


def _tokenize(sql: str) -> list[_Token]:
    """Split a query the way PostgreSQL's lexer does, as far as the safety check needs.

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
        if (end := _comment_end(sql, i)) is not None:
            token = _Token("comment", sql[i:end], i, end)
        elif (end := _literal_end(sql, i)) is not None:
            token = _Token("string", sql[i:end], i, end)
        elif ch == '"':
            end = _quoted_name_end(sql, i)
            token = _Token("identifier", sql[i + 1 : end - 1].replace('""', '"'), i, end)
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


def is_safe_query(sql: str) -> tuple[bool, str]:
    """Check if a SQL query is safe to execute (read-only).

    The query is split into tokens first, so keywords, function names and semicolons
    inside string literals ('...', E'...', $$...$$), quoted names and comments do not count,
    and nothing a literal could hide is missed. Queries the check cannot read the way
    every supported server would are rejected.

    Args:
        sql: The SQL query to validate.

    Returns:
        Tuple of (is_safe, error_message).
    """
    try:
        tokens = _tokenize(sql)
    except _UnreadableQueryError as exc:
        return False, str(exc)
    code = [token for token in tokens if token.kind != "comment"]

    if not code or code[0].kind != "word" or code[0].text.upper() not in ALLOWED_QUERY_PREFIXES:
        return False, "Only SELECT, WITH, or EXPLAIN queries are allowed"

    # Literals become '' and quoted names "", so 'please DELETE my account' is data
    code_text = " ".join("''" if t.kind == "string" else '""' if t.kind == "identifier" else t.text for t in code)
    for pattern in DANGEROUS_SQL_PATTERNS:
        if re.search(pattern, code_text, re.IGNORECASE):
            return False, "Query contains prohibited operation"

    for current, following in pairwise(code):
        is_call = current.kind in ("word", "identifier") and following.kind == "symbol" and following.text == "("
        if is_call and current.text.lower() in DANGEROUS_SQL_FUNCTIONS:
            return False, f"Query calls prohibited function {current.text.lower()}()"

    # Check for multiple statements (SQL injection protection); a trailing ; is fine
    while code and code[-1].kind == "symbol" and code[-1].text == ";":
        code.pop()
    if any(token.kind == "symbol" and token.text == ";" for token in code):
        return False, "Multiple SQL statements are not allowed"

    return True, ""


def apply_row_limit(sql: str, limit: int) -> str:
    """Ensure query has a row limit applied.

    Args:
        sql: The SQL query.
        limit: Maximum rows to return.

    Returns:
        SQL with LIMIT clause applied.
    """
    limit = min(limit, MAX_QUERY_ROWS)

    try:
        tokens = _tokenize(sql)
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
