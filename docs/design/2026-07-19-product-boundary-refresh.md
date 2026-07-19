# Design: refresh the product boundary past v0.4

**Date:** 2026-07-19 · **Status:** Approved design, pre-implementation
**Issue:** [thomas-estep/bindle#283](https://github.com/thomas-estep/bindle/issues/283)
**Target:** `thomas-estep/bindle` (repo-local docs + one `bin/check.sh` section; nothing installed into `~/.claude/`)

## Problem

`docs/product-boundary.md` is titled "Product boundary (v0.3–v0.4)". Its newest
Backlog triage is dated 2026-07-12 and classifies nothing above #88. The backlog now
runs past #283. It is the document every "this is deliberately out of scope" call rests
on, and it has not covered the period in which most of the current backlog was filed.

The scope gate is not wrong — it is not in force.

Two distinct failures are tangled together here, and separating them is the whole design:

1. **A wrapper expired.** The version range in the title, and the "next one or two minor
   releases" framing, made the document self-limiting. Nothing announced the expiry.
2. **A mechanism duplicated a live system.** Per-issue Backlog triage restated, in a
   static table, state that GitHub labels already hold live.

The durable content — Decision, Owned surfaces, Provider boundary, Operational
definitions, Explicit non-goals, Admission criteria, Revisit triggers — was **not**
falsified by any of the ~200 issues filed since. Verified by reading it against the
current open set: no line in those sections is contradicted by shipped work. This
refresh therefore preserves that content and replaces only the two failed mechanisms.

## Locked decisions (from brainstorming)

1. **Per-issue triage is retired.** The document states that it no longer triages
   individual issues, and names what does: the `status:`/`priority:` labels defined in
   `docs/issue-tracking.md`, which are the live record and already feed the dashboard. A
   third static table would be a stale duplicate of a live system and would reset the
   same clock this issue documents. Both existing tables are retained and marked
   historical — they are evidence of past reasoning, not current state.
2. **A "contested calls" section is kept.** Spot rulings on genuinely disputed scope
   questions are recorded there, by issue number, with a one-line rationale. This is the
   narrow case per-issue triage actually served well: not routine classification, but a
   hard call worth not re-litigating. It grows only when a call is contested.
3. **The document becomes unversioned.** The title drops its range; the preamble
   reframes it as a standing decision record amended when a Revisit trigger fires. Its
   triggers already work — three have fired and been adjudicated in place. This is a
   **deliberate deviation from #283's acceptance criterion 1** as literally written
   ("rescoped to the current release line and says which releases it governs"); see
   "Deviation from AC1" below.
4. **The deferral rule lands under Admission criteria**, not as a standalone section,
   because it answers an admission question.
5. **Staleness is gated, not ritualized.** An `Affirmed through:` line plus a
   `bin/check.sh` section that compares it to `VERSION`'s minor. A checklist item is the
   same class of mechanism that already lapsed once here; this repo's operating
   assumption is that a rule which is not gated does not hold.

## What changes in `docs/product-boundary.md`

Preserved byte-for-byte: `## Decision`, `## Owned surfaces`, `## Provider boundary`,
`## Operational definitions`, `## Admission criteria` (extended, see below),
`## Revisit triggers` (extended, see below), and the whole
`## Revisit 2026-07-14 — the Codex-primitives trigger (#55)` adjudication.

| Location | Change |
| --- | --- |
| Line 1, title | `# Product boundary (v0.3–v0.4)` → `# Product boundary` |
| Preamble (lines 3–8) | "Scope: the next one or two minor releases" → standing-document framing; add `Affirmed through:` line |
| `## Explicit non-goals (v0.3–v0.4)` | drop the range from the heading; body unchanged |
| `## Near-term sequence` | retitle `## Near-term sequence (v0.3–v0.4, historical)`; body unchanged — it already carries its own "all six steps shipped" status note |
| `## Backlog triage (2026-07-12)` | retitle `(2026-07-12, historical)`; body unchanged |
| new `## Backlog triage` | the retire-and-delegate block + `### Contested calls` |
| `## Admission criteria` | append `### Upstream deferral` |
| `## Revisit triggers` | append the staleness trigger |

### The retire-and-delegate block

Replaces per-issue classification. States, in substance:

- This document does not triage issues individually.
- Per-issue state lives in GitHub labels (`status:`, `priority:`) per
  `docs/issue-tracking.md`; that is the live record and the dashboard reads it.
- This document supplies the admission rule those labels are applied against, plus
  rulings on contested calls only.
- The two dated tables below are historical.

### `### Upstream deferral` (satisfies AC2)

> **Deferring to an upstream that owns a policy is in scope and preferred.
> Reimplementing that policy locally is out of scope.**

Rationale recorded with it: deferral preserves the capability and the boundary at once;
reimplementation is the actual "become a DomI+" failure mode, and is the thing worth
forbidding — not the seams.

Worked example, with the measured coupling from the 2026-07-19 audit:

| Skill | DomI references |
| --- | --- |
| `package-release-integrity` | 66 |
| `domi-consumer` | 63 |
| `release-captain` | 50 |
| the other 11 shipped skills | 0 |

Those are deferral seams — Bindle declining to own semver governance where a well-formed
`.domi-pin` marks it inherited. Named explicitly as **in scope and protected**, because
the risk today runs the other way: 50 references in `release-captain` with no scope
document covering the period they were added in reads as creep to a future session or a
dispatched subagent, and nothing on paper currently contradicts that reading.

Corollary, consistent with the existing single-user decision: Bindle serving a repo owner
who *works in* DomI-consuming repos is in scope; Bindle taking DomI's needs as a second
product owner is not.

### The staleness trigger (satisfies AC5)

Added to `## Revisit triggers`:

- **The document falls behind the release line** — `Affirmed through:` names a minor
  older than `VERSION`'s. Unlike the other triggers this one is enforced mechanically
  (see below) rather than noticed; it exists because the failure mode it guards is the
  absence of an event, and the other six triggers all require one.

## Machinery

`docs/product-boundary.md` carries, in its preamble:

```
Affirmed through: v0.8
```

New section in `bin/check.sh`, placed immediately after section 5 (version), which
already reads and validates `VERSION` — the same read is reused, no new parsing:

```
product boundary:
  ✓ boundary affirmed through v0.8 (VERSION 0.8.0)
```

Failure shape:

```
product boundary:
  ✗ docs/product-boundary.md affirmed through v0.8, but VERSION is 0.9.0 —
    re-read the boundary, then update 'Affirmed through:' or amend the document
```

Placement rules, both load-bearing:

- **Not behind `--content-only`.** It is a cheap text comparison with no external tool
  dependency, so it runs in every context: `make check`, the `bindle-content` pre-commit
  hook, and CI. This is the direct lesson of #279 — a check wired only into the full
  `check.sh` reaches no gate.
- **Compares minors only.** Patch releases do not demand re-affirmation; a boundary
  document has nothing to say about a patch.

Coverage added to `bin/test-check.sh`: affirmed == VERSION minor passes; affirmed behind
fails; a malformed or missing `Affirmed through:` line fails. Per #279's lesson the gate
is **proven failable in a scratch copy** before landing — bump `VERSION`'s minor in a
scratch tree, confirm red, restore.

### Amended during implementation — a missing document skips, it does not fail

This design originally specified that an absent `docs/product-boundary.md` should fail the
check, on the reasoning that the gate should not be dodgeable by deleting what it guards.
Implementing it proved that wrong, and `bin/test-check-frontmatter.sh` caught it: several
suites copy `check.sh` into throwaway fixture repos that have no `docs/` tree at all, and
that suite's regression floor asserts a clean `--content-only` exit. Requiring the file
would have coupled every fixture builder in the repo to it — the "maintain two lists"
defect (#227's lesson: derive, don't duplicate).

The original concern turns out to be already covered. Three `capabilities.json` entries
(`delegation-profiles`, `workflow-composition`, `workflow-eval`) name this file under
`related_docs`, so deleting it fails `bin/check-inventory.py` in section 6b with three
errors. Verified by moving the file aside and running the validator.

So section 5b skips when the file is absent and says why. Existence is the inventory's
invariant; freshness is this section's. Neither duplicates the other.

### Known weakness, recorded deliberately

`VERSION` lags merged work (#265 — `bin/release-please-sync.sh` is its only writer and
has no-op'd on two cuts). So this gate can fire **late**. It cannot fire **wrongly**: a
stale `VERSION` only delays the prompt to re-affirm; it never demands one spuriously.
The failure direction is safe, and this limitation is stated in the document rather than
left to be rediscovered.

## Deviation from AC1

#283's AC1 asks for the document to be "rescoped to the current release line and says
which releases it governs". This design deliberately does the opposite: it removes the
release scoping entirely.

Reason: pinning to a release window is the mechanism that failed. `v0.3–v0.4` expired
silently, with no event to notice, which is how 200 issues accumulated against a document
that had stopped applying. Re-pinning to `v0.8–v0.9` schedules the identical failure a
few months out. The `Affirmed through:` line plus its gate delivers what AC1 was reaching
for — a reader always knows what release state the document was last checked against —
without the silent-expiry property.

Recorded on the issue and in the PR body, following the #257 precedent (deviate, state
it, do not assume approval).

## Acceptance criteria (from #283) → how this satisfies them

| AC | Satisfied by |
| --- | --- |
| rescoped to the current release line, says which releases it governs | **Deviated** — unversioned + `Affirmed through:`; see above |
| deferral rule stated, DomI seams named as the worked example | `### Upstream deferral` under Admission criteria |
| triage extended past #88, **or** the doc states it no longer triages issues and names what does | the retire-and-delegate block (second branch taken) |
| existing DomI-facing functionality unchanged | no skill, `SKILL.md`, or agent touched — see Non-goals |
| a revisit trigger that fires on staleness | `Affirmed through:` + the `bin/check.sh` section |

## File tree

```
docs/product-boundary.md      edited (sections above)
bin/check.sh                  + one section after section 5
bin/test-check.sh             + coverage for that section
```

`capabilities.json` needs no new rows: `bin/*.sh` is already a `not_a_capability` ledger
entry, no new file is created, and no installed asset's frontmatter changes.

## Non-goals

- **This is not a pruning pass.** No skill, command, agent, or DomI seam is removed,
  narrowed, or deprecated by this work. The refresh exists to *defend* existing
  functionality that currently has no scope document covering it.
- No change to `docs/ownership-boundaries.md`, which remains accurate and out of scope.
- No successor "near-term sequence" is declared. What is next is a milestone question,
  and milestones are live where this document is standing.
- No backfill of contested calls. The section starts empty and grows when a call is
  actually contested; inventing rulings for uncontested issues would recreate the
  per-issue triage this design retires.

## Follow-ups (explicitly out of this slice)

- If `Affirmed through:` proves annoying to maintain by hand, `bin/release-please-sync.sh`
  is the natural place to bump it — but not before #265 is fixed, since that script's
  reliability is the open question.
- The contested-calls section may want a convention for superseding a ruling. Deferred
  until a second ruling exists.
