# Release Captain L3 (Claude skill) Implementation Plan — PR-B

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Claude-native `release-captain` skill that automates contract steps 1–5 (via the L2 evidence helper) and drives the L4 strategy seam through a two-approval-gate handoff, closing #116.

**Architecture:** A SKILL.md-only skill (no new helper script — it orchestrates the existing `bin/release-evidence.py` (L2) and `bin/release-strategy.sh` (L4)). It emits a recommendation, then gates: show the resolved strategy → first explicit approval → strategy `dry-run` → effect preview → second explicit approval → mint an ephemeral token → strategy `apply`. The orchestrator owns both gates and the token; the strategy stays dumb. Publication is never in the flow.

**Tech Stack:** Markdown (SKILL.md), the L1 contract (`docs/workflows/release-captain.md`), the L2 helper, the L4 seam, `capabilities.json`, `docs/skill-portability-audit.md`, pressure-test fixtures.

## Global Constraints

- **Three qualified authorities**, verbatim: intent → Release Captain; artifact → Release Please; publication → human maintainer. Never bare "authority".
- **The skill recommends and orchestrates; it never merges, tags, publishes, deploys, or authorizes a release.** Each external mutation is a separate explicit grant (L1 §2).
- **Fail-safe:** an `uncertain` classification or evidence contradicting maintainer metadata → report the gap, decline a version/timing call; never fabricate (L1 §2, Step 5).
- **Two approval gates, both human, both showing the exact resolved strategy first.** The approval token is ephemeral invocation state, not a persisted marker.
- **Stop before `apply`** on: unknown/missing strategy, dirty precondition where cleanliness is required, stale evidence, or a failed `dry-run`.
- **Claude assets stay Claude-native** (Phase 1) — SKILL.md wording/frontmatter/triggers are Claude-native; Codex/human follow the same L1 contract + helpers directly.
- **A skill isn't done until pressure-tested** (RED→GREEN). It lands `draft` in `capabilities.json` + CHANGELOG until GREEN; harness index lag may push GREEN verification to a fresh session. #116 closes only when the skill is `tested`.
- Every commit passes `make check` + pre-commit. Never `--no-verify`. Branch `feature/release-captain-l3-116`. `version_introduced` = `0.5.0`.

## Footgun (repo #29): adding a skill touches THREE places or `make check` fails

The skill dir, a `capabilities.json` skill row, AND a `docs/skill-portability-audit.md` row. All three land together (Task 3).

---

### Task 1: Write `skills/release-captain/SKILL.md`

**Files:**
- Create: `skills/release-captain/SKILL.md`

**Interfaces:**
- Produces: a Claude-native skill named `release-captain` whose body maps L1 steps 1–5 onto the L2 helper and steps the L4 seam through two approval gates. No new executable — it invokes `python3 bin/release-evidence.py` and `bin/release-strategy.sh`.

- [ ] **Step 1: Write the frontmatter + body**

Frontmatter (`name`, `description` only — match the repo idiom):

```markdown
---
name: release-captain
description: Use when deciding whether accumulated, verified work should be released and cutting that decision into a Release Please release PR — gathers evidence since the latest tag, recommends a version class + timing with rationale and confidence, then (only on explicit approval) drives the configured release strategy's dry-run and apply to create/update the release PR. Recommends and orchestrates only; never merges, tags, publishes, deploys, or authorizes a release. Publication stays an explicitly human-authorized step.
---
```

Body sections (write them concretely; keep Claude-native):

1. **Overview** — the intent/artifact/publication split; the skill owns intent, Release Please owns artifacts, the human owns publication.
2. **When to Use / When NOT** — use when asked "should we release / cut a release / what version"; NOT to publish/tag/merge (no such authority).
3. **The two authorities (invariant)** — cite L1 §2: a recommendation is not an authorization; a created release PR is a proposal, not a merge.
4. **Flow** (the operational core):
   - **Steps 1–5 (recommend):** orient (VERSION, latest tag, `RELEASE-MANIFEST.json`, CHANGELOG policy); gather evidence via `python3 bin/release-evidence.py` (L2); classify; recommend version + timing separately; emit the human- + machine-readable recommendation with rationale/confidence/included-excluded/authority statement. Fail-safe on `uncertain`.
   - **Show strategy:** run `bin/release-strategy.sh which`; display the exact resolved strategy + script path.
   - **First approval gate:** request explicit human approval to run a dry-run. No approval → stop.
   - **Dry-run + preview:** `bin/release-strategy.sh dry-run`; present the proposed release-PR effect.
   - **Second approval gate:** show the strategy again; request explicit human approval to apply. No approval → stop.
   - **Apply:** mint an ephemeral token (fresh per invocation, never persisted) and run `bin/release-strategy.sh apply --approval-token <token>`. The release PR is a proposal; its merge is a separate human decision.
5. **Stop conditions** — unknown/missing strategy (seam exits 64), dirty precondition, stale evidence, failed dry-run: stop before apply.
6. **Fit** — beside #59 release-integrity (run it before publication), below repo release policy, above `bin/release.sh` (legacy/fallback publication only).

- [ ] **Step 2: Validate frontmatter + links**

Run: `bin/check.sh --content-only` (or `make check`)
Expected: frontmatter valid; all `bin/*.sh`/doc refs `<bindle>/`-qualified where required; links resolve. Fix any Bindle-root path-ref gate hits (inline-code refs to `bin/...` in installed assets must be `<bindle>/`-qualified).

- [ ] **Step 3: Install + probe discoverability (harness-lag aware)**

Run: `make install` then dispatch a throwaway subagent to check the skill resolves (per profile: the index lags an unlink/install; a GREEN rep is invalid until a probe confirms the skill is discoverable — "Unknown skill" means wait for reindex / fresh session).

- [ ] **Step 4: Commit**

```bash
git add skills/release-captain/SKILL.md
git commit -m "feat(#116): release-captain Claude skill (L3) — steps 1-5 + two-gate handoff"
```

(Commit will trip inventory until Task 3 adds the skill row + audit row — do Task 3 before committing if the hook blocks, or commit Tasks 1+3 together.)

---

### Task 2: RED baseline — confirm the skill's behavior is absent without it

**Files:** none (throwaway fixtures under a scratch dir).

- [ ] **Step 1: Establish the RED baseline**

Per the profile's methodology: dispatch fresh `general-purpose` (sonnet) subagents in throwaway fixture repos (realistic mini repos with a VERSION + CHANGELOG + a few conventional commits since a tag; **not** named after the skill), given a realistic "should we release this?" prompt with a hard "do NOT invoke the Skill tool" prohibition. Grep each transcript (`tasks/<id>.output`) for a real `"name":"Skill"` tool-use to confirm absence. Record what the un-skilled baseline does (ad hoc, no two-gate discipline, may conflate recommendation with authorization). RED baselines dispatched pre-reindex run against a confirmed-absent skill for free.

- [ ] **Step 2: Record the RED findings** in `skills/release-captain/PRESSURE-TESTS.md` (draft; GREEN section filled in Task 4).

---

### Task 3: Register the skill (three places) + CHANGELOG

**Files:**
- Modify: `capabilities.json` (skill row, `maturity: "draft"`)
- Modify: `docs/skill-portability-audit.md` (audit row)
- Modify: `CHANGELOG.md` (Unreleased/Added, marked draft)

- [ ] **Step 1: Add the `capabilities.json` skill row**

Mirror the `package-release-integrity` skill row schema: `name: "release-captain"`, `type: "skill"`, `path: "skills/release-captain"`, `description` (copy the SKILL.md description), `provider: {"claude": "installed", "codex": "manual"}`, `maturity: "draft"` (until GREEN), `mutation: ["network", "external"]` (it drives the seam's apply), `version_introduced: "0.5.0"`.

- [ ] **Step 2: Add the `docs/skill-portability-audit.md` row**

Follow the table's column contract (read a recent row, e.g. `package-release-integrity`, for the exact columns). Status: Claude-native SKILL.md wrapper (Phase 1) over the provider-neutral L1 contract + helpers; Codex/human follow the same contract directly; maturity `draft` until pressure-tested. Do not claim `tested` or Codex-verified until evidenced.

- [ ] **Step 3: CHANGELOG Unreleased/Added (draft-marked)**

Add under `## [Unreleased]` → `### Added`: the `release-captain` skill (L3 of #116), explicitly noting **draft — pending RED→GREEN pressure tests**.

- [ ] **Step 4: Full gate**

Run: `make check`
Expected: `capability inventory OK`; skill-row bijection satisfied (skill dir ↔ capabilities row ↔ audit row); all green.

- [ ] **Step 5: Commit**

```bash
git add capabilities.json docs/skill-portability-audit.md CHANGELOG.md
git commit -m "chore(#116): register release-captain skill (draft) — capability + audit + CHANGELOG"
```

---

### Task 4: GREEN pressure tests (harness-lag permitting) → promote to `tested`

**Files:**
- Modify: `skills/release-captain/PRESSURE-TESTS.md`, `capabilities.json`, `docs/skill-portability-audit.md`, `CHANGELOG.md` (drop the draft marker) — only when GREEN passes.

- [ ] **Step 1: GREEN reps** — fresh subagents (own fixture copy each), realistic release prompts with NO skill hint; ~5 reps. Score the filesystem + transcript, not self-report: the skill triggers, produces steps 1–5, stops at the first gate without applying, and never merges/tags/publishes. Two-run persistence chain (run 2 told nothing of run 1). If the harness index still lags (subagents see "Unknown skill"), STOP and hand off GREEN to a fresh session — do not fake a GREEN.

- [ ] **Step 2: On GREEN,** record results in `PRESSURE-TESTS.md`, flip `maturity` to `tested` in `capabilities.json`, update the audit row's maturity cell, drop the CHANGELOG draft marker, commit.

- [ ] **Step 3: If GREEN cannot complete this session,** leave everything `draft`, record the harness-lag blocker in `PRESSURE-TESTS.md`, and note #116 stays open pending GREEN.

---

### Task 5: Full gate + open PR-B (PAUSE for human merge)

- [ ] **Step 1:** `make check && make test` — all green.
- [ ] **Step 2:** Push `feature/release-captain-l3-116`, open a PR to `main` referencing #116. Body: what L3 adds, the two-gate flow, the authority split, and the honest maturity state (`tested` → "closes #116" / `draft` → "#116 stays open pending GREEN pressure tests"). **Do not merge — the human confirms.**

## Self-Review

- **Spec coverage:** §6 skill flow (steps 1–5 + two gates + token) → Task 1; §6.1 stop conditions → Task 1 (Step 5 body); §6.2 Codex portability classification → Task 3 audit row; §8 pressure tests → Tasks 2+4; §9 inventory three-places → Task 3. Changelog migration (§4) is release-time, not a PR-B task.
- **Placeholder scan:** the SKILL.md body is described section-by-section with concrete invocations (`python3 bin/release-evidence.py`, `bin/release-strategy.sh which|dry-run|apply --approval-token`); the audit row references an existing row for the exact column contract rather than inventing columns.
- **Honesty gate:** maturity is `draft` until GREEN is evidenced; the plan explicitly forbids claiming `tested` or closing #116 without passing pressure tests.
