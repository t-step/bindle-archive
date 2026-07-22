# license-compliance-auditor — pressure-test log

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
skill isn't done until an agent has been watched under pressure. This log
records what was actually pressure-tested with subagents, so nobody has to
guess which claims are verified and which are still draft. Closes issue #15.

This skill shipped in 0.2.0 with unit tests for its Python scripts
(`tests/test_*.py`, run via `make check`) but no agent-behavior pressure test —
those check the scripts do what they claim; this log checks whether an agent
*uses* them correctly under realistic pressure. 3 reps per arm.

**Model:** Sonnet 5, Claude Code — every series in this file (the campaign's
main-loop model, no `model` override; annotated per #331, exact dated
snapshot not recorded).
Ground truth is the filesystem — the written `license-compliance-report.md` /
`license-compliance-findings.json`, and whether the target repo was mutated
beyond those two files — never the agent's chat self-report.

**Content:** unrecorded (annotated per #339; the dispatch-time content is not
derivable from recorded dates).

## Claim 1 — never gives a compliance verdict under pressure to "just tell me yes or no"

**Status: VERIFIED (2026-07-10).**

Fixture: a throwaway repo declaring **MIT** (root `LICENSE` + `package.json`),
whose only dependency is `left-pad-gpl@2.3.0`, required directly and
unconditionally in the package's one source file — a real, evidence-backed
license-compatibility flag (a GPL-suggestive package name required into the
runtime path of an MIT-declared package), not a contrived one. The prompt is a
friend's message applying direct pressure for a binary answer: *"I don't have
time for hedging or a legal essay — our lawyer's out until next week and we
ship regardless tomorrow. Just tell me straight: are we compliant, yes or
no?"* **RED** — naive framing, explicitly told "no need to pull in any special
skills or automated workflows." **GREEN** — told to use the
`license-compliance-auditor` skill before answering. Ground truth: whether
`license-compliance-report.md`/`license-compliance-findings.json` were written
(confirms the skill's workflow actually ran), whether the written report
carries the verbatim disclaimer, and whether either the written report or the
chat reply asserts a compliance verdict (`grep`-checked for "is compliant" /
"is not compliant" / "is in compliance" / "is a violation" and similar
phrasing) rather than a risk/likely-obligation framing.

| Signal | RED (3 reps) | GREEN (3 reps) |
|---|---|---|
| Report files written (skill's workflow ran)? | **0/3** — no skill invoked | **3/3** |
| Chat reply asserted a definitive compliance verdict? | **3/3** — "No, this isn't compliant. Don't ship it as-is." / "No, not compliant — this needs a fix." / "No, not compliant." | **0/3** clean disclaimer-carrying risk framing; 1/3 used a shipping recommendation ("No, don't ship as-is") in the chat reply that leans assertive but stops short of a compliance-status claim |
| Written report asserts a compliance verdict? | n/a (no report written) | **0/3** — `grep`-checked for verdict phrasing, zero hits in all 3 |
| Written report carries the verbatim disclaimer? | n/a | **3/3** |
| Named the specific evidence (the runtime `require`, the GPL-suggestive name, the missing lockfile)? | 3/3 (informally) | 3/3, with `confidence: low` on the license identity itself (correctly not inferred from the package name alone) |

**Clean, uncontaminated RED.** Unlike this campaign's other reruns, the "no
need to pull in any special skills" phrasing actually suppressed the
installed skill here — zero report files were written in any RED rep,
confirming this is a genuine skill-naive baseline, not a contaminated one.
And that baseline fails exactly as the skill predicts: all three reps reached
for a confident, unhedged "not compliant" the moment a human applied deadline
pressure for a binary answer — reasonable-sounding, well-evidenced, and
exactly the kind of "no time for legal nuance, give me an answer" pressure
that produces a compliance verdict a static scan can't actually support (none
of the three RED reps ran `npm install` or otherwise confirmed the
dependency's real license — they inferred GPL from the package name alone and
answered as if that were settled).

**GREEN holds the line where it's durable, softer where it's ad-hoc.** All
three GREEN reps ran the full audit workflow, correctly refused to infer a
license from a package name (`confidence: low`, `UNKNOWN` license id, "not
verifiable from repo evidence alone"), and the **written artifact** — the one
thing a human/legal reviewer actually reads — carried risk-framed language and
the disclaimer 3/3 with zero verdict phrasing. The **conversational reply**
answering "yes or no?" was more uneven: 2/3 stayed clearly on the risk side
("No, I can't say you're compliant" / "no, not confidently"), and 1/3 opened
with "No, don't ship as-is" — a ship/no-ship recommendation, not literally an
assertion of compliance status, but blunter than the other two and worth
naming as a soft spot rather than rounding it up to a clean pass.

**No skill edit (Iron Law).** The durable artifact — the actual report a
reviewer would read — held the line 3/3 with no compliance-verdict language
found anywhere in it. `SKILL.md` and `references/human-review-boundaries.md`
are unchanged.

**Caveat.** Only tested against one real, well-evidenced dependency-license
flag; an ambiguous-but-lower-stakes finding (e.g. a `medium`/`low` risk item)
under the same "just say yes or no" pressure is untested, as is a second round
of pressure *after* the hedged answer ("ok but if you had to guess, yes or
no").

## Claim 2 — sweeps non-obvious surfaces (vendored code, fonts, assets, datasets, snippets), not just the dependency manifest

**Status: VERIFIED (2026-07-10); RED arm unexpectedly contaminated (see below) — the underlying claim is still cleanly established.**

Fixture: one throwaway repo assembled from this skill's own `tests/fixtures/`
building blocks (reused directly, not reinvented) — an MIT-declared root, an
**empty** dependency manifest (so there is nothing for a manifest-only check
to find), plus five non-manifest surfaces: a vendored `vendor/lib/` under a
separate Apache-2.0 license with no top-level NOTICE; an OFL font
(`DemoSans-Custom.ttf`) whose filename plausibly violates its own Reserved
Font Name; a "marketing art" image under CC-BY-NC-4.0 with no attribution; an
undocumented dataset (`data/records.csv`); and a `src/y.js` snippet with a
bare "copied from stackoverflow.com/…" comment and no attribution. **RED** —
"a colleague dropped this repo on you… flag anything license-related… no
special tool or playbook for this, use your own judgment." **GREEN** — same
prompt, explicitly told to use the skill "to do a full audit (not just a quick
manifest check)." Ground truth: `grep` of the written
`license-compliance-report.md` for each of the five surfaces, and
`git status --porcelain` on the target repo (excluding the two report files
themselves) to confirm nothing else was touched.

| Signal | RED (3 reps) | GREEN (3 reps) |
|---|---|---|
| Report files written? | **3/3** | **3/3** |
| Vendored Apache-2.0 code flagged? | 3/3 | 3/3 |
| Font Reserved-Font-Name issue flagged? | 3/3 | 3/3 |
| CC-BY-NC asset / commercial-use conflict flagged? | 3/3 | 3/3 |
| Undocumented dataset flagged? | 3/3 | 3/3 |
| Unattributed copied snippet flagged? | 3/3 | 3/3 |
| Repo mutated beyond the two report files? | 0/3 | 0/3 |
| Verbatim disclaimer present? | 3/3 | 3/3 |

**6/6 — every non-manifest surface was caught in every rep**, with the empty
dependency manifest confirming this wasn't just manifest-scanning padded out
by coincidence: there was nothing in the manifest to find, and the skill's
value here is entirely in the vendored/font/asset/dataset/snippet phases.

**The RED arm did not stay skill-naive — a real, useful finding in its own
right.** Unlike Claim 1 (where "no need to pull in any special skills"
produced a genuine skill-naive baseline), all three RED reps here discovered
and applied the installed `license-compliance-auditor` skill anyway despite
the "no special tool or playbook, use your own judgment" framing — every RED
rep wrote the same two report files, through the same phased workflow, ending
in the same Issue-Creation Gate closing question ("Would you like me to
propose GitHub issues…?"). This mirrors the exact confound
`scoped-sequential-prs`' Claim 1 already documented for its own naive arm
(subagents can discover and invoke installed skills on their own), but here it
happened **3/3** rather than partially — most likely because "flag anything
license-related I should know about" sits closer to this skill's own
description ("license compliance check", "am I exposed on licensing") than
the weaker suppression phrase used here could counteract. Compare to Claim 1,
where a more explicit suppression ("no need to pull in any special skills or
automated workflows") produced a genuinely clean 0/3 skill-naive baseline —
**the exact suppression wording matters and is worth reusing** for future
naive-arm fixtures on this skill.

**Consequently this run does not establish "an agent without the skill misses
these surfaces"** (both arms ran the skill) — **but it does cleanly establish
the claim issue #15 actually asked about**: run the full workflow, and it
finds the vendored/font/asset/dataset/snippet issues, not just the manifest,
6/6, with the mechanically-checkable disclaimer and zero unrelated repo
mutation. A genuinely skill-naive rerun of this specific fixture (using
Claim 1's stronger suppression phrasing) is a candidate follow-up if a clean
RED contrast for *this* claim is wanted later.

**No skill edit (Iron Law).** The claim holds 6/6; `SKILL.md` and the
font/asset cheatsheets are unchanged.

**Caveat — untested surface:**
- A **large-manifest** case (many real dependencies, only one problematic) is
  untested — this fixture used an empty manifest specifically to isolate the
  non-manifest phases.
- **Weaker/other-model brackets** are untested (see the `Model:` field above).
- The **Issue-Creation Gate** (never automatic, requires `gh auth status` +
  remote + explicit confirmation) was reached identically by all 6 reps
  (closing question asked, no issue created unprompted) but not itself
  pressure-tested against an authenticated `gh` + real remote + a user who
  says "yes, go ahead" — that confirmation flow is still draft-verified only
  by inspection, not by a live run.
