"""Safety checks and execution wrapper for the bash command tool."""

from __future__ import annotations

import re
import shlex
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ApprovalCallback = Callable[[str, "SafetyDecision"], bool]


@dataclass(frozen=True)
class SafetyDecision:
    """Result of inspecting a proposed shell command."""

    allowed: bool
    reason: str
    approval_required: bool = True


DENIED_EXECUTABLES = {
    "halt",
    "mkfs",
    "mount",
    "poweroff",
    "reboot",
    "shutdown",
    "su",
    "sudo",
    "umount",
}

DENIED_PATTERNS = [
    re.compile(r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:", re.MULTILINE),
    re.compile(r"\brm\s+[^;&|]*-[^\s;&|]*[rf][^\s;&|]*\s+(/|~|\$HOME)(\s|$)"),
    re.compile(r"\brm\s+[^;&|]*-[^\s;&|]*[rf][^\s;&|]*"),
    re.compile(r"\bdd\s+.*\bof=/dev/"),
    re.compile(r"\bchmod\s+[^;&|]*-R[^;&|]*\s+777\s+(/|~|\$HOME)(\s|$)"),
    re.compile(r"\bchown\s+[^;&|]*-R[^;&|]*\s+(/|~|\$HOME)(\s|$)"),
    re.compile(r"\bgit\s+reset\s+--hard\b"),
    re.compile(r"\bgit\s+clean\s+-[^\s;&|]*[fxd][^\s;&|]*"),
    re.compile(r"\b(curl|wget)\b.*\|\s*(bash|sh|python|python3)\b"),
    re.compile(r">\s*/(etc|bin|sbin|usr|boot|dev|proc|sys|run|var)/"),
]


class BashCommandRunner:
    """Runs approved shell commands inside the workspace."""

    def __init__(
        self,
        workspace: Path,
        timeout_seconds: int,
        approval_callback: ApprovalCallback | None = None,
    ) -> None:
        self.workspace = workspace.resolve()
        self.timeout_seconds = timeout_seconds
        self.approval_callback = approval_callback

    def assess(self, command: str) -> SafetyDecision:
        return assess_command(command, self.workspace)

    def run(self, command: str) -> str:
        decision = self.assess(command)
        if not decision.allowed:
            return f"Command blocked: {decision.reason}"

        if decision.approval_required:
            if self.approval_callback is None:
                return "Command requires approval, but no approval callback is configured."
            if not self.approval_callback(command, decision):
                return "Command cancelled: approval was not granted."

        try:
            completed = subprocess.run(
                ["bash", "-lc", command],
                cwd=self.workspace,
                capture_output=True,
                check=False,
                text=True,
                timeout=self.timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return f"Command timed out after {self.timeout_seconds} seconds."

        output = _format_command_output(completed)
        return output[:10_000]


def assess_command(command: str, workspace: Path) -> SafetyDecision:
    """Reject destructive shell commands and require approval for the rest."""

    normalized = command.strip()
    if not normalized:
        return SafetyDecision(False, "empty command")

    for pattern in DENIED_PATTERNS:
        if pattern.search(normalized):
            return SafetyDecision(False, f"matched denied pattern: {pattern.pattern}")

    try:
        tokens = shlex.split(normalized)
    except ValueError as exc:
        return SafetyDecision(False, f"invalid shell syntax: {exc}")

    if not tokens:
        return SafetyDecision(False, "empty command")

    executable = Path(tokens[0]).name
    if executable in DENIED_EXECUTABLES:
        return SafetyDecision(False, f"denied executable: {executable}")

    redirect_decision = _check_redirection_targets(tokens, workspace.resolve())
    if redirect_decision is not None:
        return redirect_decision

    return SafetyDecision(True, "command is not on the deny list", approval_required=True)


def _check_redirection_targets(tokens: list[str], workspace: Path) -> SafetyDecision | None:
    redirect_tokens = {">", ">>", "1>", "1>>", "2>", "2>>"}
    for index, token in enumerate(tokens[:-1]):
        if token not in redirect_tokens:
            continue
        target = Path(tokens[index + 1])
        if target.is_absolute() and not _is_relative_to(target.resolve(), workspace):
            return SafetyDecision(False, f"redirection target is outside workspace: {target}")
    return None


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _format_command_output(completed: subprocess.CompletedProcess[str]) -> str:
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    parts = [f"exit_code={completed.returncode}"]
    if stdout:
        parts.append(f"stdout:\n{stdout}")
    if stderr:
        parts.append(f"stderr:\n{stderr}")
    return "\n".join(parts)
