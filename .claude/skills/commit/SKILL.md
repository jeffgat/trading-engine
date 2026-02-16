---
name: commit
description: Stage and commit changes with a clear, concise message matching this repo's style.
disable-model-invocation: true
allowed-tools: Bash(git *)
---

# Git Commit

## Repo Commit Style

This project uses short, imperative commit messages without conventional-commit prefixes.

Examples from history:
- `Add pre-trade gates analysis and exploration`
- `Fix chart x-axis to show Eastern time`
- `Update backtest engine and add test checklist`
- `Refactor frontend with config bar and history`

Rules:
- Start with a verb: Add, Fix, Update, Refactor, Remove, Rename, Move
- No type(scope): prefix — just the plain message
- Keep subject under 60 characters
- No period at the end
- Add a body (blank line + paragraph) only for non-obvious changes

## Process

1. Run `git status` and `git diff` (staged + unstaged) to understand what changed
2. If nothing is staged, identify the relevant changed files and stage them (prefer specific files over `git add -A`)
3. Do NOT stage files that look like secrets (.env, credentials, tokens)
4. Draft a commit message that matches the style above
5. Show the user the proposed message and staged files before committing
6. Create the commit with:
   ```
   Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
   ```

## Arguments

If the user passes arguments (e.g., `/commit fix the ATR calculation`), use them as guidance for the message but still review the actual diff to ensure accuracy.
