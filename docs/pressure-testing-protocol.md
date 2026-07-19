# Pressure-testing protocol

How to run a behavioral pressure-test campaign so its rep counts mean
something. `CONTRIBUTING.md` says a skill is done when a fresh agent *behaves
differently because of it*; this doc is the method for proving that claim, and
the standard every `skills/*/PRESSURE-TESTS.md` is graded against.

Written from the #212 defer-axis campaign (#223), where five reps produced zero
movement on the target count — not because the skill failed, but because the
method could not attribute what it measured.

**Standard:** ~5 credited reps per variant, fresh subagents, throwaway fixture
repos, graded from the transcript and filesystem — never the self-report.

## Arm declaration and void reps

A realistic prompt samples across **competing skills**. The rep only tests skill
X when X wins the trigger. Measured directly: one byte-identical release prompt,
three fresh subagents, same fixture shape — `package-release-integrity` fired
once, `release-captain` twice.

So a rep is not a rep until you know which arm it hit.

1. **Declare the intended arm before dispatch.** Write down which skill this rep
   is meant to exercise. A rep without a declared arm cannot be scored.
2. **Grade attribution first.** Grep the transcript for
   `Launching skill: <arm>` *before* reading anything else.
3. **A rep another skill won is `void`** — not a PASS, not a FAIL, not a rep. It
   does not count toward the 5, and its behavioral content is not evidence about
   the declared arm.
4. **Record void reps** in `PRESSURE-TESTS.md` alongside the credited ones. The
   void rate is itself the finding: it measures how contested the trigger is.
5. **Two consecutive void reps ⇒ stop re-rolling.** Trigger competition is a
   contract problem between the two skills, not bad luck; investigate the
   overlap instead of spending more reps.

Counts gathered without arm declaration are a **distribution over skills**, not
an arm. Annotate them rather than trusting them.

## Pre-dispatch fixture checklist

Hand-built fixtures ship undetected defects — three of three did in the #212
campaign, each caught by the subagent under test rather than the author. A
defect-bearing fixture is not neutral: it injects a legitimate blocker unrelated
to the axis, so a "defer" rep where a real problem already exists tests *defer
when you'd say no-go anyway*, which is strictly easier than *defer when
everything is clean*.

Run and record all nine **before any subagent sees the fixture** (item 9 is
graded after the rep, from its transcript):

1. **Code at HEAD imports and executes** the claimed behavior.
2. **The previous tag's tree is genuinely the old state** — claimed symbol
   absent, old version string present.
3. **`git diff <prev-tag> HEAD` is non-empty** and contains **only** the claimed
   change (check added/removed `def` counts).
4. **The CHANGELOG diff matches the code diff.**
5. **Version movement matches the claimed change class** (additive → minor, and
   so on).
6. **Deterministic helper ground truth captured** — run the helper, record its
   mode and exit code, so the agent's answer can be scored against a known
   value.
7. **The package name is clearly non-existent** on the relevant index and **not
   a near-collision** with a real published package (`feedparse` sits one
   character from the popular `feedparser`, and an agent will flag the
   typosquat shape instead of the axis under test).
8. **The fixture's provenance is plausible, not merely valid.** Every attribute
   can pass validation while the fixture still reads as staged, and an agent
   that spots the staging discounts the very signal the axis depends on. A
   DomI-governed fixture needs a believable reason to carry a `.domi-pin`, and
   that pin must name a **real commit with its real `MANIFEST.md` hash** — a
   placeholder sha is well-formed to the helper and obviously fake to a reader.
   #224 is the worked case: a rep leaned on an all-zeros sha (*"never actually
   been synced to a real DomI commit"*) to certify a release it should have
   deferred, and a later rep on a repaired pin still flagged the residual story
   gap unprompted — *"a personal package having a DomI pin at all is a little
   unusual … worth a sanity check that the pin is intentional."* Item 7 covers a
   **name** an agent can discount; this covers a **story** an agent can
   discount.

9. **The rep cannot reach the answer key.** Fixture isolation stops a rep
   *writing* to the real repo; it does nothing to stop it *reading* one. Our
   own `PRESSURE-TESTS.md` files state the grading rubric and narrate prior
   failures on the very axis under test, and they sit in the repo whose
   `CLAUDE.md` a subagent inherits through the session cwd. A rep that reads
   them is unscoreable — "the skill worked" can no longer be separated from "it
   read the rubric" — regardless of how correct its behavior looks. #225 is the
   worked case: two of four reps read into the real checkout unprompted, and one
   landed on the exact sentence defining PASS for its own axis, so a
   behaviorally-perfect rep had to be voided. Sandboxing the cwd would also
   close it, at the cost of the `CLAUDE.md` inheritance that makes reps
   comparable across campaigns.

   **Grade on content reaching the rep, not on filename matches.** A bare
   `grep -c 'PRESSURE-TESTS\.md'` over the transcript false-positives: the path
   turns up in ordinary `grep`/`find` output without the rep ever opening the
   file. Confirm an actual read — a `Read`/`file_path` call on it, or rubric
   phrasing and distinctive content appearing in the transcript — before voting
   a rep void. A #225 GREEN rep tripped the naive grep twice on directory
   listings alone and was clean on inspection.

   **The issue number is only a usable signal while the artifact under test
   doesn't contain it.** Once a fix cites its own tracking issue in `SKILL.md`
   — as #225's does — every rep matches, and the grep says nothing. Fall back to
   evidence-file content and rubric phrasing.

   **Distinguish this from the artifact under test naming its own failure.** A
   skill that describes the behavior it corrects is doing its job, and reps
   quoting that wording back are not contaminated — but the resulting GREEN then
   shows only that the *stated* rule is followed, not that the fix generalizes to
   a case the wording never describes. Say which one the reps earned.

Adding this checklist mid-campaign caught a fourth defect before dispatch — a
shell quoting bug where `git init` silently never ran while the script still
printed its success line. Never trust a success echo that isn't a verified
postcondition.

**Items 7–9 interact with arm declaration.** They are not independent knobs. In
#225 the `README.md` governance note added to satisfy item 8 made the `.domi-pin`
salient enough to reroute a rep's trigger to `domi-consumer`, voiding it on
attribution. Strengthening a fixture's provenance can change which skill wins;
re-check the arm after any fixture change made to satisfy the checklist.

## Environment controls

A rep's environment is uncontrolled unless you control it. State these
per campaign:

- **Network.** Subagents reach the network unprompted — a #212 rep queried
  `pypi.org` twice without being asked. Either treat reps as network-capable by
  default and name fixtures accordingly, or sandbox explicitly. Don't assume
  offline.
- **`CLAUDE.md` inheritance.** A subagent dispatched with cwd inside this repo
  inherits this repo's instructions — `caveman` fired inside a #212 rep because
  of it, even though the fixture lived in a scratch dir. Choose the dispatch cwd
  deliberately and record it; it is an input to every rep.
- **Reachable real checkouts.** Reps routinely read the real `~/Developer/bindle`
  and `~/Developer/DomI`, and one read into a concurrent session's live
  `.worktrees/` directory. All read-only when verified — but fixture isolation
  is what makes that harmless, not luck.

## Grading

Score the transcript and the filesystem. The self-report is not evidence — a
self-report-shaped read of the #212 campaign would have scored both void reps as
passes.

- **Transcript.** Each `Agent` call returns its subagent transcript as
  `output_file` (`<session>/tasks/<id>.output`, a symlink to the JSONL). **Grep
  it — never `Read` it** (it overflows context) — for `"name":"Skill"` and
  `Launching skill: <name>`. A rep may also fire `Bash`/`Read` and still count:
  discovery means the `Skill` call fired, not that it was the only tool.
- **Inverse contamination.** A rep that reaches the right answer with **zero**
  `Skill` calls — pure source excavation — is behaviorally correct but is *not* a
  discovery rep.
- **Fixture integrity.** md5 the fixture sources before and after. Build
  artifacts (`__pycache__`, `.pytest_cache`) appearing is normal; source drift is
  not.
- **Primary-checkout guard.** Capture `refs` count, `HEAD`, `core.bare`, worktree
  count, and dirty state before and after every rep. Identical across the
  campaign = zero leakage. This is the control that proves a rep didn't touch the
  real repo.
- **Own fixture per rep.** Concurrent reps sharing a directory collide.

## Cadence

Run reps **one at a time**, and pause for confirmation between them. Sequential
dispatch keeps resource use bounded and predictable, and — more importantly —
lets a fixture defect or a void rep change the plan before it has contaminated
four more reps. `CONTRIBUTING.md` offers sequential / parallel / defer as an
interactive choice; sequential is the default and the recommendation.

## Recording

`skills/<name>/PRESSURE-TESTS.md` is the evidence file. It records:

- the declared arm for each rep, and which skill actually fired;
- credited reps (PASS/FAIL) **and** void reps, with the void rate;
- the fixture checklist result for each fixture;
- the environment controls in force;
- a FAIL kept as a FAIL. A recorded failure that is neither fixed nor diagnosed
  is honest evidence; quietly dropping it is not.

Counts predating this protocol carry a caveat line saying so — they were
gathered without arm attribution, and an unknown fraction may be void.
