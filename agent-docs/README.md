# Agent Docs — Session Memory

This folder is the agent's persistent memory across chat sessions. Notes written here survive when a conversation ends, so the next session picks up where the last one left off instead of starting from zero.

## What goes here

- **Decisions**: Why a particular approach was chosen over alternatives
- **Debugging solutions**: Fixes that weren't obvious and shouldn't be re-discovered
- **Project state**: What's in progress, what's blocked, what's next
- **Gotchas**: Non-obvious behaviors discovered during development

## How it works

The agent is instructed (via `.cursor/rules/agent-behavior.mdc`) to write notes here when working on complex tasks. You can also ask the agent to "write a summary of what we did" at the end of a session.

## File naming

Use descriptive filenames:

```
agent-docs/
├── README.md              # This file
├── auth-flow-decisions.md # Why we chose JWT over sessions
├── db-migration-gotchas.md # Issues discovered during schema changes
└── current-sprint.md      # What's in progress right now
```

## Maintenance

Periodically review and clean up stale notes. Delete docs for completed work that's no longer relevant. This folder should stay lean — it's a working notebook, not an archive.
