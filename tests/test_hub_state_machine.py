from dataclasses import replace
from pathlib import Path

from react_agent_system.config import DEFAULT_PROMPTS, AgentSystemConfig
from react_agent_system.hub.budget import BudgetController
from react_agent_system.hub.loop import HubLoop
from react_agent_system.hub.models import (
    AssessmentAction,
    AssessmentDecision,
    HubMessage,
    HubMessagesResponse,
    HubPhase,
    HubPostResponse,
    PhaseDecision,
)
from react_agent_system.hub.state_machine import parse_phase_decision
from react_agent_system.prompts import PromptLibrary


class FakeClient:
    def __init__(self, messages: list[HubMessage]) -> None:
        self.messages = messages
        self.posts: list[tuple[str, str]] = []
        self.next_post_seq = 99

    def fetch_messages(self, since: int) -> HubMessagesResponse:
        return HubMessagesResponse(
            messages=[m for m in self.messages if m.seq > since]
        )

    def post_message(self, agent_name: str, content: str) -> HubPostResponse:
        self.posts.append((agent_name, content))
        response = HubPostResponse(status="ok", seq=self.next_post_seq)
        self.next_post_seq += 1
        return response


class FakeStateAssessor:
    def __init__(self, decision: PhaseDecision) -> None:
        self.decision = decision
        self.calls: list[list[HubMessage]] = []

    def assess(self, messages: list[HubMessage]) -> PhaseDecision:
        self.calls.append(messages)
        return self.decision


class FakeAssessor:
    def assess(self, messages: list[HubMessage], trigger: HubMessage) -> AssessmentDecision:
        return AssessmentDecision(
            action=AssessmentAction.STAY_SILENT, reason="unused"
        )


class FakeAgentSystem:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def invoke(self, message: str, thread_id: str) -> str:
        self.calls.append((message, thread_id))
        return f"agent reply for {thread_id}"


def make_config(tmp_path: Path) -> AgentSystemConfig:
    return AgentSystemConfig(
        workspace=tmp_path,
        prompt_dir=Path.cwd() / "prompts",
        session_db=tmp_path / "history.sqlite3",
        model="test/model",
        openrouter_api_key="test-key",
        prompts=dict(DEFAULT_PROMPTS),
        hub_agent_name="me",
        hub_max_messages=10,
    )


# --- PhaseDecision parsing ---


def test_parse_phase_decision_valid_json() -> None:
    decision = parse_phase_decision(
        '{"phase": "claim_task", "reason": "free task", '
        '"main_task": "build API", "chosen_task": "write tests", '
        '"response_hint": "start with unit tests"}'
    )

    assert decision.phase == HubPhase.CLAIM_TASK
    assert decision.reason == "free task"
    assert decision.main_task == "build API"
    assert decision.chosen_task == "write tests"
    assert decision.response_hint == "start with unit tests"


def test_parse_phase_decision_accepts_json_fence() -> None:
    decision = parse_phase_decision(
        '```json\n{"phase": "propose_plan", "reason": "no plan yet"}\n```'
    )

    assert decision.phase == HubPhase.PROPOSE_PLAN


def test_parse_phase_decision_fails_closed_on_bad_json() -> None:
    decision = parse_phase_decision("this is not json at all")

    assert decision.phase == HubPhase.STAY_SILENT
    assert "not valid JSON" in decision.reason


def test_parse_phase_decision_fails_closed_on_missing_fields() -> None:
    decision = parse_phase_decision('{"reason": "forgot phase"}')

    assert decision.phase == HubPhase.STAY_SILENT


def test_parse_phase_decision_minimal_fields() -> None:
    decision = parse_phase_decision(
        '{"phase": "propose_done", "reason": "all complete"}'
    )

    assert decision.phase == HubPhase.PROPOSE_DONE
    assert decision.chosen_task == ""
    assert decision.main_task == ""


# --- HubLoop state machine integration ---


def _build_loop(
    tmp_path: Path,
    messages: list[HubMessage],
    phase_decision: PhaseDecision,
) -> tuple[HubLoop, FakeClient, FakeStateAssessor, FakeAgentSystem]:
    config = make_config(tmp_path)
    client = FakeClient(messages)
    state_assessor = FakeStateAssessor(phase_decision)
    agent_system = FakeAgentSystem()
    loop = HubLoop(
        config=config,
        client=client,
        assessor=FakeAssessor(),
        agent_system=agent_system,
        budget=BudgetController(config),
        state_assessor=state_assessor,
    )
    return loop, client, state_assessor, agent_system


def test_state_machine_stay_silent_produces_no_post(tmp_path: Path) -> None:
    loop, client, state_assessor, agent_system = _build_loop(
        tmp_path,
        [HubMessage(seq=1, agent_name="other", content="hello team")],
        PhaseDecision(phase=HubPhase.STAY_SILENT, reason="nothing to do"),
    )

    result = loop.run_once()

    assert "stay_silent" in result
    assert "nothing to do" in result
    assert client.posts == []
    assert agent_system.calls == []


def test_state_machine_propose_plan_invokes_agent_and_posts(tmp_path: Path) -> None:
    loop, client, state_assessor, agent_system = _build_loop(
        tmp_path,
        [HubMessage(seq=1, agent_name="human", content="build a REST API")],
        PhaseDecision(
            phase=HubPhase.PROPOSE_PLAN,
            reason="no plan yet",
            main_task="build a REST API",
            response_hint="break into endpoints",
        ),
    )

    result = loop.run_once()

    assert "posted seq=99" in result
    assert len(agent_system.calls) == 1
    assert "Propose a structured plan" in agent_system.calls[0][0]
    assert client.posts[0][0] == "me"


def test_state_machine_claim_task_includes_chosen_task(tmp_path: Path) -> None:
    loop, client, state_assessor, agent_system = _build_loop(
        tmp_path,
        [HubMessage(seq=1, agent_name="human", content="tasks available")],
        PhaseDecision(
            phase=HubPhase.CLAIM_TASK,
            reason="free task available",
            main_task="build API",
            chosen_task="implement GET /users",
            response_hint="start coding",
        ),
    )

    result = loop.run_once()

    assert "posted seq=99" in result
    assert len(agent_system.calls) == 1
    assert "implement GET /users" in agent_system.calls[0][0]


def test_state_machine_review_task_invokes_agent(tmp_path: Path) -> None:
    loop, client, state_assessor, agent_system = _build_loop(
        tmp_path,
        [HubMessage(seq=1, agent_name="other", content="task done")],
        PhaseDecision(
            phase=HubPhase.REVIEW_TASK,
            reason="all tasks busy or done",
            main_task="build API",
        ),
    )

    result = loop.run_once()

    assert "posted seq=99" in result
    assert "Review a completed task" in agent_system.calls[0][0]


def test_state_machine_propose_done_marks_done(tmp_path: Path) -> None:
    loop, client, state_assessor, agent_system = _build_loop(
        tmp_path,
        [HubMessage(seq=1, agent_name="other", content="all done")],
        PhaseDecision(
            phase=HubPhase.PROPOSE_DONE,
            reason="everything complete",
            main_task="build API",
        ),
    )

    result = loop.run_once()

    assert "posted seq=99" in result
    assert "DONE" in agent_system.calls[0][0]


def test_state_machine_skips_when_no_new_messages(tmp_path: Path) -> None:
    loop, client, state_assessor, agent_system = _build_loop(
        tmp_path,
        [],
        PhaseDecision(phase=HubPhase.CLAIM_TASK, reason="should not run"),
    )

    result = loop.run_once()

    assert result == ""
    assert state_assessor.calls == []


def test_state_machine_respects_budget(tmp_path: Path) -> None:
    config = replace(make_config(tmp_path), hub_max_messages=0)
    client = FakeClient(
        [HubMessage(seq=1, agent_name="other", content="hello")]
    )
    state_assessor = FakeStateAssessor(
        PhaseDecision(phase=HubPhase.PROPOSE_PLAN, reason="should be blocked")
    )
    loop = HubLoop(
        config=config,
        client=client,
        assessor=FakeAssessor(),
        agent_system=FakeAgentSystem(),
        budget=BudgetController(config),
        state_assessor=state_assessor,
    )

    result = loop.run_once()

    assert "budget gate" in result
    assert client.posts == []


def test_state_machine_runs_on_existing_history_without_new_messages(tmp_path: Path) -> None:
    """The state machine re-evaluates even when no new messages arrive."""

    loop, client, state_assessor, agent_system = _build_loop(
        tmp_path,
        [HubMessage(seq=1, agent_name="other", content="here is the plan")],
        PhaseDecision(
            phase=HubPhase.CLAIM_TASK,
            reason="free task available",
            main_task="build API",
            chosen_task="implement auth",
        ),
    )

    loop.run_once()
    assert len(state_assessor.calls) == 1

    client.messages = []
    result = loop.run_once()

    assert len(state_assessor.calls) == 2
    assert "posted" in result


def test_state_machine_runs_when_only_self_messages_are_new(tmp_path: Path) -> None:
    """State machine should still run when the only new message is from this agent."""

    config = make_config(tmp_path)
    client = FakeClient(
        [HubMessage(seq=1, agent_name="other", content="plan posted")]
    )
    state_assessor = FakeStateAssessor(
        PhaseDecision(
            phase=HubPhase.CLAIM_TASK,
            reason="free task",
            chosen_task="write tests",
        )
    )
    agent_system = FakeAgentSystem()
    loop = HubLoop(
        config=config,
        client=client,
        assessor=FakeAssessor(),
        agent_system=agent_system,
        budget=BudgetController(config),
        state_assessor=state_assessor,
    )

    loop.run_once()
    assert len(state_assessor.calls) == 1

    client.messages = [HubMessage(seq=99, agent_name="me", content="I claim write tests")]
    result = loop.run_once()

    assert len(state_assessor.calls) == 2
    assert "posted" in result


def test_reactive_path_still_works_without_state_assessor(tmp_path: Path) -> None:
    """When state_assessor is None, the original reactive gate applies."""

    config = make_config(tmp_path)
    client = FakeClient(
        [HubMessage(seq=1, agent_name="other", content="general chat")]
    )
    loop = HubLoop(
        config=config,
        client=client,
        assessor=FakeAssessor(),
        agent_system=FakeAgentSystem(),
        budget=BudgetController(config),
        state_assessor=None,
    )

    result = loop.run_once()

    assert "no message explicitly addressed" in result


# --- Prompt rendering ---


def test_collaboration_rules_in_participant_prompt(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    library = PromptLibrary(config)

    rendered = library.render(
        "hub_participant",
        agent_name="me",
        agent_role="builder",
        hub_max_message_chars=4096,
    )

    assert "claim a task" in rendered.lower()
    assert "one task at a time" in rendered.lower()
    assert "alphabetical" in rendered.lower()


def test_state_assessor_prompt_renders(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    library = PromptLibrary(config)

    rendered = library.render(
        "hub_state_assessor",
        agent_name="me",
        agent_role="builder",
    )

    assert "propose_plan" in rendered
    assert "claim_task" in rendered
    assert "claim a task" in rendered.lower()
