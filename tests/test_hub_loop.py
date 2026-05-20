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


def test_is_addressed_to_agent_accepts_mentions_and_direct_names() -> None:
    assert is_addressed_to_agent("@me please check this", "me")
    assert is_addressed_to_agent("me, please check this", "me")
    assert is_addressed_to_agent("Hey me can you check this?", "me")


def test_is_addressed_to_agent_rejects_general_relevance() -> None:
    assert not is_addressed_to_agent("Can someone check this?", "me")
    assert not is_addressed_to_agent("This task might be relevant to me later", "me")
