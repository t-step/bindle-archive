# Codex-Primitives Boundary Revisit — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adjudicate the product-boundary Revisit Trigger that #55 claims fired, recording verdict FIRED (broad) and reclassifying Codex from "narrow adapter" to a supported provider — as a surgical, doc-only amendment to the standing boundary docs.

**Architecture:** Two-file prose edit. `docs/product-boundary.md` is the authoritative home (a revisit is an edit to that doc in its own PR, per its own "Revisit triggers" rule) — it gets the fired-trigger marker, the reclassification, the refined non-goal, the updated backlog triage, and a new dated revisit section holding the full decision. `docs/provider-interop.md` gets one reaffirmation sentence tying its permanent non-equivalence rule to the widened stance. No script/installer/test-behavior change; the evidence (#56/#57) already shipped.

**Tech Stack:** Markdown only. Verification via `make check` (frontmatter/links/private-info/YAML + `bin/check-inventory.py`) and targeted `grep`.

## Global Constraints

- Doc-only. No `capabilities.json` / inventory change — `bin/check-inventory.py` must stay green with the **same counts (36 capabilities, 27 ledgered exclusions)**.
- Design docs and plans under `docs/design/` and `docs/plans/` are auto-excluded from the inventory scan — do not add `not_a_capability` ledger rows for them.
- `make check` must pass before every commit. Never `--no-verify`, never commit to `main` (work stays on `feature/codex-boundary-revisit`).
- The **non-equivalence rule is reaffirmed, never weakened**: a Claude asset is not a Codex asset; no merged/generated single-source file.
- `gh` label mutations and any push happen **only with explicit operator approval** — Task 3 is gated on that.
- Source of truth for the decision content: `docs/design/2026-07-14-codex-boundary-revisit-design.md`.

---

### Task 1: Amend `docs/product-boundary.md` — the decision

**Files:**
- Modify: `docs/product-boundary.md` (5 edit sites; anchors below)

**Interfaces:**
- Consumes: the design spec's Decision section (verdict FIRED broad; 5 guardrails; plugins deferred; flow-through).
- Produces: an authoritative, dated "Revisit 2026-07-14" record that Task 2 cross-links to, and a fired-trigger marker.

- [ ] **Step 1: Reclassify Codex in "Mature vs. experimental" (anchor: the sentence ending `Codex is a supported-but-narrow adapter, not a peer.`)**

Replace:

```markdown
- **Mature vs. experimental:** an asset is *mature* when it has passed (or
  baseline-passed) the CONTRIBUTING pressure-test loop with results
  recorded; otherwise it is a *draft* and must be labeled as such in the
  CHANGELOG. Provider-wise, Claude Code is the mature implementation;
  Codex is a supported-but-narrow adapter, not a peer.
```

with:

```markdown
- **Mature vs. experimental:** an asset is *mature* when it has passed (or
  baseline-passed) the CONTRIBUTING pressure-test loop with results
  recorded; otherwise it is a *draft* and must be labeled as such in the
  CHANGELOG. Provider-wise, Claude Code is the mature implementation; Codex
  is a supported provider (still maturing) that can host provider-native
  assets — no longer a mere adapter. See the 2026-07-14 revisit below, which
  fired the Codex-primitives trigger and moved this stance.
```

- [ ] **Step 2: Refine non-goal #3 (anchor: `3. **Universal asset conversion**`)**

Replace:

```markdown
3. **Universal asset conversion** — no automatic translation of Claude
   skills/commands/agents into other providers' formats, and no
   lowest-common-denominator asset schema.
```

with:

```markdown
3. **Universal asset conversion** — no *automatic* translation of Claude
   skills/commands/agents into other providers' formats, and no
   lowest-common-denominator asset schema. (Refined 2026-07-14: a
   Codex-native asset may be *hand-authored* as its own first-class asset,
   or installed via explicit per-asset eligibility; only automatic
   translation / adapter-generation stays barred — see the revisit below.)
```

- [ ] **Step 3: Mark the trigger FIRED (anchor: the Revisit-triggers bullet containing `Claimed 2026-07-12** (issue #55)`)**

Replace:

```markdown
- **A third provider** with a real native surface worth adapting, or
  Codex gaining primitives (skills/commands) that make today's "narrow
  adapter" stance wrong. **Claimed 2026-07-12** (issue #55): current Codex
  has native Agent Skills, subagents, lifecycle hooks, and plugin
  surfaces; #55 argues this is exactly this trigger. Recorded as a claim,
  not adjudicated as fired — see the Research entry for #55/#58/#59/#60
  above. A real revisit (its own decision document, the way #34 resolved
  v0.3–v0.4) is needed before this boundary's Provider boundary/non-goals
  sections change.
```

with:

```markdown
- **A third provider** with a real native surface worth adapting, or
  Codex gaining primitives (skills/commands) that make today's "narrow
  adapter" stance wrong. **Claimed 2026-07-12** (issue #55); **FIRED
  2026-07-14** — adjudicated in the "Revisit 2026-07-14" section below on
  #56/#57 evidence (Codex's native Agent Skills/subagents/hooks, and the
  shared skill-install path Bindle already shipped in #57). The revisit
  widened the provider stance while preserving the non-equivalence,
  no-automatic-conversion, no-runtime, and hook-safety guardrails; plugins
  stay deferred.
```

- [ ] **Step 4: Update the #55/#59/#60 backlog-triage entry (anchor: the Research bullet starting `- **#55** ("Reconcile Codex interoperability`)**

Replace the entire bullet (from `- **#55** ("Reconcile Codex interoperability and DomI-derived workflow` through `Verify: a revisit decision document citing concrete evidence, same shape as #34.`) with:

```markdown
- **#55** ("Reconcile Codex interoperability and DomI-derived workflow
  dependencies") — **RESOLVED 2026-07-14.** The boundary question #55 raised
  (whether the Codex-primitives Revisit Trigger fired) was adjudicated in the
  "Revisit 2026-07-14" section below: verdict FIRED. The stance moved; the
  standing guardrails held. Its children are no longer blocked on this
  question — **#58** shipped (DomI consumer profile), and **#59** (portable
  package-release-integrity workflow) and **#60** (portable issue work loop)
  are unblocked to proceed with Codex-native participation in scope. #55
  itself is a tracking epic; close or keep it open tracking #59/#60.
```

- [ ] **Step 5: Fix the "Next: none" reason that cites the now-resolved question (anchor: the paragraph `**Next:** none currently ready.`)**

Replace:

```markdown
**Next:** none currently ready. Every open issue below is either
self-gated on evidence that hasn't materialized, blocked on the boundary
question raised by #55, or too underspecified to triage yet — see Later,
Research, and Needs input.
```

with:

```markdown
**Next:** #59 and #60, newly unblocked by the 2026-07-14 revisit below (the
boundary question that gated them is resolved). The remaining open issues are
either self-gated on evidence that hasn't materialized or too underspecified
to triage yet — see Later, Research, and Needs input.
```

- [ ] **Step 6: Add the "Revisit 2026-07-14" decision section (insert immediately BEFORE the `## Revisit triggers` heading)**

Insert:

```markdown
## Revisit 2026-07-14 — the Codex-primitives trigger (#55)

A revisit of this boundary in the shape #34 used, triggered by issue #55 and
resolved here with cited evidence. This section is the authoritative decision
record; the inline edits above (Mature-vs-experimental, non-goal #3, the fired
trigger, the backlog entry) flow from it.

### Verdict: FIRED (broad)

The Codex-primitives Revisit Trigger is adjudicated **fired**. Evidence, both
already landed and closed:

- **#56** (Codex capability re-baseline) verified against current official
  Codex/OpenAI docs that Codex has native primitives for Agent Skills,
  subagents, hooks, and plugins — recorded per-surface in
  `provider-interop.md` § "Codex capability re-baseline".
- **#57** (install compatible shared skills for Codex) shipped a real shared
  cross-provider install surface: two eligible skills install into a Codex
  Agent-Skills home via `bin/install.sh`, gated by per-skill
  `capabilities.json` `provider.codex` eligibility and covered by
  `test-install.sh`; a real Codex session discovered and followed them.

The second point is decisive: Bindle already shipped past the old "narrow
adapter, never a peer" stance. Recording the trigger fired makes the boundary
honest, not more speculative.

### Stance change

Codex is reclassified from "supported-but-narrow adapter, not a peer" to a
**supported provider that can host provider-native assets** across skills,
subagents, and hooks. "Broad" means the *surface is open* — Bindle may ship
Codex-native assets as first-class, not merely document manual participation.
It does **not** claim parity, and this revisit authors no subagent/hook asset.

### Guardrails preserved (the "not a universal runtime" floor)

1. **Non-equivalence stays permanent.** A Claude asset is not a Codex asset;
   no merged/generated single-source file. Drift is managed by review.
2. **No *automatic* asset conversion.** A Codex-native subagent/hook is
   hand-authored as its own asset, or installed via explicit per-asset
   eligibility — never machine-translated from the Claude asset (non-goal #3,
   refined not deleted).
3. **No universal runtime, orchestrator, or execution loop** (non-goal #1).
4. **Hooks stay gated on the #30 safety contract, per action** (non-goal #6);
   any executable Codex automation must degrade to the manual workflow.
5. **Installer conflict-safety, explicit targets, and per-asset eligibility
   metadata** are preserved; no directory sweeps.

### Plugins — deferred

Codex's native plugin primitive has no Bindle equivalent on either provider
and no present consumer. Recorded still-out (adjudicated-deferred, not fired);
"broad" covers skills, subagents, and hooks, not plugins.

### Flow-through

- **#59** and **#60** are unblocked — Codex-native participation is now in
  scope for them, not manual-docs-only.
- **#58** already shipped; no action.
- **#55** (epic) may close now (P0/P1 shipped, boundary resolved) or stay open
  tracking #59/#60 — an operator call, not part of this doc change.

```

- [ ] **Step 7: Verify the edits — stale framing gone, new markers present**

Run:

```bash
# (run from repo root)
# stale verdict must be gone:
! grep -n "supported-but-narrow adapter, not a peer" docs/product-boundary.md && echo "OK: stale verdict removed"
# new markers must exist:
grep -n "FIRED 2026-07-14" docs/product-boundary.md
grep -n "^## Revisit 2026-07-14" docs/product-boundary.md
grep -n "RESOLVED 2026-07-14" docs/product-boundary.md
```

Expected: `OK: stale verdict removed`, and one match each for the three `grep`s.

- [ ] **Step 8: Run the full gate**

Run:

```bash
make check
```

Expected: `All checks passed.` — including `capability inventory OK (36 capabilities, 27 ledgered exclusions)` (unchanged) and `all repo-relative markdown links resolve` (the new `provider-interop.md` cross-link resolves).

- [ ] **Step 9: Commit**

```bash
# (run from repo root)
git add docs/product-boundary.md
git commit -m "docs(#55): fire the Codex-primitives boundary trigger (verdict: broad)

Adjudicate the product-boundary Revisit Trigger #55 claimed fired. Verdict
FIRED on #56/#57 evidence; reclassify Codex from narrow adapter to a supported
provider hosting native skills/subagents/hooks. Preserve non-equivalence,
no-auto-conversion, no-runtime, and #30 hook-gating; defer plugins. Update the
fired-trigger marker, non-goal #3, and the #55/#59/#60 backlog triage.
Doc-only; unblocks #59/#60."
```

---

### Task 2: Reaffirm the stance in `docs/provider-interop.md`

**Files:**
- Modify: `docs/provider-interop.md` (1 edit site — end of § "Non-equivalences (permanent)")

**Interfaces:**
- Consumes: the "Revisit 2026-07-14" section created in Task 1.
- Produces: a forward-pointer so a reader of the interop contract learns the stance was widened without weakening non-equivalence.

- [ ] **Step 1: Add the reaffirmation sentence (anchor: the end of the `## Non-equivalences (permanent)` section — after the paragraph ending `merging dissimilar surfaces into one generated file.`)**

Insert a new paragraph immediately after that paragraph:

```markdown
These rules were **reaffirmed** by the 2026-07-14 product-boundary revisit
(`product-boundary.md` § "Revisit 2026-07-14"), which
widened Codex from a "narrow adapter" to a supported provider that can host
provider-native assets. The widening opens the *surface* — it does not merge
these dissimilar surfaces, and automatic Claude→Codex asset conversion stays
barred.
```

- [ ] **Step 2: Verify the cross-link and reaffirmation**

Run:

```bash
# (run from repo root)
grep -n "reaffirmed" docs/provider-interop.md
grep -n "Revisit 2026-07-14" docs/provider-interop.md
```

Expected: one match each.

- [ ] **Step 3: Run the full gate**

Run:

```bash
make check
```

Expected: `All checks passed.` (link to `product-boundary.md` § anchor resolves; inventory counts unchanged).

- [ ] **Step 4: Commit**

```bash
# (run from repo root)
git add docs/provider-interop.md
git commit -m "docs(#55): reaffirm non-equivalence under the widened Codex stance

Cross-link the permanent non-equivalence rules to the 2026-07-14 boundary
revisit: the stance widening opens the Codex surface without merging
dissimilar surfaces or permitting automatic asset conversion. Doc-only."
```

---

### Task 3 (operator-gated): label reconciliation for #59/#60

**Not a doc change — a `gh` mutation. Do NOT run without explicit operator approval** (repo rule: `gh` mutations only with operator OK). Presented here for completeness; execute at session end or when approved.

- [ ] **Step 1: Confirm current labels**

```bash
for n in 59 60; do gh issue view $n --json number,labels -q '{n:.number,labels:[.labels[].name]}'; done
```

Expected: both show `status: blocked`.

- [ ] **Step 2: On approval, flip `status: blocked` → `status: ready`**

```bash
gh issue edit 59 --remove-label "status: blocked" --add-label "status: ready"
gh issue edit 60 --remove-label "status: blocked" --add-label "status: ready"
```

- [ ] **Step 3: (Optional, operator call) comment on #55/#59/#60 pointing at the merged revisit**, and decide whether #55 closes. Use the `comment-issue` template + footer if posting.

---

## Self-Review

**Spec coverage:**
- Verdict FIRED (broad) → Task 1 Steps 3, 6. ✓
- Stance reclassification → Task 1 Steps 1, 6. ✓
- Five guardrails preserved → Task 1 Step 6. ✓
- Non-goal #3 refinement → Task 1 Step 2. ✓
- Plugins deferred → Task 1 Step 6. ✓
- Flow-through (#59/#60 unblock, #55 close-or-keep) → Task 1 Steps 4, 5, 6; Task 3. ✓
- Edit set = product-boundary.md + provider-interop.md reaffirm (grep-confirmed no other doc) → Tasks 1, 2. ✓
- Non-equivalence reaffirmed not weakened → Task 2. ✓
- No capabilities/inventory change → Global Constraints + Step 8/Step 3 counts assertion. ✓
- Labels gated on operator approval → Task 3 header. ✓

**Placeholder scan:** No TBD/TODO; every edit shows exact old→new text; every verification shows exact command + expected output. ✓

**Type consistency:** N/A (prose). Cross-references consistent: Task 2 links to the `## Revisit 2026-07-14` heading created in Task 1 Step 6; the anchor text matches. ✓
