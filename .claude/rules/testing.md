---
globs:
  - "tests/**/*.py"
---

# Testing Conventions

## Structure
- Files: `test_*.py`
- Functions: `test_*`
- Fixtures in `tests/conftest.py`

## Commands
- All tests: `uv run pytest`
- Single file: `uv run pytest tests/test_X.py -v`
- Skip integration: `uv run pytest -m "not integration"`

## Markers
- `@pytest.mark.integration` - requires external services
- `@pytest.mark.slow` - long-running tests

## Mocking
- Mock external APIs (OpenAI, Anthropic, Gemini)
- Use `pytest-asyncio` for async tests
