---
name: package-release-integrity
description: Use when validating whether a Python package release is safe to cut or checking the strict mechanical subset required for post-tag publication. Judgment calls (change classification) must be supplied, never guessed. Defers to DomI where a well-formed .domi-pin makes its release-semver-governance category authoritative; never itself authorizes publishing.
---

# Package release integrity

## Overview

Validates that a Python package release is internally consistent before
publish — version declarations agree, the tag matches the version, a
changelog section exists, the semver bump matches the declared change class,
and a data-only change didn't churn the version — mechanically where a
machine can check, `uncertain` where only a human can decide. Where a target
repo has a well-formed `.domi-pin`, DomI's inherited
`release-semver-governance` category is authoritative there and this skill
defers to it instead of running its own checks. In every mode, this skill
only reports; it never bumps a version, tags a release, or authorizes a
publish.

## When to Use

- Before cutting or publishing a Python package release.
- When asked "is this release consistent/safe to cut?" or to sanity-check a
  version bump against a changelog and a proposed tag.
- When a data-only change needs confirmation it didn't move the package
  version.

When NOT to use:
- To actually publish, tag, or bump a version — this skill has no mutation
  path; that stays with the repo's own release tooling.
- As a substitute for Bindle's post-tag provenance contract. The publication
  mode below supplies one evidence check; it does not generate, attach,
  download, or verify the publication artifact.

## Strict publication check

For Bindle's post-tag evidence, run the judgment-free mechanical subset:

```bash
python3 skills/package-release-integrity/scripts/release_integrity.py \
  publication-check --repo . --tag <tag>
```

`publication-check` requires exactly these verdicts to pass:
`version_source_consistency`, `tag_consistency`, and `changelog_present`.
Unlike generic `check`, it accepts no change class, previous version, build
command, test command, or no-changelog override; it never reports `uncertain`.
A well-formed DomI pin returns `mode: "defer"`, `ready: false`, and a nonzero
publication exit instead of treating advisory Bindle checks as evidence. Any
missing source, mismatch, or missing released changelog section also exits
nonzero.

This is only the `release_integrity` item in the four-check publication
evidence envelope. Publication integrity additionally requires the attached
`bindle-release-provenance.json` and detached checksum to be downloaded from
the draft, byte-checked, and semantically verified against the annotated tag,
commit, version, and complete successful evidence. If the attached artifact is
absent or unverified, publication integrity fails even when
`publication-check` passes.

## Steps

The control flow is six steps, all driven by one helper invocation:

```
python3 skills/package-release-integrity/scripts/release_integrity.py check \
  --repo <path> [--tag ...] [--prev-version ...] [--change-class ...] \
  [--build-cmd ...] [--test-cmd ...]
```

1. **Detect authority.** The helper reads `<repo>/.domi-pin` first. A
   well-formed pin (`upstream` set, `sha` a 40-hex commit) means DomI's
   release-semver-governance category is authoritative here — the helper
   returns `{"mode": "defer", "verdicts": [], "ready": None}` and stops. See
   the defer rule below; do not run the remaining steps against a deferring
   repo.
2. **Discover.** In `portable` mode, the helper finds every declared version
   (`pyproject.toml [project].version`, `[tool.poetry].version`, any
   top-level package `__init__.py`'s `__version__`).
3. **Mechanical checks.** Version-source consistency, tag consistency,
   changelog presence, and the repo-supplied `--build-cmd`/`--test-cmd` gates
   are computed directly — no judgment involved.
4. **Judgment steps.** Change classification and the semver movement it
   implies (and, for data-only changes, track routing) depend on
   `--change-class`, which the helper never guesses.
5. **Gate.** `ready = all(verdict != "fail" for verdict in verdicts)` — see
   the boundary below on what this does and doesn't promise.
6. **Report.** Relay the verdict list (or the defer notice) and `ready`
   as-is; do not summarize `uncertain` verdicts as passes and do not treat
   `ready: True` as permission to publish.

These six steps describe the generic pre-release `check` mode. They do not
replace the strict post-tag `publication-check` or its attached-artifact gate.

## Judgment boundary

`--change-class` (`breaking` / `additive` / `patch` / `data-only`) is
supplied by a human or an upstream classification step, never inferred by
the helper. Omit it and `change_classification`, `version_movement`, and
(for non-data-only changes) `track_routing` all report `uncertain` — that is
the correct, honest result, not a bug to work around. `uncertain` means
"classify the change, then re-run the check" — never fill in a guess to
turn it green.

## The defer rule

Defer instead of running the portable checks when the target repo has a
well-formed `.domi-pin` (`upstream` set, `sha` a 40-hex commit) — regardless
of that pin's drift verdict (`current`/`behind`/`forked`/`unverifiable`).
DomI's inherited-category list is fixed, not a per-repo opt-in — there is no
`owned_categories` field — so any well-formed pin always carries
`release-semver-governance`, which is this skill's authority signal. A
missing or malformed pin is not authoritative; run the portable checks
normally. See the `domi-consumer` skill, which owns `.domi-pin` detection
and the drift vocabulary — this skill reuses that authority signal and does
not reimplement drift detection itself.

## Boundaries / red flags

- **A green check is not publish authorization.** `ready: True` is a
  necessary signal, never sufficient — a human still decides whether to cut
  the release.
- **`ready: True` does not mean "every check ran and passed."** `ready` only
  fails on an explicit `fail` verdict; a repo can be `ready: True` with an
  `uncertain` gate sitting unresolved (no `--test-cmd` supplied, no declared
  change class). Treat `uncertain` as "still needs a human," never as a pass
  in disguise.
- **Never bump a version, edit a changelog, or retag just to make a verdict
  pass.** The helper only reads and reports; fix the underlying
  inconsistency through the repo's own release process, not by gaming the
  check.
- **Under defer, do not override DomI.** Once `mode: "defer"` fires, this
  skill's own checks are advisory-only at best and must not be run as if
  they were authoritative — don't hand-roll a substitute assessment.
- **Do not publish on a helper-only result.** Even a passing strict mechanical
  check is insufficient until the attached provenance and checksum have been
  downloaded and verified under `docs/release-provenance.md`.

**REQUIRED BACKGROUND:** `docs/package-release-integrity.md` (the full
contract: all nine checks, verdict keys, and worked examples) and the
`domi-consumer` skill (the defer rule's authority signal).
