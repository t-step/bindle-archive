# Implementation packet — workflow-eval policy contract (#35)

Implements [`docs/design/2026-07-13-workflow-eval-policy.md`](../design/2026-07-13-workflow-eval-policy.md)
(issue #35). Read that design in full first; it is authoritative for every
product question this packet doesn't restate. Follows the same packet shape
used for #31 and #32 — sized to a single-doc unit of work.

### Read first

- `docs/design/2026-07-13-workflow-eval-policy.md` — the approved design;
  authoritative for the seven categories, the risk matrix, the result
  schema, the stopping rule, and the three worked examples.
- `docs/runtime-security-privacy.md` — the C0–C5 mutation classes this
  doc's risk matrix reuses (must exist and be cited, not restated).
- `docs/workflow-composition.md` — what composition evals are scored
  against; Overlap 3 there is the same `fork-pr-flow` gap Worked Example 3
  names.
- `docs/delegation-profiles.md` — the #87 decision record this doc cites
  as the cross-model-eval trigger.
- `skills/verify-then-commit/PRESSURE-TESTS.md`,
  `skills/repo-hygiene-init/PRESSURE-TESTS.md`,
  `skills/fork-pr-flow/PRESSURE-TESTS.md` — the three real logs Worked
  Examples 1–3 classify; read each so the new doc's example text is
  accurate to what's actually recorded there, not a paraphrase from the
  design alone.
- `docs/delegated-implementation-packets.md` — supplies the packet
  template this file follows.
- Issue #35 body (already read this session) — the seven acceptance
  criteria and non-goals.

### Preflight

- On branch `docs/35-workflow-eval-policy`, cut fresh from `main` (which
  already has #31 and #32 merged — confirmed before this branch was cut).
- Working tree clean except the design doc already committed at `f79f165`.
- Issue #35 is open, unblocked (`product-boundary.md`'s backlog triage and
  the design doc both confirm #31/#32 — its named dependencies — are
  merged).

### Bounded objective

`docs/workflow-eval.md` exists, is registered in `capabilities.json` as a
`contract` row, and satisfies all seven of #35's acceptance criteria
verbatim:

1. The repository documents the eval categories and their purposes.
2. A risk-based rule determines which categories are required for a
   workflow.
3. The policy defines when additional repetitions or model brackets are
   justified and when to stop.
4. The result schema distinguishes mechanical evidence from
   evaluator-model judgments.
5. The policy requires exact model/provider/version **and fixture
   revision** metadata where available. (The design's state-based field
   list names model/provider/version and retry/cost metadata but doesn't
   spell out "fixture revision" verbatim — add it explicitly to the
   state-based field list; it's a literal acceptance-criteria phrase the
   design's own framing already accommodates, e.g. a commit hash or
   fixture-doc revision identifying exactly which scenario version
   produced a result.)
6. Existing pressure-test logs can map into the new taxonomy without
   rewriting their historical evidence.
7. At least three existing workflows are classified as examples.

`make check` passes.

### Expected artifacts

- `docs/workflow-eval.md` (new) — the policy contract itself.
- `capabilities.json` — one new `contract` row (`workflow-eval`); add
  `related_docs` back-references on `runtime-security-privacy`,
  `workflow-composition`, and `delegation-profiles` rows pointing at the
  new doc (mirror how #31 and #32 added their back-references).
- `CHANGELOG.md` — one `Unreleased` line.

### Do not change

- `skills/verify-then-commit/PRESSURE-TESTS.md`,
  `skills/repo-hygiene-init/PRESSURE-TESTS.md`,
  `skills/fork-pr-flow/PRESSURE-TESTS.md` — read-only inputs; the whole
  point of acceptance criterion 6 is that historical evidence is labeled,
  not rewritten. Do not add taxonomy labels into these files themselves.
- `docs/workflow-composition.md`, `docs/delegation-profiles.md`,
  `docs/runtime-security-privacy.md` — cited and cross-linked, never
  edited by this packet (beyond the `capabilities.json` `related_docs`
  additions, which live in that JSON file, not in the docs' prose).
- Any installer, `bin/`, or Makefile behavior — doc-only change, per the
  design's non-goals.
- `global/CLAUDE.md`, `CONTRIBUTING.md` — the RED→GREEN→REFACTOR loop
  they define is referenced, not altered.

### Content requirements for `docs/workflow-eval.md`

Write it in this order, translating the approved design directly (restate,
don't just link-and-omit — same discipline #31 and #32 used):

1. **Header** — title, "Resolves issue #35", the problem paragraph
   (over-testing low-risk tooling vs. under-testing external-mutation-
   capable workflows), and a non-goals paragraph covering: no re-running
   historical pressure tests, no commercial-model ranking, no eval
   harness/platform (`product-boundary.md` non-goal 4), no treating a
   single aggregate score as proof of safety.
2. **Neighboring-contracts bullets** — same pattern as
   `delegation-profiles.md`'s and `workflow-composition.md`'s opening
   lists: `runtime-security-privacy.md` supplies the risk vocabulary this
   doc reuses; `workflow-composition.md` is what composition evals are
   scored against; `delegation-profiles.md` supplies the cross-model-eval
   trigger; `product-boundary.md` non-goal 4 is why this stays policy, not
   a harness.
3. **The seven categories** — the design's table (category, what it
   answers, real example) verbatim, including the two rows that honestly
   say "no example yet" (Routing, Composition, End-to-end) rather than
   inventing one.
4. **Risk-based minimum-coverage matrix** — the design's C0–C5 table
   exactly, plus the two override rules (draft maturity caps required
   coverage; cross-model evals required only on an explicit
   weaker-model-safety claim). This section is what satisfies acceptance
   criterion 2.
5. **Result schema** — the state-based/model-graded split from the
   design, **plus the fixture-revision addition from Bounded Objective
   item 5 above** (state-based fields: `scope_respected`,
   `unauthorized_mutation`, `required_verification_run`,
   `verification_passed`, `external_side_effects`, model/provider/version,
   fixture revision, retry/turn/cost metadata; model-graded fields:
   `completion_quality`, `unnecessary_friction`, `escalation_correct`,
   `self_report_matches_state`; note on `triggered_correctly` being
   either, per-scenario). This section is what satisfies acceptance
   criteria 4 and 5.
6. **Stopping rule** — the design's 3/5/10-rep rule by tier, citing
   `verify-then-commit`'s existing 10/10 log as the grounding precedent
   and this repo's stated "~5 reps/variant" default. This section is what
   satisfies acceptance criterion 3.
7. **Three worked examples** — the design's three classified workflows,
   restated accurately against what's actually in each `PRESSURE-TESTS.md`
   (read each file per "Read first" above rather than trusting the
   design's paraphrase alone): `verify-then-commit` (C2, fully covered
   except Routing), `repo-hygiene-init` (C1, sufficient at its tier),
   `fork-pr-flow` (C5-capable, has one Pressure claim, **lacks End-to-end
   and Composition coverage — stated as an open gap, not fixed here**).
   This section is what satisfies acceptance criterion 7.
8. **Mapping historical evidence, not rewriting it** — one explicit
   paragraph stating the labeling-not-rewriting principle, citing the
   three worked examples as the demonstration. This section is what
   satisfies acceptance criterion 6.
9. **Where this fits** — closing cross-links, mirroring
   `workflow-composition.md`'s and `delegation-profiles.md`'s closing
   sections: `workflow-composition.md`, `delegation-profiles.md`,
   `runtime-security-privacy.md`, `product-boundary.md`.

### Verification

- `make check` → all checks pass, including the capability-inventory
  bijection/ledger check (the new doc must be a `contract` row) and the
  link checker (every relative link must resolve).
- Manual: confirm each of #35's seven acceptance criteria maps to a named
  section (the doc should say so explicitly, the way `delegation-profiles.md`
  and `workflow-composition.md` self-cite their acceptance criteria) —
  and confirm Worked Example 3's `fork-pr-flow` gap claim is accurate
  against the actual `skills/fork-pr-flow/PRESSURE-TESTS.md` content (one
  claim, no composition/end-to-end scenario), not just copied from the
  design without checking.
- No broader test run — no executable behavior changes.

### External mutation authority

- Edit files: yes   Commit: yes   Push: yes
- Open/update PR: yes   Comment/label issue: no   Close issue: no (PR
  "Resolves #35" closes it on merge; merge is the owner's — Privileged
  per `delegation-profiles.md`).
- Mode: authorized implementation.
- Defaults hold: no self-merge.

### Stop conditions

- If the `fork-pr-flow` gap claim (or either of the other two examples)
  turns out inaccurate once the actual `PRESSURE-TESTS.md` files are read
  — stop and report the discrepancy rather than silently adjusting the
  claim to fit the design.
- If `make check`'s capability-inventory check demands a different
  `version_introduced` than what `VERSION` currently requires — use what
  the checker requires, don't guess.

### Noticed, not done

- The three named coverage gaps (Routing has no example anywhere;
  Composition and End-to-end have none; `fork-pr-flow` lacks
  composition/end-to-end coverage at its C5 tier) are real follow-up
  candidates for future pressure-test sessions — not actioned in this
  packet.

### Closeout evidence

Report: final diff (files listed in "Expected artifacts" only), `make
check` result, the PR number/URL and its open/closed state.
