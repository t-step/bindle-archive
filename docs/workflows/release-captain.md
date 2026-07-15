# Release captain

The provider-neutral contract for turning accumulated, verified work into an
**evidence-backed release recommendation** — followed sequentially by a human,
by Codex reading this doc directly, or automated by a Claude-native skill.
Resolves the contract layer (L1) of issue `#116`; related `#59`
(release-integrity), `#60` (issue work loop).

## 1. Purpose & scope

Bindle already has release-integrity checking (`package-release-integrity`,
`docs/package-release-integrity.md`) and mechanical release cutting
(`bin/release.sh`, `bin/release-manifest.py`). What it lacks is the **decision
layer** between "verified work has accumulated" and "a release should be cut":
whether a release is justified at all, what version movement it warrants,
whether to release now or batch, and — critically — the evidence and
uncertainty behind that call.

This contract fixes that decision as six steps (below) plus a shared
classification and timing vocabulary. It is deliberately provider-neutral in
the AI sense: Section 6 maps the same six steps onto Claude-native assets and
onto what Codex (or a human) does with the same doc. Naming a mechanical tool
(Release Please, Section 3 step 6) does not break that neutrality — Release
Please is release plumbing, not an AI provider, and every step above the
handoff is followed identically regardless of who drives.

**The workflow recommends and explains. It does not merge, tag, publish,
deploy, or authorize a release.** That boundary is the invariant in Section 2,
and it holds at every step.

**Non-goals (L1).** This is not a universal release engine, does not replace
the `#59` release-integrity checks, does not replace repository-local release
policy, and never merges/tags/publishes/deploys on its own authority. It does
not support every package ecosystem, and it does not make model classification
authoritative — explicit maintainer metadata always outranks inference. The
deterministic evidence helper (L2), the Claude-native skill (L3), and the
Release Please configuration and wrapper (L4) are separate, deferred units of
`#116`, tracked separately; this document is the contract they all cite.

## 2. The two authorities (invariant)

Two kinds of mutation are separate grants, never implied by each other:

- **Repository mutation** — editing files, committing, creating or switching
  branches, working inside the checkout.
- **External mutation** — anything that changes state outside the local
  checkout on a real remote: `gh` issue comment/label/close, `git push`,
  opening a PR, merging a PR, tagging, publishing, deploying, creating a
  GitHub Release.

**A release recommendation is not a release authorization.** Producing a
recommendation — however high its confidence, however green the CI — does not
imply permission to merge, tag, publish, deploy, or create a release. Each
such external mutation needs its own explicit grant naming that exact action,
the same rule `docs/delegation-profiles.md` states for Privileged authority.
This is where the temptation to conflate the two actually shows up: a
recommendation of "release now, minor, high confidence" is still only a
recommendation, and a created release PR is a *proposal* awaiting a human
merge, not a decision already made.

**A tool or network failure produces `uncertain`, never a false
recommendation.** If evidence could not be gathered, or contradicts itself,
the workflow says so and declines to fabricate a version or timing call — the
same principle `bin/issue-dedup-scan.sh` encodes for the issue work loop. An
absent or failed check is never laundered into an optimistic "looks
releasable."

## 3. The six steps

### Step 1 — Orient

- Identify the latest valid release tag and the current version source of
  truth — for Bindle, the `VERSION` file cross-checked against
  `RELEASE-MANIFEST.json`; do not assume a version from a changelog heading
  alone.
- Verify the intended base branch and real remote state (`main`, up to date)
  — don't assume a branch or a clean tree.
- Read repository-local release policy, **including pre-1.0 semantics**. For
  Bindle this is the `CHANGELOG.md` SemVer rule: `major` = a breaking change
  to how the toolkit installs or is structured; `minor` = a new skill, agent,
  command, or capability; `patch` = a fix or tweak to something that already
  exists. That mapping — not textbook SemVer — governs Section step 4.
- Detect whether Release Please is configured, and whether repository-specific
  release authority exists (a `CODEOWNERS`, a documented release captain).
- Defer to stronger repository-local or inherited (DomI) release policy where
  present, rather than overriding it from this contract.

### Step 2 — Gather release evidence

Prefer coherent merged changes over intermediate commits. Consult evidence
sources in this precedence order, and record which one each classification
rests on:

1. explicit release labels or metadata on merged PRs;
2. breaking-change metadata;
3. Conventional Commit-compatible squash PR titles;
4. commits since the latest tag, when PR evidence is unavailable;
5. diff inspection as *supporting* evidence only — never the sole source of
   truth when intent is ambiguous.

Collect, at minimum: merged PRs and their linked issues since the latest
release; user-visible behavior changes; fixes, compatibility changes,
dependency changes, schemas, APIs, CLIs, workflows, and packaged content;
docs/test/CI-only changes (which normally do **not** justify a release);
current CI and release-integrity state; and any unresolved or uncertain
changes that may affect classification.

### Step 3 — Classify each change

Classify each coherent change as exactly one of:

- `none` — no distributable or user-relevant release effect;
- `patch` — backward-compatible fix;
- `minor` — backward-compatible capability;
- `breaking` — incompatible public behavior or contract change;
- `uncertain` — insufficient or contradictory evidence.

Explicit maintainer metadata takes precedence over inference — but where the
evidence appears *inconsistent* with that metadata, flag the inconsistency
rather than silently overriding either side.

### Step 4 — Recommend version and timing, separately

Produce two decisions, never collapsed into one:

- **Version recommendation:** `none` / `patch` / `minor` / the repository
  policy's result for `breaking`.
- **Timing recommendation:** `no-release` / `batch` / `release-now`.

The highest classified change determines the *minimum* version movement.
**Repository policy determines how each class maps to an actual version
number** — for Bindle, per step 1: a `breaking` install/structure change moves
`major`; a new capability moves `minor`; a fix moves `patch`. Under Bindle's
pre-1.0 line this mapping is applied as written (it is already a
`0.MINOR.PATCH` scheme, not a "pin everything under 1.0" convention); any
repository with different pre-1.0 semantics supplies its own mapping here.

The timing recommendation accounts for signals the version class alone does
not capture: security or installation fixes; severe regressions; externally
requested functionality; milestone completion; or several individually
releasable low-urgency fixes that are sensible to batch.

### Step 5 — Explain and request authorization

Emit a concise recommendation — human-readable and machine-readable —
containing: the current version and latest release; the suggested next
version; the timing recommendation; a confidence level; the included and
excluded PRs/issues; the rationale for each material classification;
unresolved ambiguity; release-integrity/CI readiness; and an explicit
authority statement. Example shape:

```text
Release recommendation

Current version: 0.4.0
Suggested version: 0.5.0
Timing: release now
Confidence: high

Why:
- one new user-facing workflow
- two backward-compatible fixes
- no detected public removals
- required verification passes

Included: #57, #59, #103
Excluded: CI cleanup, internal docs reconciliation

Authority boundary:
- recommendation only
- no merge, tag, publish, release, or deploy performed
```

If step 3 produced any `uncertain` change, or the evidence contradicts the
maintainer metadata, the recommendation **fails safe**: it reports the
ambiguity and declines to state a version or timing call it cannot support,
rather than fabricating one.

### Step 6 — Optional Release Please handoff

Only after explicit maintainer approval, the workflow may invoke or instruct a
checked-in wrapper that runs Release Please to create or update the release
PR. The three authorities are distinct: **Release Please owns the mechanical
release-PR artifact layer** — the version/changelog updates and the release PR
itself; **tag, GitHub Release, package publication, and deployment belong to
explicitly human-authorized publication** — a separate grant, never implied by
a created release PR; and Bindle (Release Captain) owns the release *intent*
and the authority boundaries above both. The handoff must:

- pass only an *approved* recommendation into the mechanical step;
- support dry-run/preview where available;
- preserve Release Please's release PR as the **human promotion gate** — the
  PR is a proposal, its merge is a person's decision;
- run release-integrity verification (`package-release-integrity` / `#59`)
  before any publication;
- never treat the recommendation, passing CI, or a created release PR as
  authorization to merge or publish (Section 2).

This step is the boundary between this contract (L1) and the Release Please
configuration and wrapper (L4 of `#116`, deferred). Bindle's current interim
mechanical path is `bin/release.sh`; the target mechanical layer named by this
contract is Release Please, and migrating from one to the other is L4's scope,
not this document's.

## 4. Classification & timing vocabulary

**Version classes** (mutually exclusive, one per coherent change):

- `none` — no distributable/user-relevant effect (e.g. docs, tests, CI only).
- `patch` — a backward-compatible fix to something that already exists.
- `minor` — a new, backward-compatible capability.
- `breaking` — an incompatible public behavior or contract change; mapped to a
  version number by repository policy (for Bindle, `major` only when it breaks
  install/structure — otherwise the change is `minor` under the CHANGELOG
  rule).
- `uncertain` — insufficient or contradictory evidence; never silently
  resolved to a concrete class.

**Timing recommendations** (mutually exclusive):

- `no-release` — accumulated change does not justify cutting a release now.
- `batch` — releasable work exists but is sensibly held for a later combined
  release.
- `release-now` — a signal (security/install fix, severe regression, external
  request, milestone) justifies releasing now.

**The fail-safe rule.** An `uncertain` classification, or evidence that
contradicts maintainer metadata, prevents a concrete version/timing
recommendation for the affected work. The workflow reports the gap; it does
not guess a class or a number to produce a tidier output.

## 5. Fit with the rest of Bindle

- **Above the mechanical layer.** This contract stops at a *recommendation*.
  The mechanical release-PR *artifact* work (version/changelog + the PR)
  belongs to Release Please, invoked only after human approval per step 6; tag,
  GitHub Release, package publication, and deployment are separate,
  human-authorized publication, never implied by a created release PR.
  `bin/release.sh` remains only as legacy/fallback publication tooling and does
  not regenerate Release-Please-owned artifacts.
- **Beside `#59` release-integrity.** `package-release-integrity` verifies a
  release is *safe to cut* (version-source agreement, tag/version consistency,
  changelog presence, correct semver movement). This contract decides *whether
  and what* to cut. They compose — step 6 runs the integrity check before
  publication — and neither replaces the other.
- **Below repository release policy.** Where a repo (or inherited DomI policy)
  states its own release rules, this contract defers to them (step 1); it
  supplies the reasoning loop, not the policy.

## 6. Provider mapping

Each step's *requirement* is identical across providers; only the mechanism
differs. Claude will automate the mechanical parts via a Claude-native skill
(L3 of `#116`, deferred) backed by a deterministic evidence helper (L2,
deferred); Codex — or a human — follows the same steps directly from this doc
and the repo's shell scripts.

| Step | Claude asset (when built) | Codex / human equivalent |
|---|---|---|
| 1. Orient | reads `CLAUDE.md`, `VERSION`, `RELEASE-MANIFEST.json`, `CHANGELOG.md` policy; `domi-consumer` skill | reads `AGENTS.md` + the same files; runs `bin/domi-status.sh` directly |
| 2. Gather evidence | L2 evidence helper (deferred) over `gh` PR/issue data + `git log` | same `gh` / `git log` queries by hand, same precedence order |
| 3. Classify | L3 skill applies the vocabulary; metadata precedence enforced | applies the same vocabulary manually from this doc |
| 4. Recommend version + timing | L3 skill, using the repo policy mapping from step 1 | same mapping applied by hand |
| 5. Explain + request authorization | L3 skill emits the human- + machine-readable recommendation | writes the same recommendation shape by hand |
| 6. Release Please handoff | L4 wrapper (deferred), only on explicit approval | runs the same approved wrapper / Release Please commands directly |

The contract in Sections 1–5 is what stays fixed. This table is the only place
providers are allowed to differ — consistent with
`docs/workflow-composition.md`'s Provider adapters category. Until L2/L3/L4
land, the Claude column describes intent, not installed automation: today
every provider, Claude included, follows this contract manually.
