"""Long-running RunPod hub participation loop."""

from __future__ import annotations

import re
import time
import unicodedata
import uuid
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
from react_agent_system.hub.models import (
    AssessmentAction,
    AssessmentDecision,
    HubMessage,
    HubPhase,
    PhaseDecision,
)
from react_agent_system.hub.rate_limit import RateLimiter
from react_agent_system.hub.state_machine import HubStateAssessor
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
    state_assessor: HubStateAssessor | None = None
    last_seen: int = 0
    _last_assessed_seq: int = 0
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
            self._interruptible_sleep(self.budget.status().poll_interval_seconds)

    def _interruptible_sleep(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self.console is not None and self.console.should_quit:
                return
            time.sleep(min(0.25, end - time.monotonic()))

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

        if response.messages:
            messages = sorted(response.messages, key=lambda message: message.seq)
            self._remember_messages(messages)
            self.last_seen = max(message.seq for message in messages)
            new_messages = [
                message
                for message in messages
                if message.agent_name != self.config.hub_agent_name
            ]
            for message in new_messages:
                preview = message.content[:100].replace("\n", " ")
                print(f"  inbox seq={message.seq} from={message.agent_name}: {preview}")
        else:
            new_messages = []

        if self.state_assessor is not None:
            if not self.message_history and not new_messages:
                return ""
            return self._run_state_machine()

        if not new_messages:
            return ""
        return self._run_reactive(new_messages)

    def _run_state_machine(self) -> str:
        """Proactive state-machine path: read full chat, identify phase, act."""

        latest_inbound_seq = self._latest_inbound_seq()
        if latest_inbound_seq == self._last_assessed_seq:
            return ""

        context_messages = self._recent_messages()
        context = format_hub_context(context_messages, self.config.hub_context_messages)
        self.budget.record_input_text(context)
        budget = self.budget.check()
        if not budget.can_spend:
            return f"budget gate: {budget.reason}"

        if self._quit_requested():
            return "quit requested, skipping phase assessment"

        print("  assessing phase ...")
        try:
            decision = self.state_assessor.assess(context_messages)
        except Exception as exc:
            return f"phase assessment failed ({type(exc).__name__}): {exc}"
        self._last_assessed_seq = latest_inbound_seq
        self.budget.record_output_text(decision.model_dump_json(), posted=False)
        print(f"  phase: {decision.phase.value} reason={decision.reason}")

        if self._quit_requested():
            return "quit requested, skipping phase action"

        return self._handle_phase(decision, context_messages)

    def _run_reactive(self, new_messages: list[HubMessage]) -> str:
        """Original reactive path: respond only when explicitly addressed."""

        trigger_messages = [
            message
            for message in new_messages
            if is_addressed_to_agent(
                message.content,
                self.config.hub_agent_name,
                self.config.hub_agent_aliases,
            )
            or self._is_reply_to_pending_question(message)
        ]
        if not trigger_messages:
            return f"gate: no message explicitly addressed to {self.config.hub_agent_name}"

        trigger = trigger_messages[-1]
        trigger_preview = trigger.content[:120].replace("\n", " ")
        print(f"  trigger seq={trigger.seq} from={trigger.agent_name}: {trigger_preview}")

        blocked_command_response = self._blocked_command_response(trigger)
        if blocked_command_response is not None:
            return self._post(blocked_command_response)

        context_messages = self._recent_messages()
        context = format_hub_context(context_messages, self.config.hub_context_messages)
        self.budget.record_input_text(context)
        budget = self.budget.check()
        if not budget.can_spend:
            return f"budget gate: {budget.reason}"

        if self._quit_requested():
            return "quit requested, skipping assessment"

        print("  assessing relevance ...")
        try:
            decision = self.assessor.assess(context_messages, trigger)
        except Exception as exc:
            return f"assessment failed ({type(exc).__name__}): {exc}"
        self.budget.record_output_text(decision.model_dump_json(), posted=False)
        print(f"  assessment: action={decision.action.value} reason={decision.reason}")

        if self._quit_requested():
            return "quit requested, skipping response"

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

    def _handle_phase(self, decision: PhaseDecision, messages: list[HubMessage]) -> str:
        match decision.phase:
            case HubPhase.STAY_SILENT:
                return f"phase: stay_silent ({decision.reason})"
            case HubPhase.PROPOSE_PLAN:
                return self._phase_respond(
                    messages,
                    decision,
                    "Propose a structured plan that breaks the main task into small, "
                    "independent subtasks that agents can claim individually.",
                )
            case HubPhase.CLAIM_TASK:
                return self._phase_respond(
                    messages,
                    decision,
                    f"Claim and solve the following task: {decision.chosen_task}",
                )
            case HubPhase.REVIEW_TASK:
                return self._phase_respond(
                    messages,
                    decision,
                    "Review a completed task for correctness, gaps, or bugs.",
                )
            case HubPhase.PROPOSE_DONE:
                return self._phase_respond(
                    messages,
                    decision,
                    "All tasks are done. Propose the final integrated solution and "
                    "mark it with DONE.",
                )

    def _phase_respond(
        self,
        messages: list[HubMessage],
        decision: PhaseDecision,
        instruction: str,
    ) -> str:
        budget = self.budget.check()
        if not budget.can_spend:
            return f"budget gate: {budget.reason}"

        prompt = PromptLibrary(self.config).render(
            "hub_participant",
            agent_name=self.config.hub_agent_name,
            agent_role=self.config.hub_agent_role,
            hub_max_message_chars=self.config.hub_max_message_chars,
        )
        context = format_hub_context(messages, self.config.hub_context_messages)
        task = (
            f"{prompt}\n\n"
            f"Phase: {decision.phase.value}\n"
            f"Main task: {decision.main_task}\n"
            f"Instruction: {instruction}\n"
            f"Hint: {decision.response_hint}\n\n"
            f"Group chat context:\n{context}"
        )
        self.budget.record_input_text(task)
        print(f"  invoking agent for phase={decision.phase.value} "
              f"(thread={self._agent_thread_id()}) ...")
        try:
            reply = self.agent_system.invoke(task, thread_id=self._agent_thread_id())
        except ValueError as exc:
            if not _is_invalid_tool_history_error(exc):
                raise
            self.agent_thread_id = (
                f"hub-{self.config.hub_agent_name}-recovered-{uuid.uuid4().hex[:8]}"
            )
            try:
                reply = self.agent_system.invoke(task, thread_id=self.agent_thread_id)
            except ValueError as retry_exc:
                if not _is_invalid_tool_history_error(retry_exc):
                    raise
                return "skipped: agent session history is corrupt after recovery"
        except Exception as exc:
            return f"agent invoke failed ({type(exc).__name__}): {exc}"
        return self._post(reply)

    def _respond(self, messages: list[HubMessage], decision: AssessmentDecision) -> str:
        budget = self.budget.check()
        if not budget.can_spend:
            return f"budget gate: {budget.reason}"

        prompt = PromptLibrary(self.config).render(
            "hub_participant",
            agent_name=self.config.hub_agent_name,
            agent_role=self.config.hub_agent_role,
            hub_max_message_chars=self.config.hub_max_message_chars,
        )
        context = format_hub_context(messages, self.config.hub_context_messages)
        task = (
            f"{prompt}\n\n"
            f"Internal assessment reason: {decision.reason}\n"
            f"Suggested response focus: {decision.response_hint}\n\n"
            f"Group chat context:\n{context}"
        )
        self.budget.record_input_text(task)
        print(f"  invoking agent (thread={self._agent_thread_id()}) ...")
        try:
            reply = self.agent_system.invoke(task, thread_id=self._agent_thread_id())
        except ValueError as exc:
            if not _is_invalid_tool_history_error(exc):
                raise
            self.agent_thread_id = (
                f"hub-{self.config.hub_agent_name}-recovered-{uuid.uuid4().hex[:8]}"
            )
            try:
                reply = self.agent_system.invoke(task, thread_id=self.agent_thread_id)
            except ValueError as retry_exc:
                if not _is_invalid_tool_history_error(retry_exc):
                    raise
                return "skipped: agent session history is corrupt after recovery"
        except Exception as exc:
            return f"agent invoke failed ({type(exc).__name__}): {exc}"
        return self._post(reply)

    def _post(self, content: str) -> str:
        budget = self.budget.check()
        if not budget.can_spend:
            return f"budget gate: {budget.reason}"

        chunks = _split_into_chunks(content.strip(), self.config.hub_max_message_chars)
        if not chunks:
            return "skipped empty outbound message"

        posted_seqs: list[int] = []
        for index, chunk in enumerate(chunks):
            if index > 0:
                time.sleep(1.0)
                budget = self.budget.check()
                if not budget.can_spend:
                    posted_seq_text = ",".join(str(seq) for seq in posted_seqs)
                    return (
                        f"posted {len(posted_seqs)}/{len(chunks)} chunks "
                        f"(seq={posted_seq_text}), budget gate: {budget.reason}"
                    )

            try:
                response = self.client.post_message(self.config.hub_agent_name, chunk)
            except HubRateLimitError as exc:
                chunk_number = index + 1
                return f"hub rate limit while posting chunk {chunk_number}/{len(chunks)}: {exc}"
            except HubClientError as exc:
                chunk_number = index + 1
                return f"hub post failed on chunk {chunk_number}/{len(chunks)}: {exc}"

            self._remember_messages(
                [HubMessage(seq=response.seq, agent_name=self.config.hub_agent_name, content=chunk)]
            )
            self.budget.record_output_text(chunk, posted=True)
            posted_seqs.append(response.seq)

        if len(posted_seqs) == 1:
            return f"posted seq={posted_seqs[0]}: {chunks[0][:120]}"
        posted_seq_text = ",".join(str(seq) for seq in posted_seqs)
        return f"posted {len(posted_seqs)} chunks (seq={posted_seq_text})"

    def _remember_messages(self, messages: list[HubMessage]) -> None:
        by_seq = {message.seq: message for message in self.message_history}
        by_seq.update({message.seq: message for message in messages})
        history_limit = max(self.config.hub_context_messages * 4, 100)
        self.message_history = sorted(by_seq.values(), key=lambda message: message.seq)[
            -history_limit:
        ]

    def _recent_messages(self) -> list[HubMessage]:
        return self.message_history[-self.config.hub_context_messages :]

    def _latest_inbound_seq(self) -> int:
        """Highest seq among messages from other agents, ignoring our own posts."""

        return max(
            (
                message.seq
                for message in self.message_history
                if message.agent_name != self.config.hub_agent_name
            ),
            default=0,
        )

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

    def _quit_requested(self) -> bool:
        return self.console is not None and self.console.should_quit

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
    state_assessor = HubStateAssessor(config, chat_model)
    agent_system = build_agent_system(
        config=config,
        approval_callback=approval_callback,
        stats_callback=lambda: client.fetch_stats().model_dump_json(),
        model=chat_model,
        hub_mode=True,
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
        state_assessor=state_assessor,
    )


def is_addressed_to_agent(
    content: str,
    agent_name: str,
    aliases: list[str] | None = None,
) -> bool:
    """Return true only when a message explicitly names this agent."""

    names = [agent_name, *(aliases or [])]
    return any(_is_addressed_to_name(content, name) for name in names)


def _split_into_chunks(content: str, max_chars: int) -> list[str]:
    """Split hub output into messages that each fit the configured limit."""

    if max_chars <= 0:
        return []

    stripped = content.strip()
    if not stripped:
        return []
    if len(stripped) <= max_chars:
        return [stripped]

    total_parts = 2
    while True:
        header_len = len(f"[{total_parts}/{total_parts}]\n")
        body_limit = max_chars - header_len
        if body_limit <= 0:
            return _split_body_into_chunks(stripped, max_chars)

        body_chunks = _split_body_into_chunks(stripped, body_limit)
        if len(body_chunks) == total_parts:
            break
        total_parts = len(body_chunks)

    return [
        f"[{index}/{total_parts}]\n{chunk}"
        for index, chunk in enumerate(body_chunks, start=1)
    ]


def _split_body_into_chunks(content: str, max_chars: int) -> list[str]:
    chunks: list[str] = []
    remaining = content.strip()

    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break

        split_at = _best_split_index(remaining, max_chars)
        chunks.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()

    return [chunk for chunk in chunks if chunk]


def _best_split_index(content: str, max_chars: int) -> int:
    for separator in ("\n\n", "\n", " "):
        index = content.rfind(separator, 0, max_chars + 1)
        if index > 0:
            return index + len(separator)
    return max_chars


def _is_addressed_to_name(content: str, name: str) -> bool:
    """Return true only when a message explicitly names one configured name."""

    normalized_agent_name = _normalize_address_text(name.strip())
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
