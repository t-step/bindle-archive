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
  with a contamination diff gate). `verify-then-commit` and
  `scoped-sequential-prs` are drafts pending pressure-testing (see
  `CONTRIBUTING.md`).
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
