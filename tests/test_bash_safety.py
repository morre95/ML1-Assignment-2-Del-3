from pathlib import Path

from react_agent_system.bash_safety import BashCommandRunner, assess_command


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
