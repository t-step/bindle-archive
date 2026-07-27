# Pressure-test series fields — implementation plan (#467, #356)

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a rep series' protocol status a machine-readable field beside
`**Model:**` and `**Content:**`, and gate all three so an appended series cannot
omit them.

**Architecture:** Two deliveries. PR A changes the *record* — the protocol doc
defines a `**Protocol:**` field, and every existing field block gets one, so the
thirteen hand-maintained grandfathering caveats stop enumerating and start
pointing. PR B adds the *gate* — `bin/check-pressure-series.sh` with a
`--staged` mode (pre-commit; fires on an appended series heading with no field
block) and an `--all` mode (`make check`; every block complete and well-formed).
The gate would be red against an un-retrofitted tree, so A lands first.

**Tech Stack:** bash 3.2 (macOS floor), awk, `git diff --cached`, pre-commit,
`bin/check.sh`, `capabilities.json`.

**Design spec:** `docs/superpowers/specs/2026-07-26-pressure-series-field-gate-design.md`

## Execution record — complete

Both deliveries landed: PR A as #471, PR B as #474. Every task below is
executed; the boxes are ticked to say so, and the gate is live at both call
sites. Three things the plan did not predict, recorded here so a reader does not
have to reconstruct them from the commits:

- **The plan's own tree assumptions were wrong four ways**, found by measuring
  rather than by executing — the Amendments section below is that correction,
  written before Task B1. Two of the four (any-depth sections, `verify-then-commit`'s
  `####`) would have shipped a parser blind to real series.
- **Three Major findings in `--staged`, all one root cause**: the scan depended
  on the caller's cwd and on unstaged disk state while the mode's output claimed
  "staged content only". Found by whole-branch review, not by any task's own
  verification step, and fixed in `bc2c88e`. The suite could not have caught
  them — eight of its negative assertions passed vacuously on a no-op run, which
  is exactly what each finding produced.
- **Task B6's mutation pass found one survivor that was not dead code**: a
  Protocol-less block stays rejected via the legality branch, so the verdict
  survives while the diagnosis degrades to `"" is not a legal value`. The
  assertion was a loose substring matching both messages.

Two follow-ups filed rather than absorbed: **#472** (the vacuous-negative class
across 13 suites) and **#473** (a first-ever series at `###` in a file that
declares no fields yet is outside `--staged`'s reach — a stated, disclosed
limit, not a defect).

## Global Constraints

- **bash 3.2 is the floor.** Guard every array expansion with
  `[ "${#arr[@]}" -gt 0 ]` before `for x in "${arr[@]}"` — an empty array under
  `set -u` aborts the run on macOS bash.
- **Formatting gate:** run `shfmt -i 2 -ci -w <files>` on every bash file. Bare
  `shfmt -w` uses different defaults and still fails `make check`.
- **`capabilities.json` is edited textually**, never via a
  `json.load`/`json.dumps` round-trip (#281). Verify with `git diff --stat`: a
  line count above what you inserted means it reordered — revert and redo.
- **Stage before scanning.** Every gate here reads tracked/staged files only; a
  pre-`git add` clean run proves nothing about what the commit will contain.
- **Gates, in order, before every commit:** `make check` → `bin/run-test-suites.sh`
  → `git commit` (pre-commit hooks). Run all three in the FOREGROUND with a
  generous timeout (suites ~130 s wall). A timed-out commit leaves nothing
  committed.
- **No `--no-verify`, no force-push, no push at all** — the operator handles
  pushes and merges.
- **No CHANGELOG entry.** Release Please generates entries from the Conventional
  Commit; a hand-written one is reverted.
- **Keep closing keywords out of commit messages.** They belong only in the PR
  body, and a negated one ("does not close #N") still closes.
- **Legal `**Protocol:**` values, exactly three:** `compliant`, `pre-protocol`,
  `unrecorded`. Free prose may follow the value on the same line or a
  continuation line.

---

## File Structure

| File | Responsibility | PR |
| --- | --- | --- |
| `docs/pressure-testing-protocol.md` | defines the `**Protocol:**` field, its three values, and the inheritance/override rule | A |
| `skills/*/PRESSURE-TESTS.md` (13) | each field block gains `**Protocol:**`; each head caveat shrinks to a pointer | A |
| `bin/check-pressure-series.sh` | the whole gate — section parsing, depth calibration, both modes, scope disclosure. No other file learns the format. | B |
| `bin/test-check-pressure-series.sh` | the suite; fixtures copied from real files | B |
| `bin/check.sh` | one guarded section calling `--all` | B |
| `.pre-commit-config.yaml` | `bindle-pressure-series` hook calling `--staged` | B |
| `capabilities.json` | `not_a_capability` entries for script, suite, spec, this plan | A, B |

**The parsing model, fixed here so both modes agree.** A **section** runs from a
heading (or file start, for the preamble) to the next heading of any depth. A
section **declares** if it contains any line-anchored `**Model:**`,
`**Content:**` or `**Protocol:**`. A declaring section must contain all three.
A file's **triggering depths** are the heading depths of its declaring sections
(preamble ⇒ the file default `##`); a file with no declaring section triggers on
`##`.

## Amendments — 2026-07-26, after PR #471 merged

PR A shipped the record, and the whole-branch review measured the resulting tree
against this plan. Four things below were wrong about the tree. **These override
any conflicting text later in this document**, including the code snippets,
which have been patched to match.

**1. Count blocks by field line, not by section.** The design spec's `:108` says
a section runs "up to the next heading at the same or shallower depth", which
contradicts the any-depth rule above. It matters: two real series nest a
declaring block inside another section — `verify-then-commit`'s
`#### GREEN follow-up` inside `### Weaker-model rerun`, and
`session-continuity`'s `### Results — series 2` inside `## Claim 9`. Under
same-or-shallower scoping the tree counts **35** blocks; under any-depth, **37**,
which is the real number. **Any-depth is the rule, everywhere.** The suite's
count assertion compares against the line-anchored `**Model:**` count and must
land on 37 — and a green produced by computing both sides the same wrong way is
the #459 failure, not a pass.

**2. The depth set of `verify-then-commit` is `{##, ###, ####}`.** This plan and
the spec both record `{##, ###}`. The block under `#### GREEN follow-up` is real
and predates all of this work. Calibration must be **computed from the file**,
never from a table in a document — a parser written from the table leaves `####`
appends unguarded, and the fixture then proves two of three depths.

**3. A `**Protocol:**` value may be a per-arm override.** `fork-pr-flow`'s #190
series records:

```
**Protocol:** mixed series — per-arm override (#356): arms A–B compliant,
arm C unrecorded
```

A first-token match against the three legal values rejects this — simulated
against the tree, it produces exactly one false failure. The protocol doc grants
`**Protocol:**` the same per-arm override granularity as `**Model:**`, so the
tree is right and the parser learns the shape. The rule:

- first word is a legal token ⇒ simple form, accept;
- else the field must begin `mixed series` **and** contain at least two legal
  tokens ⇒ override form, accept;
- else reject.

**4. One fixture is not enough — three block shapes exist.** `session-continuity`
Claim 9, which this plan names, is the **contiguous** shape (fields on
consecutive lines): 8 of 37. The **blank-line-separated** shape is 29 of 37, and
`license-compliance-auditor` carries a **prose-interleaved** shape where an
unrelated sentence continues the `**Model:**` line with no blank line and is
swallowed into the field's value. Copy one of each out of the repo. A parser
proved against Claim 9 alone is proved against 22% of the tree.

**Also true, and cheap to get wrong:** an unanchored
`grep -c '\*\*Protocol:\*\*'` now returns **50** against 37 line-anchored,
because all thirteen head caveats quote the field name inside a blockquote.
Re-measure; never quote a count from this document.

---

# PR A — the record (`feature/356-protocol-field`)

Branch already exists and carries the design spec at `aae0f6b`.

### Task A1: Define the `**Protocol:**` field in the protocol doc

**Files:**
- Modify: `docs/pressure-testing-protocol.md` (§ Recording, after the
  `**Content:**` bullet)

**Interfaces:**
- Produces: the three legal values and the inheritance rule every later task and
  the gate's parser depend on.

- [x] **Step 1: Add the field definition**

Insert as a new bullet immediately after the `**Content:**` bullet, before the
`any **safety claim**` bullet:

```markdown
- the **protocol status** of the series — a `**Protocol:**` line beside the
  `**Model:**` and `**Content:**` lines, recording whether the series ran under
  this method of record. Exactly three values: `compliant` (arm declared before
  dispatch), `pre-protocol` (predates the arm-declaration rule; grandfathered
  per #261 — stands as recorded, not owed a re-run, not evidence the current
  protocol was met), and `unrecorded` (an honest unknown). Free prose may follow
  the value, on the line or a continuation. Granularity matches `**Model:**`:
  per-series, with a per-arm override — a section that declares any of the three
  fields declares all three, and a series whose status differs from its file's
  default carries its own block rather than relying on prose above it. This
  field is the **single source** for protocol status (#356): a file-head caveat
  states the grandfathering rationale once and points at the fields; it does not
  enumerate which series are covered, because that list decays on the next
  append;
```

- [x] **Step 2: Run the gates**

Run: `make check` then `bin/run-test-suites.sh`
Expected: `All checks passed.` and `all 37 suites pass`. The `stale reps` WARN
for `session-continuity` is pre-existing (#465) and unrelated.

- [x] **Step 3: Commit**

```bash
git add docs/pressure-testing-protocol.md
git commit -m "docs(#356): define the per-series **Protocol:** field and its three values"
```

---

### Task A2: Retrofit the eleven single-status files

Eleven files whose head caveat says **every** series predates the rule, so every
declaring section takes the same value. 26 blocks.

**Files:**
- Modify, at the listed line of the `**Content:**` field in each declaring
  section:

| File | Declaring sections (`**Model:**` line at `91cab1c`) |
| --- | --- |
| `skills/context-graph/PRESSURE-TESTS.md` | 88, 163, 225 |
| `skills/domi-consumer/PRESSURE-TESTS.md` | 25 (preamble) |
| `skills/fork-pr-flow/PRESSURE-TESTS.md` | 46, 159 |
| `skills/hands-on-keyboard/PRESSURE-TESTS.md` | 32, 87, 135, 170 |
| `skills/issue-work-loop/PRESSURE-TESTS.md` | 201, 260, 335 |
| `skills/license-compliance-auditor/PRESSURE-TESTS.md` | 29 (preamble) |
| `skills/maintain-claude-md/PRESSURE-TESTS.md` | 37 (preamble) |
| `skills/repo-hygiene-init/PRESSURE-TESTS.md` | 27 (preamble) |
| `skills/scoped-sequential-prs/PRESSURE-TESTS.md` | 36 (preamble) |
| `skills/package-release-integrity/PRESSURE-TESTS.md` | 54, 127, 158, 231 (**not** 318 — Task A3) |
| `skills/release-captain/PRESSURE-TESTS.md` | 49 |

Line numbers drift as you edit. Re-derive before each file with:

```bash
awk 'BEGIN{h=""} /^#{2,3} /{h=$0} /^\*\*Model:\*\*/{printf "L%-5s %s\n", NR, (h==""?"(preamble)":h)}' <file>
```

- [x] **Step 1: Add the field to every listed section**

After the section's `**Content:**` field (including its continuation lines, i.e.
immediately before the next blank line), add:

```markdown
**Protocol:** pre-protocol — predates the arm-declaration rule (#223);
grandfathered per #261, not owed a re-run.
```

- [x] **Step 2: Verify each declaring section now has all three fields**

Run:

```bash
for f in skills/context-graph/PRESSURE-TESTS.md skills/domi-consumer/PRESSURE-TESTS.md \
         skills/fork-pr-flow/PRESSURE-TESTS.md skills/hands-on-keyboard/PRESSURE-TESTS.md \
         skills/issue-work-loop/PRESSURE-TESTS.md skills/license-compliance-auditor/PRESSURE-TESTS.md \
         skills/maintain-claude-md/PRESSURE-TESTS.md skills/repo-hygiene-init/PRESSURE-TESTS.md \
         skills/scoped-sequential-prs/PRESSURE-TESTS.md skills/release-captain/PRESSURE-TESTS.md; do
  printf '%-58s M=%s C=%s P=%s\n' "$f" \
    "$(grep -c '^\*\*Model:\*\*' "$f")" \
    "$(grep -c '^\*\*Content:\*\*' "$f")" \
    "$(grep -c '^\*\*Protocol:\*\*' "$f")"
done
```

Expected: `M`, `C` and `P` equal on every row.

- [x] **Step 3: Run the gates**

Run: `make check` then `bin/run-test-suites.sh`
Expected: both green.

- [x] **Step 4: Commit**

```bash
git add skills/
git commit -m "docs(#356): record **Protocol:** pre-protocol on the eleven single-status evidence files"
```

---

### Task A3: Retrofit the split files, and split the two coarse blocks

Four files whose protocol status differs *within* the file. Two of them have a
block coarser than the split, so the compliant series needs its own block.

**Files:**
- Modify: `skills/package-release-integrity/PRESSURE-TESTS.md` (section at 318)
- Modify: `skills/verify-then-commit/PRESSURE-TESTS.md` (sections at 42, 116,
  193, 242, 282, 350)
- Modify: `skills/session-continuity/PRESSURE-TESTS.md` (sections at 34, 526,
  631, 732, 906; **new block** under `## Claim 6` at ~368)
- Modify: `skills/release-captain/PRESSURE-TESTS.md` (**new block** under
  `## F-series` at ~265)

**Interfaces:**
- Consumes: the field definition from Task A1.

Values, each derived from the file's own caveat — not guessed:

| File | Section | Value |
| --- | --- | --- |
| `package-release-integrity` | `## E-series — clean release, realistic pin (#224)` (318) | `compliant` — table row reads **yes**, checklist 8/8 (item 9 unchecked) |
| `verify-then-commit` | Claim 1 (42), Claim 2 (116), the three `###` reruns (193, 242, 282) | `pre-protocol` |
| `verify-then-commit` | Claim 3 (350) | `compliant` |
| `session-continuity` | preamble (34) | `pre-protocol` — the file default, covering Claims 1–5 |
| `session-continuity` | Claims 7 (526), 8 (631), 9 (732), Results series 2 (906) | `compliant` |
| `session-continuity` | **new** block under Claim 6 | `compliant` |
| `release-captain` | **new** block under F-series | `compliant` — table row reads **yes**, checklist 8/8 |

- [x] **Step 1: Add `**Protocol:**` to the nine existing declaring sections**

`pre-protocol` sections take the Task A2 wording. `compliant` sections take:

```markdown
**Protocol:** compliant — arm declared before dispatch, fixture checklist 8/8.
```

For `package-release-integrity`'s E-series, keep its recorded qualifier:

```markdown
**Protocol:** compliant — arm predeclared, fixture checklist 8/8 (item 9
unchecked, see below).
```

- [x] **Step 2: Add the two new blocks**

`release-captain`, under `## F-series — defer under a valid .domi-pin (2026-07-18, #225)`,
overriding the file-default `## Method` block:

```markdown
**Model:** Sonnet (dispatched via the harness `sonnet` alias), Claude Code —
all arms of this series.
**Content:** unrecorded (annotated per #339; the dispatch-time content is not
reconstructable after the fact).
**Protocol:** compliant — arm predeclared, fixture checklist 8/8.
```

`session-continuity`, under `## Claim 6 — the opt-in hook automation is discoverable…`:

```markdown
**Model:** Sonnet 5, Claude Code — both arms (annotated per #331; exact dated
snapshot not reconstructable).
**Content:** unrecorded (annotated per #339; the dispatch-time content is not
reconstructable after the fact).
**Protocol:** compliant — arm declared before dispatch (2026-07-19).
```

Before writing either, read the surrounding section and copy its own recorded
model/date rather than the text above if they disagree — the block must state
what the file already says, not what this plan guessed.

- [x] **Step 3: Verify counts, per file**

Run the Step-2 loop from Task A2 against these four files.
Expected: `M = C = P` on every row; `package-release-integrity` 5/5/5,
`verify-then-commit` 6/6/6, `session-continuity` 6/6/6, `release-captain` 2/2/2.

- [x] **Step 4: Verify the whole-tree total**

Run:

```bash
for k in Model Content Protocol; do
  printf '%-9s %s\n' "$k" "$(grep -rh "^\*\*$k:\*\*" skills/*/PRESSURE-TESTS.md | wc -l | tr -d ' ')"
done
```

Expected: `36 36 36` — the 34 blocks at `91cab1c` plus the two new ones.

- [x] **Step 5: Run the gates**

Run: `make check` then `bin/run-test-suites.sh`
Expected: both green.

- [x] **Step 6: Commit**

```bash
git add skills/
git commit -m "docs(#356): record **Protocol:** on the four split files, splitting two coarse blocks"
```

---

### Task A4: Collapse the thirteen head caveats to pointers

The caveats currently enumerate which series are covered. That list is what
decays — `session-continuity`'s already has: it names Claims 6, 7, 7a and 8 as
compliant and omits Claim 9, appended 2026-07-26.

**Files:**
- Modify: all 13 `skills/*/PRESSURE-TESTS.md` (the blockquote below the `# ` title)

- [x] **Step 1: Replace the enumerating body in each caveat**

Keep the `**Method of record:**` line untouched. Replace the enumerating portion
with the pointer form — the rationale stays, the list goes:

```markdown
> **Protocol boundary (#223, #261, #356).** Which side of the arm-declaration
> rule a series falls on is recorded in that series' own `**Protocol:**` field,
> not in this caveat — a list here decays on the next append. `pre-protocol`
> series were gathered without first verifying, per rep, which skill actually
> won the trigger, so an unknown fraction may be **void** (a rep a competing
> skill answered tests nothing about this skill); treat those counts as a
> distribution over skills, not an arm. Per the #261 decision they are
> **grandfathered, not voided** — they stand as recorded, are **not** owed a
> re-run, and are not evidence that the current protocol was met.
```

- [x] **Step 2: Delete the two per-series tables**

In `release-captain` and `package-release-integrity`, remove the
`| Series | Date | Under the protocol? |` table entirely — every row it carried
is now a `**Protocol:**` field on the series itself. Verify no row's information
is lost: each table row must have a corresponding field added in Task A3.

- [x] **Step 3: Delete the per-claim prose splits**

In `verify-then-commit`, remove "**Claims 1 and 2 are pre-protocol; Claim 3 is
protocol-compliant.**". In `session-continuity`, remove the
"**Protocol-compliant:** … **Pre-protocol:** …" enumeration. Both are now
per-series fields.

- [x] **Step 4: Verify no enumeration survives**

Run:

```bash
grep -rn 'Under the protocol?\|Pre-protocol:\*\*\|are pre-protocol' skills/*/PRESSURE-TESTS.md
```

Expected: no output.

- [x] **Step 5: Run the gates**

Run: `make check` then `bin/run-test-suites.sh`
Expected: both green.

- [x] **Step 6: Commit**

```bash
git add skills/
git commit -m "docs(#356): collapse the thirteen head caveats from enumerations to pointers"
```

---

### Task A5: Open PR A

- [x] **Step 1: Confirm the branch is clean and gates are green**

Run: `git status --porcelain` (expect empty) and `make check`.

- [x] **Step 2: Ask the operator before pushing**

The operator handles all pushes. Do not push or open the PR without an explicit
request. When asked, the PR body states: the record change only, no gate yet;
it does **not** close #356 (PR B does); and it names the live stale caveat this
work found in `session-continuity`.

---

# PR B — the gate (`feature/467-series-field-gate`)

Branch off `main` **after PR A merges** (`git checkout main && git pull` — the
post-merge hook runs all suites and relinks, so run it in the foreground).

### Task B1: RED — the `--all` completeness suite

**Files:**
- Create: `bin/test-check-pressure-series.sh`

**Interfaces:**
- Produces: `GATE="$REPO_ROOT/bin/check-pressure-series.sh"`, invoked as
  `--all` and `--staged`; helpers `check`, `contains`, `not_contains`, `equals`
  copied from `bin/test-check-gitleaks.sh`.

- [x] **Step 1: Write the failing suite**

Model the header, helpers, `TMP` sandbox, hook-env scrub and guard-refs pattern
on `bin/test-check-gitleaks.sh`. The first fixture is **copied verbatim from the
repo**, never hand-written:

```bash
# Copied from skills/session-continuity/PRESSURE-TESTS.md — a real, complete,
# three-field block. A fixture hand-written in the form the parser expects
# proves the parser agrees with itself, not with the tree (#459).
#
# THREE shapes must be copied, not one (Amendment 4). Claim 9 below is the
# CONTIGUOUS shape (fields on consecutive lines), only 8 of 37 blocks. Also
# copy a BLANK-LINE-SEPARATED block (29 of 37 — e.g. skills/hands-on-keyboard)
# and the PROSE-INTERLEAVED shape in skills/license-compliance-auditor, where a
# sentence continues the **Model:** line with no blank line and is swallowed
# into the field's value. Assert on all three.
extract_real_block() { # extract_real_block FILE HEADING_REGEX > fixture
  awk -v pat="$2" '
    $0 ~ pat {inblock=1}
    inblock {print}
    inblock && /^#{2,3} / && $0 !~ pat {exit}
  ' "$1"
}

mkdir -p "$TMP/real/skills/session-continuity"
{
  echo "# session-continuity — pressure-test log"
  echo
  extract_real_block "$REPO_ROOT/skills/session-continuity/PRESSURE-TESTS.md" '^## Claim 9'
} >"$TMP/real/skills/session-continuity/PRESSURE-TESTS.md"

out="$("$GATE" --all --root "$TMP/real" 2>&1)"
check "a real three-field block passes --all" contains "1 block" "$out"
check "a real block is not reported incomplete" not_contains "missing" "$out"

# Same block with **Protocol:** deleted — the pre-A state.
sed '/^\*\*Protocol:\*\*/,/^$/d' "$TMP/real/skills/session-continuity/PRESSURE-TESTS.md" \
  >"$TMP/incomplete/skills/session-continuity/PRESSURE-TESTS.md"
out="$("$GATE" --all --root "$TMP/incomplete" 2>&1)"
check "a block missing **Protocol:** is red" equals 1 "$?"
check "the finding names the field" contains "Protocol" "$out"

# An illegal value.
out="$(printf '%s\n' '**Model:** x' '**Content:** unrecorded' '**Protocol:** probably fine' \
  | tee "$TMP/illegal/skills/s/PRESSURE-TESTS.md" >/dev/null; "$GATE" --all --root "$TMP/illegal" 2>&1)"
check "an illegal **Protocol:** value is red" contains "not a legal value" "$out"

# The live-match count — the #459 alarm. Run against the REAL repo.
live="$(grep -rh '^\*\*Model:\*\*' "$REPO_ROOT"/skills/*/PRESSURE-TESTS.md | wc -l | tr -d ' ')"
seen="$("$GATE" --all --count-only)"
check "the parser sees every real block, not zero" equals "$live" "$seen"
```

- [x] **Step 2: Run it to verify it fails**

Run: `chmod +x bin/test-check-pressure-series.sh && bin/test-check-pressure-series.sh`
Expected: every assertion fails — the gate does not exist yet (`command not found`).
Record the failing count; it is the RED baseline.

- [x] **Step 3: Do NOT commit yet — record the RED baseline**

**A deliberately-failing suite cannot be committed in this repo.** `git commit`
runs the `test suites (discovered bin/test-*.sh)` pre-commit hook, which runs
every tracked `bin/test-*.sh`; a RED suite makes the hook red and the commit
never lands. This is not a reason to weaken the suite or to pass `--no-verify`.

So the RED→GREEN boundary here is a *run*, not a commit: write the suite, run
it, write down which assertions fail and why (that record is the RED evidence
the protocol wants), and let Task B2 commit the suite and the script together.
`bin/check-gitleaks.sh` was built exactly this way — 24 assertions, 12 failing
on the first run with no script present, one commit.

Run: `chmod +x bin/test-check-pressure-series.sh && bin/test-check-pressure-series.sh`
Record the failing count and the failure text in your report.

Note for later: `bin/run-test-suites.sh` discovers suites via `git ls-files`, so
an untracked new suite is silently **not** discovered and the run still reports
all suites passing. Until B2 stages it, a green `bin/run-test-suites.sh` says
nothing about this suite.

---

### Task B2: GREEN — implement `--all`

**Files:**
- Create: `bin/check-pressure-series.sh`

**Interfaces:**
- Consumes: nothing.
- Produces: `--all`, `--count-only`, `--root <dir>` (test seam; defaults to the
  repo root). Exit 0 green / 1 red / 0 with `NOT RUN`.

- [x] **Step 1: Write the minimal implementation**

```bash
#!/usr/bin/env bash
#
# check-pressure-series.sh — every rep series records **Model:**, **Content:**
# and **Protocol:** (#467, #356).
#
# A section runs from a heading (or file start) to the next heading of any
# depth. A section that declares ANY of the three fields must declare ALL
# three; **Protocol:** must be compliant | pre-protocol | unrecorded.
#
set -uo pipefail

mode="--all"
root=""
count_only=false
while [ $# -gt 0 ]; do
  case "$1" in
    --all | --staged) mode="$1" ;;
    --count-only) count_only=true ;;
    --root)
      root="$2"
      shift
      ;;
    *)
      echo "usage: bin/check-pressure-series.sh [--all | --staged] [--root DIR]" >&2
      exit 2
      ;;
  esac
  shift
done
[ -n "$root" ] || root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

LEGAL='compliant|pre-protocol|unrecorded'

# A value is either the simple form (first word is a legal token) or the per-arm
# override form the protocol doc sanctions for **Model:** and **Protocol:**
# alike — `mixed series — per-arm override (#356): arms A–B compliant, arm C
# unrecorded`. A first-token match alone rejects the override and produces one
# false failure against the real tree (fork-pr-flow's #190 series).
legal_protocol_value() { # legal_protocol_value FIELD_TEXT
  local v="$1"
  printf '%s' "$v" | grep -Eq "^($LEGAL)\b" && return 0
  printf '%s' "$v" | grep -q '^mixed series' &&
    [ "$(printf '%s' "$v" | grep -Eo "($LEGAL)" | wc -l | tr -d ' ')" -ge 2 ]
}

# Emit one line per declaring section: FILE<TAB>LINE<TAB>DEPTH<TAB>M<TAB>C<TAB>P<TAB>PVALUE
sections() {
  local f
  for f in "$root"/skills/*/PRESSURE-TESTS.md; do
    [ -f "$f" ] || continue
    awk -v F="$f" '
      function flush() {
        if (m || c || p) printf "%s\t%d\t%d\t%d\t%d\t%d\t%s\n", F, sline, depth, m, c, p, pval
        m = c = p = 0; pval = ""
      }
      /^#+ / { flush(); match($0, /^#+/); depth = RLENGTH; sline = NR; next }
      /^\*\*Model:\*\*/    { m = 1 }
      /^\*\*Content:\*\*/  { c = 1 }
      /^\*\*Protocol:\*\*/ { p = 1; pval = $0; sub(/^\*\*Protocol:\*\* */, "", pval) }
      END { flush() }
    ' "$f"
  done
}
```

- [x] **Step 2: Add the `--all` verdict logic**

```bash
run_all() {
  local problems=0 blocks=0 files
  files=0
  while IFS="$(printf '\t')" read -r f line depth m c p pval; do
    blocks=$((blocks + 1))
    [ "$m" = 1 ] || {
      echo "  $f:$line — section declares fields but is missing **Model:**"
      problems=$((problems + 1))
    }
    [ "$c" = 1 ] || {
      echo "  $f:$line — section declares fields but is missing **Content:**"
      problems=$((problems + 1))
    }
    if [ "$p" != 1 ]; then
      echo "  $f:$line — section declares fields but is missing **Protocol:**"
      problems=$((problems + 1))
    elif ! legal_protocol_value "$pval"; then
      echo "  $f:$line — **Protocol:** \"${pval%% *}\" is not a legal value ($LEGAL)"
      problems=$((problems + 1))
    fi
  done <<<"$(sections)"

  files="$(find "$root"/skills -name PRESSURE-TESTS.md 2>/dev/null | wc -l | tr -d ' ')"
  if [ "$problems" -eq 0 ]; then
    echo "  ✓ $blocks series block(s) complete across $files evidence file(s)"
    return 0
  fi
  echo "  ✗ $problems problem(s) in $blocks block(s) across $files evidence file(s)"
  return 1
}

echo "pressure-test series fields:"
if [ "$count_only" = true ]; then
  sections | wc -l | tr -d ' '
  exit 0
fi
case "$mode" in
  --all) run_all ;;
esac
```

- [x] **Step 3: Format, then run the suite**

Run: `shfmt -i 2 -ci -w bin/check-pressure-series.sh && chmod +x bin/check-pressure-series.sh && bin/test-check-pressure-series.sh`
Expected: every `--all` assertion passes, including the live-match count.
**If `--count-only` reports 0 against the real repo, stop** — the parser does not
meet the tree, and passing fixtures mean nothing (#459).

- [x] **Step 4: Commit the suite and the script together**

The suite from Task B1 is still uncommitted by design (see B1 Step 3). Stage
both, so the tree never carries a red discovered suite:

```bash
git add bin/test-check-pressure-series.sh bin/check-pressure-series.sh
git commit -m "feat(#467): add the series-field parser and its --all completeness mode"
```

Before committing, `capabilities.json` needs a `not_a_capability` entry for
**both** new files or `make check` fails with `unclassified — add it to the
inventory or to not_a_capability`. The entries are written out in Task B5
Step 3; add them here, in this commit, rather than leaving the tree unclassified.

---

### Task B3: RED — depth calibration and the `--staged` trigger

**Files:**
- Modify: `bin/test-check-pressure-series.sh`

**Interfaces:**
- Consumes: `sections()` output from Task B2.
- Produces: assertions for `--staged` and the per-file triggering depths.

- [x] **Step 1: Add the failing assertions**

Each fixture is a throwaway git repo under `$TMP`, staged so `--staged` has
something to read. Two fixtures are copied from real files with **opposite**
expected answers, which is what proves the calibration reads the tree:

```bash
# fixture_repo NAME SRC — a git repo whose evidence file is a real one.
fixture_repo() {
  local d="$TMP/$1"
  mkdir -p "$d/skills/s"
  cp "$2" "$d/skills/s/PRESSURE-TESTS.md"
  git -C "$d" init -q
  git -C "$d" add -A
  git -C "$d" -c user.email=t@e -c user.name=t commit -qm base
  printf '%s\n' "$d"
}

# verify-then-commit declares at ##, ### AND #### -> a new ### triggers there,
# and so does a new ####. Calibration is computed from the file, never from a
# table in a document (Amendment 2).
d="$(fixture_repo vtc "$REPO_ROOT/skills/verify-then-commit/PRESSURE-TESTS.md")"
printf '\n### Weaker-model rerun — Opus 5 (2026-07-27)\n\nRED 0/5, GREEN 5/5.\n' \
  >>"$d/skills/s/PRESSURE-TESTS.md"
git -C "$d" add -A
out="$(cd "$d" && "$GATE" --staged 2>&1)"
check "a ### append triggers in a file that declares at ###" contains "missing" "$out"

# release-captain declares at ## only -> a new ### is narrative, no trigger.
d="$(fixture_repo rc "$REPO_ROOT/skills/release-captain/PRESSURE-TESTS.md")"
printf '\n### Honest coverage caveat (new)\n\nProse only.\n' >>"$d/skills/s/PRESSURE-TESTS.md"
git -C "$d" add -A
out="$(cd "$d" && "$GATE" --staged 2>&1)"
check "a ### append does not trigger in a ##-only file" not_contains "missing" "$out"

# A ## append always triggers...
printf '\n## Claim 99 — a new series\n\nRED 0/5, GREEN 5/5.\n' >>"$d/skills/s/PRESSURE-TESTS.md"
git -C "$d" add -A
out="$(cd "$d" && "$GATE" --staged 2>&1)"
check "a ## append with no field block is red" contains "Claim 99" "$out"

# ...unless it carries the escape marker.
git -C "$d" checkout -- . 2>/dev/null || true
printf '\n## Closed mechanically <!-- not-a-series: no reps, bookkeeping only -->\n\nProse.\n' \
  >>"$d/skills/s/PRESSURE-TESTS.md"
git -C "$d" add -A
out="$(cd "$d" && "$GATE" --staged 2>&1)"
check "the not-a-series marker exempts a ## append" not_contains "missing" "$out"

# A ## append WITH all three fields passes.
d="$(fixture_repo ok "$REPO_ROOT/skills/release-captain/PRESSURE-TESTS.md")"
{
  echo
  echo '## Claim 100 — a new, fully recorded series'
  echo
  echo '**Model:** Opus 5 (`claude-opus-5[1m]`), Claude Code — both arms.'
  echo '**Content:** unrecorded (dispatch-time id not captured).'
  echo '**Protocol:** compliant — arm declared before dispatch.'
} >>"$d/skills/s/PRESSURE-TESTS.md"
git -C "$d" add -A
out="$(cd "$d" && "$GATE" --staged 2>&1)"
check "a ## append carrying all three fields passes" not_contains "missing" "$out"
```

- [x] **Step 2: Run to verify the new assertions fail**

Run: `bin/test-check-pressure-series.sh`
Expected: the `--all` assertions still pass; every `--staged` assertion fails
(the mode is unimplemented).

- [x] **Step 3: Commit**

```bash
git add bin/test-check-pressure-series.sh
git commit -m "test(#467): add RED assertions for --staged and per-file depth calibration"
```

---

### Task B4: GREEN — implement `--staged`

**Files:**
- Modify: `bin/check-pressure-series.sh`

- [x] **Step 1: Implement the mode**

```bash
# A file's triggering depths are the depths at which it ALREADY declares
# fields; a file with none defaults to ##. Read from the tree, never assumed:
# ### is the series depth in two files and narrative in the other eleven.
trigger_depths() { # trigger_depths FILE
  local d
  d="$(sections | awk -v F="$1" -F'\t' '$1 == F && $3 > 0 { print $3 }' | sort -un | tr '\n' ' ')"
  [ -n "${d// /}" ] || d="2 "
  printf '%s' "$d"
}

run_staged() {
  if ! git rev-parse --git-dir >/dev/null 2>&1; then
    echo "  NOT RUN: not a git repository, so nothing was read."
    return 0
  fi

  local problems=0 checked=0 file heading depth line depths
  # -U0 so only added lines appear; the diff filter keeps this to evidence files.
  while IFS= read -r file; do
    depths=" $(trigger_depths "$root/$file")"
    while IFS= read -r hit; do
      line="${hit%%:*}"
      heading="${hit#*:}"
      case "$heading" in
        *'<!-- not-a-series:'*) continue ;;
      esac
      depth="$(printf '%s' "$heading" | awk '{match($0, /^#+/); print RLENGTH}')"
      case "$depths" in
        *" $depth "*) ;;
        *) continue ;;
      esac
      checked=$((checked + 1))
      if ! section_declares_all "$file" "$line"; then
        echo "  $file:$line — new series \"$(printf '%s' "$heading" | cut -c1-60)\""
        echo "      is missing **Model:**/**Content:**/**Protocol:**"
        echo "      (or mark it <!-- not-a-series: reason --> if it records no reps)"
        problems=$((problems + 1))
      fi
    done <<<"$(added_headings "$file")"
  done <<<"$(git diff --cached --name-only --diff-filter=AM -- 'skills/*/PRESSURE-TESTS.md')"

  if [ "$problems" -eq 0 ]; then
    echo "  ✓ $checked new series heading(s) in the staged diff carry their fields"
    echo "    scope: staged content only; a file with no field block yet triggers"
    echo "    on ## alone, so a first series at ### depth in a new file is not seen."
    return 0
  fi
  return 1
}
```

`added_headings FILE` lists `LINENO:HEADING` for headings among that file's
added lines, from `git diff --cached -U0`; `section_declares_all FILE LINE`
re-reads the **staged** content (`git show ":$file"`) and applies the same
section rule as `--all`. Implement both with the same awk used by `sections()` —
one parsing model, two callers.

- [x] **Step 2: Format and run the suite**

Run: `shfmt -i 2 -ci -w bin/check-pressure-series.sh && bin/test-check-pressure-series.sh`
Expected: `all N assertions pass`.

- [x] **Step 3: Verify against the real repo, both modes**

Run: `bin/check-pressure-series.sh --all` and, with something staged,
`bin/check-pressure-series.sh --staged`.
Expected: `--all` reports 37 blocks across 13 files; `--staged` reports 0 new
headings and prints its scope line. **37, not 36** — Amendment 1 records the
any-depth section rule that makes it 37, and Task A3's own `36 36 36` was
correct when it ran: the 37th block arrived after it, when `330a86f` gave
sub-claim 1c its own block. Measure it, per Amendment 4's closing line; do not
quote either number from this document.

- [x] **Step 4: Commit**

```bash
git add bin/check-pressure-series.sh bin/test-check-pressure-series.sh
git commit -m "feat(#467): add the --staged mode with per-file depth calibration"
```

---

### Task B5: Wire the gate into both call sites

**Files:**
- Modify: `.pre-commit-config.yaml` (after the `bindle-gitleaks` entry)
- Modify: `bin/check.sh` (beside the gitleaks section, ~line 686)
- Modify: `capabilities.json`

- [x] **Step 1: Add the pre-commit hook**

```yaml
      - id: bindle-pressure-series
        name: pressure-test series fields (Model/Content/Protocol)
        entry: bin/check-pressure-series.sh --staged
        language: script
        pass_filenames: false
        always_run: true
```

- [x] **Step 2: Add the `bin/check.sh` section**

Guarded on existence, exactly like the gitleaks call — fixture repos in
`bin/test-check.sh` contain no `bin/` script, and an unconditional call fails
their clean-exit floors (#295):

```bash
if ! $content_only && [ -x bin/check-pressure-series.sh ]; then
  bin/check-pressure-series.sh --all || problem "pressure-test series fields incomplete (see above)"
fi
```

- [x] **Step 3: Add both ledger entries**

Insert textually in `capabilities.json`'s `not_a_capability` array, beside the
other `bin/*.sh` rows:

```json
    {
      "path": "bin/check-pressure-series.sh",
      "reason": "a gate: every rep series in skills/*/PRESSURE-TESTS.md records **Model:**, **Content:** and **Protocol:** (#467, #356). Tooling, not a capability."
    },
    {
      "path": "bin/test-check-pressure-series.sh",
      "reason": "the self-test for bin/check-pressure-series.sh. Tooling, not a capability."
    },
```

- [x] **Step 4: Verify the ledger did not reorder**

Run: `git add -A && git diff --cached --stat capabilities.json`
Expected: 8 insertions, 0 deletions.

- [x] **Step 5: Re-run the check.sh regression floors**

Run: `bin/test-check.sh`
Expected: pass. This is the suite that catches a `check.sh` edit breaking
fixture-repo clean exits while `make check` stays green.

- [x] **Step 6: Run the full gates**

Run: `make check` then `bin/run-test-suites.sh`
Expected: `make check` now prints the `pressure-test series fields:` section
green; 38 suites pass (37 + the new one).

- [x] **Step 7: Commit**

```bash
git add .pre-commit-config.yaml bin/check.sh capabilities.json
git commit -m "feat(#467): wire the series-field gate into pre-commit and make check"
```

---

### Task B6: Mutation pass

**Files:**
- Create: `$CLAUDE_JOB_DIR/tmp/mutate-pressure-series.sh` (scratchpad; not
  committed — this repo has recorded four instances of losing such a harness,
  tracked as #260)

- [x] **Step 1: Predict before mutating**

Write down which guarantees have no test that would fail if the code stopped
providing them. Write those tests *first*; a test written after watching a
mutant survive tends to assert the mutation rather than the guarantee.

- [x] **Step 2: Run these mutants**

Save the target byte-identically first (`cp`, never `git checkout --`), and
guard each mutant on its target text still being present — a stale mutant
reports GUARD FAILED rather than a false kill.

| # | Mutation | Must be killed by |
| --- | --- | --- |
| 1 | `LEGAL` gains `probably` | the illegal-value assertion |
| 2 | `LEGAL` emptied | every legal-value assertion flips |
| 3 | `trigger_depths` default `2` → `3` | the `##`-append assertion |
| 4 | `trigger_depths` returns all depths always | the `###`-in-`##`-only-file assertion |
| 5 | the `not-a-series` marker branch deleted | the escape-marker assertion |
| 6 | `--all` skips the `**Protocol:**` check | the missing-Protocol assertion |
| 7 | `sections()` requires all three to emit a row | the missing-field assertions |
| 8 | `--staged` reads the worktree instead of `git show :` | a staged-vs-worktree assertion |

- [x] **Step 3: Check every survivor for dead code before writing a test**

A surviving mutant may mean the mutated code is unreachable, or that two
survivors implement one guarantee twice. The fix is then deletion, not a new
test.

- [x] **Step 4: Restore the target and confirm green**

Run: `bin/test-check-pressure-series.sh` and `git diff --stat bin/check-pressure-series.sh`
Expected: suite green, empty diff.

- [x] **Step 5: Commit any tests the pass added**

```bash
git add bin/test-check-pressure-series.sh
git commit -m "test(#467): kill the mutants the prediction pass missed"
```

---

### Task B7: Update the protocol doc's enforcement note, and open PR B

**Files:**
- Modify: `docs/pressure-testing-protocol.md` (§ Recording, the `**Protocol:**`
  bullet from Task A1)

- [x] **Step 1: Name the gate in the field's definition**

Append to the `**Protocol:**` bullet:

```markdown
  Enforced by `bin/check-pressure-series.sh`: `--staged` (the
  `bindle-pressure-series` pre-commit hook) reddens when a new series heading is
  appended without its fields, and `--all` (`make check`) reddens when any block
  is incomplete or carries an illegal value.
```

- [x] **Step 2: Run the gates**

Run: `make check` then `bin/run-test-suites.sh`
Expected: both green.

- [x] **Step 3: Commit**

```bash
git add docs/pressure-testing-protocol.md
git commit -m "docs(#467): name the gate that enforces the three recorded fields"
```

- [x] **Step 4: Ask the operator before pushing**

Do not push or open the PR without an explicit request. When asked, the PR body
carries the closing keywords for **#467 and #356** (body only, never a commit
message), states the measured block count, and names the stated limit:
a first series at `###` depth in a file with no field block yet is not caught by
`--staged`.

---

## Self-Review

**Spec coverage.** `**Protocol:**` field + three values → A1. Retrofit of all 34
blocks → A2, A3. Two coarse blocks split → A3. Caveats collapsed → A4. Two
modes → B2, B4. Depth calibration → B4, asserted in B3. Escape marker → B3, B4.
Verdicts and scope disclosure → B2, B4. Fixture copied from reality → B1.
Live-match count → B1, checked in B2 Step 3. Mutation pass → B6. Wiring and
ledger → A1, B5. Two-PR delivery → the PR A / PR B split.

**Placeholders.** None: every step names exact files, exact commands, exact
expected output, and carries the code it refers to.

**Type consistency.** `sections()` emits the same tab-separated row consumed by
`run_all()` and `trigger_depths()`; `--root` is the single test seam used by
every fixture; `section_declares_all` and `added_headings` are named in B4 Step 1
and used only there. The gate's flags (`--all`, `--staged`, `--count-only`,
`--root`) are identical across B1, B2, B3, B4 and B5.
