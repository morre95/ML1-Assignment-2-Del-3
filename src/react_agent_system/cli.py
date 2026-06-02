"""Command line interface for the ReAct agent system."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path

from react_agent_system.agents import build_agent_system
from react_agent_system.bash_safety import SafetyDecision, is_hub_auto_approved_command
from react_agent_system.config import load_config
from react_agent_system.hub.loop import build_hub_loop
from react_agent_system.llm import OpenRouterConfigurationError


def main(argv: Sequence[str] | None = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    if args_list[:1] == ["hub"]:
        return run_hub(args_list[1:])
    return run_task(args_list)


def run_task(argv: Sequence[str]) -> int:
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


def run_hub(argv: Sequence[str]) -> int:
    parser = build_hub_parser()
    args = parser.parse_args(argv)
    config_path = Path(args.config).resolve() if args.config else None
    config = load_config(config_path=config_path, workspace=Path.cwd())
    if args.agent_name:
        config = replace(config, hub_agent_name=args.agent_name)
    if args.role:
        config = replace(config, hub_agent_role=args.role)
    if args.manager:
        config = replace(config, hub_agent_is_manager=True)

    approval_callback = _auto_approve_hub_command if args.yes_to_safe_commands else None
    try:
        loop = build_hub_loop(config, approval_callback=approval_callback)
    except (OpenRouterConfigurationError, ValueError) as exc:
        print(exc)
        return 2

    loop.last_seen = args.since
    if args.console:
        loop.console.start_background_reader()
    try:
        loop.run_forever(max_iterations=args.max_iterations)
    except KeyboardInterrupt:
        print("\ninterrupted")
    else:
        print("loop ended")
    if args.goodbye:
        _post_goodbye(loop)
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


def build_hub_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the agent in RunPod hub team mode.")
    parser.add_argument(
        "--agent-name",
        help="Unique hub agent name, e.g. cryptofarian-builder.",
    )
    parser.add_argument("--role", help="Short role/personality for this hub participant.")
    parser.add_argument(
        "--manager",
        action="store_true",
        help="Run this agent as the team manager (plans and integrates) instead of a team-player.",
    )
    parser.add_argument(
        "--config",
        help="Optional YAML config file.",
    )
    parser.add_argument(
        "--console",
        action="store_true",
        help="Enable live console controls: status, pause, resume, budget, stats, quit.",
    )
    parser.add_argument(
        "--since",
        type=int,
        default=0,
        help="Initial hub sequence number to poll from.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        help="Stop after N poll iterations. Useful for dry runs and tests.",
    )
    parser.add_argument(
        "--goodbye",
        action="store_true",
        help="Post a goodbye message to the hub when signing off. Off by default.",
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


def _auto_approve_hub_command(command: str, decision: SafetyDecision) -> bool:
    if is_hub_auto_approved_command(command):
        print(f"Auto-approved hub allow-listed command: {command} ({decision.reason})")
        return True
    print(f"Hub command not on allow-list: {command} ({decision.reason})")
    return False


def _post_goodbye(loop) -> None:
    from react_agent_system.hub.client import HubClientError
    from react_agent_system.hub.loop import HubLoop

    if not isinstance(loop, HubLoop):
        return

    try:
        response = loop.client.post_message(
            loop.config.hub_agent_name,
            f"{loop.config.hub_agent_name} signing off. Goodbye!",
        )
        print(f"goodbye posted (seq={response.seq})")
    except HubClientError as exc:
        print(f"failed to post goodbye: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
