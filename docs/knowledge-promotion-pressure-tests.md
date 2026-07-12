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
risks:
- serving layer must check rights on every path; one missed path leaks
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

*(to be recorded by the scenario batches; graduation is withheld until
every row above passes at its rep count)*
