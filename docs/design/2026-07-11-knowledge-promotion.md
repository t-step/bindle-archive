# Design: knowledge promotion and durable project understanding

Resolves the design half of issue #81. Status: **approved design, not yet
implemented** — implementation issues reference this document as the product
source of truth. When an implementation question is not answered here, the
answer is decided in the implementation issue and folded back into this doc,
not improvised silently.

## Central principle

**A promoted decision is a cognitive cache.** Its purpose is not merely to
preserve rationale but to remove the need to repeatedly reconstruct or
relitigate the same conclusion. Every promoted decision therefore carries an
explicit revision condition, and is treated as settled until that condition
is met. The capability is not archiving decisions — it is buying back
thinking time.

Corollary for the whole artifact set: **evidence is the raw material;
understanding is the product.** Session notes, handoffs, issues, and PRs
remain where they are. What this capability adds is a small, curated,
human-owned reading surface over them.

## Problem

Bindle's notes home accumulates evidence artifacts — session notes,
handoffs, profiles, workflow reviews. They preserve history well and answer
"what happened" via grep. They do not answer, without reconstruction:

- what a project is trying to prove;
- why its important decisions were made, and when to reconsider them;
- which assumptions carry risk;
- what was learned that outlives the implementation;
- which lessons transfer to other projects;
- which questions are worth pursuing for their own sake.

The reconstruction cost is paid repeatedly: before meetings, in interviews,
when re-entering a project after weeks away, and — most expensively — when a
settled question is silently reopened.

## Goals

1. Per project, a single reading surface whose contract is: **recover the
   current mental model of the project in under five minutes.**
2. Promotion is evidence-grounded: every promoted item points at durable
   evidence; uncertainty is represented, never smoothed over.
3. Promotion is incremental: existing understanding is updated, not
   recreated and not appended forever.
4. Promotion is human-confirmed: the workflow proposes exact diffs; the
   owner approves before anything is written. Writing nothing is a valid and
   common outcome.
5. The MVP grows naturally toward the full promotion ladder (through
   cross-project patterns, areas of inquiry, and first principles) without
   redesign.

## Non-goals

- No database, index, or daemon (the SQLite index stays deferred per
  [sqlite-workflow-index.md](../sqlite-workflow-index.md)).
- No Obsidian plugin, no Obsidian-required features. Plain Markdown is the
  contract; Obsidian benefits are additive only.
- No transcript import, no copying evidence into understanding artifacts
  beyond one-line quotes.
- No replacement of session notes, handoffs, profiles, GitHub issues,
  `/workflow-review`, or `/promote-insight`. This capability adds one new
  route; the existing loop is untouched.
- No duplication of GitHub (issue state) or the project dashboard (live
  status). The map records *why*, not *what is open*.
- No automatic promotion. Consistent with
  [iterative-improvement.md](../iterative-improvement.md), nothing is
  written without the owner confirming the specific proposed text — here
  extended to notes-home understanding artifacts as well, because the map is
  a hand-curated document an agent must not clobber.
- Not a general knowledge-management system. Single user, few files, hard
  size caps.

## The promotion ladder

Every candidate insight is placed on exactly one rung (or discarded):

| Rung | Destination | Wave |
|---|---|---|
| 0. discard | nowhere — reported with reason | 1 |
| 1. map update | the project map's Brief / Assumptions / Open questions | 1 |
| 2. project decision | the map's Decisions section | 1 |
| 3. project learning | the map's Learnings section | 1 |
| 4. research topic | map Open questions with `inquiry?` tag → later `knowledge.md` Areas of inquiry | 1 (tag) / 2 (lift) |
| 5. cross-project pattern | map Learnings with `transfer?` tag → later `knowledge.md` Patterns | 1 (tag) / 2 (lift) |
| 6. first principle | later `knowledge.md` Principles | 2 |

Most candidates land at rungs 0–1. Rungs 4–6 are rare by design.

Routing boundary with the existing loop: **operational how-to-work facts**
(a CI failure signature, a build gate, a "never do X in this repo" rule)
are *not* understanding — they route through `/workflow-review` →
`/promote-insight` to profiles, skills, or project rules exactly as today.
The map holds understanding; the profile holds operations. The contract doc
must state this boundary with an example of each.

## Artifact contracts

### Wave 1: the project map

Path: `<notes-home>/projects/<project>/map.md` (same `<project>` slug rule
as all notes-home artifacts; see
[session-notes-format.md](../session-notes-format.md)).

Purpose (stated in the file itself): recover the current mental model in
under five minutes. Every section earns its place against that test.

```markdown
# <project> — map

updated: YYYY-MM-DD · evidence through: sessions/YYYY-MM-DD-<slug>.md

<!-- Purpose: recover the current mental model of this project in under
     five minutes. Owner-curated; /promote-knowledge proposes diffs. -->

## Brief
<!-- ≤15 lines: thesis (what this project is trying to prove or deliver),
     current direction, top ≤3 tensions. The five-minute path starts here. -->

## Decisions
<!-- Settled — do not relitigate unless the stated revisit-when condition
     is met. -->
### <one-line decision> (YYYY-MM, settled)
why: <1–2 lines>
so: <the future choice this influences / what to stop reconsidering>
revisit-when: <the evidence that would reopen this>
evidence: sessions/YYYY-MM-DD-<slug>.md, #NNN, `abc1234`

## Learnings
<!-- Durable; survives the current implementation. Optional tags:
     `transfer?` (pattern candidate), with the other project named. -->
### <one-line claim> (YYYY-MM)
why: … · so: … · revisit-when: …
evidence: …

## Assumptions & tensions
<!-- Risk-carrying assumptions with stated confidence; conflicting
     conclusions shown side by side with each side's evidence. -->

## Open questions
<!-- Worthwhile questions, including general-interest ones. Status
     open|parked. Tag `inquiry?` if the question outlives the project. -->

## Superseded
<!-- One line each: what was retired, when, what replaced it. -->
```

Contract rules:

- **Entry grammar** (Decisions and Learnings): claim line, then
  `why:` / `so:` / `revisit-when:` / `evidence:` — five lines maximum.
  `so:` must concretely answer at least one implication question (below);
  `revisit-when:` is mandatory for decisions, recommended for learnings;
  `evidence:` holds at least one durable pointer.
- **Size budget:** target ≤150 lines, hard cap 200. At the cap, nothing
  enters until something is compressed, demoted to a session note, or
  retired to Superseded. Deletion is promotion too.
- **Ownership:** the map is the owner's document. The workflow proposes
  minimal diffs against specific entries; it never regenerates the file,
  never reorders the owner's prose, and never edits lines outside the
  entries a proposal names.
- **The field set is the contract; exact formatting is convention** — same
  stance as session notes. Grep-ability of `so:` / `revisit-when:` /
  `evidence:` matters more than layout.

### Wave 2: the personal knowledge file

Path: `<notes-home>/knowledge.md`. One file, three sections — **Patterns**
(cross-project, evidence from ≥2 projects), **Principles**, **Areas of
inquiry** — governed by the same entry grammar, ownership rule, and a size
cap of its own. It splits into multiple files only when its own cap forces
it. Not built in wave 1; wave 1's `transfer?` / `inquiry?` tags are the
lift path, so nothing needs rewriting when it arrives.

A principle entry must contain all four of: the invariant; the decisions
that followed from it; the supporting evidence; the revision conditions.
The evidence bar is **multiple independent pieces of evidence** —
independent meaning different decisions, different times, or different
projects, not restatements of one event. Project count is explicitly not
the metric.

### The promotion report (output contract, not a file)

Every run of the workflow ends with — and the confirmation step is
formatted as — a three-part report:

```
Promoted   (proposed → confirmed): the exact diffs, per rung
Rejected   each with a one-line reason (no novelty / implementation
           detail / sounds-insightful-but-inert / weak evidence / …)
Deferred   each with what is missing (e.g. "pattern candidate — needs
           evidence from a second project; tagged transfer? in the map")
```

The report is ephemeral by design: deferred candidates persist as tags on
map entries, which is where the next run rediscovers them. No report files
accumulate.

## Workflow

### Shape

A **new command**, `/promote-knowledge [project]`, plus a provider-neutral
contract doc, `docs/knowledge-promotion.md` — the established pattern
(contract first, Claude automation second; Codex/human participation by
following the doc manually).

Why not an extension: `/workflow-review` routes *workflow friction* into
toolkit changes; `/promote-insight` routes a single classified insight into
toolkit/config homes. This capability routes *understanding* into knowledge
artifacts. Same cadence family, different inputs, different destinations,
different rules. Each command's doc cross-references the others ("wrong
kind of insight? use X").

### Phases

1. **Resolve and read.** Resolve the notes home; read `map.md` (if any) and
   all evidence newer than the map's `evidence through:` cursor — session
   notes, handoffs, profile changes — plus issues/PRs those notes
   reference (via `gh`, read-only, when available). First run on a project
   (no map) bootstraps from full history through the same propose→confirm
   gate.
2. **Generate candidates.** Each candidate is placed on the ladder and
   screened by the promotion rules. This phase is delegated to the
   read-only scout agent when available (below); the command works without
   it.
3. **Propose.** At most **5 proposed changes per run**, ranked by
   consequence, presented as exact diffs in promotion-report format,
   with the Rejected and Deferred lists alongside.
4. **Confirm.** The owner approves all, some, or none. No confirmation, no
   write.
5. **Apply and close.** Apply confirmed diffs, advance the cursor line,
   emit the final report.

Hard properties: **read-only toward every project repo**; writes touch only
`map.md` (wave 2 adds `knowledge.md`); idempotent — re-running with no new
evidence proposes nothing.

### The scout agent

`agents/knowledge-scout.md` (draft until pressure-tested, per
CONTRIBUTING): a read-only subagent that digests the evidence set and
returns rung-classified candidates with evidence pointers. It exists for
context economy on large evidence sets and is the natural candidate for
issue #7's first published agent alongside #80's drift auditor. The command
must degrade gracefully to inline reading when the agent is unavailable.

### Cadence

On demand — recommended every ~5–10 sessions per project, or before a
meeting, interview, or return-from-absence. No session-end hook, no
automation in wave 1.

## Promotion rules

All objective; each rejection cites the rule it failed. Writing nothing is
a valid, expected outcome.

- **Novelty.** Not already in the map. The proposal must cite the existing
  entry it was checked against (or state "no related entry"), so the check
  is auditable at confirm time rather than trusted. A refinement of an
  existing entry becomes an update to that entry, never a sibling.
- **Consequence.** The candidate must fill `so:` with a concrete answer to
  at least one of: What future decision should this influence? What should
  the owner do differently? What should the owner now be able to explain?
  Where else might this apply? What worthwhile question does this create?
  What evidence would change this conclusion? Generic-advice filter: a
  `so:` line that would be equally true in any project's map fails for a
  project map. General-interest candidates are valid — they land in Open
  questions — but must fill the inquiry implication concretely; observations
  that merely sound insightful are rejected by this rule.
- **Durability.** Still true if the current branch, PR, or implementation
  detail vanished; contains no session mechanics; plausibly matters in six
  months.
- **Evidence.** At least one durable pointer (session note, issue, PR,
  commit, committed doc). Patterns: evidence from ≥2 projects. Principles:
  multiple independent pieces of evidence as defined above; `revisit-when:`
  mandatory.
- **Uncertainty.** Unsettled or contested candidates land in Assumptions &
  tensions with confidence stated; conflicting evidence is shown on both
  sides, never silently resolved.
- **Volume guard.** ≤5 proposals per run, ranked decisions → learnings →
  tensions/questions, ties broken by the breadth of the `so:` line; the
  ranking is visible in the report and the rest land in Rejected/Deferred
  with reasons. Exception: the bootstrap run may propose up to the map's
  size budget (it is still confirm-gated); every later run obeys the guard.
- **Routing guard.** Operational facts route to the existing loop
  (profile/skills/rules), not the map.

## Update rules

- **Cursor.** `evidence through:` names the newest session note processed.
  "Evidence newer than the cursor" means notes-home files (sessions,
  handoffs, profile edits) whose date-stamped name or mtime is after the
  cursor note's date. Idempotence is defined against the cursor.
- **User edits.** Preserved by construction: proposals are minimal diffs
  against named entries; owner-authored lines outside a named entry are
  never touched. A proposal that would alter an owner-edited entry must say
  so explicitly in the diff.
- **Supersede.** A superseded decision/learning gets its status flipped and
  a one-line tombstone moved to Superseded pointing at what replaced it.
  Nothing is deleted silently; the tombstone is the audit trail.
- **Conflicts.** Two live conclusions that disagree both go to Assumptions
  & tensions, each with its evidence. The workflow never picks a winner
  without the owner.
- **Relitigation flag.** New evidence that *meets* a decision's
  `revisit-when:` condition produces a proposed revision. Session activity
  that re-argues a settled decision *without* meeting the condition is
  flagged in the report as relitigation — a finding in its own right (the
  cognitive cache is being bypassed).
- **Duplicates.** Killed by the novelty rule at generation time and by the
  owner at confirm time; two lines of defense.

## Evidence linking

- Notes-home artifacts: relative Markdown links whose target is the
  session/handoff file (link text "note" or the slug, target
  `sessions/<date>-<slug>.md`) — they render in Obsidian, editors, and
  GitHub alike, and stay greppable. Bare relative paths are acceptable
  where a link would be noise. (Examples in this design doc show bare
  paths only because the repo's link checker rightly refuses targets
  outside the repo.)
- Issues/PRs: bare `#NNN` where the project's tracker is unambiguous,
  `owner/repo#NNN` otherwise.
- Commits: short hashes in backticks.
- Quotes from evidence: one line maximum. Understanding artifacts never
  absorb evidence bodies.

## Obsidian stance

The notes home may be opened as an Obsidian vault (planned, not yet true
for the owner). The contract is plain Markdown: no plugins, no Dataview, no
required frontmatter, no wikilinks. Relative links give Obsidian backlinks
and graph edges for free. Nothing in the workflow may depend on a vault
existing.

## Privacy

Maps and `knowledge.md` live in the notes home: private by default, blunt
assessments welcome, local paths fine. If any part is ever exported into a
repo, PR, or shared doc, the existing repo-bound recipe applies unchanged —
separate sanitized artifact, `bin/check-private-info.sh` pass, block on the
result ([privacy-boundaries.md](../privacy-boundaries.md)). The workflow
itself never writes to a repo.

## Worked examples

### Valence (from `sessions/2026-07-11-registry-disposition-mirror-eligibility.md`)

**Promoted — decision (rung 2):**

```markdown
### Disposition is not rights status — the registry retains what it cannot host (2026-07, settled)
why: conflating "may we mirror it" with "does it exist" forced dishonest
  deletion; separate axes let custody-recorded be a valid terminal state
  ("blocked ≠ absent, excluded ≠ deleted").
so: registry features must never collapse the two axes; stop reconsidering
  whether rights-blocked assets belong in the registry — they do, as records.
revisit-when: upstream's claims-ledger work (#276) merges a representation
  that collapses or replaces the disposition axis.
evidence: sessions/2026-07-11-registry-disposition-mirror-eligibility.md,
  domattioli/Valence#162, domattioli/Valence#305
```

**Promoted — learning with transfer tag (rung 3, pattern candidate):**

```markdown
### Fail closed at integration seams (2026-07) `transfer?` (bindle: installer conflict-safety)
why: `rights_ok_domains` defaults to empty ⇒ nothing publishes without an
  explicit rights verdict; the seam is safe by default, not by discipline.
so: when two contexts meet (rights × publishing), compute the effective
  permission at the seam and default it to "no".
evidence: sessions/2026-07-11-registry-disposition-mirror-eligibility.md, `097bae7`
```

**Rejected (routing guard):** the Actions-billing-outage signature
("all jobs fail in 1–3s, zero steps, BlobNotFound") — operational
diagnostic, routes to the Valence *profile* via the existing loop. The
session note's own "candidate workflow improvements" already said so.

**Deferred (pattern):** "fail closed at integration seams" needs its second
project's evidence made explicit before lifting to `knowledge.md` — tagged
`transfer?` in the map, naming Bindle's installer as the candidate.

### Bindle

**Promoted — decision (rung 2):**

```markdown
### Schemas earn admission by a present consumer (2026-07, settled)
why: the capability inventory (#29) was deferred for months as "speculative
  schema" until doctor/dashboard consumers existed; admitting it early would
  have produced an unconsumed format to maintain.
so: reject manifest/index/inventory proposals that cannot name a consumer
  that would read them this release; stop reconsidering the deferred SQLite
  index until grep demonstrably hurts.
revisit-when: a proposal arrives whose consumer exists but is external
  (dashboard, doctor) and the format question reopens.
evidence: docs/product-boundary.md, #29, #79, docs/sqlite-workflow-index.md
```

**Promoted — open question with inquiry tag (rung 4):**

```markdown
- Why do pressure-test RED arms go invalid (harness skill-index lag after
  unlink) — and what does that generalize to about testing agentic systems
  whose capability surface is cached outside the filesystem? `inquiry?`
  (open) — evidence: sessions/2026-07-10-pressure-test-repo-hygiene-init.md
```

**Cross-project (wave 2 preview):** Valence's fail-closed seam + Bindle's
installer conflict-safety + the fail-closed publish gate ⇒ pattern
"at trust boundaries, absence of proof means no" — and, if further
independent evidence accumulates, a candidate first principle.

## Acceptance tests

Method: the pressure-test discipline — fixture notes homes with synthetic
session notes, fresh subagents running the workflow, results scored on the
filesystem (not self-report), recorded per
[CONTRIBUTING.md](../../CONTRIBUTING.md). Scenarios and their observable
pass conditions:

1. **No novelty.** Evidence restates existing map entries → zero proposed
   diffs; report says why.
2. **Repeated sessions / idempotence.** Run twice on the same evidence →
   second run proposes nothing; map byte-identical; cursor unchanged.
3. **Conflicting conclusions.** Two notes reach opposite conclusions → one
   proposal, into Assumptions & tensions, both sides with evidence; the
   workflow does not pick a winner.
4. **Superseded decision.** New evidence meets a `revisit-when:` → proposal
   flips status and writes the Superseded tombstone; the original owner
   prose is not deleted, only moved/marked.
5. **Cross-project learning.** Wave 1: refused with a Deferred entry and a
   `transfer?` tag proposal; never writes outside the project's map.
6. **Weak evidence.** Candidate with no durable pointer → Rejected citing
   the evidence rule.
7. **Human-edited map.** Owner-authored lines outside proposed entries are
   byte-identical after a confirmed run.
8. **Too many candidates.** >5 valid candidates → exactly 5 proposals,
   ranked by consequence; the rest in Rejected/Deferred with reasons.
9. **General-interest learning.** A non-actionable but inquiry-worthy
   question → accepted into Open questions with the inquiry implication
   filled; a merely thoughtful-sounding observation → Rejected by the
   consequence rule.
10. **Relitigation.** A synthetic note re-argues a settled decision without
    meeting its condition → flagged in the report; no map change proposed.

Plus the retrieval test: after seeding real maps (dogfood issue), the eight
briefing questions ("brief me before I meet a domain expert", "why this
architecture", "what assumptions carry risk", "what transfers", "interview
explanation", "which principles are supported by decisions", "what
non-actionable question emerged", "what should I stop reconsidering") must
be answerable from the map alone in one read.

## Migration

None. New files only; no existing artifact changes shape. Profiles keep
their operational role. The first run on a project with history is the
bootstrap (phase 1 above). No notes-home layout change; `map.md` simply
joins `profile.md` beside `sessions/` and `handoffs/`.

## Implementation plan

Wave 1, in order (one issue each; full implementation packets live in
`docs/plans/`, issue bodies stay short — recent issue bodies have been
truncated at ~500 bytes (#61, #80, #81), so the packet in the repo is the
source of truth and the issue points at it):

1. **Contract doc** — `docs/knowledge-promotion.md`: ladder, rules, map
   format, report format, routing boundary, manual (Codex/human)
   procedure. Inventory classification for the new doc (ledger entry or
   contract row, per the inventory's own conventions). `make check` green.
2. **Command + agent** — `commands/promote-knowledge.md` +
   `agents/knowledge-scout.md` (draft): the five phases, confirm gate,
   volume guard, cursor handling; `capabilities.json` rows for both (the
   bound-table footgun); CHANGELOG entries marked draft.
3. **Acceptance scenarios** — fixture notes homes + the ten scenarios
   above, scored on the filesystem; results recorded
   (`docs/knowledge-promotion-pressure-tests.md` or per-asset records).
4. **Dogfood** — bootstrap real maps for Valence and Bindle via the
   workflow; record friction and misroutes; feed corrections back into the
   contract doc. The retrieval test runs here.

Wave 2 (separate issue, explicitly deferred until wave 1 evidence exists):
`knowledge.md` (Patterns / Principles / Areas of inquiry), the tag-lift
procedure, and the principle evidence bar.

Suggested model strength: contract doc and dogfood need a strong model
(judgment-heavy); scenario reps are mechanical once designed (weaker model
fine) with strong-model scoring, per the established pressure-test
delegation pattern.

## Future work (recorded, not committed)

- `/session-start` orientation reading the map's Brief (the five-minute
  path becoming the session's warm start).
- Surfacing relitigation flags at session start ("this session's plan
  re-opens a settled decision").
- `knowledge.md` growth: split-on-cap, principle promotion campaigns.
- The SQLite index, only if grep over maps ever hurts (unlikely at these
  sizes).

## Resolved design questions (for the implementer)

- One file per project; decisions/learnings are sections, not files.
- Briefing view = the map's Brief section; no separate artifact.
- New command; `/workflow-review` and `/promote-insight` untouched.
- Write ceremony: propose-diff → confirm → write, always, including
  notes-home writes.
- `revisit-when:` (not "unless") — it is a condition, not a caveat.
- Principles bar: independent evidence, not project count.
- Promotion report: mandatory output contract, ephemeral; deferred state
  lives as map tags.
- Research topics: rung 4, `inquiry?` tag now, `knowledge.md` home later.
