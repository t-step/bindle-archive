# Content identity for pressure-test reps (#339)

**Date:** 2026-07-22
**Issue:** #339 — pressure-test reps record no identity for the skill content
they tested
**Status:** approved design, pre-implementation
**Pairs with:** #331 (model provenance — merged as PR #441). #331 records *who
produced* a rep; this records *what was tested*. Consumed by #260 (rep grader)
and #212 (rep debt), both keyed on "same content or not".

## Problem

Nothing ties a recorded rep to the skill content it exercised. Dates in
`Status:` lines are the only proxy, and churn evidence shows the gap is the
normal case, not the edge: of release-captain's 10 `SKILL.md` commits, only
2 also touched its `PRESSURE-TESTS.md` — the 5 most recent touched it zero
times (session-continuity: 3/9). Cross-vendor safety claims (#333/#334) are
un-revalidatable from the moment they are made without a content identifier.

The issue's acceptance criteria already settle **derived over declared**: the
identifier is computed from content, never hand-maintained (#309, n=275, is
this repo's standing evidence that prose rules alone don't bind).

## Decisions (operator-approved 2026-07-22)

1. **Scope: whole skill directory.** Hash covers every tracked file under
   `skills/<name>/` except `PRESSURE-TESTS.md` itself.
2. **Recording: per-series `**Content:**` line** in `PRESSURE-TESTS.md`,
   beside #331's `**Model:**` line, plus a `bin/` helper as the one-command
   staleness answer.
3. **Gate: warn-only banner** in `check.sh` — the recorded decision the
   issue's last acceptance box requires is *warn, not gate*.

## 1. Identity definition

A skill's **content-id** is:

- Membership: `git ls-files -- skills/<name>` minus
  `skills/<name>/PRESSURE-TESTS.md`. Tracked files only — canonical, and
  consistent with every other gate's tracked-file scope. Excluding the
  evidence file is load-bearing: otherwise recording a rep changes the
  identity it records.
- Bytes: read from the **working tree**, not the index or HEAD. Reps exercise
  installed disk content through the `~/.claude/skills/<name>` symlink, so
  the id must describe what actually ran, including uncommitted edits.
- Formula: sort the member paths with `LC_ALL=C sort`; for each file in that
  order, one line `<sha256-of-file-hex>  <repo-relative path>` (two spaces,
  `shasum -a 256` output shape); the content-id is the sha256 of that byte
  stream. The sort key is the path, not the composed line — composition
  happens after the path sort.
- Recorded form: `sha256:` + first 12 hex digits.

Error cases: a tracked member file missing from the working tree is a loud
failure, not a skip. An empty membership list (not a skill directory) exits 2 with a message, like a skill with no hashed series — nothing to identify.

Rejected alternatives: `SKILL.md`-only (a `references/` or `scripts/` edit
silently keeps the old identity — recreates the gap one level down); git tree
hash (tied to committed state, so a rep against uncommitted edits has no
honest id; includes `PRESSURE-TESTS.md`; couples identity to git object
format).

## 2. Recording — protocol § Recording amendment

`docs/pressure-testing-protocol.md` § Recording gains a `**Content:**` field
in each series' method statement, beside `**Model:**`, with the same rules:

- **Granularity:** per-series, with a per-arm/per-rep override. Mandatory
  override case: a REFACTOR mid-series edit means GREEN-before ≠ GREEN-after —
  two ids, recorded per arm. RED (no-skill) arms carry no id — nothing was
  loaded.
- **When written:** at dispatch time, from the helper's output — never
  reconstructed afterward.
- **Single source** (#312/#323): prose that merely restates the id collapses
  into the field; prose in which the content version is part of a *finding*
  stays.
- **Honest unknowns:** `**Content:** unrecorded` — explicit, never silence,
  never a guessed value.

## 3. Grandfathering — protocol § Grandfathered amendment

Mirrors the #331/#261 rule exactly:

- Every series recorded before this lands gets `**Content:** unrecorded` in
  all 13 existing `skills/*/PRESSURE-TESTS.md` files (same sweep shape as
  PR #441's `Model:` annotation).
- **Never derived from git archaeology.** The dispatch-time working tree is
  unknowable from a `Status:` date — the exact commit is not recorded, and
  reps may have run against uncommitted content. A guessed hash is worse than
  an honest unknown.
- Not a re-run obligation; an annotation is not a protocol credit.

## 4. Helper — `bin/skill-content-id.sh`

The one-command answer to "do skill X's existing reps still apply?"

- `bin/skill-content-id.sh <skill>` — print the current content-id.
- `bin/skill-content-id.sh --check <skill>` — recompute, then compare against
  the hashed `**Content:**` lines in that skill's `PRESSURE-TESTS.md`
  (matched with a light grep for `**Content:** sha256:`, not a structural
  parser — there is deliberately no PRESSURE-TESTS.md parser in this repo).
  Prints per-line MATCH/STALE; the verdict keys on the **last** hashed line
  in file order (series are appended, so last = newest — consistent with
  existing file practice). Exit 0 = newest matches current; 1 = drift;
  2 = no hashed series (fully grandfathered or no evidence file).
- `bin/skill-content-id.sh --check --all` — iterate every `skills/*` entry
  (skipping `_template`); used by the banner. Exit 0 = no drift anywhere;
  1 = at least one skill drifted.

Implementation constraints (profile): bash 3.2-safe; every array expansion
guarded with `[ "${#arr[@]}" -gt 0 ]`; `shfmt -i 2 -ci`; no
`cmd | grep -q` under pipefail where an early match can SIGPIPE — capture
first. Ships in the same commit with `bin/test-skill-content-id.sh`
(`git add`-ed before trusting the suite count — untracked suites are silently
not discovered) and `capabilities.json` ledger entries for both files
(inserted textually, never via a JSON round-trip).

Test coverage: id stability under file order; id change on `references/`
edit; id unchanged on `PRESSURE-TESTS.md` edit; missing tracked file fails
loudly; `--check` exit codes 0/1/2; `--all` aggregation.

## 5. Warn-only banner — `check.sh`

A non-blocking `STALE-REPS` disclosure in `check.sh` output, following the
#347 scope-banner pattern:

- Names each skill whose current content-id differs from its newest hashed
  series (helper `--check --all` under the hood).
- Skills with only `unrecorded` series are excluded — the banner **starts
  empty** at merge and only ever names genuine post-#339 drift. It never
  lists all 13 files, so it never trains readers to ignore it.
- Never fails the run. A hard gate was rejected: every routine `SKILL.md`
  edit would go red until a 5-rep series (#335 floor) re-lands, coupling doc
  edits to expensive rep campaigns; the predictable outcome is bypass
  pressure. "Explicitly scoped out" was rejected because an on-demand-only
  helper is a prose rule, and #309 is the evidence those don't bind.

## 6. Shape of the change

One branch, one PR: `feature/339-rep-content-identity`.

1. `docs/pressure-testing-protocol.md` — § Recording `Content:` field,
   § Grandfathered rule.
2. All 13 `skills/*/PRESSURE-TESTS.md` — `**Content:** unrecorded` per
   pre-existing series.
3. `bin/skill-content-id.sh` + `bin/test-skill-content-id.sh` +
   `capabilities.json` entries.
4. `check.sh` STALE-REPS banner.

Docs-heavy plus one small script — same size class as PR #441. No `SKILL.md`
content changes, so no pressure-test reps are owed by this change itself
(tooling and protocol, not skill behavior).

## Acceptance criteria mapping

| #339 criterion | Where satisfied |
|---|---|
| Result schema records a content identifier | § 2 (protocol § Recording) |
| Derived, not hand-maintained | § 1 (computed by helper; no declared field) |
| Multi-file case defined with canonical rule | § 1 (tracked files, sorted, minus evidence file) |
| Pre-existing reps grandfathered per #261 | § 3 |
| One-command staleness answer | § 4 (`--check`) |
| Recorded decision on `make check` behavior | § 5 (warn-only; gate and scope-out rejected with reasons) |
