from pathlib import Path

from react_agent_system.agents import build_agent_system
from react_agent_system.config import DEFAULT_PROMPTS, AgentSystemConfig


class FakeAgent:
    def __init__(self, name: str) -> None:
        self.name = name

    def invoke(self, *_args, **_kwargs):
        return {"messages": [{"content": f"{self.name} complete"}]}


def test_build_agent_system_wires_specialists_and_supervisor(monkeypatch, tmp_path: Path) -> None:
    calls = []

    def fake_create_react_agent(**kwargs):
        calls.append(kwargs)
        return FakeAgent(kwargs["name"])

    monkeypatch.setattr("react_agent_system.agents.create_react_agent", fake_create_react_agent)
    config = AgentSystemConfig(
        workspace=tmp_path,
        prompt_dir=Path.cwd() / "prompts",
        session_db=tmp_path / "history.sqlite3",
        model="test/model",
        openrouter_api_key="test-key",
        prompts=dict(DEFAULT_PROMPTS),
    )

    system = build_agent_system(config, model=object(), checkpointer=object())

    assert (
        system.invoke("hello", thread_id="test-thread")
        == "planner_architect_supervisor complete"
    )
    assert [call["name"] for call in calls] == [
        "summary_writer",
        "code_writer",
        "planner",
        "coder",
        "reviewer",
        "tester",
        "debugger",
        "repo_tool",
        "planner_architect_supervisor",
    ]
    assert calls[-1]["checkpointer"] is not None
