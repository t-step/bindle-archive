# Packet 1 — provider-neutral knowledge-promotion contract and map format

Implements the contract layer of
[`docs/design/2026-07-11-knowledge-promotion.md`](../design/2026-07-11-knowledge-promotion.md)
(issue #81, wave 1). Read that design in full first; it is authoritative for
every product question. This packet specifies only the implementation slice.

## 1. Objective

Create `docs/knowledge-promotion.md`: the provider-neutral contract that
defines the promotion ladder, the project-map format, cursor and evidence
semantics, the promotion-report and candidate data shapes, and a manual
execution procedure — so that the workflow exists as a followable document
before any Claude automation.

## 2. Why this packet exists

Bindle's pattern (see `docs/product-boundary.md`, "Provider boundary") is
contract doc first, provider automation second. Packets 2–3 implement
automation *of this document*; defining the shapes here prevents the command
and the scout from each inventing their own.

## 3. Dependencies

None. First packet. (The design doc is already committed on this branch.)

## 4. Exact scope

One new contract doc, one `capabilities.json` row, one CHANGELOG line.

`docs/knowledge-promotion.md` must contain, in this order:

1. **Purpose and central principle** — the cognitive-cache paragraph and the
   map's contract line ("recover the current mental model of the project in
   under five minutes"), taken from the design's "Central principle" and
   "Goals" sections (restate, do not link-and-omit).
2. **The promotion ladder** — the design's 7-row table (rungs 0–6) plus the
   wave-1 boundary: rungs 0–3 land in the map; rungs 4–5 land as
   `inquiry?` / `transfer?` tags; rung 6 and the `knowledge.md` file are
   wave 2 and out of scope.
3. **Routing boundary** — operational facts route to
   `docs/iterative-improvement.md`'s loop (profile/skills/rules); the map
   holds understanding. Include exactly two examples: a CI-outage signature
   (routes to profile) vs. an architecture decision (routes to map).
4. **The project map contract** — path
   `<notes-home>/projects/<project>/map.md` (notes-home resolution and
   `<project>` slug rule by reference to `docs/session-notes-format.md`,
   which owns them); the full file template; the entry grammar; the size
   budget; the ownership rule. Normative details in §7 below.
5. **Cursor semantics** — normative details in §7.
6. **Evidence pointer rules** — relative Markdown links or bare relative
   paths to notes-home files; `#NNN` / `owner/repo#NNN` for issues and PRs;
   short commit hashes in backticks; quotes from evidence limited to one
   line.
7. **Promotion rules** — the six rules from the design (novelty with cited
   check target, consequence via the six implication questions plus the
   generic-advice filter, durability, evidence, uncertainty, routing guard)
   and the volume guard (≤5 proposals per run; bootstrap exempt up to the
   size budget). "Writing nothing is a valid and common outcome" stated
   verbatim.
8. **Update rules** — minimal diffs against named entries; owner-line
   preservation; supersession tombstones; conflict representation;
   relitigation flag. All per the design's "Update rules".
9. **The promotion report** — output contract (Promoted / Rejected with
   rule / Deferred with what's missing / Relitigation), ephemeral, and the
   machine-readable candidate schema in §7.
10. **Manual procedure** — a numbered procedure a non-Claude assistant or a
    human can follow end-to-end (resolve notes home → read map → list
    evidence after cursor → apply rules → write the report → propose diffs
    → apply confirmed ones → advance cursor). Same participation stance as
    `docs/session-notes-format.md`'s "How Codex uses this".
11. **Privacy** — maps are notes-home artifacts, private by default;
    repo-bound export goes through `docs/privacy-boundaries.md` +
    `bin/check-private-info.sh`, block on result.

## 5. Explicit non-goals

- No command, agent, or any file under `commands/` or `agents/` (packets
  2–3).
- No `knowledge.md`, no Patterns/Principles/Areas-of-inquiry content
  (wave 2).
- No edits to `docs/iterative-improvement.md`, `commands/workflow-review.md`,
  `commands/promote-insight.md`, or any existing doc — cross-references are
  carried by the new doc only, one-directionally.
- No installer, `bin/`, or Makefile changes.
- No fixtures or tests (packet 4).

## 6. Expected files to add or modify

| File | Change |
|---|---|
| `docs/knowledge-promotion.md` | new (~250 lines) |
| `capabilities.json` | one new row in `capabilities` (below) |
| `CHANGELOG.md` | one line under `## [Unreleased]` → `### Added` |

**Repository-compliance note** (pre-existing gate, isolated here — it is
not part of the knowledge-promotion contract, workflow, or acceptance
criteria): this branch's base (`main` at `0e0c1ba`) already enforces, via
`make check`, that every file under `commands/`, `agents/`, and `docs/*.md`
is registered in `capabilities.json`. Paste the row below verbatim; no
other knowledge of that machinery is needed. Field rules the validator
enforces, verified on this branch: `mutation` ⊆ {disk, network, external};
`maturity` ∈ {draft, documented, tested}; provider values ∈ {installed,
manual, untested, unsupported, n/a}; `version_introduced` is semver and
must not be ahead of the `VERSION` file (currently `0.3.0`). Packets 2–4
refer back to this note.

```json
{
  "type": "contract",
  "name": "knowledge-promotion",
  "path": "docs/knowledge-promotion.md",
  "description": "The provider-neutral knowledge-promotion contract (promotion ladder, project-map format, cursor and evidence semantics, promotion report) from the #81 design; /promote-knowledge automates it for Claude Code, and Codex or a human follows the manual procedure directly.",
  "maturity": "documented",
  "mutation": [],
  "provider": {"claude": "manual", "codex": "manual"},
  "version_introduced": "0.3.0"
}
```

(`provider.claude` becomes `installed` in packet 2 when the command
exists.)

CHANGELOG line under `### Added`:

```markdown
- `docs/knowledge-promotion.md` — provider-neutral contract for promoting
  project evidence into a per-project `map.md` (issue #81 design, wave 1).
```

## 7. Interfaces and data shapes (normative — packets 2–4 consume these)

### Map file template

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

All six `##` sections always present, in this order, even when empty.

### Entry grammar

Decisions and Learnings entries:

```markdown
### <one-line claim> (YYYY-MM, settled)
why: <1–2 lines>
so: <concrete answer to ≥1 implication question>
revisit-when: <the evidence that would reopen this>
evidence: <ptr>[, <ptr>…]
```

- Status token: `settled` or `superseded`; Learnings omit the status token.
- `revisit-when:` is mandatory for Decisions, recommended for Learnings.
- Optional tags at the end of a Learning claim line:
  `` `transfer?` `` (name the other project in parentheses) or
  `` `inquiry?` ``.
- Five lines maximum per entry (claim line + four field lines).

Assumptions & tensions entries:

```markdown
- <assumption or tension> — confidence: high|medium|low — evidence: <ptr>
```

A conflict is one bullet with two indented sub-bullets, one per side, each
with its own evidence.

Open questions entries:

```markdown
- <question> (open|parked) — so: <inquiry implication> — evidence: <ptr> [`inquiry?`]
```

Superseded entries:

```markdown
- <claim> (retired YYYY-MM) → <what replaced it, or why>
```

### Size budget

Target ≤150 lines, hard cap 200 (`wc -l`). At the cap, no entry enters
until an existing one is compressed, demoted, or retired — the proposal
must pair the addition with the removal.

### Cursor semantics

- The `evidence through:` value is the filename (not path) of the newest
  session note processed, or `none` before the first run.
- "Evidence newer than the cursor": notes-home files under the project
  (sessions, handoffs, `profile.md`) whose date-stamped name — or mtime,
  for `profile.md` — is after the cursor note's date.
- **A completed run always advances the cursor**, including a
  confirm-none run. The cursor-line update is the only map edit applied
  without itemized confirmation (it is announced, not asked). Consequence:
  rejected/deferred candidates are not re-proposed unless *new* evidence
  raises them again.
- An aborted run (user interrupts before the confirm step completes)
  writes nothing, including the cursor.
- Bootstrap (no `map.md`): process full history; if the owner confirms
  nothing, still create the map skeleton (template above) with the cursor
  set. The map's existence records that the history was processed.

### Candidate schema (the scout↔command handoff and the report's
machine-readable form; defined here once)

```yaml
candidates:            # ≤5 after ranking (bootstrap: up to size budget)
  - rung: 1|2|3|4|5    # ladder rung; 6 is wave 2 and must not appear
    action: add|update|supersede|tag
    section: brief|decisions|learnings|assumptions|questions
    related_entry: <existing claim line, or null>   # novelty citation
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

Ranking for the ≤5 cut: rung 2 before rung 3 before rungs 1/4/5; ties by
breadth of `so:` (more decisions influenced ranks higher); the ranking is
stated in the report.

## 8. Step-by-step implementation plan

1. Branch state: work on `docs/81-knowledge-promotion-design` (this
   branch); confirm `git status --short` is clean first.
2. Write `docs/knowledge-promotion.md` per §4/§7. Reuse the design doc's
   prose where it is already normative; do not contradict it anywhere.
3. Add the `capabilities.json` row from §6's repository-compliance note
   (append to the `capabilities` array; keep the JSON valid).
4. Add the CHANGELOG line from §6.
5. Run `make check` and `make test`; fix only what they report about
   *your* files.
6. Commit: `docs: knowledge-promotion contract + map format (#81)`.

## 9. Acceptance criteria

- `docs/knowledge-promotion.md` exists and contains all eleven numbered
  elements of §4, the template, grammar, cursor rules, and candidate schema
  of §7, byte-consistent with the design doc's decisions.
- A reader with no Claude Code can execute the manual procedure of §4.10
  against a notes home using only this doc.
- `make check` and `make test` green.
- No file outside §6's table changed.

## 10. Required tests

`make check` and `make test` only — this packet is documentation; the
behavioral scenarios are packet 4's.

## 11. Failure and edge cases the doc must cover

- No notes home / no project directory: the manual procedure says create
  per `docs/session-notes-format.md` (`mkdir -p`), then bootstrap.
- No evidence after the cursor: report "nothing new", change nothing
  (cursor already current).
- Map at hard cap: pair-with-removal rule (§7 size budget).
- Map missing a `##` section (hand-edited): the procedure re-adds the
  missing header as part of the next confirmed write, never reorders
  existing content.

## 12. Manual validation steps

1. `bash -n` nothing to run — instead: follow the manual procedure yourself
   against a throwaway `BINDLE_NOTES_DIR` with two synthetic session notes;
   confirm you can produce a report and a map without consulting anything
   but the new doc.
2. `grep -c '^' docs/knowledge-promotion.md` — sanity: the doc itself
   should be ≤ ~300 lines; if it exceeds that, it is restating the design
   instead of referencing it.

## 13. Paste-ready implementation prompt

```
You are working in the Bindle repo on branch docs/81-knowledge-promotion-design.
Read docs/plans/2026-07-11-knowledge-promotion-p1-contract.md and
docs/design/2026-07-11-knowledge-promotion.md in full. Implement packet 1
exactly: create docs/knowledge-promotion.md per the packet's §4 and §7, add
the capabilities.json row and CHANGELOG line from §6, and change nothing
else. The design doc is authoritative for product questions; the packet is
authoritative for file-level scope. Run make check and make test; commit
"docs: knowledge-promotion contract + map format (#81)" only if green. Do
not push. Do not create commands, agents, fixtures, or wave-2 content.
```

## 14. Recommended model strength

Strong (Opus-class or better). The doc is judgment-heavy prose that packets
2–4 and future sessions treat as normative.

## 15. Weaker-model safety

Not safe to delegate below strong: a weaker model will paraphrase the
design and introduce contradictions the later packets inherit. Mechanical
sub-steps (capabilities row, CHANGELOG line) are safe at any strength.

## 16. Definition of done

All §9 criteria met, checks green, one commit on
`docs/81-knowledge-promotion-design`, nothing pushed.
