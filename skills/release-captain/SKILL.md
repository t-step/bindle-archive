---
name: release-captain
description: Use for ANY request to release, cut a release, "do a release", decide whether/what/when to release, or "take care of the release" for accumulated work — this is THE release-decision skill and it owns that decision. Gathers evidence since the latest tag, recommends a version class and timing with rationale and confidence, then (only on explicit per-step human approval) drives the configured release strategy to create or update a Release Please release PR. It NEVER cuts the release itself — never bumps VERSION, edits CHANGELOG, commits, tags, publishes, or deploys; those are human-authorized publication. It invokes package-release-integrity as its safety check, and is not replaced by it. Use even when the request sounds like "just handle it".
---

# Release captain

## STOP — read before doing anything

This skill **recommends and orchestrates a release decision. It never cuts the
release.** Whatever the request says — "take care of it", "get it done", "handle
the release", "just cut it" — that is **not** authority to release. Specifically,
while running this skill you must **NOT**, on your own:

- bump `VERSION`
- edit or write `CHANGELOG.md`
- `git commit` a release
- `git tag` (a tag is a publication action)
- push, publish, deploy, create a GitHub Release, or merge a release PR

Each of those is **publication authority** and needs its own **explicit,
per-action human approval** — never implied by the request, by your
recommendation, or by a green check. The two artifact-creating steps
(`dry-run`, then `apply`) run **only** after the two explicit approval gates
below, and even `apply` only ever *proposes* a release PR — a human still merges
it, tags, and publishes separately.

**The failure this skill exists to prevent:** treating "the maintainer asked me
to take care of the release" as permission to bump + commit + tag it yourself.
If you catch yourself about to edit VERSION/CHANGELOG or run `git tag`, **stop**
— you have left this skill's contract. Produce the recommendation and wait.

## Relationship to `package-release-integrity`

`release-captain` decides **whether / what / when** to release and orchestrates
the cut. `package-release-integrity` **verifies that an already-decided cut is
internally safe** (version-source agreement, tag/version consistency, changelog,
semver movement). It is a **check this skill invokes** before publication — it
is **not** a substitute for this skill and does not decide or authorize a
release. If a release request tempts you toward `package-release-integrity`
alone, you have skipped the decision layer: run `release-captain`.

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
   truth (`VERSION`); verify the base branch and remote state; read the
   repository release policy (Bindle's
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

**Hard stop after step 5.** Output the recommendation and **stop**. Do not bump
`VERSION`, edit `CHANGELOG.md`, commit, or tag — no matter how the request was
phrased. The recommendation is the deliverable of steps 1–5; cutting the release
is not yours to do. Proceed past this point only when the human explicitly
approves the next step. Before any publication (i.e. before a human merges the
resulting release PR and tags), run `package-release-integrity` to verify the
cut is safe.

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

Show the resolved strategy again (`which`) and, via `AskUserQuestion` (or an
explicit chat reply if `AskUserQuestion` isn't available), ask the human to
both approve the apply *and* supply an **approval token** in the same
answer — any short freeform string is fine. The token is not a secret; its
only job is proving the value came from the operator, not from you. Use their
answer text verbatim as `<operator-approval-token>` below. Never invent this
string yourself, and never reuse one operator answer as the token for a
later, separate approval request. No approval / no token → stop.

### Apply

```bash
<bindle>/bin/release-strategy.sh apply --approval-token <operator-approval-token>
```

`apply` creates or updates the release PR, then (for the `local-release-please`
strategy) chains `<bindle>/bin/release-please-sync.sh apply` onto that same PR
branch with the same token — issue #152 — so `VERSION` never disagrees with the
manifest on the release PR without a separately-remembered step. It never
merges, tags, publishes, or deploys. The resulting release PR is a
**proposal**; its merge is a separate human decision.

### Publishing (separate, human-authorized, outside this skill)

Once a human has merged the release PR and created/pushed the `vX.Y.Z` tag,
publishing the GitHub Release is its own explicitly human-authorized action —
this skill has no part in it. While GitHub Actions stays billing-blocked (see
`docs/workflows/release-captain.md` §5), `release.yml` never fires on the
pushed tag, so publish manually with `<bindle>/bin/release-publish.sh`, which
replicates `release.yml`'s `gh release create` step exactly and additionally
closes the relabel gap #152 identified: a manual publish leaves the merged
release PR labeled `autorelease: pending` forever (the real release-please
GitHub Action would relabel it to `autorelease: tagged`; ours never runs), and
the next `release-please release-pr` then aborts on "untagged, merged release
PRs outstanding." Same dry-run/apply + approval-token shape as the other
release scripts — same operator-supplied token, sourced the same way (never
minted by you):

```bash
bin/release-publish.sh dry-run vX.Y.Z
bin/release-publish.sh apply vX.Y.Z --approval-token <operator-approval-token>
```

## Stop conditions (before `apply`)

Halt before `apply` on any of:

- unknown or missing strategy (`which` / the seam exits 64);
- a dirty precondition where cleanliness is required;
- stale evidence (the evidence helper degraded to `uncertain` or could not
  gather);
- a failed `dry-run`;
- no operator-supplied approval token at the second approval gate (never
  substitute a self-generated string).

## Fit with the rest of Bindle

- **Beside `#59` release-integrity.** Run `package-release-integrity` before any
  publication — it verifies a release is *safe to cut*; this skill decides
  *whether and what* to cut.
- **Below repository release policy.** Defer to repo-local or inherited (DomI)
  release policy where present.
- **Above `<bindle>/bin/release.sh`.** That script remains legacy/fallback
  *publication* tooling only and does not regenerate Release-Please-owned
  artifacts (`VERSION`, `CHANGELOG.md`).
