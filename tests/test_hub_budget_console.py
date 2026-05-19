from pathlib import Path

from react_agent_system.config import DEFAULT_PROMPTS, AgentSystemConfig
from react_agent_system.hub.budget import BudgetController, estimate_tokens
from react_agent_system.hub.console import ConsoleController
from react_agent_system.hub.rate_limit import RateLimiter


def make_config(tmp_path: Path) -> AgentSystemConfig:
    return AgentSystemConfig(
        workspace=tmp_path,
        prompt_dir=Path.cwd() / "prompts",
        session_db=tmp_path / "history.sqlite3",
        model="test/model",
        openrouter_api_key="test-key",
        prompts=dict(DEFAULT_PROMPTS),
        hub_max_messages=1,
        hub_max_input_tokens=10,
        hub_max_output_tokens=10,
    )


def test_budget_blocks_after_message_cap(tmp_path: Path) -> None:
    budget = BudgetController(make_config(tmp_path))

    assert budget.check().can_spend
    budget.record_output_text("posted", posted=True)

    assert not budget.check().can_spend


def test_console_updates_runtime_budget(tmp_path: Path) -> None:
    budget = BudgetController(make_config(tmp_path))
    console = ConsoleController(budget, stats_callback=lambda: "stats-ok")

    assert console.execute("pause") == "paused"
    assert not budget.check().can_spend
    assert console.execute("resume") == "resumed"
    assert console.execute("budget tokens 123") == "token budget set to 123"
    assert console.execute("cap messages 3") == "message cap set to 3"
    assert console.execute("stats") == "stats-ok"


def test_rate_limiter_sleeps_until_next_slot() -> None:
    now = 0.0
    sleeps = []

    def clock() -> float:
        return now

    def sleeper(seconds: float) -> None:
        nonlocal now
        sleeps.append(seconds)
        now += seconds

    limiter = RateLimiter(1.0, clock=clock, sleeper=sleeper)

    limiter.wait()
    limiter.wait()

    assert sleeps == [1.0]


def test_estimate_tokens_has_minimum_for_non_empty_text() -> None:
    assert estimate_tokens("a") == 1
