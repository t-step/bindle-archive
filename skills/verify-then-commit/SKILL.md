---
name: verify-then-commit
description: Use when about to commit or push after making or resuming changes — especially after a subagent or another session edited code, before claiming work is done, or when tempted to commit because edits "look right" without running the project's tests, typecheck, and lint.
---

# verify-then-commit

## Overview

Before any commit, run the project's **tests + typecheck + lint** and commit **only if all pass green**. Reviewing a diff and deciding it looks correct is not verification — running it is.

**Committing unverified work is the failure this skill prevents. "Looks right" is not "is right".**

## When to Use

- Resuming a task where a subagent, coder agent, or a previous session made edits — verify their work before trusting it.
- You finished an implementation and are about to `git commit` / `git push`.
- About to report a task as done, fixed, or passing.

When NOT to use:
- Pure docs/markdown-only change with no test/type surface (still run the linter if one covers it).
- The operator explicitly said to commit without running checks.

## The gate

Run, in order, whatever the project actually uses. Discover the commands from the repo (`Makefile`, `package.json` scripts, `pyproject.toml`, CI workflow) — do not assume.

| Check | Typical command (verify per-repo) |
|-------|-----------------------------------|
| Tests | `pytest` · `npm test` · `vitest run` |
| Types | `tsc --noEmit` · `mypy` · `pyright` · a `lint:type` script |
| Lint | `ruff check` · `eslint` · `npm run lint` |
| Format | `ruff format --check` · `prettier --check` · `gofmt -l` |

**A linter passing does not imply a formatter passing.** They are separate commands with separate verdicts — `ruff check` passes on code `ruff format --check` rejects, and the same split exists as eslint vs prettier and as `go vet` vs `gofmt -l`. Where a toolchain separates them, both run before the gate is green, even when a `make lint` target covers only one of them. If the repo's CI runs a check its Makefile doesn't, CI's list is the gate.

**All green → commit. Any red → fix, re-run the full gate, then commit. Never commit on red.**

If a check can't run (missing dep, no venv), that's a blocker to resolve or report — not a reason to skip and commit anyway.

## Never bypass the hooks

Do not use `--no-verify`, `--force`, or admin-merge to get a commit through. A failing pre-commit hook is the gate doing its job.

## Rationalizations — all mean STOP and run the gate

| Excuse | Reality |
|--------|---------|
| "The diff looks correct" | Reading ≠ running. Types and tests catch what reading misses. |
| "It was a tiny change" | Tiny changes break builds. The gate takes seconds. |
| "The subagent said it passed" | Verify it yourself on this checkout. Reports aren't evidence. |
| "I'll fix CI if it's red" | CI is not your test runner. Verify before pushing, not after. |
| "Tests are slow, I'll commit and run after" | A commit that doesn't pass shouldn't exist. Run first. |
| "Just this once with --no-verify" | The hook exists for exactly this moment. Never bypass. |

## Red Flags — STOP

- About to commit without having run tests this session
- Trusting a "passed" claim you didn't watch produce output
- Reaching for `--no-verify` / `--force`
- Saying "done" / "fixed" / "passing" without command output to back it

**All of these mean: run the full test + typecheck + lint gate, confirm green, then commit.**

**REQUIRED BACKGROUND:** superpowers:verification-before-completion — this skill is the concrete commit-time application of that principle.
