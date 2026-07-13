# Implementation packet — workflow composition contract (#31)

Implements [`docs/design/2026-07-12-workflow-composition.md`](../design/2026-07-12-workflow-composition.md)
(issue #31). Read that design in full first; it is authoritative for every
product question this packet doesn't restate. Follows
[`docs/delegated-implementation-packets.md`](../delegated-implementation-packets.md)'s
ten-section shape, sized to a single-doc unit of work (the same shape #32
used, no phased packets needed here).

### Read first

- `docs/design/2026-07-12-workflow-composition.md` — the approved design;
  authoritative for the model, precedence order, and the three worked
  examples.
- `docs/delegation-profiles.md` — the doc this contract's inheritance
  section extends; must exist on this branch (it does — this branch is
  stacked on `docs/32-delegation-profiles`, commit `d71424e`).
- `docs/delegated-implementation-packets.md` — supplies the "state outranks
  narration" rule this doc's contradiction rule extends, and the one
  cross-link this packet fixes (its bare "#31's composition and precedence
  contract" mention).
- `docs/product-boundary.md` — non-goal 1 (no workflow engine); confirms
  scope stays a classification/precedence doc.
- Issue #31 body (already read this session) — acceptance criteria and
  non-goals.

### Preflight

- On branch `docs/31-workflow-composition`, stacked on `docs/32-delegation-profiles`
  (not `main` directly — `delegation-profiles.md` doesn't exist on `main`
  yet). PR base is `main`; the diff will include #32's commit until PR #98
  merges, then shrink automatically (standard stacked-PR behavior) —
  confirmed acceptable for this workflow.
- Working tree clean except the design doc already committed at `507f638`.
- Issue #31 is open, unblocked (no prerequisite issues named in its body).

### Bounded objective

`docs/workflow-composition.md` exists, is registered in `capabilities.json`
as a `contract` row, and satisfies all five of #31's acceptance criteria
verbatim:

1. Existing workflows can be classified under the composition model.
2. At least three realistic overlap scenarios are resolved explicitly.
3. A workflow cannot silently weaken an invariant.
4. Delegated agents receive the relevant inherited constraints.
5. Provider-specific differences remain outside the portable composition
   contract where appropriate.

`make check` passes.

### Expected artifacts

- `docs/workflow-composition.md` (new) — the contract itself.
- `docs/delegated-implementation-packets.md` — one cross-link fix (mirror
  the #32 pattern: its bare "issue #31's composition and precedence
  contract" mention becomes a link).
- `capabilities.json` — one new `contract` row (`workflow-composition`);
  add `related_docs` back-references on `delegated-implementation-packets`
  and `delegation-profiles` rows, mirroring how #32 added them.
- `CHANGELOG.md` — one `Unreleased` line.

### Do not change

- `skills/fork-pr-flow/SKILL.md` — Overlap 3 in the design explicitly
  defers editing it (dependency-declaration opportunity, not actioned
  here); do not add a cross-link from inside the skill file itself.
- `docs/delegation-profiles.md`, `docs/delegated-implementation-packets.md`'s
  section content (only the one named cross-link line changes) — no
  rewording beyond that link fix.
- Any installer, `bin/`, or Makefile behavior — doc-only change, per the
  design's non-goals.
- `global/CLAUDE.md` — classified and cited, never edited by this packet.

### Content requirements for `docs/workflow-composition.md`

Write it in this order, translating the approved design directly (restate,
don't just link-and-omit — same discipline the knowledge-promotion packets
used):

1. **Header** — title, "Resolves issue #31", one paragraph on the problem
   (multiple workflows can apply to one task; no rule for what happens when
   several do; risk of contradictory or duplicated guidance), and a
   non-goal paragraph covering both "not a workflow engine or runtime that
   decides precedence programmatically" (`product-boundary.md` non-goal 1)
   and "not automatic selection of the applicable workflow set without
   human/provider judgment" (the design's own non-goal 2), mirroring
   `delegation-profiles.md`'s opening shape.
2. **Neighboring-contracts bullets** — same pattern as
   `delegated-implementation-packets.md`'s opening list: what this doc
   owns vs. what it references (`delegation-profiles.md` for authority,
   `provider-interop.md` for what "provider adapter" means).
3. **The five categories** — a table (category, definition, real examples)
   exactly as drafted in the design's "Categories" section: Invariants,
   Project instructions, Modes, Task workflows, Provider adapters. Use the
   design's real examples verbatim (`global/CLAUDE.md` invariants;
   `hands-on-keyboard`; the six named task workflows; Claude skill vs.
   Codex manual-doc adapters).
4. **Precedence and the relaxation rule** — the fixed order (invariants →
   project instructions → modes → task workflows → provider adapters) and
   the "narrow or add, never relax/skip/contradict" rule, including the
   note that an invariant's own carve-out (e.g. "unless I explicitly ask")
   is part of the invariant, not an external override. This section is
   what satisfies acceptance criterion 3 ("a workflow cannot silently
   weaken an invariant") — state that criterion's satisfaction explicitly
   in the section, the way `delegation-profiles.md`'s governing rule 3
   states its own acceptance-criterion satisfaction.
5. **Contradiction rule** — stop-and-report for genuine same-tier or
   cross-tier contradictions, extending
   `delegated-implementation-packets.md` rule 1 (state outranks narration)
   to "contradiction outranks narration."
6. **Declaring dependencies** — the "reference, don't restate" convention,
   citing the two real precedents from the design (packets "reference,
   rather than restate"; skills' `**REQUIRED BACKGROUND:**` citations).
7. **Inheritance into delegated tasks** — the four bullets from the design
   (invariants always inherit in full; project instructions inherit unless
   explicitly narrowed; modes don't auto-inherit into a bounded subagent
   dispatch; task workflows/provider adapters inherit only what's
   relevant), stated as extending `delegation-profiles.md` rule 2. This
   section is what satisfies acceptance criterion 4.
8. **Three worked examples** — the design's three overlaps, each restated
   with its resolution: (1) invariant × explicit instruction, (2) mode ×
   task workflow, (3) duplicated invariant across two docs (note Overlap
   3's resolution explicitly says "not edited in this PR" for
   `fork-pr-flow`, matching the Do-not-change section above). This section
   is what satisfies acceptance criterion 2.
9. **Classifying every current workflow** — a table listing every skill,
   command, and contract doc this repo ships (pull the list from
   `capabilities.json`'s `skill`/`command`/`contract` rows) against its
   category (most are Task workflows; `hands-on-keyboard` is a Mode;
   `global/CLAUDE.md` is Invariants; provider-interop.md documents the
   Provider adapters axis rather than being one itself — note that
   explicitly rather than force-fitting it). This section is what
   satisfies acceptance criterion 1.
10. **Provider-specific differences stay outside** — one short paragraph
    citing `provider-interop.md`'s "non-equivalences are permanent" stance
    and confirming this contract's five categories and precedence rule
    apply identically regardless of provider; only the "provider adapters"
    category itself is provider-specific, everything above it is not. This
    section is what satisfies acceptance criterion 5.
11. **Where this fits** — closing cross-links, mirroring
    `delegation-profiles.md`'s closing section: `delegation-profiles.md`,
    `delegated-implementation-packets.md`, `provider-interop.md`,
    `product-boundary.md`.

### Verification

- `make check` → all checks pass, including the capability-inventory
  bijection/ledger check (the new doc must be a `contract` row, matching
  #32's precedent) and the link checker (every relative link, including
  `../delegation-profiles.md`-style links, must resolve — verified by this
  branch being stacked on `docs/32-delegation-profiles`).
- Manual: grep the finished doc for each of #31's five acceptance-criteria
  phrases' concepts (classification, three overlaps, invariant-weakening,
  inheritance, provider-neutrality) and confirm each maps to a section
  above — same closeout discipline as the #32 session.
- No broader test run — no executable behavior changes.

### External mutation authority

- Edit files: yes   Commit: yes   Push: yes
- Open/update PR: yes   Comment/label issue: no   Close issue: no (PR
  "Resolves #31" closes it on merge; merge is the owner's — Privileged
  per `delegation-profiles.md`).
- Mode: authorized implementation.
- Defaults hold: no self-merge. PR should note it's stacked on #98 and
  will need a rebase (or will auto-resolve) once #98 merges.

### Stop conditions

- If any of the three worked examples can't be resolved cleanly under the
  five-category model as designed — stop and report; that's a design gap,
  not something to paper over in the doc.
- If `make check`'s capability-inventory check demands a different
  `version_introduced` than `0.3.0` (e.g. if `VERSION` has changed since
  this design was written) — use what the checker requires, don't guess.

### Noticed, not done

- `fork-pr-flow`'s duplicated merge-authority line (Overlap 3) — a real,
  small follow-up (add a "See also: delegation-profiles.md" line to the
  skill) but explicitly out of scope for this packet.
- No other workflow docs in this repo currently declare dependencies using
  the "reference, don't restate" convention by name — retrofitting existing
  docs to cite it explicitly is a future cleanup, not this packet's job.

### Closeout evidence

Report: final diff (files listed in "Expected artifacts" only), `make
check` result, the PR number/URL and its open/closed state, and confirm the
stacked-branch note is in the PR body.
