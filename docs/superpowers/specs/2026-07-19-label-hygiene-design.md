# Label hygiene: contract, guard, audit — design

**Status:** proposed
**Date:** 2026-07-19

Settles `#287`'s open design question and scopes `#266` as its audit half.

## Problem

`docs/issue-tracking.md` defines a `type:`/`status:`/`priority:` taxonomy that a
live dashboard parses directly. Every transition in that taxonomy is hand-driven,
and `#287` records four frictions observed across two consecutive sessions:

1. transitions are entirely manual (`#197` triage→ready, `#261` ready→in-progress)
2. closed issues retain open-only labels (`#279` closed on merge still carrying
   `status: in-progress`; `#309` the same, one session later)
3. `status: done` duplicates the closed state
4. `priority:` is applied inconsistently (`#197` sat at `status: ready` with none)

Measured against the live repo on 2026-07-19, **all four invariants currently
hold**: 0 closed issues carry a `status:` label, 0 of 53 open issues lack a
`status:` or `priority:` label, and `status: done` has 0 uses in any state. A
single sweep during the `#227` session removed 62 stale labels; a second sweep
last session removed one more.

That is the shape of the problem. This is drift, not a standing defect — the
invariants are true whenever someone has recently swept and false whenever they
have not. Anything built here ships green on day one and earns its keep later.

### The drift path that actually fires

Both observed drifts (`#279`, `#309`) were closed by **PR merge** via a
`Resolves #N` keyword, not by `gh issue close`. Any enforcement point that
watches only explicit closure would have caught neither. Merge-closure is the
path that must be covered for this to be worth building.

## Decisions

`#287` left the choice between "a `bin/check-*.sh` leg asserting the invariants"
and "automating the transitions themselves" explicitly open. Settled:

**Prevent at the transition, and audit as a backstop — both.** The guard reaches
the machine that does nearly all closing here; the audit reaches drift the guard
structurally cannot see (web UI, a terminal outside the harness, another
person's merge). Neither alone covers the surface.

**Friction 1 is deliberately out of scope.** `ready → in-progress` rides a real
event and could be automated, but `triage → ready` cannot: per
`docs/issue-tracking.md`, that transition means the issue now carries a
[delegated implementation packet](../../delegated-implementation-packets.md) and
is safe to hand to a subagent. No event carries that judgment. A `status: ready`
that lies is worse than one that is stale, because `ready` is precisely what
makes an issue delegable without a re-read. Automating half a transition pair and
leaving the judgment half manual buys little and obscures which half is
trustworthy. Left manual, and stated as a boundary rather than a gap.

## Three units

Ordered by dependency. A is the written contract; B enforces it; C reports on it.

### A — retire `status: done`, write the contract

No code. `gh label delete "status: done"` — 0 uses, nothing to migrate. Its
existence is the invitation to the drift in friction 2: a label whose meaning is
already carried by closure, with no description, is a coin flip every time
someone closes an issue.

`docs/issue-tracking.md` then states the rules it currently only implies:

> `status:` labels scope to **open** issues. Closing an issue — directly or by
> merging a PR that references it — must remove its `status:` label. There is no
> `status: done`; done is closure.
>
> Every open issue outside `status: triage` carries a `priority:` label.

The document today says "Done is expressed by **closing** the issue, not by a
label" but never says what happens to the label already on it, and never
requires a priority at all. B and C both enforce *this text*, which is `#266`'s
third acceptance criterion — the check enforces a written contract rather than an
inferred one — satisfied by A rather than by either gate.

### B — `global/hooks/label-hygiene-guard.py`

A `PreToolUse` guard on `Bash`, in the shape of the two guards already shipped.

**Gating.** `docs/issue-tracking.md` absent from the repo root → `sys.exit(0)`.
The guard enforces the label **prefixes** `status:` and `priority:`, never
specific values.

Prefix-only matters twice. It keeps the vocabulary free to grow — adding
`status: parked` needs no guard edit — and it keeps the guard honest about what
the invariants actually turn on: "no `status:*` survives closure", "some
`priority:*` is present". Neither invariant has ever needed to know which value.

This is a different gating choice from `nested-notes-guard.py`, which hardcodes
`OWNER = "domattioli"` and matches it against `git remote -v`. That guard governs
prose style for a specific person's repos, so an owner is the correct signal.
This one governs a convention any repo could adopt, so the convention's own
contract file is the correct signal — and it fires in exactly the repos where the
rules mean something.

**Rules.**

| Rule | Trigger | Refuses when | Message |
| --- | --- | --- | --- |
| R1 | `gh issue close N` | `#N` carries `status:*` and the command has no matching `--remove-label` | the exact `--remove-label` flag to append |
| R2 | `gh pr merge N` | the PR body's closing keywords resolve to issues carrying `status:*` | one `gh issue edit --remove-label` per issue |
| R3 | `gh issue edit N --add-label "status: <non-triage>"` | `#N` carries no `priority:*` | add a `priority:` label first |

R1 needs one label read. R2 needs a PR-body read plus a label read per referenced
issue. R3 needs one label read.

Every refusal names the exact command that satisfies it. A guard that says no
without saying what yes looks like is a guard people learn to route around.

**Bypass coverage.** `gh api -X PATCH /repos/<o>/<r>/issues/N -f state=closed`
closes an issue without touching `gh issue close`. R1's matcher covers it, in the
same shape `nested-notes-guard.py` already uses to match `gh api` calls carrying a
`body=` field to an issues/pulls path. There is no GitHub MCP server configured in
this environment, so `Bash` is the entire write surface and covering `gh api`
closes the bypass completely — the `#264` lesson applied before it costs anything.

**Failure posture: fails OPEN.** An unreachable, rate-limited, or erroring GitHub
API **allows** the call, with a visible warning naming what went unverified.

This follows the doctrine `#309` set rather than departing from it. `#264` fails
closed because passing a write it could not judge was the hole it was filed to
close. Here the asymmetry runs the other way: a false allow is a stale label on a
dashboard, cosmetic and caught by C on the next audit; a false deny is an
unmergeable PR during a GitHub outage. The v0.9.0 cut hit a 503 mid-release
(`#265`) — that window is not hypothetical, and a guard that turns it into a work
stoppage costs more than every stale label it would prevent.

Per `#264`, the wire-up carries no `|| true`: only exit code 2 blocks a
`PreToolUse` call, so a missing hook already fails visibly without blocking.

### C — `bin/check-issue-labels.sh`

The audit backstop, and what `#266` asks for. Asserts all three invariants
against live GitHub state:

- no closed issue carries a `status:` label
- every open issue outside `status: triage` carries a `priority:` label
- the `status: done` label does not exist

**Not wired into `bin/check.sh`**, for two independent reasons. `check.sh` is
copied into throwaway fixture repos by `bin/test-check.sh` and
`bin/test-check-frontmatter.sh`, which have no network and no GitHub repo — a
network-dependent section would couple every fixture builder to a live API. And
the pre-commit path must stay offline.

C is therefore wired into nothing and invoked by hand. Its natural call site is
session-end, where label reconciliation is already a manual step — but making
that automatic is a separate decision about the session-end command, not part of
this design.

**Skips loudly.** `gh` absent or unauthenticated → a stated reason and a
non-green result, never a silent pass. A gate that reports success when it did
not run is the `#279` failure mode, and this repo has already paid for it once.

## Files

| Path | Unit | Inventory |
| --- | --- | --- |
| `docs/issue-tracking.md` | A | existing row |
| `global/hooks/label-hygiene-guard.py` | B | none — the inventory governs `bin/*.sh`, `docs/**/*.md`, skills, commands, agents, global guidance |
| `bin/check-issue-labels.sh` | C | `capabilities.json` row required |
| `bin/test-issue-labels.sh` | C | `bin/test-*.sh` is AUTO_EXCLUDEd |
| `bin/test-label-hygiene-guard.sh` | B | `bin/test-*.sh` is AUTO_EXCLUDEd |
| this document | — | `not_a_capability` ledger entry required |

`docs/superpowers/specs/**` is **not** AUTO_EXCLUDEd; both `#264`'s and `#309`'s
specs carry ledger entries and this one needs the same.

## Testing

Fixture-driven, no network in the suites themselves — canned GitHub JSON
responses stand in for the API so the suites run under pre-commit and offline.

- **B:** R1/R2/R3 each get a refusing case and an allowing case. The R2 case must
  exercise a PR body with a real closing keyword resolving to a labeled issue —
  the `#279`/`#309` shape, since that is the failure the guard exists for. Plus:
  the gate case (no `docs/issue-tracking.md` → exit 0, no API call), the
  fail-open case (API error → allow, warn), the `gh api` bypass case, and a
  read-shaped `gh` command that must pass untouched.
- **C:** each of the three assertions gets a passing and a failing fixture, plus
  the `gh`-unavailable case asserting a loud skip rather than a green.

**Mutation pass**, per the repo rule that a new gate must be proven failable:
stub out each rule in turn and confirm every negative assertion flips to failing.
An assertion that still passes with its rule removed was vacuous. `cmp` the
mutated copy against the original first and fail loudly if nothing changed — a
stale `sed` silently turns a failability case into a no-op that always passes.

Any git-touching fixture test must `unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE
GIT_OBJECT_DIRECTORY GIT_COMMON_DIR` at the top; git sets `GIT_DIR` in the hook
env and it overrides `git -C`.

New suites must be `git add`ed before `bin/run-test-suites.sh` discovers them —
it enumerates via `git ls-files` and reports "all N pass" while silently skipping
an untracked suite.

## Issue map

| Unit | Issue | PR |
| --- | --- | --- |
| A | `#287` | contract: label deletion + `docs/issue-tracking.md` rules |
| B | `#287` | the guard |
| C | `#266` | the audit script |

`#287`'s close comment records friction 1 as deliberately out of scope, with the
reasoning above, so the deferral is not silent.

## Non-goals

- No automation of any `status:` transition (friction 1 — see Decisions).
- No change to the dashboard, which is an external repo out of scope here.
- No `bin/check.sh` section; C stays standalone and network-dependent.
- No change to the `type:` facet, which shows no observed drift.
