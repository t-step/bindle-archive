# Pressure-test series fields — design (#467, #356)

**Date:** 2026-07-26 **Issues:** #467, #356 **Status:** approved, not yet
implemented

## Problem

`docs/pressure-testing-protocol.md` § Recording requires every rep series to
record its `**Model:**` (#331) and `**Content:**` (#339), and as of #332 a
safety claim is *scoped* to the content id recorded beside it. Nothing enforces
either field (#467). Separately, thirteen `skills/*/PRESSURE-TESTS.md` files
carry a hand-maintained caveat marking which series predate the
arm-declaration rule (#223, #261); nothing keeps that caveat true as compliant
series are appended (#356).

Both reduce to the same missing thing: **there is no machine-readable record of
a series.** Measured on `main` @ `91cab1c`:

- 34 `**Model:**` and 34 `**Content:**` field blocks exist across the 13 files,
  so every *existing* series already carries both. The gap is the next append.
  (Counted line-anchored. An unanchored `grep -c` reports 35 `**Content:**` —
  one is a prose mention, not a field. The field is the record; prose is not,
  and the count that matters is the anchored one.)
- Series boundaries are not syntactically marked. A field block sits at the file
  preamble ("every series in this file"), at `## Method`, at `## Claim N`, and
  at `### Results — series 2` — four different depths in four files. **4 of the
  34 blocks sit at `###` depth**: `session-continuity:906` and
  `verify-then-commit:193`, `:242`, `:282` (three weaker-model rerun series).
- Protocol status is expressed three ways: a blanket file-level caveat (9
  files), a per-series table (`release-captain`, `package-release-integrity`),
  and per-claim prose (`verify-then-commit`, `session-continuity`).

A series appended tomorrow with no fields at all is therefore indistinguishable
from a grandfathered one, and every gate stays green.

## Design

### 1. `**Protocol:**` becomes the third field

Protocol status stops being prose above the evidence and becomes a field beside
the two that already exist, in the same method block:

```
**Model:**    Opus 5 (`claude-opus-5[1m]`), Claude Code — both arms.
**Content:**  GREEN arm `sha256:8125f826c579`, captured at declaration.
**Protocol:** compliant — arm predeclared, fixture checklist 8/8
```

Legal values, and nothing else:

| Value | Means |
| --- | --- |
| `compliant` | ran under the method of record; arm declared before dispatch |
| `pre-protocol` | predates the arm-declaration rule; grandfathered per #261, not voided, not owed a re-run |
| `unrecorded` | honest unknown — the protocol's standing escape, never silence |

Granularity matches `**Model:**` and `**Content:**`: per-series, with a
per-arm/per-rep override. Free prose may follow the value on the same line or a
continuation line (the reason, the issue reference); the parser reads the whole
field the way #459 taught it to — the line and its wrapped continuation, up to
the next blank line, field, heading or list item.

This is #356's canonical shape. It is chosen over a canonical per-file table
because a table restates series that live further down the same file, which is
the decay #356 exists to stop; and over teaching the gate all three prose shapes
because the per-claim form is freeform English, the shape most likely to parse
green against zero real inputs (#459).

Consequence for the 13 head caveats: each shrinks to a pointer — the split is
per series, read each series' `**Protocol:**` field — and stops enumerating.
The #261 grandfathering rationale stays stated once, in the caveat; what moves
is the *list* of which series it covers.

### 2. One script, two modes

`bin/check-pressure-series.sh [--staged | --all]`, mirroring
`bin/check-gitleaks.sh` (#354). The two modes see different things, so neither
alone is the gate.

| Mode | Invoked by | Asks |
| --- | --- | --- |
| `--staged` | pre-commit hook `bindle-pressure-series` | does the staged diff add a `##` heading to a `skills/*/PRESSURE-TESTS.md` without a complete field block under it? |
| `--all` | a `bin/check.sh` section (full `make check` only) | is every field block in the tree complete and well-formed? |

`--staged` is what makes grandfathering free: it fires on the *append*, so the
12 files carrying `**Content:** unrecorded` need no edits to stay green (#467
acceptance 2, #261 — grandfathered counts are not re-litigated).

**`--staged` trigger — depth calibrated per file.** A file's triggering depths
are **the depths at which it already carries field blocks**, read from the file
itself rather than assumed. Concretely, at `91cab1c`:

| File | Block depths | Added heading that triggers |
| --- | --- | --- |
| `verify-then-commit`, `session-continuity` | `##` and `###` | `##` and `###` |
| the other 11 | `##` (or preamble) | `##` only |
| a file with no blocks yet | — | `##` (default) |

This is why the rule is calibrated rather than fixed: `###` is the series depth
in two files (three weaker-model reruns and one top-up series) and pure
narrative in the rest (`### Environment`, `### Two distinct defects`,
`### Honest coverage caveat`). A global `##`-only rule would miss 4 of 34 real
series; a global `##`+`###` rule would demand an escape marker on ~200 narrative
subsections, which is the always-firing notice #347 warns gets bypassed rather
than heeded. The calibration comes from the tree, so it cannot drift from it.

A triggering heading must have `**Model:**`, `**Content:**` and `**Protocol:**`
within its section (up to the next heading at the same or shallower depth), or
carry the marker `<!-- not-a-series: <reason> -->` on the heading line. The
marker follows this repo's existing escape-hatch precedent — `private-ok`,
`label-hygiene-guard: inert` — a greppable record rather than a quietly
reworded heading.

**Stated limit, printed by `--staged` itself:** a file that carries no field
block yet triggers on `##` only, so a *first* series introduced at `###` depth
in a new evidence file is not caught at commit. `--all` still validates its
block if it has one. A disclosure, not a silent hole.

**`--all` checks**, per field block: all three fields present; each carries a
value or the explicit `unrecorded`; `**Protocol:**` is one of the three legal
values. It reports the number of files and blocks scanned, so a green states
its own scope (#347).

### 3. Verdicts

Three, never conflated — the #354 shape:

| Verdict | Exit | When |
| --- | --- | --- |
| green | 0 | every block complete; scope stated |
| red | 1 | a triggering append with no block, or an incomplete/illegal block; each finding names file and line |
| NOT RUN | 0 | `--staged` outside a git repo, or no `skills/*/PRESSURE-TESTS.md` present |

## What this design deliberately does not build

- **No check that a `**Protocol:** compliant` claim is true.** The field records
  what the author declares; verifying that an arm really was predeclared is not
  mechanically decidable from the file. #356's invariant is that the caveat
  cannot silently go stale — a series now carries its own status, so an append
  cannot invalidate a statement made about other series.
- **No re-litigation of grandfathered counts** (#261). `pre-protocol` is a legal
  value, not a finding.
- **No `**Claim:**` enforcement.** #332 makes a claim optional and the silence
  rule intentional; a required claim field would invert it.
- **No CHANGELOG entry.** Release Please generates entries from the Conventional
  Commit; a hand-written one is reverted.

## Testing

`bin/test-check-pressure-series.sh`, written RED first, discovered by
`bin/run-test-suites.sh`.

- **Fixture copied from reality (#459).** At least one fixture is a verbatim
  copy of a real block out of the repo — `session-continuity` Claim 9 — never
  a block hand-written in the form the parser expects. A parser proved only
  against its own preferred form proves nothing about the tree.
- **Live-match count before believing green.** The suite asserts `--all` reports
  a block count equal to the real line-anchored `**Model:**` block count (34 at
  `91cab1c`; re-measured at implementation, never quoted from this document —
  see the recorded rule against citing a count from a note). A parser reporting
  0 is the alarm.
- **Depth calibration asserted on a real file.** A fixture copied from
  `verify-then-commit` (blocks at both depths) proves a `###` heading triggers
  there; one copied from `release-captain` (blocks at `##` only) proves a `###`
  heading does not. Two files, opposite expected answers, same code path.
- **Both modes on one fixture**, so a later simplification cannot collapse them.
- **Mutation pass.** Empty the legal-value list, invert the `##`-vs-`###`
  trigger, drop the escape-marker branch: every negative assertion must flip to
  failing. A survivor is checked for dead code before a test is written for it.
- **`bin/test-check.sh` clean-exit floors** re-run, since `check.sh` gains a
  section (#295's trap: fixture repos containing no `bin/` script).

## Wiring and ledger

- `.pre-commit-config.yaml`: `bindle-pressure-series`, `entry:
  bin/check-pressure-series.sh --staged`, `pass_filenames: false`,
  `always_run: true`.
- `bin/check.sh`: a section guarded on `[ -x bin/check-pressure-series.sh ]`,
  full-run only (not `--content-only`).
- `capabilities.json`: `not_a_capability` entries for both the script and its
  suite, inserted textually — never via a `json.load`/`json.dumps` round-trip
  (#281).
- `docs/pressure-testing-protocol.md` § Recording: the `**Protocol:**` field
  definition, its legal values, and the two-mode gate named as its enforcement.

## Delivery — two PRs

One issue, one branch, one PR. The gate would be red against an un-retrofitted
tree, so the record change lands first.

| PR | Branch | Contents | Closes |
| --- | --- | --- | --- |
| A | `feature/356-protocol-field` | this spec; the protocol-doc field definition; `**Protocol:**` retrofitted onto every existing block; the 13 head caveats collapsed to pointers | — |
| B | `feature/467-series-field-gate` | the script, its suite, pre-commit + `check.sh` wiring, ledger entries | #467, #356 |

Each existing block's retrofit value is *derived from that file's own caveat
prose*, not guessed: the 9 blanket files are `pre-protocol` throughout; the two
table files and the two per-claim files already state the split per series.

## Acceptance mapping

**#467**

| Criterion | Where met |
| --- | --- |
| appending a series recording neither field fails a gate | `--staged` trigger |
| grandfathered series stay green without edits | `--staged` fires on appends only; `pre-protocol`/`unrecorded` are legal values |
| explicit `unrecorded` passes | legal value in all three fields |
| fixture copied from a real series | Testing, first bullet |
| self-test proves the gate reddens; assertions mutation-checked | Testing, RED-first + mutation pass |

**#356**

| Criterion | Where met |
| --- | --- |
| appending a series without updating its caveat fails a gate | the caveat *is* the per-series `**Protocol:**` field, and `--staged` requires it |
| one canonical caveat shape, or the gate handles each shape | one shape: the field |
| self-test appends a compliant series to a fixture, gate reddens | Testing, both-modes fixture |
