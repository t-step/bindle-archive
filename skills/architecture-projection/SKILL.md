---
name: architecture-projection
description: Use when creating or refreshing a project's architecture map from a structural-graph document — running the preview → confirm → apply loop, reading a projection plan before approving it, or deciding whether a deferred or over-cap candidate is safe to ignore. Also when a projection run reports a stale token, a conflict, or an unplaceable identity.
---

# architecture-projection

## Overview

`architecture-projection.py` turns a **structural-graph document** — files,
symbols and edges a provider observed — into a small set of durable,
human-readable architecture notes in the notes home.

It is not a symbol-graph export and not a visualization. It creates a bounded
map (a codebase map plus component notes) and maintains it across runs without
ever losing what you wrote.

**The projection never decides anything you did not approve.** Every run is
`preview → confirm → apply`, and the plan you approve is the plan that gets
written or nothing is.

## When to Use

- Creating an architecture map for a project for the first time.
- Refreshing one after the code moved.
- Reading a projection plan and deciding whether to approve it.
- Diagnosing `stale_preview`, a deferred candidate, or a conflicted note.

When NOT to use:
- Editing the notes by hand — do that directly, outside the generated region.
- Producing the structural-graph document itself. This tool consumes one; it
  does not build one.

## The loop

The CLI lives at `<bindle>/bin/architecture-projection.py` and takes
`--notes-home PATH --project SLUG` on every verb, plus `--format json|text`.

| Verb | What it does | Writes? |
|------|--------------|---------|
| `init` | allocates the project identity, writes `config.json` | yes, once |
| `config status` / `config validate` | reads configuration and lock state | no |
| `config add-binding` | registers one repository binding | yes |
| `preview` | builds the plan and prints its **fingerprint** | **no** |
| `confirm` | checks a held fingerprint and reports the policy | **no** |
| `apply` | writes the approved plan under the project lock | yes |

Every verb that runs the chain takes the graph the same way — repeatable
`--graph BINDING_ID=PATH`, where `BINDING_ID` must already be configured.

## The token

`preview` prints a plan **fingerprint**. Pass it back to `confirm
--fingerprint` and to `apply --approval-token`.

The fingerprint is a digest of the inputs the plan was built from. `apply`
recomputes it and **aborts as `stale_preview` if anything moved**, rather than
writing a plan you never read. That is the whole safety property: a
confirmation binds the plan it was given for.

The token is **never stored**. It is invocation state you carry between two
commands. If you lose it, re-run `preview` — that is always legal and writes
nothing.

## Reading a plan

`preview` reports each planned entry with a `note_state`, which is decided
against what is actually on disk:

- `absent` — the note will be created.
- `changed` — the generated region will be refreshed.
- `current` — nothing to do.
- `conflict` — the note exists but its generated region cannot be safely
  replaced. Apply leaves it alone.

Read `note_state`, not the plan-level `disposition`. Disposition compares
against the previous run's records, which are not persisted, so it reads
`mint` on every run.

Two more lists matter:

- **`deferred`** — candidates that will **not** be projected. A contested or
  low-confidence identity match is reported rather than guessed at, because
  choosing would either mint a second identity for code that already has one
  or silently pick a winner. This is expected, not a failure.
- **`over_cap`** — candidates ranked below the note cap. The cap binds
  creation, so these are reported rather than created.

`confirm` reports these as `confirmation_reasons` alongside a diff size checked
against the configured limit. It **reports**; it does not refuse. Deciding is
yours.

## Rules

- **Never hand-edit inside the generated region.** Each note fences its
  generated content between `bindle:architecture:generated` markers. Anything
  below that fence is yours and the projection will never touch it. Edits
  *inside* it are overwritten on the next refresh — or turn the note into a
  `conflict`, which stops the refresh entirely.
- **A rerun at an unchanged commit must write zero bytes.** If a rerun reports
  writes, an input moved; find out which before approving.
- **Never delete a projected note to "reset" it.** Identity lives in the
  judgments log, not in the note. Deleting the note orphans nothing, but
  deleting the projection state loses the record of where notes live.
- **One project at a time.** Apply takes a project-wide lock; a contended run
  reports the holder rather than waiting.

## Exit codes

`0` success · `1` a findings list was rendered (a domain error, a stale token,
a refused plan) · `2` argument usage error.

Findings are always a list under `findings`, each with a `code` and a
`message`. A non-zero exit with a findings list is a normal, reportable
outcome — not a crash.
