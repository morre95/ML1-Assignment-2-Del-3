"""Proactive state-machine assessor for hub team mode."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from react_agent_system.config import AgentSystemConfig
from react_agent_system.hub.assessment import _strip_json_fence, format_hub_context
from react_agent_system.hub.models import HubMessage, HubPhase, PhaseDecision
from react_agent_system.prompts import PromptLibrary


class HubStateAssessor:
    """Reads the full chat and decides which phase the agent should enter."""

    def __init__(self, config: AgentSystemConfig, model: Any) -> None:
        self.config = config
        self.model = model
        self.prompt_library = PromptLibrary(config)

    def assess(
        self,
        messages: list[HubMessage],
        *,
        is_manager: bool = False,
        allow_plan_fallback: bool = False,
    ) -> PhaseDecision:
        context = format_hub_context(messages, len(messages))
        prompt = self.prompt_library.render(
            "hub_state_assessor",
            agent_name=self.config.hub_agent_name,
            agent_role=self.config.hub_agent_role,
            is_manager=is_manager,
            allow_plan_fallback=allow_plan_fallback,
        )
        response = self.model.invoke(
            [
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": (
                        f"Group chat context:\n{context}\n\n"
                        "Determine the current phase and return the assessment JSON now."
                    ),
                },
            ]
        )
        content = getattr(response, "content", response)
        if not isinstance(content, str):
            content = str(content)
        return parse_phase_decision(content)


def parse_phase_decision(content: str) -> PhaseDecision:
    """Parse model JSON, failing closed to stay_silent."""

    try:
        raw = json.loads(_strip_json_fence(content))
        return PhaseDecision.model_validate(raw)
    except (json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
        preview = content[:300].replace("\n", " ")
        print(f"  phase parse failed ({type(exc).__name__}): {preview}")
        return PhaseDecision(
            phase=HubPhase.STAY_SILENT,
            reason="phase assessment output was not valid JSON",
        )
