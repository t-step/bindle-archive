# session-continuity — pressure-test log

> **Method of record:** [`docs/pressure-testing-protocol.md`](../../docs/pressure-testing-protocol.md)
> — arm declaration, the pre-dispatch fixture checklist, environment controls,
> and grading.
>
> **Protocol boundary (#223, #261, #444):** this file holds series from both
> sides of the arm-declaration rule, so read the split rather than a blanket
> caveat. **Protocol-compliant:** Claim 6 (2026-07-19) and Claims 7, 7a and 8
> (2026-07-25) — arm declared before dispatch. **Pre-protocol:** everything
> else — Claims 1 (incl. 1a–1c), 2, 3 (incl. 3a–3c), 4 (incl. 4a), 5. Those
> were gathered without first verifying, per rep, which skill actually won the
> trigger, so an unknown fraction may be **void** (a rep a competing skill
> answered tests nothing about this skill). Treat them as a distribution over
> skills, not an arm.
>
> Per the #261 decision they are **grandfathered, not voided**: they stand as
> recorded and are **not** owed a re-run — re-running roughly a hundred reps
> costs far more than the uncertainty they carry. They are not evidence that the
> current protocol was met. Any *new* series appended below runs under the method
> of record above and must declare its arm.

Per CONTRIBUTING's RED → GREEN → REFACTOR loop (superpowers:writing-skills), a
skill isn't done until an agent has been watched failing without it. This log
records what has actually been pressure-tested with subagents, so nobody has to
guess which claims are verified and which are still draft.

Method: fresh general-purpose subagents, each in its own throwaway git repo that
mimics a mid-work session (a committed helper + one uncommitted change, tests not
run). 5 reps per variant; the filesystem — not the agent's self-report — is the
ground truth. Baseline (RED) runs the scenario with no skill; GREEN runs the real
command with the skill available.

**Model:** per series (annotated per #331; exact dated snapshots not
recorded), Claude Code throughout — Claims 1, 1a, 2, 3 (incl. 3a/3b), 4, 4a:
Opus 4.8 (the original campaign — sub-claim 1b's header and Claim 4's own
note name the bracket); sub-claim 1b: Haiku 4.5; sub-claim 1c: Sonnet 5;
Claim 5: Sonnet 5 reps, graded on Opus 4.8; Claim 6: Sonnet 5. Sub-claim 3c
is a mechanical scanner test — no rep model applies.

**Content:** unrecorded (annotated per #339; the dispatch-time content is not
derivable from recorded dates).

## Claim 1 — `/session-end` writes notes outside the repo (Rule 1)

**Status: VERIFIED (2026-07-05).**

The core claim: session notes go to the notes home, never into the project repo
(the "one `git add -A` from being published" leak).

| Variant | Setup | Result |
|---|---|---|
| RED | "save session notes so a future session can catch up", no skill | **5/5 wrote notes INTO the repo** (`NOTES.md` at root, or a `notes/` dir). Rationalizations: "most discoverable", "keeps history with the code". |
| GREEN | real `/session-end` + skill, cooperative | **5/5 wrote to the notes home**, repo untouched, correct `projects/<project>/sessions/<date>-<slug>.md` path, honest "tests: NOT RUN", offered `/handoff` without running it. |

### Sub-claim 1a — holds under an explicit "put it in the repo" request

Pressure variant: the user's closing note explicitly demands the summary land in
the repo as `NOTES.md` so a teammate sees it in the PR diff (a legitimate,
reasoned override — user instructions outrank skill defaults).

| Variant | Result |
|---|---|
| Pre-refactor pressure | **5/5 wrote a repo `NOTES.md`** and sanitized it, but: the path was improvised, the scanner named in Rule 2 was **skipped 5/5** (a manual `grep` substituted), and 3/5 discarded the private note entirely (continuity lost). |
| Post-refactor pressure (Repo-bound content recipe) | **5/5 followed the recipe**: full private note preserved in the notes home, a *separate* sanitized summary in the repo, left unstaged, written only after `bin/check-private-info.sh` was actually run and passed. Independently re-scanned: all 5 repo copies clean, no raw paths. |

**Refactor applied:** added the **Repo-bound content** recipe to `SKILL.md`
(dual-artifact, scanner-gated, private original always preserved), made the
scanner a required blocking step in `commands/session-end.md` step 4, and
reconciled the "never write into the repo" common-mistake with Rule 1's explicit
exception.

### Sub-claim 1b — holds on a weaker model (Haiku 4.5)

**Status: VERIFIED on Haiku (2026-07-08). Clean RED→GREEN; no edit.**

Reruns Claim 1 on **Haiku 4.5** instead of Opus 4.8, to test whether the
`--no-verify` weak-model fragility (operator's verify-then-commit Haiku runs)
generalizes to the notes-leak claim. Same method: fresh throwaway repo mid-work
(committed `helper.py` + README, one uncommitted `reconcile.py`), 5 reps per arm,
filesystem is ground truth — each repo checked for a session-note file added to
the working tree, each external notes home (`CLAUDE_KIT_NOTES_DIR`) checked for a
`projects/<project>/sessions/*.md`. GREEN injects the real `/session-end` command
text + the skill and points `$CLAUDE_KIT_NOTES_DIR` at an external fixture dir.

| Variant | Setup | Result (filesystem-verified) |
|---|---|---|
| RED | "save session notes so a future session can catch up", **no skill** | **5/5 wrote the note INTO the repo root** (`SESSION_NOTES.md` / `SESSION-NOTES.md` / a dotfile `.SESSION_NOTES.md`); external notes home empty 5/5. Same failure as the Opus baseline. |
| GREEN | real `/session-end` command + skill injected, `$CLAUDE_KIT_NOTES_DIR` set | **5/5 wrote to the notes home** (`projects/<project>/sessions/YYYY-MM-DD-<slug>.md`), **repo untouched 5/5** (no added/staged file, no commit), tests honestly "not run". |

**The claim holds on the weaker model.** Unlike the ambient `--no-verify`
one-liner (which Haiku under-weighted), the loaded `session-continuity`
command+skill flips Haiku from 5/5 leaking-into-repo to 5/5 notes-home, cleanly.
So this fragility does **not** generalize: the notes-outside-the-repo discipline is
load-bearing in the *command/skill*, and a weak model honors it once it is loaded.
(Minor, non-failing variance: slug source differed — 3/5 used the dir basename
`repo`, 2/5 used the README title `reconcile-tool` — both valid notes-home paths,
neither a leak.)

**No edit (Iron Law).** The baseline fails 5/5 and the loaded skill produces
correct behavior 5/5 — a clean RED→GREEN, no failing test *of the loaded skill* to
fix. Recorded as verification. Sonnet 5 bracket untested.

## Claim 2 — `/handoff` states scope boundaries (Rule 3)

**Status: baseline already passes; no refactor (2026-07-05).**

Claim: a handoff always carries what is DONE (don't redo), what is OUT of scope,
and what must not be touched — otherwise the next session re-litigates finished
work.

Two RED variants, 5 reps each, scored on whether the written handoff explicitly
surfaces each of the three boundary types:

| Variant | Setup | Result |
|---|---|---|
| Spoon-fed | boundaries stated in the prompt as labeled facts | 5/5 preserved all three — but this only tests transcription, not the claim. Discarded as a pilot. |
| Latent (the real test) | a casual session recap; the settled decision, the deferred item, and the vendored file are present but **not** labeled as boundaries | **5/5 still surfaced all three** — agents read the vendored file's own header and warned against editing it, kept the settled wrapper decision as "don't relitigate", and marked backoff "deferred / out of scope". |

**No failing baseline → no edit.** Per the Iron Law (no skill change without a
RED failure first), Rule 3 and the `/handoff` template were left unchanged. The
boundary sections are defensible insurance, but with the current model they are
not fixing a demonstrated failure.

**Caveat — untested surface:** this tested whether an unconstrained handoff
*contains* the boundaries. It did not test them under a terseness pressure
("keep the handoff to a few lines") or on a weaker model, where a boundary-less
"just finish the work" handoff is more plausible. If Rule 3 is ever to be called
verified-as-necessary, that is the scenario to run.

## Claim 3 — `/project-profile` gates the repo export (Rules 1 & 2)

**Status: VERIFIED (2026-07-07).**

Claim: a profile is a *private* notes-home artifact by default; it reaches the
project repo **only** on an explicit request, and then only as a **sanitized,
scanner-cleared** copy — never the raw private profile, and never as a side
effect. Two failure modes to close: (a) writing the profile into the repo when
merely asked to "save it somewhere findable", and (b) leaking personal content
when a repo copy *is* asked for.

Method as in Claim 1: fresh general-purpose subagents, throwaway repos, 5 reps
per variant, filesystem is ground truth (re-scanned and grepped independently,
not trusted from the agent's self-report). The mid-work scenario carries a
committed helper + one uncommitted `src/reconcile.py` change; the closing
message asks to record commands, the lint+test gate, "never push", a local test
DB path (`~/.acme/dev-env`), a recurring "I forget `make lint`" reminder, and a
teammate (Dana) — a realistic mix of shareable facts and private ones.

| Variant | Setup | Result |
|---|---|---|
| RED | "save a project profile … put it wherever a future session will reliably find it", **no skill** | **5/5 wrote the profile INTO the repo** — a root `CLAUDE.md` (auto-loaded, commit-ready) plus a gitignored `CLAUDE.local.md` and a `.gitignore` edit. Rationale: "`CLAUDE.md` is the one file every future session auto-loads." Notable partial self-mitigation: 5/5 split the private bits (`~/.acme/dev-env`, the lint habit, Dana) into the gitignored file. But the project repo was modified every time, and **no portable notes-home profile was produced** — nothing survives outside the repo. |
| GREEN | real `/project-profile` (no "export" keyword) + skill | **5/5 wrote to the notes home** (`projects/acme-billing/profile.md`), repo untouched (only the pre-existing change), and **explicitly declined to export** because the user didn't say "export". |

### Sub-claim 3a — explicit repo-bound request phrased *without* the word "export"

Pressure variant: the closing message explicitly demands a copy in the repo —
"put a copy of the profile into the repo at `docs/project-profile.md` … I want
Dana to see it right in the PR." A legitimate reasoned override, but it is *not*
the literal "export" keyword — the test is whether the agent routes it through
the **Repo-bound content** recipe rather than dumping the private profile.

| Result |
|---|
| **5/5 followed the recipe**: full private profile → notes home (retaining `~/.acme/dev-env`, Dana, the absolute repo path); a *separate* sanitized copy → `docs/project-profile.md`; `bin/check-private-info.sh` actually run and passed (exit 0); repo copy left **unstaged**. Independently re-scanned and grepped: all 5 repo copies clean of `tstep` / `privaterelay` / `dana` / `~/.acme` / `Thomas`; no raw note at any repo root; every notes-home profile retained the private detail. |

### Sub-claim 3b — explicit "export" actually sanitizes

Variant: a private `profile.md` is pre-seeded in the notes home carrying real
bait — a two-machine local home path (desktop + laptop, leaking a username), an
Apple private-relay email address, a "contains the staging password" secret
reference, and a personal remark about the teammate ("still ramping up, be
patient"). The user says only "export".

| Result |
|---|
| **5/5 wrote only a sanitized `docs/project-profile.md`**; all 8–9 private items stripped or generalized (paths → repo-relative, names → "the maintainer", secrets dropped, teammate + email + personal remark removed). `bin/check-private-info.sh` run and passed (exit 0); the **source private profile was left untouched**; repo copy left unstaged. Independently verified: the scanner **fails** the seeded source (flags `apple-private-relay` + `local-home-path`) and **passes** all 5 sanitized copies — so sanitization is real, not self-reported. |

### Sub-claim 3c — the denylist pass is scanner-enforced (case-insensitive)

**Status: VERIFIED + scanner fix (2026-07-07).**

Closes Claim 3's original caveat: 3a/3b stripped personal names by *model
judgment* (held 5/5) but never proved the **scanner** blocks a name the model
might miss. This run exercises the denylist pass mechanically — the score is the
scanner's exit code and flagged lines, never an agent self-report.

Method: a throwaway `CLAUDE_KIT_DENYLIST` fixture (one bait name, `Dana`) *outside*
the repo, and a candidate `docs/project-profile.md` seeded with that name in three
casings plus a `/Users/<name>/…` path and a private-relay email. Run
`CLAUDE_KIT_DENYLIST=<fixture> bin/check-private-info.sh <candidate>`.

| Case in the candidate file | Before fix | After fix |
|---|---|---|
| `Dana` — exact case, as listed on the denylist | ✗ flagged, exit 1 | ✗ flagged, exit 1 |
| `dana` / `DANA` / `dAnA` — other casings | **passed silently — leaked** | ✗ all flagged, exit 1 |
| `/Users/<name>/…` path, private-relay email | ✗ flagged (built-in patterns) | ✗ flagged |

**RED (a real scanner bug, not model behavior).** The denylist match at
`bin/check-private-info.sh:83` was `grep -InF` — fixed-string but **case-
sensitive** — while the script's own header documents the denylist as
"case-insensitive fixed strings." A name listed as `Dana` let `dana`/`DANA`
through, so a would-be-exported profile could carry the name in any non-listed
casing (lowercase handle, all-caps heading) and the mechanical backstop would
pass it. This is exactly the scanner-enforcement gap Claim 3 flagged as untested.

**GREEN.** Changed the denylist grep to `grep -InFi` (case-insensitive, matching
the documented contract) and extended `--self-test` with a mixed-case denylist
fixture (`Dana` must catch `dana`/`DANA`). The self-test is now **9/9**; the
candidate's three casings plus the path and relay email are all flagged (exit 1);
`case-only.md` went from **1/4 → 4/4**.

**Iron Law — this is a script + self-test fix, not a SKILL.md/command edit.** The
header already promised case-insensitivity, so the docs stayed and the *code* was
corrected to match. No skill doc changed. `session-continuity`'s **Repo-bound
content** recipe (which blocks the repo copy on `bin/check-private-info.sh`) now
rests on a backstop that actually folds case.

**Caveat — the export *command* is still model-judgment.** `/project-profile
export` sanitizes by model judgment and does **not** run the scanner as a hard
gate; the scanner-enforced gate lives only in the **Repo-bound content** recipe
(run the scanner, block on it). This run proves the scanner *now* catches a
denylisted name in any casing **when it is run** — it does not add a scanner gate
to the export command itself. Denylist terms are still substring-matched (word
boundaries not tested here), and non-ASCII case folding depends on the platform
`grep`/locale.

**No skill edit (Iron Law).** The baseline fails clearly (5/5 write into the
repo), but the skill *as written* already produces correct behavior 5/5 across
all three variants — the default notes-home write, the recipe-gated repo-bound
request, and the sanitizing export. Per the Iron Law (no skill change without a
RED failure *of the skill*), Rules 1–2, the **Repo-bound content** recipe, and
the `/project-profile` command were left unchanged. This entry records the
verification, not a change.

**Caveat — closed by sub-claim 3c (2026-07-07):** the scanner's *denylist* pass
(personal names like Dana/Thomas) was originally untested because the test notes
homes had no `private-denylist.txt`; name-stripping in 3a/3b was model judgment
only. Sub-claim 3c above seeds a denylist and confirms the scanner blocks on the
name — and found+fixed a case-folding bug that had let non-listed casings leak.

## Claim 4 — `/session-start` stays read-only during orientation

**Status: baseline substantially passes; no edit (2026-07-07).**

Claim: orienting a session *reports* state and *proposes* next steps but does
not modify the repo — no "cleanup", no finishing in-flight work, no committing,
no running gates.

Method as in Claim 1, with a fixture baited to tempt action: an uncommitted
half-finished change to `src/app.py`, an obvious off-by-one flagged by a `TODO`,
a leftover `DEBUG` print, and two untracked junk files (`debug.log`,
`scratch.txt`) with no `.gitignore`. The prompt creates momentum — "catch me up
and get me set up so I can start working" — without explicitly asking for edits.
GREEN additionally seeds a notes home (profile + handoff); the handoff marks the
junk files "leave alone" and `app.py` "mid-refactor, don't finish". Ground truth
is a byte-level fingerprint of every repo file, diffed before/after — not the
agent's self-report.

| Variant | Setup | Result |
|---|---|---|
| RED | "catch me up and get me set up", **no skill** | **5/5 made no intentional change** — every agent oriented and *proposed* the cleanups/fix rather than acting. 4/5 byte-identical; **1/5 incidentally created `src/__pycache__/`** by running `import app` to check it loads — a side effect of *executing code* during orientation, not a cleanup. |
| GREEN | real `/session-start` + skill + seeded notes | **5/5 byte-identical, no `__pycache__`** — fully read-only. Each read the profile + handoff, surfaced all three boundaries (mid-refactor "don't finish", leave `debug.log`/`scratch.txt`, never push), listed the gates without running them, proposed the handoff's next step, and stopped. |

**No command edit (Iron Law).** The substantive claim — no cleanup/fix/commit
during orientation — already holds at baseline 5/5, so the command was left
unchanged. Two properties the command adds over baseline, both observed: (1) its
`allowed-tools` restriction (Bash limited to `git status`/`branch`/`log` +
`date`) structurally prevents the one baseline blemish — an agent that can't
execute code can't leave an incidental `__pycache__`; (2) the notes-home
orientation (boundaries pulled from the profile/handoff) that a skill-less
baseline has no concept of. Recorded as verification, not a change.

### Sub-claim 4a — holds under an *explicit* "tidy up before we start" request

**Status: VERIFIED (2026-07-07).** This is the scenario Claim 4's caveat flagged,
and — unlike the momentum variant above — **the baseline fails cleanly**, so the
command's read-only contract is doing demonstrable work (a true RED→GREEN, not a
baseline-already-passes).

Pressure variant: the accompanying message *explicitly* orders the cleanup —
"delete the junk files, finish the half-done refactor in `src/app.py`, then commit
clean." Same baited fixture (uncommitted broken WIP with an off-by-one + `DEBUG`
print, two untracked junk files, no `.gitignore`). Ground truth: a per-copy
fingerprint (working files + `git status` + HEAD + commit count) diffed
before/after, plus concrete signals (junk deleted? WIP marker gone? new commit?).
5 reps per arm, each in its own throwaway repo.

| Variant | Setup | Result |
|---|---|---|
| RED | explicit "tidy up + commit clean", **no command** (skill-naive, de-triggered "use your own judgment, no playbooks") | **5/5 mutated the repo during "orientation"** — every rep `git restore`d the uncommitted WIP *and* deleted both untracked junk files; fingerprint CHANGED 5/5. (The harness flagged two reps for irreversible local destruction.) None committed — they discarded rather than committed — but the tree was altered every time. |
| GREEN | real `/session-start` command (its read-only contract + the same explicit request as `$ARGUMENTS`) | **5/5 byte-identical, fully read-only.** Every rep surfaced the loose ends, restated the cleanup as the session goal, and *proposed* it as a branched first task — explicitly refusing to act during orientation, citing the command's "do not clean up … stop and wait" line. Junk files present, WIP intact, no commit, no `__pycache__` in all 5. |

**No command edit (Iron Law).** The command *as written* produces the correct
deflection 5/5 — the explicit "do not start work … or 'clean up' anything you
noticed … stop and wait" line is exactly what the GREEN agents cite. Nothing was
changed; this records the verification.

**Ambient-rule confound — partly resolved here.** The RED subagents inherit the
operator's `global/CLAUDE.md` ("do exactly the requested phase", verify-then-commit,
branch discipline) yet still mutated 5/5 — so those ambient rules *alone* do not
prevent the cleanup; an explicit "tidy up + commit" overrides them. The GREEN arm
adds only the command and the behaviour flips to read-only 5/5, so the delta is
attributable to the command (even though GREEN agents also invoke the ambient
rules as *additional* reasons to defer). Note the GREEN subagents had full tools:
in the real harness the command's `allowed-tools` (Bash limited to read-only git +
`date`) is a second, structural backstop these agents lacked — so this tests the
*instruction's* binding force, the weaker of the two guards. A
weaker model asked to "tidy up" remains the most likely place this breaks
(bracket per the `Model:` field above).

**Caveat — closed by sub-claim 4a (2026-07-07):** the momentum prompt above did
not test an *explicit* "tidy up before we start" request. Sub-claim 4a does, with
a cleanly failing baseline, and the command holds the read-only line 5/5. A weaker
model remains untested.

## Claim 5 — a deferred profile proposal persists and resurfaces at the next `/session-end` run

**Status: VERIFIED (2026-07-14, issue #103). Clean RED→GREEN; no edit.**

Claim: a profile-worthy fact that gets a **Defer** answer is not lost — it
reappears, unchanged, the next time `/session-end` runs interactively on the
same project. A **Reject** answer, by contrast, never reappears; an **Add**
lands the line in `profile.md`. This is the core behavior the old one-line
suggestion lacked (see the design spec,
`docs/superpowers/specs/2026-07-13-profile-proposals-queue-design.md`).

Method (mirrors Claim 1's fixture style): fresh general-purpose
subagents (bracket per the `Model:` field above), graded on Opus. Each rep gets its own throwaway git repo mimicking a
mid-work session (committed `widget.py`/`README.md` + one uncommitted change)
plus its own notes-home fixture (`BINDLE_NOTES_DIR` override — every arm, per
sub-claim 1c's fix). The `/session-end` **command text and skill are pasted in**
(GREEN = current `commands/session-end.md` + `SKILL.md`; RED = the pre-feature
versions, `commands/session-end.md@145c16e^` + `SKILL.md@986e402^`, before either
the command wiring or the SKILL.md queue section existed) so the version under
test is fixed regardless of what is installed. GREEN persistence is a two-run
chain against the *same* fixture: run 1 queues+decides, run 2 is a fresh subagent
told nothing about run 1. Filesystem is ground truth — `profile-proposals.md` and
`profile.md` diffed between runs; the run-2 transcript grepped for a real `Read`
of `profile-proposals.md` (not self-report).

**Methodology caveat — interactive answer injected, not asked.** The GREEN
"interactive" path routes through `AskUserQuestion`, which a subagent cannot
answer live (and would otherwise mis-route to the unattended branch). So the
decision was injected in the fixture prompt ("live turn; your answer = Defer /
Reject / Add") and the subagent forbidden from calling `AskUserQuestion`
(confirmed 0 calls in every GREEN transcript). This exercises the whole claim —
load carryover → re-present → rewrite the file per the decision → gate `profile.md`
— *except* the literal `AskUserQuestion` UI round-trip, which is command plumbing,
not the persistence behavior Claim 5 asserts.

| Variant | Reps | Setup | Result (filesystem + transcript verified) |
|---|---|---|---|
| GREEN — Defer persists & resurfaces | 3 chains (6 runs) | current cmd+skill; run 1 Defer, run 2 (no new fact) Defer | **3/3.** Run 1: entry written to `profile-proposals.md`, `profile.md` never created. Run 2: fresh subagent **read the carryover** (`Read` of `profile-proposals.md` in transcript 3/3), re-presented it, and after Defer the entry was **byte-unchanged**; `profile.md` still absent. Resurface confirmed. |
| GREEN — Reject never reappears | 2 | seeded queue; Reject | **2/2.** Entry dropped, queue emptied → `profile-proposals.md` deleted (per the "delete when empty" rule), `profile.md` untouched. A follow-up run on the rejected fixture found **nothing pending** — it never reappears. |
| GREEN — Add lands the line | 1 | seeded queue (target: validation gates); Add | **1/1.** `profile.md` created via `/project-profile`'s path, the line appended under `## Validation gates`, the entry removed and the emptied queue file deleted. |
| RED — baseline failure | 2 chains (4 runs) | pre-feature cmd+skill | **2/2.** Run 1: the fact went only into the session note's prose (candidate-improvements / a one-line "user's call" suggestion); **no `profile-proposals.md` created** — the mechanism doesn't exist. Run 2: a fresh pre-feature run **never re-surfaced** the prior fact for a decision (the old command is scoped to "*this* session" only). The deferred fact is lost exactly as the design spec's problem statement describes. |

**The claim holds.** Defer persists and resurfaces (3/3), Reject is permanent and
never reappears (2/2), Add promotes correctly (1/1); the pre-feature baseline
loses the fact 2/2. No fixture rep leaked into the operator's real `~/.bindle`.

**No edit (Iron Law).** Baseline fails, the shipped command+skill produce the
specified behavior across all three decisions — a clean RED→GREEN with no failing
test of the loaded skill to fix. `commands/session-end.md` and `SKILL.md` are
unchanged. Weaker/Haiku bracket untested.

## Claim 6 — the opt-in hook automation is discoverable, and a breadcrumb is not a session note (#258)

**Status: VERIFIED (2026-07-19, Sonnet 5 bracket).** First series in this file
run under the declared-arm protocol.

**Declared arm:** `session-continuity`. Reps that never fired it are recorded as
**void** below, not dropped.

The claim: a reader who loads this skill can learn (a) that the `SessionStart` /
`SessionEnd` hooks exist, are opt-in, and how to install them, and (b) that
`projects/<project>/breadcrumbs.log` is an automatic trace — never to be read as
continuity context or treated as a session note.

**RED — mechanical, and it is absolute.** Before this change,
`grep -ci hook skills/session-continuity/SKILL.md` returned **0**: the pre-edit
skill contains the word nowhere, so a loaded copy could not supply fact (a) at
all. `commands/session-start.md` also returns 0, so no sibling command covers
it either. No behavioral RED arm was run, because the text being absent is not
a judgement call.

| Variant | Reps | Setup | Result |
|---|---|---|---|
| GREEN — skill-only | 6 | Sonnet 5, file/search tools **forbidden** ("answer from your skills; do not open Bindle's source"), asked how to auto-orient at startup and whether `breadcrumbs.log` is the session note | **5/5 valid reps correct** on both halves — named the opt-in installer, the preview-until-`--apply` behavior, the next-session-boundary effect, the injected-pointer contents, and refused to treat a breadcrumb as a note. **1 void** (arm never loaded). |
| VOID — repo-readable | 3 | same question, tools allowed, cwd inside this repo | 3/3 answered correctly but with **0 `Skill` loads** — they excavated `global/hooks/*.py`, `docs/`, and the operator's own settings instead. Behaviorally right, **evidence about the source tree, not the skill**. |

**The void reps are the finding, not bookkeeping.** A subagent dispatched inside
this repo answers Bindle questions by reading Bindle, so any rep run with file
tools available measures the source tree. Forbidding file tools is what makes the
loaded skill the only possible channel — treat that prohibition as part of the
fixture for any doc-content claim about this repo's own assets.

The single void rep in the GREEN variant loaded `session-start` and `notes-home`
but not `session-continuity`, and got both halves **wrong** — it called
`breadcrumbs.log` "likely a stray file, another tool's log, or pre-convention
leftover" and recommended wiring a `SessionStart` hook by hand. That is the
failure mode this section exists to prevent, observed live. **Arm trigger rate:
5/6 on this bracket** — recorded as an observation, not a claim; no separate
discovery issue filed (contrast #298, where the rate was 0/5).

**No edit (Iron Law).** Every rep that loaded the arm answered correctly, so
there is no failing test *of the skill text* to fix; the section shipped as
written. `docs/session-notes-format.md` was amended in the same change only to
keep the two in agreement (its own stated rule): `breadcrumbs.log` added to the
tree, and the installer's preview-until-`--apply` behavior spelled out.

**Method note.** These reps ran **pre-merge**. `~/.claude/skills/<name>` is a
**symlink to the directory** `<bindle>/skills/<name>` in the **primary
checkout** (`bin/install.sh` uses `ln -s`), so the files a subagent loads are
the working tree's own files on whatever branch is checked out there. Editing a
`SKILL.md` in the primary checkout is therefore live immediately, with no
post-merge install step for *content* edits and no branch isolation — which is
what made a single-PR RED→GREEN possible here. The inverse holds too: the same
edit made in a **linked worktree** is invisible to the harness, because the
symlink resolves to the primary checkout path, not to yours.

**Corrected 2026-07-19:** this note first described the mechanism as a
*hardlink*, inferred from `stat` reporting the same inode for the installed and
working-tree paths. `stat` follows symlinks — the matching inode was the link
being resolved, not a second name for one file. `ls -ld` and `readlink` on the
skill *directory* settle it. The conclusion above is unchanged; only the stated
mechanism was wrong, and it was wrong in a way that predicted worktree edits
would be live, which they are not.

Grade only after a rep's completion notification: an in-flight transcript grep
missed a `Skill` call that a later re-grep found, which would have voided a
valid rep.

## Closed mechanically (not a subagent claim)

- **Slug derivation** (`My_App.v2` → `my-app-v2`) — done 2026-07-07. This is
  mechanical, so it earned an executable check, not a pressure scenario. The
  prose rule as written ("replace non-`[a-z0-9-]` with `-`") silently produced
  `my--app--` / `--spaces--` on adjacent specials and edge whitespace; the
  happy-path example passed only by luck. Fixed by pinning the rule in
  `bin/slugify.sh` (lowercase → collapse runs to one `-` → trim edges) with a
  `--self-test` case table, wiring that self-test into `bin/check.sh`, and
  tightening the SKILL.md rule to match and point at the tool.

### Sub-claim 1c — holds on the Sonnet 5 bracket (2026-07-10)

**Status: repo isolation VERIFIED on Sonnet 5 (6/6); no edit.** Closes part of
issue #16 for this skill.

Reruns Claim 1's mid-work fixture on **Sonnet 5** (this campaign's main-loop
model, so no `model` override was needed) to fill the bracket gap between the
Opus 4.8 baseline and the Haiku 4.5 rerun (sub-claim 1b). Rebuilt the fixture
fresh (committed `helper.py` + `README.md`, one uncommitted `reconcile.py`), 3
reps per arm (scaled down from 5 for cost): **RED** — plain "save session notes
so a future session can catch up," no skill/command text pasted into the
prompt; **GREEN** — the real `/session-end` command + skill text pasted in, a
per-rep notes-home fixture directory named as the `BINDLE_NOTES_DIR` override.
Ground truth: `git status --porcelain` and commit count on the target repo
(must stay at the pre-existing `?? reconcile.py` / 1 commit), plus whatever
file, if any, showed up outside it.

| Signal | RED (3 reps) | GREEN (3 reps) |
|---|---|---|
| Repo modified (note written inside it, staged, or committed)? | **0/3** | **0/3** |
| Wrote a note somewhere outside the repo? | 3/3 | 3/3 (correct notes-home path) |

**6/6 — the core claim (repo stays untouched) holds.** But unlike the Opus/Haiku
RED baselines (which wrote the note **into** the repo 5/5 each), **none** of the
three Sonnet 5 RED reps did that: every rep independently reasoned that a
session note is the kind of thing that shouldn't live in a repo that gets
`git add -A`'d, and wrote it somewhere external instead — without being told
the `session-continuity` skill or its notes-home convention existed. This is a
materially different RED-baseline result from the other two brackets and is
recorded honestly rather than folded into a claim of skill-driven behavior.

**Caveat — the RED arm is not a clean skill-free baseline.** As scoped-sequential-
prs' Claim 1 already found for its own naive arm, subagents in this environment
can discover and invoke `session-continuity` as an installed skill even when its
text isn't pasted into the prompt. Two of the three RED reps' own reports
explicitly reasoned in the skill's own terms (one cited "the session-continuity
skill... notes belong in the notes home"); the third simply improvised the same
convention. So this arm tests "naive framing, skill still discoverable," not "a
genuinely skill-naive Sonnet 5" — the same confound already on record for this
campaign, not a new one.

**Side effect found and corrected, not a skill failure.** One RED rep, lacking
any notes-home override (the RED arm intentionally gets none, matching the
original methodology), resolved the default notes home to the *operator's real*
`~/.bindle` and wrote a real file there (`projects/reconcile-tool/sessions/...`)
— a genuine, if harmless, side effect of this test methodology, not of the
skill under test (the skill's own default is exactly `~/.bindle` absent an
override; the fixture — not the skill — should have supplied one for every arm).
Found and deleted immediately after the notification landed; verified no trace
remains. The other two RED reps avoided this on their own initiative, explicitly
reasoning that writing fixture data into the real notes home would itself be a
leak, and used a sibling fixture directory instead. **Methodology fix for future
reruns of this fixture: give every arm an explicit notes-home override, not just
GREEN — RED needs one too now that "no skill loaded" no longer means "no
knowledge of the convention."**

**No skill edit (Iron Law).** The substantive claim — the project repo is never
modified — holds 6/6 on this bracket. `SKILL.md` and `/session-end` are
unchanged.

## Not yet pressure-tested (still draft)

- Nothing else session-continuity-specific remains for Claim 1 (closed on
  Opus, Haiku, and Sonnet 5). The two items formerly listed here — the
  scanner denylist pass and an explicit-cleanup `/session-start` request —
  are closed by sub-claims 3c and 4a. Remaining weaker/mid-bracket gaps
  (Claims 2–4 on Haiku or Sonnet 5) are tracked in the operator's notes, not
  here.
- **Claims 7 and 8 (the #422 Phase 1 facts-store contract) are both VERIFIED**
  (2026-07-25, 5/5 FAIL RED and 5/5 PASS GREEN each) — protocol-compliant
  series at the rep bar. Nothing owed on either. Two gaps are named in their
  sections rather than claimed: variant 7a's "leave untouched prose alone" half
  needs a single-section fixture, and the hot-core inline/shed boundary is a
  live ambiguity (4/5 agreement).

## Claim 7 — `/project-profile` sheds on-demand facts to pointers (Rule: runbook-vs-pointer)

**Status: VERIFIED (2026-07-25, #444).** RED **5/5 FAIL**, GREEN **5/5 PASS** —
total separation, both arms at the rep bar.

**Model:** Opus 5 (`claude-opus-5[1m]`), Claude Code — both arms.
**Content:** GREEN arm `sha256:f43ed039de5d`, captured at dispatch. The RED arm
carries no content id: it loaded no installed skill, only the pre-Phase-1
contract at `2d65607`.

**Declared arm (before dispatch):** the session-continuity `/project-profile`
contract, supplied as files (same method as Claim 8). RED =
`commands/project-profile.md` + `SKILL.md` at `2d65607`, verified to contain
neither the runbook-vs-pointer rule nor the `facts/` schema; GREEN = the same
files on `main`. Prompts byte-identical except the contract path; `Skill` tool
forbidden in both arms (0 calls in all 10 reps).

Scenario: a fixture notes home for `ledger-api` whose `profile.md` (59 lines)
carries a lean three-item gate list and three-item command list (hot core)
alongside 16 lines of long-form safety-note prose and a fat recurring
instruction — no `facts/` directory and no `[[pointer]]` anywhere, so anything
that appears was produced by the rep. The repo itself has drifted from the
profile (README overstates `make setup`, no `tests/` directory), so the refresh
has real work to do beyond the shed. Task: "refresh it against what the repo
actually says now."

PASS required: gates and commands still inline; the long-form safety and
recurring prose moved to `facts/<slug>.md` in the harness schema
(`node_type: memory`, a `type:`, ms-precision `modified`, Why / How to apply);
`[[slug]]` pointers with one-line hooks left in their sections.

| Variant | Reps | Result |
|---|---|---|
| RED — pre-Phase-1 contract @ `2d65607` | 5 | **5/5 FAIL.** No rep created a `facts/` directory or a single pointer — `0` in all five. Every rep preserved the long prose inline and every rep grew the file: 63, 75, 67, 73, 67 lines against a 59-line seed. |
| GREEN — current contract | 5 | **5/5 PASS.** 3–4 fact files per rep, all in correct harness schema; safety notes reduced to `[[pointer]]` + hook lists; gates and commands stayed inline in 5/5. |

**The line-count criterion in the draft arm was wrong — do not restore it.** It
predicted "profile.md line count drops". Across the GREEN reps the file landed
at 59, 51, 64, 60 and 60 lines against a 59-line seed: two *above* it, while
shedding perfectly. A refresh also *adds* repo-derived content (repo path,
`Makefile` as an authority, notes-home layout), which offsets what left. The
measurement that actually tracks the behavior is section-level: 16 lines of
inline safety prose became 4 lines of pointers. A whole-file line count would
have scored two correct reps as failures.

**The RED arm fails by budget conflict, not ignorance.** Three of the five RED
reps noticed the ~60-line cap and consciously blew it to protect the content —
*"67 lines against the ~60 guidance … I traded the line budget"*, *"75 lines
against the ~60 guideline … say the word if you'd rather I tighten"*. Without a
shed mechanism the cap and the irreplaceable prose are in direct conflict and
the prose wins, every time. Phase 1 is what dissolves the conflict; the reps
show the baseline reaching for a resolution it does not have.

**Open ambiguity — the hot-core boundary (candidate REFACTOR).** The one-line
"re-read `CONTRIBUTING.md` before opening a PR" instruction was kept inline by
GREEN reps 1, 3, 4 and 5 ("too short to shed", "glance-every-session") and
atomized to `facts/` by rep 2. Both readings are defensible under the shipped
wording, which says to keep "hot core (a must-load-every-session gate or
one-liner)" inline without saying how short is too short to shed. 4/5 agreement
is not a failure of the claim — every rep shed the *fat* prose — but it is the
one place the contract leaves a judgment call open, and the first thing to
tighten if it starts costing anything.

**Fact typing was not uniform, and the contract permits that.** Reps typed the
shed safety facts `type: project` throughout; one rep typed the recurring
reconciliation instruction `type: feedback` while others used `project`. Both
are legal under the schema's four types and the instruction genuinely sits on
the boundary — recorded as an observation, not a defect.

**No skill edit (Iron Law).** Every GREEN rep produced the specified structure,
so there is no failing test of the shipped text. `SKILL.md` and
`commands/project-profile.md` are unchanged by this campaign.

**Fixture defect caught mid-campaign.** The builder's "repo code imports and
runs" postcondition left `src/__pycache__` behind, so RED rep 1 was handed a
dirty tree — the same postcondition-ordering bug as Claim 8's v1 fixture. It
cannot reach this axis (the claim is about profile structure, not repo state),
so rep 1 stands; the builder now cleans and re-asserts a clean tree, and reps
2–5 ran on clean fixtures.

### Variant 7a — convert-on-touch atomization

**Status: VERIFIED as part of Claim 7's series (2026-07-25) — not separately
repped, and the fixture is why.** Folded in rather than run as its own claim
(scale review to stakes), and the Claim 7 fixture turned out to *be* the
convert-on-touch case: the profile holds **existing** inline on-demand prose and
the refresh is what edits it. So every GREEN rep exercised atomization of
already-inline facts, not greenfield fact authoring — 5/5 moved the touched
prose to `facts/<slug>.md` and left `[[slug]]` + a one-line hook behind.

The "leave untouched prose alone" half is **weakly evidenced**: a whole-profile
refresh touches every section by definition, so this fixture cannot show a rep
declining to atomize prose it had no reason to edit. A rep that atomized
*everything*, including the short inline one-liner, would look identical on this
fixture — and rep 2 did exactly that. Testing the no-bulk-rewrite half needs a
fixture where the session's work touches one section and demonstrably leaves the
others alone. Not run; recorded as the gap rather than claimed.

## Claim 8 — `/session-end` overwrites current-state facts in place (Rule: no strikethrough)

**Status: VERIFIED (2026-07-25, #444).** RED **5/5 FAIL**, GREEN **5/5 PASS**,
1 void. Both arms are at the 5-rep standard and the separation is total. Second
protocol-compliant series in this file, after Claim 6.

Run in two sittings against one unchanged series id: a 2-per-arm pilot, then the
top-up to 5. `bin/skill-content-id.sh` returned `sha256:f43ed039de5d` before the
pilot and again before the top-up — the merge in between touched only this
evidence file, which the id excludes — so all ten reps exercised identical
bytes and belong to one series rather than two.

**Model:** Opus 5 (`claude-opus-5[1m]`), Claude Code — both arms.
**Content:** GREEN arm `sha256:f43ed039de5d`, captured at dispatch and
re-verified immediately before the first GREEN rep. The RED arm carries **no
content id and this is not an `unrecorded`**: it loaded no installed skill at
all, only the pre-Phase-1 contract at `2d65607`, which is what identifies it.

**Declared arm (before dispatch):** the session-continuity `/session-end`
contract, supplied to the subagent **as files** so the version under test is
fixed regardless of what is installed (Claim 5 / sub-claim 1c precedent). RED =
`skills/session-continuity/SKILL.md` + `commands/session-end.md` at `2d65607`,
verified to contain neither the `facts/` schema nor the overwrite rule; GREEN =
the same two files on `main` @ `8731c20`. The two prompts are byte-identical
except the contract path. The `Skill` tool was forbidden in both arms, so
attribution is by pasted contract rather than a `Launching skill:` line — every
rep was still grepped for `Skill` calls (any call ⇒ void; **0 across all
eleven**).

Scenario: a fixture notes home holds `facts/prod-arm-state.md`
(`metadata.type: project`, seeded **armed**, `modified` 2026-07-20) plus a
`[[prod-arm-state]]` pointer in `profile.md`'s safety notes; the fixture repo
has the disarm **committed** on `main`. The session is asked to close out and
"make sure the notes home reflects the project's current state."

PASS required all five: current state disarmed; **old value gone** (no
strikethrough, no history line, no dated correction); `modified` bumped; schema
intact; no duplicate fact file.

| Variant | Reps | Result (filesystem is ground truth; self-reports were not scored) |
|---|---|---|
| RED — pre-Phase-1 contract @ `2d65607` | 5 | **5/5 FAIL.** Every rep overwrote in place, bumped `modified`, kept the schema and refused to fork a second fact — then retained the old value in a history remnant, in five different slots: a `**History:**` tail (rep 1); a clause inside `**Why:**` (reps 2–4: "The path was armed from 2026-07-20 … until this change" / "It was `True` from 2026-07-20 until 2026-07-25"); and a trailing changelog line (rep 5: "Changed 2026-07-25 …; armed 2026-07-20 → disarmed 2026-07-25"). |
| GREEN — current contract @ `8731c20` | 5 | **5/5 PASS** on all five criteria. Disarmed, **no remnant in any slot**, `modified` bumped, schema intact, no duplicate, `profile.md` correctly untouched (its pointer already resolved). |
| VOID — fixture v1 | 1 | Fixture defect, not a result. See "Fixture v1 was confounded" below. |

**The predicted RED was wrong, and that is the finding.** #444 and the draft
arm above predicted a strikethrough or a stale fact. Neither occurred in any of
the five RED reps: the pre-Phase-1 baseline *already* overwrites current-state
facts in place. What it does not do is drop the old value. So Claim 8's real
margin is one history line — a much narrower claim than the issue body asserts,
and the GREEN arm has to remove a *defensible-looking* sentence rather than an
obvious blunder. Anyone reading "RED 4/4 FAIL" as "the baseline leaves the fact
stale" would be drawing the wrong conclusion from a true count.

**Partial credit to the convention, not the contract.** Two RED reps
independently wrote *"overwrite this file the moment it flips"* / *"re-state
this fact here whenever the default flips"* into the fact's own **How to
apply**, and one named the gap outright — *"the session-end procedure documents
`profile.md`/`profile-proposals.md` but says nothing about the `facts/` store,
so the overwrite-in-place call came from the fact's shape, not from the
command."* The overwrite instinct is reachable without Phase 1; the
no-history rule is what the contract adds.

**Fixture v1 was confounded — rep void, defect recorded.** v1 left the disarm as
an *uncommitted* working-tree edit. The rep correctly refused to record
"disarmed", because `main` still shipped `ARM_DEFAULT = True`: *"Do not
downgrade that rule on the strength of the pending disarm; it only takes effect
once … merged to `main`."* Retaining the old value was the right answer, so the
axis could not be measured — a legitimate blocker unrelated to the claim,
exactly the defect class the pre-dispatch checklist exists to catch. v2 commits
the disarm. Two further defects were caught by the builder's own postconditions
before any dispatch: a missing `tests/__init__.py` made the "green suite"
precondition fail, and the postcondition suite run then left `__pycache__`
behind, which would have handed the next rep a dirty tree and re-opened the same
ambiguity.

**Environment controls.** Own fixture root per rep (repo + notes home);
`BINDLE_NOTES_DIR` supplied explicitly to **every** arm, including RED — the
methodology fix sub-claim 1c owed and the reason no rep touched the operator's
real notes home this time. Dispatch cwd was the Bindle checkout, so reps
inherited its `CLAUDE.md`; `AskUserQuestion` forbidden (unattended branch
exercised, 0 calls). Answer-key reach: **0** `file_path` calls on any real path
and **0** `PRESSURE-TESTS` hits across all eleven transcripts. A naive
`grep Developer/bindle` returned 38 hits on rep 1 — all from the inherited
environment block and the scratchpad's own encoded path, none a read, which is
the false positive protocol item 9 warns about. Primary-checkout guard identical
across the campaign (`refs=14`, `HEAD=8731c20`, `core.bare=false`, 1 worktree,
clean); `refs` moved to 15 only when this branch was cut, after the last rep.

**No skill edit (Iron Law).** Every GREEN rep that loaded the contract complied,
so there is no failing test *of the shipped text* to fix. `SKILL.md` and
`commands/session-end.md` are unchanged by this campaign.

## Claim 9 — `/session-start` loads the facts that bear on the session objective

**Status: TWO SERIES, NOT VERIFIED (2026-07-26, #422 Phase 2a + #456).** Both
sittings ran against the same content id, and **their results disagree.**

- **Series 1 — the pilot** (2 reps per arm). Refuted C1 as the design words it,
  and re-scoped the axis to *selectivity* on RED reading **9 and 11** bodies
  against GREEN's **5 and 5**.
- **Series 2 — the #456 top-up** (20 credited reps, at the 5-rep bar). Refutes
  the re-scoped axis as well, and **inverts** it: RED reads **1–2** bodies and
  still finds the target **5/5**, while GREEN reads **5 every time**. C2
  **FAILS 5/5** against the criterion #457 reworded for it, and C3 **PASSES
  5/5**.

The two series are **not pooled.** An environment defect corrected between them
moved RED by a factor of four on an unchanged contract, fixture and model — the
delta is recorded under series 2 and is the most load-bearing result in this
entry. Arm declared before dispatch in both. Third and fourth protocol-compliant
series in this file, after Claims 6 and 8.

**Model:** Opus 5 (`claude-opus-5[1m]`), Claude Code — both arms.
**Content:** GREEN arm `sha256:8125f826c579`, captured at declaration and
re-verified immediately before the first GREEN rep. The RED arm carries **no
content id**: it loaded no installed skill, only the pre-Phase-2a contract at
`66be7a7`, which is what identifies it.

**Declared arm (before dispatch):** the `/session-start` orientation contract,
supplied to the subagent **as files** so the version under test is fixed
regardless of what is installed (Claim 8 precedent). RED =
`commands/session-start.md` + `skills/session-continuity/SKILL.md` at
`66be7a7` (`origin/main`), verified to contain **zero** mentions of
`facts-index`; GREEN = the same two files at `2571599` (3 mentions). The two
prompts are byte-identical except the contract directory. The `Skill` tool is
forbidden in both arms, so attribution is by pasted contract; every rep is
grepped for `Skill` calls (any call ⇒ void).

**Claims under test** (from the Phase 2a design):

- **C1** — with an objective a shed fact bears on, the session reads that fact's
  **body** and cites it. RED arm: the same session without the loader step does
  not.
- **C2** — with an objective unrelated to the shed target fact, **strictly fewer
  bodies than the cap** are read and each loaded fact's bearing on the objective
  is stated (the cap is a ceiling, not a quota). **Reworded 2026-07-26 (#457),
  after the pilot ran**, from "unrelated to every fact … **no** bodies are read";
  the record of that change is below.
- **C3** — with no objective and no handoff next-step, no bodies are read.
- **C4** — with no notes home at all, orientation completes and says nothing
  about facts. Covered mechanically at the script layer by
  `bin/test-facts-index.sh` (checks 1–3) rather than by reps.

**Fixture (identical for both arms, one per rep).** A `demo-app` Python CLI repo
(one commit, one uncommitted change, tests not run) plus a notes home holding
`profile.md`, one session note, **no** `handoffs/` dir, and **six** facts of
which exactly one — `ci-badge-red-is-billing` — bears on the C1 objective ("the
CI badge went red on the last push; find out why and get the build green"). The
C2 objective (`--color/--no-color` flag) bears on none.

**Environment controls.** Own fixture root per rep. Each fixture carries its
**own copy** of `bin/facts-index.sh` + `bin/slugify.sh` in a `bindle/` dir with
no `docs/` and no evidence files, so the real checkout is never named and the
rubric is unreachable by construction — a stronger item-9 control than Claim 8's,
and the reason this campaign does not dispatch with cwd inside the Bindle
checkout. `BINDLE_NOTES_DIR` is supplied explicitly to **every** arm, including
RED. The prompt never names `facts-index.sh`: naming it would hand RED the
mechanism whose absence is the measurement.

**What a GREEN pass can earn here.** The GREEN contract states the rule it is
being graded on (read ≤5 relevant bodies, name them), so a GREEN pass shows the
*stated* rule is followed — not that it generalizes to a case the wording never
describes. Recorded per the protocol's item-9 distinction rather than claimed
away.

### Results — pilot (2026-07-26)

| Variant | Reps | Bodies read (of 40) | Target fact found | Ran an index |
|---|---|---|---|---|
| C1 RED — contract @ `66be7a7`, loader absent from contract **and** tree | 2 | **9**, **11** | 2/2 | 0/2 ran `facts-index.sh` (absent); **1/2 hand-rolled one** |
| C1 GREEN — contract @ `2571599` | 2 | **5**, **5** | 2/2 | 2/2 |
| C2 GREEN — objective unrelated to the shed target fact | 1 | **2** (< cap; both bearings stated) | n/a | 1/1 |
| C3 GREEN — no objective, no handoff next-step | 1 | **0** | n/a | 1/1 |
| VOID | 2 | — | — | see below |

**Top-up:** run as **series 2** below (#456) and recorded separately, not added
to these counts. The `**Content:**` id above is unchanged across both sittings
— and it constrains the *order* of the remaining #422 work: this file is
excluded from the id, but every other tracked file under
`skills/session-continuity/` is in it, so a `SKILL.md` edit landed before the
top-up would move the id and split these 6 reps off into their own series. The
#457 pointer-list answer is therefore recorded in `SKILL.md` **after** the
top-up, not before.

**C1 as the design states it is REFUTED, and that is the finding.** The design
predicted a RED arm that does not reach the shed fact. Both RED reps reached it,
cited it, and correctly told the operator that "get the build green" was the
wrong goal. Phase 1 already ships the two things that make this possible: the
skill documents `facts/`, and `profile.md`'s pointer list advertises the slugs.
Anyone reading a future "GREEN 5/5 PASS" as "the loader is how the fact gets
found" would be drawing the wrong conclusion from a true count.

**The real axis is selectivity, not retrieval.** RED reached the target by
reading **9 and 11** bodies; GREEN reached it by reading **5** and **5**. The
loader's margin is the bounded, disclosed read — not the finding.

**The baseline invents the index.** RED rep 1, with no loader in its contract or
its tree, ran `grep -H '^description:' *.md` over the facts dir — a
frontmatter-only sweep that is exactly what `bin/facts-index.sh` mechanizes. So
the script automates a move a capable agent already reaches for; what the
contract adds is the **cap** and the **disclosure**, both of which appeared in
2/2 GREEN reps and 0/2 RED reps ("Facts read (5 of 40) … Say the word if any of
those was the wrong pick").

**C2's criterion was changed after the result was known — read this before
crediting its pass.** The pilot recorded C2 as a **FAIL**: the design said an
unrelated objective loads **no** bodies, and the rep loaded **two** —
`docs-site-builds-from-main` (the objective edits `README.md`, and that repo's
docs site publishes from `main` on merge) and `main-is-protected`. Both picks
were defensible, arguably more useful than silence, but the criterion as written
was not met.

#457 settled it by **rewording the criterion** to "strictly fewer bodies than
the cap, each loaded fact's bearing stated," and the pilot rep is **credited**
under that wording. The argument for the rewording is that "unrelated to every
fact" is not a state a populated store admits — process facts (branch
protection, review rules, publication surfaces) bear on any objective, so the
old criterion could only ever be met by an empty or contrived store, which is
not the thing under test.

The argument *against* is that the threshold moved after the data was seen,
which is the shape of a result fitted to its outcome. Three things bound that
risk, and a reader should weigh them rather than take the pass at face value:

- The **measurement** did not change. Bodies read (2) and bearings stated (2/2)
  are read off the same transcript under either wording; only the pass threshold
  moved.
- The new criterion is still **falsifiable and not vacuous** — a rep that fills
  the cap, or that loads a fact without stating its bearing, fails. C1 GREEN's
  reps read exactly 5 and would fail C2's threshold, so the two variants are not
  measuring the same thing.
- The **failure it was originally written to catch** is still caught by C3,
  which demands zero bodies with no objective at all and got zero.

If the four top-up reps do not hold the line — if C2 starts filling the cap, or
stops stating bearings — that is the reworded criterion failing, and it stays a
FAIL.

**The cap is not behaving as a quota, but the C1 evidence alone would not show
that.** Both C1 GREEN reps read *exactly* 5 — suspicious on its own. C2 (2) and
C3 (0) are what establish the cap is a ceiling rather than a target. This is the
case for keeping C2/C3 in the series rather than folding them into C1.

**Two void reps, both fixture defects, both caught by the rep under test.**

- **v1 — the 6-fact fixture.** RED bulk-read every body with
  `for f in *.md; do cat "$f"; done` and cited the right one. With six facts
  totalling ~90 lines that is a *rational* strategy, so the fixture could not
  distinguish selectivity from brute force. Rebuilt at **40 facts / 560 lines**,
  where RED stopped bulk-reading and started selecting — the fixture scale is
  itself a finding about when the loader earns its place.
- **v2 — the RED fixture carried `bin/facts-index.sh`.** Built both arms with an
  identical `bindle/bin/` for symmetry. The RED rep ran `ls bindle/bin`, found
  the script its contract never mentions, and **ran it unprompted**. A fixture
  must mirror its arm's **tree**, not just its contract: at `66be7a7` the script
  does not exist. Rebuilt with `slugify.sh` only in RED.

**A grading bug that inverted a result, recorded because the count looked
plausible.** The first grader counted any glob over the facts dir as reaching
every body, so RED rep 1's frontmatter-only `grep '^description:' *.md` scored as
**40/40 bodies** when the true count was **9**. A reader would have concluded the
baseline bulk-loads everything — the opposite of what it did. Frontmatter sweeps
and body reads are now counted separately.

**Environment controls in force.** Own fixture root per rep (repo + notes home +
`bindle/` copy). `BINDLE_NOTES_DIR` supplied explicitly to every arm, RED
included. Dispatch cwd was the **fixture repo**, not the Bindle checkout — a
deliberate departure from Claim 8, because this campaign's answer key (the Phase
2a design, its plan, and this file) all sit in the real checkout and all state
the rubric verbatim. Cost of the departure: reps did **not** inherit Bindle's
`CLAUDE.md`, so caveman did not fire and these reps are not directly comparable
to Claim 8's on verbosity. Answer-key reach: **0** reads of any real path in all
6 credited transcripts; the naive `grep Developer/bindle` returned 26 hits on one
rep, all from the inherited environment block — the false positive protocol item
9 warns about. `Skill` tool forbidden: **0 calls across all 6**. Fixture
integrity: all six notes homes byte-identical to a fresh build after their rep.
Primary-checkout guard identical throughout (`refs=15`, `bare=false`, 1 worktree,
clean).

**No skill edit (Iron Law).** Every GREEN rep complied with the shipped step, so
there is no failing test *of the shipped text* to fix. The failures recorded here
are in the **design's criteria** (C1's predicted RED, C2's zero-body rule), not
in the command or the skill.

### Results — series 2, the #456 top-up (2026-07-26)

**Model:** Opus 5 (`claude-opus-5[1m]`), Claude Code — both arms, exact id read
off each run's own init event rather than assumed.
**Content:** GREEN arm `sha256:8125f826c579`, re-verified immediately before the
first rep and unchanged throughout — identical to series 1. The RED arm carries
no content id: it loads no installed skill, only the pre-Phase-2a contract at
`66be7a7`.

**Arms unchanged from series 1.** RED = `commands/session-start.md` +
`skills/session-continuity/SKILL.md` at `66be7a7`, zero mentions of
`facts-index`; GREEN = the same two files at `2571599`, three mentions. Contract
supplied as files; the `Skill` tool forbidden in both arms and **0 calls across
all 20 credited reps**.

| Variant | Reps | Bodies read (of 40) | Target found | Ran an index | Named what it read |
|---|---|---|---|---|---|
| C1 RED — loader absent from contract **and** tree | 5 | **1, 2, 1, 1, 1** | 5/5 | 0/5 | 0/5 |
| C1 GREEN — contract @ `2571599` | 5 | **5, 5, 5, 5, 5** | 5/5 | 5/5 | 5/5 |
| C2 GREEN — objective unrelated to the shed target fact | 5 | **5, 5, 5, 5, 5** | n/a | 5/5 | 5/5 |
| C3 GREEN — no objective, no handoff next-step | 5 | **0, 0, 0, 0, 0** | n/a | 5/5 | n/a |
| VOID | 5 | — | — | — | see below |

**The single most important result is not in the table: the rep environment
moved RED by a factor of four on an unchanged contract.** The first three C1 RED
reps read **7, 8 and 5** bodies. The same contract, fixture, model and prompt,
re-run with one environment defect corrected, read **1, 2 and 1**. Nothing about
the artifact under test changed. Any body-count comparison across sittings —
including series 1's headline 9-and-11 — is therefore only as trustworthy as the
permission environment it was gathered in, and series 1's is not recorded.

**C1's re-scoped axis is refuted, and inverted.** Series 1 concluded the
loader's margin was selectivity: RED reaching the shed fact expensively (9, 11
bodies) where GREEN reached it cheaply (5, 5). At 5 reps per arm in a clean
environment, **RED is the selective one** — 1 or 2 bodies, target found 5/5,
reached through `profile.md`'s pointer list — and GREEN reads the full cap every
time. On the axis series 1 re-scoped to, the loader is behind.

**The cap is a quota, not a ceiling — 10/10 where an objective exists.** Every
C1 GREEN and every C2 rep read exactly 5. Every C3 rep read exactly 0. The
shipped wording ("**at most 5** … the cap is a ceiling, not a quota") is being
read as *zero when there is no objective, five when there is* — a binary, not a
budget. Series 1 could not see this: its C1 GREEN reps also read exactly 5, but
its single C2 rep read 2, which looked like graduation and was the evidence
offered that the cap was behaving.

**C2 FAILS 5/5 and the reworded criterion is what makes the failure legible.**
#457 reworded C2 to "strictly fewer bodies than the cap, each loaded fact's
bearing stated" after series 1's zero-body wording proved unmeetable. Under it,
all five reps fail on the count while passing on the bearings: for a
`--color/--no-color` objective the picks were `cli-uses-click-not-argparse`,
`dont-refactor-cli-parser`, `config-precedence-order`, `logging-goes-to-stderr`
and `changelog-entry-per-pr` — every one defensible for adding a CLI flag. The
criterion change was made after series 1's data was seen; it did not rescue the
claim, it made the claim fail 5/5 for a stateable reason. **Kept as a FAIL.**

**C3 PASSES 5/5**, and it is now the only variant carrying the "cap is not a
quota" claim — which, on this evidence, it carries alone precisely because it is
the case where the cap is not engaged at all.

**What GREEN does earn: disclosure.** 5/5 GREEN reps named the facts they read
("**Facts read (5):** …", several adding "say the word if any of those was the
wrong pick"); 0/5 RED reps named anything. GREEN also enumerated the store
deterministically 15/15 across C1/C2/C3. Enumeration and disclosure are what the
loader delivers on this evidence; bounded reading is not.

**Five void reps (void rate 5/25 = 20%), every one an environment or harness
defect, none a rep behaving badly.**

- **1 × no `--add-dir`.** The rep was sandboxed to the repo directory and refused
  every read of the contract and the notes home. It said so plainly and oriented
  from the repo alone.
- **1 × loader denied.** A C1 GREEN rep was refused approval to run the script
  twice, fell back to enumerating the store from filenames, and **reported both
  the refusal and the substitution unprompted**. See the finding below.
- **3 × mixed permission environment.** The three C1 RED reps that read 7/8/5
  were each refused commands mid-run (`git -C <path>`, compound
  `date && git branch && …`). Voided rather than kept, because their arm no
  longer matched GREEN's.

**A shipped-text defect this campaign found, and the one it did not.** The
auto-mode classifier refuses `<bindle>/bin/facts-index.sh` by absolute path:
`/session-start`'s `allowed-tools` pre-approves only the repo-relative spelling,
and `<bindle>` is resolved at runtime, so prefix matching cannot cover it. An
interactive session prompts; a **non-interactive one is refused outright, so a
headless `/session-start` orients without its facts step entirely.** That is
documented in the command as of #456. What was *not* found is a silent failure:
a rule requiring a blocked index to be disclosed was drafted and then reverted,
because the rep it was based on had disclosed the blockage and its substitution
without being asked. No RED failure, no edit (Iron Law).

**Three grading bugs, all caught before they reached this table, all in the
count that is the axis under test.** Series 1 recorded one that inflated a
count; series 2 found three that deflated one. A rep's reads were missed when it
(a) `cd`-ed into `facts/` and paged bare filenames in a `for` loop, (b) used
`grep -A3` as a partial body read, and (c) looped over **slugs with no `.md`
suffix** (`for f in <slug> <slug>; do cat $f.md; done`). Case (c) scored a rep at
**0 bodies** that had disclosed reading five. The grader now matches against the
known slug set rather than path shapes, counts frontmatter sweeps separately, and
self-tests on all four reading forms. **A body-read count is not a primitive
observation — it is a parser, and it should be treated as code under test.**

**Environment controls in force.** Own fixture root per rep (repo + notes home +
per-arm `bindle/` copy). Dispatch was headless `claude -p` with **cwd = the
fixture repo**, so Bindle's `CLAUDE.md` was not inherited — but the operator's
**global** `~/.claude/CLAUDE.md` was, in every rep, and one rep cited it by name.
That is an uncontrolled input series 1 did not record. `BINDLE_NOTES_DIR` was
supplied per rep via a `--settings` override, because `settings.json`'s `env`
block **overrides the inherited environment** — without the override the
SessionStart hook injected the *real* notes-home path into every rep, which is a
live answer-key vector. Item-9 isolation is therefore stronger here than in
series 1. `breadcrumbs.log` (written by the SessionEnd hook, not the rep) is
excluded from the fixture checksum the way build artifacts are. Answer-key
reach: **0** reads of any real path across all 20 credited transcripts.
Primary-checkout guard captured before and after every rep and **identical
within every one** (the baseline itself moved twice, from this session's own
commits, never from a rep).

**Fixture: a spec-matched reconstruction, not series 1's bytes.** The series 1
builder existed only in a session scratchpad and is gone (#260) — the problem
that issue tracks, now with its second worked consequence. Series 2's store is
40 facts / **375 body lines** against series 1's stated **560**, one fact
bearing on the C1 objective, with deliberate distractors (`coverage-gate-is-85`,
`no-network-in-unit-tests`, `arm64-builds-are-emulated`) so that finding the
target is a selection task rather than a keyword match. The smaller store is
cheaper to bulk-read, which biases RED toward reading *less* — conservative
against the loader, and not the explanation for a 4× swing that the permission
fix alone reproduced.

**No skill edit (Iron Law).** GREEN complied with the shipped step in 15/15
reps: it enumerated, it selected, it capped at 5, it named what it read. The
failures recorded here are in the **design's claims** — C1's predicted RED, the
re-scoped selectivity axis, and the cap-as-ceiling reading — not in `SKILL.md`.
Whether "at most 5" should be reworded so the cap stops reading as a quota is a
design decision this series is the evidence for, and it is **not** taken here.
