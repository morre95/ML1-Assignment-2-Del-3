"""Agent graph construction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langgraph.prebuilt import create_react_agent

from react_agent_system.bash_safety import ApprovalCallback
from react_agent_system.config import AgentSystemConfig
from react_agent_system.llm import build_chat_model
from react_agent_system.prompts import PromptLibrary
from react_agent_system.session import build_sqlite_checkpointer, build_thread_config
from react_agent_system.tools.factory import build_agent_tool, build_repo_tools, build_research_tools


@dataclass
class AgentSystem:
    """Runnable lead agent with persistent session history."""

    app: Any
    config: AgentSystemConfig

    def invoke(self, message: str, thread_id: str) -> str:
        result = self.app.invoke(
            {"messages": [{"role": "user", "content": message}]},
            config=build_thread_config(thread_id, self.config.recursion_limit),
        )
        return extract_last_message_text(result)


def build_agent_system(
    config: AgentSystemConfig,
    approval_callback: ApprovalCallback | None = None,
    model: Any | None = None,
    checkpointer: Any | None = None,
) -> AgentSystem:
    """Build the full supervisor plus specialist-agent tool graph."""

    chat_model = model or build_chat_model(config)
    prompt_library = PromptLibrary(config)
    repo_tools = build_repo_tools(
        workspace=config.workspace,
        timeout_seconds=config.command_timeout_seconds,
        approval_callback=approval_callback,
    )
    research_tools = build_research_tools(config.web_search_max_results)

    summary_agent = create_react_agent(
        model=chat_model,
        tools=[],
        name="summary_writer",
        prompt=prompt_library.render("summary_writer"),
    )
    code_writer_agent = create_react_agent(
        model=chat_model,
        tools=repo_tools,
        name="code_writer",
        prompt=prompt_library.render("code_writer"),
    )

    summary_tool = build_agent_tool(
        "ask_summary_writer",
        "Ask the summary writer agent to summarize technical context or results.",
        _agent_invoker(summary_agent, config.recursion_limit),
    )
    code_writer_tool = build_agent_tool(
        "ask_code_writer",
        "Ask a focused code-writing subagent to implement a small coding task.",
        _agent_invoker(code_writer_agent, config.recursion_limit),
    )

    planner_agent = create_react_agent(
        model=chat_model,
        tools=research_tools + [summary_tool],
        name="planner",
        prompt=prompt_library.render("planner"),
    )
    coder_agent = create_react_agent(
        model=chat_model,
        tools=repo_tools + [code_writer_tool],
        name="coder",
        prompt=prompt_library.render("coder"),
    )
    reviewer_agent = create_react_agent(
        model=chat_model,
        tools=repo_tools + [summary_tool],
        name="reviewer",
        prompt=prompt_library.render("reviewer"),
    )
    tester_agent = create_react_agent(
        model=chat_model,
        tools=repo_tools,
        name="tester",
        prompt=prompt_library.render("tester"),
    )
    debugger_agent = create_react_agent(
        model=chat_model,
        tools=repo_tools + [code_writer_tool],
        name="debugger",
        prompt=prompt_library.render("debugger"),
    )
    repo_tool_agent = create_react_agent(
        model=chat_model,
        tools=repo_tools + research_tools,
        name="repo_tool",
        prompt=prompt_library.render("repo_tool"),
    )

    supervisor_tools = repo_tools + research_tools + [
        build_agent_tool(
            "ask_planner",
            "Ask the planner/architect agent to break down a user request.",
            _agent_invoker(planner_agent, config.recursion_limit),
        ),
        build_agent_tool(
            "ask_coder",
            "Ask the coder agent to implement a clearly scoped task.",
            _agent_invoker(coder_agent, config.recursion_limit),
        ),
        build_agent_tool(
            "ask_reviewer",
            "Ask the reviewer agent to inspect code or proposed changes.",
            _agent_invoker(reviewer_agent, config.recursion_limit),
        ),
        build_agent_tool(
            "ask_tester",
            "Ask the test agent to create or run tests for a task.",
            _agent_invoker(tester_agent, config.recursion_limit),
        ),
        build_agent_tool(
            "ask_debugger",
            "Ask the debug/fixer agent to diagnose failures and propose minimal fixes.",
            _agent_invoker(debugger_agent, config.recursion_limit),
        ),
        build_agent_tool(
            "ask_repo_tool_agent",
            "Ask the repo/tool agent to inspect files, search, edit, or run approved commands.",
            _agent_invoker(repo_tool_agent, config.recursion_limit),
        ),
        summary_tool,
        code_writer_tool,
    ]

    app = create_react_agent(
        model=chat_model,
        tools=supervisor_tools,
        name="planner_architect_supervisor",
        prompt=prompt_library.render("supervisor"),
        checkpointer=checkpointer or build_sqlite_checkpointer(config.session_db),
    )
    return AgentSystem(app=app, config=config)


def _agent_invoker(agent: Any, recursion_limit: int) -> Any:
    def invoke(task: str) -> str:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": task}]},
            config={"recursion_limit": recursion_limit},
        )
        return extract_last_message_text(result)

    return invoke


def extract_last_message_text(result: dict[str, Any]) -> str:
    """Return the final assistant message from a LangGraph result."""

    messages = result.get("messages", [])
    if not messages:
        return ""

    last_message = messages[-1]
    if isinstance(last_message, dict):
        content = last_message.get("content", "")
    else:
        content = getattr(last_message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(block) for block in content)
    return str(content)
