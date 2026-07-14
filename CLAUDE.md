<!--
Project memory for Bindle ITSELF — auto-loaded only when working in this
repo. This file is NOT installed anywhere: the every-project personal
instructions live in `global/CLAUDE.md`, which `bin/install.sh` symlinks to
~/.claude/CLAUDE.md. Keep Bindle development guidance here; keep
every-project preferences in `global/CLAUDE.md`. Nothing here leaks to other
projects.
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
  triggers, or install layout to make them provider-neutral.
- **Editing `global/CLAUDE.md` changes behavior in every project.** Keep each rule
  there universally safe or gated on an observable repo signal — see that file's
  header.
- **Default to caveman mode (`full` intensity) in this repo.** Invoke the
  `caveman` skill at session start and stay in it for the whole session —
  don't wait for the user to ask. Drop it only for the skill's own
  auto-clarity carve-outs (security warnings, irreversible-action
  confirmations, misreadable multi-step sequences, or when the user asks to
  clarify). *Why here and not `global/CLAUDE.md`:* this repo's sessions are
  issue triage / retros / transcript review — high token volume, low risk of
  losing nuance — so the win is worth it here without forcing the tradeoff on
  every other project.
