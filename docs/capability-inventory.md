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

## What it generates

The inventory now drives both generated install projections and selected
documentation tables:

- `install-manifest.tsv` is generated from installable capability rows and is
  consumed by `install.sh` / `doctor.sh`.
- The provider install-layout blocks in `README.md` and
  `docs/provider-interop.md` are generated and drift-checked by
  `bin/check-inventory.py`.

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
| `install_destination` | no | authored | optional per-row override of the derived destination. Destinations are otherwise derived from `type` into the generated `install-manifest.tsv`, which `make check` drift-checks and `install.sh`/`doctor.sh` consume (see #79). Honored for a same-directory rename; a cross-subdirectory override is not fully wired (parent-dir creation and prune coverage) and no row uses one today. |
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
(`skill`/`agent`/`command`/`global-guidance`, plus the local `bindle`
executable) into a committed tab-separated manifest — `provider  category  name
src_rel  dest_rel`. `install.sh` and `doctor.sh` read it via
`bin/lib/manifest.sh`, so the type→destination mapping lives only in the
generator. `make check` regenerates it in memory and fails on drift; run
`make manifest` (or `bin/new.sh`, which regenerates automatically) to refresh
it. Never hand-edit it.

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

### What the validator does *not* cover: hand-written prose

The validator governs generated text only — what sits inside
`<!-- GENERATED:... -->` markers. Prose outside those markers can contradict
the inventory indefinitely, and did (#290/#291): a hand-written README
paragraph said a Codex install ships `global/AGENTS.md` and nothing else, two
lines below a generated block listing the Codex-installed skills.

One narrow cross-check now closes that specific class — `bin/check.sh`'s
"codex provider docs" section. While any skill carries
`provider.codex: "installed"`, it requires the user-facing install docs to
name `--agents-skills-home`, and forbids the contrary claim — that a Codex
install ships `global/AGENTS.md` and nothing else — as a statement of current
behavior in any tracked Markdown outside the historical records (`CHANGELOG.md`,
`docs/design/**`, `docs/plans/**`, `docs/superpowers/plans/**`). It is a fixed
doc list plus two literal claim patterns, deliberately not a prose linter; the
allow/skip lists live at the top of `bin/check.sh` with a comment per entry.

## Deferred follow-ups

Named explicitly as out of scope for v1, not forgotten:

1. Generate the README mapping blocks and `provider-interop.md` install-layout
   table from the inventory, replacing the current hand-maintained
   duplication with derivation.
2. Extend the bound-table check to validate `provider-interop.md`'s
   capability matrix rows the same way it validates the skill-portability
   audit table.

Single-sourcing the type→install-destination mapping (previously listed here)
is done — see [`install-manifest.tsv`](#install-manifesttsv-generated) above
(#79).
