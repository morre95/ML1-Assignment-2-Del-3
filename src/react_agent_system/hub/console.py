"""Live console controls for hub team mode."""

from __future__ import annotations

from collections.abc import Callable
from threading import Thread

from react_agent_system.hub.budget import BudgetController

StatsCallback = Callable[[], str]


class ConsoleController:
    """Parses and applies live hub commands."""

    def __init__(
        self,
        budget: BudgetController,
        stats_callback: StatsCallback | None = None,
    ) -> None:
        self.budget = budget
        self.stats_callback = stats_callback
        self.should_quit = False

    def execute(self, command: str) -> str:
        parts = command.strip().split()
        if not parts:
            return ""

        match parts:
            case ["status"]:
                return self.budget.status().model_dump_json()
            case ["pause"]:
                self.budget.set_paused(True)
                return "paused"
            case ["resume"]:
                self.budget.set_paused(False)
                return "resumed"
            case ["budget", "tokens", value]:
                token_budget = int(value)
                self.budget.set_token_budget(
                    max_input_tokens=token_budget,
                    max_output_tokens=token_budget,
                )
                return f"token budget set to {token_budget}"
            case ["budget", "input", value]:
                self.budget.set_token_budget(max_input_tokens=int(value))
                return f"input token budget set to {value}"
            case ["budget", "output", value]:
                self.budget.set_token_budget(max_output_tokens=int(value))
                return f"output token budget set to {value}"
            case ["budget", "cost", "none"]:
                self.budget.set_cost_budget(None)
                return "cost budget disabled"
            case ["budget", "cost", value]:
                self.budget.set_cost_budget(float(value))
                return f"cost budget set to {value}"
            case ["rate", "seconds", value]:
                self.budget.set_poll_interval(float(value))
                return f"poll interval set to {value} seconds"
            case ["cap", "messages", value]:
                self.budget.set_message_cap(int(value))
                return f"message cap set to {value}"
            case ["stats"]:
                if self.stats_callback is None:
                    return "stats callback is not configured"
                return self.stats_callback()
            case ["quit"] | ["exit"]:
                self.should_quit = True
                return "quitting"
            case ["help"]:
                return help_text()
            case _:
                return "unknown command; type 'help'"

    def start_background_reader(self) -> Thread:
        thread = Thread(target=self._read_commands, daemon=True)
        thread.start()
        return thread

    def _read_commands(self) -> None:
        while not self.should_quit:
            try:
                command = input("hub> ")
            except EOFError:
                self.should_quit = True
                return
            output = self.execute(command)
            if output:
                print(output)


def help_text() -> str:
    return (
        "commands: status, pause, resume, budget tokens N, budget input N, "
        "budget output N, budget cost N, budget cost none, rate seconds N, "
        "cap messages N, stats, quit"
    )
