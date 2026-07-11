# Ownership boundaries

What Bindle owns, what it may touch, and what it must never touch. This is
the contract behind the installer's "good citizen guarantee" and the session
workflow's "don't mutate project repos" default. If a change to the kit would
violate a line here, the change is wrong.

## What Bindle owns

- **This repo** — its Claude assets, provider guidance files, docs, and `bin/`
  scripts.
- **Symlinks in installed provider surfaces whose target resolves inside this
  repo.** That is the entire ownership test (`install.sh` prefix-matches
  `readlink` output against the repo root). A link the kit created is owned;
  everything else is foreign.
- **`~/.bindle/`** — the preferred user-level data directory (project profiles,
  session notes, handoffs). Deprecated `~/.claude-kit/` remains an alias; data is
  not moved automatically.

## What it may read

- Any project repo it's invoked in — status, branches, history, docs, config —
  in order to summarize state and find validation gates.
- Provider project guidance such as `.claude/`, `CLAUDE.md`, and `AGENTS.md`
  (read to *respect* them, never to edit them unless explicitly asked).
- Existing notes/profiles under `~/.bindle/`, `BINDLE_NOTES_DIR`, or deprecated
  `~/.claude-kit/` / `CLAUDE_KIT_NOTES_DIR`.

## What it may write

- Its own repo (when you're developing the kit itself).
- Owned symlinks in installed provider surfaces (create, retarget,
  prune-if-broken).
- Files under `~/.bindle/` or the configured notes dir.
- A project repo **only when explicitly asked** — e.g. an explicit
  `/project-profile` export into the repo, or ordinary requested code changes.
  Session bookkeeping never lands in a project repo by default.
- `~/.claude/settings.json`, but only via an explicit, standalone opt-in
  command — never `bin/install.sh`, never silently. Every such command
  follows the same discipline: validate the file is parseable JSON first,
  back it up before writing, touch only the specific key(s)/hook entries it
  owns (every other key is preserved byte-for-byte), preview the exact diff,
  and require `--apply` (or an interactive `y`) before writing anything.
  Today: `bin/notes-home.sh set|reset` (the `env.BINDLE_NOTES_DIR` key) and
  `bin/install-session-hooks.sh install|uninstall` (the `hooks.SessionStart`
  / `hooks.SessionEnd` entries whose `command` points at
  `global/hooks/session-start-context.py` /
  `global/hooks/session-end-breadcrumb.py` — every other hook entry, e.g. the
  `nested-notes-guard` `PreToolUse` hook, is left untouched).

## What it must never touch

- Foreign files or symlinks in any installed provider surface — anything a
  plugin, another tool, or you-by-hand put there. The installer reports
  `CONFLICT` and moves on; it never renames, edits, backs up, or deletes foreign
  content.
- Project repos' provider config — project config is authoritative; Bindle
  adapts to it, not the reverse.
- Secrets, credential stores, keychains, `.env` files.
- Remotes: the kit never pushes, publishes, or deploys anything.

## Interaction with project-level config

Claude Code's precedence already does the right thing: project `.claude/` and
`CLAUDE.md` override user-level config where they overlap. The kit is designed
around that — it fills in *everywhere else* and loses every conflict on
purpose. A project that ships its own skill or command with the same name wins
inside that project.

Codex Phase 1 support is direct `AGENTS.md` guidance. Bindle installs
`global/AGENTS.md` only to an explicit `--codex-home` target and does not assume
Claude skills, agents, or commands have Codex equivalents.

## Interaction with plugins, MCP, and DomI-style setups

- **Plugins** (installed via `claude plugin …`) manage their own lifecycle. The
  kit references their skills by name (soft runtime pointers) and never vendors
  or shadows them deliberately.
- **MCP servers** are configuration the kit doesn't manage at all.
- **Pin/sync systems** (e.g. DomI) may place their own links into `~/.claude/`.
  To the installer those are foreign symlinks: conflicts, left untouched.

## What `--prune` may remove

Only entries that are **both**:

1. owned (a symlink pointing into this repo), **and**
2. broken (the target no longer exists — i.e. the item was deleted here).

Never working owned links, never foreign links (broken or not), never real
files. `bin/test-install.sh` asserts this on every commit.

## Recovery when conflicts happen

A `CONFLICT` line from `install.sh` means a destination is already taken by
something the kit doesn't own. Nothing was modified, but the requested
install is incomplete — by default the installer exits `1` so scripted callers
(dotfiles installers, agents) can't mistake conflict-safety for success. Pass
`--allow-conflicts` to keep the warnings but exit `0` (e.g. for an interactive
run where you'll resolve conflicts by hand afterward). See the exit codes
documented in `bin/install.sh`'s usage header. Your options, in order of
preference:

1. **Rename the kit's item** (`skills/<new-name>/`, re-run `install.sh`) so
   both coexist.
2. **Keep theirs** — delete or don't-install the kit's version.
3. **Adopt it into the kit** — if the foreign file is actually yours and worth
   versioning, move its content into this repo, remove the foreign file
   yourself, and re-run `install.sh`. The installer will not do this move for
   you, by design.

## Recovery when the repo was moved or renamed

If the repo moved (or was re-cloned elsewhere), installed links still point at
the old path: broken, and — because the ownership test is a prefix match
against *this* checkout — classified as foreign by the new location.
`bin/doctor.sh` reports these as `earlier-checkout`. To recover:

1. **Preferred:** run `bin/install.sh --adopt` from the new checkout. It lists
   every *broken* link whose target ends with an expected Bindle item path
   (e.g. `…/skills/fork-pr-flow`), shows the old prefix, and relinks only
   after you confirm. It never touches live links, real files, or broken
   links that don't match an expected item exactly — verify the old prefix
   shown really is your previous Bindle checkout before answering yes.
   Declining leaves everything untouched (reported as conflicts).
2. Or re-clone/restore the repo at the *old* path and run `bin/install.sh`.
3. Or remove the stale links by hand
   (`find ~/.claude -type l ! -exec test -e {} \; -print` lists broken Claude
   links to review) and reinstall. `bin/install.sh --prune` won't help here —
   it only sweeps links that point into *this* checkout.
