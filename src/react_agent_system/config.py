"""Configuration loading for the ReAct agent system."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv

DEFAULT_PROMPTS = {
    "planner": "agents/planner.j2",
    "coder": "agents/coder.j2",
    "reviewer": "agents/reviewer.j2",
    "tester": "agents/tester.j2",
    "debugger": "agents/debugger.j2",
    "repo_tool": "agents/repo_tool.j2",
    "summary_writer": "agents/summary_writer.j2",
    "code_writer": "agents/code_writer.j2",
    "supervisor": "agents/supervisor.j2",
    "hub_assessor": "agents/hub_assessor.j2",
    "hub_participant": "agents/hub_participant.j2",
}


@dataclass(frozen=True)
class AgentSystemConfig:
    """Runtime settings that can come from YAML and environment variables."""

    workspace: Path
    prompt_dir: Path
    session_db: Path
    model: str
    openrouter_api_key: str | None
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    http_referer: str = "http://localhost"
    app_title: str = "ReAct Agent System"
    recursion_limit: int = 40
    command_timeout_seconds: int = 30
    web_search_max_results: int = 5
    require_bash_approval: bool = True
    hub_url: str = "https://wb48jtfnjng6on-8080.proxy.runpod.net"
    hub_password: str | None = None
    hub_agent_name: str = "cryptofarian-builder"
    hub_agent_role: str = "You are a concise software-building agent in a group chat."
    hub_poll_interval_seconds: float = 4.0
    hub_request_interval_seconds: float = 1.0
    hub_max_messages: int = 10
    hub_max_message_chars: int = 4096
    hub_context_messages: int = 20
    hub_max_input_tokens: int = 30_000
    hub_max_output_tokens: int = 8_000
    hub_max_cost: float | None = None
    hub_input_token_cost_per_million: float = 0.0
    hub_output_token_cost_per_million: float = 0.0
    prompts: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_PROMPTS))


def load_config(
    config_path: Path | None = None,
    workspace: Path | None = None,
) -> AgentSystemConfig:
    """Load configuration from `.env`, optional YAML, and environment overrides."""

    root = (workspace or Path.cwd()).resolve()
    # Mounted .env must win over empty defaults injected by Docker Compose.
    load_dotenv(root / ".env", override=True)
    raw = _read_yaml(config_path) if config_path else {}

    prompt_dir = _path_from_config(raw, "prompt_dir", root / "prompts", root)
    session_db = _path_from_config(
        raw,
        "session_db",
        Path(os.getenv("REACT_AGENT_SESSION_DB", "sessions/agent-history.sqlite3")),
        root,
    )

    return AgentSystemConfig(
        workspace=root,
        prompt_dir=prompt_dir,
        session_db=session_db,
        model=os.getenv("REACT_AGENT_MODEL", str(raw.get("model", "openai/gpt-5.2"))),
        openrouter_api_key=os.getenv("OPENROUTER_API_KEY") or raw.get("openrouter_api_key"),
        openrouter_base_url=str(
            raw.get("openrouter_base_url", "https://openrouter.ai/api/v1")
        ),
        http_referer=os.getenv(
            "REACT_AGENT_HTTP_REFERER", str(raw.get("http_referer", "http://localhost"))
        ),
        app_title=os.getenv(
            "REACT_AGENT_APP_TITLE", str(raw.get("app_title", "ReAct Agent System"))
        ),
        recursion_limit=int(raw.get("recursion_limit", 40)),
        command_timeout_seconds=int(raw.get("command_timeout_seconds", 30)),
        web_search_max_results=int(raw.get("web_search_max_results", 5)),
        require_bash_approval=_bool_from_config(raw.get("require_bash_approval", True)),
        hub_url=os.getenv(
            "REACT_AGENT_HUB_URL",
            str(raw.get("hub_url", "https://wb48jtfnjng6on-8080.proxy.runpod.net")),
        ),
        hub_password=os.getenv("REACT_AGENT_HUB_PASSWORD") or raw.get("hub_password"),
        hub_agent_name=os.getenv(
            "REACT_AGENT_HUB_AGENT_NAME", str(raw.get("hub_agent_name", "cryptofarian-builder"))
        ),
        hub_agent_role=os.getenv(
            "REACT_AGENT_HUB_AGENT_ROLE",
            str(
                raw.get(
                    "hub_agent_role",
                    "You are a concise software-building agent in a group chat.",
                )
            ),
        ),
        hub_poll_interval_seconds=float(raw.get("hub_poll_interval_seconds", 4.0)),
        hub_request_interval_seconds=float(raw.get("hub_request_interval_seconds", 1.0)),
        hub_max_messages=int(raw.get("hub_max_messages", 10)),
        hub_max_message_chars=int(raw.get("hub_max_message_chars", 4096)),
        hub_context_messages=int(raw.get("hub_context_messages", 20)),
        hub_max_input_tokens=int(raw.get("hub_max_input_tokens", 30_000)),
        hub_max_output_tokens=int(raw.get("hub_max_output_tokens", 8_000)),
        hub_max_cost=_optional_float(raw.get("hub_max_cost")),
        hub_input_token_cost_per_million=float(
            raw.get("hub_input_token_cost_per_million", 0.0)
        ),
        hub_output_token_cost_per_million=float(
            raw.get("hub_output_token_cost_per_million", 0.0)
        ),
        prompts={**DEFAULT_PROMPTS, **dict(raw.get("prompts", {}))},
    )


def _read_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file does not exist: {path}")
    with path.open(encoding="utf-8") as file:
        data = yaml.safe_load(file) or {}
    if not isinstance(data, dict):
        raise ValueError("Config file must contain a YAML mapping at the top level.")
    return data


def _path_from_config(raw: dict[str, Any], key: str, default: Path, root: Path) -> Path:
    value = Path(raw.get(key, default))
    if not value.is_absolute():
        value = root / value
    return value.resolve()


def _optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _bool_from_config(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
