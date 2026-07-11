# Design: machine-readable capability inventory

**Date:** 2026-07-11 · **Status:** Approved design, pre-implementation
**Issue:** [thomas-estep/bindle#29](https://github.com/thomas-estep/bindle/issues/29)
**Target:** `thomas-estep/bindle` (repo-local tooling; not installed into `~/.claude/`)

## Problem

Bindle's capabilities — skills, commands, agents, global guidance, helper scripts,
and portable contract docs — are described across the README, `docs/provider-interop.md`,
`docs/skill-portability-audit.md`, CHANGELOG entries, and per-item frontmatter. There is
no single machine-readable record, so hand-maintained support matrices drift and an agent
cannot cheaply answer: what capabilities exist, which providers implement each, what type
each is, whether it mutates disk/network/external systems, what version introduced it, and
which document is normative.

This design adds one authored inventory file plus a CI validator that keeps it honest
against the actual repository. It **describes existing assets** — it is not a speculative
universal plugin schema, and it does not (yet) generate documentation or replace the
installer's own logic.

## Locked decisions (from brainstorming)

1. **Source-of-truth model — author + CI reconcile.** One hand-editable inventory file is
   the source of truth for the fields that cannot be derived (provider support, maturity,
   mutation class, version introduced, notes). A CI check reconciles it against the
   filesystem every run. Derived fields (name, type, description) are **cross-checked**
   against the filesystem, never treated as an independent truth.
2. **Format — JSON.** Validated by a Python **stdlib-only** script (zero new CI
   dependencies, matching the dependency-light ethos stated in sibling issues #58/#59 and
   the existing `skills/*/scripts/selftest.py` convention). Hand-editing friction is
   mitigated by having `bin/new.sh` append rows.
3. **Scope — broad.** v1 covers `skill · command · agent · global-guidance · script ·
   contract`, not just the installable set. Because scripts and docs have no clean
   installer bijection, completeness is enforced by a **classified ledger** (see below).
4. **Metadata stays out of `SKILL.md` frontmatter.** The Phase-1 rule "do not rewrite
   `skills/*/SKILL.md` frontmatter" holds; all non-derivable metadata lives in the central
   inventory file, not in per-item frontmatter.
5. **Defer generation.** v1 *validates* one hand-maintained table against the inventory;
   it does not generate README / provider-interop blocks, and does not make
   `install.sh` / `doctor.sh` consume the inventory. Both are named follow-ups.

## Completeness mechanism (the crux)

The six capability types split into "clean" (a directory/file maps 1:1 to a row) and
"fuzzy" (no such mapping). Completeness — issue #29's "every shipped non-template
capability appears" — is enforced differently for each:

- **Clean types — bijection.** Inventory rows of each clean type must exactly match the
  filesystem set:
  - `skill` ⟷ `skills/*/` (dirs with a `SKILL.md`, excluding `_template`)
  - `command` ⟷ `commands/*.md` (excluding `_template.md`)
  - `agent` ⟷ `agents/*.md` (excluding `_template.md`)
  - `global-guidance` ⟷ `global/CLAUDE.md`, `global/AGENTS.md`
  A missing, extra, or renamed capability fails CI. This reuses the same walk
  `doctor.sh:claude_section()` already performs.

- **Fuzzy types — classified ledger.** Every candidate file must be **either** an
  inventory row **or** an explicit entry in a `not_a_capability` exclusion list carrying a
  one-line `reason`. An unclassified new `bin/*.sh` or `docs/**/*.md` fails CI until it is
  classified. Auto-exclude rules keep the ledger small (they are matched before the
  ledger is consulted, so they need no hand entries):
  - `bin/test-*.sh` — the test harness, never a capability.
  - `docs/design/**`, `docs/plans/**` — specs and plans (this document included).
  - `bin/check-private-info.sh` and any script sourced only by `check.sh`/tests may be
    ledgered as internal-machinery with a reason.
  Candidate sets: `bin/*.sh` (minus auto-excludes) and `docs/**/*.md` (minus auto-excludes).

This converts the fuzzy boundary into an enforced, auditable decision rather than a silent
omission — the property that makes the broad scope safe.

## Schema

`capabilities.json` is a JSON object with two keys: `capabilities` (array of records) and
`not_a_capability` (the ledger). One record per capability:

| Field | Required | Source | Validation |
|---|---|---|---|
| `name` | yes | authored | unique per `(type, name)`; for `skill·command·agent` must equal the dir/file stem; for `global-guidance` a stable label (`claude` / `agents`) mapped to the file |
| `type` | yes | authored | enum: `skill·command·agent·global-guidance·script·contract` |
| `path` | yes | authored | a single repo-relative string; must exist on disk (a skill's `path` is its dir; supporting files travel with it) |
| `description` | yes | authored | for `skill·command·agent`: must match the item's frontmatter `description` |
| `provider` | yes | authored | object `{claude, codex}`, each enum: `installed·manual·untested·unsupported·n/a` |
| `maturity` | yes | authored | enum: `draft·documented·tested`; a `skill` marked `tested` must have a `PRESSURE-TESTS.md` |
| `mutation` | yes | authored | array, subset of `{disk, network, external}`; `[]` = read-only |
| `version_introduced` | yes | authored | valid semver, `<=` repo `VERSION` |
| `install_destination` | no | authored | if present, a `~/.claude/...`-style path string; source path must exist |
| `dependencies` | no | authored | array of other capability `name`s or external tool names |
| `related_docs` | no | authored | array of repo-relative doc paths (must exist) |

Ledger entries: `{ "path": "...", "reason": "..." }`.

Enum rationale:
- **provider** mirrors the vocabulary already used in prose in `provider-interop.md`
  (`installed`, `manual via docs`, `Untested`) promoted to controlled values, keeping
  provider differences explicit (#29 acceptance criterion).
- **maturity** mirrors `skill-portability-audit.md`'s evidence levels
  (`tested`/`documented`) plus `draft` for scaffolded-but-unverified items; the
  `tested ⟹ PRESSURE-TESTS.md` cross-check ties it to the real marker.
- **mutation** is #29's "modify disk / invoke networked tools / mutate external systems"
  expressed as three independent flags.

## Machinery

### `bin/check-inventory.py` (Python 3, stdlib-only)

Read-only validator. Exits non-zero with a per-line diagnostic on any failure. Checks:

1. **Schema** — every record has required fields; enums valid; `version_introduced` is
   semver and `<= VERSION`; `(type, name)` unique.
2. **Completeness** — bijection for clean types; classified-ledger coverage for fuzzy
   types (every candidate is a row or a ledgered exclusion).
3. **Paths** — every `path`, `install_destination` source, and `related_docs` entry
   exists on disk.
4. **Cross-checks** — `description` equals frontmatter for skill/command/agent;
   `tested` skills have `PRESSURE-TESTS.md`.
5. **Bound table (criterion c)** — the set of `skill`-type names in the inventory equals
   the set of skill rows in `docs/skill-portability-audit.md`'s per-skill table. Drift in
   either direction fails. This is the "checked against" target; it is the richest,
   most drift-prone hand-maintained per-item table.

### `check.sh` integration

Add one inline numbered section (matching the existing pattern — `problem`/`ok` helpers,
the global `fail` flag) that runs `python3 bin/check-inventory.py`. A companion
`bin/test-check-inventory.sh` follows the existing `test-*.sh` convention (auto-discovered
by the shellcheck/shfmt sweep and runnable via the test suite) and exercises the validator
against small pass/fail fixtures.

### `bin/new.sh` wiring (criterion e)

When scaffolding a `skill`/`agent`/`command`, append a stub inventory row with the derived
fields filled (`name`, `type`, `path`, `description` copied from the new frontmatter) and
placeholders the author completes (`provider`, `maturity: draft`, `mutation`,
`version_introduced`). Because the bijection check would otherwise fail for a freshly
scaffolded capability, this makes the "documented inventory step" automatic rather than a
thing to remember. Scripts/contracts are not scaffolded by `new.sh`; the classified-ledger
check is what forces their classification.

### Documentation

- `docs/capability-inventory.md` — the schema reference and the "how to add a capability"
  step (including how to classify a new script/doc).
- `CONTRIBUTING.md` — a pointer to that doc in the "before you call it done" checklist.
- `CHANGELOG.md` — an `[Unreleased]` entry.

## File tree (v1)

```
capabilities.json                      # authored inventory + not_a_capability ledger
bin/check-inventory.py                 # stdlib validator
bin/test-check-inventory.sh            # test harness for the validator (+ fixtures)
bin/check.sh                           # + one inline section invoking the validator
bin/new.sh                             # + append-stub-row on skill/agent/command scaffold
docs/capability-inventory.md           # schema + "add a capability" guide
CONTRIBUTING.md                        # + pointer
CHANGELOG.md                           # + [Unreleased] entry
```

## Acceptance criteria (from #29) → how this satisfies them

- *Every shipped non-template capability appears* — bijection (clean) + classified ledger
  (fuzzy); unclassified files fail CI.
- *Referenced paths validated by CI* — path-existence check on `path` /
  `install_destination` / `related_docs`.
- *At least one manual table generated from or checked against the inventory* — the
  `skill-portability-audit.md` skill-set drift check.
- *Provider differences remain explicit* — the `provider.{claude,codex}` controlled enum.
- *Adding a new capability has a documented inventory step* — `new.sh` stub-append +
  `docs/capability-inventory.md`.

## Non-goals (v1)

- Generating README / `provider-interop.md` blocks from the inventory (follow-up).
- Making `install.sh` / `doctor.sh` consume the inventory to remove the 4×
  type→destination duplication (follow-up, once the inventory is trusted).
- Adding any field to `SKILL.md` / command / agent frontmatter.
- A universal cross-provider plugin schema, package registry, or remote marketplace.

## Follow-ups (explicitly out of this slice)

1. Generate the README mapping blocks and `provider-interop.md` install-layout table from
   the inventory (replaces hand-maintained duplication with derivation).
2. Single-source the type→install-destination mapping: have `install.sh` and `doctor.sh`
   read the inventory, removing the documented 4× duplication.
3. Extend the bound-table check to validate `provider-interop.md`'s capability matrix rows.
