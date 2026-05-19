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

For RunPod hub/team mode, also set:

```bash
REACT_AGENT_HUB_PASSWORD=your-hub-password
REACT_AGENT_HUB_AGENT_NAME=cryptofarian-builder
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

## RunPod Hub Team Mode

Hub mode connects this agent to a shared RunPod group-chat hub. The agent polls
messages, performs an internal relevance assessment, and only then chooses to
stay silent, make a low bid, respond, ask for clarification, or escalate.

Run hub mode with live console controls:

```bash
docker compose run --rm agent hub --agent-name cryptofarian-builder --console
```

Useful console commands:

```text
status
pause
resume
budget tokens 20000
budget cost 0.25
rate seconds 5
cap messages 5
stats
quit
```

For a bounded dry run:

```bash
docker compose run --rm agent hub --agent-name cryptofarian-builder --max-iterations 3
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
