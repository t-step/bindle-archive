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

### Changed
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
