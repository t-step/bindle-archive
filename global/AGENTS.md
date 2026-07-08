<!--
Global personal instructions for Codex-compatible AGENTS.md surfaces.
`bin/install.sh --provider codex --codex-home <dir>` symlinks this file to
`<dir>/AGENTS.md`. The target directory is explicit; Bindle does not claim an
undocumented Codex global install standard.

Keep every rule here either (a) universally safe, or (b) gated on an observable
repo signal. Bindle's own dev guidance lives in the repo-root AGENTS.md, which
is not installed.
-->

# Personal preferences

## Working style

- **Do exactly the requested phase, then stop and report.** Don't run ahead into
  the next step, execute a plan I only asked you to write, or start adjacent
  work. When a message says "...and stop there", that boundary is the
  deliverable.
- **Respect a repo's branch discipline.** If a repo signals a branch-and-PR flow
  — a `no-commit-to-branch` hook, a protected default branch, a fork with an
  `upstream` remote, or its own instructions/README saying so — never commit
  directly to `main`: branch (`feature/<x>`/`fix/<x>`) off it, one PR-able unit
  per branch, and land via PR. Do not bypass hooks.
- **Never push** to `origin`, `upstream`, or a deploy target unless I explicitly
  ask. I handle pushes and deploys myself.
- **One fix at a time.** Reproduce a bug before proposing a fix; don't stack
  speculative fixes.
- Prefer small, single-purpose, reviewable commits over one large blob.

## Tooling defaults

- **Verify before committing:** run the project's tests, typecheck, and lint
  where available. Commit only if green. Never use `--no-verify` or `--force`.
- Match the repo's existing stack; detect tooling before adding any.

## Provider notes

- Claude Code-only surfaces such as `skills/`, `agents/`, slash commands, and
  `CLAUDE.md` may be useful context, but they are not automatically Codex
  primitives.
- Prefer direct repo instructions in `AGENTS.md` for Codex behavior.

## Communication

- Be concise. Lead with the answer or the value, not a file-by-file narrative.
