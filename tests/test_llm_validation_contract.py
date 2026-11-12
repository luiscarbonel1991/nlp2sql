"""What AIProviderPort.validate_query may answer (ports/ai_provider.py)."""

import pytest

from nlp2sql.ports.ai_provider import checked_validation, validation_unavailable

TOKENS = 12


def test_an_unavailable_review_is_never_valid() -> None:
    answer = validation_unavailable("connection refused")

    assert answer == {
        "is_valid": False,
        "errors": ["LLM validation unavailable: connection refused"],
        "warnings": [],
        "llm_validation_error": "connection refused",
    }


@pytest.mark.parametrize(
    "answer",
    [None, "not json", [], {}, {"errors": []}, {"is_valid": "true"}, {"is_valid": 1}],
    ids=["none", "text", "list", "empty", "no-verdict", "string-verdict", "number-verdict"],
)
def test_an_answer_without_a_boolean_verdict_is_unavailable(answer: object) -> None:
    checked = checked_validation(answer)

    assert checked["is_valid"] is False
    assert checked["llm_validation_error"]
    assert checked["errors"] == [f"LLM validation unavailable: {checked['llm_validation_error']}"]


def test_a_verdict_keeps_its_errors_and_warnings() -> None:
    checked = checked_validation({"is_valid": False, "errors": ["wrong join"], "warnings": ["no LIMIT"]})

    assert checked == {"is_valid": False, "errors": ["wrong join"], "warnings": ["no LIMIT"]}


def test_errors_and_warnings_are_always_lists() -> None:
    assert checked_validation({"is_valid": True}) == {"is_valid": True, "errors": [], "warnings": []}

    checked = checked_validation({"is_valid": False, "errors": "wrong join", "warnings": None})

    assert checked["errors"] == ["wrong join"]
    assert checked["warnings"] == []


def test_issues_is_an_older_name_for_errors() -> None:
    checked = checked_validation({"is_valid": False, "issues": ["orders has no column total"]})

    assert checked["errors"] == ["orders has no column total"]
    assert "issues" not in checked


def test_an_answer_that_reports_its_own_failure_is_not_an_approval() -> None:
    # What an adapter that swallows a failed call used to answer
    checked = checked_validation({"is_valid": True, "issues": [], "error": "Validation error: Connection error."})

    assert checked["is_valid"] is False
    assert checked["llm_validation_error"] == "Validation error: Connection error."
    assert "error" not in checked


def test_checking_twice_changes_nothing() -> None:
    for answer in (
        validation_unavailable("connection refused"),
        checked_validation({"is_valid": False, "issues": ["wrong join"], "suggestions": ["add an index"]}),
    ):
        assert checked_validation(answer) == answer


def test_other_keys_pass_through() -> None:
    checked = checked_validation({"is_valid": True, "suggestions": ["add an index"], "_tokens_used": TOKENS})

    assert checked["suggestions"] == ["add an index"]
    assert checked["_tokens_used"] == TOKENS


def test_the_tokens_of_an_unreadable_answer_are_kept() -> None:
    checked = checked_validation({"errors": [], "_tokens_used": TOKENS})

    assert checked["is_valid"] is False
    assert checked["_tokens_used"] == TOKENS
