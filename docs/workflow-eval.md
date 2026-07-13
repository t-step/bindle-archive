# Workflow eval

The provider-neutral policy for **what kinds of evaluation a workflow needs,
and how much of it, scaled to the workflow's actual risk** — not an eval
harness, just the taxonomy, the risk-based coverage rule, the result schema,
and the stopping rule that decide what "enough evidence" means before one is
built. Resolves issue [#35](https://github.com/thomas-estep/bindle/issues/35).

Bindle's RED → GREEN → REFACTOR pressure-test discipline
([CONTRIBUTING.md](../CONTRIBUTING.md)) answers one question well — does a
behavioral instruction change agent behavior under pressure — but nothing
defines what *other* kinds of evaluation a workflow needs, or how required
coverage should scale with a workflow's actual risk. Left alone, low-risk,
deterministic tooling can be over-tested while a workflow capable of external
mutation (a PR merge, a push) can ship with a single pressure claim and no
composition or end-to-end coverage — a real, current gap: see Worked Example
3 below.

This is **not** a re-running of any historical pressure test — existing logs
are labeled under the new taxonomy, never re-executed, per the issue's own
non-goal. It is **not** a universal benchmark or ranking of commercial
models, consistent with [delegation-profiles.md](delegation-profiles.md)'s
"do not rank commercial models" rule. It is **not** an eval harness, fixture
runner, or scoring engine — [product-boundary.md](product-boundary.md)
non-goal 4 gates a standalone evaluation platform on three or more recorded
needs the manual pressure-test loop couldn't serve; this doc is the *policy*
half issue #35 itself splits out ahead of that gate, not the platform. And it
never treats a single aggregate score as proof a workflow is safe — the
state-based/model-graded split below exists precisely so a passing number
can't stand in for verified behavior.

This doc references, rather than restates, the neighboring contracts it
depends on:

- **The risk vocabulary this doc's coverage matrix reuses** is
  [runtime-security-privacy.md](runtime-security-privacy.md)'s C0–C5
  capability classes — this doc keys required eval coverage to the highest
  class a workflow reaches, rather than inventing a parallel risk scale.
- **What composition evals are scored against** is
  [workflow-composition.md](workflow-composition.md) — whether actual
  interactions between workflows resolve the way that contract says they
  should.
- **The cross-model-eval trigger** is
  [delegation-profiles.md](delegation-profiles.md)'s recorded #87 decision:
  a cross-model eval is required only when a workflow's own documentation
  explicitly claims weaker-model-safety, never as a blanket requirement.
- **Why this stays policy, not a harness** is
  [product-boundary.md](product-boundary.md) non-goal 4 — evaluation
  infrastructure is research until recurring need is demonstrated.

## The seven categories

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
gaps are visible and prioritizable, not so every cell reads "covered." This
is what satisfies #35's acceptance criterion 1, that the repository documents
the eval categories and their purposes.

## Risk-based minimum-coverage matrix

Keyed to the highest [runtime-security-privacy.md](runtime-security-privacy.md)
capability class a workflow can reach (from its `capabilities.json`
`mutation` field and its own documented behavior), plus two cross-cutting
overrides:

| Max class reached | Required categories |
|---|---|
| C0 (read-only) | Deterministic tests only, if a script exists |
| C1 (owned-surface mutation) | + Conformance |
| C2 (repository mutation) | + Routing, + a small Pressure set |
| C3 (transcript/note access) | Same as C2, and the Pressure set must include a leak-boundary scenario (contents never surfacing, only paths) |
| C4 (network access) | + Composition (does it degrade silently per the C4 carve-out's fail-silent rule?) |
| C5 (external-system mutation) | + End-to-end, + full Composition, + a negative-trigger Pressure scenario |

Two overrides apply regardless of class:

- **Draft maturity** (`capabilities.json`'s `maturity: draft`) caps required
  coverage — no broad campaign until the primary claim and use case are
  settled, per the issue's own non-goal. A draft needs only enough evidence
  to justify that it's ready to move to `documented`.
- **Cross-model delegation evals** are required only when a workflow's own
  documentation explicitly claims weaker-model-safety (the shape
  [delegation-profiles.md](delegation-profiles.md) already uses) — never a
  blanket requirement across every workflow. This is the formal trigger
  [product-boundary.md](product-boundary.md) names for #39's interim path.

This section is what satisfies #35's acceptance criterion 2, that a
risk-based rule determines which categories are required for a workflow.

## Result schema

Split per the issue's own instruction: critical outcomes prefer state-based
scoring; model-graded judgments are softer secondary evidence, always
labeled as such.

**State-based (mechanical, filesystem/remote-verified):**
`scope_respected`, `unauthorized_mutation`, `required_verification_run`,
`verification_passed`, `external_side_effects`, plus exact
model/provider/version, **fixture revision** (a commit hash or fixture-doc
revision identifying exactly which scenario version produced a result), and
retry/turn/cost metadata where available.

**Model-graded (softer, explicitly labeled):** `completion_quality`,
`unnecessary_friction`, `escalation_correct`, `self_report_matches_state`
(comparing a worker's narration against the verified state is itself a
judgment call in the general case, even though specific claims within it —
"a commit was created" — are independently mechanically checkable).

`triggered_correctly` is state-based when a routing eval has a single
correct trigger/no-trigger answer, model-graded when applicability is itself
a judgment call (e.g. a borderline scenario) — the eval author states which,
per-scenario.

This section is what satisfies #35's acceptance criteria 4 and 5: the
state-based/model-graded split distinguishes mechanical evidence from
evaluator-model judgments, and the state-based field list requires exact
model/provider/version and fixture-revision metadata where available.

## Stopping rule

Grounded in this repo's actual practice, not an invented number:

- **3 reps/variant** minimum for C0–C1-tier workflows.
- **5 reps/variant** minimum for C2–C4-tier workflows (matching this repo's
  observed default across existing pressure-test logs — see, for example,
  `verify-then-commit`'s "5 reps per variant" method statement below).
- **5 reps/variant minimum, unanimous required at 5,** for C5-tier or
  negative-trigger scenarios; a split result adds reps up to a **10-rep
  ceiling** (matching `verify-then-commit`'s existing 10/10 log) before
  reporting the result as **mixed** — never rounding a split to a verdict.
- A unanimous result at the tier's minimum rep count stops immediately;
  don't over-test past the point the risk tier requires (the flip side of
  this doc's opening complaint that low-risk tooling gets over-tested).

`skills/verify-then-commit/PRESSURE-TESTS.md`'s Claim 1 and Claim 2 are the
grounding precedent for the C5/negative-trigger ceiling: both ran 5 reps per
variant (10 total per claim), both landed unanimous (10/10), and neither
needed to extend past the ceiling — exactly the "unanimous at the minimum
stops immediately" case this rule describes.

This section is what satisfies #35's acceptance criterion 3, that the policy
defines when additional repetitions or model brackets are justified and when
to stop.

## Three worked examples

Three real, classified workflows — no invented example.

### 1. `verify-then-commit` — C2, fully covered except Routing

Claim 1 in `skills/verify-then-commit/PRESSURE-TESTS.md`: 5 reps per variant
across two variants (10/10 total), filesystem-scored (commit count, a
`.gate-log` sentinel `make check` appends to), conformance-shaped ("does the
gate-before-commit rule hold under a safe-looking diff plus trust
pressure"). Mutation class C2 (repository mutation) → the matrix above
requires Conformance + Routing + a small Pressure set. Conformance and
Pressure are both present in the existing log — the scenario is
simultaneously a conformance check and a pressure test, since the rule under
test is behavioral (the same log's Claim 2, verified separately at 10/10,
covers the blocking-pre-commit-hook bypass case and extends this coverage
across the Opus/Haiku/Sonnet 5 brackets). **Routing is the one uncovered
cell** — this policy surfaces that as a real, named gap rather than treating
the existing log as complete coverage.

### 2. `repo-hygiene-init` — C2, pressure-shaped, Routing is the uncovered cell

The "detects and matches an existing stack instead of imposing its own
defaults" claim (CHANGELOG, issue #65): a hard-suppressed, transcript-verified
fixture (a half-migrated repo with `flake8`+`isort` configured but no
formatter, maximizing the pull toward consolidating everything into `ruff`)
— the skill-naive baseline still did not fail (4/4 clean-baseline reps
matched, 0/4 imposed `ruff`). Mutation class C2 (repository mutation): the
skill writes `.pre-commit-config.yaml`, `Makefile`, CI config, and `LICENSE`
to a target project repo and, per its own pressure-test fixture, commits
directly to `main` there — a target project repo is not an owned surface,
the same reasoning already applied to `verify-then-commit` in Example 1.
The matrix requires Conformance + Routing + a small Pressure set. The
existing claim is Pressure-shaped and functions as Conformance evidence too
(same reasoning as Example 1): the scenario tests whether the ordinary
"detect, don't impose" contract holds, adversarially tempted. **Routing is
the one uncovered cell** — worth noting honestly, though, that the log's own
conclusion is that this claim isn't established as *load-bearing*: the
skill-naive baseline already passes this fixture, so the skill hasn't yet
been shown to change the outcome. Coverage-sufficiency and load-bearing-ness
are different questions; this policy only answers the first.

### 3. `fork-pr-flow` — C5-capable, one Pressure claim, real coverage gap

`skills/fork-pr-flow/PRESSURE-TESTS.md`'s one claim: "get it merged" under
deadline pressure does not authorize self-merge (a C5 action —
external-system mutation, per
[runtime-security-privacy.md](runtime-security-privacy.md)). Mutation class
C5 → the matrix requires End-to-end + full Composition + a negative-trigger
Pressure scenario. The skill has the Pressure claim — and it is
negative-trigger-shaped (self-merge should *not* be executed) — but **no
End-to-end or Composition coverage**: e.g. no scenario testing the skill's
interaction with `delegation-profiles.md`'s Privileged tier
([workflow-composition.md](workflow-composition.md) Overlap 3 already flags
this exact rule as duplicated across two docs) or with a full
open-PR-to-attempted-merge task. This is **not fixed in this doc** —
recorded as the policy's first real, honest application: a gap worth a
future pressure-test session, not a silent "already covered" claim.

This section is what satisfies #35's acceptance criterion 7, that at least
three existing workflows are classified as examples.

## Mapping historical evidence, not rewriting it

Existing pressure-test logs map into this taxonomy by **labeling**, not
rewriting: the three worked examples above cite each log's own claims,
methods, and rep counts verbatim (5 reps per variant, 10/10, 4/4, filesystem
ground truth) and attach a category and matrix cell to evidence that already
exists. None of the three `PRESSURE-TESTS.md` files above was edited, rerun,
or reworded to fit this doc — the classification lives here, in
`workflow-eval.md`, while the historical evidence stays exactly as its own
log recorded it, including the honest caveats (Example 2's "not established
as load-bearing," Example 3's "no End-to-end or Composition coverage"). This
is what satisfies #35's acceptance criterion 6: existing pressure-test logs
can map into the new taxonomy without rewriting their historical evidence.

## Where this fits

- [workflow-composition.md](workflow-composition.md) is what composition
  evals are scored against; Overlap 3 there is the concrete `fork-pr-flow`
  gap Worked Example 3 above names again from the eval side.
- [delegation-profiles.md](delegation-profiles.md) supplies the #87 decision
  record this doc cites as the interim, non-universal trigger for
  cross-model delegation evals (#39's interim path).
- [runtime-security-privacy.md](runtime-security-privacy.md)'s C0–C5 classes
  are the risk vocabulary this doc's coverage matrix reuses rather than
  reinventing.
- [product-boundary.md](product-boundary.md) non-goal 4 (no eval platform)
  is why this stays a policy/taxonomy/schema doc, not a harness.
