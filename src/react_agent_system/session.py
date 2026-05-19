"""Session persistence for LangGraph runs."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver


def build_sqlite_checkpointer(path: Path) -> SqliteSaver:
    """Create a SQLite checkpointer for persistent thread history."""

    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, check_same_thread=False)
    return SqliteSaver(connection)


def build_thread_config(thread_id: str, recursion_limit: int) -> dict[str, object]:
    """Build the LangGraph config for a persistent thread."""

    return {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": recursion_limit,
    }
