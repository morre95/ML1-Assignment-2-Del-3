"""Internal relevance assessment before hub responses."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from react_agent_system.config import AgentSystemConfig
from react_agent_system.hub.models import AssessmentAction, AssessmentDecision, HubMessage
from react_agent_system.prompts import PromptLibrary


class HubAssessor:
    """Asks the model for a structured action before the agent responds."""

    def __init__(self, config: AgentSystemConfig, model: Any) -> None:
        self.config = config
        self.model = model
        self.prompt_library = PromptLibrary(config)

    def assess(
        self,
        messages: list[HubMessage],
        trigger_message: HubMessage,
    ) -> AssessmentDecision:
        context = format_hub_context(messages, self.config.hub_context_messages)
        prompt = self.prompt_library.render(
            "hub_assessor",
            agent_name=self.config.hub_agent_name,
            agent_role=self.config.hub_agent_role,
        )
        response = self.model.invoke(
            [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": (
                        f"Group chat context:\n{context}\n\n"
                        "Assess only this explicitly addressed trigger message:\n"
                        f"[seq={trigger_message.seq} agent={trigger_message.agent_name}] "
                        f"{trigger_message.content}\n\n"
                        "Return the assessment JSON now."
                    ),
                },
            ]
        )
        content = getattr(response, "content", response)
        if not isinstance(content, str):
            content = str(content)
        return parse_assessment(content)


def parse_assessment(content: str) -> AssessmentDecision:
    """Parse model JSON, failing closed to stay_silent."""

    try:
        raw = json.loads(_strip_json_fence(content))
        return AssessmentDecision.model_validate(raw)
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError):
        return AssessmentDecision(
            action=AssessmentAction.STAY_SILENT,
            reason="assessment output was not valid JSON",
            confidence=0.0,
        )


def format_hub_context(messages: list[HubMessage], max_messages: int) -> str:
    recent = messages[-max_messages:]
    return "\n".join(
        f"[seq={message.seq} agent={message.agent_name}] {message.content}"
        for message in recent
    )


def _strip_json_fence(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith("```json"):
        stripped = stripped.removeprefix("```json").strip()
    elif stripped.startswith("```"):
        stripped = stripped.removeprefix("```").strip()
    if stripped.endswith("```"):
        stripped = stripped.removesuffix("```").strip()
    return stripped
