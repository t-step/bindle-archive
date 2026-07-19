# Contributing to Bindle

This is my personal toolkit, but it follows a discipline so that a fresh session
(or future me) can pick it up cold. If you're an agent working *on this repo*,
read this file and the [README](README.md) before adding or changing anything.

## The shape of the repo

See the [README](README.md) for what Bindle is and how `bin/install.sh`
installs provider-specific surfaces. Claude Code remains the mature path: each
`skills/<name>/SKILL.md`, `agents/<name>.md`, and `commands/<name>.md` becomes a
Claude user-level capability under `~/.claude/`. Codex Phase 1 support is direct
`AGENTS.md` guidance installed only to an explicit `--codex-home` target.

## Branch & commit discipline

- **Never commit to `main`.** `main` mirrors the published/upstream state; a
  `no-commit-to-branch` pre-commit hook enforces this. Work on a `feature/<x>` or
  `fix/<x>` branch cut fresh off `main`, one PR-able unit per branch.
- If the hook blocks a commit, that's the control working — branch, don't
  `--no-verify` past it.
- **Verify before committing:** `make check` must pass. Never bypass hooks.
- Small, single-purpose commits over one large blob.

### Test suites are discovered, not registered

Any tracked `bin/test-<name>.sh` is a suite. `make test` and the commit gate
both run every one of them via `bin/run-test-suites.sh` — there is no list to
add yourself to, in the `Makefile` or in `.pre-commit-config.yaml`.

Name a new suite to the convention and it is covered from the moment it is
tracked. This is deliberate: hand-registration is how eleven suites ended up
running under `make test` while never reaching the commit gate (#256, #257).
Python hooks under `global/hooks/` are covered the same way, through the
shell suites that exercise them (`bin/test-nested-notes-guard.sh`,
`bin/test-session-hooks.sh`).

## Delegating implementation work

Handing an approved issue to a subagent (or a future session) uses the
[delegated implementation packet contract](docs/delegated-implementation-packets.md):
a bounded objective, explicit "do not change" scope, exact verification, and a
per-action mutation allow-list, so authority is granted rather than inferred.
Copy its template into the issue or handoff instead of re-typing guardrails.

## Authoring a skill (this is TDD, not just writing docs)

A skill is not "done" when the prose reads well — it's done when a fresh agent
*behaves differently because of it*. Follow `superpowers:writing-skills`, which
applies RED → GREEN → REFACTOR to documentation:

1. **RED** — Before writing, run the pressure scenario on a subagent *without*
   the skill and record what it actually does (the baseline failure). If the
   baseline doesn't fail, there's nothing to fix — don't write the skill.
2. **GREEN** — Write the minimal skill that addresses those specific failures.
   Discipline skills (rules/gates) get a rationalization table + red-flags list;
   technique skills get one excellent example.
3. **REFACTOR** — Re-run with the skill, close any new loopholes, repeat until it
   holds under pressure.

Mechanics:

- Scaffold with `bin/new.sh skill <name>` (kebab-case; `name:` must match the
  folder — `bin/check.sh` enforces it).
- `description:` starts with "Use when…", third person, describes **when** to use
  it, not what it does (a workflow summary in the description makes agents skip
  the body).
- Build on existing skills by *referencing* them
  (`**REQUIRED BACKGROUND:** superpowers:test-driven-development`) — don't vendor
  copies. See the README's "Building on other sources".
- Running pressure-test reps follows
  [the pressure-testing protocol](docs/pressure-testing-protocol.md): declare
  the intended arm before dispatch and discard reps a competing skill won as
  **void**, run the pre-dispatch fixture checklist, and grade the transcript
  rather than the agent's self-report.
- Before running pressure-test reps (RED or REFACTOR) in an interactive
  session, ask how: **sequential** (recommended — one subagent rep at a
  time, bounded/predictable resource use), **parallel** (faster wall-clock,
  runs reps concurrently), or **defer and file an issue** (don't run now —
  create a `type: chore`, `status: triage` GitHub issue per
  [docs/issue-tracking.md](docs/issue-tracking.md) describing the pressure
  test to run later). In an unattended/autonomous run, skip the ask and
  default to sequential.

Agents and commands: same branch discipline; `agents/_template.md` and
`commands/_template.md` document their Claude-native frontmatter.

## Draft vs. tested

A skill that hasn't been through the RED→GREEN→REFACTOR loop above is a **draft**
— structurally valid but unverified. Note a skill's status in its `CHANGELOG`
entry until it has been pressure-tested. Don't describe a draft skill as
finished.

## Versioning & release

Toolkit-level SemVer (see the README): a new skill/agent/command is a **minor**
bump. Release Please assembles the changelog and the version bump on the release
PR from your Conventional Commit messages; `bin/release.sh` remains a
legacy/fallback local cutter (and never pushes — you review first).

## Before you call it done

- [ ] On a branch, not `main`.
- [ ] `make check` passes.
- [ ] New skill went through (or is marked draft pending) the writing-skills loop.
- [ ] Commits carry Conventional Commit prefixes (`feat:`, `fix:`, `docs:`, …)
      so Release Please can generate the changelog entry — `CHANGELOG.md` has no
      hand-maintained Unreleased section to edit.
- [ ] New/renamed capability recorded in `capabilities.json` (see the
      [capability-inventory doc](docs/capability-inventory.md)); `make check`
      reconciles it.
