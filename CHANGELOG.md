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
