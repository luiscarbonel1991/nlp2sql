# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## Versioning policy

- **MAJOR** — incompatible public API changes (removing/renaming a public symbol
  or changing a port/ABC contract in a non-backward-compatible way).
- **MINOR** — backward-compatible functionality (new adapters, new optional
  parameters, new optional extras).
- **PATCH** — backward-compatible bug fixes.

Pre-1.0 the project ships release candidates (e.g. `0.2.0rcN`). Public surface
changes — moving/renaming exported symbols, or adding methods to a published
port such as `ExampleRepositoryPort` — MUST be recorded under `Unreleased`
before release and called out as **Breaking** if they affect external
implementers. Backward-compatible shims are preferred over hard breaks while
pre-1.0.

## [Unreleased]

### Changed
- **User-visible: the LLM no longer reviews its own SQL by default.** Every `ask()`
  made a second LLM call that sent the whole schema context back to the model; it
  doubled the latency of each question and its tokens were not reported. Column,
  dialect, semantic and read-only checks still run, and execution modes still
  validate against the database. Turn the review back on with
  `connect(..., llm_validation=True)`, `NLP2SQL_LLM_VALIDATION=true` or
  `nlp2sql query --llm-validation`. `NLP2SQL.validate(sql)` still asks the LLM.
- `QueryResult.tokens_used` now counts every LLM call made for the question
  (retries, repairs and LLM validation); it used to report only the last
  generation call. `metadata["token_usage"]` has the breakdown.
- `refresh_schema()` (PostgreSQL and Redshift) now drops the cached table list so
  the next `get_tables()` reads the database again. PostgreSQL no longer runs
  `ANALYZE` on the whole database on the first `connect()` and every 24 hours.
- Provider calls are retried only on rate limits, timeouts, connection errors and
  provider-side errors. Authentication and request errors fail on the first
  attempt, instead of after about 8 seconds and 3 requests.

### Added
- `llm_validation` option on `connect()`, `create_query_service()` and
  `create_and_initialize_service()`, `NLP2SQL_LLM_VALIDATION`, and
  `nlp2sql query --llm-validation`.
- `ProviderAuthenticationError`, `ProviderRequestError`, `ProviderRateLimitError`
  and `ProviderUnavailableError`, subclasses of `ProviderException`, raised by the
  OpenAI, Anthropic and Gemini adapters and available as the `__cause__` of the
  `QueryGenerationException` raised by `ask()`.

### Fixed
- Each `ask()` opened 5 new database connections per table in the schema context
  (41 for a multi-table question). The context is now built from the table list
  loaded at `connect()`, with no extra connections.
- `RedshiftRepository.refresh_schema()` was a no-op.
- The Anthropic and Gemini adapters raised `TypeError` instead of
  `TokenLimitException` when the context was too large, and dropped the SDK error
  as the cause of generation failures.
- `docs/API.md` showed catching `TokenLimitException` and `ProviderException`
  directly from `ask()`; they arrive as the cause of `QueryGenerationException`.

## [0.2.0rc16] - 2026-10-19

### Changed
- Release: packages are published to PyPI only from a release tag whose name
  matches the `pyproject.toml` version and that has a published GitHub Release.
  The publish workflows build in one job and upload from another, so only the
  upload job can request a PyPI token.
- CI: runs on `ubuntu-24.04` with the Node 24 versions of `actions/checkout` and
  `actions/setup-python`, and fails when any copy of the package version is out
  of sync with `pyproject.toml`.
- CI: a `clean-install` job installs the built wheel in a fresh environment
  without the lock file, and the integration lane runs the README Quick Start
  and a false-invalid regression set against a local fake of the OpenAI API.

### Fixed
- `import nlp2sql` failed on a plain `pip install nlp2sql` since 0.2.0rc13
  (`No module named 'yaml'`): `pyyaml` is now a declared dependency.
- `connect()` raised `Unknown embedding provider` with
  `ProviderConfig(provider="anthropic")` or `"gemini"`, and with OpenAI failed
  unless `OPENAI_API_KEY` was exported, because the `ProviderConfig` key never
  reached the embedding adapter. Without an explicit embedding provider,
  OpenAI chat now uses OpenAI embeddings with the same key; other providers use
  local embeddings when `nlp2sql[embeddings-local]` is installed and no
  embeddings otherwise. Few-shot examples share that provider, and are skipped
  with a warning when there is none.
- Correct queries came back with `is_valid=False` when they did not use the
  table the heuristic intent plan guessed from the question (4 of 14 in a
  sample of realistic questions), even with no semantic layer. Plan-derived
  expectations are now warnings; rules from a semantic layer are still errors.
- `is_valid` was `True` for queries that write (`DELETE ...` in the default
  `generate_only` mode) and for queries whose execution failed. Both are now
  invalid, with the reason in the validation errors.
- The read-only check rejected valid queries with keywords inside string
  literals (`WHERE name = 'Gift Set'`), and allowed functions with side effects
  such as `pg_terminate_backend`, `set_config`, `nextval` or `dblink`. It now
  ignores literals and rejects those functions.
- `generate_sql(max_tokens=...)` and the CLI `--max-tokens` (default 1000) also
  capped the schema context sent to the model; the schema budget is now always
  `NLP2SQL_MAX_SCHEMA_TOKENS`.
- `nlp2sql setup` crashed when configuring a database (it called the
  nonexistent `click.choice`), and offered MySQL and SQLite, which have no
  adapter. It now offers PostgreSQL and Redshift.

## [0.2.0rc15] - 2026-09-18

### Changed
- Default chat models refreshed to current, non-retired IDs. **User-visible: cost,
  latency and SQL style change for anyone who does not pin `model`.**
  - OpenAI: `gpt-4o-mini` -> `gpt-5.6-luna` (1.05M context, 922K input, 128K output).
    `gpt-4o-mini` remains callable; pin it with `ProviderConfig(model="gpt-4o-mini")`.
  - Anthropic: `claude-sonnet-4-20250514` (retired by Anthropic on 2026-06-15) ->
    `claude-sonnet-5` (1M context, 128K output).
  - Gemini: `gemini-2.0-flash` (shut down by Google on 2026-06-01) ->
    `gemini-3.6-flash` (1,048,576 context, 65,536 output).
- `ProviderConfig.DEFAULT_MODELS` is now the single source of truth for provider
  defaults; the adapters, `Settings.get_provider_config()` and `nlp2sql providers list`
  read from it.
- `AnthropicAdapter` no longer sends `temperature` to the Messages API: Claude 4.7+
  models reject non-default sampling parameters (HTTP 400) and the `anthropic` SDK
  removes the keyword in 1.0. `ProviderConfig(temperature=...)` is still accepted for
  Anthropic but ignored (logged at INFO); explicitly pinned older Claude models now run
  at the API default temperature.
- `OpenAIAdapter` sends `max_completion_tokens` instead of the deprecated `max_tokens`.
  For reasoning models (every model outside the `gpt-3.5`, `gpt-4` and `chatgpt-4o`
  families, including `gpt-5.6-*`) it sets `reasoning_effort` (default `low`, new
  `reasoning_effort` constructor argument) and omits `temperature`; `gpt-4o`/`gpt-4.1`
  keep receiving `temperature`. Response metadata gains `reasoning_effort` and
  `reasoning_tokens`.
- Unknown model IDs no longer fall back to crippling context limits (OpenAI 8,192,
  Gemini 30,720, Anthropic 100,000). They resolve by model family where possible and
  otherwise fall back to 128,000 / 1,048,576 (Gemini family) / 200,000, logging a
  warning when the adapter is constructed.
- `OpenAIAdapter` token counting maps the `gpt-5`, `gpt-4.1`, `gpt-4o` and `o1`-`o4`
  families to `o200k_base` (tiktoken has no entry for `gpt-5.6-*`) and falls back to
  `o200k_base`, never `cl100k_base`, for unknown IDs.
- `GeminiAdapter` reads token usage from `usage_metadata` instead of issuing extra
  `count_tokens` calls after each response.
- Minimum dependency versions raised: `openai>=1.58.0` (`reasoning_effort`),
  `tiktoken>=0.7.0` (`o200k_base`), `google-generativeai>=0.8.5` (`usage_metadata`).

### Fixed
- `connect()` / `ask()` failed out of the box for Anthropic and Gemini because their
  default model IDs had been retired by the providers.
- Reasoning/thinking models that exhaust `max_tokens` before emitting content now raise
  an actionable `ProviderException` instead of "Invalid JSON response" or
  "Failed to parse response".
- `AnthropicAdapter` and `GeminiAdapter` re-raise `ProviderException` after exhausting
  retries instead of surfacing `tenacity.RetryError`.

## [0.2.0rc14] - 2026-09-16

### Added
- `PgvectorExampleRepository`: a Postgres + `pgvector` implementation of
  `ExampleRepositoryPort`, an alternative to the on-disk FAISS `ExampleStore`
  for storing and semantically searching few-shot examples. Stores examples in
  a single table with a `namespace` column (per-database isolation via
  `md5(database_url:schema_name)`, byte-identical to `ExampleStore`), cosine
  distance search over an HNSW index, and idempotent `auto_migrate` DDL.
- Optional `pgvector` extra: `pip install 'nlp2sql[pgvector]'`.
- CI: a `pgvector-integration` job that runs the adapter's integration tests
  against a `pgvector/pgvector:pg16` service. The job fails (rather than skips)
  when the database or `vector` extension is unavailable
  (`NLP2SQL_REQUIRE_INTEGRATION`).

### Changed
- `docker/docker-compose.yml`: the `postgres` service image is now
  `pgvector/pgvector:pg16` (drop-in replacement for `postgres:16`, adds the
  `vector` extension) so integration tests run out of the box.
