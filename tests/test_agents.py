from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage

from react_agent_system.agents import _build_history_trim_hook, build_agent_system
from react_agent_system.config import DEFAULT_PROMPTS, AgentSystemConfig
from react_agent_system.tools.factory import build_hub_tools


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


def test_build_agent_system_adds_hub_stats_tool_when_configured(
    monkeypatch,
    tmp_path: Path,
) -> None:
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

    build_agent_system(
        config,
        stats_callback=lambda: '{"total_messages":1}',
        model=object(),
        checkpointer=object(),
    )

    supervisor_tool_names = {tool.name for tool in calls[-1]["tools"]}
    assert "hub_stats" in supervisor_tool_names


def test_build_agent_system_supervisor_includes_hub_code_delivery_in_hub_mode(
    monkeypatch,
    tmp_path: Path,
) -> None:
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
        hub_max_message_chars=3000,
    )

    build_agent_system(config, model=object(), checkpointer=object(), hub_mode=True)

    supervisor_prompt = calls[-1]["prompt"]
    assert "fenced markdown code blocks" in supervisor_prompt
    assert "3000 characters" in supervisor_prompt


def test_supervisor_gets_trim_hook_only_in_hub_mode(monkeypatch, tmp_path: Path) -> None:
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

    build_agent_system(config, model=object(), checkpointer=object())
    assert calls[-1]["pre_model_hook"] is None

    calls.clear()
    build_agent_system(config, model=object(), checkpointer=object(), hub_mode=True)
    assert calls[-1]["pre_model_hook"] is not None


def test_history_trim_hook_keeps_recent_messages_starting_on_human() -> None:
    hook = _build_history_trim_hook(3)
    messages = [
        HumanMessage("h1"),
        AIMessage("a1"),
        HumanMessage("h2"),
        AIMessage("a2"),
        HumanMessage("h3"),
        AIMessage("a3"),
    ]

    trimmed = hook({"messages": messages})["llm_input_messages"]

    assert len(trimmed) <= 3
    assert isinstance(trimmed[0], HumanMessage)
    assert trimmed[-1].content == "a3"


def test_hub_stats_tool_returns_callback_output() -> None:
    tools = build_hub_tools(lambda: '{"max_global":100}')

    assert len(tools) == 1
    assert tools[0].name == "hub_stats"
    assert tools[0].invoke({}) == '{"max_global":100}'
