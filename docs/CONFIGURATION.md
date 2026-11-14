# Configuration Reference

This document explains how to configure `nlp2sql` for the DSL, CLI, tests, and production services.

## Core Concepts

Configuration falls into four buckets:

- provider credentials
- database and schema scope
- retrieval and cache behavior
- runtime guidance for semantic context, examples, and execution modes

## Environment Variables

### Provider Credentials

At least one provider key is required, unless the model is served by another [OpenAI-compatible endpoint](#openai-compatible-endpoints).

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | OpenAI provider key |
| `ANTHROPIC_API_KEY` | Anthropic provider key |
| `GOOGLE_API_KEY` | Gemini provider key |

```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
export GOOGLE_API_KEY="AI..."
```

### Database Connection

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | Default connection URL used by scripts or tools |

Supported formats:

```bash
export DATABASE_URL="postgresql://testuser:testpass@localhost:5432/testdb"
export DATABASE_URL="redshift://user:pass@cluster.region.redshift.amazonaws.com:5439/analytics"
```

### Retrieval and Cache Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `NLP2SQL_MAX_SCHEMA_TOKENS` | `8000` | Maximum schema tokens sent to the model |
| `NLP2SQL_SCHEMA_CACHE_TTL_HOURS` | `24` | Refresh window for schema caches |
| `NLP2SQL_EMBEDDINGS_DIR` | `./embeddings` | Disk location for schema indexes and table caches (`/tmp/nlp2sql_embeddings` if the working directory is read-only) |
| `NLP2SQL_EXAMPLES_DIR` | `./examples_index` | Disk location for example indexes (`/tmp/nlp2sql_examples` if the working directory is read-only) |
| `NLP2SQL_EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Default local embedding model |
| `NLP2SQL_EMBEDDING_PROVIDER` | `local` | Default embedding provider |

```bash
export NLP2SQL_MAX_SCHEMA_TOKENS=8000
export NLP2SQL_SCHEMA_CACHE_TTL_HOURS=24
export NLP2SQL_EMBEDDINGS_DIR=/data/nlp2sql/embeddings
export NLP2SQL_EXAMPLES_DIR=/data/nlp2sql/examples
export NLP2SQL_EMBEDDING_MODEL=all-MiniLM-L6-v2
export NLP2SQL_EMBEDDING_PROVIDER=local
```

### Practical Notes

- `NLP2SQL_MAX_SCHEMA_TOKENS` controls how much schema detail can fit into the prompt after retrieval and compression.
- `NLP2SQL_SCHEMA_CACHE_TTL_HOURS` affects when schema metadata and indexes are refreshed from the database.
- `NLP2SQL_EMBEDDINGS_DIR` and `NLP2SQL_EXAMPLES_DIR` should point to persistent writable storage in long-lived deployments.
- changing the embedding provider or model for an existing cache usually requires `nlp2sql cache clear --embeddings`

### General Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `NLP2SQL_LLM_VALIDATION` | `false` | Also ask the LLM to review each generated query (a second call per question) |
| `NLP2SQL_LOG_LEVEL` | `WARNING` in the CLI | Level of the CLI logs, written to stderr. The library itself never configures logging: applications set the level of the `nlp2sql` logger |
| `NLP2SQL_CACHE_ENABLED` | `true` | Enable or disable query-result caching |
| `NLP2SQL_ENV` | unset | Optional environment label |
| `TOKENIZERS_PARALLELISM` | unset | Set to `false` to reduce tokenizer warnings |

## OpenAI-Compatible Endpoints

The OpenAI provider can use any server that speaks OpenAI's Chat Completions API, such as Ollama, vLLM, LiteLLM or another gateway. Pass the server's address as `base_url`:

```python
import nlp2sql
from nlp2sql import ProviderConfig

nlp = await nlp2sql.connect(
    database_url,
    provider=ProviderConfig(
        provider="openai",
        base_url="http://localhost:11434/v1",  # a local Ollama
        model="llama3.2",
    ),
)
```

If the server needs a key, pass it as `api_key`. `base_url` is only accepted for the `openai` provider.

The notes below were checked against Ollama 0.20.5 with `llama3.2`. Other servers can differ.

### A Ready Client

For anything `ProviderConfig` has no field for, such as timeouts, custom headers or a reasoning model, build the adapter yourself and pass it as the provider:

```python
from openai import OpenAI

import nlp2sql
from nlp2sql import OpenAIAdapter

client = OpenAI(base_url="https://llm-gateway.example.com/v1", api_key=gateway_key, timeout=120)
nlp = await nlp2sql.connect(database_url, provider=OpenAIAdapter(client=client, model="my-model"))
```

`client` is the SDK's synchronous client, `openai.OpenAI`. An `AsyncOpenAI` client is rejected, because the adapter runs each request in a worker thread.

`connect()` takes any `AIProviderPort` implementation this way, not only `OpenAIAdapter`.

### What Is Different on Another Endpoint

| Topic | Behavior |
|-------|----------|
| API key | Only the `api_key` passed with `base_url` is sent to that server. `OPENAI_API_KEY` is never sent there. Without a key, the request carries a placeholder, which servers that take no key ignore. |
| Request parameters | OpenAI model names keep the parameters they get on OpenAI. Any other name is treated as an open model and is sent `temperature` and `max_tokens`. For a reasoning model with another name, build `OpenAIAdapter(base_url=..., model=..., reasoning_effort="low")`: it is then sent `reasoning_effort` and `max_completion_tokens`. Ollama rejects `reasoning_effort` for a model without thinking, and ignores `max_completion_tokens`. |
| JSON answers | Requests ask for a JSON object through `response_format`, so the server and the model must support JSON mode. |
| Embeddings | `connect()` does not send that key to OpenAI. It uses local embeddings when `nlp2sql[embeddings-local]` is installed, and no embeddings otherwise. For OpenAI embeddings next to a local chat model, pass `embedding_provider_type="openai"`, which reads `OPENAI_API_KEY`. |
| Token counts | Prompts are measured with an OpenAI tokenizer, and a model the library does not know is assumed to have a 128K context window. For other models both are estimates. |

### Context Size of Local Models

Each question sends up to `NLP2SQL_MAX_SCHEMA_TOKENS` schema tokens (8000 by default), plus the question, the examples and the instructions. The model needs a context window that fits them. If its window is smaller, lower `NLP2SQL_MAX_SCHEMA_TOKENS` or raise the window.

A prompt longer than the window is not an error in Ollama. It drops the beginning of the prompt, where the schema is, and answers from the rest. `ollama ps` shows the window a loaded model has.

Ollama's OpenAI-compatible API has no parameter for the context size. Set it in a `Modelfile`:

```text
FROM llama3.2
PARAMETER num_ctx 16384
```

Create a model from it, in the folder that holds the `Modelfile`, and use that name as `model`:

```bash
ollama create llama3.2-16k
```

### `OPENAI_BASE_URL`

The OpenAI SDK also reads `OPENAI_BASE_URL`. It redirects every OpenAI request, chat and embeddings, and `OPENAI_API_KEY` goes with them. Use it for a proxy in front of OpenAI: for `nlp2sql` that is still OpenAI, so models keep OpenAI's request parameters.

It is not a way to reach a local model. A name that is not an OpenAI model is sent `reasoning_effort`, and Ollama answers `400 ... does not support thinking` for a model without thinking. The CLI and the MCP server build their provider from the environment, so they cannot use such a model yet. Use `base_url` from Python.

## Semantic Context Guidance

Semantic context is not configured by environment variable. It is passed through the API or CLI and should be chosen intentionally per integration.

### Use In-Memory Semantic Context When

- you are integrating `nlp2sql` into an application or service
- the semantic context is assembled from runtime state
- you want the most idiomatic DSL usage

```python
result = await nlp.ask(
    "Show revenue by source category for the flagship store",
    semantic_context=my_semantic_context,
)
```

### Use File-Based Semantic Context When

- you are testing from the CLI
- you want versioned artifacts for experiments
- you need a quick reproducible benchmark setup

```bash
nlp2sql query \
  --database-url "$DATABASE_URL" \
  --question "Show revenue by source category for the flagship store" \
  --semantic-context-file semantic-context.json
```

Both approaches end up producing the same runtime `SemanticContext`.

## Few-Shot Example Guidance

Examples are also a runtime input, not a global environment setting.

### Python

```python
nlp = await nlp2sql.connect(
    database_url,
    provider=provider_config,
    examples=my_examples,
)
```

### CLI

```bash
nlp2sql query \
  --database-url "$DATABASE_URL" \
  --question "Show revenue by source category for the flagship store" \
  --examples-file examples.json
```

### How Examples Are Loaded

When examples are provided:

1. the library normalizes the payload
2. embeddings are created using the configured embedding provider
3. an example index is created or reused on disk
4. relevant examples are selected at query time

Because example indexes are embedding-provider specific, switching between `openai` and `local` without clearing the old index can produce a dimension mismatch.

## Cache Behavior in Tests and Real Usage

### In Tests

Integration tests often isolate cache directories so runs do not interfere with each other. This is especially useful when:

- mixing mock and real embedding providers
- switching between local and OpenAI embeddings
- running tests in parallel

Typical pattern:

```bash
export NLP2SQL_EMBEDDINGS_DIR=/tmp/test-embeddings
export NLP2SQL_EXAMPLES_DIR=/tmp/test-examples
```

### In Services

Use stable persistent directories so schema and example indexes survive restarts:

```bash
export NLP2SQL_EMBEDDINGS_DIR=/var/lib/nlp2sql/embeddings
export NLP2SQL_EXAMPLES_DIR=/var/lib/nlp2sql/examples
```

### In CI

Use disposable cache directories unless you are explicitly testing warm-cache behavior.

## Execution Mode Guidance

The runtime has three practical execution modes.

| Mode | When to use it |
|------|----------------|
| `generate_only` | fast generation, prompt iteration, or no execution port available |
| `generate_and_validate` | safe validation of generated SQL against a readonly execution target |
| `generate_validate_repair` | production-like usage where repair is worth the extra latency |

Every mode checks column names, dialect rules, semantic rules and that the query is read-only,
without extra LLM calls. An additional LLM review of the generated SQL is off by default: it
doubles the latency of each question, and executing the query against the database gives a
stronger signal. Turn it on with `connect(..., llm_validation=True)`,
`NLP2SQL_LLM_VALIDATION=true` or `nlp2sql query --llm-validation`.

A review that cannot be done is not an approval. If the call fails, or the model's answer
cannot be read, the result is not valid, `validation["llm_validation_error"]` says why, and
the question keeps its SQL.

### Python

```python
await nlp.ask("Count active users by region")
await nlp.ask("Count active users by region", validate=True)
await nlp.ask("Count active users by region", validate=True, repair=True)
```

### CLI

```bash
nlp2sql query --database-url "$DATABASE_URL" --question "Count active users by region"
nlp2sql query --database-url "$DATABASE_URL" --question "Count active users by region" --validate
nlp2sql query --database-url "$DATABASE_URL" --question "Count active users by region" --validate --repair
```

### What Changes Between Modes

- `generate_only` returns the first generated SQL
- `generate_and_validate` can surface execution validation metadata
- `generate_validate_repair` can retry after semantic or runtime failures

## Schema Filters

Schema filters reduce retrieval scope before indexing and prompting.

| Filter | Type | Description |
|--------|------|-------------|
| `include_schemas` | `list[str]` | Include only these schemas |
| `exclude_schemas` | `list[str]` | Exclude these schemas |
| `include_tables` | `list[str]` | Include only these tables |
| `exclude_tables` | `list[str]` | Exclude these tables |
| `exclude_system_tables` | `bool` | Exclude system relations |

### Example

```python
schema_filters = {
    "include_tables": ["stores", "marketing_channels", "daily_channel_metrics"],
    "exclude_system_tables": True,
}
```

Filters are applied before indexing, which keeps retrieval focused and lowers token usage.

## Local Public Example Domain

The repository ships a public e-commerce domain for documentation and integration tests.

Start it with:

```bash
cd docker
docker compose up -d postgres
```

Connection URL:

```bash
postgresql://testuser:testpass@localhost:5432/testdb
```

This is the recommended baseline for public experimentation.

## Example Production Baseline

```bash
export NLP2SQL_ENV=production
export NLP2SQL_LOG_LEVEL=INFO
export NLP2SQL_CACHE_ENABLED=true
export NLP2SQL_MAX_SCHEMA_TOKENS=8000
export NLP2SQL_SCHEMA_CACHE_TTL_HOURS=24
export NLP2SQL_EMBEDDINGS_DIR=/data/nlp2sql/embeddings
export NLP2SQL_EXAMPLES_DIR=/data/nlp2sql/examples
export OPENAI_API_KEY="sk-prod-..."
export DATABASE_URL="postgresql://readonly-user:readonly-pass@warehouse-host:5432/analytics"
```

## Related Docs

- [README](../README.md)
- [API Reference](API.md)
- [Architecture](ARCHITECTURE.md)
