<!--
Project memory for Bindle ITSELF — auto-loaded only when working in this
repo. This file is NOT installed anywhere: the every-project personal
instructions live in `global/AGENTS.md`, which `bin/install.sh --provider codex
--codex-home <dir> --agents-skills-home <dir2>` symlinks to `<dir>/AGENTS.md`
(that same command installs Codex-eligible skills into `<dir2>/`). Keep Bindle
development
guidance here; keep every-project preferences in `global/AGENTS.md`. Nothing
here leaks to other projects.
-->

# Working on Bindle

Read [`README.md`](README.md) (what this repo is; the install/symlink model) and
[`CONTRIBUTING.md`](CONTRIBUTING.md) (branch discipline + the test-driven loop
skills go through) before adding or changing items.

- **This repo uses branch-and-PR.** A `no-commit-to-branch` hook protects `main`
  — work on a `feature/<x>`/`fix/<x>` branch; `make check` must pass before every
  commit.
- **A skill isn't done until it's pressure-tested** per superpowers:writing-skills
  (RED → GREEN → REFACTOR). Mark unverified skills as drafts in the CHANGELOG;
  don't describe a draft as finished.
- **Claude assets remain Claude-native in Phase 1.** Do not rewrite
  `skills/*/SKILL.md`, `agents/*.md`, `commands/*.md`, their frontmatter,
  triggers, or install layout to make them provider-neutral. Treat
  `bin/check.sh` frontmatter checks as Claude-provider regression tests.
- **Editing `global/AGENTS.md` changes behavior wherever you explicitly install
  it.** Keep each rule universally safe or gated on an observable repo signal —
  see that file's header.
