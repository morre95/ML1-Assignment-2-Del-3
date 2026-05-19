# Cursor Playbook

A production-ready `.cursor/` directory template that enforces professional software engineering standards in any project using [Cursor](https://cursor.com).

Drop it into a new repo and start building with guardrails from day one.

> If you find this useful, a star helps others discover it too.

---

## Why This Exists

Cursor is powerful, but without guardrails it will:
- Introduce bandaid fixes instead of addressing root causes
- Build components in isolation that drift from the rest of the system
- Leave dead code, duplicate models, and inconsistent patterns behind
- Produce N+1 queries, silent error swallowing, and hardcoded secrets

This template prevents that. It provides **rules** (loaded every session), **skills** (reusable workflows), and **hooks** (automated checks) — all configured and ready to use.

---

## What's Included

```
.cursor/
├── hooks.json                         # Hook registry
│
├── rules/                             # Loaded automatically every session
│   ├── project-instructions.mdc       # Project commands, style, platform, architecture
│   ├── agent-behavior.mdc             # Communication, verification, self-review
│   ├── code-quality.mdc               # No dead code, no bandaids, root-cause fixes
│   ├── engineering-principles.mdc     # DRY, YAGNI, KISS, SRP, code smells, naming
│   ├── architecture.mdc               # Separation of concerns, dependency direction
│   ├── api-design.mdc                 # REST conventions, response format, pagination
│   ├── error-handling.mdc             # Structured errors, custom exceptions, fail fast
│   ├── security.mdc                   # OWASP, secrets, auth, input validation
│   ├── database.mdc                   # Schema design, constraints, query patterns
│   ├── alembic.mdc                    # Migration best practices (Python/SQLAlchemy)
│   ├── frontend.mdc                   # Components, state management, TypeScript
│   ├── frontend-consistency.mdc       # Reuse before create, no visual drift
│   ├── testing.mdc                    # Test types, structure, reliability
│   ├── performance.mdc                # Query optimization, caching, async patterns
│   ├── git-workflow.mdc               # Commits, branches, PR standards
│   ├── llm-prompts.mdc               # Jinja2 templates for prompt management
│   ├── python-standards.mdc           # Python-specific (only loads for .py files)
│   └── common-mistakes.mdc           # Project-specific pitfalls (you populate this)
│
├── skills/                            # On-demand workflows invoked by the agent
│   ├── review/SKILL.md               # Pre-commit code review against all rules
│   ├── fix-issue/SKILL.md            # End-to-end GitHub issue resolution
│   ├── review-pr/SKILL.md            # Structured PR review
│   └── security-reviewer/SKILL.md    # Delegated security audit via subagent
│
└── hooks/                             # Automated scripts on agent events
    └── lint-on-edit.sh               # Auto-lint after every file edit

agent-docs/                            # Session memory — agent notes that persist across chats
└── README.md                          # Explains the pattern
```

### Understanding the Components

Cursor has three extension mechanisms. Each serves a different purpose and fires at a different time.

#### Rules — "Always think this way"

Rules (`.mdc` files with `alwaysApply: true`) are loaded into the agent's context at the start of **every session**. They shape how the agent reasons about your code — what patterns to follow, what to avoid, what standards to enforce.

**Use rules for**: engineering principles, coding standards, architectural patterns, naming conventions — anything that requires AI judgment to apply.

**Examples**: "No N+1 queries", "Use custom exceptions not bare HTTPException", "Reuse existing components before creating new ones"

Rules can also be scoped to specific file types using the `globs` frontmatter field:

```yaml
---
description: TypeScript conventions
globs: **/*.ts
alwaysApply: false
---
```

#### Skills — "Do this workflow when I ask"

Skills are multi-step workflows stored in `.cursor/skills/*/SKILL.md`. The agent reads and follows them when the user invokes a relevant request. Skills use the agent's full reasoning — reading files, analyzing code, making decisions.

**Use skills for**: code review, issue fixing, PR review, security audits — complex workflows that are too expensive to run automatically but valuable when invoked deliberately.

**Examples**: "review my changes before I commit", "fix issue 123", "review PR 456"

#### Hooks — "Run this script automatically, every time"

Hooks are **shell scripts** that fire automatically on specific agent events. They are **deterministic** — they execute every time, no exceptions, no AI judgment involved.

**Use hooks for**: linting, formatting, type-checking — fast, deterministic checks that don't need AI reasoning.

**Hook trigger events**:

| Event | When it fires | Use case |
|-------|--------------|----------|
| `afterFileEdit` | After the agent edits a file | Lint/format the file just edited |
| `beforeShellExecution` | Before the agent runs a shell command | Block or audit risky commands |
| `preToolUse` | Before the agent uses a tool | Intercept/modify tool calls |
| `postToolUse` | After a tool call succeeds | Add follow-up context |
| `sessionStart` / `sessionEnd` | Session lifecycle | Setup or audit |
| `stop` | Agent finishes responding | Run tests after agent is done |

Hooks receive event data as JSON on stdin and respond with JSON on stdout.

#### Choosing the Right One

```
Need AI reasoning?
├── Yes
│   ├── Should it run every session? → Rule
│   └── Should it run on demand?     → Skill
└── No (deterministic script)        → Hook
```

| Scenario | Right choice | Why |
|----------|-------------|-----|
| "Always use ApiResponse wrapper" | **Rule** | Needs AI judgment during code generation |
| "Review my changes before I commit" | **Skill** | Expensive AI analysis, run deliberately |
| "Audit this code for security issues" | **Skill** (security-reviewer) | Runs in isolated subagent |
| "Lint every file after edit" | **Hook** | Fast shell script, must happen every time |
| "Block commits to production branch" | **Hook** | Deterministic check, no AI reasoning required |

---

## Getting Started

### Starting a new project (recommended)

Use this repo as a **GitHub template**:

(Optional)
If you have not added the skill to clone this repo. Follow docs/apply-template-skill.md

1. Click the green **"Use this template"** button at the top of this repo
2. Choose **"Create a new repository"**
3. Name your repo, set visibility, and click **"Create"**
4. Clone your new repo — it already has the full `.cursor/` scaffolding

From the command line:

```bash
gh repo create my-new-project --template morre95/CursorProjectStart --public --clone
cd my-new-project
```

**After creating your repo:**

1. Edit `.cursor/rules/project-instructions.mdc` — replace the template commands with your actual build/test/lint commands
2. Remove rules that don't apply (no database? delete `database.mdc` and `alembic.mdc`)
3. Add project-specific details to the rules you keep
4. Start building — Cursor picks up the rules automatically

### Adding to an existing project

```bash
# From your project root
cp -r /path/to/cursor-playbook/.cursor/ .cursor/
cp -r /path/to/cursor-playbook/agent-docs/ agent-docs/
```

Then customize `project-instructions.mdc` with your project's commands, style, and architecture.

---

## Customizing for Your Project

### Step 1: Edit `project-instructions.mdc`

Replace the template commands with your actual build, test, and lint commands.

### Step 2: Make rules project-specific

The rules are intentionally generic. After copying, add your project's real file paths, class names, and patterns:

**Generic (template):**
> Use custom exception classes instead of framework-default exceptions

**Project-specific (customized):**
> Use `NotFoundError`, `BadRequestError`, `ForbiddenError` from `app/core/exceptions.py`. Handlers registered in `main.py:72-125` return `{"success": false, "error": {"code": "...", "message": "..."}}`

### Step 3: Remove what doesn't apply

- No database? Delete `database.mdc` and `alembic.mdc`
- No frontend? Delete `frontend.mdc` and `frontend-consistency.mdc`
- No LLM features? Delete `llm-prompts.mdc`
- No Python? Delete `python-standards.mdc` (it only loads for `.py` files anyway)

### Step 4: Add domain-specific rules

Create new `.mdc` files for your domain:

```
.cursor/rules/
├── payments.mdc       # PCI compliance, transaction handling
├── ml-pipeline.mdc    # Model versioning, data validation
└── infrastructure.mdc # Terraform conventions, deployment rules
```

### Step 5: Scope rules to specific file types (optional)

```yaml
---
description: Backend API rules
globs: src/api/**/*.ts
alwaysApply: false
---

# Backend API Rules
These rules only apply when working with backend API files.
```

---

## Rules Reference

### Core Principles
| File | What it enforces |
|------|-----------------|
| `project-instructions.mdc` | Commands, code style, platform/environment, workflow, architecture |
| `agent-behavior.mdc` | Communication style, verification standards, linter discipline, self-review checklist |
| `code-quality.mdc` | No dead code, no bandaid fixes, root-cause solutions only |
| `engineering-principles.mdc` | DRY, YAGNI, KISS, Single Responsibility, code smells, naming |
| `architecture.mdc` | Separation of concerns, dependency direction, single source of truth |
| `common-mistakes.mdc` | Project-specific pitfalls — you populate this as mistakes occur |

### Backend
| File | What it enforces |
|------|-----------------|
| `api-design.mdc` | REST resource naming, consistent response envelope, pagination, HTTP status codes |
| `error-handling.mdc` | Custom exception classes, structured error responses, no silent swallowing |
| `security.mdc` | OWASP top 10, secrets in env vars, auth on all mutations, parameterized queries |
| `database.mdc` | One model per table, constraints at DB level, no N+1 queries, transactions |
| `alembic.mdc` | Idempotent migrations, reversible up/down, dangerous operation safety |
| `python-standards.mdc` | Type hints, imports, naming, explicit params, `pathlib` (only loads for `.py` files) |

### Frontend
| File | What it enforces |
|------|-----------------|
| `frontend.mdc` | Single API client, store patterns, TypeScript strictness, controlled forms |
| `frontend-consistency.mdc` | Reuse before create, no bubble development, design system tokens |

### Process
| File | What it enforces |
|------|-----------------|
| `testing.mdc` | Test pyramid, Arrange-Act-Assert, deterministic tests, regression tests |
| `performance.mdc` | Profile before optimizing, batch queries, pagination, lazy load routes |
| `git-workflow.mdc` | Imperative commit messages, one change per commit, feature branches, small PRs |
| `llm-prompts.mdc` | Jinja2 templates in `prompts/` directory, versioned, composable |

---

## Skills Reference

Skills activate when you ask the agent to perform the corresponding workflow.

| Skill | Ask the agent | What it does |
|-------|--------------|-------------|
| `review` | "review my changes" | Reviews all uncommitted changes against project rules — run before committing |
| `fix-issue` | "fix issue 123" | Reads the GitHub issue, investigates the codebase, implements a fix, writes tests, creates a PR |
| `review-pr` | "review PR 456" | Reviews a PR for correctness, architecture, security, and test coverage |
| `security-reviewer` | "audit this for security issues" | Runs a security audit in an isolated subagent |

### Creating your own skills

Add a directory with a `SKILL.md` to `.cursor/skills/`:

```
.cursor/skills/your-skill/
└── SKILL.md
```

SKILL.md requires YAML frontmatter with `name` and `description`:

```markdown
---
name: your-skill
description: What this skill does and when to use it. Use when the user asks...
---

# Your Skill

Instructions for the agent...
```

---

## Hooks Reference

Hooks run automatically at specific points in the agent's workflow.

| Hook | Trigger | What it does |
|------|---------|-------------|
| `lint-on-edit.sh` | After any file edit | Runs ruff (Python) or ESLint (JS/TS) on the edited file |

The hook registry is in `.cursor/hooks.json`. To add or modify hooks, edit that file directly.

### Linter requirements

The `lint-on-edit.sh` hook requires:
- Python files: [`ruff`](https://github.com/astral-sh/ruff) on `$PATH`
- JS/TS files: `npx` available (uses project-local ESLint)

If a linter isn't installed, the hook exits silently — it won't break the agent.

### Creating your own hooks

Add entries to `.cursor/hooks.json`:

```json
{
  "version": 1,
  "hooks": {
    "afterFileEdit": [
      {
        "command": ".cursor/hooks/lint-on-edit.sh"
      }
    ],
    "beforeShellExecution": [
      {
        "command": ".cursor/hooks/approve-network.sh",
        "matcher": "curl|wget",
        "failClosed": true
      }
    ]
  }
}
```

Hook scripts receive event data as JSON on stdin. Exit code `0` = success, `2` = block the action.

---

## Agent Docs — Session Memory

The `agent-docs/` folder at the project root is the agent's persistent memory. When working on complex tasks, the agent writes notes here about decisions, debugging solutions, and project state. These notes survive across chat sessions, so the next conversation picks up where the last one left off.

You can also ask the agent to "write a summary of what we did" at the end of a session. Periodically review and clean up stale notes.

---

## Growth Path

Not every rule needs to be active from day one. Start with the defaults and add rules when you feel the pain they solve. Every rule costs context window tokens on every response — keep your setup lean.

**Add soon** (high value, low complexity):
- Populate `common-mistakes.mdc` as you encounter repeated agent errors — this compounds with every session
- Fill in the Platform / Environment section of `project-instructions.mdc`
- Start using `agent-docs/` for session memory on complex tasks

**Add when you've hit the problem**:
- Language-specific rules beyond `python-standards.mdc` (e.g., `rust-standards.mdc`, `go-standards.mdc`)
- Domain-specific rules (`payments.mdc`, `ml-pipeline.mdc`, `infrastructure.mdc`)
- File-scoped rules with `globs` for conventions that only apply to certain file types

**What to skip**: Don't add rules for problems you haven't encountered. A rule that fires every session but prevents a problem you've never had is pure overhead.

---

## Contributing

Contributions welcome. If you have rules that have proven valuable across real projects, open a PR.

Guidelines:
- Rules must be **generic and framework-agnostic** — no project-specific file paths or class names
- Each rule should prevent a **concrete, common problem** — not generic advice like "write clean code"
- Keep rules actionable: "Never query inside a loop" is enforceable; "Write performant code" is not
- One topic per file, descriptive filename

---

## License

[MIT](LICENSE) — use, modify, and distribute freely.
