# Apply Template — Global Cursor Skill Setup

This document describes a global Cursor agent skill that lets you apply the `morre95/CursorProjectStart` template files into any existing project with a single chat command.

Once installed, you can say things like:

> *"Apply the cursor template to this project"*
> *"Bootstrap this project with the CursorProjectStart setup"*
> *"Copy the template files into this directory"*

...and the agent will download and apply all template files — including dotfiles like `.cursor/` and `.env.example` — into your current project. Your existing `README.md`, `.gitignore`, and `LICENSE` are automatically preserved and never overwritten.

---

## Prerequisites

- [GitHub CLI (`gh`)](https://cli.github.com/) installed and authenticated (`gh auth login`)
- `unzip` available in your shell

---

## Install the Skill

Tell your Cursor agent (in **Agent mode**):

> *"Create a global Cursor skill at `~/.cursor/skills/apply-template/SKILL.md` that downloads the `morre95/CursorProjectStart` template from GitHub using `gh api repos/morre95/CursorProjectStart/zipball` and applies it to the current project. It should: unzip to a temp folder; back up any existing `README.md`, `.gitignore`, and `LICENSE` with a `.bak` extension before moving files; use `shopt -s dotglob` so dotfiles are included; move everything with `bash -c 'shopt -s dotglob && mv tmp_template/*/* .'`; restore the backed-up files so they are never overwritten; clean up temp files; and ask the user for confirmation before starting."*

The agent will create the skill file at:

```
~/.cursor/skills/apply-template/SKILL.md
```

This is a **personal global skill** — it is available in every project you open in Cursor, not just this one.

---

## How It Works

When triggered, the agent runs these steps:

1. Asks for your confirmation
2. Downloads the template zip:
   ```bash
   gh api repos/morre95/CursorProjectStart/zipball --output template.zip
   ```
3. Extracts it:
   ```bash
   unzip template.zip -d tmp_template
   ```
4. Backs up any existing protected files so they are not lost:
   ```bash
   for f in README.md .gitignore LICENSE; do
     [ -f "$f" ] && cp "$f" "${f}.bak"
   done
   ```
5. Moves all files — including hidden dotfiles — into the current directory:
   ```bash
   bash -c 'shopt -s dotglob && mv tmp_template/*/* .'
   ```
6. Restores your originals over the template versions:
   ```bash
   for f in README.md .gitignore LICENSE; do
     [ -f "${f}.bak" ] && mv "${f}.bak" "$f"
   done
   ```
7. Cleans up:
   ```bash
   rm -rf tmp_template template.zip
   ```
8. Reports what was added

> **Why `shopt -s dotglob`?** By default, `*` in bash does not match files starting with `.`. Without this flag, `.cursor/` rules and other hidden template files would be silently skipped.

> **Protected files** (`README.md`, `.gitignore`, `LICENSE`) are always preserved if they already exist. On a brand-new project without these files, the template versions are used instead.
