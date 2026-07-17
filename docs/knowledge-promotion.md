# Knowledge promotion — the provider-neutral contract

How accumulated project evidence becomes durable understanding: a living
per-project **map** that a returning mind can read in minutes, updated
through an explicit propose → confirm → write ceremony. This document is
the contract; any assistant (or human) that can read and write Markdown
can follow it. Claude Code automates it with the `/promote-knowledge`
command; the design record is
[docs/design/2026-07-11-knowledge-promotion.md](design/2026-07-11-knowledge-promotion.md)
(issue #81). Scope here is **wave 1**: per-project maps only.

## Purpose and central principle

**A promoted decision is a cognitive cache.** Its purpose is not merely to
preserve rationale but to remove the need to repeatedly reconstruct or
relitigate the same conclusion. Every promoted decision therefore carries
an explicit revision condition, and is treated as settled until that
condition is met. This capability is not archiving decisions — it is
buying back thinking time.

**Evidence is the raw material; understanding is the product.** Session
notes, handoffs, profiles, issues, and PRs stay where they are. The map is
a small, curated, owner-controlled reading surface over them, with one
contract: **recover the current mental model of the project in under five
minutes.** Every section, entry, and line earns its place against that
test.

## The promotion ladder

Every candidate insight lands on exactly one rung, or is discarded:

| Rung | Destination | Wave |
|---|---|---|
| 0. discard | nowhere — reported with the rule it failed | 1 |
| 1. map update | the map's Brief / Assumptions & tensions / Open questions | 1 |
| 2. project decision | the map's Decisions section | 1 |
| 3. project learning | the map's Learnings section | 1 |
| 4. research topic | Open questions with an `` `inquiry?` `` tag | 1 (tag only) |
| 5. cross-project pattern | Learnings with a `` `transfer?` `` tag | 1 (tag only) |
| 6. first principle | a personal knowledge file | 2 — out of scope |

Most candidates land at rungs 0–1; rungs 4–6 are rare by design. In
wave 1, rungs 4–5 exist only as tags — the tag records the lift candidate
so nothing needs rewriting when wave 2 arrives. Rung 6 must never be
written in wave 1; a would-be principle that *survives the promotion
rules* is recorded as a deferred item — one that fails a rule (e.g. the
consequence rule's generic-advice filter) is rejected with that rule,
not deferred.

## What routes elsewhere

The map holds *understanding*; operational how-to-work facts route through
the existing loop in
[iterative-improvement.md](iterative-improvement.md) to profiles, skills,
project rules, or checks. Two contrasting examples:

- "On a private repo, CI jobs failing in 1–3 s with zero steps means an
  Actions spending-limit outage, not a code defect" — **operational
  diagnostic → the project profile** (via `/promote-insight`), not the map.
- "The registry retains rights-blocked assets as records rather than
  deleting them, because disposition and rights are separate axes" —
  **understanding → the map's Decisions.**

Workflow friction (repeated manual steps, recurring failure modes in *how
you work*) stays with `/workflow-review`. Wrong-kind candidates are
rejected with the `routing` rule, naming the right destination.

## The project map

### Path and ownership

`<notes-home>/projects/<project>/map.md` — beside `profile.md`,
`sessions/`, and `handoffs/`. Notes-home resolution, the `<project>` slug
rule, and privacy posture are owned by
[session-notes-format.md](session-notes-format.md); this contract does not
redefine them. Create directories on demand (`mkdir -p`).

The map is **the owner's document**. A promotion workflow proposes minimal
diffs against specific entries; it never regenerates the file, never
reorders the owner's prose, and never edits lines outside the entries a
confirmed proposal names.

### File template

````markdown
# <project> — map

updated: YYYY-MM-DD · evidence through: <sessions-filename or "none">

<!-- Purpose: recover the current mental model of this project in under
     five minutes. Owner-curated; /promote-knowledge proposes diffs. -->

## Brief

## Decisions

## Learnings

## Assumptions & tensions

## Open questions

## Superseded
````

All six `##` sections are always present, in this order, even when empty.
The Brief holds ≤15 lines: the thesis (what the project is trying to prove
or deliver), the current direction, and the top ≤3 tensions — the
five-minute path starts and often ends here. **The field set is the
contract; exact formatting is convention** (grep-ability of the field
names matters more than layout — the same stance session notes take).

### Entry grammar

Decisions and Learnings (Decisions are settled — do not relitigate unless
the stated condition is met):

```markdown
### <one-line claim> (YYYY-MM, settled) <!-- bindle:context-id: context-node:<slug>:<32-hex> -->
why: <1–2 lines>
so: <concrete answer to at least one implication question>
revisit-when: <the evidence that would reopen this>
evidence: <ptr>[, <ptr>…]
```

- Status token: `settled` or `superseded`. Learnings omit the status token.
- `revisit-when:` is mandatory for Decisions, recommended for Learnings.
- Optional tags at the end of a Learning claim line: `` `transfer?` ``
  (name the other project in parentheses) or `` `inquiry?` ``.
- Five lines maximum per entry: the claim line plus the four field lines
  (the identity marker rides on the claim line and doesn't count against it).
- The identity marker (see "Stable identities" below) is present on every
  *newly* confirmed entry. An existing entry promoted before #179 has no
  marker and stays that way until the separate #183→#184→#185 anchoring
  workflow explicitly reaches it — this contract never adds one as a side
  effect of an unrelated update.

Assumptions & tensions:

```markdown
- <assumption or tension> — confidence: high|medium|low — evidence: <ptr> <!-- bindle:context-id: context-node:<slug>:<32-hex> -->
```

A conflict is one bullet with two indented sub-bullets, one per side, each
carrying its own evidence. Conflicts are represented, never silently
resolved. The identity marker goes on the parent bullet only — the two
sides are structured content of that one entry and never carry a marker of
their own.

Open questions (general-interest questions are welcome here — the bar is a
concrete inquiry implication, not immediate actionability):

```markdown
- <question> (open|parked) — so: <inquiry implication> — evidence: <ptr> [`inquiry?`] <!-- bindle:context-id: context-node:<slug>:<32-hex> -->
```

Superseded (the audit trail — nothing is deleted silently). A tombstone is
**typed**: it names the retired entry's kind and preserves that entry's
identity, plus an optional identity-based pointer at whatever replaced it:

```markdown
- <kind>: <claim> (retired YYYY-MM) → <human-readable replacement or reason> <!-- bindle:context-id: <retired-id> --> [<!-- bindle:superseded-by: <replacement-id> -->]
```

- `<kind>` is `decision`, `learning`, `assumption`, `tension`, or `question`.
- The tombstone's `bindle:context-id` is the **retired** entry's own id,
  copied unchanged — never a new allocation. For a Decision or Learning this
  duplicates the id already sitting on that entry's still-present, now
  `superseded`-flagged heading (see Supersession below); that pairing is
  expected, not a duplicate-id conflict.
- `bindle:superseded-by` is present **only** when a specific replacement
  entry exists, and names that replacement's own (newly allocated) id — never
  the retired id, never a heading or claim string. Its human-readable prose
  (`→ …`) is presentation only and never substitutes for this identity
  pointer; the deterministic direction later consumed by #183/#184 is
  `replacement --supersedes--> retired entry`.
- A tombstone with no `<kind>:` prefix, or with a `bindle:context-id` that
  doesn't resolve to any entry's own marker, is reported by
  `bin/map-entry-id.py validate` as an untyped/incomplete tombstone — never
  auto-repaired. Every map written before #179 has untyped tombstones; that
  is expected and not an error on its own.

### Stable identities

**Contract, from #179.** Every newly confirmed top-level entry above
receives one opaque, durable identity, in the exact form:

```text
context-node:<creation-project-slug>:<32-lowercase-hex>
```

stored as an inline HTML comment (`<!-- bindle:context-id: ... -->`) on the
entry's own anchor line — the claim heading for a Decision/Learning, the
top-level bullet for a single Assumption, a tension's parent bullet, or an
Open question. Indented field lines and tension sides are structured content
of their parent entry and never receive one.

- **Allocation is command-owned, not model-owned.** `bin/map-entry-id.py
  allocate --project <slug>` prints one new id, using
  `secrets.token_hex(16)` for the hex suffix. The slug is the project slug
  in effect at the moment of allocation — an opaque historical label,
  independent of claim text, section, status, date, or evidence, and never
  rewritten if the project is later renamed. No assistant, model, or
  provider ever invents or edits the entropy or the final id.
- **Two authorized callers only.** This knowledge-promotion contract, for
  newly promoted entries (this document); and #184 anchor acceptance, for
  existing unanchored entries reaching that issue's explicit
  preview-and-confirm lifecycle. No other surface — labels, content hashes,
  heading text, GitHub, Git — ever chooses a semantic id.
- **Durable once written.** An id is preserved across every later update,
  tag, section move, and supersession. Editing an entry's heading, evidence,
  status, date, or field lines never recomputes or replaces its id. A valid
  existing id is never silently replaced; a malformed or duplicate one is
  reported by `bin/map-entry-id.py validate`, never repaired automatically.
- **Distinct entries, distinct ids.** Two allocations are always distinct
  (cryptographically). A replacement entry — even one whose claim text and
  section exactly match the entry it replaces — always gets a freshly
  allocated id; it never reuses the retired entry's id.
- **Existing maps are untouched.** This contract's scope is newly promoted
  entries only. An entry promoted before #179 has no marker and stays
  byte-identical; anchoring it is the separate #183→#184→#185 workflow, out
  of scope here.
- **Validation is read-only.** `bin/map-entry-id.py validate --map
  <path>` deterministically discovers every anchored/unanchored entry and
  reports malformed ids, duplicate ids, markers on an unsupported location
  (a field line, a tension side, anywhere outside the six defined entry
  shapes), multiple markers on one entry, untyped retirement tombstones, and
  malformed/duplicate/self-referential/unresolved `bindle:superseded-by`
  metadata. It never writes to the map under any circumstance, success or
  failure.

### Size budget

Target ≤150 lines, hard cap 200 (`wc -l`). At the cap, no entry enters
until an existing one is compressed, demoted back to a session note, or
retired to Superseded — a proposal at the cap must pair its addition with
a removal. Deletion is promotion too.

## Cursor semantics

- The `evidence through:` value is the **filename** (not path) of the
  newest session note processed, or `none` before the first run.
- "Evidence newer than the cursor" means the project's notes-home files —
  `sessions/*.md` and `handoffs/*.md` by date-stamped filename,
  `profile.md` by mtime — dated after the cursor note's date.
- **A completed run always advances the cursor**, including a run where
  the owner confirms nothing. The cursor-line update (and its `updated:`
  date) is the only map edit applied without itemized confirmation — it is
  announced, not asked. Consequence: rejected and deferred candidates are
  not re-proposed unless *new* evidence raises them again.
- An **aborted** run — interrupted before confirmation completes — writes
  nothing at all, cursor included.
- **Bootstrap** (no `map.md` yet): process the project's full history
  through the same propose → confirm gate, then create the map once — the
  template with the confirmed entries (if any) in place and the cursor
  set. Even a confirm-none bootstrap creates the skeleton: the map's
  existence records that history was processed. Exception: a project with
  **zero** evidence files has no history to record — write nothing.
- Idempotence follows: re-running with no new evidence proposes nothing
  and changes nothing.

## Evidence pointers

- Notes-home artifacts: relative Markdown links from the map (target
  `sessions/<date>-<slug>.md` or `handoffs/…` — the map lives beside those
  directories), or bare relative paths where a link would be noise. Both
  render in editors and Obsidian and stay greppable.
- Issues and PRs: bare `#NNN` where the project's tracker is unambiguous;
  `owner/repo#NNN` otherwise.
- Commits: short hashes in backticks.
- Quoting evidence: one line maximum. Understanding artifacts never absorb
  evidence bodies.

## Promotion rules

All objective; every rejection cites the rule it failed. **Writing nothing
is a valid and common outcome.**

- **Novelty.** Not already in the map. A proposal must cite the existing
  entry it was checked against (or state "no related entry"), so the check
  is auditable at confirm time. A refinement of an existing entry becomes
  an update to that entry, never a sibling.
- **Consequence.** The candidate must fill `so:` with a concrete answer to
  at least one of: What future decision should this influence? What should
  the owner do differently? What should the owner now be able to explain?
  Where else might this apply? What worthwhile question does this create?
  What evidence would change this conclusion? Generic-advice filter: a
  `so:` line equally true in any project's map fails for a project map.
  Observations that merely sound insightful fail this rule; genuine
  general-interest questions pass it by filling the inquiry implication.
- **Durability.** Still true if the current branch, PR, or implementation
  detail vanished; no session mechanics; plausibly matters in six months.
- **Evidence.** At least one durable pointer (session note, issue, PR,
  commit, committed doc) that records the claim's *support* — a decision
  made, an outcome observed. A note that merely voices an unreproduced
  hunch or half-remembered incident (no log, issue, commit, or
  reproduction behind it) is not evidence for the claim it voices —
  reject under this rule. A tagged pattern candidate (`transfer?`) names
  the second project it might transfer to.
- **Uncertainty.** Unsettled or contested candidates land in Assumptions &
  tensions with confidence stated; conflicting evidence is shown on both
  sides.
- **Routing.** Operational facts go to the iterative-improvement loop, not
  the map (see "What routes elsewhere").
- **Volume guard.** At most **5 proposals per run**, ranked rung 2 → rung
  3 → rungs 1/4/5, ties broken by the breadth of the `so:` line; the
  ranking is stated in the report and everything else lands in Rejected or
  Deferred with reasons. Exception: a bootstrap run may propose up to the
  map's size budget (still confirm-gated); every later run obeys the
  guard.

## Update rules

- **Minimal diffs.** Proposals target named entries; owner-authored lines
  outside a named entry are never touched. A proposal that would alter an
  owner-edited entry must say so explicitly.
- **Supersession.** A superseded decision or learning gets its status
  flipped and a one-line typed tombstone in Superseded pointing at what
  replaced it. The status-token flip is the only edit the retired entry
  receives — its claim text, field lines, and identity marker stay
  byte-intact; any replacement enters as a *new* entry with a freshly
  allocated identity (see "Stable identities" above). The tombstone carries
  the retired entry's existing id (copied, never reallocated) and, when a
  specific replacement exists, that replacement's id as
  `bindle:superseded-by` — never invented, never the retired id repeated.
  Superseding an entry that predates #179 and was never anchored carries no
  id to copy — its tombstone gets the `<kind>:` prefix and the human-
  readable reason like any other, but no `bindle:context-id`. That never
  retroactively anchors the retired entry itself; anchoring existing
  entries stays out of scope here (the #183→#184→#185 workflow). The new
  *replacement* entry still gets a freshly allocated id like any other
  confirmed `add` — supersession's identity rules are about the retired
  side, not the replacement side.
- **Relitigation.** New evidence that *meets* a decision's `revisit-when:`
  condition produces a proposed revision, applied as a supersession —
  never a rewrite of the settled entry in place, and never deferred to
  wait for a replacement: when no replacement decision exists yet, the
  tombstone points at the triggering evidence or an Open question. Activity that re-argues a
  settled decision *without* meeting the condition is flagged in the
  report as relitigation — a finding in its own right (the cognitive cache
  is being bypassed) — and produces no map change.
- **Duplicates.** Killed by the novelty rule at generation time and by the
  owner at confirm time.
- A hand-edited map missing a `##` section header gets the header re-added
  as part of the next confirmed write; existing content is never
  reordered.

## The promotion report

Every run ends with — and the confirmation step is formatted as — a
three-part report: **Promoted** (the proposed exact edits, numbered, with
ranking), **Rejected** (one line + the rule each), **Deferred** (one line
+ what is missing), plus any **Relitigation** flags. The report is
ephemeral by design: deferred state survives as tags on map entries, which
is where the next run rediscovers it. No report files accumulate.

The machine-readable form (also the handoff shape between an evidence
scout and the workflow that owns propose/confirm/write):

```yaml
candidates:            # ≤5 after ranking (bootstrap: up to the size budget)
  - rung: 1|2|3|4|5    # 6 is wave 2 and must not appear
    action: add|update|supersede|tag
    section: brief|decisions|learnings|assumptions|questions
    related_entry: <existing claim line, or null>   # the novelty citation
    claim: <one line>
    why: <1–2 lines>
    so: <one line>
    revisit_when: <one line>        # required when rung == 2
    evidence: [<ptr>, …]            # ≥1 durable pointer
rejected:
  - {summary: <one line>, rule: novelty|consequence|durability|evidence|routing}
deferred:
  - {summary: <one line>, missing: <one line>}
relitigation:
  - {decision: <claim line>, activity: <evidence ptr>, condition: <revisit-when text>, met: false}
```

Proposal rendering at the confirm step: each numbered proposal shows the
complete entry text as it would appear in the map, plus its anchor — the
target section and, for `update`/`supersede`, the existing claim line
being modified. The rendered entry *is* what gets written on confirmation.
The rendered preview never shows an identity marker: an `add` or a
`supersede`'s replacement entry has no id yet at proposal time (see "Stable
identities" — allocation happens only during the confirmed write, never
speculatively for a candidate that might be rejected).

## Manual procedure

Any assistant or human can execute this contract directly (Claude Code
automates the same steps as `/promote-knowledge`):

1. Resolve the notes home and project per
   [session-notes-format.md](session-notes-format.md); `mkdir -p` what is
   missing.
2. Read `projects/<project>/map.md`; note the cursor. No map → bootstrap.
3. List evidence newer than the cursor (see Cursor semantics). None →
   report "nothing new", stop; write nothing.
4. Read the evidence; where notes reference issues or PRs and a read-only
   viewer is available, read those too — **read-only toward every
   repository, no exceptions**.
5. Generate candidates; screen each against the Promotion rules; classify
   the survivors and casualties into the report shape above.
6. Present the promotion report with rendered proposals.
7. Take the owner's confirmation: `all`, `none`, or a list of proposal
   numbers. Anything else: re-ask once, then treat as `none`.
8. Apply exactly the confirmed subset as minimal edits. On bootstrap with
   `none`, still create the skeleton. For each confirmed `add`, and for the
   replacement side of each confirmed `supersede`, allocate one identity —
   `bin/map-entry-id.py allocate --project <slug>` — and write its marker
   as part of the same edit that writes the entry; never ask a model to
   invent one, never persist a marker separately from its entry. A
   confirmed `update` or `tag` leaves any existing marker untouched. A
   confirmed `supersede` also writes the typed tombstone, copying the
   retired entry's existing id and (only when a specific replacement
   exists) the replacement's newly allocated id as `bindle:superseded-by`.
   `none`, a rejected/deferred candidate, or a run interrupted before this
   step completes allocates and persists no identity at all — no pending-id
   side file exists anywhere in this contract.
9. Advance the cursor and `updated:` date; announce it.
10. Summarize: promoted / rejected / deferred counts and the new cursor.

## Privacy

Maps are notes-home artifacts: private by default, blunt assessments
welcome, local paths fine. If any part is ever exported into a repo, PR,
or shared doc, the standard repo-bound recipe applies unchanged — a
separate sanitized artifact checked with `bin/check-private-info.sh`,
blocking on the result (see
[privacy-boundaries.md](privacy-boundaries.md)). The promotion workflow
itself never writes into any repository.

## Out of scope (wave 1)

- The personal knowledge file (patterns / principles / areas of inquiry)
  and any rung-6 write — wave 2, tracked separately.
- Any database or index (see
  [sqlite-workflow-index.md](sqlite-workflow-index.md) for the standing
  deferral), any Obsidian-specific feature, any session-start/-end hook
  integration, any automatic (unconfirmed) promotion.
