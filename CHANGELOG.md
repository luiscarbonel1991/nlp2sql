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
