"""Jinja2 prompt rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

from react_agent_system.config import AgentSystemConfig


@dataclass(frozen=True)
class PromptLibrary:
    """Loads configured agent prompts from the prompt directory."""

    config: AgentSystemConfig

    def __post_init__(self) -> None:
        environment = Environment(
            loader=FileSystemLoader(self.config.prompt_dir),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
            undefined=StrictUndefined,
        )
        object.__setattr__(self, "_environment", environment)

    def render(self, prompt_name: str, **context: Any) -> str:
        template_path = self.config.prompts[prompt_name]
        try:
            template = self._environment.get_template(template_path)
        except TemplateNotFound as exc:
            raise FileNotFoundError(f"Prompt template not found: {template_path}") from exc

        return template.render(
            app_title=self.config.app_title,
            workspace=str(self.config.workspace),
            **context,
        ).strip()
