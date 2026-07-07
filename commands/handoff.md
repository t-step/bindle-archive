---
description: Generate a clean, scope-bounded prompt for a future session (Claude Code, Fable, or Codex)
argument-hint: [focus for the next session]
allowed-tools: Bash(git status:*), Bash(git branch:*), Bash(git log:*), Bash(date:*), Bash(mkdir -p:*)
---

<!-- Conventions (notes home layout, slug rules, privacy):
     the session-continuity skill is the source of truth — read it first. -->

Write a handoff: a single self-contained prompt a future session can start
from cold — any harness (Claude Code, Fable, Codex), no access to this
conversation. Requested focus, if any: "$ARGUMENTS"

Current repo state:

- today: !`date +%F`
- branch: !`git branch --show-current`
- status: !`git status --short --branch`
- recent commits: !`git log --oneline -15`

Steps:

1. Read the `session-continuity` skill; resolve the notes home and
   `projects/<project>/handoffs/`; `mkdir -p` as needed.
2. Draft the handoff prompt with exactly these sections:
   - **Repo** — name/path and how to get oriented (key docs to read first);
   - **Current state** — branch, what's committed vs. uncommitted, CI/check
     status as last observed;
   - **Objective** — the goal the next session should pursue;
   - **Completed — do not redo** — finished work and decisions already made,
     so they aren't re-litigated;
   - **Changed files** — where the work lives;
   - **Key decisions** — one line each, with the why;
   - **Tests/checks** — what gates exist, what currently passes;
   - **Known risks** — sharp edges the next session must know;
   - **Scope boundaries** — explicitly out of scope; files/areas not to touch;
     "stop and report" points;
   - **Next steps** — concrete, ordered, smallest-first.
3. Write it honestly: unverified means unverified. A handoff that oversells
   state wastes the next session's first hour.
4. Save to `handoffs/YYYY-MM-DD-<slug>.md` in the notes home — never into this
   repo. If the user wants it committed somewhere (a PR description, a doc),
   sanitize first per claude-kit's `docs/privacy-boundaries.md`: repo-relative paths only,
   no personal names/emails, no pasted transcript, and say that you did so.

Reply with the saved path, then the full handoff in one copy-pasteable block.
