---
name: release-captain
description: Use when deciding whether accumulated, verified work should be released and cutting that decision into a Release Please release PR — gathers evidence since the latest tag, recommends a version class and timing with rationale and confidence, then (only on explicit approval) drives the configured release strategy's dry-run and apply to create or update the release PR. Recommends and orchestrates only; never merges, tags, publishes, deploys, or authorizes a release. Publication stays an explicitly human-authorized step.
---

# Release captain

## Overview

Turns accumulated, verified work into an **evidence-backed release
recommendation**, and — only after explicit human approval — drives the
configured release strategy to create or update the release PR. This skill
automates steps 1–5 of the provider-neutral contract in
`docs/workflows/release-captain.md` (the L1 layer) and orchestrates the L4
strategy seam; Codex and humans follow that same contract directly.

Three authorities are distinct and never imply one another:

- **intent authority — Release Captain (this skill).** Decides whether a
  release is justified, the version class, timing, rationale, and confidence,
  and requests human authorization. Produces a *recommendation*, never a
  release.
- **artifact authority — Release Please.** Owns the `VERSION` bump, the
  `CHANGELOG.md` content, and the release-PR contents (via the strategy's
  `apply`).
- **publication authority — the human maintainer.** Merging the release PR, and
  any subsequent tag, GitHub Release, package publication, or deployment, each
  require their own explicit human authorization.

**This skill recommends and orchestrates. It never merges, tags, publishes,
deploys, or authorizes a release.**

## When to Use

- When asked "should we release this?", "what version is this?", or to decide
  whether accumulated work justifies cutting a release.
- When, after a recommendation is approved, a release PR should be created or
  updated through the configured strategy.

When NOT to use:

- To merge a release PR, tag, publish, deploy, or create a GitHub Release —
  this skill has no such authority. Those are separate, explicitly
  human-authorized publication actions.
- To bypass the evidence/recommendation step and "just cut a release."

## The two authorities (invariant)

Per `docs/workflows/release-captain.md` §2: **a release recommendation is not a
release authorization.** However high the confidence or green the CI, a
recommendation does not imply permission to merge, tag, publish, deploy, or
release. A created release PR is a *proposal awaiting a human merge*, not a
decision already made. A tool or network failure produces `uncertain`, never a
fabricated recommendation.

## Flow

### Steps 1–5 — produce the recommendation

1. **Orient.** Identify the latest valid release tag and the version source of
   truth (`VERSION`, cross-checked against `RELEASE-MANIFEST.json`); verify the
   base branch and remote state; read the repository release policy (Bindle's
   `CHANGELOG.md` SemVer rule: breaking-install/structure → major, new
   capability → minor, fix → patch); detect whether Release Please is
   configured (`release-please-config.json`).
2. **Gather evidence.** Run the L2 helper:

   ```bash
   python3 <bindle>/bin/release-evidence.py
   ```

   It structures merged PRs + linked issues since the latest tag in the
   contract's evidence-precedence order and emits JSON + a human summary.
3. **Classify** each coherent change as `none` / `patch` / `minor` /
   `breaking` / `uncertain`. Explicit maintainer metadata outranks inference;
   where evidence contradicts metadata, flag it rather than override.
4. **Recommend version and timing, separately** — version
   (`none`/`patch`/`minor`/breaking-policy result) and timing
   (`no-release`/`batch`/`release-now`), mapped by the repo policy from step 1.
5. **Explain and request authorization.** Emit the human- and machine-readable
   recommendation: current version + latest release, suggested next version,
   timing, confidence, included/excluded PRs/issues, rationale per material
   classification, unresolved ambiguity, release-integrity/CI readiness, and an
   explicit authority statement. **Fail-safe:** if any change is `uncertain` or
   evidence contradicts metadata, report the gap and decline a version/timing
   call — never fabricate one.

Stop here unless the human explicitly approves proceeding.

### Show the resolved strategy

Before either approval gate, display the exact strategy that will run:

```bash
<bindle>/bin/release-strategy.sh which
```

Show the resolved `strategy=` and `script=` to the human. If it exits non-zero
(fail-closed: missing `release-captain.toml`, missing `strategy` key, or an
unknown strategy), **stop** — do not proceed to a dry-run.

### First approval gate

Request explicit human approval to run a dry-run. No approval → stop.

### Dry-run and effect preview

```bash
<bindle>/bin/release-strategy.sh dry-run
```

This is read-only (zero mutation). Present the proposed release-PR effect (the
version bump, changelog delta, and PR that would be created or updated).

### Second approval gate

Show the resolved strategy again (`which`) and request a second explicit human
approval to apply. No approval → stop.

### Apply

Mint an **ephemeral approval token** — fresh for this one invocation, never a
reusable secret and never persisted — and run:

```bash
<bindle>/bin/release-strategy.sh apply --approval-token <ephemeral-token>
```

`apply` may only create or update the release PR. It never merges, tags,
publishes, or deploys. The resulting release PR is a **proposal**; its merge is
a separate human decision.

## Stop conditions (before `apply`)

Halt before `apply` on any of:

- unknown or missing strategy (`which` / the seam exits 64);
- a dirty precondition where cleanliness is required;
- stale evidence (the evidence helper degraded to `uncertain` or could not
  gather);
- a failed `dry-run`.

## Fit with the rest of Bindle

- **Beside `#59` release-integrity.** Run `package-release-integrity` before any
  publication — it verifies a release is *safe to cut*; this skill decides
  *whether and what* to cut.
- **Below repository release policy.** Defer to repo-local or inherited (DomI)
  release policy where present.
- **Above `<bindle>/bin/release.sh`.** That script remains legacy/fallback
  *publication* tooling only and does not regenerate Release-Please-owned
  artifacts (`VERSION`, `CHANGELOG.md`).
