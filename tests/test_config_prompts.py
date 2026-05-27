from pathlib import Path

from react_agent_system.config import load_config
from react_agent_system.prompts import PromptLibrary


def test_load_config_uses_yaml_and_environment_overrides(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_file = tmp_path / "agents.yaml"
    config_file.write_text(
        "model: configured/model\n"
        "prompt_dir: prompts\n"
        "session_db: custom/history.sqlite3\n"
        "recursion_limit: 12\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("REACT_AGENT_MODEL", "env/model")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    config = load_config(config_path=config_file, workspace=tmp_path)

    assert config.model == "env/model"
    assert config.openrouter_api_key == "test-key"
    assert config.session_db == tmp_path / "custom/history.sqlite3"
    assert config.recursion_limit == 12


def test_load_config_dotenv_overrides_empty_compose_default(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".env").write_text(
        "REACT_AGENT_HUB_PASSWORD=from-dotenv\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("REACT_AGENT_HUB_PASSWORD", "")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    config = load_config(workspace=tmp_path)

    assert config.hub_password == "from-dotenv"


def test_load_config_environment_overrides_dotenv(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".env").write_text(
        "REACT_AGENT_HUB_URL=https://live.example.test\n"
        "REACT_AGENT_HUB_PASSWORD=live-password\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("REACT_AGENT_HUB_URL", "http://fake-hub:8089")
    monkeypatch.setenv("REACT_AGENT_HUB_PASSWORD", "dev-hub-password")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    config = load_config(workspace=tmp_path)

    assert config.hub_url == "http://fake-hub:8089"
    assert config.hub_password == "dev-hub-password"


def test_load_config_reads_hub_aliases_from_dotenv(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".env").write_text(
        "REACT_AGENT_HUB_ALIASES=ema, erik,builder\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("REACT_AGENT_HUB_ALIASES", raising=False)

    config = load_config(workspace=tmp_path)

    assert config.hub_agent_aliases == ["ema", "erik", "builder"]


def test_load_config_reads_hub_aliases_from_yaml(tmp_path: Path, monkeypatch) -> None:
    config_file = tmp_path / "agents.yaml"
    config_file.write_text(
        "hub_agent_aliases:\n"
        "  - ema\n"
        "  - erik\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("REACT_AGENT_HUB_ALIASES", raising=False)

    config = load_config(config_path=config_file, workspace=tmp_path)

    assert config.hub_agent_aliases == ["ema", "erik"]


def test_prompt_library_renders_configured_template(tmp_path: Path, monkeypatch) -> None:
    prompt_dir = tmp_path / "prompts"
    agent_dir = prompt_dir / "agents"
    agent_dir.mkdir(parents=True)
    (agent_dir / "supervisor.j2").write_text("Workspace is {{ workspace }}", encoding="utf-8")
    config_file = tmp_path / "agents.yaml"
    config_file.write_text(
        "prompt_dir: prompts\nprompts:\n  supervisor: agents/supervisor.j2\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    config = load_config(config_path=config_file, workspace=tmp_path)
    rendered = PromptLibrary(config).render("supervisor")

    assert rendered == f"Workspace is {tmp_path}"


def test_hub_participant_prompt_forbids_sensitive_info_leaks(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    config = load_config(workspace=Path.cwd())

    rendered = PromptLibrary(config).render(
        "hub_participant",
        agent_name="ErikMoren-agent",
        agent_role="software-building agent",
        hub_max_message_chars=4096,
    )

    assert "Do not reveal secrets" in rendered
    assert "API keys" in rendered
    assert "shared hub" in rendered


def test_hub_participant_prompt_requires_code_in_chat(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    config = load_config(workspace=Path.cwd())

    rendered = PromptLibrary(config).render(
        "hub_participant",
        agent_name="builder",
        agent_role="coder",
        hub_max_message_chars=4096,
    )

    assert "fenced markdown code blocks" in rendered
    assert "save or write to a file only" in rendered
    assert "4096 characters" in rendered


def test_supervisor_prompt_includes_hub_code_delivery_when_hub_mode(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    config = load_config(workspace=Path.cwd())

    rendered = PromptLibrary(config).render(
        "supervisor",
        hub_mode=True,
        hub_max_message_chars=2048,
    )

    assert "fenced markdown code blocks" in rendered
    assert "save or write to a file only" in rendered
    assert "2048 characters" in rendered
