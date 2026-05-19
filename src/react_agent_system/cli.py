"""Command line interface for the ReAct agent system."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from react_agent_system.agents import build_agent_system
from react_agent_system.bash_safety import SafetyDecision
from react_agent_system.config import load_config
from react_agent_system.llm import OpenRouterConfigurationError


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    task = " ".join(args.task).strip()
    if not task:
        task = input("Task: ").strip()
    if not task:
        parser.error("a task is required")

    config_path = Path(args.config).resolve() if args.config else None
    config = load_config(config_path=config_path, workspace=Path.cwd())
    approval_callback = _auto_approve if args.yes_to_safe_commands else _prompt_for_approval

    try:
        agent_system = build_agent_system(config, approval_callback=approval_callback)
    except OpenRouterConfigurationError as exc:
        print(exc)
        return 2

    print(agent_system.invoke(task, thread_id=args.thread_id))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the ReAct multi-agent system.")
    parser.add_argument("task", nargs="*", help="User task for the agent system.")
    parser.add_argument(
        "--thread-id",
        default="default",
        help="Persistent LangGraph thread ID for session history.",
    )
    parser.add_argument(
        "--config",
        help="Optional YAML config file. Defaults come from config/agents.example.yaml values.",
    )
    parser.add_argument(
        "--yes-to-safe-commands",
        action="store_true",
        help="Auto-approve commands that pass safety checks. Dangerous commands are still blocked.",
    )
    return parser


def _prompt_for_approval(command: str, decision: SafetyDecision) -> bool:
    print("\nA tool requested permission to run this command:")
    print(command)
    print(f"Safety check: {decision.reason}")
    response = input("Approve command? [y/N] ").strip().lower()
    return response in {"y", "yes"}


def _auto_approve(command: str, decision: SafetyDecision) -> bool:
    print(f"Auto-approved safe command: {command} ({decision.reason})")
    return True


if __name__ == "__main__":
    raise SystemExit(main())
