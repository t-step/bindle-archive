---
description: Orient a new session — repo state, project profile, prior notes, validation gates
argument-hint: [objective]
allowed-tools: Bash(git status:*), Bash(git branch:*), Bash(git log:*), Bash(date:*)
---

<!-- Conventions (notes home layout, slug rules, privacy):
     the session-continuity skill is the source of truth — read it first. -->

Orient this session. **Read-only:** do not modify, create, or delete any file
in this repo during orientation.

Current repo state:

- today: !`date +%F`
- branch: !`git branch --show-current`
- status: !`git status --short --branch`
- recent commits: !`git log --oneline -10`

Steps:

1. Read the `session-continuity` skill for the notes-home conventions.
2. Locate durable context: with the notes base `$CLAUDE_KIT_NOTES_DIR` (or
   `~/.claude-kit` if unset), look under `projects/<project>/` for
   `profile.md`, the most recent file in `sessions/`, and the most recent in
   `handoffs/`. Read what exists; say plainly if nothing does (and suggest
   `/project-profile` once — don't nag).
3. Identify the validation gates for this repo: from the profile if it lists
   them, otherwise infer from the repo (Makefile, CI workflow, test config,
   pre-commit config, CONTRIBUTING/CLAUDE.md). Don't run them yet.
4. Summarize in ≤15 lines: where the repo stands, what the last session
   finished/deferred (per notes), the gates that must pass before committing,
   and any safety notes from the profile (branch discipline, "never touch X").
5. Objective: if the user provided one ("$ARGUMENTS"), restate it as the
   session goal and note anything in the profile/handoff that conflicts with
   it. If none was provided and the latest handoff names a clear next step,
   propose that. Only ask for an objective if you have neither.

Then stop and wait for direction. Do not start work, run gates, or "clean up"
anything you noticed during orientation.
