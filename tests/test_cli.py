from react_agent_system import cli


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
