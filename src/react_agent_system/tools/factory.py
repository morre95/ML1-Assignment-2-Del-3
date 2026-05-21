"""LangChain tool factories."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from langchain_core.tools import BaseTool, tool

from react_agent_system.bash_safety import ApprovalCallback, BashCommandRunner
from react_agent_system.tools.github import fetch_github_pull_request_context
from react_agent_system.tools.repo import read_text_file, replace_exact_section, search_text
from react_agent_system.tools.research import web_search, wikipedia_lookup

AgentInvoker = Callable[[str], str]


def build_research_tools(max_web_results: int) -> list[BaseTool]:
    """Create web and Wikipedia research tools."""

    @tool("web_search")
    def web_search_tool(query: str) -> str:
        """Search the public web for current information."""

        return web_search(query, max_results=max_web_results)

    @tool("wikipedia_lookup")
    def wikipedia_lookup_tool(query: str) -> str:
        """Look up encyclopedic background information on Wikipedia."""

        return wikipedia_lookup(query)

    return [web_search_tool, wikipedia_lookup_tool]


def build_github_tools() -> list[BaseTool]:
    """Create read-only GitHub pull request inspection tools."""

    @tool("fetch_github_pr_context")
    def fetch_github_pr_context_tool(pr_url: str) -> str:
        """Fetch read-only context for a GitHub pull request URL."""

        return fetch_github_pull_request_context(pr_url)

    return [fetch_github_pr_context_tool]


def build_repo_tools(
    workspace: Path,
    timeout_seconds: int,
    approval_callback: ApprovalCallback | None,
) -> list[BaseTool]:
    """Create repository inspection, edit, and command tools."""

    runner = BashCommandRunner(
        workspace=workspace,
        timeout_seconds=timeout_seconds,
        approval_callback=approval_callback,
    )

    @tool("read_file")
    def read_file_tool(path: str) -> str:
        """Read a UTF-8 text file inside the workspace."""

        return read_text_file(workspace, path)

    @tool("search_repo")
    def search_repo_tool(query: str, glob: str = "**/*") -> str:
        """Search text files in the workspace for a case-insensitive string."""

        return search_text(workspace, query, glob=glob)

    @tool("edit_file_section")
    def edit_file_section_tool(path: str, old_text: str, new_text: str) -> str:
        """Replace exactly one section of a workspace file."""

        return replace_exact_section(workspace, path, old_text, new_text)

    @tool("bash_command")
    def bash_command_tool(command: str) -> str:
        """Run a shell command after safety checks and approval."""

        return runner.run(command)

    return [read_file_tool, search_repo_tool, edit_file_section_tool, bash_command_tool]


def build_agent_tool(name: str, description: str, invoke_agent: AgentInvoker) -> BaseTool:
    """Wrap a specialist agent as a callable tool."""

    @tool(name, description=description)
    def agent_tool(task: str) -> str:
        return invoke_agent(task)

    return agent_tool
