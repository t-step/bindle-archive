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
~/.bindle/                            # or $BINDLE_NOTES_DIR if set
  private-denylist.txt                # personal terms for check-private-info
  projects/<project>/
    profile.md                        # curated runbook + pointer index — NOT a fact store
    profile-proposals.md              # pending profile.md Add/Defer/Reject queue
    facts/                            # canonical per-fact store — one durable fact per file
      MEMORY.md                       # Claude Code's auto-index (harness-managed)
      <fact-slug>.md                  # one fact; harness frontmatter schema (see "Fact files")
    sessions/YYYY-MM-DD-<slug>.md     # one note per session
    handoffs/YYYY-MM-DD-<slug>.md     # paste-ready prompts for future sessions
    breadcrumbs.log                   # opt-in SessionEnd hook only — NOT a note
```

- `<project>` = the repo's directory basename, kebab-cased: lowercase, every
  run of non-`[a-z0-9]` characters collapses to a single `-`, and leading/
  trailing `-` are trimmed (`My_App.v2` → `my-app-v2`, `My  App!!` → `my-app`).
  `<bindle>/bin/slugify.sh` — at the root of your Bindle checkout, *not* the
  repo you're working in (the installed skill dir ships only this `SKILL.md` as
  a symlink into `<bindle>/skills/session-continuity/`; resolve it to find
  `<bindle>`) — is the canonical implementation of this rule (with a
  `--self-test`); pipe a name through it rather than hand-deriving edge cases.
- `<slug>` = 2–5 kebab-case words naming the session's goal, same rule. Never
  put `/`, spaces, or personal names in filenames.
- Honor `BINDLE_NOTES_DIR` when set: it replaces `~/.bindle` as the base.
  Deprecated `CLAUDE_KIT_NOTES_DIR` and `~/.claude-kit` aliases remain
  supported. Pointing the notes dir at an Obsidian vault directory makes every
  note appear in the vault — plain Markdown is all Obsidian needs. Nothing here
  may *require* Obsidian (no plugin syntax, no sync assumptions).
- Create directories on demand (`mkdir -p`). Plain Markdown only.

`profile.md` is a curated runbook + pointer index, not a fact store. Its seven
sections (unchanged, so the tooling contract holds) are each **either** a small
inline *runbook block* (the gate list, canonical commands — glance-before-you-
touch, loaded wholesale every session) **or** a *pointer list* of `[[fact]]`
+ a one-line hook (long-form safety notes, recurring instructions, context
locations). Keep a fact inline only if you need it in context **every** session;
shed on-demand reference to `facts/` and leave a pointer. profile.md points; it
does not restate.

## Fact files (`facts/`)

A fact file holds one durable fact. Its format is **Claude Code's per-fact
memory schema, adopted verbatim**, so one physical store round-trips through the
harness unchanged — Bindle does not invent a competing schema.

```
---
name: <slug matching the filename>
description: "<one-line summary — used for relevance-loading>"
metadata:
  node_type: memory
  type: feedback | project | reference | user
  originSessionId: <uuid>            # harness-written; tolerate, never require
  modified: <ISO-8601 datetime, ms + Z, e.g. 2026-07-21T20:22:05.367Z>
---

<the fact>. For feedback/project facts, follow with **Why:** and
**How to apply:** lines. Link related facts with double-bracketed slugs.
```

- `type` and `modified` live **under `metadata`**, not at the top level.
- **`type: project` facts are current-state — overwrite them in place** with a
  fresh `metadata.modified`. Never append a correction or leave a
  strikethrough; the old value is gone, the file states only what is true now.
- `type: user` facts belong in global `~/.claude/CLAUDE.md`; a project-scoped
  one is advisory-misplaced — flag it, don't delete it. The type stays legal.
- `MEMORY.md` is Claude Code's flat auto-index; it coexists with `profile.md`.
  Both point at the same fact files; neither restates them.
- A fact's relations are double-bracketed slugs in the body; a pointer that
  names a not-yet-written fact is fine — it marks work, not an error.

### Migration — convert-on-touch (no big-bang)

profile.md shrinks monotonically; there is no flag day. When a session **edits**
a fact that currently lives as inline profile.md prose but is on-demand
reference by nature, atomize it: move it to `facts/<slug>.md` and leave a
`[[slug]]` pointer behind. Touching a fact is the trigger; untouched prose stays
until a session next needs it. Never do a bulk rewrite as a side effect.

## Opt-in hook automation

Two hooks can carry part of this without anyone running a command. They are
**opt-in**: `<bindle>/bin/install.sh` never installs them, because wiring means
writing to `~/.claude/settings.json` — foreign territory per Bindle's
`docs/ownership-boundaries.md`. `<bindle>/bin/install-claude-hooks.sh` is the
explicit installer (`status`, `install`, `uninstall`; `install`/`uninstall`
only PREVIEW until you pass `--apply` or answer the prompt, and both are
idempotent). A bare `install` wires these two session hooks and nothing else —
the `PreToolUse` guards it also knows about are wired only when named with
`--guard`. Wiring takes effect at the next session boundary, not immediately.

- **`SessionStart` → `global/hooks/session-start-context.py`** runs
  `<bindle>/bin/session-context.sh` and injects a compact orientation block:
  notes-home resolution, the *paths* of the latest session note and handoff
  (never their contents), open `status: in-progress` issues, and a one-line
  git summary. It is a budget-capped pointer, not a substitute — `/session-start`
  is still the deep version.
- **`SessionEnd` → `global/hooks/session-end-breadcrumb.py`** appends one line
  to `projects/<project>/breadcrumbs.log` — timestamp, repo, branch, commits
  made — even when a session never runs `/session-end`.

A breadcrumb is **not** a session note. It lives outside `sessions/*.md` on
purpose, so a later `/session-start` can never mistake a thin automatic trace
for a real, model-authored note: don't read `breadcrumbs.log` as continuity
context, and never let a breadcrumb stand in for writing the note. Both hooks
are pure scripts with no model involvement, and both degrade silently — a
missing notes home or a non-git directory never blocks session start or end.

There is deliberately no `Stop`-hook nag about unwritten session notes. The
breadcrumb is the honest floor; running `/session-end` stays a choice.

## Profile proposals queue

`profile-proposals.md` holds facts proposed for `profile.md` that don't yet
have a decision. `/session-end` is the only writer: it loads any pending
entries left over from earlier sessions, adds any new profile-worthy facts
this session surfaced, and — on a live interactive turn — asks Add / Defer /
Reject for each one via the `AskUserQuestion` tool (batched at most 4
questions per call). Add moves the line into `profile.md`'s named section and
drops the entry; Defer leaves the entry untouched, to resurface next time;
Reject removes it for good. An unattended run never asks — it just appends
new proposals as pending and moves on, so `profile.md` is never written to
without an explicit per-item answer.

Format — one entry per pending proposal:

```markdown
# Pending profile.md proposals — <project>

Awaiting a decision (Add / Defer / Reject) at the next interactive
/session-end. Deferred items stay here; rejected items are removed; added
items move into profile.md and are removed from here.

- [2026-07-12 product-boundary-retriage] (recurring instructions) Re-triage
  product-boundary.md's backlog after any issue-state-changing PR.
```

Each entry is `- [<date> <session-slug>] (<profile.md section>) <exact
proposed line>` — the section name matches one of `profile.md`'s seven
headings (project, common commands, validation gates, important docs, safety
notes, recurring instructions, context locations). The file doesn't exist
until the first proposal is queued, and is deleted once the queue empties.

## Rules

1. **Read-only toward the project repo.** Starting or ending a session, or
   writing a handoff, must not modify the repo being worked on. One built-in
   exception applies to `/session-end` only: as its final step it may switch to
   `main` and fast-forward it to `origin/main` — a lossless navigation that
   creates, modifies, or deletes no tracked file and makes no commit, done only
   when safe and otherwise reported as a blocker (see the session-end command).
   The other exception is content: the user *explicitly* asks for it in the
   repo (a `/project-profile` export, or "put the session summary in the
   repo/PR"). An explicit request is honored — but only via the **Repo-bound
   content** recipe below, never by writing the raw note into the repo.
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
   - sanitize per Bindle's `docs/privacy-boundaries.md` — repo-relative
     paths only, no personal names/emails/denylist terms, no pasted transcript,
     no private "next-prompt for future-me" meta;
   - **run the scanner and block on it.** If the Bindle repo is reachable,
     run `<bindle>/bin/check-private-info.sh <the summary file>` (a Bindle-root
     path, like `slugify.sh` above — not the repo you're scanning); if it flags
     anything,
     do **not** leave the file in the repo — fix and re-run until it passes. A
     manual `grep` is not a substitute for running the scanner.
   - write it to the path the user named (or propose one and confirm); leave it
     **unstaged and uncommitted** — staging is the user's call.

If the Bindle repo isn't reachable to run the scanner, say so and let the
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
candidate workflow improvements: (see Bindle's `docs/iterative-improvement.md`;
  profile updates specifically: see "Profile proposals queue" above)
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
  the recipe says *run `<bindle>/bin/check-private-info.sh`* — a grep is not that.
- Writing a sanitized repo copy but skipping the full private note — the
  continuity record is the point; the repo copy is the extra, not the swap.
- A handoff without scope boundaries ("continue the work") — the next session
  re-litigates finished decisions.
- Stuffing the profile with things already in the project's README — it goes
  stale and drowns the personal signal.
- Blocking on a missing notes home — `mkdir -p` and continue; never ask the
  user to create directories.
- Writing a profile-worthy fact straight into `profile.md` without queuing it
  through `profile-proposals.md` first — even an obviously-true fact still
  needs its own Add/Defer/Reject decision on a live turn; the only exception
  is an unattended run, which queues it as pending and does not touch
  `profile.md` at all.
