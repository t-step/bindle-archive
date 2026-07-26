# gitleaks gate — design (#354)

**Date:** 2026-07-26 **Issue:** #354 **Status:** approved, not yet implemented

## Problem

`gitleaks` is installed (8.30.1), `.gitleaks.toml` has been narrowed and verified
against the built-in ruleset (#259), and the repo scans clean — but the scan is
wired into no gate. It is absent from `Makefile`, `bin/check.sh`,
`.pre-commit-config.yaml` and `.github/workflows/`. Everything expensive has been
paid for; what is missing is a call site.

## What the scan modes can actually see

Measured on this repo, 2026-07-26:

| Mode | Sees | Cost |
| --- | --- | --- |
| `gitleaks git .` | every commit (523) | 1.5 s, 5.85 MB |
| `gitleaks git --staged` | staged content | 40 ms |
| `gitleaks dir .` | working tree incl. untracked, ignores `.gitignore` | noisy — a prior run reported 100 hits where the tracked-file count was 3 |

The load-bearing fact: **a history scan is blind to staged content**, because
staged content is not yet a commit. A gate wired only into `make check` would
therefore have reported clean on PR #345's three home-path hits at the moment
they were staged — reproducing the #347 hole rather than closing it. The two
useful modes cover different things, so the design keeps both.

## Design

### One script, two modes

`bin/check-gitleaks.sh [--staged | --history]` owns everything gitleaks: mode
selection, scope disclosure, and missing-binary handling. No other file learns
the gitleaks CLI.

| Mode | Invoked by | Scans | States |
| --- | --- | --- | --- |
| `--staged` | pre-commit hook `bindle-gitleaks` | staged content | count of staged files scanned; PARTIAL banner naming unstaged-modified and untracked files it did not see |
| `--history` | a `bin/check.sh` section, full `make check` only | all commits | count of commits scanned; PARTIAL banner naming working-tree content not yet in history |

Both modes pass `--redact --no-banner`; the config resolves from `.gitleaks.toml`
by target path. The history sweep does **not** run under `--content-only`, so a
commit runs the staged scan once instead of both.

### Three verdicts, never conflated

1. **Hit** — print the redacted findings, exit 1.
2. **Clean** — `no leaks — <N> <units> scanned`, followed by the PARTIAL banner
   when anything was outside scope.
3. **Binary absent** — `NOT RUN: gitleaks not installed`, an install hint, and
   exit 0. The word *clean* never appears on this path.

Per #347, the PARTIAL banner prints on red runs too, so fixing findings cannot
silently promote a partial scan to a clean one. The absent-binary path exits 0
deliberately: `bin/check-private-info.sh` is the always-on, dependency-free
layer, and a gate that blocks work on a missing optional tool gets bypassed
rather than heeded. The cost of that choice is a sixth "skipping" notice in
`bin/check.sh`, a shape this repo already treats as a wart — accepted here
because the notice names a real, fixable local condition rather than a CI
promise.

### Scope disclosure, concretely

The banner mirrors the #347 implementation in `bin/check-private-info.sh`:
enumerate what was skipped, cap the list at ten, exclude ignored files, and
report nothing when the scope *is* the argument list. `--staged` skips the
unstaged and untracked; `--history` skips everything not yet committed.

## What this design deliberately does not build

**The `private-ok` / allowlist pairing check.** `bin/check-private-info.sh`
honors an inline `private-ok` marker; gitleaks has no marker equivalent and needs
a `.gitleaks.toml` path allowlist instead, and nothing enforces the pairing. The
issue asked for a report of any file carrying `private-ok` without a matching
allowlist entry.

Measured before designing: **6 tracked files carry `private-ok`, and only 3 are
covered by the allowlist** — while the repo scans clean. The three uncovered
files need no entry; their markers annotate patterns gitleaks does not match. A
checker written to the literal criterion would emit three false alarms on every
run, which is how a notice gets ignored.

The deeper point is that the criterion was written when nothing ran gitleaks.
**Once the gate exists, the divergence cannot be silent in either direction:** a
`private-ok`'d fake secret with no allowlist entry reddens the gate at commit
time, and an allowlisted file with no marker reddens the private-info scan. The
wiring is the enforcement. Building a second checker on top of it buys nothing
and costs a fixture.

Also out of scope: CI wiring (billing-blocked repo-wide, #267 — it buys no signal
today), `gitleaks dir`, and any change to `.gitleaks.toml`'s rules or its
HISTORY-ONLY entries.

## Testing

`bin/test-check-gitleaks.sh`, auto-discovered by `bin/run-test-suites.sh` — and
`git add`ed before any count or green is trusted, since discovery is by
`git ls-files`.

1. Planted synthetic secret in a throwaway fixture repo — the gate reddens.
2. The same secret **staged but uncommitted** — `--staged` reddens, `--history`
   does not and names the file in its banner. This pair is what proves the two
   modes are not redundant; without it, either mode alone looks sufficient.
3. Secret present in history, working tree clean — `--history` reddens.
4. Binary absent (invoked with `PATH` stripped) — exit 0, output contains
   `NOT RUN` and does not contain `clean`.
5. Every assertion verified RED before the implementation exists, then mutated to
   confirm it can fail for the right reason.

Two fixture hazards, both previously paid for in this repo:

- **The suite must not become a finding.** The synthetic secret is assembled at
  runtime from fragments rather than written as a literal, so the tracked suite
  file carries no matchable secret and needs no allowlist entry of its own —
  which would otherwise re-introduce the asymmetry this design declined to
  automate.
- **`git` fixture isolation.** The suite unsets `GIT_DIR`, `GIT_WORK_TREE`,
  `GIT_INDEX_FILE`, `GIT_OBJECT_DIRECTORY` and `GIT_COMMON_DIR` at the top: git
  sets `GIT_DIR` in the pre-commit hook environment and it overrides `git -C`,
  which has previously corrupted the real checkout. A before/after ref-count on
  the primary checkout confirms zero leakage.

## Wiring and ledger

- `.pre-commit-config.yaml` gains `bindle-gitleaks` (`language: script`,
  `pass_filenames: false`, `always_run: true`).
- `bin/check.sh` gains one section calling the script in `--history` mode.
- `bin/check-gitleaks.sh` is machinery invoked *by* `bin/check.sh` and pre-commit,
  so it is a `not_a_capability` ledger entry — not a `script` capability row,
  which is what a user-invoked `bin/check-*.sh` would be.
- `docs/privacy-boundaries.md` loses its "on-demand only" description of gitleaks.
- CHANGELOG gains an entry; this spec gains its own ledger entry, since
  `docs/superpowers/specs/**` is not AUTO_EXCLUDEd.

## Acceptance mapping

| Issue criterion | Where satisfied |
| --- | --- |
| a gate runs gitleaks and fails on a hit | verdict 1, both modes; test 1 |
| scanned scope stated, no green on an unstaged tree | PARTIAL banner, both modes; test 2 |
| `private-ok` divergence reported rather than silent | satisfied by the wiring itself — see "What this design deliberately does not build" |
| self-test plants a secret and confirms the gate reddens | tests 1–3 |
