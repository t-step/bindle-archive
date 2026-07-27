# Contributing to Bindle

This is my personal toolkit, but it follows a discipline so that a fresh session
(or future me) can pick it up cold. If you're an agent working *on this repo*,
read this file and the [README](README.md) before adding or changing anything.

## The shape of the repo

See the [README](README.md) for what Bindle is and how `bin/install.sh`
installs provider-specific surfaces. Claude Code remains the mature path: each
`skills/<name>/SKILL.md`, `agents/<name>.md`, and `commands/<name>.md` becomes a
Claude user-level capability under `~/.claude/`. Codex support is narrower and
fully explicit: `global/AGENTS.md` installs to a `--codex-home` target, and
skills marked `provider.codex: "installed"` in `capabilities.json` install to
an `--agents-skills-home` target.

## Branch & commit discipline

- **Never commit to `main`.** `main` mirrors the published/upstream state; a
  `no-commit-to-branch` pre-commit hook enforces this. Work on a `feature/<x>` or
  `fix/<x>` branch cut fresh off `main`, one PR-able unit per branch.
- If the hook blocks a commit, that's the control working — branch, don't
  `--no-verify` past it.
- **Verify before committing:** `make check` must pass. Never bypass hooks. It
  is not the whole gate — see "The gate of record is local" below.
- Small, single-purpose commits over one large blob.

### The gate of record is local — CI is not a signal

**A red check on a PR here tells you nothing about the change.** GitHub Actions
runs do not start on this repo: every run since at least 2026-07-15 has failed
within seconds with an account-level billing annotation, and the operator has
decided not to resolve that condition. Treat it as the standing state, not an
outage to wait out (#267).

Nor could a check be *required*. This repo is private, and
`GET /repos/:owner/:repo/branches/main/protection` answers 403 "Upgrade to
GitHub Pro or make this repository public to enable this feature" — there is no
branch protection here to enforce anything. `main` is protected by the
`no-commit-to-branch` pre-commit hook, which is a local guard in your checkout,
not a server-side rule.

So the gate is, in full:

1. the pre-commit hooks at commit time (they run the discovered suites);
2. `make check`;
3. `make test` (`bin/run-test-suites.sh`) — `make check` does **not** run the
   suites, so a change can be green under `make check` and still fail at commit;
4. the all-files sweep, when you want what CI would have covered:
   `SKIP=no-commit-to-branch pre-commit run --all-files --show-diff-on-failure`.

Nothing schedules any of these. The one thing Actions gave that a local run
cannot is a clean checkout with freshly-resolved tool versions, so tool drift
(Python, shellcheck, shfmt, pre-commit) surfaces only when someone goes looking.

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
