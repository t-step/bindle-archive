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

## Subagent orchestration

- Use subagents selectively for independent analysis, specialized review, or
  genuinely parallel workstreams.
- Default to no more than 2 concurrent subagents.
- Up to 4 concurrent subagents may be used when the workstreams are clearly
  independent and each has a distinct deliverable.
- Normally use no more than 6 subagents over the lifetime of one task.
- Do not allow subagents to spawn additional subagents.
- Give every subagent a bounded question, a concrete expected output, and a
  non-overlapping scope.
- Do not create subagents for simple file searches, command execution, or
  reasoning the primary agent can perform directly.
- Continue useful primary work while agents run. Collect results at natural
  synchronization points rather than repeatedly polling.
- If a subagent is slow or unavailable, proceed without it unless its result is
  required for safety or correctness.
- Before exceeding 2 concurrent subagents, state briefly why the workstreams are
  independent.
- Treat subagent findings as advisory. The primary agent remains responsible for
  verifying claims, resolving conflicts, and producing the final result.

## Provider notes

- If a repo has `AGENTS.md`, treat it as authoritative Codex-facing project
  guidance.
- If both `AGENTS.md` and `CLAUDE.md` exist, `AGENTS.md` is authoritative for
  Codex; `CLAUDE.md` may add useful context but must not override it.
- If a repo has no `AGENTS.md` but does have `CLAUDE.md`, read `CLAUDE.md` as
  fallback project context.
- In all cases, treat Claude-only references as non-portable unless the
  current environment explicitly supports them: hooks, skills, agents, and slash commands.
- When asked to write a session note or handoff and the Bindle repo is
  available, follow its portable conventions — `docs/session-notes-format.md`
  and `docs/using-bindle-with-codex.md` in that repo — instead of inventing a
  format or writing notes into the project repo.

## Communication

- Be concise. Lead with the answer or the value, not a file-by-file narrative.

<!-- CODEGRAPH_START -->
## CodeGraph

In repositories indexed by CodeGraph (a `.codegraph/` directory exists at the repo root), reach for it BEFORE grep/find or reading files when you need to understand or locate code:

- **MCP tool** (when available): `codegraph_explore` answers most code questions in one call — the relevant symbols' verbatim source plus the call paths between them, including dynamic-dispatch hops grep can't follow. Name a file or symbol in the query to read its current line-numbered source. If it's listed but deferred, load it by name via tool search.
- **Shell** (always works): `codegraph explore "<symbol names or question>"` prints the same output.

If there is no `.codegraph/` directory, skip CodeGraph entirely — indexing is the user's decision.
<!-- CODEGRAPH_END -->
