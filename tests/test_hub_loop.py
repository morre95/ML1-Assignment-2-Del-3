from dataclasses import replace
from pathlib import Path

from react_agent_system.config import DEFAULT_PROMPTS, AgentSystemConfig
from react_agent_system.hub.budget import BudgetController
from react_agent_system.hub.loop import HubLoop, is_addressed_to_agent
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

    def fetch_messages(self, since: int) -> HubMessagesResponse:
        return HubMessagesResponse(
            messages=[message for message in self.messages if message.seq > since]
        )

    def post_message(self, agent_name: str, content: str) -> HubPostResponse:
        self.posts.append((agent_name, content))
        return HubPostResponse(status="ok", seq=99)


class FakeAssessor:
    def __init__(self, decision: AssessmentDecision) -> None:
        self.decision = decision
        self.calls = []

    def assess(
        self,
        messages: list[HubMessage],
        trigger_message: HubMessage,
    ) -> AssessmentDecision:
        self.calls.append((messages, trigger_message))
        return self.decision


class FakeAgentSystem:
    def invoke(self, message: str, thread_id: str) -> str:
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
    config = replace(config, hub_agent_name="ErikMoren-agent")
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
            content="kan ErikMoren-agent kolla reviewen?",
        )
    )
    second_result = loop.run_once()

    assert "no message explicitly addressed" in first_result
    assert "posted seq=99" in second_result
    assert assessor.calls[0][1].seq == 2


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


def test_is_addressed_to_agent_rejects_general_relevance() -> None:
    assert not is_addressed_to_agent("Can someone check this?", "me")
    assert not is_addressed_to_agent("This task might be relevant to me later", "me")
    assert not is_addressed_to_agent("@method please check this", "me")
