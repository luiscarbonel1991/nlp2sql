"""Regex-based query validator — validates SQL columns using pattern matching."""

import re
from typing import Any

from ..core.sql_keywords import SQL_KEYWORDS
from ..ports.query_validator import QueryValidatorPort


class RegexQueryValidator(QueryValidatorPort):
    """Validates SQL column references using regex extraction.

    Extracts table references, aliases, CTEs, and identifiers from SQL
    using regex patterns, then checks that every identifier is either a
    known SQL keyword, table name, column, or alias.
    """

    async def validate_columns(self, sql: str, tables: list[Any]) -> list[str]:
        """Validate column names in SQL against the columns of referenced tables."""
        # Build table -> columns mapping
        table_columns: dict[str, set[str]] = {}
        all_table_names: set[str] = set()
        for table in tables:
            all_table_names.add(table.name.lower())
            table_columns[table.name.lower()] = {c["name"].lower() for c in table.columns}

        # Extract tables referenced in SQL (after FROM / JOIN, with optional schema prefix)
        referenced_tables: set[str] = set()
        for match in re.finditer(r"\b(?:from|join)\s+(?:\w+\.)?(\w+)\b", sql, re.IGNORECASE):
            name = match.group(1).lower()
            if name in all_table_names:
                referenced_tables.add(name)

        if not referenced_tables:
            return []

        # Valid columns = only from referenced tables
        valid_columns: set[str] = set()
        for tname in referenced_tables:
            valid_columns.update(table_columns.get(tname, set()))

        # Extract aliases (after AS) to exclude from validation
        aliases = {m.lower() for m in re.findall(r"\bAS\s+(\w+)\b", sql, re.IGNORECASE)}

        # Extract CTE names (WITH cte_name AS) to exclude from validation
        cte_names = {m.lower() for m in re.findall(r"\bWITH\s+(\w+)\s+AS\s*\(", sql, re.IGNORECASE)}
        cte_names.update(m.lower() for m in re.findall(r",\s*(\w+)\s+AS\s*\(", sql, re.IGNORECASE))

        # Extract table aliases (FROM/JOIN table alias, table AS alias)
        table_aliases: set[str] = set()
        for match in re.finditer(r"\b(?:from|join)\s+(?:\w+\.)?(\w+)\s+(?:AS\s+)?([a-z_]\w*)\b", sql, re.IGNORECASE):
            alias = match.group(2).lower()
            if alias not in SQL_KEYWORDS:
                table_aliases.add(alias)

        # Combine all exclusions
        excluded = aliases | cte_names | table_aliases

        # Extract all identifiers from SQL (excluding string literals)
        sql_clean = re.sub(r"'[^']*'", "", sql)
        tokens = set(re.findall(r"\b[a-z_][a-z0-9_]*\b", sql_clean.lower()))

        errors = []
        for token in tokens:
            # Skip short tokens (likely aliases like f, j, t, o)
            if len(token) <= 2:
                continue
            if token in SQL_KEYWORDS or token in all_table_names or token in valid_columns or token in excluded:
                continue
            # Find close matches in the referenced tables' columns
            close = sorted(c for c in valid_columns if token in c or c in token)
            if close:
                tables_str = ", ".join(referenced_tables)
                errors.append(
                    f"Column '{token}' not found in tables ({tables_str}). Similar columns: {', '.join(close[:3])}"
                )

        return errors
