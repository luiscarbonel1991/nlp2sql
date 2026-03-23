"""SQL keywords — shared set for validation and tokenization."""

SQL_KEYWORDS: frozenset[str] = frozenset({
    "select", "from", "where", "and", "or", "not", "in", "between",
    "group", "by", "order", "having", "limit", "offset", "as", "on",
    "join", "left", "right", "inner", "outer", "cross", "full",
    "case", "when", "then", "else", "end", "null", "true", "false",
    "asc", "desc", "distinct", "union", "all", "exists", "any",
    "count", "sum", "avg", "min", "max", "abs", "round", "floor", "ceil",
    "date_trunc", "dateadd", "datediff", "current_date", "getdate",
    "extract", "epoch", "convert_timezone", "to_date", "to_char",
    "coalesce", "nullif", "cast", "like", "ilike", "is", "with",
    "month", "year", "day", "quarter", "week", "hour", "minute", "second",
    "varchar", "int", "integer", "bigint", "numeric", "decimal",
    "date", "timestamp", "boolean", "float", "double", "precision",
    "over", "partition", "row_number", "rank", "dense_rank",
    "lag", "lead", "first_value", "last_value", "listagg",
    "approximate", "interval", "explain", "analyze",
})
