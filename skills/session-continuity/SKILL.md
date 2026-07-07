---
name: session-continuity
description: Use when starting or ending a working session, writing a handoff prompt for a future session, or deciding where session notes and project profiles should live — including when a session is about to end with undocumented decisions, or notes are about to be written inside a project repo.
---

# session-continuity

## Overview

Sessions die; context shouldn't. This skill defines one durable, portable home
for cross-session context — **outside every project repo** — and the shape of
the three artifacts that live there: project profiles, session notes, and
handoffs. The `/session-start`, `/session-end`, `/handoff`, and
`/project-profile` commands all follow these conventions.

Core principle: **project repos hold code and project-owned config; everything
about *your* work on them lives in the notes home.** A note inside a repo is
one `git add -A` away from being published.

## The notes home

```
~/.claude-kit/                        # or $CLAUDE_KIT_NOTES_DIR if set
  private-denylist.txt                # personal terms for check-private-info
  projects/<project>/
    profile.md                        # durable facts: gates, commands, safety notes
    sessions/YYYY-MM-DD-<slug>.md     # one note per session
    handoffs/YYYY-MM-DD-<slug>.md     # paste-ready prompts for future sessions
```

- `<project>` = the repo's directory basename, kebab-cased: lowercase, every
  run of non-`[a-z0-9]` characters collapses to a single `-`, and leading/
  trailing `-` are trimmed (`My_App.v2` → `my-app-v2`, `My  App!!` → `my-app`).
  `bin/slugify.sh` is the canonical implementation of this rule (with a
  `--self-test`); pipe a name through it rather than hand-deriving edge cases.
- `<slug>` = 2–5 kebab-case words naming the session's goal, same rule. Never
  put `/`, spaces, or personal names in filenames.
- Honor `CLAUDE_KIT_NOTES_DIR` when set: it replaces `~/.claude-kit` as the
  base. Pointing it at an Obsidian vault directory makes every note appear in
  the vault — plain Markdown is all Obsidian needs. Nothing here may *require*
  Obsidian (no plugin syntax, no sync assumptions).
- Create directories on demand (`mkdir -p`). Plain Markdown only.

## Rules

1. **Read-only toward the project repo.** Starting or ending a session, or
   writing a handoff, must not modify the repo being worked on. The only
   exception: the user *explicitly* asks for content in the repo (a
   `/project-profile` export, or "put the session summary in the repo/PR"). An
   explicit request is honored — but only via the **Repo-bound content** recipe
   below, never by writing the raw note into the repo.
2. **Notes are private by default.** Write them for yourself: local paths and
   blunt assessments are fine *in the notes home*. Content destined for a repo
   is a different artifact — see the recipe below; it is always the sanitized
   summary, never the private note.

## Repo-bound content (only on explicit request)

A raw session note in the repo is the leak this skill exists to close, so an
explicit "put it in the repo/PR" request does **not** relax the default — it
produces two separate artifacts:

1. **Full private note → notes home, always.** Write it first, in full (local
   paths, blunt risk notes, the next-prompt). This is the durable record;
   losing it to a repo-only write breaks cross-session continuity.
2. **Sanitized summary → the repo, only after the scanner passes.** Then, and
   only then, produce a *separate* teammate-facing summary and:
   - sanitize per claude-kit's `docs/privacy-boundaries.md` — repo-relative
     paths only, no personal names/emails/denylist terms, no pasted transcript,
     no private "next-prompt for future-me" meta;
   - **run the scanner and block on it.** If the claude-kit repo is reachable,
     run `bin/check-private-info.sh <the summary file>`; if it flags anything,
     do **not** leave the file in the repo — fix and re-run until it passes. A
     manual `grep` is not a substitute for running the scanner.
   - write it to the path the user named (or propose one and confirm); leave it
     **unstaged and uncommitted** — staging is the user's call.

If the claude-kit repo isn't reachable to run the scanner, say so and let the
user decide, rather than writing an unscanned summary into the repo.
3. **Handoffs state scope boundaries.** A handoff that says only what to do
   next invites the next session to redo or bulldoze finished work. Always
   include what is DONE (don't redo), what is OUT of scope, and what must not
   be touched.
4. **Don't duplicate the repo's own memory.** Facts that belong to the project
   (build commands every contributor uses, architecture) belong in the
   project's CLAUDE.md/docs — the profile *points* at them and records what the
   repo can't: your gates, your risk notes, your recurring instructions.

## Session note shape (written by /session-end)

```markdown
# YYYY-MM-DD <goal, one line>
repo / branch / commits made / files changed
tests-checks: what ran, pass/fail
decisions: what was chosen and why (one line each)
risks: what could bite later
deferred: what was consciously not done
candidate workflow improvements: (see claude-kit's `docs/iterative-improvement.md`)
next: the single best next prompt
```

Precision beats prose: a future session greps these files.

## Common mistakes

- Writing the raw session note into the project repo — even when the user asks
  for it in the repo/PR. The note itself always goes to the notes home; only a
  scanned, sanitized *summary* goes to the repo, per **Repo-bound content**.
  "The user explicitly asked" is honored *through that recipe*, not by dumping
  the private note into the repo.
- Treating a manual `grep` as the privacy check. When a summary is repo-bound,
  the recipe says *run `bin/check-private-info.sh`* — a grep is not that.
- Writing a sanitized repo copy but skipping the full private note — the
  continuity record is the point; the repo copy is the extra, not the swap.
- A handoff without scope boundaries ("continue the work") — the next session
  re-litigates finished decisions.
- Stuffing the profile with things already in the project's README — it goes
  stale and drowns the personal signal.
- Blocking on a missing notes home — `mkdir -p` and continue; never ask the
  user to create directories.
