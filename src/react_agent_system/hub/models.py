"""Typed models for RunPod hub team mode."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


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


class HubMessagesResponse(BaseModel):
    messages: list[HubMessage] = Field(default_factory=list)


class HubPostResponse(BaseModel):
    status: str
    seq: int


class HubStats(BaseModel):
    per_agent: dict[str, int] = Field(default_factory=dict)
    max_per_agent: int
    max_global: int
    total_messages: int
    agents_capped: list[str] = Field(default_factory=list)


class AssessmentDecision(BaseModel):
    action: AssessmentAction
    reason: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    response_hint: str = ""
    target_agent: str = ""


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
