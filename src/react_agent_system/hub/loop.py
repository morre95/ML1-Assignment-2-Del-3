"""Long-running RunPod hub participation loop."""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from react_agent_system.agents import AgentSystem, build_agent_system
from react_agent_system.bash_safety import ApprovalCallback, assess_command
from react_agent_system.config import AgentSystemConfig
from react_agent_system.hub.assessment import HubAssessor, format_hub_context
from react_agent_system.hub.budget import BudgetController
from react_agent_system.hub.client import (
    HubAuthenticationError,
    HubClientError,
    HubRateLimitError,
    RunPodHubClient,
)
from react_agent_system.hub.console import ConsoleController
from react_agent_system.hub.models import AssessmentAction, AssessmentDecision, HubMessage
from react_agent_system.hub.rate_limit import RateLimiter
from react_agent_system.llm import build_chat_model
from react_agent_system.prompts import PromptLibrary


@dataclass
class HubLoop:
    """Polls the hub, assesses messages, and posts only approved actions."""

    config: AgentSystemConfig
    client: RunPodHubClient
    assessor: HubAssessor
    agent_system: AgentSystem
    budget: BudgetController
    console: ConsoleController | None = None
    last_seen: int = 0
    message_history: list[HubMessage] = field(default_factory=list)
    agent_thread_id: str | None = None

    def run_forever(self, max_iterations: int | None = None) -> None:
        iterations = 0
        while self.console is None or not self.console.should_quit:
            outcome = self.run_once()
            if outcome:
                print(outcome)
            iterations += 1
            if max_iterations is not None and iterations >= max_iterations:
                return
            time.sleep(self.budget.status().poll_interval_seconds)

    def run_once(self) -> str:
        try:
            response = self.client.fetch_messages(self.last_seen)
        except HubAuthenticationError as exc:
            if self.console is not None:
                self.console.should_quit = True
            return f"hub authentication failed: {exc}"
        except HubRateLimitError as exc:
            return f"hub rate limit: {exc}"
        except HubClientError as exc:
            return f"hub request failed: {exc}"

        if not response.messages:
            return ""

        messages = sorted(response.messages, key=lambda message: message.seq)
        self._remember_messages(messages)
        self.last_seen = max(message.seq for message in messages)
        new_messages = [
            message
            for message in messages
            if message.agent_name != self.config.hub_agent_name
        ]
        if not new_messages:
            return ""

        trigger_messages = [
            message
            for message in new_messages
            if is_addressed_to_agent(message.content, self.config.hub_agent_name)
            or self._is_reply_to_pending_question(message)
        ]
        if not trigger_messages:
            return f"gate: no message explicitly addressed to {self.config.hub_agent_name}"

        blocked_command_response = self._blocked_command_response(trigger_messages[-1])
        if blocked_command_response is not None:
            return self._post(blocked_command_response)

        context_messages = self._recent_messages()
        context = format_hub_context(context_messages, self.config.hub_context_messages)
        self.budget.record_input_text(context)
        budget = self.budget.check()
        if not budget.can_spend:
            return f"budget gate: {budget.reason}"

        decision = self.assessor.assess(context_messages, trigger_messages[-1])
        self.budget.record_output_text(decision.model_dump_json(), posted=False)
        return self._handle_decision(decision, context_messages)

    def _handle_decision(self, decision: AssessmentDecision, messages: list[HubMessage]) -> str:
        match decision.action:
            case AssessmentAction.STAY_SILENT:
                return f"assessment: stay_silent ({decision.reason})"
            case AssessmentAction.LOW_BID:
                return self._post(decision.response_hint or "I can help if this needs coding work.")
            case AssessmentAction.ASK_CLARIFICATION:
                return self._post(
                    decision.response_hint or "What detail should I clarify before acting?"
                )
            case AssessmentAction.ESCALATE:
                target = decision.target_agent or "a better-suited specialist"
                hint = decision.response_hint or f"This should be handled by {target}."
                return self._post(hint)
            case AssessmentAction.RESPOND:
                return self._respond(messages, decision)

    def _respond(self, messages: list[HubMessage], decision: AssessmentDecision) -> str:
        budget = self.budget.check()
        if not budget.can_spend:
            return f"budget gate: {budget.reason}"

        prompt = PromptLibrary(self.config).render(
            "hub_participant",
            agent_name=self.config.hub_agent_name,
            agent_role=self.config.hub_agent_role,
        )
        context = format_hub_context(messages, self.config.hub_context_messages)
        task = (
            f"{prompt}\n\n"
            f"Internal assessment reason: {decision.reason}\n"
            f"Suggested response focus: {decision.response_hint}\n\n"
            f"Group chat context:\n{context}"
        )
        self.budget.record_input_text(task)
        try:
            reply = self.agent_system.invoke(task, thread_id=self._agent_thread_id())
        except ValueError as exc:
            if not _is_invalid_tool_history_error(exc):
                raise
            self.agent_thread_id = f"hub-{self.config.hub_agent_name}-recovered-{self.last_seen}"
            reply = self.agent_system.invoke(task, thread_id=self.agent_thread_id)
        return self._post(reply)

    def _post(self, content: str) -> str:
        budget = self.budget.check()
        if not budget.can_spend:
            return f"budget gate: {budget.reason}"

        trimmed = content.strip()[: self.config.hub_max_message_chars]
        if not trimmed:
            return "skipped empty outbound message"

        try:
            response = self.client.post_message(self.config.hub_agent_name, trimmed)
        except HubRateLimitError as exc:
            return f"hub rate limit while posting: {exc}"
        except HubClientError as exc:
            return f"hub post failed: {exc}"

        self._remember_messages(
            [HubMessage(seq=response.seq, agent_name=self.config.hub_agent_name, content=trimmed)]
        )
        self.budget.record_output_text(trimmed, posted=True)
        return f"posted seq={response.seq}: {trimmed[:120]}"

    def _remember_messages(self, messages: list[HubMessage]) -> None:
        by_seq = {message.seq: message for message in self.message_history}
        by_seq.update({message.seq: message for message in messages})
        history_limit = max(self.config.hub_context_messages * 4, 100)
        self.message_history = sorted(by_seq.values(), key=lambda message: message.seq)[
            -history_limit:
        ]

    def _recent_messages(self) -> list[HubMessage]:
        return self.message_history[-self.config.hub_context_messages :]

    def _is_reply_to_pending_question(self, message: HubMessage) -> bool:
        previous_messages = [
            history_message
            for history_message in self.message_history
            if history_message.seq < message.seq
        ]
        if not previous_messages:
            return False

        previous_message = previous_messages[-1]
        return (
            previous_message.agent_name == self.config.hub_agent_name
            and "?" in previous_message.content
        )

    def _blocked_command_response(self, message: HubMessage) -> str | None:
        if not _looks_like_shell_run_request(message.content):
            return None

        decision = assess_command(message.content, self.config.workspace)
        if decision.allowed:
            return None
        return (
            "I can't run that command because it is blocked by the command safety policy. "
            f"Reason: {decision.reason}"
        )
    

    def _agent_thread_id(self) -> str:
        if self.agent_thread_id is None:
            self.agent_thread_id = f"hub-{self.config.hub_agent_name}"
        return self.agent_thread_id


def build_hub_loop(
    config: AgentSystemConfig,
    approval_callback: ApprovalCallback | None = None,
    model: Any | None = None,
) -> HubLoop:
    """Build a hub loop with real clients and the existing ReAct agent system."""

    if not config.hub_password:
        raise ValueError("REACT_AGENT_HUB_PASSWORD is required for hub mode.")

    chat_model = model or build_chat_model(config)
    budget = BudgetController(config)
    rate_limiter = RateLimiter(config.hub_request_interval_seconds)
    client = RunPodHubClient(
        base_url=config.hub_url,
        password=config.hub_password,
        rate_limiter=rate_limiter,
    )
    assessor = HubAssessor(config, chat_model)
    agent_system = build_agent_system(
        config=config,
        approval_callback=approval_callback,
        model=chat_model,
    )
    console = ConsoleController(
        budget,
        stats_callback=lambda: client.fetch_stats().model_dump_json(),
    )
    return HubLoop(
        config=config,
        client=client,
        assessor=assessor,
        agent_system=agent_system,
        budget=budget,
        console=console,
    )


def is_addressed_to_agent(content: str, agent_name: str) -> bool:
    """Return true only when a message explicitly names this agent."""

    normalized_agent_name = _normalize_address_text(agent_name.strip())
    if not normalized_agent_name:
        return False

    normalized_content = _normalize_address_text(content)
    escaped_agent_name = re.escape(normalized_agent_name)
    name_boundary = r"(?![\w-])"
    if _is_distinct_agent_name(normalized_agent_name):
        return bool(
            re.search(
                rf"(^|[^\w-]){escaped_agent_name}{name_boundary}",
                normalized_content,
            )
        )

    patterns = [
        rf"(^|\s)@{escaped_agent_name}{name_boundary}",
        rf"(^|\s){escaped_agent_name}{name_boundary}\s*[:,]",
        rf"(^|\n)\s*{escaped_agent_name}{name_boundary}\s+\S+",
        rf"\b(can|could|would|will)\s+{escaped_agent_name}{name_boundary}\s+\S+",
        rf"\bhey\s+{escaped_agent_name}{name_boundary}",
        rf"\bhi\s+{escaped_agent_name}{name_boundary}",
    ]
    return any(re.search(pattern, normalized_content) for pattern in patterns)


def _normalize_address_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_diacritics = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return without_diacritics.casefold()


def _is_distinct_agent_name(normalized_agent_name: str) -> bool:
    return "-" in normalized_agent_name or len(normalized_agent_name) >= 8


def _looks_like_shell_run_request(content: str) -> bool:
    normalized = _normalize_address_text(content)
    return bool(re.search(r"\b(run|execute|bash|shell|command)\b", normalized))


def _is_invalid_tool_history_error(exc: ValueError) -> bool:
    message = str(exc)
    return "tool_calls" in message and "ToolMessage" in message
