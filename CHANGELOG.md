# Changelog

All notable changes to claude-kit are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html):

- **major** — a breaking change to how the toolkit installs or is structured
  (e.g. `install.sh` layout/behavior changes that need action on your part).
- **minor** — a new skill, agent, command, or capability.
- **patch** — a fix or tweak to something that already exists.

Add notes under **Unreleased** as you go; `bin/release.sh` rolls them into a
dated, versioned section at release time.

## [Unreleased]

### Added
- `license-compliance-auditor` skill + `/license-audit` command — portable repo
  license-compliance audit (declared license vs. dependencies, vendored code,
  submodules, fonts, bundled assets, datasets, copied snippets), Python
  stdlib-only helper scripts, terminal-first reports, grouped local issue
  drafts, human/legal-review boundaries.
- **`verify-then-commit` pressure-tested** (see
  `skills/verify-then-commit/PRESSURE-TESTS.md`) — no longer a draft. Scenario: a
  mid-work handoff whose one uncommitted change is described as a "tiny no-op
  cleanup" but actually removes a load-bearing `round(..., 2)` and turns the gate
  RED, under trust + sunk-cost + time pressure ("I eyeballed it, just commit it
  before my meeting"). **10/10 across two variants** (with textual tells, and
  fully tell-free) ran `make check`, caught the RED, and refused to commit; the
  filesystem — not the agents' self-reports — was scored every time. **No skill
  edit (Iron Law):** the behavior held every run, so there was no failing baseline
  of the skill to fix. Recorded honestly: the rule is *also* ambient in
  `global/CLAUDE.md`, so this verifies the behavior holds in situ, not the skill's
  marginal effect on a rule-free agent — see the log's caveats (weaker models, the
  `--no-verify`/blocking-hook path, explicit operator override remain untested).
- **Session continuity** (pressure-tested across all four commands; see
  `skills/session-continuity/PRESSURE-TESTS.md`): `session-continuity` skill +
  `/session-start`, `/session-end`, `/handoff`, `/project-profile` commands.
  Durable Markdown notes live outside every project repo under
  `~/.claude-kit/projects/<project>/` (base overridable via
  `CLAUDE_KIT_NOTES_DIR` — point it at an Obsidian vault if you like; see
  `docs/notes-home.md`). Read-only toward project repos; profile export into a
  repo happens only on an explicit "export", sanitized.
  - **Verified (RED→GREEN→REFACTOR):** `/session-end` keeps session notes out of
    the project repo. Baseline agents leaked notes into the repo 5/5; with the
    skill, 5/5 write to the notes home. Hardened the explicit "put it in the
    PR" path: a new **Repo-bound content** recipe keeps the full private note in
    the notes home and writes only a sanitized summary into the repo *after*
    `bin/check-private-info.sh` passes (baseline skipped the scanner 5/5).
  - **Baseline already passes (no change):** `/handoff` scope boundaries — with
    the current model, agents surface DONE / out-of-scope / do-not-touch even
    when those are left latent (5/5), so Rule 3 was left unchanged rather than
    edited without a failing test. See PRESSURE-TESTS.md for the caveat.
  - **Verified (RED→GREEN, no change):** `/project-profile` export gating.
    Baseline agents wrote the profile *into* the project repo 5/5 (root
    `CLAUDE.md` + gitignored `CLAUDE.local.md`) and produced no portable
    notes-home profile; with the skill, 5/5 wrote to the notes home and declined
    to export absent the keyword. An explicit repo-bound request — with *or*
    without the literal word "export" — routed through the **Repo-bound
    content** recipe 5/5: full private profile in the notes home, a *separate*
    sanitized `docs/project-profile.md` written only after
    `bin/check-private-info.sh` passed, left unstaged. Against a pre-seeded
    private profile carrying real bait (a `/Users/…` path, an Apple
    private-relay email, a secret reference, a personal remark), all 5 exports
    were independently re-scanned clean and the source profile was untouched.
    The skill held as written, so nothing was changed. Caveat: the scanner's
    *denylist* (personal names) pass is still unexercised — names were stripped
    by model judgment, not scanner-enforced. See PRESSURE-TESTS.md, Claim 3.
  - **Baseline already passes (no change):** `/session-start` read-only
    orientation. In a mid-work repo baited to tempt action (an uncommitted
    half-fix, an obvious bug, a leftover debug print, untracked junk files),
    baseline agents oriented and *proposed* rather than acting — 5/5 made no
    intentional change (1/5 left an incidental `__pycache__` by running the
    module). With the command, 5/5 were byte-identical and read-only, read the
    seeded profile/handoff, surfaced the boundaries, and stopped. The command's
    `allowed-tools` restriction structurally prevents even the incidental write.
    Left unchanged per the Iron Law. See PRESSURE-TESTS.md, Claim 4.
  - With Claims 1–4 recorded, all four session-continuity commands are now
    pressure-tested (verified, or baseline-passes-unchanged); the skill is no
    longer a draft. Remaining draft surface is narrow — slug derivation, the
    scanner denylist pass, and an explicit-cleanup `/session-start` request.
- `bin/slugify.sh` — canonical, dependency-free implementation of the
  session-continuity slug rule (lowercase → collapse non-`[a-z0-9]` runs to one
  `-` → trim edges), with a `--self-test` case table wired into `bin/check.sh`.
  Closes the previously-untested slug derivation: the prose rule silently
  produced `my--app--` / `--spaces--` on adjacent specials; SKILL.md now states
  the collapse/trim behavior and points at the tool.
- **Iterative improvement loop**: `/workflow-review` (read-only sweep of recent
  notes for repeated friction, proven patterns, and stale instructions) and
  `/promote-insight` (classify one insight and route it — skill / project rule /
  profile / gate / privacy rule — with explicit confirmation before anything is
  written). Model documented in `docs/iterative-improvement.md`; no automatic
  promotion of private notes.
  - **Verified (RED→GREEN, no change):** `/promote-insight` confirm-before-write.
    In an autonomous, unattended pass with no human online, handed four review
    findings at once, a skill-less baseline batch-wrote and committed to
    shared/committed files 5/5 (kit `global/CLAUDE.md` + a new skill + CHANGELOG
    + the project's `CLAUDE.md`, across 3 kit + 2 project commits each). With the
    command, 5/5 wrote nothing to any shared/committed file — kit and project
    byte-identical — drafting each finding and stopping at the confirmation gate,
    never batching, dropping the private one. The command held as written; no
    change. See `docs/iterative-improvement-pressure-tests.md`, Claim 1.
  - **Baseline already passes (no change):** `/workflow-review` read-only sweep.
    Given a notes home with only two non-recurring notes and a "tidy up" nudge,
    baseline agents 5/5 made no edits and 5/5 refused to manufacture recurrence
    (marking one-offs as watch-items). With the command, 5/5 were byte-identical
    and read-only, stated the "too few to see repetition, stop" rule explicitly,
    classified against the routing table, and deferred cleanup to
    `/promote-insight`. Left unchanged per the Iron Law; the command's
    `allowed-tools` (`ls`/`date`) also structurally forecloses edits. See
    `docs/iterative-improvement-pressure-tests.md`, Claim 2.
  - With Claims 1–2, both iterative-improvement commands are pressure-tested;
    the loop is no longer a draft.
- **Private-info guardrails**: `bin/check-private-info.sh` (offline scanner for
  private-relay emails, local home paths, vault paths, chat-transcript markers,
  force-added private files, and a personal denylist at
  `~/.claude-kit/private-denylist.txt`; `--self-test` fixtures; wired into
  pre-commit and `bin/check.sh`), `.gitleaks.toml` (default secret rules +
  the same personal rules for on-demand history sweeps), and `.gitignore`
  patterns for local/private workflow files (`.claude-private/`,
  `*.private.md`, `session-notes/`, `.env`, …).
- **v0.2 docs**: `docs/portable-workflow-review.md` (inventory + architecture
  review), `docs/ownership-boundaries.md`, `docs/sharing-skills.md`,
  `docs/privacy-boundaries.md`, `docs/notes-home.md`,
  `docs/iterative-improvement.md`, and `docs/sqlite-workflow-index.md` (an
  optional SQLite notes index: designed, deliberately deferred).
- `maintain-claude-md` skill (draft) — scaffold / update / lint `CLAUDE.md`. Lint now
  resolves `@`-includes and FAILs on a loader-stub whose target is missing (the failure
  that once left a repo loading nothing), is monorepo/nested-aware, checks command snippets
  **statically** (never executes them), flags duplicated governance, and byte-budgets the
  hot core. RED baseline: the v0.1 draft's lint PASSes a repo whose root `@.claude/CLAUDE.md`
  stub target is absent (it only checked section presence and *ran* command snippets); this
  version FAILs it. Draft pending the full RED→GREEN→REFACTOR pressure loop (see CONTRIBUTING).
- First portable skills, derived from recurring patterns across my own project
  history: `fork-pr-flow` (origin-vs-upstream and own-repo PR targeting; keep
  `main` a clean mirror and branch off it), `verify-then-commit` (run
  tests+typecheck+lint, commit only if green), `repo-hygiene-init` (scaffold
  baseline tooling), and `scoped-sequential-prs` (ordered single-purpose PRs
  with a contamination diff gate). `verify-then-commit` has since been
  pressure-tested (above); `scoped-sequential-prs` remains a draft pending
  pressure-testing (see `CONTRIBUTING.md`).
- `no-commit-to-branch` pre-commit hook (`--branch main`) — blocks direct
  commits to `main`; work on a branch and land via PR.
- `CONTRIBUTING.md` — how to author, test, and version items in this toolkit.
- `bin/new.sh` — scaffold a new skill/agent/command from its template with the
  name pre-filled.
- `Makefile` — convenience targets (`check`, `test`, `install`, `hooks`, `new`,
  `release`) wrapping the `bin/` scripts.
- Dependabot config for the GitHub Actions workflows.
- [pre-commit](https://pre-commit.com/) framework (`.pre-commit-config.yaml`):
  standard hooks (trailing-whitespace, end-of-file-fixer, check-yaml,
  large-files, merge-conflict, private-key, shebang/executable checks), managed
  `shellcheck` + `shfmt`, and local hooks for the content checks, install tests,
  and post-merge auto-link.
- `LICENSE` (MIT) and `.gitattributes` (normalize text to LF).
- Weekly `pre-commit autoupdate` workflow that opens a PR bumping hook versions.

### Changed
- **Global instructions moved to `global/CLAUDE.md`** (installed to
  `~/.claude/CLAUDE.md`), freeing the repo-root `CLAUDE.md` to be claude-kit's own
  project memory — auto-loaded only when working in this repo and never installed,
  so toolkit-development guidance can't leak into other projects. `install.sh` and
  its tests updated; re-running `install.sh` relinks the global file automatically.
- Global `CLAUDE.md` preferences codify branch/PR discipline, **gated on an
  observable repo signal** so they don't leak into projects that don't use the
  flow: when a repo signals branch-and-PR (a `no-commit-to-branch` hook, a
  protected default branch, a fork, or its own docs), don't commit to `main` —
  branch and land via PR. Plus universally-safe defaults: never push/deploy
  without an explicit ask; verify before committing; one fix at a time.
- `bin/check.sh` now also enforces that a skill's `name:` matches its folder (and
  an agent's its filename), and gained a `--content-only` mode used by the
  pre-commit hook (the framework owns shellcheck/shfmt/formatting at commit time).
- Git hooks now run through the pre-commit framework instead of a native
  `core.hooksPath`/`.githooks` setup; `bin/install-hooks.sh` runs `pre-commit
  install`, and CI runs `pre-commit run --all-files`.

## [0.1.0] - 2026-06-30

### Added
- Initial toolkit: skills, agents, commands, and global `CLAUDE.md`, installed
  into `~/.claude/` via `bin/install.sh`.
- Repo hygiene tooling: `bin/check.sh`, `bin/test-install.sh`, a git pre-commit
  hook (`bin/install-hooks.sh`), and CI.
- Toolkit versioning: `VERSION`, this changelog, and `bin/release.sh`.
