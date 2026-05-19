"""Runtime budget controls for hub team mode."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock

from react_agent_system.config import AgentSystemConfig
from react_agent_system.hub.models import RuntimeStatus


@dataclass
class BudgetSnapshot:
    can_spend: bool
    reason: str = ""


class BudgetController:
    """Tracks message, token, cost, and pause controls at runtime."""

    def __init__(self, config: AgentSystemConfig) -> None:
        self._lock = Lock()
        self.paused = False
        self.messages_sent = 0
        self.max_messages = config.hub_max_messages
        self.estimated_input_tokens = 0
        self.estimated_output_tokens = 0
        self.max_input_tokens = config.hub_max_input_tokens
        self.max_output_tokens = config.hub_max_output_tokens
        self.estimated_cost = 0.0
        self.max_cost = config.hub_max_cost
        self.input_cost_per_million = config.hub_input_token_cost_per_million
        self.output_cost_per_million = config.hub_output_token_cost_per_million
        self.poll_interval_seconds = config.hub_poll_interval_seconds

    def check(self) -> BudgetSnapshot:
        with self._lock:
            if self.paused:
                return BudgetSnapshot(False, "hub loop is paused")
            if self.messages_sent >= self.max_messages:
                return BudgetSnapshot(False, "message cap reached")
            if self.estimated_input_tokens >= self.max_input_tokens:
                return BudgetSnapshot(False, "input token budget reached")
            if self.estimated_output_tokens >= self.max_output_tokens:
                return BudgetSnapshot(False, "output token budget reached")
            if self.max_cost is not None and self.estimated_cost >= self.max_cost:
                return BudgetSnapshot(False, "cost budget reached")
            return BudgetSnapshot(True)

    def record_input_text(self, text: str) -> None:
        self.record_tokens(input_tokens=estimate_tokens(text), output_tokens=0)

    def record_output_text(self, text: str, posted: bool) -> None:
        self.record_tokens(input_tokens=0, output_tokens=estimate_tokens(text))
        if posted:
            with self._lock:
                self.messages_sent += 1

    def record_tokens(self, input_tokens: int, output_tokens: int) -> None:
        with self._lock:
            self.estimated_input_tokens += max(0, input_tokens)
            self.estimated_output_tokens += max(0, output_tokens)
            self.estimated_cost += (
                input_tokens * self.input_cost_per_million
                + output_tokens * self.output_cost_per_million
            ) / 1_000_000

    def set_paused(self, paused: bool) -> None:
        with self._lock:
            self.paused = paused

    def set_token_budget(
        self,
        max_input_tokens: int | None = None,
        max_output_tokens: int | None = None,
    ) -> None:
        with self._lock:
            if max_input_tokens is not None:
                self.max_input_tokens = max_input_tokens
            if max_output_tokens is not None:
                self.max_output_tokens = max_output_tokens

    def set_cost_budget(self, max_cost: float | None) -> None:
        with self._lock:
            self.max_cost = max_cost

    def set_message_cap(self, max_messages: int) -> None:
        with self._lock:
            self.max_messages = max_messages

    def set_poll_interval(self, seconds: float) -> None:
        with self._lock:
            self.poll_interval_seconds = max(1.0, seconds)

    def status(self) -> RuntimeStatus:
        with self._lock:
            return RuntimeStatus(
                paused=self.paused,
                messages_sent=self.messages_sent,
                max_messages=self.max_messages,
                estimated_input_tokens=self.estimated_input_tokens,
                estimated_output_tokens=self.estimated_output_tokens,
                max_input_tokens=self.max_input_tokens,
                max_output_tokens=self.max_output_tokens,
                estimated_cost=self.estimated_cost,
                max_cost=self.max_cost,
                poll_interval_seconds=self.poll_interval_seconds,
            )


def estimate_tokens(text: str) -> int:
    """Conservative fallback token estimate when provider usage is unavailable."""

    return max(1, (len(text) + 3) // 4) if text else 0
