# Portable facts loader (Phase 2a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `bin/facts-index.sh` (deterministic, body-free enumeration of a
project's `facts/` store) and a `/session-start` step that selects and reads at
most five fact bodies against the session objective, so Phase 1's shed tail
reaches context for Claude and Codex alike.

**Architecture:** One read-only bash script enumerates
`<notes-home>/projects/<project>/facts/*.md`, printing
`<slug><TAB><type><TAB><description>` parsed from frontmatter only — it never
reads a body, so its cost scales with fact *count*, not fact size. The
`/session-start` command runs it, and the *model* picks which bodies to read;
Bindle ships no ranker (spec constraint 3). The command layer is what Codex
runs through the interop layer, so both agents get identical retrieval.

**Tech Stack:** bash 3.2 (macOS floor), `awk`/`sed`/`sort` only, `python3` only
where an existing resolver already uses it (settings.json read). No new
dependencies. Suite is a plain `bin/test-facts-index.sh` in the repo's existing
fixture style (`bin/test-session-context.sh` is the model).

**Source spec:** `docs/superpowers/specs/2026-07-26-facts-loader-phase2a-design.md`.

## Global Constraints

- **Read-only toward the notes home.** The loader never writes a fact, never
  bumps `modified`, never repairs frontmatter (spec constraint 4).
- **Degrade silently.** Absent notes home, absent `facts/`, or an empty one:
  exit 0, print nothing, block nothing (spec constraint 5).
- **Never read a fact body.** Only the leading `---`-delimited frontmatter
  block, and only its `name`, `description`, and `metadata.type` keys.
- **No ranker in Bindle code.** The script lists; the model chooses (constraint 3).
- **Body cap: at most 5 fact bodies per session**, and zero when the session has
  no objective and no handoff next-step.
- **bash 3.2 compatible.** No `mapfile`, no associative arrays, no `${var^^}`.
  Guard every array expansion with `[ "${#arr[@]}" -gt 0 ]` under `set -u`.
- **Formatting gate:** run `shfmt -i 2 -ci -w <files>` — bare `shfmt -w` uses
  different defaults and still fails `make check`.
- **Inventory gate:** every new file under `bin/` needs a `capabilities.json`
  entry in the same commit, *except* `bin/test-*.sh`, which
  `bin/check-inventory.py:350` already excludes by pattern.
- **Suite discovery gate:** `bin/run-test-suites.sh` discovers suites via
  `git ls-files` — `git add` a new suite before trusting its green.
- **Full local gate before every commit:** `make check` green, then
  `bin/run-test-suites.sh` green (`make check` does *not* run the suites), then
  `gitleaks git . --redact` by hand. Branch is `feature/422-phase2a-loader`;
  never commit to `main`, never push (the operator pushes).

## Decision this plan settles (the spec left it open)

The spec says `bin/facts-index.sh` "resolves the notes home the same way the
rest of Bindle does." Verified against the tree on 2026-07-26: **there is no
single way.** Three resolvers exist and they differ.

| Script | Chain |
|---|---|
| `bin/notes-home.sh:88` | `$BINDLE_NOTES_DIR` → `$CLAUDE_KIT_NOTES_DIR` → `~/.bindle` |
| `bin/session-context.sh:55` | the above, plus persisted `env.BINDLE_NOTES_DIR` from `~/.claude/settings.json` before the `~/.bindle` default |
| `bin/check-private-info.sh:48-55` | the first chain, plus a deprecated `~/.claude-kit` read fallback |

**Decision: mirror `bin/session-context.sh`'s chain**, including the persisted
settings.json read and the `--home DIR` test override.

- It is the only chain that resolves correctly for a **Codex** session, which
  never inherits Claude Code's `env` block — spec constraint 1 (same behavior
  for both agents) picks it outright.
- It is the newest chain and the nearest analogue: the same "runs at session
  start, degrades silently, exits 0 always" posture.
- The deprecated `~/.claude-kit` *read* fallback is deliberately **not**
  copied: `facts/` is a Phase 1 (2026-07) construct, so no fact can predate the
  rename. `$CLAUDE_KIT_NOTES_DIR` stays supported because the skill documents it.

---

### Task 1: `bin/facts-index.sh` + `bin/test-facts-index.sh`

**Files:**
- Create: `bin/facts-index.sh`
- Create: `bin/test-facts-index.sh`
- Modify: `capabilities.json` (one new entry under `capabilities`)

**Interfaces:**
- Consumes: `bin/slugify.sh` (existing; project-slug rule),
  `bin/session-context.sh:55`'s resolution chain (copied, not sourced — the
  repo's existing scripts each carry their own copy).
- Produces: `bin/facts-index.sh [--cwd DIR] [--home DIR]`, printing zero or more
  lines of `<slug><TAB><type><TAB><description>`, sorted by slug (`LC_ALL=C`),
  always exit 0. Task 2's `/session-start` step calls it with no arguments.

- [ ] **Step 1: Write the failing test suite**

Create `bin/test-facts-index.sh`:

```bash
#!/usr/bin/env bash
#
# test-facts-index.sh — exercise bin/facts-index.sh against throwaway notes
# homes and a scrubbed environment. Never touches the real ~/.bindle,
# ~/.claude, or any real git repo.
#
# Usage: bin/test-facts-index.sh
#
set -uo pipefail

# Under a git hook (pre-commit/post-merge), git exports GIT_DIR and friends to
# subprocesses; in a worktree GIT_DIR is absolute, so the fixture-repo git
# calls below would hit the real repository. Scrub the hook environment.
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FI="$REPO_ROOT/bin/facts-index.sh"

pass=0 fail=0
check() { # check "description" command...
  local desc="$1"
  shift
  if "$@"; then
    printf '  ✓ %s\n' "$desc"
    pass=$((pass + 1))
  else
    printf '  ✗ %s\n' "$desc"
    fail=$((fail + 1))
  fi
}

contains() { grep -qF -- "$1" <<<"$2"; }
not_contains() { ! grep -qF -- "$1" <<<"$2"; }
exit_is() { [ "$1" -eq "$2" ]; }
is_empty() { [ -z "$1" ]; }
line_count_is() { [ "$(grep -c . <<<"$2")" -eq "$1" ]; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# make_repo DIR — a throwaway git repo whose basename is the project slug.
make_repo() {
  mkdir -p "$1"
  git -C "$1" init -q
  git -C "$1" config user.email t@example.com
  git -C "$1" config user.name t
  : >"$1/README.md"
  git -C "$1" add README.md
  git -C "$1" commit -qm init
}

# write_fact FILE SLUG TYPE DESCRIPTION — a well-formed fact per the
# session-continuity schema (type/modified nested under metadata).
write_fact() {
  cat >"$1" <<EOF
---
name: $2
description: "$4"
metadata:
  node_type: memory
  type: $3
  modified: 2026-07-26T00:00:00.000Z
---

Body of $2. This line must never appear in the index output.
EOF
}

# run_fi HOME_DIR [env VAR=... ...] -- ARGS...
run_fi() {
  local home_dir="$1"
  shift
  local envs=()
  while [ $# -gt 0 ] && [ "$1" != "--" ]; do
    envs+=("$1")
    shift
  done
  shift # the --
  env -u BINDLE_NOTES_DIR -u CLAUDE_KIT_NOTES_DIR HOME="$home_dir" \
    ${envs[@]+"${envs[@]}"} "$FI" "$@"
}

REPO="$TMP/demo-proj"
make_repo "$REPO"
H="$TMP/home"
mkdir -p "$H"

echo "1. no notes home at all:"
out="$(run_fi "$H" -- --cwd "$REPO" 2>&1)"
status=$?
check "exits 0 with no notes home" exit_is "$status" 0
check "prints nothing" is_empty "$out"

echo
echo "2. notes home exists but the project has no facts/ dir:"
NOTES="$TMP/notes"
mkdir -p "$NOTES/projects/demo-proj/sessions"
out="$(run_fi "$H" BINDLE_NOTES_DIR="$NOTES" -- --cwd "$REPO" 2>&1)"
status=$?
check "exits 0 with no facts dir" exit_is "$status" 0
check "prints nothing" is_empty "$out"

echo
echo "3. empty facts/ dir:"
FACTS="$NOTES/projects/demo-proj/facts"
mkdir -p "$FACTS"
out="$(run_fi "$H" BINDLE_NOTES_DIR="$NOTES" -- --cwd "$REPO" 2>&1)"
status=$?
check "exits 0 on an empty facts dir" exit_is "$status" 0
check "prints nothing" is_empty "$out"

echo
echo "4. well-formed facts:"
write_fact "$FACTS/zeta-fact.md" zeta-fact project "the zeta thing is true"
write_fact "$FACTS/alpha-fact.md" alpha-fact feedback "always do the alpha thing"
out="$(run_fi "$H" BINDLE_NOTES_DIR="$NOTES" -- --cwd "$REPO" 2>&1)"
check "lists both facts" line_count_is 2 "$out"
check "emits slug TAB type TAB description" \
  contains "alpha-fact	feedback	always do the alpha thing" "$out"
check "sorts by slug (alpha before zeta)" \
  [ "$(head -1 <<<"$out" | cut -f1)" = alpha-fact ]
check "strips the quotes around description" not_contains '"always' "$out"
check "never reads a body" not_contains "must never appear" "$out"

echo
echo "5. MEMORY.md is the harness index, not a fact:"
# The real MEMORY.md is a list of markdown links; written link-free here so
# this plan's own copy of the fixture doesn't trip make check's link checker.
cat >"$FACTS/MEMORY.md" <<'EOF'
- Alpha -> alpha-fact.md — hook
EOF
out="$(run_fi "$H" BINDLE_NOTES_DIR="$NOTES" -- --cwd "$REPO" 2>&1)"
check "still lists only the two facts" line_count_is 2 "$out"
check "does not list MEMORY" not_contains "MEMORY" "$out"

echo
echo "6. malformed facts stay VISIBLE (an invisible fact is worse):"
cat >"$FACTS/no-frontmatter.md" <<'EOF'
Just a body, no frontmatter block at all.
EOF
cat >"$FACTS/unterminated.md" <<'EOF'
---
name: unterminated
description: "never closed"
EOF
out="$(run_fi "$H" BINDLE_NOTES_DIR="$NOTES" -- --cwd "$REPO" 2>&1)"
check "lists all four files" line_count_is 4 "$out"
check "falls back to the filename slug" contains "no-frontmatter		" "$out"
check "an unterminated block yields an empty description" \
  contains "unterminated		" "$out"
rm -f "$FACTS/no-frontmatter.md" "$FACTS/unterminated.md"

echo
echo "7. body lines can never leak into a field:"
cat >"$FACTS/decoy.md" <<'EOF'
---
name: decoy
description: "the real description"
metadata:
  type: reference
---

description: "a body line that looks like frontmatter"
name: not-the-slug
EOF
out="$(run_fi "$H" BINDLE_NOTES_DIR="$NOTES" -- --cwd "$REPO" 2>&1)"
check "uses the frontmatter description" contains "the real description" "$out"
check "ignores the body decoy" not_contains "looks like frontmatter" "$out"
check "ignores the body name" not_contains "not-the-slug" "$out"
rm -f "$FACTS/decoy.md"

echo
echo "8. a tab inside a description cannot forge a column:"
printf -- '---\nname: tabby\ndescription: "a\tb"\nmetadata:\n  type: project\n---\n\nbody\n' \
  >"$FACTS/tabby.md"
out="$(run_fi "$H" BINDLE_NOTES_DIR="$NOTES" -- --cwd "$REPO" 2>&1)"
check "the tabby row still has exactly 3 fields" \
  [ "$(grep tabby <<<"$out" | awk -F'\t' '{print NF}')" = 3 ]
rm -f "$FACTS/tabby.md"

echo
echo "9. non-.md files and subdirectories are not facts:"
: >"$FACTS/notes.txt"
mkdir -p "$FACTS/subdir"
out="$(run_fi "$H" BINDLE_NOTES_DIR="$NOTES" -- --cwd "$REPO" 2>&1)"
check "still lists only the two facts" line_count_is 2 "$out"
rm -rf "$FACTS/notes.txt" "$FACTS/subdir"

echo
echo "10. resolution chain:"
KITNOTES="$TMP/kitnotes"
mkdir -p "$KITNOTES/projects/demo-proj/facts"
write_fact "$KITNOTES/projects/demo-proj/facts/kit-fact.md" kit-fact project "from the deprecated var"
out="$(run_fi "$H" CLAUDE_KIT_NOTES_DIR="$KITNOTES" -- --cwd "$REPO" 2>&1)"
check "honors the deprecated CLAUDE_KIT_NOTES_DIR" contains "kit-fact" "$out"
out="$(run_fi "$H" BINDLE_NOTES_DIR="$NOTES" CLAUDE_KIT_NOTES_DIR="$KITNOTES" -- --cwd "$REPO" 2>&1)"
check "BINDLE_NOTES_DIR outranks the deprecated var" not_contains "kit-fact" "$out"

HP="$TMP/persisted-home"
mkdir -p "$HP/.claude"
cat >"$HP/.claude/settings.json" <<EOF
{"env": {"BINDLE_NOTES_DIR": "$NOTES"}}
EOF
out="$(run_fi "$HP" -- --cwd "$REPO" --home "$HP/.claude" 2>&1)"
check "reads a persisted env.BINDLE_NOTES_DIR (the Codex path)" \
  contains "alpha-fact" "$out"

HB="$TMP/broken-home"
mkdir -p "$HB/.claude"
echo 'not json {' >"$HB/.claude/settings.json"
out="$(run_fi "$HB" -- --cwd "$REPO" --home "$HB/.claude" 2>&1)"
status=$?
check "exits 0 on an unparseable settings.json" exit_is "$status" 0
check "leaks no python traceback" not_contains "Traceback" "$out"

echo
echo "11. project identity:"
OTHER="$TMP/My_Other.Proj"
make_repo "$OTHER"
mkdir -p "$NOTES/projects/my-other-proj/facts"
write_fact "$NOTES/projects/my-other-proj/facts/other-fact.md" other-fact project "belongs to the other project"
out="$(run_fi "$H" BINDLE_NOTES_DIR="$NOTES" -- --cwd "$OTHER" 2>&1)"
check "slugifies the repo basename (My_Other.Proj -> my-other-proj)" \
  contains "other-fact" "$out"
check "does not leak the other project's facts" not_contains "alpha-fact" "$out"

echo
echo "12. usage errors are loud, everything else is silent:"
out="$(run_fi "$H" BINDLE_NOTES_DIR="$NOTES" -- --bogus 2>&1)"
status=$?
check "exits 2 on an unknown flag" exit_is "$status" 2
check "names the flag" contains "--bogus" "$out"

echo
echo "passed $pass, failed $fail"
[ "$fail" -eq 0 ]
```

- [ ] **Step 2: Run the suite to verify it fails**

```bash
chmod +x bin/test-facts-index.sh
bin/test-facts-index.sh
```

Expected: FAIL — every `run_fi` call errors because `bin/facts-index.sh` does
not exist yet (`No such file or directory`), and the final line reports a
non-zero `failed` count.

- [ ] **Step 3: Write the script**

Create `bin/facts-index.sh`:

```bash
#!/usr/bin/env bash
#
# facts-index.sh — print one line per durable fact in the current project's
# notes home, as <slug><TAB><type><TAB><description>, sorted by slug.
#
# The index, never a body: this reads only the leading '---'-delimited
# frontmatter block of each facts/<slug>.md, so its cost is bounded by fact
# COUNT, not fact size. Selecting which bodies to then read is the model's job
# (docs/superpowers/specs/2026-07-26-facts-loader-phase2a-design.md,
# constraint 3) — Bindle ships no ranker.
#
# Usage:
#   bin/facts-index.sh [--cwd DIR] [--home DIR]
#
#   --cwd DIR   directory to orient from (default: $PWD)
#   --home DIR  Claude home override, for notes-home resolution parity with
#               bin/session-context.sh (tests only; does not affect real installs)
#
# Read-only toward the notes home: never writes, never bumps `modified`, never
# repairs frontmatter (#423 owns validation). Degrades silently — no notes
# home, no facts/ dir, or an empty one prints nothing and exits 0. A MALFORMED
# fact is listed with an empty type/description rather than skipped: an
# invisible fact is worse than an ugly line.
#
# Exit codes: 0 always, except 2 for a usage error (bad flag/missing argument).
#
set -uo pipefail

CWD="$PWD"

while [ $# -gt 0 ]; do
  case "$1" in
    --cwd)
      [ $# -ge 2 ] || {
        echo "facts-index.sh: --cwd needs a directory argument" >&2
        exit 2
      }
      CWD="$2"
      shift 2
      ;;
    --home)
      [ $# -ge 2 ] || {
        echo "facts-index.sh: --home needs a directory argument" >&2
        exit 2
      }
      CLAUDE_HOME_OVERRIDE="$2"
      shift 2
      ;;
    *)
      echo "facts-index.sh: unknown argument: $1" >&2
      exit 2
      ;;
  esac
done

# --- notes-home resolution (mirrors bin/session-context.sh's chain) ----------
#
# The persisted settings.json read is what makes this work for a CODEX session,
# which never inherits Claude Code's env block. bin/notes-home.sh's chain stops
# at the environment; this one does not. The deprecated ~/.claude-kit READ
# fallback in bin/check-private-info.sh is deliberately absent: facts/ is a
# Phase 1 (2026-07) construct, so no fact can predate the rename.

resolve_notes_home() {
  if [ -n "${BINDLE_NOTES_DIR:-}" ]; then
    NOTES_DIR="$BINDLE_NOTES_DIR"
  elif [ -n "${CLAUDE_KIT_NOTES_DIR:-}" ]; then
    NOTES_DIR="$CLAUDE_KIT_NOTES_DIR"
  else
    local claude_home="${CLAUDE_HOME_OVERRIDE:-${HOME}/.claude}"
    local persisted=""
    if [ -f "$claude_home/settings.json" ]; then
      persisted="$(python3 -c 'import json,sys
try:
    print(json.load(open(sys.argv[1])).get("env", {}).get("BINDLE_NOTES_DIR", ""))
except Exception:
    print("")' "$claude_home/settings.json" 2>/dev/null)"
    fi
    if [ -n "$persisted" ]; then
      NOTES_DIR="$persisted"
    else
      NOTES_DIR="${HOME}/.bindle"
    fi
  fi
}

# --- project identity (same rule as bin/session-context.sh) -----------------

REPO_ROOT="$(git -C "$CWD" rev-parse --show-toplevel 2>/dev/null || true)"
if [ -n "$REPO_ROOT" ]; then
  PROJECT_DIR="$REPO_ROOT"
else
  PROJECT_DIR="$CWD"
fi
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="$(basename "$PROJECT_DIR" | "$SCRIPT_DIR/slugify.sh" 2>/dev/null || basename "$PROJECT_DIR")"

# --- frontmatter parsing ----------------------------------------------------

# fm_block FILE — print the leading '---'-delimited block (delimiters
# excluded), or nothing when the file has no terminated block. Parsing ONCE
# into this block is what stops a body line that happens to start with
# "description:" from leaking into a field (bin/check.sh:117 makes the same
# argument for Claude frontmatter).
fm_block() {
  local file="$1" close
  [ "$(head -1 "$file" 2>/dev/null)" = "---" ] || return 0
  close="$(awk 'NR>1 && /^---[[:space:]]*$/ {print NR; exit}' "$file")"
  [ -n "$close" ] || return 0
  sed -n "2,$((close - 1))p" "$file"
}

# clean_field TEXT — one safe TSV field: strip a matched pair of surrounding
# quotes, turn any embedded tab into a space (a tab in a description must not
# forge a fourth column), and trim the edges.
clean_field() {
  local v="$1"
  case "$v" in
    \"*\") v="${v#\"}" && v="${v%\"}" ;;
    \'*\') v="${v#\'}" && v="${v%\'}" ;;
  esac
  printf '%s' "$v" | tr '\t' ' ' | sed -e 's/^[[:space:]]*//' -e 's/[[:space:]]*$//'
}

# fm_top BLOCK KEY — value of a top-level frontmatter key (first occurrence).
fm_top() {
  sed -n -E "s/^$2:[[:space:]]*//p" <<<"$1" | head -1
}

# fm_meta BLOCK KEY — value of an INDENTED key under `metadata:`. The schema
# nests type/modified there (session-continuity SKILL.md, "Fact files"), so a
# top-level match would silently miss them.
fm_meta() {
  awk -v key="$2" '
    /^metadata:[[:space:]]*$/ { inmeta = 1; next }
    /^[^[:space:]]/ { inmeta = 0 }
    inmeta && $0 ~ "^[[:space:]]+" key ":" {
      sub("^[[:space:]]+" key ":[[:space:]]*", "")
      print
      exit
    }
  ' <<<"$1"
}

# --- enumeration ------------------------------------------------------------

resolve_notes_home
FACTS_DIR="$NOTES_DIR/projects/$PROJECT/facts"
[ -d "$FACTS_DIR" ] || exit 0

emit_fact() {
  local file="$1" block slug type desc
  block="$(fm_block "$file")"
  slug="$(clean_field "$(fm_top "$block" name)")"
  [ -n "$slug" ] || slug="$(basename "$file" .md)"
  type="$(clean_field "$(fm_meta "$block" type)")"
  desc="$(clean_field "$(fm_top "$block" description)")"
  printf '%s\t%s\t%s\n' "$slug" "$type" "$desc"
}

{
  for f in "$FACTS_DIR"/*.md; do
    [ -f "$f" ] || continue
    [ "$(basename "$f")" = "MEMORY.md" ] && continue
    emit_fact "$f"
  done
} | LC_ALL=C sort
exit 0
```

- [ ] **Step 4: Format, then run the suite to verify it passes**

```bash
shfmt -i 2 -ci -w bin/facts-index.sh bin/test-facts-index.sh
chmod +x bin/facts-index.sh
bin/test-facts-index.sh
```

Expected: every check `✓`, final line `passed 30, failed 0`, exit 0. If a check
fails, fix the **script**, not the assertion, unless the assertion is provably
wrong about the schema.

- [ ] **Step 5: Sanity-check it against the real notes home**

```bash
bin/facts-index.sh | head -20
```

Expected: one line per file in `<notes-home>/projects/bindle/facts/`, no
`MEMORY.md` row, no body text, exit 0. This is a read-only look; do not edit
anything it reveals.

- [ ] **Step 6: Add the capabilities.json entry**

Edit `capabilities.json` by hand — **never** via a `json.load`/`json.dumps`
round-trip, which reorders all ~230 entries. Insert into the `capabilities`
array, keeping the file's existing key order:

```json
    {
      "name": "facts-index",
      "type": "script",
      "path": "bin/facts-index.sh",
      "description": "Enumerate the current project's durable facts from the notes home as slug/type/description lines, reading frontmatter only and never a fact body; the deterministic half of the /session-start facts loader.",
      "provider": {
        "claude": "installed",
        "codex": "untested"
      },
      "maturity": "tested",
      "mutation": [],
      "version_introduced": "0.11.0"
    },
```

`bin/test-facts-index.sh` needs no entry: `bin/check-inventory.py:350` excludes
`^bin/test-.*\.sh$` by pattern.

- [ ] **Step 7: Refresh the manifest if the inventory changed it**

```bash
make manifest
git status --short install-manifest.tsv
```

Expected: either no change (scripts are not installed assets) or a regenerated
`install-manifest.tsv` — commit whichever state `make check` requires.

- [ ] **Step 8: Run the full local gate**

```bash
git add bin/facts-index.sh bin/test-facts-index.sh capabilities.json install-manifest.tsv
make check
bin/run-test-suites.sh
gitleaks git . --redact
```

Expected: `make check` green with **no PARTIAL banner** (the `git add` above is
what removes it); `bin/run-test-suites.sh` reports one more suite than the last
recorded count (36) and all pass; gitleaks reports no leaks.

- [ ] **Step 9: Commit**

```bash
git commit -m "feat(#422): enumerate a project's facts store without reading bodies

bin/facts-index.sh prints <slug>TAB<type>TAB<description> from frontmatter
only, so the index costs fact count rather than fact size. Resolution mirrors
bin/session-context.sh's chain (including the persisted settings.json read)
because that is the only variant a Codex session resolves correctly."
```

---

### Task 2: the `/session-start` selection step

**Files:**
- Modify: `commands/session-start.md:21-46` (renumber steps; insert the new step 4)
- Modify: `skills/session-continuity/SKILL.md` ("Fact files" section — one
  paragraph naming the loader)

**Interfaces:**
- Consumes: `bin/facts-index.sh` from Task 1 (no arguments; TSV on stdout).
- Produces: the summary contract Task 3 grades — the ≤15-line summary names
  every fact body loaded, or says nothing at all when none were.

- [ ] **Step 1: Insert the selection step into the command**

In `commands/session-start.md`, replace the block from `3. Identify the
validation gates` through the end of step 5 with (steps 3 and 5→6 keep their
existing text verbatim; only the new step 4 and the renumbering are new):

```markdown
3. Identify the validation gates for this repo: from the profile if it lists
   them, otherwise infer from the repo (Makefile, CI workflow, test config,
   pre-commit config, CONTRIBUTING/CLAUDE.md). Don't run them yet.
4. Load the durable facts that bear on this session — index always, bodies
   rarely:
   - Run `<bindle>/bin/facts-index.sh` (resolve `<bindle>` the same way step 1
     resolves the skill). It prints one `<slug><TAB><type><TAB><description>`
     line per fact, or nothing at all — no notes home, no `facts/` dir, or an
     empty one is normal and silent. Say nothing about facts in that case.
   - Against the session objective ("$ARGUMENTS", or the next step named by the
     latest handoff), pick the facts whose descriptions bear on it and read
     **at most 5** bodies. With no objective and no handoff next-step, read
     **none** — the cap is a ceiling, not a quota.
   - Name the ones you read in the step-5 summary, so the operator can say "not
     that one."
5. Summarize in ≤15 lines: where the repo stands, what the last session
   finished/deferred (per notes), the gates that must pass before committing,
   and any safety notes from the profile (branch discipline, "never touch X").
   If the repo state above lists any in-progress issues, ask whether each is
   still accurate — a stale `status:` label is a lie the dashboard shows
   live, and catching it here means it doesn't sit for another session. (No
   listing appears if the repo has no such issues, or `gh` isn't installed or
   authenticated — skip silently in that case.)
6. Objective: if the user provided one ("$ARGUMENTS"), restate it as the
   session goal and note anything in the profile/handoff that conflicts with
   it. If none was provided and the latest handoff names a clear next step,
   propose that. Only ask for an objective if you have neither.
```

Note the renumber: the old step 4 (summary) becomes step 5 and the old step 5
(objective) becomes step 6. Verify the finished file has exactly one
`5. Summarize` and one `6. Objective`, and that nothing else in the repo
references `/session-start`'s steps by number
(`grep -rn "session-start" --include="*.md" . | grep -i "step"`).

- [ ] **Step 2: Add `Bash(bin/facts-index.sh:*)` to the command's allowed-tools**

`commands/session-start.md:4` currently reads:

```
allowed-tools: Bash(git status:*), Bash(git branch:*), Bash(git log:*), Bash(date:*), Bash(gh issue list:*)
```

Replace with:

```
allowed-tools: Bash(git status:*), Bash(git branch:*), Bash(git log:*), Bash(date:*), Bash(gh issue list:*), Bash(bin/facts-index.sh:*)
```

- [ ] **Step 3: Document the loader in the skill's "Fact files" section**

In `skills/session-continuity/SKILL.md`, immediately after the bullet list that
ends `...it marks work, not an error.`, add:

```markdown
### Reading facts (the loader)

`<bindle>/bin/facts-index.sh` prints one
`<slug><TAB><type><TAB><description>` line per fact and never reads a body, so
enumerating the whole store is cheap. `/session-start` runs it and then reads
**at most five** bodies — the ones whose descriptions bear on the session
objective — and names them in its summary. With no objective and no handoff
next-step it reads none. Selection is the model's job: Bindle ships no ranker,
and the index is the only thing loaded unconditionally.
```

- [ ] **Step 4: Sync `capabilities.json` for the edited descriptions**

Editing a `SKILL.md` or command `description:` breaks `make check` until the
mirrored `capabilities.json` entry matches. Neither edit above touches a
`description:` frontmatter line — confirm that with:

```bash
git diff -- commands/session-start.md skills/session-continuity/SKILL.md | grep -E '^[+-]description:'
```

Expected: no output. If there *is* output, sync the matching entry by hand
(remember a name may have more than one entry; match on `path`, not `name`).

- [ ] **Step 5: Run the full local gate**

```bash
git add commands/session-start.md skills/session-continuity/SKILL.md
make check
bin/run-test-suites.sh
```

Expected: both green. `make check`'s link check will follow the new relative
paths — a broken one fails here, not later.

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(#422): load the facts that bear on the session objective

/session-start now runs bin/facts-index.sh, reads at most five fact bodies
selected against the objective (none without one), and names what it loaded.
Index always, bodies rarely — the shed tail from Phase 1 finally has a reader."
```

---

### Task 3: pressure-test C1–C4 and record the verdict

**Files:**
- Modify: `skills/session-continuity/PRESSURE-TESTS.md` (append one series)
- Create (scratchpad only, never committed): fixture builder + per-rep roots

**Interfaces:**
- Consumes: the shipped Task 1 + Task 2 behavior. Per the profile's standing
  fact, `~/.claude/skills/<name>` symlinks to the **primary checkout**, so
  `SKILL.md`/command edits made here are live for subagents immediately — reps
  run pre-merge, on this branch. Confirm before dispatch, don't assume.
- Produces: either a VERIFIED series (draft marker never applied) or a recorded
  failure plus a `draft` marker on the new command step.

**Method of record:** `docs/pressure-testing-protocol.md`. Arm declared
**before** dispatch or the reps are void.

- [ ] **Step 1: Run the two mechanical claims first (they need no subagent)**

C4 (no notes home) and the silence half of C3 are deterministic at the script
layer and already covered by Task 1's suite (checks 1–3). Record that, and run
the command-layer version by hand from a scrubbed environment:

```bash
env -u BINDLE_NOTES_DIR -u CLAUDE_KIT_NOTES_DIR HOME="$(mktemp -d)" \
  bin/facts-index.sh --cwd "$PWD" --home "$(mktemp -d)"; echo "exit=$?"
```

Expected: no output, `exit=0`.

- [ ] **Step 2: Declare the arm in writing, before any dispatch**

Append to `skills/session-continuity/PRESSURE-TESTS.md` a series header naming:
the content id (`bin/skill-content-id.sh`, captured now and re-verified
immediately before the first rep), the worker model, and the two arms —
RED = `commands/session-start.md` at `origin/main` (no step 4);
GREEN = the same file on this branch. Both arms get the contract **as files**,
so what is under test is fixed regardless of what is installed.

- [ ] **Step 3: Build one fixture per rep**

Each rep gets its own throwaway repo + notes home (concurrent reps sharing a
directory collide). The notes home holds `facts/` with ~6 facts: one whose
description plainly bears on the objective, five that plainly do not, plus a
`profile.md` whose pointer list mentions all six. `BINDLE_NOTES_DIR` is
supplied **explicitly to every arm, including RED** — that is the sub-claim 1c
methodology fix and the reason no rep can touch the operator's real notes home.

- [ ] **Step 4: Run the reps**

- **C1** — objective bears on one shed fact: 5 RED + 5 GREEN. PASS = the
  transcript reads that fact's *body* and cites it in the summary.
- **C2** — objective unrelated to every fact: 5 GREEN. PASS = **zero** bodies
  read (the cap is not a quota).
- **C3** — no objective, no handoff next-step: 5 GREEN. PASS = zero bodies read.

Grade on the transcript and the filesystem, not the self-report. Grep every rep
for answer-key reach (`PRESSURE-TESTS`, real-path `file_path` calls); any hit
voids that rep.

- [ ] **Step 5: Record the result honestly**

Write the counts, the void reps and why, and any predicted-RED-was-wrong
finding — the Claim 8 entry is the model for this. If C1's separation is not
total, the finding is the finding: record it and mark the new `/session-start`
step **draft**, per CLAUDE.md, rather than describing it as done.

- [ ] **Step 6: Commit**

```bash
git add skills/session-continuity/PRESSURE-TESTS.md
make check
git commit -m "docs(#422): record the C1-C4 pressure-test series for the facts loader"
```

---

### Task 4: close out the branch

- [ ] **Step 1: Re-run every gate on the final tree**

```bash
make check
bin/run-test-suites.sh
gitleaks git . --redact
bin/check-issue-labels.sh
```

Expected: all green, `check-issue-labels.sh` exit 0.

- [ ] **Step 2: Open the PR (do not merge, do not push without an ask)**

Body: what shipped, the gate output quoted, the C1–C4 verdict, and the three
open calls the spec left (body cap, whether `/session-end` consults the index,
whether the loader retires `profile.md`'s pointer lists) restated as still
open. The operator merges.

- [ ] **Step 3: Leave #422 accurate**

Comment on #422 with the Phase 2a outcome and what remains (Phase 2b: the
symlink vs. drift-check store decision). Label changes and any `gh` write need
an explicit ask first.

---

## Self-review

**Spec coverage.** Design §`bin/facts-index.sh` → Task 1 (output format, the
frontmatter-only read, `MEMORY.md` skip, exit-0 silence, malformed-fact
visibility — each has a named check). Design §`/session-start` → Task 2 (all
four sub-steps, including the ≤5 cap and the name-what-you-loaded rule).
Verification §C1–C4 + the fixture suite → Tasks 1 and 3. Success criteria → Task
1 step 5 (real notes home), Task 2, Task 3, and the "no restatement" constraint,
which holds because nothing in either task copies a fact into `profile.md`,
`MEMORY.md`, or the command.

**Placeholders.** None: every code step carries the actual file content, every
command its expected output. Task 3's rep *outcomes* are deliberately unwritten
— that is the measurement, not a placeholder.

**Type consistency.** `bin/facts-index.sh [--cwd DIR] [--home DIR]` and the
`<slug><TAB><type><TAB><description>` contract are identical in the script, the
suite, the command step, the skill paragraph, and the capabilities entry.

**Renumbering risk.** Task 2 renumbers `/session-start`'s steps 4 and 5 to 5
and 6. Its Step 1 includes the grep that proves nothing else references those
numbers.
