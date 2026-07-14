# Design — portable package release-integrity workflow

**Status:** Design spec, v1 · **Issue:** thomas-estep/bindle#59 (parent #55) ·
**Date:** 2026-07-14

A point-in-time brainstorming spec. The shipped capability is the contract doc
`docs/package-release-integrity.md`, the skill
`skills/package-release-integrity/`, and its helper; this file is a planning
artifact, not itself a capability.

## Problem

Bindle validates its *own* repository release (`bin/release.sh` guards a clean
tree, semver `VERSION`, and a `## [Unreleased]` changelog section;
`bin/release-manifest.py` records provenance for #33). It has no portable way to
answer a different question that DomI answers for consumer repos: *is a
project/package release internally consistent and safe to cut?* — version-source
agreement, tag/version equality, changelog presence, correct semver movement
(including pre-1.0), track routing, and a verification gate, all *before* any
publish action.

DomI already owns a `release-integrity` skill (upstream, with scripts). #59 does
**not** copy or replace it. Per the #55 principles, DomI stays authoritative for
DomI-owned policy; Bindle extracts the *portable contract beneath* it so the
same checks can be followed by Claude Code, Codex, or a human without DomI
installed — and defers to DomI where a repo declares DomI release governance
authoritative.

## Scope (slice 1)

Python packages only (the concrete, repeated dependency in the active mesh).
The contract is designed so other ecosystem adapters can be added later without
becoming a universal release framework.

**Clean-room:** no code or prose is copied from DomI's skill. Structural
similarity (a checker with verbs, semver logic) is convergent, not vendored.

## Deliverables

1. `docs/package-release-integrity.md` — the provider-neutral contract. Flat in
   `docs/`, matching the existing contract-doc convention (status line →
   categories → worked examples → "Where this fits"); **not** a new
   `docs/workflows/` subdir. Carries the 9 checks, the defer rule, and worked
   examples.
2. `skills/package-release-integrity/` — the Claude-native skill:
   `SKILL.md`, `PRESSURE-TESTS.md`, and `scripts/`.
3. `skills/package-release-integrity/scripts/release_integrity.py` — the
   deterministic helper (stdlib only: `tomllib`, `re`, `subprocess`).
4. `skills/package-release-integrity/scripts/selftest.py` — auto-discovered and
   run by `bin/check.sh` (zero extra Makefile wiring for the selftest).
5. `skills/package-release-integrity/tests/fixtures/` — 7 synthetic Python
   package scenarios.
6. `bin/test-package-release-integrity.sh` — the RED→GREEN fixture suite, wired
   into `Makefile` `test:` and `.pre-commit-config.yaml`.
7. Registration: a `type:"contract"` row (doc) and a `type:"skill"` row (skill)
   in `capabilities.json`; an 11-column row in `docs/skill-portability-audit.md`.

## Architecture — the control flow the skill drives

```
1. Detect authority  ── reuse the domi-consumer skill (#58): is there a
   │                     .domi-pin, and is "release-integrity" a DomI-owned
   │                     policy category in this repo?
   ├─ YES → DEFER: report "DomI authoritative here — run DomI's
   │        release-integrity". Bindle's checks may run advisory-only; they
   │        never override DomI and never claim to replace it.
   └─ NO  → PORTABLE: run the mechanical helper + the contract judgment steps.

2. Discover  ── version source (pyproject.toml / package module / generated),
                release-check command, pre- vs post-1.0, changelog convention,
                tag naming, and whether the repo separates code / data /
                dataset / deployment tracks.
3. Mechanical checks (helper) ── version-source consistency, tag==version,
                changelog-present, semver-movement-given-declared-class.
4. Judgment steps (contract-guided) ── change classification (#1) and track
                routing (#8): the helper returns "uncertain"; a human/agent
                decides, guided by the contract.
5. Gate ── shell out to the repo's own build (#6) and test (#7) commands.
6. Report ── ready / not-ready with per-check evidence. Never authorizes
                publish.
```

Step 1 reuses the already-shipped `domi-consumer` skill (#58) for authority
detection — no new drift/pin logic is invented here.

## The nine checks (from #59) and who owns each

| # | Check | Owner |
|---|-------|-------|
| 1 | Change classification (breaking / additive / fix / data-only) | **Judgment** — helper emits `uncertain`; never guesses breaking (non-goal) |
| 2 | Required version movement (incl. explicit pre-1.0 rules) | Helper, **given** a declared change class |
| 3 | Version-source consistency (all authoritative/derived versions agree) | Helper |
| 4 | Tag consistency (proposed/existing tag == package version) | Helper |
| 5 | Changelog / release-note presence where the repo requires it | Helper |
| 6 | Build-metadata validation using the repo's own package tools | Helper shells out |
| 7 | Verification gate (repo tests/checks pass) | Helper shells out |
| 8 | Track routing (data-only change must not churn the package version) | **Judgment** — helper flags; contract guides |
| 9 | No publication authority | Contract text — never a code action |

## The helper — `release_integrity.py`

- **CLI:** `release_integrity.py check [--repo PATH]
  [--change-class breaking|additive|patch|data-only] [--json]`.
- **Output:** per-check verdicts `pass` / `fail` / `uncertain`. Classification
  (#1) and track routing (#8) return `uncertain` unless `--change-class` is
  supplied; the helper never infers a breaking change.
- **Exit code:** non-zero on any `fail`. `uncertain` alone does **not** fail —
  it is a "human must decide" signal, per the "report uncertainty when
  public-API impact cannot be determined mechanically" boundary.
- **Dependencies:** stdlib only. `tomllib` (3.11+) parses `pyproject.toml`; no
  `packaging` dependency — semver comparison is a small internal function.
- **Discovery, not assumption:** the version source, release-check command,
  changelog convention, tag naming, and track split are discovered from the
  target repo, not hard-coded.

## Fixtures and tests

`skills/package-release-integrity/tests/fixtures/` — 7 directories, one per
acceptance scenario, each a minimal `pyproject.toml` plus whatever
changelog/tag state the case needs:

`pre-1.0-breaking`, `post-1.0-breaking`, `additive`, `patch`, `data-only`,
`tag-mismatch`, `missing-changelog`.

These are the first `pyproject.toml` fixtures in the repo (greenfield).

`bin/test-package-release-integrity.sh` follows `bin/test-check.sh`'s shape
(a `pass`/`fail` counter with `contains` / `not_contains` helpers over captured
output, throwaway fixture dirs under `mktemp -d` with a cleanup `trap`). It runs
the helper against each fixture and asserts the expected verdict. Wired into the
`Makefile` `test:` list **and** `.pre-commit-config.yaml`. `scripts/selftest.py`
covers the helper's pure logic (semver movement, version-source parsing) and is
auto-run by `make check`.

**Pressure test (required before "done"):** per the repo rule, a skill is a
CHANGELOG **draft** until pressure-tested — fresh subagents in throwaway fixture
repos (~5 reps/variant), scored on the filesystem/verdict, not self-report,
recorded in `PRESSURE-TESTS.md`. The RED arm is validated by confirming the
skill is absent first.

## DomI defer-path validation (acceptance criterion 3)

A read-only dry-run in a `.domi-pin` repo (DomI itself) confirming step 1
detects DomI release governance and the skill **defers** (advisory-only, no
override) rather than running its portable checks as authoritative. The portable
path is proven by the 7 fixtures; the defer path is proven here.

## Capability registration (the triple-touch FOOTGUN)

1. `capabilities.json`: a `type:"contract"` row (path → the doc) **and** a
   `type:"skill"` row (`bin/new.sh skill package-release-integrity` scaffolds a
   draft skill row; the contract row is hand-added). This spec file itself gets
   a `not_a_capability` entry.
2. `docs/skill-portability-audit.md`: an 11-column matrix row for the skill
   (manual — `bin/new.sh` does not touch this file).
3. Portability disposition: the helper is stdlib Python that shells out to the
   repo's own tools → **Codex-portable**; the `SKILL.md` invocation wording
   stays Claude-native (Phase 1).

## Boundaries and non-goals (restated so implementation honors them)

- Never bump a version merely because the workflow was invoked; recommend
  first, mutate only under explicit delegated scope.
- A green package check is **not** authorization to publish, push tags, update
  datasets, or deploy.
- Repo-local release instructions and inherited DomI policy win over generic
  Bindle defaults.
- Network / tool failure produces `uncertain` or a degraded report — never a
  false "ready" / "already-done".
- **Out of scope:** publishing to any registry or deploy target; automatically
  deciding whether a nuanced API change is breaking; replacing repo-specific
  release scripts; signing / provenance attestations (later release work).

## Testing summary

- `make check` green (helper `selftest.py` auto-run; contract doc passes
  frontmatter/link/private-info checks; capability inventory reconciles).
- `bin/test-package-release-integrity.sh` green over all 7 fixtures.
- Pressure tests recorded in `PRESSURE-TESTS.md` before the CHANGELOG entry
  drops its "draft" marker.
- DomI defer-path dry-run confirms the deferral branch.
