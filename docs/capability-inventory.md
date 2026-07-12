# Capability inventory

**Status:** Contract, v1 · **Issue:** [thomas-estep/bindle#29](https://github.com/thomas-estep/bindle/issues/29)

`capabilities.json` is Bindle's single machine-readable record of what this repo
ships: skills, commands, agents, global guidance, helper scripts, and portable
contract docs — which provider(s) support each, how mature it is, whether it
mutates anything, and what version introduced it. `bin/check-inventory.py`
(stdlib-only Python, run by `make check`/`make test`) reconciles the authored
file against the actual repository every run, so the inventory can't silently
drift the way the README/`provider-interop.md`/per-item frontmatter used to.

This doc is the schema reference and the "how do I add a capability" guide.
The full design rationale lives in
[`docs/design/2026-07-11-capability-inventory.md`](design/2026-07-11-capability-inventory.md).

## What it is not (yet)

- It does not generate the README / `docs/provider-interop.md` blocks from
  itself — those are still hand-maintained and only checked against the
  inventory in one place (see "Bound table" below).

This is a named follow-up in the design doc, deferred until the inventory has
proven itself trustworthy. (The type→install-destination mapping — the other
named follow-up — is no longer duplicated: `install.sh` and `doctor.sh` now
read it from the generated `install-manifest.tsv`, see below.)

## Schema

`capabilities.json` is a JSON object with two top-level keys: `capabilities`
(array of records) and `not_a_capability` (the classified ledger — see
below). One record per capability:

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
| `install_destination` | no | authored | optional per-row override of the derived destination. Destinations are otherwise derived from `type` into the generated `install-manifest.tsv`, which `make check` drift-checks and `install.sh`/`doctor.sh` consume (see #79). |
| `dependencies` | no | authored | array of other capability `name`s or external tool names |
| `related_docs` | no | authored | array of repo-relative doc paths (must exist) |

Ledger entries: `{ "path": "...", "reason": "..." }`.

### Enum rationale

- **provider** mirrors the vocabulary already used in prose in
  `provider-interop.md` (`installed`, `manual via docs`, `Untested`) promoted
  to controlled values, keeping provider differences explicit (#29 acceptance
  criterion).
- **maturity** mirrors `skill-portability-audit.md`'s evidence levels
  (`tested`/`documented`) plus `draft` for scaffolded-but-unverified items;
  the `tested ⟹ PRESSURE-TESTS.md` cross-check ties it to the real marker.
- **mutation** is #29's "modify disk / invoke networked tools / mutate
  external systems" expressed as three independent flags.

Derived fields (`name`, `type`, `description`) are hand-authored but
cross-checked against the filesystem/frontmatter, never treated as an
independent source of truth — if a description drifts, fix the inventory
row, not the other way around, unless the frontmatter is actually wrong.

### `install-manifest.tsv` (generated)

`bin/check-inventory.py --emit-manifest` projects the installable capabilities
(`skill`/`agent`/`command`/`global-guidance`) into a committed tab-separated
manifest — `provider  category  name  src_rel  dest_rel`. `install.sh` and
`doctor.sh` read it via `bin/lib/manifest.sh`, so the type→destination mapping
lives only in the generator. `make check` regenerates it in memory and fails on
drift; run `make manifest` (or `bin/new.sh`, which regenerates automatically) to
refresh it. Never hand-edit it.

## The completeness model

The six capability types split into "clean" (a directory/file maps 1:1 to a
row) and "fuzzy" (no such mapping). Completeness — every shipped
non-template capability appears — is enforced differently for each.

### Clean types — bijection

Inventory rows of each clean type must exactly match the filesystem set. A
missing, extra, or renamed capability fails CI:

- `skill` ⟷ `skills/*/` (dirs with a `SKILL.md`, excluding `_template`)
- `command` ⟷ `commands/*.md` (excluding `_template.md`)
- `agent` ⟷ `agents/*.md` (excluding `_template.md`)
- `global-guidance` ⟷ `global/CLAUDE.md`, `global/AGENTS.md`

### Fuzzy types — classified ledger

Every candidate `bin/*.sh` or `docs/**/*.md` file must be **either** an
inventory row (type `script` or `contract`) **or** an explicit entry in the
`not_a_capability` ledger carrying a one-line `reason`. An unclassified new
file fails CI until it's classified one way or the other — this is what
converts the fuzzy boundary into an enforced, auditable decision instead of a
silent omission.

Auto-exclude rules keep the ledger small — matched *before* the ledger is
consulted, so they never need hand entries:

- `bin/test-*.sh` — the test harness, never a capability.
- `docs/design/**`, `docs/plans/**` — specs and plans (this doc's own design
  spec lives here and is excluded).

Candidate sets are git-tracked files only: `bin/*.sh` and `docs/**/*.md`
(minus the auto-excludes above).

### Bound table (criterion c)

`bin/check-inventory.py` also cross-checks the inventory against one
hand-maintained table: the set of `skill`-type names in the inventory must
equal the set of skill rows in `docs/skill-portability-audit.md`'s per-skill
table. Drift in either direction fails. This is deliberately the richest,
most drift-prone per-item table in the repo, so it's the one wired up as the
"checked against" target for #29's "at least one manual table generated from
or checked against the inventory" criterion.

**This means adding a new skill touches two files, not one:** a row in
`capabilities.json` *and* a row in `docs/skill-portability-audit.md`'s table.
`bin/new.sh` only appends the inventory row (see below) — the audit-table row
is still a manual step, and `make check` will fail with a `check_bound_table`
diagnostic until it's added.

## How to add a capability

1. **Skill, agent, or command:** scaffold with `bin/new.sh skill|agent|command
   <name>`. It appends a draft `capabilities.json` row with the derived
   fields filled in (`name`, `type`, `path`, `description` copied from the
   new frontmatter) and placeholders for you to complete: `provider`,
   `maturity: draft`, `mutation`, `version_introduced`. Fill those in, then —
   **for a new skill only** — also add a row to
   `docs/skill-portability-audit.md`'s per-skill table (the bound-table
   check requires the two skill sets to match; `bin/new.sh` does not do this
   part for you).
2. **Global guidance:** there are only two rows (`claude`/`global/CLAUDE.md`,
   `agents`/`global/AGENTS.md`); this set essentially never grows. If it
   ever does, add the row by hand.
3. **A new `bin/*.sh` script or `docs/**/*.md` file:** decide whether it's a
   capability. If it is, add a row with `type: script` or `type: contract`.
   If it's internal machinery, a test harness, an audit artifact, or a
   planning doc that isn't itself invoked as a capability, add it to
   `not_a_capability` instead, with a one-line `reason`. Either way, CI fails
   on an unclassified file — that's the enforcement mechanism, not an
   optional courtesy.
4. **Run the validator** and let its diagnostics drive what's still missing:
   `python3 bin/check-inventory.py --root .` (or just `make check`, which
   runs it as one of its numbered sections). It reports schema errors,
   missing/extra bijection rows, unclassified fuzzy candidates, dangling
   paths, frontmatter-description drift, missing `PRESSURE-TESTS.md` for
   `tested` skills, and bound-table drift, one diagnostic per line. Don't
   hand-guess completeness — the validator is the completeness oracle.
5. `make test` also runs `bin/test-check-inventory.sh`, which exercises the
   validator itself against small pass/fail fixtures (not the real
   `capabilities.json`).

## Deferred follow-ups

Named explicitly as out of scope for v1, not forgotten:

1. Generate the README mapping blocks and `provider-interop.md` install-layout
   table from the inventory, replacing the current hand-maintained
   duplication with derivation.
2. Extend the bound-table check to validate `provider-interop.md`'s
   capability matrix rows the same way it validates the skill-portability
   audit table.

Single-sourcing the type→install-destination mapping (previously listed here)
is done — see [`install-manifest.tsv`](#install-manifest-tsv-generated) above
(#79).
