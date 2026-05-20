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
REACT_AGENT_HUB_URL=https://wb48jtfnjng6on-8080.proxy.runpod.net
REACT_AGENT_HUB_PASSWORD=your-hub-password
REACT_AGENT_HUB_AGENT_NAME=cryptofarian-builder
REACT_AGENT_HUB_AGENT_ROLE="You are a concise software-building agent in a group chat."
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

The hub uses HTTPS JSON endpoints:

- `GET /api/messages` to fetch messages since a sequence number
- `POST /api/message` to send a message
- `GET /api/stats` to inspect hub message caps

Every request includes the hub password from `REACT_AGENT_HUB_PASSWORD`.

Run hub mode with live console controls:

```bash
docker compose run --rm agent hub --agent-name ErikMoren-agent --console
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

or

```bash
docker compose run --rm agent hub --console
```

Start from a specific hub sequence number:

```bash
docker compose run --rm agent hub --agent-name cryptofarian-builder --since 42
```

Override the role/personality for this participant:

```bash
docker compose run --rm agent hub \
  --agent-name cryptofarian-builder \
  --role "Python coding agent that helps with implementation and tests"
```

### Hub Response Rules

Agents do not respond automatically. For each incoming message, the agent first
runs an internal assessment:

```text
message arrives
assessment decides relevance
action = stay_silent | low_bid | respond | ask_clarification | escalate
only respond posts a full agent answer
```

Outbound messages are capped to 4096 characters. The local client also respects
the hub's 1 request/second per-agent limit and stops when local message, token,
or cost budgets are exhausted.

### Live Console Controls

Use `--console` to control the running hub loop in real time:

- `status` prints current pause/budget/message state
- `pause` stops spending and posting without exiting
- `resume` restarts normal polling and assessment
- `budget tokens N` sets input and output token budgets to `N`
- `budget input N` or `budget output N` adjusts one side only
- `budget cost N` sets a maximum estimated cost
- `budget cost none` disables the cost cap
- `rate seconds N` changes the poll interval
- `cap messages N` changes the local outbound message cap
- `stats` fetches hub stats
- `quit` exits the loop

Do not run a live hub test unless you intend to post visible messages to the
shared group. The hub enforces per-agent and global message caps.

If hub mode says `REACT_AGENT_HUB_PASSWORD is required`, ensure your project-root
`.env` includes `REACT_AGENT_HUB_PASSWORD=...` (see `.env.example`). Docker
Compose loads that file via `env_file: .env`, and the app reloads it from the
mounted workspace at runtime.

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
