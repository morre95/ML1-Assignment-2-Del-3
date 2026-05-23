from react_agent_system import cli
from react_agent_system.bash_safety import SafetyDecision


class FakeAgentSystem:
    def invoke(self, message: str, thread_id: str) -> str:
        return f"{thread_id}: {message}"


def test_cli_runs_agent_with_thread_id(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "build_agent_system", lambda *_args, **_kwargs: FakeAgentSystem())

    exit_code = cli.main(["--thread-id", "abc", "write", "code"])

    assert exit_code == 0
    assert "abc: write code" in capsys.readouterr().out


def test_hub_parser_accepts_team_mode_options() -> None:
    parser = cli.build_hub_parser()

    args = parser.parse_args(["--agent-name", "cryptofarian-builder", "--max-iterations", "1"])

    assert args.agent_name == "cryptofarian-builder"
    assert args.max_iterations == 1


def test_hub_mode_does_not_prompt_for_command_approval_by_default(monkeypatch) -> None:
    captured = {}

    class FakeLoop:
        console = None
        last_seen = 0

        def run_forever(self, max_iterations: int | None = None) -> None:
            captured["max_iterations"] = max_iterations

    def fake_build_hub_loop(config, approval_callback=None):
        captured["approval_callback"] = approval_callback
        return FakeLoop()

    monkeypatch.setattr(cli, "build_hub_loop", fake_build_hub_loop)

    exit_code = cli.run_hub(["--max-iterations", "1"])

    assert exit_code == 0
    assert captured["approval_callback"] is None
    assert captured["max_iterations"] == 1


def test_hub_mode_can_auto_approve_safe_commands_when_requested(monkeypatch) -> None:
    captured = {}

    class FakeLoop:
        console = None
        last_seen = 0

        def run_forever(self, max_iterations: int | None = None) -> None:
            captured["max_iterations"] = max_iterations

    def fake_build_hub_loop(config, approval_callback=None):
        captured["approval_callback"] = approval_callback
        return FakeLoop()

    monkeypatch.setattr(cli, "build_hub_loop", fake_build_hub_loop)

    exit_code = cli.run_hub(["--yes-to-safe-commands", "--max-iterations", "1"])

    assert exit_code == 0
    assert captured["approval_callback"]("pwd", SafetyDecision(True, "safe")) is True
    assert (
        captured["approval_callback"]("cd /workspace && pwd", SafetyDecision(True, "safe"))
        is True
    )
    assert (
        captured["approval_callback"](
            "python -c 'import shutil; shutil.rmtree(\".\")'",
            SafetyDecision(True, "not on deny list"),
        )
        is False
    )
