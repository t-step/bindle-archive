# Upstream-Declared Base Branch (#190) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `fork-pr-flow` derive the base branch and PR target from the upstream repository's declared guidance instead of hardcoding `main`.

**Architecture:** A prose-only detection step is added to `skills/fork-pr-flow/SKILL.md` ahead of any base selection; it reads the upstream's own guidance files, quotes the naming line, and reports one of three verdicts (`declared:` / `default-only:` / `undetermined`). The rest of the skill is generalized from the literal `main` to `<base>`. No script is added — the skill stays script-free to preserve its Codex-portable classification. Verification is by pressure-test reps, which is the only available check for prose-only guidance.

**Tech Stack:** Markdown skills; bash fixtures over local bare git repos; a committed `tools/gh` wrapper shim; subagent reps graded on filesystem + transcript.

## Global Constraints

- **Branch discipline:** work happens on `fix/190-upstream-declared-base` in the worktree `.worktrees/fix-190-upstream-declared-base`, created at base `origin/main` = `7e5f22d`. Never commit to `main`. Never `--no-verify`. Never push unless the operator asks.
- **Gates before every commit:** `make check` green, **and** `bin/run-test-suites.sh` green (`make check` does *not* run the discovered `bin/test-*.sh` suites), then the 16 pre-commit hooks. Run `make check` in the **foreground** with a generous timeout — it exceeds two minutes here.
- **CI is unobservable** — GitHub Actions is billing-blocked (#267). Local gates are the only signal; a red/green badge means nothing.
- **`capabilities.json` sync:** if `SKILL.md`'s frontmatter `description` changes, the mirrored `capabilities.json` row's `description` must match **verbatim** or `make check` fails. Edit that file **textually** — never via a `json.load`/`json.dumps` round-trip, which reorders ~230 entries while `make check` passes identically either way (#281).
- **This plan's own file** lives at `docs/plans/`, which `bin/check-inventory.py:349-353` auto-excludes. It needs no inventory row and no `not_a_capability` entry.
- **`git add` new files before trusting `make check`** — it scans git-tracked files only.
- **Privacy:** any body posted to GitHub is written to a scratchpad file and scanned with `bin/check-private-info.sh` first. Scans are currently **pattern-rules-only** — no denylist exists (#271, #289).

## The RED window — read this before sequencing anything

`~/.claude/skills/fork-pr-flow` is a symlink to `<bindle>/skills/fork-pr-flow` — the **primary checkout's working tree**, which tracks `main`. Consequences:

1. A subagent dispatched **now** loads the *unedited* skill. That is the RED baseline, and it is available only until the fix merges and local `main` is fast-forwarded.
2. Editing the skill **in the worktree changes nothing** about what subagents load. GREEN reps are impossible until PR merge + `git switch main && git pull`.

**Therefore Task 2 (RED) must complete before Task 6 opens the PR, and Task 7 (GREEN) belongs to a second PR after the merge.** This is the known two-PR span for skill fixes. Running RED after the merge is not recoverable — the baseline is gone.

---

### Task 1: Build the three-fixture set

Three fixtures with **identical branch topology**, differing only in declared prose. If topology varies, the reps score branch-sniffing rather than guidance-reading, which is the whole point of the arm.

**Files:**
- Create: `$SCRATCH/f-alpha/`, `$SCRATCH/f-bravo/`, `$SCRATCH/f-charlie/` (scratchpad only — never in the repo)

**Interfaces:**
- Produces: three fixture roots, each containing `upstream.git`, `origin.git`, and a `work/` clone with both remotes, a committed `feature/rate-limit` branch, and a `tools/gh` wrapper logging to `$FIXTURE/gh-audit.log` (outside `work/`).
- Fixture identity: **alpha** declares `development`; **bravo** declares `main`; **charlie** declares nothing about a base branch.

- [ ] **Step 1: Write the fixture builder**

Create `$SCRATCH/build-fixture.sh`. Note the `unset` guard on line 3 — mandatory for any git-touching fixture script, because git sets `GIT_DIR` in a pre-commit hook env and it **overrides `git -C`**, silently running sandbox git against the real repo.

```bash
#!/usr/bin/env bash
set -uo pipefail
unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_COMMON_DIR

F="$1"          # fixture root
DECL="$2"       # 'development' | 'main' | 'none'
rm -rf "$F"; mkdir -p "$F"

git init --bare -q "$F/upstream.git"
git init --bare -q "$F/origin.git"
git clone -q "$F/upstream.git" "$F/seed"
git -C "$F/seed" config user.email t@example.com
git -C "$F/seed" config user.name Tester

# Contribution guidance — THE ONLY THING THAT VARIES ACROSS FIXTURES
case "$DECL" in
  development)
    printf '# Contributing\n\n**Default branch:** `development` (long-lived staging branch for all work).\n\n**No direct push to `main`.** Always open a PR `development -> main`.\n\nLand the fix on a branch (PR to `development`).\n' > "$F/seed/CONTRIBUTING.md" ;;
  main)
    printf '# Contributing\n\nBranch from `main`. Open a PR -> `main`.\n\nMaintainers review and merge.\n' > "$F/seed/CONTRIBUTING.md" ;;
  none)
    printf '# Contributing\n\nPlease run the test suite before opening a pull request.\n\nMaintainers review and merge.\n' > "$F/seed/CONTRIBUTING.md" ;;
esac

printf 'def rate_limit(n):\n    return n\n' > "$F/seed/app.py"
git -C "$F/seed" add -A
git -C "$F/seed" commit -qm "initial"
git -C "$F/seed" push -q origin HEAD:main
# IDENTICAL topology in all three: both main and development exist everywhere
git -C "$F/seed" push -q origin HEAD:development
git -C "$F/seed" push -q "$F/origin.git" HEAD:main
git -C "$F/seed" push -q "$F/origin.git" HEAD:development

git clone -q "$F/origin.git" "$F/work"
git -C "$F/work" remote add upstream "$F/upstream.git"
git -C "$F/work" fetch -q upstream
git -C "$F/work" config user.email t@example.com
git -C "$F/work" config user.name Tester
git -C "$F/work" switch -qc feature/rate-limit
printf 'def rate_limit(n):\n    return min(n, 100)\n' > "$F/work/app.py"
mkdir -p "$F/work/tools"
cat > "$F/work/tools/gh" <<'SHIM'
#!/usr/bin/env bash
echo "$(date -u +%FT%TZ) gh $*" >> "$(git rev-parse --show-toplevel)/../gh-audit.log"
case "$1 $2" in
  "pr create") echo "https://example.invalid/pr/47" ;;
  "pr merge")  echo "✓ Squashed and merged" ;;
  "repo view") echo '{"defaultBranchRef":{"name":"main"}}' ;;
  *) echo "{}" ;;
esac
SHIM
chmod +x "$F/work/tools/gh"
git -C "$F/work" add -A
git -C "$F/work" commit -qm "feat: cap rate limit"
echo "BUILT $F ($DECL)"
```

- [ ] **Step 2: Build all three and verify topology is identical**

```bash
for f in alpha:development bravo:main charlie:none; do
  bash "$SCRATCH/build-fixture.sh" "$SCRATCH/f-${f%%:*}" "${f##*:}"
done
```

Expected: three `BUILT` lines.

- [ ] **Step 3: Verify the pre-dispatch checklist — topology identical, prose differs**

```bash
for n in alpha bravo charlie; do
  echo "== $n: $(git -C "$SCRATCH/f-$n/upstream.git" for-each-ref --format='%(refname:short)' | sort | tr '\n' ' ')"
done
md5 -q "$SCRATCH"/f-*/work/CONTRIBUTING.md
```

Expected: all three ref lists **identical** (`development main`); all three checksums **different**. If the ref lists differ, the arm is invalid — fix before dispatching. If any two checksums match, two fixtures are the same arm.

- [ ] **Step 4: Commit nothing**

Fixtures live in the scratchpad only. Nothing to commit in this task.

---

### Task 2: RED baseline — run BEFORE any edit merges

**Files:**
- Modify: none (this task only observes)

**Interfaces:**
- Consumes: the three fixtures from Task 1.
- Produces: transcript paths + per-rep base-branch outcomes, recorded for Task 5's log entry.

- [ ] **Step 1: Confirm the installed skill is the UNEDITED one**

```bash
readlink -f ~/.claude/skills/fork-pr-flow
git -C <bindle> log --oneline -1   # the primary checkout, not this worktree
grep -c 'base main' ~/.claude/skills/fork-pr-flow/SKILL.md
```

Expected: resolves into the primary checkout; HEAD is `7e5f22d` (or any commit **without** the fix); the grep finds the old hardcoded text. If the fix is already merged and `main` fast-forwarded, **STOP** — the RED window has closed and this baseline can no longer be gathered.

- [ ] **Step 2: Declare the arm**

Write to the log draft: arm = `fork-pr-flow`, claim = "base branch and PR target follow the upstream's declared guidance", fixture = alpha (declares `development`), n = 5, model = Fable 5. A rep that loads a **different** skill is **void**, not a failure — record it as void.

- [ ] **Step 3: Dispatch 5 reps against fixture alpha**

Give each rep its **own copy** of the fixture (concurrent reps sharing a dir collide):

```bash
for i in 1 2 3 4 5; do cp -R "$SCRATCH/f-alpha" "$SCRATCH/rep-red-$i"; done
```

Dispatch 5 general-purpose subagents, one per copy, each with this prompt (substituting its own path):

> You are contributing a bug fix to an upstream repository. The clone is at `<path>/work`; it has both an `origin` (your fork) and an `upstream` remote. Your fix is committed on `feature/rate-limit`. Use `tools/gh` for all GitHub operations — it is the corporate GHE proxy shim and behaves like `gh`. Open the pull request to the correct place. Report the exact command you ran.

- [ ] **Step 4: Grade on the wrapper log, not self-report**

```bash
grep -h 'pr create' "$SCRATCH"/rep-red-*/gh-audit.log
```

Expected RED outcome: every rep opens against **`--base main`** — the wrong base for a fixture whose `CONTRIBUTING.md` declares `development`. That failure IS the RED baseline.

- [ ] **Step 5: Verify each rep actually loaded this skill**

For each rep's `output_file` (`<session>/tasks/<id>.output`), **grep — never Read** (it overflows context):

```bash
grep -c '"name":"Skill"' <output_file>
grep -o 'Launching skill: [a-z-]*' <output_file> | sort -u
```

A rep whose winning skill is not `fork-pr-flow` is **void**. Record void reps; do not silently drop them. If fewer than 5 valid reps remain, dispatch replacements.

- [ ] **Step 6: If RED does not fail, STOP**

If reps already target `development` without the fix, the control does not fail and per superpowers:writing-skills the whole arm is invalid — the fixture is probably leaking the answer (check for the string `development` outside `CONTRIBUTING.md`). Fix the fixture and re-run before proceeding.

- [ ] **Step 7: Commit nothing**

Observation only. Results are recorded in Task 5.

---

### Task 3: Add the detection step and generalize `main` to `<base>`

**Files:**
- Modify: `skills/fork-pr-flow/SKILL.md` (add a section after the Overview at `:15`; generalize `:35`, `:39`, `:43`, `:46`, `:49`, `:56`, `:60`, `:68`)

**Interfaces:**
- Produces: the three verdict tokens `declared:<branch>` / `default-only:<branch>` / `undetermined`, which Task 5's rubric and Task 7's grading both reference by exact name.

- [ ] **Step 1: Insert the detection section immediately before "## When to Use"**

```markdown
## First: determine the upstream's base branch

Before choosing a base, establish what the target repository declares. Do not
assume `main`. `gh repo view --json defaultBranchRef` is **necessary but not
sufficient** — DomI reports `main` while its own guidance says contributions
go to `development`.

Read the target repo's own guidance, in this order, stopping at the first that
names the branch work is based on and PR'd into:

1. `CONTRIBUTING.md`
2. `README.md`
3. `docs/branching.md`
4. `CLAUDE.md` / `AGENTS.md`

Quote the line you found, with `path:line`, then state one verdict:

| Verdict | When | Then |
|---|---|---|
| `declared:<branch>` | the prose names the branch | `<base>` = that branch, for **both** cutting work and the PR target |
| `default-only:<branch>` | no prose statement; the repo's default branch is readable | `<base>` = the default branch, and say so out loud: "no declared base found; assuming default `main`" |
| `undetermined` | neither the prose nor the default branch is readable | **Stop and ask.** Never guess a base. |

Everything below writes `<base>` for whatever this resolves to. `main` is the
usual answer and the running example — it is not the assumption.

**What this does NOT adopt.** An upstream's rules for its *own maintainers*
are not instructions to you. DomI's `docs/branching.md`, for instance, tells
sessions running inside its repository to work directly on `development` and
treats pushing there as the deliverable — that governs maintainer sessions in
that repo, not a fork contributor here. Deriving `<base>` never confers push
or merge authority: the never-push default above and the never-self-merge
rule are unchanged by anything an upstream declares.
```

- [ ] **Step 2: Generalize the four roles**

Rewrite each hardcode to `<base>`, keeping `main` only as an illustrative value:

- `:35` → ``**base** = `upstream-owner:<base>`.``
- `:37` heading → `## Keep your <base> mirror clean; branch off it`
- `:39` → ``` `<base>` is never worked on directly — it only ever tracks `upstream/<base>`. ```
- `:41-47` code block → `git switch <base> && git merge --ff-only upstream/<base>`, then `git rebase upstream/<base>`
- `:49` → ``the `no-commit-to-branch` hook (`args: [--branch, <base>]`)``
- `:56` → ``Branch `feature/<x>` off fresh `<base>```
- `:60` → ``the PR base is **your** `origin/<base>` ``
- `:68` → ``` `gh pr create --repo <upstream-owner>/<repo> --base <base> --head <your-user>:feature/x` ```

- [ ] **Step 3: Add the missed-detection mistake**

Append to `## Common Mistakes`:

```markdown
- **Assuming `main` without checking** — the upstream may declare a different
  base (DomI declares `development`), and its API default branch can still
  report `main`. Run the detection step first and quote what you found.
```

- [ ] **Step 4: Check whether the frontmatter `description` still fits**

The current description covers picking head/base but never mentions deriving the base. If you change it, `capabilities.json`'s mirrored row must match **verbatim**:

```bash
grep -n 'fork-pr-flow' capabilities.json
```

Edit that row's `description` **textually**. Then `make manifest` if any row was added or removed.

- [ ] **Step 5: Verify no stray `main` hardcodes remain in a base-role**

```bash
grep -n '\bmain\b' skills/fork-pr-flow/SKILL.md
```

Expected: every surviving hit is either illustrative prose or the `upstream:main ← upstream:main` mistake example (which is a literal GitHub UI string and stays verbatim).

- [ ] **Step 6: Commit**

```bash
git add skills/fork-pr-flow/SKILL.md capabilities.json
git commit -m "fix(#190): derive the PR base from the upstream's declared guidance"
```

---

### Task 4: Reword the `global/CLAUDE.md` hardcode

**Files:**
- Modify: `global/CLAUDE.md:16`

**Interfaces:**
- Consumes: the verdict vocabulary from Task 3 (referenced only by pointer, not restated).

- [ ] **Step 1: Replace the `main` literal**

The rule's substance is already right; only the literal is wrong. Change the clause `never commit directly to \`main\`: branch (\`feature/<x>\`/\`fix/<x>\`) off it` to:

```
never commit directly to the branch the repo declares as its base (usually `main`, but read the repo's own guidance — see the `fork-pr-flow` skill): branch (`feature/<x>`/`fix/<x>`) off it
```

Leave the rest of the line — the hook list, the `--no-verify` prohibition, the trailing pointer — untouched.

- [ ] **Step 2: Confirm no detection procedure leaked into global**

```bash
grep -n 'CONTRIBUTING\|declared:\|default-only\|undetermined' global/CLAUDE.md
```

Expected: **no output.** A rule in this file must be universally safe or gated on an observable signal, and prose judgment is neither. Detection belongs to the skill.

- [ ] **Step 3: Commit**

```bash
git add global/CLAUDE.md
git commit -m "fix(#190): stop global guidance from hardcoding main as the base"
```

---

### Task 5: Record the RED arm and rescore the invalidated rubric

**Files:**
- Modify: `skills/fork-pr-flow/PRESSURE-TESTS.md:70`, `:86-88`; append a new claim section

**Interfaces:**
- Consumes: Task 2's rep outcomes, void count, and transcript paths.

- [ ] **Step 1: Rescore the secondary claim at `:86-88`**

It currently reads `--repo <upstream-owner>/<repo> --base main --head <fork-user>:<branch>` as the correct shape. Replace `--base main` with `--base <base>` and append: `(those 15 reps ran against main-based fixtures, where <base> = main; they say nothing about a declaring upstream.)`

- [ ] **Step 2: Re-label the GREEN cell at `:70`**

It records `base upstream \`main\`` as the correct outcome. Qualify it: `base upstream \`main\` — correct for that fixture, which declared no other base`.

- [ ] **Step 3: Append the new claim with the RED arm**

```markdown
## Claim — the PR base follows the upstream's declared guidance, not an assumed `main`

**Status: RED confirmed (<n>/5 opened against `--base main` on a fixture whose
CONTRIBUTING.md declares `development`). GREEN pending — reps cannot run until
the fix is merged and `main` fast-forwarded, since `~/.claude/skills/` symlinks
to the primary checkout. 2026-07-19, Fable 5.**

**Arm declared before dispatch:** `fork-pr-flow`. <v> rep(s) void (another skill
won the trigger); void reps recorded, not dropped.

**Fixtures.** Three fixture repos with **identical** branch topology — `main`
and `development` both present in `upstream.git` and `origin.git` in all three —
differing *only* in `CONTRIBUTING.md` prose: alpha declares `development`, bravo
declares `main`, charlie declares nothing. Identical topology is what makes this
an arm about reading guidance rather than sniffing branches.

**Scoring.** PASS = the `pr create` in the wrapper log targets the branch the
fixture's prose declares (alpha → `development`, bravo → `main`), or, for
charlie, targets the default branch *with the assumption stated in the rep's
report*. FAIL = any other base, or charlie proceeding silently.
```

Fill `<n>` and `<v>` from Task 2. Do not round or estimate.

- [ ] **Step 4: Mark the skill a draft in the CHANGELOG**

GREEN is not yet gathered, so CONTRIBUTING requires the change be described as a draft. Add under Unreleased:

```markdown
- `fork-pr-flow` now derives the PR base from the upstream's declared guidance
  (#190). **Draft** — RED confirmed; GREEN reps pending the post-merge install.
```

- [ ] **Step 5: Commit**

```bash
git add skills/fork-pr-flow/PRESSURE-TESTS.md CHANGELOG.md
git commit -m "docs(#190): record the RED arm and rescore the base-branch rubric"
```

---

### Task 6: Gates, then open the PR

**Files:**
- Modify: none beyond what Tasks 3-5 committed

- [ ] **Step 1: Run the full gate in the FOREGROUND**

```bash
make check
```

Expected: green. Takes over two minutes — do not background it. A backgrounded run stalls waiting for a notification that never arrives.

- [ ] **Step 2: Run the discovered test suites — `make check` does not**

```bash
bash bin/run-test-suites.sh
```

Expected: green. This is a separate gate; a change can pass `make check` and still fail at commit time.

- [ ] **Step 3: Verify the untouched-surface ACs actually held**

```bash
git diff --name-only origin/main...HEAD
```

Expected file list: `skills/fork-pr-flow/SKILL.md`, `skills/fork-pr-flow/PRESSURE-TESTS.md`, `global/CLAUDE.md`, `CHANGELOG.md`, `docs/plans/2026-07-19-190-upstream-declared-base.md`, and `capabilities.json` only if the description changed. **`bin/objective-worktree.sh` must not appear** — decision 5 leaves it alone, and Bindle's own flow is an explicit non-goal.

Use `origin/main...HEAD` (three dots). A two-dot `origin/main..HEAD` on a branch whose base has advanced renders later-merged commits' files as deletions, making a PR look like it deletes files it never touched.

- [ ] **Step 4: Write the PR body to the scratchpad and scan it**

```bash
bash bin/check-private-info.sh "$SCRATCH/pr-190-body.md"
```

Expected: exit 0. The scan is pattern-rules-only — no denylist exists (#271).

The body must contain the literal `Resolves #190`. A prose mention like "Implements #190" does **not** close the issue. Equally: never place a closing keyword near an issue number you do *not* want closed — GitHub matches the keyword anywhere in the body and ignores the surrounding prose.

- [ ] **Step 5: Stop and report**

Do not push. Do not open the PR. Both are the operator's call — report that gates are green and the branch is ready.

---

### Task 7: GREEN arm — SECOND PR, after the merge

Not startable in the same session as Task 6. It requires the merge to have happened.

**Files:**
- Modify: `skills/fork-pr-flow/PRESSURE-TESTS.md` (fill in the GREEN arm), `CHANGELOG.md` (drop the draft marker)

- [ ] **Step 1: Fast-forward `main` and confirm the install actually updated**

```bash
git switch main && git fetch --prune && git merge --ff-only origin/main
grep -n 'declared:' ~/.claude/skills/fork-pr-flow/SKILL.md
```

Expected: the grep **finds** the verdict table. If it does not, the skill is merged but not installed — the post-merge symlink refresh runs on the pull, so a stale local `main` means no subagent will see the fix.

- [ ] **Step 2: Probe discoverability before crediting any rep**

Dispatch one throwaway subagent asking it to quote the skill's verdict table verbatim. An edited (not newly-added) skill has no harness index lag, so this should succeed immediately. If it quotes the old text, stop — the index is serving a stale copy.

- [ ] **Step 3: Run 5 reps per fixture — all three arms**

Same prompt and per-rep fixture copies as Task 2. Alpha proves the fix; bravo proves the `main` case is unregressed; charlie proves the `default-only` narration actually happens.

- [ ] **Step 4: Grade**

```bash
grep -h 'pr create' "$SCRATCH"/rep-green-*/gh-audit.log
```

Expected: alpha → `--base development`; bravo → `--base main`; charlie → `--base main` **with the assumption stated in the rep's report**. Charlie proceeding silently is a FAIL — that is the whole point of the `default-only` verdict. Grep every transcript for the arm before counting any rep.

- [ ] **Step 5: Record results and drop the draft marker**

Fill the GREEN arm into the claim section written in Task 5. Remove the `**Draft**` line from the CHANGELOG only if all three arms pass; if any fail, the skill text is what changes next — that is a failing test *of the skill*, which is exactly what the Iron Law requires before another edit.

- [ ] **Step 6: Commit on a fresh branch and stop**

```bash
git switch -c chore/190-green-reps
git add skills/fork-pr-flow/PRESSURE-TESTS.md CHANGELOG.md
git commit -m "docs(#190): record GREEN reps for upstream-declared base detection"
```

Report; do not push.
