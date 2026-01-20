---
globs:
  - "src/**/*.py"
  - "tests/**/*.py"
  - "mcp_server/**/*.py"
---

# Python Code Style

## Formatting
- Line length: 120 characters
- Use Ruff (Black-compatible): `uv run ruff format .`
- Lint check: `uv run ruff check .`

## Type Hints
- Required in all function signatures
- Use `Optional[T]` for nullable types
- Mypy strict mode: `uv run mypy src/`

## Imports
- Group: stdlib, third-party, local
- Use absolute imports from `nlp2sql/`

## Naming
- Classes: PascalCase
- Functions/variables: snake_case
- Constants: UPPER_SNAKE_CASE
- Private: _underscore_prefix
