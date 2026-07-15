# Release Captain L3 + L4 — design

Completes issue `#116` by building the two remaining layers of the
release-captain capability on top of the shipped L1 contract
(`docs/workflows/release-captain.md`) and L2 evidence helper
(`bin/release-evidence.py`):

- **L4** — a provider-neutral **release-strategy seam** with a single checked-in
  **local Release Please strategy**, selected by an explicit repo-local config
  value.
- **L3** — a Claude-native **`release-captain` skill** that orchestrates the
  contract's steps 1–5, then drives the selected strategy through a
  two-approval-gate handoff.

L1 and L2 are already merged into `main` (in the `[Unreleased]` CHANGELOG at the
time of writing). This design does not restate them; it slots into L1's Step 6
("Optional Release Please handoff") and §6 provider table exactly.

## 1. The three authorities (naming contract)

Every document and script produced here uses these three **qualified** terms and
never the bare word "authority":

- **intent authority — Release Captain.** Decides whether a release is
  justified, the recommended version class, timing, rationale, confidence, and
  the request for human authorization. Produces a *recommendation*, never a
  release.
- **artifact authority — Release Please.** Owns generation *and subsequent
  updates* of the release-PR artifacts: the `VERSION` bump, the `CHANGELOG.md`
  content, and the release PR itself.
- **publication authority — the human maintainer.** Merging the release PR, and
  every subsequent tag, GitHub Release, package publication, and deployment,
  each require their own explicit human authorization.

These map onto L1 §2's two-mutation invariant: intent authority produces only
repository-local *reads* plus a recommendation; artifact authority performs a
bounded external mutation (create/update one PR) that is still only a
*proposal*; publication authority is the separate grant that turns a proposal
into a released artifact.

## 2. Scope boundaries

**In scope (this design → PR-A + PR-B):**

- `release-captain.toml` at the repository root, narrow schema, strategy
  selection only.
- A provider-neutral strategy seam: checked-in strategy scripts implementing a
  two-verb contract (`dry-run`, `apply`).
- One strategy implementation: `local-release-please`.
- Release Please configuration (`release-please-config.json`,
  `.release-please-manifest.json`) enabling it as artifact authority.
- The `release-captain` Claude skill (steps 1–5 + the handoff orchestration).
- Fixture tests, pressure tests, capability-inventory and portability-audit
  registration.

**Out of scope (explicitly deferred, not required for `#116` / v0.5.0):**

- Any strategy registry, discovery, or auto-detection mechanism. One strategy,
  named explicitly. Revisit only when a second real strategy exists.
- A publication strategy. Tag / GitHub Release / publish / deploy stay human.
- A documented, repeatable mechanism for injecting curated release-note prose
  into RP-owned artifacts without hand editing. May be considered later as its
  own unit; it is **not** a requirement here.
- Migrating or retiring `bin/release.sh` beyond documenting it as legacy /
  fallback publication tooling.

## 3. L4 — the release-strategy seam

### 3.1 Config: `release-captain.toml`

A new file at the repository root. Intentionally narrow initial schema:

```toml
strategy = "local-release-please"
```

- The orchestrator reads exactly this one value to choose a strategy.
- **Fail closed.** A missing file, a missing `strategy` key, or a `strategy`
  value that does not name a checked-in strategy script is a hard stop. There is
  **no implicit fallback, no registry, no discovery** in this release.
- The file may gain additional stable policy inputs later; this design commits
  only to the single `strategy` key.

### 3.2 Strategy contract (two verbs)

Strategies are checked-in scripts under `bin/release-strategies/`. Each strategy
implements exactly two verbs and nothing else:

- **`dry-run`** — compute and print the proposed release-PR effect (the version
  bump, the changelog delta, the PR that would be created or updated). It must
  prove **zero mutation** of the repository, branch, remote, Release Please
  manifest, and working tree. No file is written, no branch is created, no
  network state is changed. This is safe to run at any time.
- **`apply`** — create or update the release PR. It may **only** create or
  update that PR. It must **never** merge, tag, create a GitHub Release,
  publish, or deploy. `apply` refuses to run unless the orchestrator passes a
  valid, ephemeral approval token (§3.4).

Both verbs are **non-interactive**: a strategy script never prompts, never
blocks on input, and reads its approval signal only from the orchestrator-passed
token. All human interaction lives in the orchestrator (L3), never in the
strategy.

`local-release-please` is an **artifact strategy, not a publication strategy** —
this classification is stated in the script header and in the L1 sharpening
(§5). Its `apply` runs `npx release-please release-pr …` and stops. It never
touches the `github-release` subcommand or any tag/publish path.

### 3.3 `local-release-please` behavior

- `dry-run` → `npx release-please release-pr --dry-run …` (plus the flags that
  point Release Please at this repo and its config), capturing and printing the
  proposed version + changelog + PR without creating anything.
- `apply` → the same `release-please release-pr` invocation *without*
  `--dry-run`, creating or updating the release PR. Guarded by the approval
  token.
- Requires `npx` / Node at invocation time. Absence of `npx` is a clean,
  explanatory hard stop, not a silent skip.

### 3.4 The approval token

- The token is **ephemeral invocation state** passed by the orchestrator into
  the strategy's `apply` call for that one invocation.
- It is **not** a reusable repository secret and **not** a persisted approval
  marker (no file, no env var left behind, no committed flag). Nothing about a
  prior approval survives to authorize a later `apply`.
- `apply` with a missing or invalid token is a hard stop before any mutation.

### 3.5 Release Please configuration

- `release-please-config.json` + `.release-please-manifest.json` at the repo
  root. `release-type: simple` (manages a `VERSION` file and `CHANGELOG.md`
  without any language/packaging assumptions).
- The manifest is **seeded at the current released version, `0.4.0`**, so the
  first managed `release-pr` computes the next version from Conventional Commits
  since `v0.4.0`.

## 4. Changelog migration (first v0.5.0 release)

Enabling Release Please as **artifact authority** retires the hand-curated
`[Unreleased]` workflow. For the first managed release:

- Release Please generates `VERSION`, `CHANGELOG.md`, and the release PR from the
  Conventional Commits since `v0.4.0`. Bindle's commits are already
  Conventional, so this is well-defined.
- The Release Please section style (`### Features` / `### Bug Fixes` …) and its
  terser generated notes are **accepted as the migration cost**. The CHANGELOG
  representation shifts to Release Please's format from this release forward.

The spec states explicitly, and the implementation must preserve, that:

- **Release Please owns generation and subsequent updates of the release-PR
  artifacts.** `VERSION` and `CHANGELOG.md` are RP-owned once RP is enabled.
- **Human review may reject and rerun the process, but ordinary manual edits to
  RP-owned `VERSION` or `CHANGELOG.md` are not part of the release path.** The
  human reviews and approves (or rejects and reruns) the artifact; the human does
  **not** become a second artifact generator. There is no competing, manually
  maintained changelog representation.
- **Publication notes may add narrative context** — in the GitHub Release
  description at publication time, or in durable project documentation — **but
  must not become another source of truth for the versioned changelog.**

Any important curated context that would previously have gone into the
hand-written `[Unreleased]` prose is preserved outside the RP-owned artifact
path (publication-time GitHub Release description, or durable docs), never as a
parallel changelog.

## 5. L1 sharpening

`docs/workflows/release-captain.md` currently lumps "tagging, and GitHub Release
creation" under Release Please's mechanical layer (Step 6 / §5). This design
sharpens that wording to match the three-authority split:

- **Release Please owns the mechanical release-PR artifact layer** — the
  version/changelog updates and the release PR.
- **Tag, GitHub Release, package publication, and deployment belong to
  explicitly human-authorized publication** — a separate grant, never implied by
  a created release PR.

This is a wording sharpening, not a contract change: L1 §2 already forbids the
workflow from tagging/publishing on its own authority. The edit lands with PR-B
(where the skill makes the boundary operational), or PR-A if convenient.

## 6. L3 — the `release-captain` Claude skill

`skills/release-captain/SKILL.md` automates the contract and orchestrates the
handoff. Flow:

1. **Steps 1–5 (recommendation).** Orient, gather evidence (invoking the L2
   `bin/release-evidence.py` helper), classify, recommend version + timing
   separately, and emit the human- + machine-readable recommendation with
   rationale, confidence, included/excluded work, and the explicit authority
   statement. Fail-safe on `uncertain` / contradictory evidence per L1 §2 and
   Step 5.
2. **First approval gate.** The orchestrator shows the **exact selected
   strategy** (read from `release-captain.toml`) and requests explicit human
   approval to proceed to a dry-run.
3. **Strategy `dry-run` + effect preview.** Run the selected strategy's
   `dry-run`; present the proposed release-PR effect.
4. **Second approval gate.** Request a second explicit human approval to apply.
   The orchestrator again shows the exact selected strategy before this gate.
5. **Strategy `apply`.** Mint the ephemeral approval token and call the selected
   strategy's `apply`, which creates/updates the release PR and stops.

The orchestrator **owns both approval gates and the token**; the strategy stays
non-interactive and unaware of human interaction. Publication (merge/tag/release)
is never part of this flow — it is a separate, later, human-authorized action.

### 6.1 Stop conditions (before `apply`)

The orchestrator halts before `apply` on any of:

- unknown or missing strategy (`release-captain.toml` fail-closed);
- a dirty precondition where cleanliness is required;
- stale evidence;
- a failed `dry-run`.

### 6.2 Portability

The skill is classified for Codex portability using Bindle's existing capability
metadata (a `docs/skill-portability-audit.md` row), not assumed. Codex/human
followers use the same L1 contract + the same strategy scripts directly, per
L1 §6.

## 7. Legacy publication tooling

`bin/release.sh` may survive as **legacy / fallback publication tooling only**.
It must be documented as such and must **not** independently regenerate
Release-Please-owned artifacts (`VERSION`, `CHANGELOG.md`). Once Release Please is
the artifact authority, there is no parallel manual artifact-generation path in
the normal workflow.

## 8. Testing

- **L4 strategy (PR-A).** Fixture tests asserting:
  - `dry-run` produces the expected `release-please` command assembly and
    performs **zero** repository/branch/remote/manifest/working-tree mutation
    (verified against the fixture filesystem + git state, not self-report);
  - `apply` refuses without a valid approval token (hard stop, no mutation);
  - fail-closed behavior on missing/unknown strategy.
  - Wired into `make test`.
- **L3 skill (PR-B).** RED→GREEN pressure tests in throwaway fixture repos per
  the repo's writing-skills rule — the skill is not "done" until pressure-tested;
  recorded in `skills/release-captain/PRESSURE-TESTS.md`. Grade the filesystem
  and the subagent transcript, not the self-report.

## 9. Capability / inventory treatment

- **New skill** (`skills/release-captain/`) touches three places or `make check`
  fails: the skill dir, a `capabilities.json` row, and a
  `docs/skill-portability-audit.md` row.
- **New `bin/*.sh`** (strategy script) and **new docs / config**
  (`release-captain.toml`, `release-please-config.json`,
  `.release-please-manifest.json`, this spec) each need a `capabilities.json`
  inventory row or a `not_a_capability` ledger entry, or `make check` fails on
  inventory reconciliation.
- `version_introduced` for the new capabilities = `0.5.0` (one bump ahead of
  `VERSION` `0.4.0`, which `bin/check-inventory.py` accepts).

## 10. PR split

Two sequential PRs, both referencing `#116`:

- **PR-A — L4 strategy seam.** `release-captain.toml`; provider-neutral strategy
  selection; the `local-release-please` strategy; Release Please config +
  manifest; fixture tests; inventory treatment; (optionally) the L1 sharpening.
  This shared design doc lands here.
- **PR-B — L3 Release Captain skill.** Steps 1–5 orchestration; evidence-helper
  integration; recommendation + rationale; first approval gate; strategy
  dry-run; effect preview; second approval gate; strategy apply; capability
  registration + Codex-portability classification; RED→GREEN pressure tests; the
  L1 sharpening (if not already in PR-A).

**PR-B depends on PR-A. `#116` closes when PR-B lands.**

## 11. The release itself (after `#116`)

Once PR-B lands, cut **v0.5.0 through the new path** — Release Captain produces
the recommendation → first approval → local-RP `dry-run` → effect preview →
second approval → `apply` opens the release PR → human reviews and merges →
publication (tag / GitHub Release) as a separate, explicitly authorized human
step. The first release of the capability is thereby its own first dogfooding.
