---
name: quality
description: Run all code quality checks
---

Execute in order:
1. `uv run ruff format .`
2. `uv run ruff check .`
3. `uv run mypy src/`

Report any issues found.
