# ReAct Agent System

CLI-first agentic coding system built with Python, LangGraph, and OpenRouter.
It includes specialist agents for planning, coding, review, testing, debugging,
repo/tool work, summarization, and focused code writing.

## Setup

Create a local `.env` file from the example and add your OpenRouter key:

```bash
cp .env.example .env
```

Required value:

```bash
OPENROUTER_API_KEY=your-openrouter-key
```

## Run With Docker Compose

Build the container:

```bash
docker compose build agent
```

Run a task:

```bash
docker compose run --rm agent "your task here"
```

Use a persistent session/thread:

```bash
docker compose run --rm agent --thread-id my-session "continue the previous task"
```

Auto-approve safe shell commands that pass the deny-list checks:

```bash
docker compose run --rm agent --yes-to-safe-commands "inspect the repo and run tests"
```

## File Access

Docker Compose mounts the repo into the container at `/workspace`, so files the
agent reads or edits there are the same files on your host machine.

Session history is stored at:

```text
sessions/agent-history.sqlite3
```

That path is ignored by git.

## Local Python Usage

If you install the package locally, run:

```bash
react-agent "your task here"
```

or:

```bash
python -m react_agent_system.cli "your task here"
```
