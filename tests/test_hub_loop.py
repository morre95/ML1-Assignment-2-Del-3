from dataclasses import replace
from pathlib import Path

from react_agent_system.config import DEFAULT_PROMPTS, AgentSystemConfig
from react_agent_system.hub.budget import BudgetController
from react_agent_system.hub.loop import HubLoop, _split_into_chunks, is_addressed_to_agent
from react_agent_system.hub.models import (
    AssessmentAction,
    AssessmentDecision,
    HubMessage,
    HubMessagesResponse,
    HubPostResponse,
)


class FakeClient:
    def __init__(self, messages: list[HubMessage]) -> None:
        self.messages = messages
        self.posts = []
        self.next_post_seq = 99

    def fetch_messages(self, since: int) -> HubMessagesResponse:
        return HubMessagesResponse(
            messages=[message for message in self.messages if message.seq > since]
        )

    def post_message(self, agent_name: str, content: str) -> HubPostResponse:
        self.posts.append((agent_name, content))
        response = HubPostResponse(status="ok", seq=self.next_post_seq)
        self.next_post_seq += 1
        return response


class FakeAssessor:
    def __init__(self, decision: AssessmentDecision | list[AssessmentDecision]) -> None:
        self.decisions = decision if isinstance(decision, list) else [decision]
        self.calls = []

    def assess(
        self,
        messages: list[HubMessage],
        trigger_message: HubMessage,
    ) -> AssessmentDecision:
        self.calls.append((messages, trigger_message))
        if len(self.decisions) == 1:
            return self.decisions[0]
        return self.decisions.pop(0)


class FakeAgentSystem:
    def __init__(self, failures: list[Exception] | None = None) -> None:
        self.calls = []
        self.failures = failures or []

    def invoke(self, message: str, thread_id: str) -> str:
        self.calls.append((message, thread_id))
        if self.failures:
            raise self.failures.pop(0)
        return f"{thread_id}: response to {message[:20]}"


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


def test_split_into_chunks_short_message_unchanged() -> None:
    assert _split_into_chunks("  short message  ", 20) == ["short message"]


def test_split_into_chunks_splits_at_paragraph_boundary() -> None:
    chunks = _split_into_chunks("alpha beta\n\nsecond paragraph\n\nthird paragraph", 30)

    assert chunks == [
        "[1/3]\nalpha beta",
        "[2/3]\nsecond paragraph",
        "[3/3]\nthird paragraph",
    ]
    assert all(len(chunk) <= 30 for chunk in chunks)


def test_split_into_chunks_splits_at_word_boundary() -> None:
    chunks = _split_into_chunks("alpha beta gamma delta", 18)

    assert chunks == ["[1/2]\nalpha beta", "[2/2]\ngamma delta"]
    assert all(len(chunk) <= 18 for chunk in chunks)


def test_split_into_chunks_hard_cuts_when_no_boundary() -> None:
    chunks = _split_into_chunks("abcdefghij", 8)

    assert chunks == ["[1/5]\nab", "[2/5]\ncd", "[3/5]\nef", "[4/5]\ngh", "[5/5]\nij"]
    assert all(len(chunk) <= 8 for chunk in chunks)


def test_split_into_chunks_adds_part_headers() -> None:
    chunks = _split_into_chunks("one two three four five six", 15)

    assert chunks[0].startswith("[1/")
    assert chunks[-1].startswith(f"[{len(chunks)}/{len(chunks)}]\n")
    assert all(len(chunk) <= 15 for chunk in chunks)


def test_hub_loop_gates_unaddressed_message_without_assessment(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    client = FakeClient([HubMessage(seq=1, agent_name="other", content="please code")])
    assessor = FakeAssessor(
        AssessmentDecision(action=AssessmentAction.RESPOND, reason="would respond")
    )
    loop = HubLoop(
        config=config,
        client=client,
        assessor=assessor,
        agent_system=FakeAgentSystem(),
        budget=BudgetController(config),
    )

    result = loop.run_once()

    assert "no message explicitly addressed" in result
    assert assessor.calls == []
    assert client.posts == []


def test_hub_loop_responds_and_posts(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    client = FakeClient([HubMessage(seq=1, agent_name="other", content="@me please code")])
    assessor = FakeAssessor(
        AssessmentDecision(
            action=AssessmentAction.RESPOND,
            reason="coding request",
            response_hint="answer",
        )
    )
    loop = HubLoop(
        config=config,
        client=client,
        assessor=assessor,
        agent_system=FakeAgentSystem(),
        budget=BudgetController(config),
    )

    result = loop.run_once()

    assert "posted seq=99" in result
    assert client.posts[0][0] == "me"
    assert assessor.calls[0][1].content == "@me please code"


def test_hub_loop_handles_newest_first_hub_messages(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    client = FakeClient(
        [
            HubMessage(seq=3, agent_name="other", content="@me current request"),
            HubMessage(seq=2, agent_name="other", content="@me old request"),
            HubMessage(seq=1, agent_name="other", content="background"),
        ]
    )
    assessor = FakeAssessor(
        AssessmentDecision(
            action=AssessmentAction.RESPOND,
            reason="coding request",
            response_hint="answer",
        )
    )
    loop = HubLoop(
        config=config,
        client=client,
        assessor=assessor,
        agent_system=FakeAgentSystem(),
        budget=BudgetController(config),
    )

    result = loop.run_once()

    assert "posted seq=99" in result
    assert loop.last_seen == 3
    assert assessor.calls[0][1].seq == 3


def test_hub_loop_accepts_direct_name_call_without_mention(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    client = FakeClient([HubMessage(seq=1, agent_name="other", content="me please code")])
    assessor = FakeAssessor(
        AssessmentDecision(
            action=AssessmentAction.RESPOND,
            reason="coding request",
            response_hint="answer",
        )
    )
    loop = HubLoop(
        config=config,
        client=client,
        assessor=assessor,
        agent_system=FakeAgentSystem(),
        budget=BudgetController(config),
    )

    result = loop.run_once()

    assert "posted seq=99" in result
    assert client.posts[0][0] == "me"
    assert assessor.calls[0][1].content == "me please code"


def test_hub_loop_responds_to_addressed_message_after_startup(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    config = replace(config, hub_agent_name="ErikMoren-agent", hub_agent_aliases=["ema"])
    client = FakeClient([HubMessage(seq=1, agent_name="other", content="background")])
    assessor = FakeAssessor(
        AssessmentDecision(
            action=AssessmentAction.RESPOND,
            reason="coding request",
            response_hint="answer",
        )
    )
    loop = HubLoop(
        config=config,
        client=client,
        assessor=assessor,
        agent_system=FakeAgentSystem(),
        budget=BudgetController(config),
    )

    first_result = loop.run_once()
    client.messages.append(
        HubMessage(
            seq=2,
            agent_name="human",
            content="@ema kan du kolla reviewen?",
        )
    )
    second_result = loop.run_once()

    assert "no message explicitly addressed" in first_result
    assert "posted seq=99" in second_result
    assert assessor.calls[0][1].seq == 2


def test_hub_loop_keeps_clarification_context_across_polls(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    client = FakeClient([HubMessage(seq=1, agent_name="human", content="@me build a script")])
    assessor = FakeAssessor(
        [
            AssessmentDecision(
                action=AssessmentAction.ASK_CLARIFICATION,
                reason="missing language",
                response_hint="Which language should I use?",
            ),
            AssessmentDecision(
                action=AssessmentAction.RESPOND,
                reason="user answered clarification",
                response_hint="use Python",
            ),
        ]
    )
    agent_system = FakeAgentSystem()
    loop = HubLoop(
        config=config,
        client=client,
        assessor=assessor,
        agent_system=agent_system,
        budget=BudgetController(config),
    )

    first_result = loop.run_once()
    client.messages.append(
        HubMessage(seq=100, agent_name="human", content="Python 3.12 please")
    )
    second_result = loop.run_once()

    assert "posted seq=99: Which language should I use?" in first_result
    assert "posted seq=100" in second_result
    assert assessor.calls[1][1].content == "Python 3.12 please"
    assert any(
        message.agent_name == "me" and message.content == "Which language should I use?"
        for message in assessor.calls[1][0]
    )
    assert "Which language should I use?" in agent_system.calls[0][0]
    assert "Python 3.12 please" in agent_system.calls[0][0]


def test_hub_loop_posts_blocked_command_without_invoking_agent(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    client = FakeClient([HubMessage(seq=1, agent_name="human", content="me run rm -rf .")])
    assessor = FakeAssessor(
        AssessmentDecision(
            action=AssessmentAction.RESPOND,
            reason="explicit command request",
        )
    )
    agent_system = FakeAgentSystem()
    loop = HubLoop(
        config=config,
        client=client,
        assessor=assessor,
        agent_system=agent_system,
        budget=BudgetController(config),
    )

    result = loop.run_once()

    assert "posted seq=99" in result
    assert "blocked by the command safety policy" in client.posts[0][1]
    assert "matched denied pattern" in client.posts[0][1]
    assert assessor.calls == []
    assert agent_system.calls == []


def test_hub_loop_recovers_from_invalid_tool_history(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    client = FakeClient([HubMessage(seq=1, agent_name="human", content="@me summarize")])
    assessor = FakeAssessor(
        AssessmentDecision(
            action=AssessmentAction.RESPOND,
            reason="direct request",
        )
    )
    agent_system = FakeAgentSystem(
        failures=[
            ValueError(
                "Found AIMessages with tool_calls that do not have a corresponding ToolMessage."
            )
        ]
    )
    loop = HubLoop(
        config=config,
        client=client,
        assessor=assessor,
        agent_system=agent_system,
        budget=BudgetController(config),
    )

    result = loop.run_once()

    assert "posted seq=99" in result
    assert agent_system.calls[0][1] == "hub-me"
    assert agent_system.calls[1][1] == "hub-me-recovered-1"


def test_post_sends_multiple_chunks_with_delay(tmp_path: Path, monkeypatch) -> None:
    sleep_calls = []
    monkeypatch.setattr(
        "react_agent_system.hub.loop.time.sleep",
        lambda seconds: sleep_calls.append(seconds),
    )
    config = replace(make_config(tmp_path), hub_max_message_chars=18)
    client = FakeClient([])
    loop = HubLoop(
        config=config,
        client=client,
        assessor=FakeAssessor(
            AssessmentDecision(action=AssessmentAction.STAY_SILENT, reason="test")
        ),
        agent_system=FakeAgentSystem(),
        budget=BudgetController(config),
    )

    result = loop._post("alpha beta gamma delta")

    assert result == "posted 2 chunks (seq=99,100)"
    assert client.posts == [
        ("me", "[1/2]\nalpha beta"),
        ("me", "[2/2]\ngamma delta"),
    ]
    assert sleep_calls == [1.0]


def test_post_stops_on_budget_exhaustion_mid_chunk(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("react_agent_system.hub.loop.time.sleep", lambda seconds: None)
    config = replace(make_config(tmp_path), hub_max_message_chars=18, hub_max_messages=1)
    client = FakeClient([])
    loop = HubLoop(
        config=config,
        client=client,
        assessor=FakeAssessor(
            AssessmentDecision(action=AssessmentAction.STAY_SILENT, reason="test")
        ),
        agent_system=FakeAgentSystem(),
        budget=BudgetController(config),
    )

    result = loop._post("alpha beta gamma delta epsilon")

    assert result == "posted 1/3 chunks (seq=99), budget gate: message cap reached"
    assert client.posts == [("me", "[1/3]\nalpha beta")]


def test_is_addressed_to_agent_accepts_mentions_and_direct_names() -> None:
    assert is_addressed_to_agent("@me please check this", "me")
    assert is_addressed_to_agent("me, please check this", "me")
    assert is_addressed_to_agent("me please check this", "me")
    assert is_addressed_to_agent("Hey me can you check this?", "me")
    assert is_addressed_to_agent(
        "ErikMoren-agent can you summarize your role?",
        "ErikMoren-agent",
    )
    assert is_addressed_to_agent(
        "ErikMorén-agent can you summarize your role?",
        "ErikMoren-agent",
    )
    assert is_addressed_to_agent(
        "can ErikMoren-agent build a hello world script in python",
        "ErikMoren-agent",
    )
    assert is_addressed_to_agent(
        "could ErikMorén-agent check this?",
        "ErikMoren-agent",
    )
    assert is_addressed_to_agent(
        "kan ErikMoren-agent kolla in stefan-code-disaster kod review",
        "ErikMoren-agent",
    )
    assert is_addressed_to_agent(
        "Does anyone know whether ErikMoren-agent can review this?",
        "ErikMoren-agent",
    )
    assert is_addressed_to_agent("@ema please check this", "ErikMoren-agent", ["ema"])
    assert is_addressed_to_agent("builder run pwd", "ErikMoren-agent", ["ema", "builder"])


def test_is_addressed_to_agent_rejects_general_relevance() -> None:
    assert not is_addressed_to_agent("Can someone check this?", "me")
    assert not is_addressed_to_agent("This task might be relevant to me later", "me")
    assert not is_addressed_to_agent("@method please check this", "me")
