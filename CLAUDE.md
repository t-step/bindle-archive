<!--
Project memory for claude-kit ITSELF — auto-loaded only when working in this
repo. This file is NOT installed anywhere: the every-project personal
instructions live in `global/CLAUDE.md`, which `bin/install.sh` symlinks to
~/.claude/CLAUDE.md. Keep claude-kit development guidance here; keep
every-project preferences in `global/CLAUDE.md`. Nothing here leaks to other
projects.
-->

# Working on claude-kit

Read [`README.md`](README.md) (what this repo is; the install/symlink model) and
[`CONTRIBUTING.md`](CONTRIBUTING.md) (branch discipline + the test-driven loop
skills go through) before adding or changing items.

- **This repo uses branch-and-PR.** A `no-commit-to-branch` hook protects `main`
  — work on a `feature/<x>`/`fix/<x>` branch; `make check` must pass before every
  commit.
- **A skill isn't done until it's pressure-tested** per superpowers:writing-skills
  (RED → GREEN → REFACTOR). Mark unverified skills as drafts in the CHANGELOG;
  don't describe a draft as finished.
- **Editing `global/CLAUDE.md` changes behavior in every project.** Keep each rule
  there universally safe or gated on an observable repo signal — see that file's
  header.
