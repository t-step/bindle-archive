# Using Bindle with Codex

How a Codex session can honestly use Bindle today. The short version: Codex
gets direct `AGENTS.md` guidance, the docs, and the shell scripts — and it
participates in session continuity by following Markdown conventions, not by
pretending to have Claude's skills or slash commands.

## Install the global guidance

```bash
bin/install.sh --provider codex --codex-home ~/.codex
```

`--codex-home` is an **explicit target directory you choose** — Bindle does
not claim a universal Codex global-install standard; on this machine
lowercase `~/.codex` is the local convention. The install is exactly one
symlink: `global/AGENTS.md` → `<codex-home>/AGENTS.md`. Nothing else is
installed for Codex.

## What Codex may use directly

- a repo's own `AGENTS.md` (project guidance);
- the docs in this repo — start with
  [session-notes-format.md](session-notes-format.md) (the portable
  session-continuity contract) and
  [privacy-boundaries.md](privacy-boundaries.md);
- [`bin/check-private-info.sh`](../bin/check-private-info.sh) — the privacy
  scanner (plain grep, offline);
- [`bin/slugify.sh`](../bin/slugify.sh) — the canonical slug rule for
  notes-home path segments;
- the provider-neutral session-note conventions themselves: notes home,
  file naming, session-note / handoff / profile shapes.

## What Codex must not assume

These are Claude Code primitives. They exist in this repo, but Codex has no
runtime for them — do not try to invoke them, and do not claim to have run
them:

- Claude skills (`skills/*/SKILL.md`);
- Claude slash commands (`commands/*.md`, e.g. `/session-end`);
- Claude subagents (`agents/*.md`);
- Claude hooks.

Their *content* is still readable Markdown — reading
`skills/session-continuity/SKILL.md` to learn the conventions is fine;
"running" it is not a thing Codex can do.

## Project guidance precedence

When a repo contains:

- **`AGENTS.md` only** — it is the authoritative project guidance.
- **`CLAUDE.md` only** — read it as fallback project context. Treat
  Claude-only references in it (hooks, skills, subagents, slash commands)
  as non-portable unless the environment explicitly supports them.
- **Both** — `AGENTS.md` is authoritative for Codex; `CLAUDE.md` may add
  useful context but must not override it.

## Writing a handoff a future Claude Code session can consume

Claude Code's `/session-start` looks in the notes home for the project's
profile and its newest session note and handoff. Write to the same places
with the same shapes and a future Claude session picks your work up
automatically:

1. Resolve the notes home: `$BINDLE_NOTES_DIR`, else deprecated
   `$CLAUDE_KIT_NOTES_DIR`, else `~/.bindle`.
2. Slugify the project name:
   `project="$(basename "$PWD" | bin/slugify.sh)"`.
3. Write the handoff to
   `<notes-home>/projects/<project>/handoffs/YYYY-MM-DD-<slug>.md`
   (`mkdir -p` the directory first).
4. Follow the handoff shape in
   [session-notes-format.md](session-notes-format.md): objective, current
   state, **what is done — do not redo**, **what is out of scope**, ordered
   next steps, and honest verification status ("not run" if you didn't run
   it). Matching `/handoff`'s ten-section layout is nice-to-have; the
   boundary semantics are what matter.

The same recipe with `sessions/` instead of `handoffs/` produces a session
note Claude's `/session-start` will read as prior context.

## Keeping private notes out of project repos

- Session notes, handoffs, and profiles go to the notes home — **never into
  the repo you are working on**. Session workflows are read-only toward the
  project repo.
- If the user explicitly asks for a summary in the repo or a PR: keep the
  full note in the notes home, write a *separate* sanitized summary
  (repo-relative paths, no personal names/emails/denylist terms, no pasted
  transcripts), run `bin/check-private-info.sh <file>` on it and block on
  the result, and leave it unstaged. If the Bindle repo isn't reachable to
  run the scanner, say so and let the user decide.
- Details and the leak-recovery procedure:
  [privacy-boundaries.md](privacy-boundaries.md).
