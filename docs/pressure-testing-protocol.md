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

- **Worker model.** The single largest determinant of a rep's outcome, and a
  controlled input like any other: declare which model (and provider — Claude
  Code vs. Codex) runs each series *before dispatch*, and record it per
  § Recording below. `docs/workflow-eval.md`'s result schema already requires
  exact model/provider/version as a state-based field; this bullet is where
  the protocol of record catches up (#331). Reps run under Codex
  (`codex exec`) are a different provider *and* a different model — never
  record them interchangeably with Claude Code reps.
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
- the **model** that produced the series — a `**Model:**` line in each
  series' method statement, naming exact model/provider/version, e.g.
  "**Model:** Sonnet 5 (`claude-sonnet-5`), Claude Code" or "**Model:**
  gpt-5.5, Codex CLI 0.143.0". Granularity is **per-series, with a
  per-rep override**: one
  line covers every rep in the series; a series that mixes models must
  instead name the model per rep or per arm (the fork-pr-flow Fable+Haiku
  campaign is the worked example). A series whose model is not known writes
  `**Model:** unrecorded` — an explicit unknown, never silence, and never a
  guessed value more precise than the evidence (a historical series known
  only as "Sonnet 5" records that, not an invented dated snapshot);
- the **content identity** of the skill under test — a `**Content:**` line
  beside the `**Model:**` line in each series' method statement, recording
  the output of `bin/skill-content-id.sh <skill>` (e.g. "**Content:**
  sha256:3f7a29c04d11"), computed **at dispatch time**, never reconstructed
  afterward. The id covers every tracked file under `skills/<name>/` except
  `PRESSURE-TESTS.md` itself, hashed from the working tree — it describes
  the bytes the reps actually exercised, uncommitted edits included.
  Granularity matches `**Model:**`: per-series, with a per-arm/per-rep
  override — a REFACTOR mid-series edit means the GREEN arms before and
  after the edit carry different ids, recorded per arm. RED (no-skill) arms
  carry no id — nothing was loaded. A series whose id is not known writes
  `**Content:** unrecorded` — an explicit unknown, never silence, never a
  value derived after the fact;
- the **protocol status** of the series — a `**Protocol:**` line beside the
  `**Model:**` and `**Content:**` lines, recording whether the series ran under
  this method of record. Exactly three values: `compliant` (arm declared before
  dispatch), `pre-protocol` (predates the arm-declaration rule; grandfathered
  per #261 — stands as recorded, not owed a re-run, not evidence the current
  protocol was met), and `unrecorded` (an honest unknown). Free prose may
  follow the value, on the line or a continuation. An example line reads
  "**Protocol:** compliant — arm predeclared, fixture checklist 8/8".
  Granularity matches `**Model:**`: per-series, with a per-arm override — a
  section that declares any of the three fields declares all three, and a
  series whose status differs from its file's default carries its own block
  rather than relying on prose above it. This field is the **single source**
  for protocol status (#356): a file-head caveat states the grandfathering
  rationale once and points at the fields; it does not enumerate which series
  are covered, because that list decays on the next append. Enforced by
  `bin/check-pressure-series.sh` (#467), which is why the three fields are a
  contract rather than a convention: `--staged`, wired as the
  `bindle-pressure-series` pre-commit hook, reddens when a new series heading is
  appended without its field block — at one of the heading depths that file
  already declares at, so calibration is read from the file and never from a
  table here; `--all`, wired into `make check`, reddens when any existing block
  is incomplete or carries a value outside the three. Because the gate fires on
  the **append**, a grandfathered series needs no edit to stay legal — the
  #261 decision is enforced, not re-opened. A heading that records no reps
  (bookkeeping, a closing note) is exempted in place with
  `<!-- not-a-series: reason -->`, which states the reason where a reader will
  find it;
- any **safety claim** the series earns — a `**Claim:**` line beside the
  `**Model:**` and `**Content:**` lines, asserting that a named bracket is
  safe **for this workflow's task shape**, e.g. "**Claim:** vendor-safe
  (Codex CLI) for the commit-gate task shape — discovered, read, and
  behaviorally followed". A claim is optional; most series earn none, and
  a series that earns none writes no line (see the silence rule below);
- a FAIL kept as a FAIL. A recorded failure that is neither fixed nor diagnosed
  is honest evidence; quietly dropping it is not.

The `**Model:**` field is the **single source** for model provenance
(#312/#323: one declared place). Prose that merely restates the series'
model collapses into the field; prose in which the model is part of a
*finding* — a cross-bracket comparison, a weaker-model failure analysis —
stays, because that is evidence, not a caveat.

The `**Content:**` field follows the same single-source rule. It is also the
field tooling keys on: `bin/skill-content-id.sh --check <skill>` is the
one-command answer to "do this skill's hashed reps still apply to its current
content?", and `bin/check.sh` prints a warn-only `stale reps` banner when a
skill's newest hashed series no longer matches — a disclosure, not a gate,
by the recorded #339 decision. What `--check` reads is the whole `**Content:**`
**field** — the line and its wrapped continuation, up to the next blank line,
field, heading or list item — so an arm qualifier and backticks around the id
are fine, and a per-arm override may land on a continuation line. An id
mentioned in surrounding prose is **not** a record: put every id that counts
inside the field. (Before #459 the parser required the id to follow
`**Content:** ` immediately and unquoted, so it matched nothing this repo had
ever written and the banner never fired.)

### Safety claims (#332)

A **claim** is an assertion in a workflow's own evidence file that a named
bracket — a weaker Claude tier, or another vendor — is safe for that
workflow's task shape. It matters because it is a **trigger**:
[workflow-eval.md](workflow-eval.md) requires a cross-model eval only when a
workflow explicitly claims weaker-model-safety, never as a blanket
requirement. Until a claim exists, that machinery never runs.

- **One home.** The `**Claim:**` field is the single declared place, for the
  same reason `**Model:**` and `**Content:**` are (#312/#323). It sits next to
  the evidence that earns it, so a reader never has to reconcile a claim in one
  file against reps in another. Prose that restates a claim collapses into the
  field; prose in which the bracket is part of a *finding* stays.
- **The bar is [workflow-eval.md](workflow-eval.md)'s stopping rule** for the
  workflow's own capability class: 3 reps per variant for C0–C1, 5 for C2–C4,
  5 unanimous for C5 — with the result schema's state-based fields recorded,
  which is what the `**Model:**` and `**Content:**` fields exist to supply. A
  claim below its bar is not a weaker claim; it is not a claim.
- **Vendor claims name their surface.** "Safe under Codex" is not one property.
  `skill-portability-audit.md`'s U1–U6 already decompose it — discovered,
  read, behaviorally followed — and a claim names the surfaces actually
  evidenced. The asymmetry is live, not hypothetical: U2 is resolved for
  `verify-then-commit` and explicitly open for `fork-pr-flow`, so a flat
  "Codex-safe" claim would be false for one of the two.
- **A claim is scoped to the content that earned it.** It applies to the
  `**Content:**` id recorded beside it and to nothing else. When the skill's
  content moves, `bin/check.sh`'s warn-only `stale reps` banner names the
  file, and every claim in it is **void until re-earned** — the drift signal
  is the one already shipped for reps (#339), not a second mechanism. Warn-only
  is deliberate and matches that decision: a stale claim is a disclosure
  problem, and a gate that blocks commits gets bypassed rather than heeded.
- **Silence means unknown.** A workflow that claims nothing writes nothing;
  absence is not a denial, and no counter-statement is owed. The one exception:
  a file that claims **one** bracket must name the brackets it does **not**
  claim, so a partial claim cannot be read as a general one.
- **Neither axis implies the other.** A vendor claim is not a weaker-model
  claim and a weaker-model claim is not a vendor claim, in either direction.
- **A claim is never a ranking.** Per `delegation-profiles.md`, this contract
  names no commercial model and ranks none against another. A claim is scoped
  to one workflow's task shape — the #87 campaign's framing, "pressure-tested
  for that task shape, not a general ranking of one model." A claim that
  generalizes past its task shape is out of scope, however good its reps.

Counts predating this protocol carry a caveat line saying so — they were
gathered without arm attribution, and an unknown fraction may be void.

A file that contains **both** pre- and post-protocol series does not carry a
blanket caveat, and does not enumerate the split in prose either: each series
records its own `**Protocol:**` field, and the file-head caveat states the
grandfathering rationale once and points at those fields (#356). A blanket
caveat over a file with a compliant series appended is wrong in the other
direction — it buries evidence that was actually earned — and an enumerated
list in the caveat is wrong in a third way: it decays silently the moment the
next series is appended without updating it.
`skills/package-release-integrity/PRESSURE-TESTS.md` is a worked example of the
shape — an illustration, not a census. Which files are mixed is read off the
`**Protocol:**` fields, never from a list kept here.

## Grandfathered pre-protocol counts (#261)

Rep counts gathered before this protocol are **grandfathered, not voided**. They
stand as recorded and are not owed a re-run — re-running roughly a hundred reps
costs far more than the uncertainty they carry. The hazard being managed is not
the uncertainty itself but an *unmarked* count: a future session reads "5/5 PASS"
and assumes it was earned under this protocol.

The split is **temporal and per-series**, not per-file. Every series recorded
before the protocol landed is pre-protocol, including series in files that also
carry compliant ones — and including a same-day series that predates
the finding it produced. The discriminator is whether the series **declared its
arm before dispatch**, not its date.

The `**Model:**` field (#331) follows the same rule: historical series are
**annotated with what is already known** — the model their own prose or
session notes name, `unrecorded` where nothing does — and are **never re-run
to learn their model**. The new field is not a re-run obligation, and an
annotation is not a protocol credit: a pre-protocol series with a `Model:`
line is still pre-protocol.

The `**Content:**` field (#339) is stricter still: historical series are
annotated `**Content:** unrecorded`, full stop. The dispatch-time working
tree is unknowable from a `Status:` date — the exact commit was not
recorded, and reps may have run against uncommitted content — so a hash
derived from git archaeology is a guess wearing precision, worse than an
honest unknown. Never re-run a series to learn its id; an annotation is not
a protocol credit.

### What this does to #212's targets

#212 tracks topping under-repped skills up to the ~5-reps/variant standard. Its
per-skill numbers were quoted from the `PRESSURE-TESTS.md` files as they stood
when it was filed. The shortfalls it recorded still stand and have no other
home, so they are kept here:

| Skill | #212's recorded shortfall |
|---|---|
| `package-release-integrity` | 1–2 reps/axis across 6 axes; data-only track unexercised by a Claude subagent |
| `license-compliance-auditor` | 3/arm on both claims; Issue-Creation Gate inspected, never run live — the gate's live run is owed regardless |
| `repo-hygiene-init` | 3/arm original, 3–4/arm on the #65 rerun |
| `maintain-claude-md` | Claims 5–6 at 3/arm |
| `scoped-sequential-prs` | Claim 5 at 3/arm, Claim 6 at 3/bracket |
| `release-captain` | restraint GREEN re-test at 4 reps; dry-run → gate → apply never exercised end-to-end — the unexercised positive path is owed regardless |
| `context-graph` | closed — topped to 5 live-discovery reps/scenario |
| `issue-work-loop` | PT3 and PT8 at inline `n=1` |
| `domi-consumer`, `fork-pr-flow`, `hands-on-keyboard` | excluded as already at bar (5/arm or 5/variant) |

Which of those reps were earned under this protocol is deliberately **not**
restated here: every series records its own `**Protocol:**` field (#356), and a
per-skill list in this doc is the shape the field replaced — it decays the
moment the next series is appended. Read the fields. `session-continuity` and
`verify-then-commit` were not enumerated by #212, so this table records no
shortfall for them; that says nothing about their protocol status either.

Two consequences for anyone picking #212 up:

1. **A topped-up skill ends with a mixed record.** Top-up reps run today are
   protocol-credited; the base they are added to is not. "5 reps" on such a skill
   means *n* credited plus *5 − n* grandfathered, and the file must say which.
   Do not report a mixed total as though the whole of it were earned under this
   protocol.
2. **Reaching 5 is no longer the same claim it was when #212 was filed.** For a
   skill whose entire record is grandfathered, "already at bar" means at bar on
   count only. Whether that is worth converting into protocol-credited reps is a
   per-skill judgement #212 should make explicitly, not an automatic debt — the
   grandfather decision exists precisely to avoid re-running the corpus wholesale.
