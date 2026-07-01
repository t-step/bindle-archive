<!--
Global personal instructions. `bin/install.sh` symlinks this file (global/CLAUDE.md)
to ~/.claude/CLAUDE.md, so EVERY rule here fires in EVERY project. A project's own
CLAUDE.md and explicit user instructions take precedence. To avoid leaking into
projects where a rule shouldn't apply: keep each rule either (a) universally safe,
or (b) gated on an observable repo signal (e.g. "if the repo has X"). Anything that
should apply to only some projects belongs in that project's CLAUDE.md, not here.
(claude-kit's own dev guidance lives in the repo-root CLAUDE.md, which is not installed.)
-->

# Personal preferences

## Working style

- **Do exactly the requested phase, then stop and report.** Don't run ahead into the next step, execute a plan I only asked you to write, or start adjacent work. When a message says "…and stop there", that boundary is the deliverable.
- **Respect a repo's branch discipline.** If a repo signals a branch-and-PR flow — a `no-commit-to-branch` hook, a protected default branch, a fork (an `upstream` remote), or its own CLAUDE.md/README saying so — never commit directly to `main`: branch (`feature/<x>`/`fix/<x>`) off it, one PR-able unit per branch, and land via PR; don't `--no-verify` past the hook. Absent any such signal, follow the repo's existing convention. See the `fork-pr-flow` skill.
- **Never push** to `origin`, `upstream`, or a deploy target (PyPI, HuggingFace, Vercel, etc.) unless I explicitly ask — I handle pushes and deploys myself. See the `fork-pr-flow` skill for the branch/PR mechanics.
- **One fix at a time.** Reproduce a bug before proposing a fix; don't stack speculative fixes. See superpowers:systematic-debugging.
- Prefer small, single-purpose, reviewable commits over one large blob.

## Tooling defaults

- **Verify before committing:** run the project's tests + typecheck + lint and commit only if green. Never `--no-verify` or `--force`. See the `verify-then-commit` skill.
- Match the repo's existing stack; detect tooling before adding any.

## Communication

- Be concise. Lead with the answer or the value, not a file-by-file narrative.
