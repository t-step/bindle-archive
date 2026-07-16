# Portable workflow review (v0.2 planning)

A point-in-time inventory of claude-kit as of v0.1.0 + unreleased work, written
before the v0.2 "portable workflow substrate" pass. Behavior described here was
verified against the actual scripts and tests, not assumed.

## Current architecture

claude-kit is "dotfiles for Claude Code": a single repo that version-controls
user-level Claude Code assets and symlinks them into `~/.claude/`.

| Repo path | Installed to | Meaning |
|---|---|---|
| `skills/<name>/` (dir with `SKILL.md`) | `~/.claude/skills/<name>` | reusable techniques |
| `agents/<name>.md` | `~/.claude/agents/<name>.md` | subagents |
| `commands/<name>.md` | `~/.claude/commands/<name>.md` | slash commands |
| `global/CLAUDE.md` | `~/.claude/CLAUDE.md` | global personal instructions |
| root `CLAUDE.md` | *(never installed)* | this repo's own project memory |

Names starting with `_` or `.` are skipped (templates). Everything is plain
Markdown + shell; there is no database, daemon, or runtime dependency.

Supporting tooling, all in `bin/`:

- `install.sh` — the symlink installer (`--prune`, `--home DIR` for tests).
- `check.sh` — hygiene checks: shellcheck/shfmt, frontmatter (`name` +
  `description`, name↔folder/filename match), whitespace/EOF, repo-relative
  markdown links resolve, semver `version.txt` + Release Please changelog state.
  `--content-only` mode for the pre-commit hook.
- `test-install.sh` — end-to-end installer tests against a fake repo and a temp
  `--home` (13 assertions; see coverage below).
- `new.sh` — scaffold skill/agent/command from `_template` files.
- `install-hooks.sh` — `pre-commit install` (pre-commit + post-merge stages).
- The former local version-bump/tag wrapper from this point-in-time inventory
  is retired. Release Please now owns checked-in release state, and post-tag
  provenance publication uses the dedicated verified workflow.

Current convenience targets cover `check`, `test`, `install`, `doctor`,
`hooks`, `new`, `manifest`, and `docs`. Release publication has no convenience
target.

## Installer ownership model

Verified behavior of `install.sh` (`link_item` / `prune_dir`):

- **Owned = a symlink whose target resolves inside this repo.** That is the
  entire ownership test (`readlink` prefix-matched against `$REPO_ROOT/`).
- Owned links are created, retargeted (relinked) if stale, and counted.
- A foreign **symlink** (target outside the repo) → `CONFLICT`, left untouched.
- A foreign **real file/dir** at a destination name → `CONFLICT`, left
  untouched.
- `--prune` removes only links that are **both** owned **and** broken
  (target no longer exists). Working owned links and all foreign entries
  survive pruning.
- Idempotent: a re-run reports `0 linked, N already current`.

## Compatibility guarantees (as of v0.1)

1. Project-level `.claude/` and `CLAUDE.md` always win over user-level on
   overlap (Claude Code precedence; the kit fills in everywhere else).
2. The installer never clobbers anything it doesn't own (plugins, DomI-style
   pin/sync links, hand-placed files) — conflicts are reported, not resolved.
3. `--prune` cannot remove foreign content, by construction.
4. Other people's skills are consumed at their own level (plugins) and
   *referenced*, never vendored.
5. The kit writes only to `~/.claude/` (via install) and its own repo. It never
   mutates project repos.

## Test / check coverage

`bin/test-install.sh` (runs on every commit via pre-commit, and in CI):

- fresh install links all four item types;
- re-run is idempotent (`0 linked`, `4 already current`);
- foreign real file and foreign symlink survive an install (`CONFLICT`);
- broken owned link survives without `--prune`, is removed with it.

`bin/check.sh` covers frontmatter validity, name matching, link integrity,
formatting, and version sanity. CI (`.github/workflows/ci.yml`) runs
`pre-commit run --all-files` on PRs, on pushes to `main`, and on a weekly
schedule (Mondays 07:00 UTC) — the PR run is the primary gate, and the other
two triggers cover a direct/admin push to `main`, a branch-protection
misconfiguration, and tool drift (Python, shellcheck, shfmt, pre-commit)
between PRs, none of which a PR-only trigger would catch.

**Not covered today:** no tests for privacy/PII in committed content beyond
`detect-private-key`; no coverage that new command/skill *content* behaves as
intended (CONTRIBUTING's RED→GREEN→REFACTOR loop is manual discipline).

## Repo hygiene setup

- pre-commit framework: standard hooks (whitespace, EOF, YAML, large files,
  merge conflicts, private keys, shebang/exec), managed shellcheck + shfmt,
  `no-commit-to-branch` for `main`, local hooks for `check.sh --content-only`,
  `test-install.sh`, and `test-check.sh`, and a post-merge hook that re-runs
  `install.sh`.
- CI runs the same suite on PRs, on pushes to `main`, and on a weekly
  schedule; Dependabot + a weekly `pre-commit autoupdate` workflow keep
  hook/action versions current.
- Deliberately **no** markdown formatter (would churn carefully-phrased
  instruction prose).
- Branch discipline: `main` is protected by the `no-commit-to-branch` hook;
  everything lands via PR.

## Risks / gaps

1. **No personal-info guardrail.** `detect-private-key` catches keys, nothing
   catches private-relay emails, `/Users/<me>/…` paths, vault paths, pasted
   chat transcripts, or a personal denylist. One careless commit publishes it.
2. **No session continuity.** Each session rediscovers repo state, gates, and
   context from scratch; handoffs between Claude Code / Fable / Codex sessions
   are ad-hoc prose with no consistent shape.
3. **Session/scratch content has no designated home.** Without a documented
   "write durable notes *here*, outside the project repo" default, notes end up
   inside project repos — the main leak vector for risk 1.
4. **No improvement loop.** Recurring friction observed across sessions has no
   path into better skills/commands; insights evaporate at session end.
5. **Sharing model undocumented.** "Don't copy `~/.claude/` wholesale" is
   folklore, not a doc a collaborator can follow.
6. **Ownership boundaries are code comments.** The good-citizen guarantee lives
   in `install.sh`'s header and the README; there is no doc stating what the
   kit may read/write/never touch, or what recovery from a conflict looks like.
7. Minor: `check.sh`'s link check only sees standard inline markdown link
   syntax; `@path` includes are mentioned in its header comment but not
   actually checked. (It also greps inside code spans, so docs can't quote
   link syntax literally.)

## Recommended v0.2 slice

Keep the symlink installer untouched; add layers around it, all Markdown/shell:

1. **Docs** — ownership boundaries, collaborator sharing, privacy boundaries
   (this review plus three companion docs under `docs/`).
2. **Privacy guardrails** — `bin/check-private-info.sh` (offline, editable
   pattern list + personal denylist, fixture-tested, fails closed),
   `.gitleaks.toml` for optional Gitleaks runs, `.gitignore` entries for
   local/private workflow files, pre-commit + Makefile wiring.
3. **Session continuity MVP** — `/session-start`, `/session-end`, `/handoff`,
   `/project-profile` commands plus a `session-continuity` skill. Durable notes
   default to `~/.claude-kit/projects/<project>/`, overridable with
   `CLAUDE_KIT_NOTES_DIR` (point it at an Obsidian vault if you want one).
   Read-only toward project repos by default.
4. **Improvement loop** — `/workflow-review` + `/promote-insight` commands and
   `docs/iterative-improvement.md`; session-end emits candidate improvements.
5. **SQLite: design only** — `docs/sqlite-workflow-index.md` describes a future
   optional index; no implementation in v0.2 (fails the "obviously small and
   safe" bar while the Markdown layer is still new).

## Deferred (deliberately out of v0.2)

- SQLite implementation (design note only; revisit once Markdown notes have
  accumulated enough to need indexing).
- Obsidian-specific features (sync, backlink automation, plugin templates) —
  the notes dir is just Markdown; Obsidian can point at it.
- Any daemon, watcher, or background process.
- Automatic promotion of session insights into skills/docs (stays explicit and
  human-confirmed).
- Fixing the `@path` link-check gap in `check.sh` (harmless today; separate
  small PR if it starts to matter).
- A `--dry-run` flag for `install.sh` (nice-to-have; the temp `--home` tests
  cover the risk today).
