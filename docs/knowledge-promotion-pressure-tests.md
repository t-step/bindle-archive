# knowledge promotion — pressure-test log

Per CONTRIBUTING's discipline (a workflow isn't done until an agent has been
watched exercising it in a controlled environment), this log records the
pressure tests for the knowledge-promotion workflow — the
[contract](knowledge-promotion.md), the `/promote-knowledge` command, and the
`knowledge-scout` agent (issue #81, packet 4; scenarios from
[the design](design/2026-07-11-knowledge-promotion.md) §validation). Method
mirrors [iterative-improvement-pressure-tests.md](iterative-improvement-pressure-tests.md):
fresh subagents, throwaway environments, the filesystem is ground truth.

## Method

- **Fresh subagent per rep.** Each rep assembles a throwaway fixture notes
  home (`mktemp -d`), snapshots it byte-for-byte, then hands a fresh
  general-purpose subagent the executor prompt below. The subagent executes
  `commands/promote-knowledge.md` as written against that home.
- **Scoring is filesystem assertions** — map bytes diffed against the
  pre-run snapshot, cursor line, field greps, entry counts — never the
  subagent's claim about what it did. Conditions that live in the promotion
  *report* (which rule a rejection cited, the stated ranking, the
  `/promote-insight` reminder) are checked in the subagent's returned
  report text and recorded as transcript-verified notes.
- **Reps:** ≥3 per scenario; 5 for scenarios 8 and 9 (the destructive-risk
  ones). Scenarios 1 and 9 run twice each — scout-delegated and inline —
  with identical filesystem outcomes required. All other scenarios run
  inline (the mode-equivalence claim is carried by 1 and 9; inline is also
  the guaranteed-available path).
- **Scout simulation.** The executor runs as a subagent, so "the
  knowledge-scout agent is installed" is simulated: in scout mode the
  executor is told the agent is installed and must delegate step 6 to a
  fresh subagent whose instructions are the verbatim contents of
  `agents/knowledge-scout.md` plus the inputs its Input contract lists,
  requiring back exactly one fenced YAML block. In inline mode it is told
  the agent is not installed, triggering the command's documented fallback.
- **Scripted owner.** The owner exists only as one scripted confirmation
  reply embedded in the executor prompt (`all` or `none` per scenario).
- **Rep validity** (packet §11): a rep whose subagent hangs or ignores the
  scripted reply is discarded and redone, and the discard is noted in
  Results — rep validity, not scenario failure.
- **The real notes home is provably untouched.** Before each batch:
  `MARKER=$(mktemp)`; after: `find ~/.bindle -newer "$MARKER"` must print
  nothing, recorded per batch in Results.
- **Read-only toward every repository.** Fixture issue references (`#12`
  etc.) are fictional; the executor is told the fixture project's tracker
  is unreachable, exercising the command's skip-silently branch.

### Executor prompt template

```text
You are executing Bindle's /promote-knowledge command, exactly as written.

- Command: <repo>/commands/promote-knowledge.md — read it and follow its
  steps in order. It defers to <repo>/docs/knowledge-promotion.md (the
  contract); on any conflict the contract wins.
- Notes home: treat $BINDLE_NOTES_DIR as set to <home> (it exists).
- Project argument: "<project>".
- <mode line — scout-delegated or inline, per Method>
- The fixture project's issue tracker is unreachable from this machine;
  the command permits skipping issue/PR reads silently — do so.
- The owner is present only through this scripted reply: when you reach
  the confirmation step, the owner's reply is exactly: <reply>.
- Read-only toward every git repository. Write only inside <home>.
- Return: the promotion report exactly as you presented it, the owner
  reply you applied, and your closing one-line summary.
```

Mode lines:

- scout-delegated: "The knowledge-scout agent IS installed. To delegate
  step 6, spawn a fresh subagent whose instructions are the verbatim
  contents of `<repo>/agents/knowledge-scout.md`, providing the inputs its
  Input contract lists (contract path, current map entries, explicit
  evidence file list, no issue/PR extracts); require back exactly one
  fenced YAML block in the contract's candidate schema."
- inline: "The knowledge-scout agent is NOT installed; perform step 6
  inline per the command's fallback and note the fallback in the report."

## Fixtures

Two fully synthetic projects. `harborlight` is registry-shaped (a
preservation registry for maritime archival media); `toolkit` is
kit-shaped (a personal script toolkit). Every name, issue number, commit
hash, and event is invented; the notes are *modeled on* public shapes
only, never copied from real session notes.

Paste the builder into a shell with `FIXTURES` pointing at an empty
working directory. It creates the source tree and a `mkhome` helper;
each rep then assembles its own home (the `H*` recipes below).

```bash
: "${FIXTURES:?set FIXTURES to an empty working directory}"
mkdir -p "$FIXTURES/harborlight/sessions" "$FIXTURES/toolkit/sessions" "$FIXTURES/maps"

# mkhome <project> <map-file|-> <session-note>...  -> prints the new home
mkhome() {
  local proj="$1" map="$2" home n; shift 2
  home="$(mktemp -d)"
  mkdir -p "$home/projects/$proj/sessions"
  [ "$map" != - ] && cp "$FIXTURES/maps/$map" "$home/projects/$proj/map.md"
  for n in "$@"; do
    cp "$FIXTURES/$proj/sessions/$n" "$home/projects/$proj/sessions/"
  done
  printf '%s\n' "$home"
}

# ---------------------------------------------------------------- harborlight
cat >"$FIXTURES/harborlight/sessions/2026-06-01-kickoff.md" <<'EOF'
# 2026-06-01 — kickoff: registry skeleton

goal: stand up the harborlight registry skeleton (catalog + ingest stub)
branch: feature/skeleton
commits made: 1a2b3c4 (catalog model), 5d6e7f8 (ingest stub)
tests/checks run: unit suite green (14/14)
decisions:
- start with a flat catalog table; revisit sharding only past 1M records
risks:
- ingest stub accepts any payload — validation not yet designed
deferred: rights model, disposition model
next: design the rights/disposition data model
EOF

cat >"$FIXTURES/harborlight/sessions/2026-06-02-disposition-rights-model.md" <<'EOF'
# 2026-06-02 — disposition vs rights: separate axes

goal: settle how rights-blocked assets are stored
branch: feature/rights-model
commits made: 9c8d7e6 (disposition field), 2f3a4b5 (rights gate on serving)
tests/checks run: unit suite green (19/19)
decisions:
- the registry RETAINS rights-blocked assets as records with
  `disposition: retained` instead of deleting them. Rights control
  serving; disposition controls record lifecycle — two separate axes.
  Deleting on rights-block conflates them and destroys provenance we can
  never rebuild. Settled after the takedown dry-run in #12.
- if a statutory erasure demand ever requires physical deletion, this
  design has to be revisited — record purge would need a tombstone
  mechanism we deliberately did not build.
deferred: tombstone mechanism (no legal requirement today)
next: audit serving paths for the rights check
EOF

cat >"$FIXTURES/harborlight/sessions/2026-06-05-fail-closed-ingest-seam.md" <<'EOF'
# 2026-06-05 — ingest validator fails closed; saved a corrupt batch

goal: wire schema validation into ingest
branch: feature/ingest-validation
commits made: 7a6b5c4 (validator), 3e2d1c0 (unknown-version reject)
tests/checks run: unit + integration green (27/27)
decisions:
- unknown schema versions are REJECTED at the seam (fail closed), not
  coerced. Within a week this bounced a 400-item batch whose exporter
  stamped a version we never published — every item had truncated
  checksums. Coercion would have written 400 silently corrupt records
  (#14).
risks:
- fail-closed means a legitimate new schema version needs a deploy first
deferred: version negotiation
next: document the version-bump runbook
EOF

cat >"$FIXTURES/harborlight/sessions/2026-06-08-ci-outage-diagnosis.md" <<'EOF'
# 2026-06-08 — CI diagnosis: 1-3 s zero-step failures = spending limit

goal: unblock the red CI queue
branch: none (ops only)
commits made: none
tests/checks run: n/a
decisions:
- none for the codebase. Root cause of this morning's all-red queue: jobs
  failing in 1-3 seconds with zero steps executed. That signature is the
  CI provider's spending limit being hit, not a code defect. Bumped the
  limit; queue green again.
risks:
- the same signature will fool us again if we forget it
deferred: nothing
next: back to the serving-path audit
EOF

cat >"$FIXTURES/harborlight/sessions/2026-06-10-catalog-cache-clockskew.md" <<'EOF'
# 2026-06-10 — stale catalog reads: clock-skew conclusion

goal: find why the catalog cache serves stale entries after updates
branch: fix/stale-cache
commits made: none (investigation only)
tests/checks run: repro script — stale read reproduced 7/10
decisions:
- tentative conclusion: invalidation timestamps come from two registry
  nodes whose clocks drift ~4 s apart, so entries written on the laggard
  node are judged fresh/expired wrongly. NTP capture attached in #18.
risks:
- not proven end-to-end; the TTL layer has not been ruled out
deferred: the fix — conclusion needs confirming first
next: instrument the TTL layer
EOF

cat >"$FIXTURES/harborlight/sessions/2026-06-12-catalog-cache-ttl.md" <<'EOF'
# 2026-06-12 — stale catalog reads: TTL-rounding conclusion (contradicts 06-10)

goal: instrument the TTL layer for the stale-read bug
branch: fix/stale-cache
commits made: 8b9c0d1 (TTL tracing)
tests/checks run: repro 9/10 with tracing on
decisions:
- tracing points the opposite way from the 06-10 note: TTLs are rounded
  DOWN to whole minutes at write time, so entries written late in a
  minute live up to 59 s too short — and node clocks agreed within 40 ms
  during every reproduced stale read (#19). The clock-skew conclusion
  looks wrong, but the 06-10 NTP capture did show 4 s drift that day.
  Unresolved.
risks:
- two competing explanations; building the wrong fix wastes a sprint
deferred: the decision on which fix to build
next: reproduce with pinned clocks to separate the two
EOF

cat >"$FIXTURES/harborlight/sessions/2026-06-15-reflections.md" <<'EOF'
# 2026-06-15 — mid-project reflections

goal: none — end-of-sprint reflection
branch: none
commits made: none
tests/checks run: n/a
decisions:
- none. General observation from the sprint: good abstractions come from
  concrete use cases, not up-front design — we keep being better off
  building the concrete thing first and abstracting second.
risks: none noted
deferred: nothing
next: pick up the embargo question
EOF

cat >"$FIXTURES/harborlight/sessions/2026-06-18-provenance-event-log.md" <<'EOF'
# 2026-06-18 — provenance is an append-only event log

goal: settle provenance storage
branch: feature/provenance
commits made: 4c5d6e7 (event log), 1f2e3d4 (chain verifier)
tests/checks run: unit green (33/33)
decisions:
- provenance is stored as an append-only event log per asset, never as a
  mutable current-state blob. Corrections are new events; history is the
  product. Chosen after the 06-02 rights work showed lost provenance can
  never be rebuilt (#21).
risks:
- the log grows unbounded; compaction deliberately out of scope
deferred: compaction policy, until a real size problem exists
next: access tiers
EOF

cat >"$FIXTURES/harborlight/sessions/2026-06-20-thumbnail-derivatives.md" <<'EOF'
# 2026-06-20 — thumbnails are cache, not archive

goal: stop derivative storage from tripling the archive
branch: feature/derivatives
commits made: 6d7e8f9 (regeneration pipeline)
tests/checks run: integration green (35/35)
decisions:
- rendered derivatives (thumbnails, previews) are disposable cache:
  regenerated from masters on demand, never archived. Cut storage
  projections ~60% (#23). Only masters carry preservation guarantees.
  This holds as long as nobody ever needs the exact bytes of a
  previously served derivative back.
risks:
- regeneration depends on renderer determinism staying good enough
deferred: renderer version pinning
next: embargo semantics
EOF

cat >"$FIXTURES/harborlight/sessions/2026-06-22-access-tiers.md" <<'EOF'
# 2026-06-22 — three access tiers, enforced at the serving edge

goal: settle the access model
branch: feature/access-tiers
commits made: 0a1b2c3 (tier field), 9e8d7c6 (edge enforcement)
tests/checks run: unit + integration green (41/41)
decisions:
- exactly three access tiers — public / staff / rights-holder — enforced
  at the serving edge, not in catalog queries. A fourth "partner" tier
  was cut: every proposed partner case collapsed into rights-holder with
  a scope note (#25).
risks:
- edge enforcement means internal tools bypass tiers unless they also go
  through the edge
deferred: internal-tool audit
next: embargo question, for real this time
EOF

cat >"$FIXTURES/harborlight/sessions/2026-06-24-embargo-question.md" <<'EOF'
# 2026-06-24 — embargo semantics: open question

goal: scope embargo support
branch: none (design discussion)
commits made: none
tests/checks run: n/a
decisions:
- none — deliberately left open. Unresolved: is an embargo a RIGHTS state
  (serving-side, expires into public) or a DISPOSITION state
  (lifecycle-side, expires into review)? Donor agreements read both ways
  (#27). Whichever axis we pick constrains the tier model, so picking
  blind could force a migration.
risks:
- building either reading now could force a migration later
deferred: the whole feature, until two real donor agreements are in hand
next: collect the two agreements
EOF

cat >"$FIXTURES/harborlight/sessions/2026-06-28-disposition-restated.md" <<'EOF'
# 2026-06-28 — takedown drill: disposition model reconfirmed

goal: quarterly takedown drill
branch: none (drill)
commits made: none
tests/checks run: drill checklist green
decisions:
- none new. The drill reconfirmed the 06-02 model: the rights-blocked
  test asset stayed a catalog record (`disposition: retained`) and
  stopped being served — disposition and rights behaved as the separate
  axes the map already records. No surprises.
risks: none new
deferred: nothing
next: none
EOF

cat >"$FIXTURES/harborlight/sessions/2026-06-30-rights-holder-archival-demand.md" <<'EOF'
# 2026-06-30 — new donor contract requires archiving exact rendered previews

goal: review the incoming donor contract's technical clauses
branch: none (contract review)
commits made: none
tests/checks run: n/a
decisions:
- none yet — but clause 7 requires archiving the EXACT rendered previews
  shown at accession time, for audit. That is precisely the condition the
  06-20 derivatives decision named as what would reopen it (disposable
  cache assumed nobody needs exact bytes back). This needs a decision
  revision, not a silent exception (#31).
risks:
- regeneration is not byte-stable across renderer versions
deferred: implementation, until the decision is revised
next: revise the derivatives decision
EOF

# ------------------------------------------------------------------- toolkit
cat >"$FIXTURES/toolkit/sessions/2026-06-03-manifest-schema-deferred.md" <<'EOF'
# 2026-06-03 — no manifest schema until a second consumer exists

goal: decide whether the kit manifest gets a formal schema
branch: feature/manifest
commits made: 2b3c4d5 (manifest loader)
tests/checks run: checks green
decisions:
- the manifest stays schema-less until a SECOND consumer exists. Today
  the installer is the only reader; a schema now would encode one
  consumer's guesses and calcify them. The installer's own validation is
  the de facto contract (#7). Revisit the moment a second tool wants to
  read the manifest.
risks:
- schema-less drift if a second consumer appears silently
deferred: the schema work itself
next: sync command polish
EOF

cat >"$FIXTURES/toolkit/sessions/2026-06-07-naming-convergence-inquiry.md" <<'EOF'
# 2026-06-07 — inquiry: do personal-tool naming conventions converge?

goal: rename three scripts; noticed a pattern
branch: chore/renames
commits made: 5e6f7a8 (renames)
tests/checks run: checks green
decisions:
- none beyond the renames. Noticed: after three rename rounds the scripts
  drifted to verb-first kebab-case — the same shape team CLIs converge
  on. Open inquiry, not actionable here: do solo-maintained tools
  converge on the same naming shapes as team tools, and is the pressure
  the same (handoff to a future stranger — which for a solo tool is
  future-me)? Worth reading up on; would sharpen how the kit's naming
  guidance is argued (#11).
risks: none
deferred: nothing
next: none
EOF

cat >"$FIXTURES/toolkit/sessions/2026-06-09-exporter-symlink-hunch.md" <<'EOF'
# 2026-06-09 — hunch: exporter may break on symlinked configs

goal: none — recording a nagging recollection
branch: none
commits made: none
tests/checks run: tried to reproduce today — could NOT
decisions:
- none. I half-remember the exporter mangling a symlinked config months
  ago, but today's attempts don't reproduce it, and I can find no failing
  log, no issue, and no commit touching symlink handling. Recording the
  hunch so it stops rattling around; there is nothing to point at.
risks:
- if real, it corrupts exported configs silently
deferred: everything — nothing to act on
next: none
EOF

# ---------------------------------------------------------------------- maps
# map-a: disposition decision already promoted; cursor at 2026-06-15.
cat >"$FIXTURES/maps/map-a.md" <<'EOF'
# harborlight — map

updated: 2026-06-16 · evidence through: 2026-06-15-reflections.md

<!-- Purpose: recover the current mental model of this project in under
     five minutes. Owner-curated; /promote-knowledge proposes diffs. -->

## Brief

Registry for maritime archival media. Thesis: preservation-grade catalog
with rights-aware serving, without an institutional stack. Direction:
harden ingest and serving before any new surface. Top tension: two
competing explanations for the stale-cache bug.

## Decisions

### Rights-blocked assets are retained as records, never deleted (2026-06, settled)
why: rights control serving; disposition controls record lifecycle — separate axes. Deleting conflates them and destroys provenance.
so: takedown handling never removes catalog records; serving-side gates carry the whole rights burden.
revisit-when: a statutory erasure demand requires physical deletion of records.
evidence: sessions/2026-06-02-disposition-rights-model.md, #12

## Learnings

### Ingest validation fails closed on unknown schema versions
why: coercion writes silently corrupt records; rejection bounced a 400-item corrupt batch within a week.
so: a new schema version needs a deploy before its batches ingest; that cost is accepted.
revisit-when: fail-closed blocks a time-critical accession.
evidence: sessions/2026-06-05-fail-closed-ingest-seam.md, #14

## Assumptions & tensions

- stale catalog reads: clock skew vs TTL rounding — confidence: low — evidence: #18, #19
  - clock-skew reading: ~4 s node drift in the 06-10 NTP capture — evidence: sessions/2026-06-10-catalog-cache-clockskew.md, #18
  - TTL reading: minute-rounding shortens TTLs up to 59 s; clocks agreed during every reproduced stale read — evidence: sessions/2026-06-12-catalog-cache-ttl.md, #19

## Open questions

## Superseded
EOF

# map-b: derivatives decision settled; cursor at 2026-06-24.
cat >"$FIXTURES/maps/map-b.md" <<'EOF'
# harborlight — map

updated: 2026-06-25 · evidence through: 2026-06-24-embargo-question.md

<!-- Purpose: recover the current mental model of this project in under
     five minutes. Owner-curated; /promote-knowledge proposes diffs. -->

## Brief

Registry for maritime archival media. Thesis: preservation-grade catalog
with rights-aware serving. Direction: derivatives and access model are
settled; embargo semantics deliberately open.

## Decisions

### Rendered derivatives are disposable cache — regenerated, never archived (2026-06, settled)
why: only masters carry preservation guarantees; regeneration cut storage projections ~60%.
so: no backup, replication, or audit burden for thumbnails and previews.
revisit-when: any requirement to reproduce the exact bytes of a previously served derivative.
evidence: sessions/2026-06-20-thumbnail-derivatives.md, #23

## Learnings

## Assumptions & tensions

## Open questions

- is an embargo a rights state or a disposition state? (open) — so: the chosen axis constrains the tier model — evidence: sessions/2026-06-24-embargo-question.md, #27

## Superseded
EOF

# map-c: hand-edited by the owner (phrasing + comment markers are theirs);
# cursor at 2026-06-15.
cat >"$FIXTURES/maps/map-c.md" <<'EOF'
# harborlight — map

updated: 2026-06-16 · evidence through: 2026-06-15-reflections.md

<!-- Purpose: recover the current mental model of this project in under
     five minutes. Owner-curated; /promote-knowledge proposes diffs. -->
<!-- OWNER NOTE: I reworded the Brief by hand — keep my phrasing. -->

## Brief

Harborlight is my bet that a small registry can be preservation-grade
without an institutional stack. (owner-authored, 2026-06-16)

## Decisions

### Rights-blocked assets are retained as records, never deleted (2026-06, settled)
why: rights and disposition are separate axes — deleting conflates them and destroys provenance I care about.
so: takedowns never remove records; serving gates carry the rights burden.
revisit-when: a statutory erasure demand requires physical deletion.
evidence: sessions/2026-06-02-disposition-rights-model.md, #12
<!-- owner: the wording above is mine, do not regenerate -->

## Learnings

## Assumptions & tensions

## Open questions

- should accession notes be public by default? (parked) — so: changes what donors can be promised — evidence: #16

## Superseded
EOF

# map-d: sparse early map; cursor at kickoff, so everything after is new.
cat >"$FIXTURES/maps/map-d.md" <<'EOF'
# harborlight — map

updated: 2026-06-01 · evidence through: 2026-06-01-kickoff.md

<!-- Purpose: recover the current mental model of this project in under
     five minutes. Owner-curated; /promote-knowledge proposes diffs. -->

## Brief

Registry for maritime archival media, at the skeleton stage.

## Decisions

## Learnings

## Assumptions & tensions

## Open questions

## Superseded
EOF

echo "fixtures built under $FIXTURES"
```

### Per-scenario homes

```bash
H1()  { mkhome harborlight map-a.md 2026-06-02-disposition-rights-model.md \
          2026-06-05-fail-closed-ingest-seam.md 2026-06-10-catalog-cache-clockskew.md \
          2026-06-12-catalog-cache-ttl.md 2026-06-15-reflections.md \
          2026-06-28-disposition-restated.md; }
H2()  { mkhome toolkit - 2026-06-03-manifest-schema-deferred.md \
          2026-06-07-naming-convergence-inquiry.md 2026-06-09-exporter-symlink-hunch.md; }
H3()  { mkhome harborlight - 2026-06-02-disposition-rights-model.md; }
H4()  { mkhome harborlight - 2026-06-08-ci-outage-diagnosis.md; }
H5()  { mkhome harborlight - 2026-06-10-catalog-cache-clockskew.md \
          2026-06-12-catalog-cache-ttl.md; }
H6()  { mkhome harborlight map-b.md 2026-06-20-thumbnail-derivatives.md \
          2026-06-24-embargo-question.md 2026-06-30-rights-holder-archival-demand.md; }
H7()  { mkhome toolkit - 2026-06-09-exporter-symlink-hunch.md; }
H8()  { mkhome harborlight map-c.md 2026-06-02-disposition-rights-model.md \
          2026-06-18-provenance-event-log.md 2026-06-20-thumbnail-derivatives.md; }
H9()  { mkhome harborlight map-d.md 2026-06-01-kickoff.md \
          2026-06-02-disposition-rights-model.md 2026-06-05-fail-closed-ingest-seam.md \
          2026-06-08-ci-outage-diagnosis.md 2026-06-10-catalog-cache-clockskew.md \
          2026-06-12-catalog-cache-ttl.md 2026-06-15-reflections.md \
          2026-06-18-provenance-event-log.md 2026-06-20-thumbnail-derivatives.md \
          2026-06-22-access-tiers.md 2026-06-24-embargo-question.md; }
H10() { mkhome toolkit - 2026-06-07-naming-convergence-inquiry.md; }
H11() { mkhome harborlight - 2026-06-15-reflections.md; }
```

## Scenarios

Pass conditions are filesystem assertions on the home after the run (diffed
against the pre-run snapshot); "report:" items are transcript-verified.

| # | Scenario | Home | Reply | Pass condition | Reps |
|---|---|---|---|---|---|
| 1 | No novelty | H1 | `none` (if asked) | zero proposals; map diff is exactly the `updated:`/cursor line (cursor → `2026-06-28-disposition-restated.md`); report: cites the disposition entry as the novelty check target | 3 scout + 3 inline |
| 2 | Repeated evidence / idempotence | H2 | run 1 `all`; run 2 n/a | run 1 bootstraps the map; run 2 writes nothing — map byte-identical between runs; report: "nothing new" | 3 (each rep = both runs) |
| 3 | Consequential decision | H3 | `all` | exactly one `###` entry under Decisions with claim + `why:` + `so:` + `revisit-when:` (non-empty) + `evidence:`; no other section gains an entry beyond the Brief | 3 |
| 4 | Incidental implementation detail | H4 | `none` (if asked) | Decisions and Learnings gain nothing; skeleton map exists with cursor at the CI note; report: rejected with rule `routing`, names `/promote-insight` | 3 |
| 5 | Contradictory evidence | H5 | `all` | one top-level Assumptions & tensions bullet with exactly two sub-bullets, each carrying its own `evidence:`; no Decisions/Learnings entry picks a winner | 3 |
| 6 | Superseded decision | H6 | `all` | the derivatives claim line's status flips to `superseded`; one tombstone line appears under Superseded; the entry's original `why:`/`so:` lines still present in the file | 3 |
| 7 | Weak evidence | H7 | `none` (if asked) | no entry written anywhere; skeleton + cursor only; report: rejected with rule `evidence` | 3 |
| 8 | Human-edited map preservation | H8 | `all` | every owner-authored line of map-c (both `<!-- -->` markers, the Brief line, the existing Decisions entry, the Open-questions bullet) byte-identical; diff confined to the confirmed new entries + cursor line | 5 |
| 9 | More than five candidates | H9 | `all` | exactly 5 new entries enter the map (volume guard; not a bootstrap — map-d exists); report: ranking stated, remainder in Rejected/Deferred with reasons | 5 scout + 5 inline |
| 10 | Valid general-interest inquiry | H10 | `all` | one Open questions bullet with a concrete `so:` inquiry implication and the `` `inquiry?` `` tag | 3 |
| 11 | Inert "insight" rejection | H11 | `none` (if asked) | no entry written; skeleton + cursor only; report: rejected with rule `consequence` | 3 |

Scenario 1 and 9 scout/inline pairs must produce identical filesystem
outcomes (packet 3's degradation claim); a divergence is a packet-3 bug —
record, fix there, re-run both modes.

## Retrieval test

Seed two maps by full bootstraps with reply `all`: harborlight from an
H9-style home *without* map-d (pure bootstrap, volume-guard exempt), and
toolkit from H2. Then a fresh subagent per project receives **only** the
seeded `map.md` content — no sessions/, no handoffs/, no repo — and
answers the design's eight briefing questions:

1. Brief me on this project before I meet a domain expert.
2. Why is the architecture the way it is?
3. What assumptions carry risk?
4. What here might transfer to other projects?
5. Explain one core decision as you would in an interview.
6. Which principles or decisions are supported by recorded decisions?
7. What non-actionable question has emerged?
8. What should I stop reconsidering, and until when?

Pass: every answer is derivable from map content alone — the grader checks
each claim in each answer against the map bytes; any answer that needs the
evidence archive is a fail. Question 8 must be answered from
`revisit-when:` lines.

## Results

Run 2026-07-12. Executor subagents: fresh general-purpose agents on
claude-sonnet (per the packet's weaker-model delegation guidance); scoring
by filesystem assertion scripts plus strong-model transcript checks.
Scout-mode reps delegated step 6 to a nested fresh subagent running
`agents/knowledge-scout.md` verbatim, per Method.

| # | Scenario | Reps | Result | Notes |
|---|---|---|---|---|
| 1 | No novelty | 3 scout + 3 inline | **PASS 6/6** | Every rep: map diff exactly the cursor line, cursor → `2026-06-28-…`; report cites the disposition Decision as the novelty check target; both modes filesystem-identical. Scout YAML parsed cleanly in 3/3 scout reps (no fallback needed). |
| 2 | Idempotence | 3 (×2 runs) | **PASS 3/3** | Run 1 bootstraps (six sections, cursor at newest note); run 2 stops at "nothing new", map byte-identical in 3/3. |
| 3 | Consequential decision | 3 + 3 | **first batch FAIL 0/3 → fixture amended → PASS 3/3** | All three first-batch reps promoted a *second*, contract-legitimate A&T candidate from the fixture note's `risks:` line ("serving layer must check rights on every path") — a fixture-construction defect, not a command defect: the packet's §7.3 condition permits only the Decision entry. Fix: removed the ambiguous `risks:` line from the fixture (this doc); full re-run green — exactly one Decisions entry, all four fields non-empty, no other section gains an entry. |
| 4 | Incidental detail | 3 | **PASS 3/3** | Skeleton + cursor at CI note only; all reports reject with rule `routing` and name `/promote-insight`. |
| 5 | Contradictory evidence | 3 | **PASS 3/3** | One A&T bullet, exactly two sub-bullets, each with own `evidence:`; no Decisions/Learnings winner in any rep. |
| 6 | Superseded decision | 3 + 3 + 3 | **batch 1 FAIL 1/3 → contract fix → FAIL 2/3 → contract fix → PASS 3/3** | Two real contract gaps found. (a) "produces a proposed revision" read as rewrite-in-place: one rep amended the settled claim line in place, one replaced the entry wholesale deleting the original prose. Fix: Supersession now states the status flip is the only edit the retired entry receives; Relitigation applies as supersession, never a rewrite. (b) One second-batch rep then *deferred* the supersession because no replacement decision existed yet. Fix: Relitigation now states a met condition is never deferred to wait for a replacement — the tombstone points at the triggering evidence or an Open question. Final re-run 3/3: status flip byte-clean, tombstone present, original `why:`/`so:` prose intact. |
| 7 | Weak evidence | 3 + 3 | **batch 1 report-FAIL 0/3 → contract fix → PASS 3/3** | Filesystem passed all batch-1 reps (the scripted `none` saved it), but 0/3 rejected by the evidence rule — each *proposed* the unreproduced hunch (as A&T or Open question), reading the hunch note itself as the durable pointer. Fix: Evidence rule now requires the pointer to record the claim's *support*; an unreproduced hunch/half-remembered incident is not evidence for the claim it voices. Re-run 3/3: rejected with rule `evidence`, nothing written, skeleton + cursor only. |
| 8 | Human-edited map | 5 | **PASS 5/5** | Every owner-authored line (both `<!-- -->` markers, hand-worded Brief, owner Decision entry, parked Open question) byte-identical in 5/5; diff confined to confirmed entries + cursor line; cursor → `2026-06-20-…`. |
| 9 | >5 candidates | 5 scout + 5 inline | **PASS 10/10** | Every rep: exactly 5 new entries enter the map (all rung-2 Decisions; the guard displaced valid rung-1 candidates to Deferred with reasons), ranking stated, cursor → `2026-06-24-…`; routing reminder present in all reps (the CI note was among the rejected). Scout YAML parsed cleanly 5/5; in one scout rep the scout misread the run as bootstrap-scale and the *command* corrected it, enforcing the guard — the propose/confirm owner kept control as designed. Mode equivalence: identical structural outcomes in both modes (5 new Decisions entries, same cursor, nothing else touched); entry wording varies rep-to-rep equally within each mode, so equivalence is structural, not byte-level. |
| 10 | General-interest inquiry | 3 | **PASS 3/3** | One Open questions bullet with concrete `so:` implication and `` `inquiry?` `` tag in 3/3. |
| 11 | Inert "insight" | 3 + 3 | **batch 1 FAIL 2/3 → contract fix → PASS 3/3** | One rep routed the generic reflection to Deferred as a "would-be rung-6 principle" instead of rejecting it — the ladder's deferral clause was an escape hatch around the consequence rule. Fix: ladder now defers only would-be principles that *survive* the promotion rules; rule-failers are rejected with the rule. Re-run 3/3: rejected with rule `consequence`, skeleton + cursor only. |

### Contract/fixture amendments made by this campaign

All four amendments are minimal sharpenings of `docs/knowledge-promotion.md`
implementing what the design already specified (the design itself was not
reopened); one fixture amendment to this doc:

1. Fixture: dropped the `risks:` line from the 06-02 disposition note
   (scenario 3 isolation — the line was a second legitimate candidate).
2. Evidence rule: the pointer must record the claim's support; unreproduced
   hunks/recollections are rejected under this rule (scenario 7).
3. Supersession: the status-token flip is the only edit the retired entry
   receives; replacements enter as new entries (scenario 6).
4. Relitigation: a met `revisit-when:` is applied as a supersession — never
   a rewrite in place, never deferred waiting for a replacement (scenario 6).
5. Ladder: a would-be rung-6 principle is deferred only if it survives the
   promotion rules; a rule-failer is rejected with that rule (scenario 11).

### Rep validity

No reps discarded: no hangs, and every executor honored its scripted reply.
Scenario 3's first batch and scenario 6's first two batches are recorded as
scenario failures (not invalid reps) with their dispositions above.

### Retrieval test

**PASS (both projects).** Seeded per Method: harborlight by a pure
bootstrap over all 11 notes (73-line map: Brief, 6 Decisions, 1 A&T
conflict, 1 Open question), toolkit from H2 (1 Decision, 1 tagged
inquiry). Fresh subagents received only the map bytes (content pasted
inline — no paths, no tools) and answered all eight briefing questions.
Grading (strong model, claim-by-claim against map bytes): every claim in
every answer traces to map content; no answer required the evidence
archive; both "stop reconsidering" answers were built entirely from
`revisit-when:` lines; the toolkit answerer correctly flagged the empty
Brief instead of inventing one, and named the `` `inquiry?` ``-tagged
question for Q7. One observation, not a failure: harborlight's Q7 answer
hedged because that seeded map's open question carries no `` `inquiry?` ``
tag — the tag, when present, is what makes Q7 unambiguous.

### Real-notes-home check

A single mtime marker created before the first batch (2026-07-12 11:17,
before any executor ran) covered the whole campaign;
`find ~/.bindle -newer <marker>` printed nothing after the final batch.
One marker spanning all batches rather than one per batch — same
guarantee, recorded honestly as a deviation from the per-batch wording.

### Verdict

All eleven scenarios pass at their stated rep counts (48 executor reps,
0 discarded), retrieval passes for both projects, real notes home
provably untouched → `promote-knowledge` and `knowledge-scout` graduate
`draft` → `tested`.

## Stable identities (issue #179)

Two layers, per the split the contract itself draws: the identity *helper*
(`bin/map-entry-id.py`) is deterministic code, pressure-tested directly and
fast; the *integration* into `/promote-knowledge` (allocating on confirmed
writes, preserving ids through updates and supersession, never allocating on
`none`/rejected/deferred) is prompt-driven workflow behavior, pressure-tested
the same way as the campaign above — fresh subagent executors against
throwaway fixture homes, filesystem/JSON as ground truth.

### Layer 1 — the helper: `bin/test-map-entry-id.sh`

Deterministic, offline, no subagents. Covers the issue's 28 listed
scenarios wherever they're a property of the helper itself (allocation
format/uniqueness/no-side-file, marker placement per entry shape,
duplicate/malformed-id detection, typed tombstone + `bindle:superseded-by`
validation including unresolved/self-referential/duplicate/empty-value,
byte preservation, zero-mutation validation, determinism after
persistence, real-notes-home isolation via a mtime-marker check). Every
fixture is a throwaway file under `mktemp -d`; `$BINDLE_NOTES_DIR` is
pointed at that same tree.

**Result (2026-07-16): PASS 39/39 checks**, 0 failures, run via
`bin/test-map-entry-id.sh` (also wired into `make test`). The one issue-list
item this layer cannot cover — "confirm-none allocates and writes no
IDs" (scenario 10) — is a workflow property with nothing for the helper
alone to exercise (no code path in `bin/map-entry-id.py` ever gets called
unless something explicitly calls `allocate`); it's covered by Layer 2's
scenario X1 below instead.

#### Follow-up: duplicate-id pairing invariant (adversarial review, 2026-07-16)

A same-session adversarial review of commit `ae76f61` found a real gap in
the *first* cut of duplicate-id detection: it kept independent
"live-section" and "Superseded-section" occurrence buckets and never
flagged a same-id collision that happened to straddle the two buckets — so
an unrelated live entry and an unrelated tombstone could silently share an
id as long as one landed in each bucket, not just the one legitimate
retirement pair (a retired Decision's still-present heading + its own
matching tombstone). `bin/map-entry-id.py` was rewritten to a flat
occurrence list plus an explicit `_is_legitimate_retirement_pair()` check —
exactly two occurrences, same claim (byte-for-byte), same kind, and the
live side's status token literally `superseded` — with everything else
reported as `duplicate-id`. The rewrite also surfaced, and required naming
explicitly, a real limit already implied by the frozen grammar: Learnings
carry no status token at all ("Learnings omit the status token") and
Assumptions/tensions/Open questions carry no retirement status token
either, so none of those kinds has a deterministic in-place-retirement
signal to pair on — a same-id collision involving them is always a
conflict, documented as a known contract gap rather than papered over with
invented pairing logic.

9 new focused checks were added to `bin/test-map-entry-id.sh` (all folded
into the same 2026-07-16 run): a valid retirement pair (no conflict); a
settled-never-retired entry sharing an id with an unrelated tombstone
(conflict); kind mismatch; claim mismatch; two ordinary live entries
sharing an id; two tombstones sharing an id; a valid pair plus a stray
third occurrence; the documented Learning gap (a Learning + its own
matching tombstone is still a conflict); a legacy retired entry paired with
a correctly typed-but-markerless tombstone (informational only, `ok:
true`); and zero-mutation across every one of those fixtures.

**Result: PASS 53/53 checks** (39 original + 14 new — the count above also
absorbed a fixture bug the rewrite's stricter matching caught: an existing
supersession fixture had used differently-cased claim text between a
retired heading and its tombstone, which the new byte-for-byte claim check
correctly flagged; the fixture, not the validator, was wrong, and was
fixed to use identical claim text). 0 failures.

### Layer 2 — workflow integration: 3 new scenarios, subagent-executed

**Method**: identical to the Method section above — fresh general-purpose
subagent per rep, inline mode (the `knowledge-scout` fallback path;
mode-equivalence was already established for the base workflow by
scenarios 1 and 9 above and isn't re-litigated here), scripted owner reply,
read-only toward every repository including Bindle itself. Reuses this
doc's existing `harborlight` fixture builder and homes (`H3`'s single
disposition-rights session note for the add-path scenarios; `H6`'s seeded
`map-b.md` + 3 new session notes for the supersede-path scenario). Scoring:
the returned `map.md` bytes plus `bin/map-entry-id.py validate --format
json` run against the result (`ok`, `anchored_count`, exact id values).

| # | Scenario | Home | Reply | Pass condition | Reps |
|---|---|---|---|---|---|
| X1 | Confirm-none allocates nothing (contract scenario 10) | H3 | `none` | bootstrap skeleton only, zero `##` entries, zero `bindle:context-id` anywhere in the file | 3 |
| X2 | A confirmed `add` gets exactly one valid, freshly allocated id, written atomically with the entry | H3 | `all` | `map-entry-id.py validate` reports `ok: true`; every confirmed entry is `anchored: true` with an id matching `context-node:harborlight:[0-9a-f]{32}`; distinct ids across multiple confirmed adds in one run | 3 |
| X3 | Supersession: legacy (pre-#179, unanchored) retired entry gets no retroactive id; its tombstone carries no `bindle:context-id` (nothing to copy) but the confirmed replacement/new entry gets a freshly allocated one | H6 | `all` | retired heading byte-intact except the status-token flip, no id added to it; tombstone has the `<kind>:` typed prefix; `validate` reports `ok: true` with only the expected `info`-level `untyped-tombstone` finding (never an error) | 3 |

**Results (2026-07-16): PASS 9/9 reps, 0 discarded.**

- **X1 (3/3 PASS).** Every rep: bootstrap created the six-section skeleton
  only, `Decisions`/`Open questions` stayed empty, no `bindle:context-id`
  marker anywhere in the file — `allocate` was never invoked (no confirmed
  candidates to allocate for). Byte-identical outcome across all 3 reps.
- **X2 (3/3 PASS).** Every rep produced 1–2 freshly anchored entries (a
  Decision, and in 2/3 reps an Open question too — candidate count is not
  scripted, only the reply is); `validate --format json` returned `ok:
  true`, `anchored_count` matching the confirmed-entry count, and every id
  matched the exact `context-node:<slug>:<32-hex>` format. Ids were
  distinct within and across reps.
- **X3 (3/3 PASS).** All 3 reps correctly declined to add an id to the
  legacy retired entry (status-token flip only, claim/fields byte-intact)
  and correctly omitted `bindle:context-id` from its tombstone. The reps
  diverged on a legitimate contract branch not specific to identities —
  one proposed an immediate replacement Decision (getting it a fresh id,
  `bindle:superseded-by` on the tombstone pointing at it), two deferred the
  actual policy revision to a new Open question instead (no
  `bindle:superseded-by`, since no specific replacement exists yet) — both
  are valid per the existing Relitigation rule ("the tombstone points at
  the triggering evidence or an Open question" when no replacement exists
  yet), and both applied the identity rules correctly for the branch they
  took. `validate` returned `ok: true` in all 3, with only the expected
  informational `untyped-tombstone` finding (a marker-less legacy retirement
  is not an error).

### Real-notes-home check (this campaign)

A marker created immediately before dispatching the 9 Layer-2 subagents,
checked against both `~/.bindle` and the operator's actual configured
`$BINDLE_NOTES_DIR` after all 9 completed: `find <home> -newer <marker>`
printed nothing for either — the real notes home was never touched. Layer
1's own real-notes-home check (inside `bin/test-map-entry-id.sh`) passed
independently as part of its 39/39.

### Verdict

`bin/map-entry-id.py` and the `/promote-knowledge` identity integration
graduate `draft` → `tested`: Layer 1 53/53 (39 original + 14 from the
duplicate-id pairing follow-up), Layer 2 9/9, 0 discarded, real notes home
provably untouched in both layers.
