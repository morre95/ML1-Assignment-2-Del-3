"""OpenRouter-backed chat model construction."""

from __future__ import annotations

from langchain_openai import ChatOpenAI

from react_agent_system.config import AgentSystemConfig


class OpenRouterConfigurationError(RuntimeError):
    """Raised when OpenRouter settings are incomplete."""


def build_chat_model(config: AgentSystemConfig) -> ChatOpenAI:
    """Create a LangChain chat model that talks to OpenRouter."""

    if not config.openrouter_api_key:
        raise OpenRouterConfigurationError(
            "OPENROUTER_API_KEY is required for live agent runs. "
            "Set it in the environment or a local .env file."
        )

    return ChatOpenAI(
        model=config.model,
        api_key=config.openrouter_api_key,
        base_url=config.openrouter_base_url,
        temperature=0,
        default_headers={
            "HTTP-Referer": config.http_referer,
            "X-OpenRouter-Title": config.app_title,
            "X-OpenRouter-Categories": "cli-agent,software-agent",
        },
    )
