"""QueryResult carries the validation behind is_valid and, when executed, the rows."""

from nlp2sql.core.result import QueryResult


def test_from_dict_keeps_validation_rows_and_columns():
    validation = {"is_valid": False, "errors": ["Execution failed: relation does not exist"], "warnings": []}

    result = QueryResult.from_dict(
        {
            "sql": "SELECT region, COUNT(*) AS users FROM users GROUP BY region",
            "confidence": 0.9,
            "validation": validation,
            "rows": [{"region": "EU", "users": 3}],
            "columns": ["region", "users"],
        }
    )

    assert result.is_valid is False
    assert result.validation == validation
    assert result.rows == [{"region": "EU", "users": 3}]
    assert result.columns == ["region", "users"]


def test_from_dict_without_execution_or_validation():
    result = QueryResult.from_dict({"sql": "SELECT 1", "confidence": 0.5, "validation": None})

    assert result.is_valid is False
    assert result.validation == {}
    assert result.rows is None
    assert result.columns is None
