---
name: release-captain
description: Use for ANY request to release, cut a release, "do a release", decide whether/what/when to release, or "take care of the release" for accumulated work — this is THE release-decision skill and it owns that decision. Gathers evidence since the latest tag, recommends a version class and timing with rationale and confidence, then (only on explicit per-step human approval) drives the configured release strategy to create or update a Release Please release PR. It NEVER cuts the release itself — never bumps VERSION, edits CHANGELOG, commits, tags, publishes, or deploys; those are human-authorized publication. It invokes package-release-integrity as its safety check, and is not replaced by it. Where a well-formed .domi-pin marks release-semver-governance as inherited, upstream (DomI) policy is the default for the version and timing call and this skill routes rather than settles it locally. Use even when the request sounds like "just handle it".
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
   configured (`release-please-config.json`); and **detect inherited release
   policy** — see below. Both halves of this step are required; the contract
   (`docs/workflows/release-captain.md` §step 1) states them together.

   **Detect inherited release policy.** Run
   `<bindle>/bin/domi-status.sh --repo <repo> --category release-semver-governance`
   (or the `domi-consumer` skill, which owns pin detection) and read its one
   line of output directly — `inherited=true|false|malformed` is the answer,
   not an input to evaluate:

   - `inherited=false` (exit 1, no `.domi-pin`) → decide locally as normal.
   - `inherited=true` (exit 0) → **upstream policy is the default** for
     version class and timing.
   - `inherited=malformed` (exit 5) → decide locally; say which field was bad.

   When upstream is the default, keep doing the local work this skill owns —
   gather evidence, classify, check changelog and version-source hygiene — but
   **route the version/timing call upstream rather than settling it here**, and
   carry that through to step 5. Where inherited policy does not cover a
   question, decide it here as normal.

   A pin whose sha is a placeholder, or that reports `behind`/`forked`, is still
   a pin: drift or an implausible-looking sha is a reason to flag it, never a
   reason to treat the repo as ungoverned and proceed.
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

   **When step 1 found inherited policy**, the authority statement is not a
   caveat appended to a settled answer — it *is* the answer's status. Say that
   upstream owns the version/timing call, name where to take it, and present the
   local reasoning as input to that decision rather than as the decision. A
   recommendation that reads "release now, confidence high" with the inherited
   authority noted as a footnote has not routed anything; that is the #225
   failure verbatim.

**Hard stop after step 5.** Output the recommendation and **stop**. Do not bump
`VERSION`, edit `CHANGELOG.md`, commit, or tag — no matter how the request was
phrased. The recommendation is the deliverable of steps 1–5; cutting the release
is not yours to do. Proceed past this point only when the human explicitly
approves the next step. Before any publication (i.e. before a human merges the
resulting release PR and tags), run `package-release-integrity` to verify the
cut is safe. Where that skill defers under a `.domi-pin`, the defer obliges
running the authority: invoke `<bindle>/bin/domi-release-check.sh --repo <repo>`
and relay DomI's verdict — an exit-`4` `checker-unreachable` is a degraded
outcome to report explicitly, never a pass (see "Routing obliges invoking"
below).

### Show the resolved strategy

Before either approval gate, display the exact strategy that will run. Run it
**from inside the repo being released** — the seam resolves
`release-captain.toml` from the current repo, not from Bindle's checkout, so
the working directory selects which repo is answered for:

```bash
cd <target repo> && <bindle>/bin/release-strategy.sh which
```

Show the resolved `strategy=`, `config=`, and `script=` to the human, and check
that `config=` names the repo being released. If it exits non-zero (fail-closed:
missing `release-captain.toml`, missing `strategy` key, unknown strategy, or not
inside a git repository), **stop** — do not proceed to a dry-run.

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

Before dispatching to the strategy script, `apply` itself (issue #278) refuses
a dirty target tree (exit 65) and refuses to run at all when step 1 found
`release-semver-governance` inherited and the call has not been routed (exit
66) — pass `--inherited-policy-routed` once a human confirms the routing
happened; the flag is stripped before the strategy script ever sees it. Both
are hard stops enforced by the script, not preconditions trusted to whoever
read this skill.

`apply` creates or updates the release PR, then (for the `local-release-please`
strategy) chains `<bindle>/bin/release-please-sync.sh apply` onto that same PR
branch with the same token — issue #152 — so `VERSION` never disagrees with the
manifest on the release PR without a separately-remembered step. It then runs
`<bindle>/bin/release-please-sync.sh check` (read-only, no token) and fails the
whole `apply` if the two still disagree — issue #265, because the sync can run
before the PR is labeled `autorelease: pending`, report "nothing to sync", and
exit 0, which is how v0.7.0 shipped with a stale `VERSION`. A mismatch is now a
failed release step, not a rule someone has to remember to check. It never
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

Four of the five are enforced by `release-strategy.sh apply` itself (#278) — a
skill-reading agent no longer has to remember them, though the reasoning below
still explains what's happening and why:

- unknown or missing strategy — the seam exits 64 (`which` shows the same);
- a dirty target tree — `apply` exits 65;
- **inherited release policy covers the decision and has not been routed** —
  `apply` exits 66. Step 1 found a well-formed `.domi-pin` naming
  `release-semver-governance`, and the version/timing call has not gone
  upstream. `apply` drives release-PR artifacts off that call; producing them
  while upstream owns it overrides the policy this skill is required to defer
  to. This is the #225 failure mode — an agent skipped this precondition 2 of
  2 times when it was prose only — now a hard stop rather than a rule to
  remember. Halting here is not the same as declining to help — the evidence,
  classification, and hygiene checks are still yours to deliver.
- no operator-supplied approval token at the second approval gate — the
  strategy script exits 3/4 (never substitute a self-generated string).

One remains a judgement call the script cannot make for you: **stale evidence**
(the evidence helper degraded to `uncertain` or could not gather). Nothing
downstream of step 2 knows whether the evidence it was handed is trustworthy —
halt before proposing `dry-run`/`apply` if it is. A failed `dry-run` is caught
naturally: `dry-run` and `apply` are separate invocations, so a `dry-run`
that exited non-zero produced nothing to approve at the second gate.

## Fit with the rest of Bindle

- **Beside `#59` release-integrity.** Run `package-release-integrity` before any
  publication — it verifies a release is *safe to cut*; this skill decides
  *whether and what* to cut. Note that skill defers on the same signal, so under
  a governing pin it returns `mode: defer` rather than a verdict; that is the
  authority working, not a check that failed to run.
- **Routing obliges invoking (#242, settled).** When step 1 finds inherited
  policy, routing the call upstream also obliges **running DomI's own
  release-integrity checker when it is discoverable** — as one command:
  `<bindle>/bin/domi-release-check.sh --repo <repo>` — and relaying its
  output and `domi-exit=<n>` verbatim as the authority's answer. Exit `4`
  (`checker-unreachable`) is the only legitimate verbal defer: report it
  explicitly as a degraded outcome, never a pass. This closes the E-series
  soft spot where both this skill and `package-release-integrity` named the
  authority, left its check unrun, and stayed compliant; the helper is
  script-enforced for the same reason `--category` is (#278) — advisory
  prose alone has not bound here. The advisory boundary stands: Bindle
  relays DomI's verdict and is never the release authority.
- **Below repository release policy.** Defer to repo-local or inherited (DomI)
  release policy where present — detected in Flow step 1, carried through step
  5, and enforced by the stop condition above. This bullet states the
  *relationship*; those three are where it is *performed*. #225 is the worked
  case for why the distinction matters: when this was the only place the
  obligation appeared, agents read the pin and recommended a release anyway,
  2/2.
- **Above `<bindle>/bin/release.sh`.** That script remains legacy/fallback
  *publication* tooling only and does not regenerate Release-Please-owned
  artifacts (`VERSION`, `CHANGELOG.md`).
