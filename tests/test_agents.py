from pathlib import Path

from react_agent_system.agents import build_agent_system
from react_agent_system.config import DEFAULT_PROMPTS, AgentSystemConfig
from react_agent_system.tools.factory import build_hub_file_tools, build_hub_tools


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
    assert "hub_upload_file" in supervisor_prompt
    assert "32768 bytes" in supervisor_prompt


def test_hub_stats_tool_returns_callback_output() -> None:
    tools = build_hub_tools(lambda: '{"paused":false}')

    assert len(tools) == 1
    assert tools[0].name == "hub_stats"
    assert tools[0].invoke({}) == '{"paused":false}'


def test_build_hub_file_tools_wires_all_callbacks() -> None:
    tools = build_hub_file_tools(
        upload_callback=lambda filename, content: f"uploaded {filename}",
        read_callback=lambda filename: f"read {filename}",
        list_callback=lambda: "files",
        billboard_callback=lambda: "plan",
    )

    tool_names = {tool.name for tool in tools}
    assert tool_names == {
        "hub_upload_file",
        "hub_read_file",
        "hub_list_files",
        "hub_read_billboard",
    }
    upload_tool = next(tool for tool in tools if tool.name == "hub_upload_file")
    assert upload_tool.invoke({"filename": "game.py", "content": "x"}) == "uploaded game.py"


def test_build_hub_file_tools_omits_missing_callbacks() -> None:
    tools = build_hub_file_tools(None, None, None, None)

    assert tools == []


def test_build_agent_system_adds_hub_file_tools_in_hub_mode(
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
        upload_file_callback=lambda filename, content: "ok",
        read_file_callback=lambda filename: "ok",
        list_files_callback=lambda: "ok",
        billboard_callback=lambda: "ok",
        model=object(),
        checkpointer=object(),
        hub_mode=True,
    )

    supervisor_tool_names = {tool.name for tool in calls[-1]["tools"]}
    assert {"hub_upload_file", "hub_read_file", "hub_list_files", "hub_read_billboard"} <= (
        supervisor_tool_names
    )
