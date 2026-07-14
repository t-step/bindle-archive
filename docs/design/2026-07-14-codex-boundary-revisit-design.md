# Design: product-boundary revisit — the Codex-primitives trigger (#55)

**Status:** design spec, awaiting implementation
**Issue:** #55 (parent); unblocks #59, #60
**Author:** session 2026-07-14
**Shape:** a boundary revisit, the same shape #34 used to resolve v0.3–v0.4.

## Problem

`product-boundary.md` names a Revisit Trigger:

> A third provider with a real native surface worth adapting, or **Codex
> gaining primitives (skills/commands) that make today's "narrow adapter"
> stance wrong.**

Issue #55 claims that trigger has fired: current Codex has native Agent
Skills, subagents, lifecycle hooks, and plugin surfaces. The boundary doc
records the claim but explicitly does **not** adjudicate it — it says the
trigger stays unfired until "its own decision, the way #34 resolved
v0.3–v0.4," is written, and that #58/#59/#60 stay blocked behind that
decision. #58 shipped anyway (its deliverable was orthogonal); #59 and #60
remain blocked on this adjudication.

This spec defines the decision document that adjudicates the trigger and the
surgical amendments it makes to the standing boundary/interop docs.

## Decision (what the revisit concludes)

**The trigger is ADJUDICATED FIRED.** Two independent pieces of evidence,
both already landed and closed:

- **#56 (Codex capability re-baseline)** — verified against current official
  Codex/OpenAI docs that Codex has native primitives for Agent Skills,
  subagents, hooks, and plugins. Recorded per-surface in
  `provider-interop.md` § "Codex capability re-baseline (2026-07-11)".
- **#57 (install compatible shared skills for Codex)** — Bindle already
  installs two eligible skills (`verify-then-commit`, `fork-pr-flow`) into a
  Codex Agent-Skills home, and a real Codex session discovered and
  behaviorally followed them. The installer, `capabilities.json`
  `provider.codex` eligibility metadata, and `test-install.sh` coverage all
  exist today.

The second point is decisive: Bindle **already shipped a shared cross-provider
install surface** past the old "narrow adapter, never a peer" stance. The
boundary doc is factually behind the repo. Recording the trigger as fired
makes the doc honest rather than authorizing new speculative scope.

### Stance change

Codex is reclassified from **"supported-but-narrow adapter, not a peer"** to a
**supported provider that can host provider-native assets** across skills,
subagents, and hooks. The "narrow adapter, never a peer" language is struck
and replaced wherever it appears (`product-boundary.md`
§ "Mature vs. experimental"; the Provider-boundary framing).

"Broad" here means the *surface is open*: Bindle may ship Codex-native
skills/subagents/hooks as first-class assets, not merely document manual
participation. It does **not** mean parity is claimed, nor that any
subagent/hook asset is built by this revisit (see Non-goals preserved).

### Guardrails that survive (the "not a universal runtime" floor)

The stance widens; these standing rules do **not** move, and the doc must say
so explicitly so "broad" cannot be read as "universal runtime":

1. **Non-equivalence stays permanent** (`provider-interop.md`
   § "Non-equivalences"). A Claude asset is still not a Codex asset. No merged
   or generated single-source-of-truth file across providers. Drift is managed
   by review.
2. **No *automatic* asset conversion.** Non-goal #3 is *refined, not deleted*:
   a Codex-native subagent or hook is **hand-authored as its own asset**, or
   installed only via explicit per-asset eligibility metadata — never
   machine-translated from the Claude asset. This is the key reconciliation:
   the revisit opens the *surface*, not a translator/adapter-generator.
3. **No universal runtime, orchestrator, or execution loop** (non-goal #1
   unchanged). Workflows still run inside a provider's session.
4. **Hooks stay gated on the #30 safety contract, per action** (non-goal #6
   unchanged). The surface opens; any executable Codex automation still earns
   its way in through the security/privacy contract and must degrade to the
   manual workflow.
5. **Installer conflict-safety, explicit targets, and per-asset eligibility
   metadata** (`capabilities.json` `provider.codex`) are preserved. No
   directory sweeps; every Codex install target stays explicit and
   `test-install.sh`-covered.

### Plugins — deferred (not opened)

Codex has a native plugin primitive with **no Bindle equivalent on either
provider** and no present consumer. It is recorded as **still out of scope**,
adjudicated-deferred (not fired), for the same reason the boundary defers
speculative schemas: nothing to ship, no consumer. "Broad" covers skills,
subagents, and hooks — not plugins.

### Flow-through to blocked children

- **#59** (portable consumer-package release-integrity workflow) and **#60**
  (portable issue work loop) are **unblocked**: they may now assume
  Codex-native participation is in-scope, not manual-docs-only. Their
  `status: blocked` labels come off (→ `status: ready` / re-triage) — a
  label mutation, done only with operator approval.
- **#58** already shipped; no action.
- **#55** (epic) may close once this revisit lands (P0/P1 shipped, boundary
  resolved) or stay open tracking #59/#60. Decided at session end, not here.

## Scope of the change (files touched by implementation)

This spec's implementation is **doc-only**. No script, no installer, no test
behavior changes — the evidence it cites already shipped.

1. **New decision doc** — `docs/design/` already holds this spec; the *decision*
   itself lands as an amendment to `product-boundary.md` (a revisit is an edit
   to the boundary doc in its own PR, per its own "Revisit triggers" rule),
   not as a separate standalone file. The implementation plan will confirm
   whether a short standalone revisit note adds value or whether the
   `product-boundary.md` "Decision"/"Revisit triggers" edits are sufficient
   self-contained record. Default: fold it into `product-boundary.md` to keep
   one source of truth, mirroring how #34 lives in that doc.
2. **`product-boundary.md`** — the surgical amendment:
   - mark the Codex-primitives Revisit Trigger **FIRED (2026-07-14)** with the
     #56/#57 evidence and a pointer to the decision;
   - strike/replace "narrow adapter, never a peer" and the Codex row in
     "Mature vs. experimental";
   - refine non-goal #3 (auto-conversion still barred; hand-authored
     provider-native assets now permitted);
   - update the Backlog-triage entry for #55/#59/#60 (no longer "blocked on
     the boundary question — that question is now resolved").
3. **`provider-interop.md`** — update the standing stance prose that still
   frames Codex as narrow (§ "Mature vs. experimental" cross-reference,
   § "Standing boundaries" auto-conversion line stays but is cross-linked to
   the refined non-goal). The **Non-equivalences section does not change** —
   it is reaffirmed, not weakened.
4. **No `capabilities.json` / inventory change** — no new capability is added;
   this is a policy decision. (A future #59/#60 asset would add rows then.)

## Non-goals preserved (explicit)

- No subagent or hook asset is authored in this change.
- No auto-translation/adapter-generator for Claude→Codex assets.
- No universal runtime, orchestrator, plugin system, or marketplace.
- No installer/behavioral code change.

## Testing / verification

Doc-only change; the gate is `make check` (shellcheck/shfmt N/A, but
frontmatter/links/private-info/YAML and the inventory reconciliation all run).
Because no capability rows change, `bin/check-inventory.py` must stay green
with the same counts. Manual verification: every struck "narrow adapter"
phrase is actually replaced (grep), and the #55/#59/#60 triage entry no longer
says "blocked."

## Open question for the implementation plan

Whether to also strike the parallel "Codex is a supported-but-narrow adapter,
not a peer" sentence in any *other* doc (e.g. `README.md`, `sharing-skills.md`)
— the plan should grep the repo for the stale framing and decide the full
edit set, so the stance change is consistent, not just in the two named docs.
