# Design: portable issue work loop (#60, slice 1)

**Status:** design approved 2026-07-14; slice 1 of #60 (parent #55).
**Related:** #31 (`docs/workflow-composition.md`), #32 (`docs/delegation-profiles.md`),
#63 (`docs/delegated-implementation-packets.md`), #58 (`docs/domi-consumer.md`),
#56/#57 (Codex compat), #38 (e2e evals — deferred).

## Problem

Bindle has strong point workflows for branch/PR targeting, sequential-PR scope,
verification, and session continuity, but no single portable contract for taking
a repository issue from discovery to an honest end state. In practice the
discover→dedup→execute→verify→report loop is partly supplied by **DomI-fleet
skills that are not part of Bindle** — `check-done`, `list-issues`,
`dispatch-issue`, `gh-issues`, `verify-plan`. A Codex session or a fresh Bindle
install does not have them, so the loop silently depends on tools outside the
kit. Claude and Codex can each perform locally reasonable steps yet produce
different or incomplete external state.

**Goal (why this slice exists):** portability / independence. Define a
provider-neutral issue work loop that Claude *and* Codex follow to produce
equivalent final-state evidence, referencing Bindle-native assets rather than
DomI-fleet skills — and close the one gap with no Bindle-native asset today
(discover + deduplicate) with a portable, deterministic helper.

## Non-goals (slice 1)

- No scheduler, autonomous queue runner, or workflow engine.
- No parallel wave dispatch.
- No automatic model selection/assignment.
- No automatic PR merge or issue closure.
- No reproduction of DomI's fleet labels, project board, or rolling-PR
  conventions.

## Prior-work verification (dedup, done 2026-07-14)

`not-started`. No `docs/workflows/` dir, no issue-work-loop file, no `#60`
commit/PR/branch, zero comments on #60. Dependencies mostly CLOSED and shipped:
#31, #32, #63, #58, #56, #57. Of the point-skills #60 names, only
`fork-pr-flow`, `verify-then-commit`, `session-continuity`, `domi-consumer`,
`scoped-sequential-prs` are Bindle-native; the rest are DomI-fleet — which is
precisely the dependency this slice removes.

## Architecture: the repo's contract + skill + adapter trio

Slice 1 ships three artifacts, mirroring `docs/domi-consumer.md` +
`domi-consumer` skill + `bin/domi-status.sh`:

1. **`docs/workflows/issue-work-loop.md`** — the normative **portable
   contract**. The six phases, the state vocabulary, the authority rules.
   Provider-neutral: both Claude and Codex follow it. Source of truth.
2. **`skills/issue-work-loop/SKILL.md`** — Claude-native **automation** that
   *walks* the contract, delegating each phase to existing Bindle-native
   skills. A thin orchestrator, not a reimplementation. Ships as **draft**.
3. **`bin/issue-dedup-scan.sh`** — portable **adapter** for Phase 3, with tests.
   Pure `git` + `gh` bash, no Claude-only primitive.

## The six phases (contract) and their delegations (skill)

| Phase | Contract requires | Claude skill delegates to |
| --- | --- | --- |
| 1 Orient | read authoritative instructions + precedence; inspect branch/remotes/status; identify verification commands and mutation boundaries; detect `.domi-pin` | read `CLAUDE.md`; `domi-consumer` skill |
| 2 Discover & qualify | read issue + comments; confirm open/actionable/unblocked; classify task + delegation profile; name the expected deliverable | `gh issue view` (portable); `docs/delegation-profiles.md` |
| 3 Dedup before claiming | bounded evidence scan; return one verdict; failure never reads as "no prior work" | **`bin/issue-dedup-scan.sh`** → interpret emitted evidence |
| 4 Bound & execute | state exact scope + explicit non-goals; select minimal workflows; delegate only within granted authority; keep repo mutation separate from external mutation | `docs/workflow-composition.md` (#31); `docs/delegation-profiles.md` (#32); `scoped-sequential-prs`; `fork-pr-flow` targeting |
| 5 Verify | run the repo's actual checks; review final diff + git state; verify claimed remote state on the real remote; distinguish `not run` / `failed` / `passed` | `verify-then-commit` |
| 6 Close out honestly | open/update PR; comment with evidence; close only when criteria met AND closure authority explicit; leave handoff if incomplete; record adjacent work without scope creep | `session-continuity` / handoff |

## Central invariant: two separate authorities

The contract's core rule — repo mutation (edit/commit/branch) and external
mutation (`gh` comment/label/close, push, open PR) are **separate grants**.
General permission to implement does **not** imply permission to close, merge,
publish, or deploy. A worker must not trust another agent's `done` claim without
checking the current checkout and the real remote. The skill encodes explicit
gates at Phase 4 (execute) and Phase 6 (close out). This mirrors how the
operator's profile already runs (`gh` mutations + pushes need explicit
approval).

## The dedup helper: honest by construction

The contract's verdict vocabulary is the full five:
`not-started` / `in-progress-elsewhere` / `already-done` / `partially-done` /
`uncertain`. But a bash helper cannot honestly *classify* `already-done` vs
`partially-done` — that needs judgment (does the merged PR fully close the
issue?). Over-claiming that determinism would manufacture the exact false
`already-done` that #60 forbids. So the helper proves only what bash can, and
the model/human classifies the rest from the emitted evidence:

```
bin/issue-dedup-scan.sh <issue#>     # emits evidence JSON on stdout
  exit 0  no-evidence     all sub-queries ran, found nothing     -> contract: not-started
  exit 3  evidence-found  matching PR / commit / comment found   -> contract: model reads evidence,
                                                                     picks in-progress-elsewhere /
                                                                     already-done / partially-done
  exit 4  uncertain       ANY sub-query failed (gh error, no net) -> contract: never a clean verdict
```

**The guarantee #60 demands lives in the exit code:** query failure (exit 4) is
structurally distinct from an empty-but-successful scan (exit 0). "Empty/failed
query never = already-done" is enforced by bash, not by model prose. The helper
never emits `already-done`/`partially-done` on its own.

**Evidence sources scanned** (each a separate sub-query; any failing → exit 4):
recent `git log`; repo specs/plans/ADRs (`docs/design/`, `docs/plans/`, `specs/`);
open PRs; closed/merged PRs; the issue's own comments and linked issues.

**Output shape:** JSON on stdout — `{ "verdict": "...", "evidence": [ {source,
ref, why} ], "queries": [ {name, status: ok|failed} ] }`. Machine-readable so
the skill (or Codex) reads the evidence, not a self-report.

## Testing and rollout

- **Helper — tested this slice.** Deterministic, so unit-tested now. Fixtures
  cover: genuinely new issue → `no-evidence`/exit 0; merged PR present →
  `evidence-found`/exit 3; a forced sub-query failure → `uncertain`/exit 4
  (the critical anti-false-negative case). Test harness follows the repo's
  existing `tests/` bash pattern.
- **Skill — ships draft.** Per repo discipline a skill isn't done until
  pressure-tested (RED→GREEN→REFACTOR). Slice 1 ships `skills/issue-work-loop`
  marked **draft in CHANGELOG**; the pressure-test campaign is a follow-up
  session (the #59/#103 rhythm: build, then a separate RED→GREEN session).
- **Pressure-test matrix (deferred to follow-up).** #60's seven state-based
  scenarios become the skill's matrix: new issue; open issue already solved by
  a merged PR; duplicated open issue with active work elsewhere; partial
  implementation with stale issue state; implementation complete but checks not
  run; checks green but PR/issue state not updated; blocked external mutation
  where a local handoff is correct.
- **#38 e2e / composition evals — deferred** until the contract is stable.

## Inventory & gates (#29)

Adding these artifacts is the known 3-place touch, enforced by `make check`
(`bin/check-inventory.py`):

- `docs/workflows/issue-work-loop.md` — new `docs/**/*.md` not under an excluded
  prefix, so it needs a `contract` capability row (or a `not_a_capability`
  ledger entry). *This design spec under `docs/design/` is excluded (checker's
  `^docs/design/` rule), so it needs no entry.*
- `skills/issue-work-loop/` — a skill capability row (`bin/new.sh` scaffolds a
  draft one) **and** a `docs/skill-portability-audit.md` row, or the bound-table
  bijection fails.
- `bin/issue-dedup-scan.sh` — a new `bin/*.sh`, so a `script` capability row or
  a `not_a_capability` entry.

Link references inside contract/spec bodies use inline-code, not markdown links,
to avoid the link-checker resolving relative paths against the file's own dir.

## Acceptance mapping (#60)

- Full discover→dedup→execute→verify→report/handoff loop, provider-neutral —
  contract §phases.
- Existing workflows referenced, not duplicated — delegation table; helper is
  the one net-new capability (no Bindle dedup asset exists).
- Claude and Codex follow the same state transitions — one neutral contract,
  the skill is Claude's adapter, `gh`/`git` are portable.
- Repository vs external mutation distinguished — two-authority invariant.
- Dedup cannot read empty/failed as no-prior-work — helper exit 4 vs exit 0.
- #29 records the capability + adapters — inventory section.
- `make check` passes; helper has tests — testing section.

## Open items carried to implementation

- Exact evidence-source query commands and their failure detection in the
  helper (each sub-query must fail-closed to exit 4).
- Whether Phase 2 classification pulls the delegation profile inline or defers
  it to the operator — resolve when writing the contract body.
