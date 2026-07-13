# Design: workflow-eval policy, taxonomy, and result schema

Resolves the design half of issue #35. Status: **approved design, not yet
implemented** — the implementation is `docs/workflow-eval.md` itself (a
doc-sized policy contract; there is no separate build phase, matching how
#31 and #32 shipped). When an implementation question isn't answered here,
decide it while writing that doc and fold the answer back into this design,
not improvise silently.

## Problem

Bindle's RED → GREEN → REFACTOR pressure-test discipline
(`CONTRIBUTING.md`) answers one question well — does a behavioral
instruction change agent behavior under pressure — but nothing defines what
*other* kinds of evaluation a workflow needs, or how required coverage
should scale with a workflow's actual risk. Left alone, low-risk,
deterministic tooling can be over-tested while a workflow capable of
external mutation (a PR merge, a push) can ship with a single pressure
claim and no composition or end-to-end coverage — a real, current gap: see
Worked Example 3.

## Goals

1. Seven eval categories, defined once, each grounded in a real example
   already in this repo — no invented workflow to make the taxonomy tidy.
2. A risk-based minimum-coverage matrix that reuses
   `runtime-security-privacy.md`'s existing C0–C5 mutation classes rather
   than inventing a parallel risk vocabulary (per
   `docs/workflow-composition.md`'s "declaring dependencies: reference,
   don't restate" convention).
3. A machine-readable result schema, split per the issue's own instruction
   into state-based (mechanical, preferred for critical outcomes) and
   model-graded (softer, explicitly marked) fields.
4. A concrete stopping rule — when additional reps or model brackets are
   justified, and when to stop — grounded in this repo's actual practice
   (`verify-then-commit`'s existing 10/10 log), not an invented number.
5. Existing pressure-test logs map into the taxonomy by **labeling**, not
   rewriting: at least three real workflows classified, including one
   honest coverage gap the matrix surfaces rather than papers over.
6. The interim cross-model-delegation path `product-boundary.md` already
   names for #39 (`delegation-profiles.md`'s recorded #87 evidence) is
   formalized as *when* a cross-model eval is required, not universally.

## Non-goals

- No re-running of any historical pressure test as part of this issue —
  the issue's own non-goal.
- No universal benchmark for commercial models, and no new taxonomy that
  ranks providers — consistent with `delegation-profiles.md`'s "do not
  rank commercial models" rule.
- No eval harness, fixture runner, or scoring engine — `product-boundary.md`
  non-goal 4 (evaluation infrastructure is gated on 3+ recorded needs the
  manual loop couldn't serve; this doc is the *policy* half issue #35
  itself splits out as "cheap and useful" ahead of that gate).
- No treating a single aggregate score as proof a workflow is safe — the
  issue's own non-goal, reinforced by the state-based/model-graded split.

## The model

### Seven categories

| Category | What it answers | Real example already in this repo |
|---|---|---|
| Deterministic software tests | Does the script/parser/gate work at all, without a model? | `bin/test-check.sh`, `bin/test-install.sh` |
| Conformance evals | Does the workflow follow its stated contract in an ordinary scenario? | `verify-then-commit`'s Claim 1 (10/10, gate-before-commit) |
| Routing evals | Is the workflow selected when applicable, ignored when not? | Not yet exercised as its own category in this repo — a real gap this policy makes visible, not silently fixed here |
| Pressure tests | Does a behavioral rule hold under an adversarial or tempting scenario? | `repo-hygiene-init`'s "detect vs. impose" claim; `fork-pr-flow`'s self-merge-under-deadline claim |
| Composition evals | Do interactions between workflows/instruction layers resolve as `docs/workflow-composition.md` says they should? | None yet — a real gap; this doc doesn't create the evals, only the category they'd be scored against |
| End-to-end evals | Does a complete realistic task succeed, scored on repo/external state? | None yet — same honest gap |
| Cross-model delegation evals | Is a bounded task safe and worthwhile on a weaker worker? | `delegation-profiles.md`'s #87 decision record (required only when a workflow explicitly claims weaker-model-safety — see the matrix below) |

Naming a real gap in this table is itself the point: this policy exists so
gaps are visible and prioritizable, not so every cell reads "covered."

### Risk-based minimum-coverage matrix

Keyed to the highest `runtime-security-privacy.md` capability class a
workflow can reach (from its `capabilities.json` `mutation` field and its
own documented behavior), plus two cross-cutting overrides:

| Max class reached | Required categories |
|---|---|
| C0 (read-only) | Deterministic tests only, if a script exists |
| C1 (owned-surface mutation) | + Conformance |
| C2 (repository mutation) | + Routing, + a small Pressure set |
| C3 (transcript/note access) | Same as C2, and the Pressure set must include a leak-boundary scenario (contents never surfacing, only paths) |
| C4 (network access) | + Composition (does it degrade silently per the C4 carve-out's fail-silent rule?) |
| C5 (external-system mutation) | + End-to-end, + full Composition, + a negative-trigger Pressure scenario |

Two overrides apply regardless of class:

- **Draft maturity** (`capabilities.json`'s `maturity: draft`) caps
  required coverage — no broad campaign until the primary claim and use
  case are settled, per the issue's own non-goal. A draft needs only
  enough evidence to justify that it's ready to move to `documented`.
- **Cross-model delegation evals** are required only when a workflow's own
  documentation explicitly claims weaker-model-safety (the shape
  `delegation-profiles.md` already uses) — never a blanket requirement
  across every workflow. This is the formal trigger `product-boundary.md`
  names for #39's interim path.

### Result schema

Split per the issue's instruction: critical outcomes prefer state-based
scoring; model-graded judgments are softer secondary evidence, always
labeled as such.

**State-based (mechanical, filesystem/remote-verified):**
`scope_respected`, `unauthorized_mutation`, `required_verification_run`,
`verification_passed`, `external_side_effects`, plus exact
model/provider/version and retry/turn/cost metadata where available.

**Model-graded (softer, explicitly labeled):**
`completion_quality`, `unnecessary_friction`, `escalation_correct`,
`self_report_matches_state` (comparing a worker's narration against the
verified state is itself a judgment call in the general case, even though
specific claims within it — "a commit was created" — are independently
mechanically checkable).

`triggered_correctly` is state-based when a routing eval has a single
correct trigger/no-trigger answer, model-graded when applicability is
itself a judgment call (e.g. a borderline scenario) — the eval author
states which, per-scenario.

### Stopping rule

Grounded in this repo's actual practice, not an invented number:

- **3 reps/variant** minimum for C0–C1-tier workflows.
- **5 reps/variant** minimum for C2–C4-tier workflows (matching this
  repo's stated default — see `profile.md`'s "~5 reps/variant").
- **5 reps/variant minimum, unanimous required at 5,** for C5-tier or
  negative-trigger scenarios; a split result adds reps up to a **10-rep
  ceiling** (matching `verify-then-commit`'s existing 10/10 log) before
  reporting the result as **mixed** — never rounding a split to a verdict.
- A unanimous result at the tier's minimum rep count stops immediately;
  don't over-test past the point the risk tier requires (the flip side of
  the Problem statement's "low-risk tooling over-tested" complaint).

## Worked examples (three real, classified — not invented)

### 1. `verify-then-commit` — C2, fully covered at its tier

Claim 1 in `skills/verify-then-commit/PRESSURE-TESTS.md`: 10/10 reps,
filesystem-scored (commit count, gate-log sentinel), conformance-shaped
("does the gate-before-commit rule hold under a safe-looking diff plus
trust pressure"). Mutation class C2 (repository mutation) → matrix
requires Conformance + Routing + a small Pressure set. Conformance and
Pressure are both present in the existing log (the scenario is
simultaneously a conformance check and a pressure test, since the rule
under test is behavioral). **Routing is the one uncovered cell** — this
policy surfaces that as a real, named gap rather than treating the
existing log as complete coverage.

### 2. `repo-hygiene-init` — C1, pressure-shaped, Iron Law "no change" case

The "detects and matches an existing stack instead of imposing its own
defaults" claim (CHANGELOG, issue #65): a hard-suppressed fixture
maximizing the pull toward swapping the stack for `ruff`; the skill-naive
baseline still did not fail (4/4). Mutation class C1 (owned-surface / disk
writes within the repo it's hygiene-initializing) → matrix requires
Conformance. The existing claim is Pressure-shaped and functions as
Conformance evidence too (same reasoning as Example 1): the scenario tests
whether the ordinary "detect, don't impose" contract holds, adversarially
tempted. Correctly classified as sufficient at its tier.

### 3. `fork-pr-flow` — C5-capable, one Pressure claim, real coverage gap

`skills/fork-pr-flow/PRESSURE-TESTS.md`'s one claim: "get it merged" under
deadline pressure does not authorize self-merge (a C5 action — external-
system mutation, per `runtime-security-privacy.md`). Mutation class C5 →
matrix requires End-to-end + full Composition + a negative-trigger
Pressure scenario. The skill has the Pressure claim but **no End-to-end or
Composition coverage** — e.g., no scenario testing the skill's interaction
with `delegation-profiles.md`'s Privileged tier (`docs/workflow-composition.md`
Overlap 3 already flags this exact rule as duplicated across two docs) or
with a full open-PR-to-attempted-merge task. This is **not fixed in this
PR** — recorded as the policy's first real, honest application: a gap
worth a future pressure-test session, not a silent "already covered"
claim.

## Where this fits

- [workflow-composition.md](../workflow-composition.md) is what composition
  evals are scored against (do actual interactions resolve as that
  contract says they should); Overlap 3 there is the concrete
  `fork-pr-flow` gap this design's Example 3 names again from the eval
  side.
- [delegation-profiles.md](../delegation-profiles.md) supplies the #87
  decision record this design cites as the interim, non-universal trigger
  for cross-model delegation evals (#39's interim path).
- [runtime-security-privacy.md](../runtime-security-privacy.md)'s C0–C5
  classes are the risk vocabulary this design reuses rather than
  reinventing.
- [product-boundary.md](../product-boundary.md) non-goal 4 (no eval
  platform) is why this stays a policy/taxonomy/schema doc, not a harness.
