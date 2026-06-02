# ReAct Agent System

CLI-first agentic coding system built with Python, LangGraph, and OpenRouter. LangGraph is used to help with this otherwise complex work-flow. The system includes specialist agents for planning, coding, review, testing, debugging, repo/tool work, summarization, and focused code writing.

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

Post a goodbye message to the hub when the agent signs off. This is off by
default, so the agent leaves silently unless you pass `--goodbye`:

```bash
docker compose run --rm agent hub --agent-name cryptofarian-builder --goodbye
```

### Team Roles, Calibration, and Memory

Hub mode is tuned to behave as a collaborative team-player rather than a solo
programmer. The behavior is described in the agent's **static system prompt**, so it
survives history trimming and is never compressed away:

- **Team-player vs manager.** By default the agent is a team-player: it claims exactly
  one task and works on it. Run it as the team manager (proposes and integrates the
  plan, declares `DONE`, does not implement subtasks) with `--manager` or
  `hub_agent_is_manager: true`. A team-player may still propose a plan itself if none
  exists after `hub_plan_fallback_rounds` assessment rounds, so the chat never deadlocks.
- **Fast in dialogue, deep with tools.** The prompt instructs the agent to keep
  coordination posts short and quick, but to take its time doing thorough work silently
  with its tools before posting one concise result.
- **Important-message retention.** When the recent-message window slides, the plan, task
  claims, and `DONE` markers are pinned (up to `hub_pinned_messages`) so they stay in the
  context the agent reasons over even if the full chat is not kept.
- **Context caching.** The agent reuses one stable thread per session and keeps the
  large system prompt as a stable prefix, so the OpenAI/OpenRouter automatic prompt cache
  is reused across rounds. `hub_history_max_messages` bounds the thread so long sessions
  do not overflow the context window.

#### Live calibration via a runtime file

Point `hub_runtime_config_path` at a small YAML file (see
`config/hub-runtime.example.yaml`). It is re-read at the start of every poll round, so you
can calibrate prompts and behavior without restarting:

```yaml
is_manager: false        # flip the role live
extra_instruction: ""    # one-off nudge appended to the agent's task this round
paused: false            # pause posting without quitting
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

## Local Fake Hub

Use the fake hub to test hub mode without connecting to the live RunPod URL. It
implements the same local API shape as the TH25 hub plus development endpoints
for seeding and inspecting messages.

Start the fake hub:

```bash
docker compose up --build --force-recreate fake-hub
```

Open the local message view in your browser:

```text
http://localhost:8089/
```

Seed a message that should stay silent because it does not address the agent:

```bash
curl -X POST http://localhost:8089/api/seed \
  -H 'Content-Type: application/json' \
  -d '{"agent_name":"human","content":"Can someone summarize their role?","password":"dev-hub-password"}'
```

Seed a message that should pass the local addressed-message gate:

```bash
curl -X POST http://localhost:8089/api/seed \
  -H 'Content-Type: application/json' \
  -d '{"agent_name":"human","content":"ErikMoren-agent can you summarize your role?","password":"dev-hub-password"}'
```

Run one bounded fake-hub poll from the agent container:

```bash
docker compose run --rm \
  -e REACT_AGENT_HUB_URL=http://fake-hub:8089 \
  -e REACT_AGENT_HUB_PASSWORD=dev-hub-password \
  agent hub --agent-name ErikMoren-agent --max-iterations 1
```

Inspect all stored messages and stats as JSON:

```bash
curl -s "http://localhost:8089/api/messages?since=0&password=dev-hub-password" | python -m json.tool
```

Stop the fake hub when you are done:

```bash
docker compose stop fake-hub
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



## Körlogg

```bash
del3 main via 🐍 v3.14.4 (.venv) ✗ react-agent "tell me a joke"
Why do programmers prefer dark mode?

Because light attracts bugs.
```

```bash
del3 main via 🐍 v3.14.4 (.venv) ❯ python -m react_agent_system.cli "what joke did you just tell me"
I told you this joke:

“Why do programmers prefer dark mode? Because light attracts bugs.”
```

```bash
del3 main  via 🐍 v3.14.4 (.venv) ✗ react-agent "Vad är det för väder i Stockholm"
Just nu i Stockholm är det **klart väder** och cirka **17,1 °C** (känns som **15,2 °C**).
**Vind:** ca **13 km/h**. **Nederbörd:** **0,0 mm**. **Luftfuktighet:** **63 %**.
```


### Run tests:
Locally
```bash
python -m pytest
```
or run tests in docker:
```bash
docker compose run --rm --entrypoint /bin/sh agent -lc 'python -m pip install --user pytest >/tmp/dev-install.log && python -m pytest'
```

