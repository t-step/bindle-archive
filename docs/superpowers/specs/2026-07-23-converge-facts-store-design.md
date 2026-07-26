# Converge the profile monolith and the per-fact memory store — design

**Status:** proposed
**Date:** 2026-07-23
**Issue:** #422 (coupled to #423)

## Problem

Bindle keeps a project's private working-memory in two places over the same
fact space:

- **The Bindle notes home** (`$BINDLE_NOTES_DIR/projects/<project>/profile.md`)
  — one monolithic `profile.md` (7 fixed sections, loaded wholesale every
  session by `/session-start`).
- **The Claude Code harness memory store**
  (`~/.claude/projects/<encoded-repo-path>/memory/` — per-fact `*.md` files plus
  a thin `MEMORY.md` index). The harness injects that **index** on its own; the
  fact *bodies* it does not (measured 2026-07-25 — see "Risks and open
  validation items").

They run the same taxonomy (feedback / project / reference / user) and **drift
independently**: measured duplication of ~¼–⅓ of the profile's substance,
stacked-strikethrough "current-state" corrections that never overwrite,
divergent counts, broken gate numbering. Two homes for one fact, each with the
weaknesses the other lacks: the monolith loads everything every session,
appends instead of overwriting, and has no per-fact retrieval; the per-fact
store has all three but lives Claude-Code-only under `~/.claude/`.

## Constraints that set direction

1. **The vault must be canonical, not the harness store.** The harness memory
   lives under `~/.claude/` — Claude-Code-only, the one store that will not
   follow a multi-agent operator to Codex. Convergence makes the Bindle vault
   the source of truth; the harness store becomes a view onto it.
2. **The operator runs ~50/50 Codex and Claude Code.** This is the decisive
   constraint. It rules out the tempting asymmetric end-state — "Claude's
   harness surfaces facts proactively for free; Codex just greps." At 50% Codex
   that asymmetry is felt every other session, which is exactly the tool-coupling
   the convergence exists to remove, merely relocated from the *store* to the
   *loader*. Whatever we build must give Claude and Codex the **same** behavior.
   *Measured 2026-07-25:* the free surfacing Claude actually gets is the
   `MEMORY.md` **index**, not fact bodies — so the asymmetry this constraint
   guards against is narrower than assumed, and the constraint itself is
   unchanged (see "Risks and open validation items").
3. **The fact-file format is not ours to design.** Claude Code already writes
   the per-fact store in a fixed schema (see below). For a single physical store
   to round-trip through the harness unchanged, the canonical `facts/` format
   **must be that schema, adopted as-is and extended** — not a clean-slate
   design. Both #422's body and #423's lint sketch assumed a *flat*
   `type`/`modified`; the real schema nests them under `metadata`. #423's lint
   must be corrected to match (see "Coupling to #423").
4. **Markdown stays canonical; no database as primary.** Per the issue's
   storage-substrate decision: plain-text is what makes the store tool-agnostic,
   Obsidian-browsable, diffable, and hand-editable. A derived SQLite index is a
   later, disposable cache — out of scope here (YAGNI at ~100 facts).

## The canonical fact format (adopted from the harness, verbatim)

Inspected on disk (`scale-review-to-stakes.md`, a real harness-written fact):

```yaml
---
name: scale-review-to-stakes
description: "Operator stops disproportionate multi-agent review; match fan-out to stakes, not interestingness"
metadata:
  node_type: memory
  type: feedback
  originSessionId: <uuid>
  modified: 2026-07-21T20:22:05.367Z
---

<body> **Why:** … **How to apply:** … Related: [[other-fact-name]]
```

Rules the canonical format inherits from what the harness already writes:

- `name` equals the filename slug; `description` is a quoted one-liner. It is
  what an index entry and any relevance-selection step have to work from; note
  that no measurement here shows the harness selecting on it — what the harness
  demonstrably injects is `MEMORY.md`.
- **`type` is `metadata.type`**, not a top-level key; vocabulary
  `feedback | project | reference | user`.
- **`modified` is `metadata.modified`**, a full ISO-8601 **datetime** with
  milliseconds and `Z` — not a date.
- `metadata.node_type` and `metadata.originSessionId` are harness-specific.
  Bindle tooling and any non-Claude loader **tolerate and ignore** them.
- Body carries the `**Why:** / **How to apply:**` structure for feedback/project
  facts and `[[wikilink]]` relations. Each `MEMORY.md` index entry is a markdown
  link to the fact file plus a one-line hook (bracketed title, the fact's
  filename in parentheses, em-dash, hook).

## Target architecture

### Store — one physical home, harness symlinked onto it

- The canonical store is `$BINDLE_NOTES_DIR/projects/<project>/facts/`: git-
  tracked, Obsidian-browsable, one durable fact per file in the format above.
- Claude Code's `~/.claude/projects/<encoded-repo-path>/memory/` becomes a
  **symlink onto that `facts/` directory.** Consequences, all intended:
  - The harness's *native* loading now reads the vault directly — Claude gets
    the vault's `MEMORY.md` **index** injected for free. Fact bodies still cost
    a read (measured; see "Risks and open validation items"), so this buys
    index surfacing, not proactive recall.
  - The harness's *writes* (new memories, `modified` bumps) land as vault facts,
    so there is genuinely one store, not a mirror to reconcile.
  - The harness's `MEMORY.md` auto-index lives inside `facts/`.
- The symlink is a **committed part of the design**, not an optional
  optimization. Phase 2 opens by validating that the harness reads and writes
  through a symlinked `memory/` dir (rather than resolving or recreating the
  real path); if that validation fails, it is a **blocker to surface**, and the
  named fallback is a drift-check over two format-identical stores (below) —
  never a silent pivot.

### Index — `profile.md` as curated runbook + pointers

`profile.md` keeps its 7-section skeleton (the `/session-start`, `/session-end`,
`/project-profile`, and profile-proposals contract is unchanged), but each
section becomes **either** a small inline *runbook block* **or** a *pointer
list*:

- **Inline (hot core), stays in `profile.md`:** the consolidated validation-gate
  list, common-commands block, important-docs pointers, standing branch/safety
  one-liners — the glanceable "how to operate here," loaded wholesale by every
  agent every session.
- **Pointer (shed tail), moves to `facts/`:** long-form safety-note prose,
  recurring-instruction essays, current-state sagas, campaign summaries,
  context-location trackers. `profile.md` points (`[[fact]]` + one-line hook);
  it does not restate.

`profile.md` (Bindle's curated, portable index) and `MEMORY.md` (the harness's
flat auto-index) **coexist**: two indexes, different jobs, both pointing at the
same fact files, neither restating them. No drift, because indexes point.

### Retrieval — same behavior for both agents

- **Claude Code:** native harness loading, now reading the vault via the
  symlink — which delivers the `MEMORY.md` index, not the fact bodies.
- **Codex:** a **portable loader in Bindle's command layer** (`/session-start`
  enumerates `facts/`, reads each `description`, loads what is relevant to the
  session goal). Because Codex runs Bindle's commands through the interop layer,
  this is **Phase 2**.

Reactive retrieval (an agent that knows it needs a fact greps `facts/`) already
works for every agent today with zero mechanism; the loader adds *proactive*
surfacing of the shed tail — which 50/50 makes worth having for both agents.

**The correction below changes the arithmetic of this section.** Since the
harness injects only the index, the portable loader is the only mechanism on the
table that surfaces fact *bodies* proactively — and it does so for **both**
agents, Claude included. The symlink is therefore not "Claude's half of
retrieval"; it is a single-store convenience whose retrieval benefit stops at
the index.

## Phasing

The split exists so Phase 1's value does **not** depend on the symlink working.

### Phase 1 — the drift fix (no symlink dependency)

1. **Single-home the confirmed duplicates.** Extract each measured duplicate to
   one canonical `facts/` file; replace the `profile.md` prose with a pointer.
2. **Overwrite-in-place discipline for `type: project` current-state facts.**
   Prod-arm / schema-rev / active-slug facts are overwritten with a fresh
   `metadata.modified`, never append-corrected. This ends the stacked-
   strikethrough pathology structurally. This is a writing-discipline change in
   `/session-end`, not a format change.
3. **Thin `profile.md` conservatively.** Shed only the genuinely on-demand tail
   to pointers; keep every must-load-every-session fact inline, because at 50/50
   there is no harness to lean on half the time. The keeps/sheds line is
   deliberately conservative until the Phase 2 loader exists.
4. **Freeze the `facts/` format** as specified above, so the Phase 2 loader and
   the symlink are drop-ins with no second migration.

### Phase 2 — one store + portable loader (the symlink)

1. **Validation step:** confirm the harness reads/writes through a symlinked
   `memory/` dir and survives the harness's own dir management. Blocker if it
   fails (fallback: drift-check over two format-identical stores).
2. **Establish the symlink** from the harness `memory/` dir onto the vault
   `facts/` dir.
3. **Build the portable loader** in the command layer for Codex parity.

## `type: user` handling

The harness writes `metadata.type: user` facts into the project memory dir, so
Bindle **cannot forbid** the type. Bindle treats a project-scoped `user` fact as
**advisory-misplaced** — it belongs in global `~/.claude/CLAUDE.md`, not a
project store — and flags (does not delete or reject) it. `type: user` remains
legal in the vocabulary.

## Coupling to #423

#423 is the frontmatter lint, and the issue's own comment calls it a
precondition for the `description`-relevance-loading and drift-check here being
trustworthy. The format discovery in this design **corrects #423's sketch**:

- The lint asserts `metadata.type` (in the vocabulary) and `metadata.modified`,
  **not** flat `type`/`modified`.
- `modified` is a valid ISO-8601 **datetime**, not a date.
- The lint must **tolerate** `metadata.node_type` and `metadata.originSessionId`
  rather than flag them as unknown.
- `name` still equals the filename slug; `[[wikilinks]]` must resolve; no
  duplicate `name`.

Order of operations: **#422 freezes the schema → #423 enforces it.** Freezing
the format here without #423 leaves the schema unenforced, which is the exact
gripe the convergence closes — so the two are co-dependent on this schema and
should reference each other.

## Migration — no big-bang

- **One-time pass (Phase 1):** extract the confirmed duplicates to canonical
  fact files; replace profile prose with pointers.
- **Convert-on-touch thereafter:** when a session edits a fact, atomize it and
  leave a profile pointer. `profile.md` shrinks monotonically; no flag day.

## Risks and open validation items

- **Symlink-through behavior is MEASURED (2026-07-25), and it is split:**
  **reads work, headless writes do not.** Fixture probes against throwaway repos
  with `memory/` symlinked to a vault dir:
  - *Read:* the loader resolves the symlink and injects the vault's `MEMORY.md`
    — 3/3 runs quoted a canary that exists only in the vault.
  - *Write, interactive:* succeeds; the file lands in the vault through the
    symlink.
  - *Write, headless (`claude -p`):* refused 3/3 —
    `… /memory/<file>.md which is a sensitive file` — while the identical write
    into a **real** `memory/` dir passes. The symlink is the discriminator (a
    target *inside* the repo is blocked too), and `--add-dir` on the target does
    not unblock it.
  - *Corollary:* writing to the symlink's **resolved** path instead bypasses the
    harness's frontmatter enrichment — the file lands without `node_type`,
    `originSessionId`, or `modified`, which is precisely what #423's lint must
    reject.
  - *Enrichment does not survive the symlink.* A follow-up run proved enrichment
    is applied **at write time**, not at session end: an agent that wrote a
    memory into a real `memory/` dir and immediately read it back saw
    `node_type`, `originSessionId`, and `modified` it had not authored. The
    interactive write through the symlink stayed unenriched indefinitely. So the
    symlink costs the enrichment on every write, not just on the resolved-path
    workaround above.
  So the single-store symlink is viable for interactive sessions and breaks
  memory writes in unattended ones. The named fallback — a drift-check over two
  format-identical stores — remains open, and the Phase 2 choice between them is
  deliberately not made here.
- **Correction to a premise: the harness does not auto-inject fact *bodies*.**
  This doc as first written (and #422's body) described the harness as loading
  the per-fact store "by relevance"; the sections above have since been corrected
  to match what follows. What is injected up front is the **`MEMORY.md` index**; the
  fact body is not. Asked a question answerable only from a fact file's body and
  forbidden from using tools, a session replied `NO-FACT` — **in both arms**,
  symlinked *and* real `memory/` dir. So this is not a symlink defect; it is what
  the mechanism does. Consequence for the design: the symlink's advertised payoff
  ("Claude gets proactive surfacing of vault facts for free") is really *index*
  surfacing for free, with the body still costing a read — and in headless runs a
  read of a symlink target outside the workspace is itself sandbox-blocked. That
  narrows the asymmetry between Claude and Codex the loader was meant to close,
  which makes the Phase 2 portable loader *more* attractive relative to the
  symlink, not less.
- **The harness memory dir is keyed to the git repo root, not to cwd** — the
  *transcript* dir is keyed to the encoded cwd, and only that. Measured: a
  session whose cwd is `repo/.worktrees/wt1` gets its own
  `~/.claude/projects/<worktree-key>/` transcript dir but resolves memory to the
  **primary** repo key, and read the vault canary through the primary's symlink.
  Corroborated in this repo, where two historical worktree-keyed project dirs
  exist and neither has a `memory/`. Confirmed again for a worktree created
  **outside** the repo tree, which also read the primary key's memory — so the
  rule is the git repo root, not "a subdirectory of the checkout". One symlink at
  the primary key covers every worktree; a *moved* repo still remaps. The vault is keyed to the kebab
  slug from `<bindle>/bin/slugify.sh`; the encoded-path mapping is the harness's,
  not Bindle's.
- **Harness writes become vault git changes.** Every harness memory write dirties
  the (private) notes-home git — intended for single-home, but noisier history.
- **Two indexes** (`profile.md`, `MEMORY.md`) must both stay pointers, never
  restatements, or the drift returns one level up.

## Out of scope (non-goals)

- A SQLite (or any DB) primary store — Markdown stays canonical; a derived index
  is a later, disposable cache, not built here.
- Retraining or replacing the Claude Code harness memory mechanism — Bindle
  adapts to its schema, not the reverse.
- Forbidding `type: user` in project scope — advisory only.
- Building the Codex loader in Phase 1 — it is Phase 2, format-frozen now.
- The lint implementation itself — that is #423.

## Success criteria

- Each confirmed duplicate has exactly one canonical `facts/` file; `profile.md`
  and `MEMORY.md` both point at it, neither restates it.
- `type: project` current-state facts are overwritten in place with a fresh
  `metadata.modified`; no new stacked-strikethrough corrections appear.
- `profile.md`'s 7-section contract still satisfies `/session-start`,
  `/session-end`, `/project-profile`, and the profile-proposals queue unchanged.
- The canonical `facts/` format is exactly the harness schema plus Bindle's
  tolerated extensions, verified by a file that round-trips through both the
  harness and Bindle tooling without rewriting.
- (Phase 2) Claude and Codex surface the same shed-tail facts from the one vault
  store. Note what each mechanism can deliver: the symlink gives Claude the
  vault's index; only the portable loader surfaces fact *bodies*, and it can do
  that for either agent.
