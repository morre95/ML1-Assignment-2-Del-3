"""LangChain tool factories."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from langchain_core.tools import BaseTool, tool

from react_agent_system.bash_safety import ApprovalCallback, BashCommandRunner
from react_agent_system.tools.github import fetch_github_pull_request_context
from react_agent_system.tools.repo import (
    RepositoryToolError,
    read_text_file,
    replace_exact_section,
    search_text,
)
from react_agent_system.tools.research import weather_lookup, web_search, wikipedia_lookup

AgentInvoker = Callable[[str], str]
StatsCallback = Callable[[], str]
UploadFileCallback = Callable[[str, str], str]
ReadFileCallback = Callable[[str], str]
ListFilesCallback = Callable[[], str]
BillboardCallback = Callable[[], str]


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

    @tool("weather_lookup")
    def weather_lookup_tool(location: str) -> str:
        """Look up current weather for a city or location."""

        return weather_lookup(location)

    return [web_search_tool, wikipedia_lookup_tool, weather_lookup_tool]


def build_github_tools() -> list[BaseTool]:
    """Create read-only GitHub pull request inspection tools."""

    @tool("fetch_github_pr_context")
    def fetch_github_pr_context_tool(pr_url: str) -> str:
        """Fetch read-only context for a GitHub pull request URL."""

        return fetch_github_pull_request_context(pr_url)

    return [fetch_github_pr_context_tool]


def build_hub_tools(stats_callback: StatsCallback | None) -> list[BaseTool]:
    """Create hub/server inspection tools when hub mode is available."""

    if stats_callback is None:
        return []

    @tool("hub_stats")
    def hub_stats_tool() -> str:
        """Fetch current hub state: pause flag, manager, billboard, and shared files."""

        return stats_callback()

    return [hub_stats_tool]


def build_hub_file_tools(
    upload_callback: UploadFileCallback | None,
    read_callback: ReadFileCallback | None,
    list_callback: ListFilesCallback | None,
    billboard_callback: BillboardCallback | None,
) -> list[BaseTool]:
    """Create tools for the shared hub file store and project billboard.

    The shared files are the team's deliverable, so the agent contributes code
    through these tools rather than only the local workspace.
    """

    tools: list[BaseTool] = []

    if upload_callback is not None:

        @tool("hub_upload_file")
        def hub_upload_file_tool(filename: str, content: str) -> str:
            """Upload or replace a file in the shared hub store (e.g. game.py).

            Read the file with hub_read_file first if it already exists.
            """

            return upload_callback(filename, content)

        tools.append(hub_upload_file_tool)

    if read_callback is not None:

        @tool("hub_read_file")
        def hub_read_file_tool(filename: str) -> str:
            """Read the current content of a shared hub file before modifying it."""

            return read_callback(filename)

        tools.append(hub_read_file_tool)

    if list_callback is not None:

        @tool("hub_list_files")
        def hub_list_files_tool() -> str:
            """List all files currently in the shared hub store."""

            return list_callback()

        tools.append(hub_list_files_tool)

    if billboard_callback is not None:

        @tool("hub_read_billboard")
        def hub_read_billboard_tool() -> str:
            """Read the shared project plan (billboard) posted by the manager."""

            return billboard_callback()

        tools.append(hub_read_billboard_tool)

    return tools


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

        try:
            return read_text_file(workspace, path)
        except RepositoryToolError as exc:
            return f"Error: {exc}"

    @tool("search_repo")
    def search_repo_tool(query: str, glob: str = "**/*") -> str:
        """Search text files in the workspace for a case-insensitive string."""

        try:
            return search_text(workspace, query, glob=glob)
        except RepositoryToolError as exc:
            return f"Error: {exc}"

    @tool("edit_file_section")
    def edit_file_section_tool(path: str, old_text: str, new_text: str) -> str:
        """Replace exactly one section of a workspace file."""

        try:
            return replace_exact_section(workspace, path, old_text, new_text)
        except RepositoryToolError as exc:
            return f"Error: {exc}"

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
