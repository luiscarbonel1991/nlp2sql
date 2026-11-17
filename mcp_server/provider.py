"""Which AI provider the MCP server uses, read from the environment.

Kept apart from server.py so that it can be imported, and tested, without the MCP SDK.
"""

import logging
import os

from nlp2sql import ProviderConfig

logger = logging.getLogger(__name__)

# An OpenAI-compatible server (Ollama, vLLM, a gateway): its address, the model to ask
# for, and its key if it has one
LLM_BASE_URL_ENV = "NLP2SQL_LLM_BASE_URL"
LLM_MODEL_ENV = "NLP2SQL_LLM_MODEL"
LLM_API_KEY_ENV = "NLP2SQL_LLM_API_KEY"

ENDPOINT_LABEL = "openai-compatible"


def endpoint_config() -> ProviderConfig | None:
    """The OpenAI-compatible endpoint the environment points at, if any.

    Only ``NLP2SQL_LLM_API_KEY`` is sent to that server: ``OPENAI_API_KEY`` is for OpenAI.
    """
    base_url = os.getenv(LLM_BASE_URL_ENV)
    if not base_url:
        ignored = [name for name in (LLM_MODEL_ENV, LLM_API_KEY_ENV) if os.getenv(name)]
        if ignored:
            logger.warning("%s ignored: they are only read with %s", ", ".join(ignored), LLM_BASE_URL_ENV)
        return None
    return ProviderConfig(
        provider="openai",
        base_url=base_url,
        model=os.getenv(LLM_MODEL_ENV) or None,
        api_key=os.getenv(LLM_API_KEY_ENV) or None,
    )


def provider_config(provider: str | None = None) -> ProviderConfig:
    """The provider of a query service.

    A named provider uses its API key from the environment. Otherwise the endpoint of
    ``NLP2SQL_LLM_BASE_URL`` when it is set, else the first provider with an API key.

    Raises:
        ValueError: If the named provider has no API key, or nothing is configured.
    """
    env_vars = ProviderConfig.API_KEY_ENV_VARS
    if provider:
        api_key = os.getenv(env_vars.get(provider, ""))
        if not api_key:
            raise ValueError(f"API key not configured for provider '{provider}'")
        return ProviderConfig(provider=provider, api_key=api_key)

    endpoint = endpoint_config()
    if endpoint is not None:
        return endpoint
    for name, env_var in env_vars.items():
        api_key = os.getenv(env_var)
        if api_key:
            return ProviderConfig(provider=name, api_key=api_key)
    raise ValueError(
        f"No AI provider configured. Set one of: {', '.join(env_vars.values())}, "
        f"or {LLM_BASE_URL_ENV} for an OpenAI-compatible server"
    )


def provider_label(config: ProviderConfig) -> str:
    """A name for logs and cache metadata. It never holds the endpoint's address or key."""
    return ENDPOINT_LABEL if config.base_url else config.provider


def service_cache_key(database_url: str, config: ProviderConfig, schema_name: str) -> str:
    """One cached service per database, provider (or endpoint and model) and schema."""
    target = f"{config.base_url}:{config.resolved_model}" if config.base_url else config.provider
    return f"service:{database_url}:{target}:{schema_name}"
