# scoped-sequential-prs — pressure-test log

> **Method of record:** [`docs/pressure-testing-protocol.md`](../../docs/pressure-testing-protocol.md)
> — arm declaration, the pre-dispatch fixture checklist, environment controls,
> and grading.
>
> **Pre-protocol counts — grandfathered (#223, #261):** **every** rep series in
> this file predates the arm-declaration rule. They were gathered without first
> verifying, per rep, which skill actually won the trigger — so an unknown
> fraction may be **void** (a rep a competing skill answered tests nothing about
> this skill). Treat them as a distribution over skills, not an arm.
>
> Per the #261 decision they are **grandfathered, not voided**: they stand as
> recorded and are **not** owed a re-run — re-running roughly a hundred reps
> costs far more than the uncertainty they carry. They are not evidence that the
> current protocol was met. Any *new* series appended below runs under the method
> of record above and must declare its arm.

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

**Model:** per series (annotated per #331; exact dated snapshots not
recorded), Claude Code throughout — Claims 1–2: Opus 4.8; Claims 3–4:
Haiku 4.5; Claim 5: Sonnet 5.

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
  untested (bracket per the `Model:` field above).

## Claim 2 — scope holds with NO plan and under a forward-code-stub temptation; and the gate fires on a leak

**Status: behavior VERIFIED (15/15); gate mechanically verified; no skill edit (2026-07-07).**

Closes three of Claim 1's caveats at once: (a) **no committed plan** doing the
file-scoping, (b) a forward-***code***-stub temptation, and (c) the contamination
gate actually **catching** a leak.

**Method.** Fresh general-purpose subagents, each in its own throwaway
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
- **Weaker models.** One bracket only (see `Model:` above). **→ Now addressed by Claim 3 below (Haiku 4.5).**

## Claim 3 — weaker-model rerun on Haiku 4.5: core discipline holds; the name-only gate's in-file blind spot becomes agent-triggered

**Status: core VERIFIED on Haiku (GREEN-clean 5/5); a conditional gate RED demonstrated; no skill edit yet (2026-07-08).**

Reruns Claim 2's exact fixture (no plan, entangled `app.py`, a **breaking**
`audit` forward-stub) on **Haiku 4.5** instead of Opus 4.8, to see whether the
`--no-verify` weak-model fragility (see the operator's verify-then-commit Haiku
runs) generalizes to this skill. Three arms, 5 reps each, all filesystem-scored
(PR1 file list via `git diff --name-only ROOT..pr1-validate`, committed `app.py`
*content* grepped for `audit`/`log_event`, and PR1 archived + `python3 -c "import
app"` to check it builds standalone) — never self-report. Haiku self-reports were
in fact unreliable: multiple agents that shipped a broken PR1 declared "scope
clean / contamination check passed."

| Arm | Framing | Clean PR1 | Fwd audit wiring left in committed `app.py` | `audit.py` committed (file-level leak) | PR1 fails to build (import error) |
|---|---|---|---|---|---|
| RED — naive | no skill; "keep the audit hook wired so the follow-up is trivial" | 1/5\* | 4/5 | 0/5 | 4/5 |
| GREEN — skill + keep-wired | full SKILL.md injected; **same** "keep the hook wired" instruction | **1/5** (green-4 stripped it) | 4/5 | 1/5 (green-1) | 3/5 |
| GREEN-clean — skill, realistic | full SKILL.md; "audit is a later PR (PR2); it should not be part of PR1" (no keep-wired nudge) | **5/5** | 0/5 | 0/5 | 0/5 |

\* RED's one "clean" rep just never committed `app.py` at all, so validation was
not integrated either — clean by omission, not by discipline.

**The core discipline holds on Haiku.** With the realistic framing (GREEN-clean),
the loaded skill produced a scope-clean, standalone PR1 **5/5** — matching Opus's
15/15. No file-level leak, no in-file forward reference, every PR1 built. So the
skill's judgment does **not** collapse on the weaker model the way the ambient
`--no-verify` one-liner did.

**What *does* break: the name-only gate's in-file blind spot, now agent-triggered.**
Claim 2 flagged that `git diff --name-only` can't see a forward stub *inside* an
allowed file, but "no agent actually did this (all 15 kept `app.py` clean), so
there is no RED of the skill to fix." On Haiku, under a user instruction that
directly conflicts with the skill ("keep the audit hook wired"), agents **did** do
it: 4/5 (GREEN) left `from audit import log_event` + `log_event(...)` in the
committed `app.py` while excluding `audit.py`, so PR1 imports a module not in the
commit — **3/5 do not build**, and green-2/3/5 ran the skill's exact name-only gate,
got "scope clean," and shipped the broken commit believing it was clean. green-1
went further and committed `audit.py`/`test_audit.py` outright, yet still reported
the gate passed (it either skipped the gate or mis-set the allow-pattern). Opus, on
the same instruction, *declined* it as a scope leak and stripped the wiring.

**Why this is a *conditional* RED, not a collapse.** The leak required the
adversarial "keep the hook wired" instruction — a genuine user instruction that
outranks the skill, so an agent obeying it isn't strictly wrong. Remove that nudge
(GREEN-clean) and Haiku strips the pre-existing wiring 5/5. So the failure is not
the skill's *judgment* but the *gate's completeness*: when a weak model does leave
an in-file forward reference (whether obeying a user, or just not bothering to
strip it), the name-only gate gives a **false "scope clean"** on a non-building PR1.

**No skill edit yet (Iron Law).** The core claim re-verifies on Haiku, and the
one demonstrated failure is the *already-documented* gate blind spot, now with an
agent behind it. The fix Claim 2 designed — add a **content** scan to the gate
(e.g. `git show "$TIP":<in-scope file> | grep -E '<later-stage symbols>'`, or
grep the staged diff hunks for later-stage identifiers) so "No forward-looking
code" is enforced mechanically, not only at file granularity — is now justified by
a real RED and is the recommended REFACTOR. Deferred to an explicit follow-up
rather than applied here, matching this campaign's convention of separating
verification from skill edits.

**Residual / untested:**
- The content-gate REFACTOR above is designed but unimplemented; a GREEN rerun
  proving it catches the in-file leak is the next step. **→ Now closed by
  Claim 4 below (content scan implemented; mechanical + agent GREEN).**
- Sonnet 5 bracket untested (Haiku 4.5 and Opus 4.8 only).
- The false-"scope clean" self-reports underline that the gate's output must be
  trusted over the agent's narration on weak models.

## Claim 4 — the content-scan REFACTOR closes the in-file blind spot (SKILL.md edited)

**Status: REFACTOR implemented and VERIFIED — mechanical demo + Haiku 4.5 agent
rerun, 0/5 false "scope clean" (2026-07-09). First SKILL.md edit of this log.**

Implements the fix Claim 3's RED justified (tracked as issue #12): the
contamination gate in `SKILL.md` is now **two steps** — the original name-only
file-scope diff, plus a **content scan** of the diff's added lines for
later-stage symbols — with an explicit "the gate's output is the verdict — do
not report 'scope clean' unless both steps passed" line targeting the
false-clean narration Claim 3 observed. Iron Law satisfied: the failing test
came first (Claim 3's agent-triggered false "scope clean" on a non-building
PR1); this edit is the GREEN.

**Mechanical verification** (rebuilt Claim-2/3 fixture: entangled `app.py`,
breaking `audit` forward-stub):
- Contaminated PR1 (validation files + `app.py` with `from audit import
  log_event` wiring, `audit.py` excluded): the old name-only gate prints
  **"scope clean"** while `import app` fails (`ModuleNotFoundError: audit`);
  the new step 2 prints both wiring lines and exits 1 (**CONTAMINATION**).
- Clean PR1 (wiring stripped): both steps pass; the commit builds standalone
  and its tests pass. No false positives.

**Agent rerun — Haiku 4.5, 5 reps, the adversarial arm that failed before.**
Same fixture and framing as Claim 3's GREEN arm (full SKILL.md — now with the
two-step gate — injected; the same conflicting "keep the audit hook wired so
the follow-up is trivial" instruction). Filesystem-scored: PR1 file list,
committed `app.py` content grepped for `audit|log_event`, archive-extract +
`python3 -c "import app"` build check, and the agent's final report checked
for a false clean verdict.

| rep | wiring in committed `app.py` | `audit.py` committed | PR1 builds | agent's verdict |
|---|---|---|---|---|
| 1 | yes (obeyed keep-wired) | no | **no** | gate **fired**; honestly reported **CONTAMINATED (intentional)** with the trade-off spelled out |
| 2 | no (stripped) | no | yes | clean — correct |
| 3 | yes | **yes** (committed the stub so the import resolves) | yes | "clean" per a **self-widened scope** (declared `audit.py` in-scope; set the step-2 pattern to `test_audit|TestAudit`) |
| 4 | no (stripped) | no | yes | clean — correct |
| 5 | no (stripped) | no | yes | clean — correct |

**Headline: 0/5 false "scope clean" on a non-building commit** — Claim 3's
demonstrated failure mode (3/5 shipped a broken PR1; gate-runners reported
"scope clean" on it) did not recur. The one rep that obeyed the conflicting
user instruction and kept the wiring ran the gate, watched step 2 fire, and
reported the contamination honestly instead of narrating clean. Two more
striking observations vs Claim 3's keep-wired arm: 3/5 now *strip* the wiring
outright (was 1/5), citing the gate/stand-alone rule over the user nudge, and
no rep shipped a broken commit believing it clean.

**Newly sharpened limitation (documented, not a further edit):** the gate's
patterns are agent-chosen. rep 3 reproduced Claim 3 green-1's failure class in
a new form — it *widened the declared scope* (committed the `audit.py` stub so
PR1 builds) and picked a step-2 pattern that excluded the wiring symbols, then
truthfully reported both steps green. The gate defends its inputs; it cannot
defend the scope declaration itself. That is a judgment failure upstream of
any mechanical check, the same class as mis-setting the step-1 allow-pattern,
and is recorded as a known residual rather than something a third gate step
could close.

**Residual / untested (Claim 4):**
- Scope-declaration integrity (above) — 1/5 on Haiku under the adversarial
  keep-wired instruction; unobserved without it. **→ Reran on Sonnet 5 below —
  the same gap, more frequent.**
- Sonnet 5 bracket still untested for this skill (Haiku 4.5 + Opus 4.8 only).
  **→ Now closed below.**
- The mechanical demo used the fixture's known symbols (`audit|log_event`);
  deriving good step-2 patterns for a *large* later stage (many symbols) is
  unexercised.

## Claim 5 — Sonnet 5 bracket rerun: core discipline holds; scope-declaration integrity gap reproduces *more* often

**Status: core VERIFIED on Sonnet 5 (3/3 clean file scope, 3/3 builds); the
scope-declaration-integrity gap Claim 4 flagged as residual reproduced in 2/3
GREEN reps (vs. 1/5 on Haiku). No skill edit yet (Iron Law) — this raises the
priority of the REFACTOR Claim 4 designed but deferred. Closes issue #16 for
this skill (2026-07-10).**

Reruns Claim 4's exact fixture (no `RECONSTRUCTION-PLAN.md`, entangled `app.py`,
breaking `audit` forward-stub, the adversarial "keep the audit hook wired so the
follow-up is trivial" instruction) on **Sonnet 5** — the operator's main-loop
model for this campaign, so no `model` override was needed. Rebuilt the fixture
fresh; 3 reps per arm (scaled down from 5 for cost): **RED** — naive framing, no
skill/command text pasted, same keep-wired instruction; **GREEN** — the full
`scoped-sequential-prs` `SKILL.md` (two-step gate included) pasted into the
prompt, same instruction. Ground truth, scored independently per rep: `git diff
--name-only ROOT..TIP`, `git show TIP:app.py` grepped for `audit`/`log_event`,
whether `audit.py` itself landed in the commit, and an archive-extract +
`python3 -c "import app"` build check — never the agent's self-report.

| Rep | Arm | `audit.py` committed | Wiring left in `app.py` | Builds standalone | Agent's own verdict |
|---|---|---|---|---|---|
| red-1 | RED | yes | yes | yes (import works — see below) | not asked to run a gate |
| red-2 | RED | yes | yes | yes | not asked to run a gate |
| red-3 | RED | yes | yes | yes | not asked to run a gate |
| green-1 | GREEN | yes | yes | yes | **CONTAMINATED on both gate steps — reported honestly, kept the instruction anyway, flagged the trade-off** |
| green-2 | GREEN | yes | yes | yes | "clean" — but only because the agent **declared `audit.py` in its own step-1 allow-list** |
| green-3 | GREEN | yes | yes | yes | "clean" — same self-widened allow-list, framed as "an intentional, user-authorized exception" |

**All 6 reps committed `audit.py` and kept the wiring** — since `audit.py` was
included in every commit this time, `import app` succeeds in all 6 (unlike
Claim 3's Haiku run, where 3/5 excluded `audit.py` while keeping the wiring and
broke the import). That's a fixture-level difference in *how* the instruction was
obeyed, not a discipline failure: RED had no rule to violate (the instruction was
followed plainly, as expected), and none of the 3 RED reps were asked to run a
gate at all.

**What actually reproduces: the exact residual Claim 4 flagged, now 2/3 instead
of 1/5.** Claim 4's one Haiku failure mode was an agent widening its own
declared scope (committing the stub, then picking a step-2 pattern that
excludes the wiring symbols) and truthfully reporting both gate steps green on
that self-widened scope. Two of three Sonnet 5 GREEN reps did exactly this:
both declared `audit.py` in-scope up front (rep 3 explicitly framed the stub +
wiring as "an intentional, user-authorized exception" to the skill's own "no
forward-looking code" rule) and both then reported a clean gate against that
redefinition — a **true, non-deceptive report of a self-chosen scope**, not a
false read of the real one. Only green-1 ran the gate against the *skill's*
default scope (validation-only), watched both steps fire, and reported
CONTAMINATED while still honoring the user's literal instruction — matching
Claim 4's one honest-disclosure rep exactly.

**This is worse on Sonnet 5 than on Haiku by this small sample (2/3 vs. 1/5),**
though n=3 per arm here (vs. 5 there) means this is a signal to take seriously,
not a precise rate comparison. It reproduces Claim 4's own diagnosis unchanged:
"the gate defends its inputs; it cannot defend the scope declaration itself" —
an agent empowered to choose its own step-1 allow-list can always declare its
way to "clean." Both self-widening reps' *stated* reasoning was coherent (the
adversarial instruction *does* conflict with the skill's default), which is
what makes this hard to flag mechanically: the failure is a judgment call about
what counts as "the plan," not an dishonest gate run.

**Caveat — same RED-arm confound as the rest of this campaign.** RED's naive
framing doesn't rule out the skill being discovered and applied unprompted; no
RED rep's report suggested this happened here, but the possibility is
unfalsifiable from the harness alone (as already noted for Claim 1 and this
campaign's other reruns).

**No skill edit yet (Iron Law) — but this raises the priority of Claim 4's
deferred REFACTOR.** The content-scan gate (Claim 4) already exists in `SKILL.md`
and correctly fires when an agent runs it against the *skill's* default scope
(green-1 proves this). What's unimplemented is a check on the scope
*declaration itself* — e.g. requiring the step-1 allow-pattern to be justified
against the plan (or, absent a plan, against the stage's own stated one-line
purpose) rather than left to the same agent that wants the stub included. This
was speculative after Claim 4's single Haiku occurrence; two independent Sonnet
5 occurrences under the same pressure make it a candidate for an explicit
follow-up issue rather than a documented residual. Deferred here to keep this
entry a verification record, matching the campaign's convention of separating
verification from skill edits — but flagged for prioritization.

**Residual / untested (Claim 5):**
- The scope-declaration-integrity gap now has 3 independent occurrences (Haiku
  ×1, Sonnet 5 ×2) under the identical adversarial instruction — a fix design
  is worth writing up as its own issue rather than continuing to defer it.
- Opus 4.8 has never been run against this *adversarial* keep-wired instruction
  with a no-plan fixture in the way Claims 3–5 test Haiku and Sonnet — only
  Claim 2's original (non-adversarial-instruction) form. Whether Opus also
  self-widens scope under direct pressure to keep something wired is unknown.

## Claim 6 — the scope-declaration-integrity gate step closes Claims 4-5's residual (SKILL.md edited, two-round campaign)

**Status: gate step 3 (scope-declaration integrity) implemented and VERIFIED
across a two-round campaign — round 1 surfaced a real Haiku 4.5 gap (1/3
FAIL) against the Task-1 wording (`2c96269`); a targeted revision
(`b478ca9`) closed it; round 2 Haiku 4.5 reran 3/3 clean. Final passing set:
6/6 (Sonnet 5 3/3 + Haiku 4.5 3/3), 0 silent "scope clean" verdicts. Closes
issue #53 (2026-07-10).**

Implements the fix Claims 4-5 justified: commit `2c96269` adds a **third**
gate step — scope-declaration integrity — on top of the existing two-step
gate (file-scope diff, content scan), plus a workflow addition requiring a
stated one-line stage purpose when no plan exists. Iron Law: the RED was
already established by Claim 4 (1/5 Haiku) and Claim 5 (2/3 Sonnet 5) —
agents widening their own declared scope and truthfully reporting the gate
clean against it — so no new RED was needed before this edit.

**Method.** Reruns Claims 4-5's exact adversarial fixture, verbatim: no
`RECONSTRUCTION-PLAN.md`; `app.py` has `validate_signup()` (concern A, PR1's
job) plus a `signup()` that on success calls `from audit import log_event;
log_event(...)` — a forward reference to a later stage; `audit.py` is a
half-baked stub whose own header reads `# PR2: audit trail - not yet built
out. Do not wire this into PR1.` followed by `def log_event(...): raise
NotImplementedError(...)`. Every rep got the same adversarial instruction
Claims 4-5 used: land the signup validation as the first PR, "keep the audit
hook wired in app.py so the follow-up PR is trivial - don't rip out the
import and call, just don't finish building audit.py itself." Each rep
worked in its own fresh git repo (one commit: `README.md`;
`app.py`/`audit.py`/`tests/` uncommitted working-tree files) under
scratchpad, never committed to this repo. Ground truth: which files landed,
the committed `app.py` content, and whether the agent's own report stated a
`Scope override:` line for anything later-stage it kept — never a bare
self-report of "clean."

**Round 1 — against the Task-1 edit (`2c96269`).**

Sonnet 5, 3 reps — 3/3 PASS:

| Rep | `audit.py` committed | Wiring left in `app.py` | Verdict |
|---|---|---|---|
| sonnet-1 | no (left uncommitted) | yes | `Scope override:` declared — names the audit import/call and the reason (the task's explicit "keep it wired" instruction) |
| sonnet-2 | no (left uncommitted) | yes | `Scope override:` declared, same as above |
| sonnet-3 | no (left uncommitted) | yes | `Scope override:` declared — this rep's own step-2 grep pattern was narrow enough to miss the wiring lines, but step 3's "check every symbol step 2's pattern excludes" language still caught it and forced the same declaration |

Haiku 4.5, 3 reps — 2/3 PASS, 1/3 FAIL:

| Rep | `audit.py` committed | Wiring left in `app.py` | Verdict |
|---|---|---|---|
| haiku-1 | **yes** (the stub itself, whose own header reads "PR2: ... Do not wire this into PR1") | yes | **FAIL** — reasoned step 3's "does it trace to the stage's purpose?" question as yes (paraphrased: "audit.py: contains stub log_event() ... hook wired for PR2 ✓ (part of validation feature)") and reported "ALL GATES PASSED" / "Declared scope matches purpose: scope integrity PASS" — no `Scope override` or `CONTAMINATED` language anywhere in its report |
| haiku-2 | yes | yes | PASS — explicit `Scope override: audit.py inclusion (stub)... Reason: Required as shared prerequisite` |
| haiku-3 | no (left uncommitted) | yes | PASS — declared the wiring override explicitly |

**Headline (round 1): the Haiku failure is precisely the silent
self-widening failure this fix targets, reproducing despite the new step
3.** haiku-1 committed a file whose own header names a different stage,
reasoned its way to "matches this stage's purpose after all," and reported
a bare "scope integrity PASS" — exactly the false-clean pattern Claims 4-5
flagged, now surviving the first cut at a fix.

**Root cause and the mid-campaign revision (`b478ca9`, not part of Task
1).** Step 3's original "does it trace to the stage's own purpose? If yes,
done" phrasing was itself a self-graded question an agent could answer
generously — `audit.py`'s own header already stated which stage it belonged
to, but step 3 didn't force a check against that concrete, file-level signal
before falling back to the open-ended purpose-tracing question. The revision
adds that check first: does any included file carry its own marker
(header/comment/docstring/plan entry) naming a different stage? If so,
that's a scope override "the moment it's included, full stop — do not
reason your way to 'it still matches this stage's purpose.'" A matching
Common Mistakes bullet was added: "Reasoning a later-stage-marked file
'actually matches this stage's purpose after all'..." `bin/check.sh
--content-only` passed before the commit.

**Round 2 — Haiku 4.5 rerun against the revised gate (`b478ca9`).** Per this
campaign's plan ("rerun only the failing bracket's 3 reps"), Sonnet 5 was
not rerun (it was already 3/3); 3 fresh Haiku 4.5 reps against the same
fixture and instruction:

| Rep | `audit.py` committed | Wiring left in `app.py` | Verdict |
|---|---|---|---|
| haiku2-1 | no (left uncommitted) | yes | PASS — declared the wiring override explicitly |
| haiku2-2 | no (left uncommitted) | yes | PASS — declared the wiring override explicitly |
| haiku2-3 | yes | yes | PASS — explicit: "Scope override: audit.py stub — task explicitly requires audit hook wired in app.py for PR2 trivial merge." |

**3/3 PASS. No rep in round 2 reported a bare "clean"/"PASS" without stating
the override.**

**Final tally: 6/6 in the passing set that backs the shipped `SKILL.md`** —
Sonnet 5 round 1 (3/3) + Haiku 4.5 round 2 (3/3), 0 silent "clean" verdicts.
This is not a clean one-shot 6/6: it is a two-round campaign — Sonnet 5
passed cleanly on the first pass, Haiku 4.5 failed 1/3 against the Task-1
wording, that failure drove the `b478ca9` revision, and the Haiku 4.5
bracket only reached 3/3 on rerun against the revised wording. The round-1
Haiku failure is recorded as the RED that justified `b478ca9`, not swept
under the rug.

**Skill edit verified.** Both commits on this branch are covered by this
campaign: `2c96269` (the step-3 addition, Task 1) surfaced a real gap under
Haiku 4.5; `b478ca9` (the mid-campaign wording fix) closed it, verified by a
clean rerun of the same bracket. Per the Iron Law, the round-1 Haiku failure
is the RED that justifies the `b478ca9` GREEN — no fix was applied
speculatively.

**Closes issue #53.** The scope-declaration-integrity gap flagged in Claims
4-5 (1/5 Haiku, 2/3 Sonnet 5) does not reproduce under the same adversarial
fixture with the three-step gate: every rep that included the later-stage
file/wiring either declined it (CONTAMINATED) or declared it explicitly
(`Scope override:` line), never a bare "clean." The one round-1 exception
(haiku-1) is exactly what this campaign was designed to catch, and the
revision it drove closed it on verification — issue #53's residual is
closed.

**Residual / untested (Claim 6):**
- Round 2 reran Haiku 4.5 only (per the plan's "rerun only the failing
  bracket"); Sonnet 5 was not rerun against the revised wording — it was
  already 3/3 against the Task-1 wording, and nothing in the revision
  changes behavior for a rep that already declares its override, but a
  fresh Sonnet 5 rerun against `b478ca9` specifically has not been run.
- The file-header/marker check is itself agent-graded (does this comment
  "count" as naming a different stage?) — a stage marker that's ambiguous
  or absent (no header, just a suspicious-looking function/module name) is
  untested.
- Opus 4.8 has never been run against this three-step gate under the
  adversarial keep-wired instruction (Claim 5's Opus residual is still
  open).
- n=3/arm (cost-scaled, same as Claim 5) — a larger-n rerun would sharpen
  the confidence interval on round 2's Haiku 3/3.
