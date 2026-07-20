# Session notes format — the portable contract

The provider-neutral contract behind Bindle's session continuity: where
durable session context lives, how its files are named, and what shape each
artifact takes. Any agent that can read and write Markdown and run a shell
script can participate — Claude Code happens to automate it with a skill and
slash commands; Codex (or a human) can follow it by hand.

This doc **describes** the existing behavior of the `session-continuity`
skill and the `/session-start`, `/session-end`, `/handoff`, and
`/project-profile` commands. It does not define a parallel system. If this
doc and those assets disagree, that is a bug — fix one of them, don't fork.

## Contract levels

Not everything here is equally load-bearing. Each section is labeled:

- **Stable contract** — conventions Bindle preserves across providers.
  Breaking one is a breaking change.
- **Current Claude automation** — what Claude slash commands/skills happen to
  automate today. Useful to imitate; allowed to evolve.
- **Compatibility behavior** — deprecated `CLAUDE_KIT_*` / `~/.claude-kit`
  support, kept so old data keeps working. Don't build new things on it.
- **Recommendation** — helpful habits. Not rules; do not enforce them.

## The notes home

**Stable contract.** Durable session context lives in one directory tree,
**outside every project repo**:

```
<notes-home>/
  private-denylist.txt                # personal terms for check-private-info
  projects/<project>/
    profile.md                        # durable facts: gates, commands, safety notes
    sessions/YYYY-MM-DD-<slug>.md     # one note per session
    handoffs/YYYY-MM-DD-<slug>.md     # paste-ready prompts for future sessions
    breadcrumbs.log                   # opt-in SessionEnd hook only — NOT a note
    context.md                        # NEW — regenerable projection, #185 apply
    .bindle/
      .lock                           # NEW — single-writer lock, project-scoped (#228)
      context/
        config.json                   # NEW — authoritative, #191
        judgments.jsonl               # NEW — append-only ledger, #184
        index.json                    # NEW — rebuildable materialized graph, #185
```

Everything is plain Markdown. There is no database, daemon, or init step;
create directories on demand (`mkdir -p`). The notes home is never a project
repo and never this repo — a note inside a repo is one `git add -A` away from
publication. See [notes-home.md](notes-home.md) for the user-facing view
(relocation, Obsidian).

### Resolution order

Resolve `<notes-home>` in this order:

1. `$BINDLE_NOTES_DIR` — **stable contract**;
2. `$CLAUDE_KIT_NOTES_DIR` — **compatibility behavior** (deprecated);
3. `~/.bindle` — **stable contract** (the default);
4. an existing `~/.claude-kit` — **compatibility behavior**: only when a
   workflow intentionally keeps using the old location. Bindle never
   migrates data between homes automatically.

The privacy scanner's denylist **follows this same notes home**. An explicit
`$BINDLE_DENYLIST` (deprecated: `$CLAUDE_KIT_DENYLIST`) overrides everything;
otherwise the scanner reads `private-denylist.txt` at the notes home root,
walking the four locations above in order. Relocating the notes home therefore
moves the denylist with it — see
[`bin/check-private-info.sh`](../bin/check-private-info.sh).

A clean scan says which of the two it is: with no denylist resolved, the
scanner reports `pattern rules only — NO personal denylist loaded`. That is a
verdict about the *patterns*, not evidence that your personal terms are
absent.

## Naming

**Stable contract.**

- `<project>` is the repo's directory basename, slugified: lowercase, every
  run of non-`[a-z0-9]` characters collapses to a single `-`, leading and
  trailing `-` trimmed (`My_App.v2` → `my-app-v2`).
  [`bin/slugify.sh`](../bin/slugify.sh) is the canonical implementation
  (with `--self-test`); pipe names through it rather than hand-deriving
  edge cases.
- Session notes: `projects/<project>/sessions/YYYY-MM-DD-<slug>.md`.
- Handoffs: `projects/<project>/handoffs/YYYY-MM-DD-<slug>.md`.
- Project profile: `projects/<project>/profile.md`.
- `<slug>` follows the same slug rule and names the session's goal. Never
  put `/`, spaces, or personal names in filenames.

**Recommendation:** keep `<slug>` to 2–5 kebab-case words. `YYYY-MM-DD` is
the local date.

## Artifact shapes

For all three artifacts, the **field set is the contract; the exact Markdown
formatting is current convention**. A future session greps these files, so
keep the field names recognizable; precision beats prose.

### Session note

**Stable contract** — one note per session, containing:

- **goal** — what the session set out to do (also the title line);
- **branch / commits made / files changed** — the git reality;
- **tests/checks run** — what actually ran and its actual result. If tests
  were not run, the note says "not run", never "passing";
- **decisions** — one line each, with the why;
- **risks** — what could bite a future session;
- **deferred** — consciously not done;
- **candidate workflow improvements** — see
  [iterative-improvement.md](iterative-improvement.md);
- **next** — the single best next prompt.

**Current Claude automation:** `/session-end` additionally records an
explicit **validation status** (green / red / not verified) and reconstructs
the session from git state rather than trusting the conversation's claims. In
repos that track work as GitHub Issues (see
[issue-tracking.md](issue-tracking.md)), it also proposes `status:`-label
reconciliation for issues the session touched — user-approved before any `gh`
command runs — and folds the outcome into **decisions**. `/session-start`
correspondingly surfaces open `status: in-progress` issues so a stale label
is caught at the start of the next session too. Imitating that honesty is
strongly recommended; the extra field is not required of other writers.

### Handoff

A handoff is a single self-contained prompt a future session — any harness,
no access to the current conversation — can start from cold.

**Stable contract** — a handoff must state its boundaries, not just its
task:

- the objective;
- current state (branch, committed vs. uncommitted, check status as last
  observed);
- **what is DONE — do not redo** (finished work and decisions, so they are
  not re-litigated);
- **what is OUT of scope / must not be touched**;
- concrete next steps;
- honest verification status — unverified means unverified.

**Current Claude automation:** `/handoff` renders those as exactly ten
sections (Repo, Current state, Objective, Completed — do not redo, Changed
files, Key decisions, Tests/checks, Known risks, Scope boundaries, Next
steps). Matching that layout makes handoffs uniform and grep-friendly, but
the section list is convention; the boundary semantics above are the
contract.

### Project profile

Durable, portable facts a fresh session needs about a project.

**Stable contract** — lives at `projects/<project>/profile.md`; contains no
secrets, tokens, or personal-life details (profiles travel); records what
the repo itself can't say — *your* gates, safety notes, and recurring
instructions — and points at, rather than copies, facts the project's own
README/provider guidance already states.

**Current Claude automation:** `/project-profile` writes these sections:
project, common commands, validation gates, important docs, safety notes,
recurring instructions, context locations.

**Recommendation:** keep it under ~60 lines so the personal signal doesn't
drown.

## Privacy and repo-bound content

**Stable contract**, for every provider:

1. **Session workflows are read-only toward the project repo.** Starting or
   ending a session, or writing a handoff, must not modify the repo being
   worked on.
2. **Notes are private by default.** In the notes home, local paths and
   blunt assessments are fine — that's what it's for.
3. **Repo-bound content only on explicit request, and only sanitized.** If
   the user explicitly asks for a summary in the repo or a PR: the full
   private note still goes to the notes home first; then a *separate*
   sanitized summary is produced per
   [privacy-boundaries.md](privacy-boundaries.md) (repo-relative paths, no
   personal names/emails/denylist terms, no pasted transcripts), verified
   with [`bin/check-private-info.sh`](../bin/check-private-info.sh) — block
   on its result — and left **unstaged**; staging is the user's call. Never
   write the raw note into a repo. A manual grep is not the scanner.

## How Claude Code uses this

Claude Code automates the contract natively: the `session-continuity` skill
holds the conventions, and the `/session-start`, `/session-end`, `/handoff`,
and `/project-profile` slash commands apply them. These assets are
Claude-native and stay that way — their frontmatter, triggers, and install
layout are not part of this contract.

### Opt-in hook automation (breadcrumbs)

**Current Claude automation**, and explicitly opt-in (never part of the
default `bin/install.sh` — see
[ownership-boundaries.md](ownership-boundaries.md)):
`bin/install-claude-hooks.sh install` (preview-only until `--apply`, or a `y`
at the prompt; idempotent, and effective at the next session boundary) wires a
`SessionStart` hook
(`global/hooks/session-start-context.py`) that runs
[`bin/session-context.sh`](../bin/session-context.sh) and injects its compact
output — notes-home resolution, latest session-note/handoff *paths* (never
contents), open `status: in-progress` issues, a one-line git summary — so a
fresh session opens oriented without depending on the human running
`/session-start` first. `/session-start` remains the deep version; this is a
cheap pointer, budget-capped to a few hundred tokens.

The paired `SessionEnd` hook (`global/hooks/session-end-breadcrumb.py`)
appends one line to `projects/<project>/breadcrumbs.log` — timestamp, repo,
branch, commits made this session — even when a session never runs
`/session-end`. This is **not** a session note: it lives outside
`sessions/*.md` on purpose, so a future `/session-start` never mistakes a
thin automatic trace for a real, model-authored note. Pure script, no model
involvement, and it never blocks session start or end on failure (missing
notes home, no git repo, etc. all degrade silently).

**Explicit decision:** no `Stop`-hook "you haven't written a session note"
nag. It would fight the user more than it helps; the breadcrumb is the
honest floor, `/session-end` remains something you choose to run.

## How Codex uses this

Codex has no skills or slash commands; it participates manually:

- read this doc, then read/write the Markdown artifacts above directly;
- run [`bin/slugify.sh`](../bin/slugify.sh) for path segments and
  [`bin/check-private-info.sh`](../bin/check-private-info.sh) before any
  repo-bound summary;
- to pick up prior context: resolve the notes home, read
  `projects/<project>/profile.md`, the newest file in `sessions/`, and the
  newest in `handoffs/`.

See [using-bindle-with-codex.md](using-bindle-with-codex.md) for the full
Codex-side guide.

## Out of scope

Intentionally not part of this contract:

- any index, database, daemon, or sync mechanism (see
  [sqlite-workflow-index.md](sqlite-workflow-index.md) for the deferred
  design note);
- automatic migration between notes homes;
- automatic promotion of note content into committed files (always explicit
  — see [iterative-improvement.md](iterative-improvement.md));
- a cross-provider command/skill format — providers automate this contract
  with their own native surfaces or not at all.
