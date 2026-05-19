from pathlib import Path

from react_agent_system.config import DEFAULT_PROMPTS, AgentSystemConfig
from react_agent_system.hub.budget import BudgetController
from react_agent_system.hub.loop import HubLoop
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

    def assess(self, _messages: list[HubMessage]) -> AssessmentDecision:
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


def test_hub_loop_stays_silent_without_posting(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    client = FakeClient([HubMessage(seq=1, agent_name="other", content="hello")])
    loop = HubLoop(
        config=config,
        client=client,
        assessor=FakeAssessor(
            AssessmentDecision(action=AssessmentAction.STAY_SILENT, reason="not relevant")
        ),
        agent_system=FakeAgentSystem(),
        budget=BudgetController(config),
    )

    result = loop.run_once()

    assert "stay_silent" in result
    assert client.posts == []


def test_hub_loop_responds_and_posts(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    client = FakeClient([HubMessage(seq=1, agent_name="other", content="please code")])
    loop = HubLoop(
        config=config,
        client=client,
        assessor=FakeAssessor(
            AssessmentDecision(
                action=AssessmentAction.RESPOND,
                reason="coding request",
                response_hint="answer",
            )
        ),
        agent_system=FakeAgentSystem(),
        budget=BudgetController(config),
    )

    result = loop.run_once()

    assert "posted seq=99" in result
    assert client.posts[0][0] == "me"
