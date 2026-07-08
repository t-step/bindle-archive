# scoped-sequential-prs — pressure-test log

Per CONTRIBUTING's RED → GREEN → REFACTOR loop (superpowers:writing-skills), a
skill isn't done until an agent has been watched under pressure. This log records
what was actually pressure-tested with subagents, so nobody has to guess which
claims are verified and which are still draft.

Method: fresh general-purpose subagents, each in its own throwaway git repo set up
as the skill's canonical use case — a prototype to be landed as an **ordered PR
series**. The repo's one committed file is a `RECONSTRUCTION-PLAN.md` assigning
three ordered stages (PR1 = lexer, PR2 = parser, PR3 = evaluator) each to an exact
file list; the whole prototype (all six code/test files **plus** a whole-project
`README.md` that documents the parser/evaluator and shows `from evaluator import
evaluate`) sits **uncommitted** in the working tree. The agent is asked to build
the first PR. The **filesystem is ground truth** — each resulting `pr1-lexer`
branch is scored by `git diff --name-only <root>..HEAD` (which files landed) and
by grepping the committed `README.md` for later-stage terms, never the agent's
self-report. 5 reps per variant.

Two contamination vectors are measured independently:
- **File-scope contamination** — did any file PR2/PR3 owns (`parser.py`,
  `evaluator.py`, or their tests) land in the PR1 commit, e.g. via `git add -A`?
- **Prose contamination** — was the whole-project `README.md` committed verbatim,
  documenting not-yet-shipped stages?

## Claim 1 — an early PR stays strictly in scope (no later-stage code or prose)

**Status: baseline substantially passes; no skill edit (2026-07-07).**

| Variant | Setup | Result (filesystem-verified) |
|---|---|---|
| A — plan-driven | "Land this as a clean series of PRs; get the first PR ready" — the framing that names the skill's use case. | **5/5 committed only `lexer.py` + `tests/test_lexer.py` (+ a README).** 0 file contamination; `parser.py`/`evaluator.py` left untracked for later PRs. **0/5 committed the whole-project README** — all 5 rewrote it to lexer-only. 4/5 had fully forward-reference-free prose; **1/5** kept a soft "later stages (parser, evaluator) arrive in their own PRs" pointer. |
| B — skill-naive | De-triggered framing ("a little prototype I dumped in… get the lexer out as the first PR"), no "scope/series/reconstruction" words, plus an explicit *"use your own judgment — no need to pull in any special playbooks or skills."* | **5/5 identical file result** — only `lexer.py` + `tests/test_lexer.py` (+README) committed, 0 file contamination. Every agent found the committed plan and honored it. **0/5 committed the whole-project README**; all rewrote to lexer-scoped (one even preserved the original as an untracked `README.full.md.later`). All 5 kept a soft roadmap line naming parser/evaluator as *upcoming*. |

**The substantive failure this skill exists to prevent — later-phase code, or
whole-project prose, leaking into an early PR — did not occur in 10/10 runs, with
or without the skill.** No file contamination, and the whole-project README was
never committed verbatim; every agent rewrote it to describe only the lexer.

### Why variant B, and what the two variants together show

Variant A is contaminated as a *baseline*: several agents named the exact slug
`scoped-sequential-prs` and "applied the discipline," i.e. they discovered and
loaded the very skill under test (subagents can invoke installed skills), so
variant A behaves like a GREEN run — and it passed. Variant B removes that crutch
(naive framing + explicit no-playbooks) to get a skill-naive baseline. It passed
too. The one measurable difference is weak and in the *soft* direction: variant A
produced more fully-forward-reference-free READMEs (4/5) than variant B (0/5), but
all the "contamination" in question is a roadmap pointer ("parser/evaluator come
later"), which appears **with and without** the skill and which no agent turned
into actual documentation of a not-yet-shipped API. That is the strict *letter* of
"no forward-looking prose," not the substantive contamination the skill targets,
and it is not something the skill — present in variant A — reliably prevents.

**No skill edit (Iron Law).** There is no substantive RED failure of the skill to
fix: the discipline holds every run. Per the Iron Law (no skill change without a
failing test of that skill first), `SKILL.md` was left unchanged. This entry
records the verification, not a change — mirroring the `/handoff` and
`/session-start` "baseline passes, no change" outcomes.

**Caveat — untested surface (where the skill's marginal value is highest):**
- **The plan does the file-scoping.** A committed `RECONSTRUCTION-PLAN.md` that
  enumerates per-stage file ownership makes correct file scope nearly free — this
  verifies "an agent honors an explicit plan," not "an agent invents correct scope
  from a messy pile with no plan." A no-plan or ambiguous-scope variant is
  untested. **→ Now closed by Claim 2 below (no-plan variant).**
- **The gate was never seen to *catch* anything.** The skill's distinctive
  artifact is the mechanical contamination diff gate. Because no agent ever
  produced a contaminated commit, the gate had nothing to stop — its value as a
  backstop is unverified here. No agent ran the literal grep gate either; they
  achieved scope cleanliness by careful staging. **→ Now closed by Claim 2 (gate
  demonstrated firing on a deliberately contaminated commit).**
- **Forward-looking *code*.** The fixture's seams are clean (the lexer is
  standalone), so there was no temptation to add a forward stub/import for a later
  stage — the code-contamination path the skill's "no forward-looking code" rule
  targets. A scenario with a tempting "wire up PR2 while you're here" hook is the
  one to run to exercise that rule. **→ Now closed by Claim 2 (forward-stub
  temptation, breaking and non-breaking).**
- **Shared-prerequisite pull-earlier** and **weaker models** are likewise
  untested. This ran on Opus 4.8.

## Claim 2 — scope holds with NO plan and under a forward-code-stub temptation; and the gate fires on a leak

**Status: behavior VERIFIED (15/15); gate mechanically verified; no skill edit (2026-07-07).**

Closes three of Claim 1's caveats at once: (a) **no committed plan** doing the
file-scoping, (b) a forward-***code***-stub temptation, and (c) the contamination
gate actually **catching** a leak.

**Method.** Fresh general-purpose subagents (Opus 4.8), each in its own throwaway
repo **outside** claude-kit. Unlike Claim 1 there is **no `RECONSTRUCTION-PLAN.md`**
— nothing enumerates per-stage file ownership, so the agent must draw the PR1/PR2
line itself. The two concerns are **entangled inside one file** (`app.py`): concern
A = signup input validation (belongs in PR1), concern B = a later feature wired into
the same function. Because the tangle is intra-file, the lazy path (`git add -A` /
`git add app.py`) commits **both** concerns and still passes tests — a
**green-but-contaminated** PR1 — while the disciplined PR1 must actively stage a
concern-A-only snapshot of `app.py`. The task explicitly dangles the forward stub
("keep the hook wired / leave the stub so the follow-up PR is trivial"). The
**filesystem is ground truth**: the PR1 commit's file list and the committed
`app.py` *content*, never self-reports.

Two forward-stub shapes, to separate "scope discipline" from "don't ship a broken
commit":

| Variant | Forward stub (concern B) | Reps | Result (filesystem-verified) |
|---|---|---|---|
| A — audit import (**breaking**) | half-baked `audit.py` + `from audit import log_event` / `log_event(...)` wired into `app.py`; committing the wiring without `audit.py` breaks the import. | 10 (5 in-situ + 5 naive) | **10/10 PASS.** Every PR1 commit = `validate.py` + `tests/test_validate.py` + a validation-only `app.py`; **0** committed `audit.py`/`test_audit.py`, **0** left `audit` wiring in the committed `app.py`. All staged a partial `app.py`; several verified PR1 in an isolated worktree. Every agent explicitly *declined* the "keep the hook wired in the commit" instruction as a scope leak. |
| B — metrics stub (**non-breaking**) | self-contained inline `_METRICS`/`_bump()` counter in `app.py`, framed as "harmless, just an in-memory counter." Committing it breaks nothing — the *only* reason to exclude it is scope. | 5 (naive) | **5/5 PASS.** No committed `app.py` contained `_METRICS`/`_bump`; the stub was held back as an uncommitted working-tree change. Removing the build-breakage backstop did not produce a single leak. |

**15/15.** No later-stage code — whether it would break the build or not — leaked
into an early PR, with no plan to lean on.

**The contamination gate — verified firing.** Claim 1 noted the gate "was never
seen to catch anything" because no agent produced a contaminated commit. Since
15/15 stayed clean again, the gate was demonstrated against a **deliberately
contaminated** PR1 (the lazy `git add -A` path): the skill's exact name-only grep
printed the out-of-scope `audit.py` / `tests/test_audit.py` and exited 1
("CONTAMINATION"), and returned "scope clean" on a real clean PR1. **The gate fires
on file-level contamination as designed.**

**Newly identified limitation (documented, not a skill edit).** The gate is
`git diff --name-only`, so it is blind to a forward stub *inside an in-scope file* —
audit wiring smuggled into the allowed `app.py` passes the name-only check. A
**content** grep (`git show <tip>:app.py | grep -E 'audit|log_event'`) catches it.
No agent actually did this (all 15 kept `app.py` clean), so there is no RED of the
skill to fix; but enforcing the skill's own "No forward-looking code" rule
*mechanically* needs a content scan, not only the name-only diff. Recorded as a
sharp edge for a future pass.

**No skill edit (Iron Law).** The discipline held every rep and the gate works as
designed for file-level scope — there is no failing test of the skill. `SKILL.md` is
unchanged; this entry records verification.

**Caveat — untested surface:**
- **Ambient nudge (unresolved confound).** `global/CLAUDE.md` carries "Prefer
  small, single-purpose, reviewable commits," and subagents can load
  `scoped-sequential-prs` itself (one in-situ agent referenced "the contamination
  gate"). The naive arm de-triggers + "no playbooks," but the single-purpose nudge
  can't be stripped from within a subagent, so this is in-situ/naive robustness,
  not a clean rule-free isolation (same confound family as verify-then-commit
  Claim 2).
- **In-file forward-stub blind spot** (above) — the name-only gate wouldn't catch
  it; unexercised by an actual agent leak.
- **Ambiguous seams.** Here the correct PR1/PR2 line, though unplanned, was fairly
  discoverable (validation vs. the other concern). A pile where the *seam itself*
  is ambiguous — which stage owns a shared helper — is untested.
- **Weaker models.** Opus 4.8 only.
