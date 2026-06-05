"""Typed models for RunPod hub team mode."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _NullTolerantModel(BaseModel):
    """Base model that treats an explicit JSON null as an omitted field.

    The live hub sometimes sends keys with null values (e.g. allowed_agents)
    instead of omitting them; this lets the field default apply instead of
    failing validation.
    """

    model_config = ConfigDict(extra="ignore")

    @model_validator(mode="before")
    @classmethod
    def _drop_null_values(cls, data: Any) -> Any:
        if isinstance(data, dict):
            return {key: value for key, value in data.items() if value is not None}
        return data


class AssessmentAction(StrEnum):
    """Actions allowed after internal message assessment."""

    STAY_SILENT = "stay_silent"
    LOW_BID = "low_bid"
    RESPOND = "respond"
    ASK_CLARIFICATION = "ask_clarification"
    ESCALATE = "escalate"


class HubMessage(BaseModel):
    seq: int
    agent_name: str
    content: str
    timestamp: str | None = None


class HubFileSummary(_NullTolerantModel):
    """Lightweight file listing entry from the shared file store."""

    filename: str
    size: int = 0
    author: str = ""
    updated_at: str = ""


class HubFileContent(_NullTolerantModel):
    """Full content of a single shared file."""

    filename: str
    content: str = ""
    author: str = ""
    updated_at: str = ""


class HubBillboard(_NullTolerantModel):
    """The shared project plan posted by the manager."""

    content: str = ""
    updated_by: str = ""
    updated_at: str = ""


class HubState(_NullTolerantModel):
    """Hub runtime state embedded in the messages response."""

    paused: bool = False
    manager: str = ""
    allowed_agents: dict[str, bool] = Field(default_factory=dict)
    billboard: HubBillboard = Field(default_factory=HubBillboard)
    files: list[HubFileSummary] = Field(default_factory=list)


class HubMessagesResponse(_NullTolerantModel):
    messages: list[HubMessage] = Field(default_factory=list)
    stats: HubState = Field(default_factory=HubState)


class HubFilesResponse(_NullTolerantModel):
    files: list[HubFileSummary] = Field(default_factory=list)


class HubFileUploadResponse(_NullTolerantModel):
    ok: bool = True
    filename: str = ""


class HubPostResponse(_NullTolerantModel):
    seq: int
    status: str | None = None
    ok: bool | None = None
    paused: bool = False
    manager: str = ""
    allowed_agents: dict[str, bool] = Field(default_factory=dict)


class AssessmentDecision(BaseModel):
    action: AssessmentAction
    reason: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    response_hint: str = ""
    target_agent: str = ""

    @field_validator("confidence", mode="before")
    @classmethod
    def normalize_confidence(cls, value: float) -> float:
        if isinstance(value, (int, float)) and value > 1.0:
            return value / 100.0
        return value


class HubPhase(StrEnum):
    """Phases of the proactive hub state machine loop."""

    PROPOSE_PLAN = "propose_plan"
    CLAIM_TASK = "claim_task"
    REVIEW_TASK = "review_task"
    PROPOSE_DONE = "propose_done"
    POST_ROSTER = "post_roster"
    STAY_SILENT = "stay_silent"


class PhaseDecision(BaseModel):
    """Structured output from the state-machine assessor."""

    phase: HubPhase
    reason: str
    main_task: str = ""
    chosen_task: str = ""
    response_hint: str = ""
    manager: str = ""


class RuntimeStatus(BaseModel):
    paused: bool
    messages_sent: int
    max_messages: int
    estimated_input_tokens: int
    estimated_output_tokens: int
    max_input_tokens: int
    max_output_tokens: int
    estimated_cost: float
    max_cost: float | None
    poll_interval_seconds: float
