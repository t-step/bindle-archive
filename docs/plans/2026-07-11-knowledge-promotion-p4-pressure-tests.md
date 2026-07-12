# Packet 4 — pressure tests and fixture dogfood for knowledge promotion

Validates packets 1–3 against the acceptance scenarios and retrieval test of
[`docs/design/2026-07-11-knowledge-promotion.md`](../design/2026-07-11-knowledge-promotion.md)
(issue #81, wave 1), using the repo's established pressure-test discipline
(`CONTRIBUTING.md`; precedent: `docs/iterative-improvement-pressure-tests.md`).

## 1. Objective

Create `docs/knowledge-promotion-pressure-tests.md` (method, fixtures,
scenario table, recorded results), run every scenario with fresh subagents
in throwaway fixture notes homes, score on the filesystem, and — only if
all pass — graduate the command and agent from `draft` to `tested`.

## 2. Why this packet exists

Repo rule: a workflow isn't done until pressure-tested; unverified assets
stay drafts in the CHANGELOG. This packet is the graduation gate for
packets 2–3 and the empirical check on packet 1's rules.

## 3. Dependencies

Packets 1–3 committed. (Packet 3 optional: if the scout was deferred, run
scout-marked steps inline-only and say so in the results.)

## 4. Exact scope

### The pressure-test doc

`docs/knowledge-promotion-pressure-tests.md` containing:

1. **Method** — fresh subagent per rep; fixture notes home via
   `BINDLE_NOTES_DIR=$(mktemp -d)`; the subagent gets the fixture, the
   command, and a scripted confirmation reply; scoring is filesystem
   assertions only (map bytes, cursor line, file mtimes), never the
   subagent's self-report. ≥3 reps per scenario; 5 reps for scenarios 8
   and 9 (the destructive-risk ones). The real notes home must be provably
   untouched: record `find ~/.bindle -newer <marker>` empty after each
   batch.
2. **Fixture builder** — a fenced bash block (heredocs) the tester pastes;
   no new `bin/` script. It builds two fixture projects:
   - `harborlight` — a registry-style project modeled on Valence's public
     shape (a disposition-vs-rights decision note, a fail-closed-seam
     learning note, a CI-outage operational note, two conflicting-conclusion
     notes, one inert "sounds insightful" note);
   - `toolkit` — a kit-style project modeled on Bindle's public shape (a
     schema-needs-a-consumer decision note, a general-interest inquiry
     note, a weak-evidence note).
   All fixture text is synthetic: no real usernames, absolute home paths,
   emails, or denylist terms — the doc is committed and must pass
   `bin/check-private-info.sh` via `make check`.
3. **Scenario table** — the eleven scenarios in §7, each with fixture,
   scripted confirmation, and pass condition.
4. **Retrieval test** — §7.12.
5. **Results** — per scenario: reps, pass/fail, transcript-verified notes,
   date. Honest: failures recorded as failures.

### Graduation edits (only if everything passes)

The draft→tested discipline is `CONTRIBUTING.md`'s; the `capabilities.json`
touches are the pre-existing registration gate (see packet 1's
repository-compliance note — paste and move on):

- `capabilities.json`: `promote-knowledge` and `knowledge-scout` rows
  `maturity: "draft"` → `"tested"` (a validator enum value; verified valid
  on this branch).
- `CHANGELOG.md`: one `### Changed` line noting the pressure-test pass and
  draft-flag removal (edit the packet-2/3 Added lines' "(draft, pending
  pressure tests)" markers to "(tested)").
- Registration entry for the new doc, in `capabilities.json`'s
  `not_a_capability` list (same gate):

```json
{
  "path": "docs/knowledge-promotion-pressure-tests.md",
  "reason": "pressure-test method and recorded results for the knowledge-promotion workflow; QA record, not a capability."
}
```

## 5. Explicit non-goals

- **No writes to the real notes home or any real project map.** The true
  dogfood (real Valence/Bindle maps) is a separate, later, user-driven
  session — out of this packet.
- No new `bin/` scripts, no Makefile targets, no CI wiring.
- No wave-2 tests (patterns/principles/`knowledge.md`).
- No fixture content copied from real session notes — modeled-on, never
  pasted.
- No skill-style `PRESSURE-TESTS.md` under `skills/` — this workflow is a
  command+agent, and the record lives in `docs/`, following the
  iterative-improvement precedent.

## 6. Expected files to add or modify

| File | Change |
|---|---|
| `docs/knowledge-promotion-pressure-tests.md` | new |
| `capabilities.json` | 2 maturity flips + 1 registration entry (compliance note) |
| `CHANGELOG.md` | draft markers updated + 1 `### Changed` line |

## 7. Scenarios (fixture → scripted reply → filesystem pass condition)

1. **No novelty** — evidence restating an existing map entry → reply n/a →
   zero proposals; map bytes unchanged except cursor; report cites the
   checked entry.
2. **Repeated evidence / idempotence** — run twice on the same fixture,
   confirm `all` then rerun → second run proposes nothing; map identical
   between runs (except nothing — cursor already current).
3. **Consequential decision** — the harborlight disposition note → `all` →
   one Decisions entry with all four fields, `revisit-when:` non-empty.
4. **Incidental implementation detail** — the CI-outage note → n/a →
   rejected with rule `routing`; report names `/promote-insight` as the
   route; nothing written to Decisions/Learnings.
5. **Contradictory evidence** — the two conflicting notes → `all` → one
   Assumptions & tensions bullet with two evidence-bearing sub-bullets; no
   winner picked.
6. **Superseded decision** — fixture map with a settled decision + a note
   meeting its `revisit-when:` → `all` → status flipped, tombstone line in
   Superseded, original prose not deleted.
7. **Weak evidence** — the no-pointer note → n/a → rejected with rule
   `evidence`.
8. **Human-edited map preservation** — fixture map with an owner-authored
   entry and comment lines → `all` on unrelated candidates → owner lines
   byte-identical (diff scoped to the confirmed entries + cursor). 5 reps.
9. **More than five candidates** — a rich multi-note fixture → `all` →
   exactly 5 proposals, ranking stated; the rest in rejected/deferred. 5
   reps.
10. **Valid general-interest inquiry** — the toolkit inquiry note → `all` →
    Open questions entry with a concrete `so:` inquiry implication and
    `inquiry?` tag.
11. **Inert "insight" rejection** — the sounds-insightful note (a
    generic-advice line true of any project) → n/a → rejected with rule
    `consequence`.

Scenarios 1 and 9 run twice each: scout-delegated and inline (agent file
temporarily absent) — identical filesystem outcomes required (packet 3
§10).

### 7.12 Retrieval test

Seed both fixture maps by confirming `all` on their bootstrap runs. Then a
*fresh* subagent, given only the fixture `map.md` (no sessions/, no
handoffs/), answers the design's eight retrieval questions for that
project. Pass: every answer is derivable from map content alone (grader
checks each claim against the map; any answer requiring the evidence
archive = fail), and the "stop reconsidering" question is answered from
`revisit-when:` lines.

## 8. Step-by-step implementation plan

1. Clean `git status --short`; branch `docs/81-knowledge-promotion-design`.
2. Write the fixtures and the doc skeleton (§4.1–4.4) with an empty
   Results section; commit
   `test: knowledge-promotion pressure-test method + fixtures (#81)`.
3. Run the scenario batches (subagents; score filesystem; keep raw
   assertions in the doc's Results).
4. If a scenario fails: fix the *contract or command* per the design (the
   design is authoritative; if the design itself is wrong, stop and report
   — do not silently redesign), re-run the failed scenario's full rep
   count.
5. On all-pass: apply §4's graduation edits.
6. `make check`, `make test`; commit
   `test: knowledge-promotion scenarios pass — graduate command+agent (#81)`.

## 9. Acceptance criteria

- The doc exists with method, builder, all eleven scenario rows, retrieval
  test, and a Results section with real recorded outcomes (dates, rep
  counts).
- Every scenario's pass condition met at its rep count, or the failure and
  its disposition honestly recorded and graduation withheld.
- Real notes home untouched (the `find -newer` check recorded per batch).
- Graduation edits present iff all scenarios passed.
- `make check` + `make test` green.

## 10. Required tests

This packet *is* the tests. Structural gates: `make check`, `make test`,
`git diff --check`.

## 11. Failure and edge cases

- A rep hangs or a subagent ignores the scripted reply → discard and redo
  the rep; note it (rep validity, not scenario failure).
- Scenario passes inline but fails via scout (or vice versa) → packet-3
  degradation bug; record, fix there, re-run both modes.
- Fixture accidentally trips `check-private-info` → fix the fixture text;
  never allowlist.

## 12. Manual validation steps

After the batches: `make check && make test`; open the doc and confirm the
Results table has no "TBD"; `git diff --check` clean;
`grep -rn "draft, pending pressure tests" CHANGELOG.md` returns nothing if
graduation happened.

## 13. Paste-ready implementation prompt

```
You are working in the Bindle repo on branch docs/81-knowledge-promotion-design.
Read docs/plans/2026-07-11-knowledge-promotion-p4-pressure-tests.md,
docs/knowledge-promotion.md, commands/promote-knowledge.md, and
agents/knowledge-scout.md in full. Implement packet 4 exactly: write
docs/knowledge-promotion-pressure-tests.md with the method, the two
synthetic fixture projects, the eleven scenarios, and the retrieval test;
run every scenario with fresh subagents in throwaway BINDLE_NOTES_DIR
fixture homes at the stated rep counts; score on the filesystem only;
record honest results. Never touch the real notes home (~/.bindle) or any
real repo. Graduate maturity flags only on all-pass. Run make check and
make test; commit per the packet's §8. Do not push.
```

## 14. Recommended model strength

Strong for scenario design judgment calls and grading; the reps themselves
are mechanical once scripted.

## 15. Weaker-model safety

Reps and fixture building: safe for a weaker model. Grading (retrieval
test, rep validity) and any fix-the-contract decision: strong model only.
Split accordingly if delegating.

## 16. Definition of done

All §9 criteria; two commits (method+fixtures, then results+graduation) on
`docs/81-knowledge-promotion-design`; nothing pushed; real notes home
provably untouched.
