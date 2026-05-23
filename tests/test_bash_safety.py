from pathlib import Path

from react_agent_system.bash_safety import (
    BashCommandRunner,
    assess_command,
    is_hub_auto_approved_command,
)


def test_assess_command_blocks_recursive_remove(tmp_path: Path) -> None:
    decision = assess_command("rm -rf /", tmp_path)

    assert not decision.allowed


def test_assess_command_requires_approval_for_safe_command(tmp_path: Path) -> None:
    decision = assess_command("python -m pytest", tmp_path)

    assert decision.allowed
    assert decision.approval_required


def test_runner_does_not_execute_without_approval_callback(tmp_path: Path) -> None:
    runner = BashCommandRunner(tmp_path, timeout_seconds=1)

    result = runner.run("pwd")

    assert "requires approval" in result


def test_runner_executes_when_approved(tmp_path: Path) -> None:
    runner = BashCommandRunner(tmp_path, timeout_seconds=5, approval_callback=lambda *_: True)

    result = runner.run("printf hello")

    assert "exit_code=0" in result
    assert "hello" in result


def test_hub_auto_approval_allows_small_safe_command_set() -> None:
    assert is_hub_auto_approved_command("pwd")
    assert is_hub_auto_approved_command("cd /workspace && pwd")
    assert is_hub_auto_approved_command("ls -la")
    assert is_hub_auto_approved_command("git status --short")
    assert is_hub_auto_approved_command("git diff --stat")
    assert is_hub_auto_approved_command("python -m pytest tests")
    assert is_hub_auto_approved_command("ruff check src tests")


def test_hub_auto_approval_rejects_arbitrary_or_writing_commands() -> None:
    assert not is_hub_auto_approved_command("python -c 'import shutil; shutil.rmtree(\".\")'")
    assert not is_hub_auto_approved_command("find . -delete")
    assert not is_hub_auto_approved_command("printf hi > file.txt")
    assert not is_hub_auto_approved_command("rm -rf .")
    assert not is_hub_auto_approved_command("git reset --hard")
