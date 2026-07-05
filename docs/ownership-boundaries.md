# Ownership boundaries

What claude-kit owns, what it may touch, and what it must never touch. This is
the contract behind the installer's "good citizen guarantee" and the session
workflow's "don't mutate project repos" default. If a change to the kit would
violate a line here, the change is wrong.

## What claude-kit owns

- **This repo** — its skills, agents, commands, `global/CLAUDE.md`, docs, and
  `bin/` scripts.
- **Symlinks in `~/.claude/` whose target resolves inside this repo.** That is
  the entire ownership test (`install.sh` prefix-matches `readlink` output
  against the repo root). A link the kit created is owned; everything else is
  foreign.
- **`~/.claude-kit/`** — the kit's own user-level data directory (project
  profiles, session notes, handoffs). Created on demand by the session
  workflow; never inside a project repo.

## What it may read

- Any project repo it's invoked in — status, branches, history, docs, config —
  in order to summarize state and find validation gates.
- Project-level `.claude/` and `CLAUDE.md` (read to *respect* them, never to
  edit them).
- Existing notes/profiles under `~/.claude-kit/` (or `CLAUDE_KIT_NOTES_DIR`).

## What it may write

- Its own repo (when you're developing the kit itself).
- Owned symlinks in `~/.claude/` (create, retarget, prune-if-broken).
- Files under `~/.claude-kit/` (or the configured notes dir).
- A project repo **only when explicitly asked** — e.g. an explicit
  `/project-profile` export into the repo, or ordinary requested code changes.
  Session bookkeeping never lands in a project repo by default.

## What it must never touch

- Foreign files or symlinks in `~/.claude/` — anything a plugin, another tool
  (e.g. a DomI-style pin/sync setup), or you-by-hand put there. The installer
  reports `CONFLICT` and moves on; it never renames, edits, backs up, or
  deletes foreign content.
- Project repos' `.claude/` and `CLAUDE.md` — project config is authoritative;
  the kit adapts to it, not the reverse.
- Secrets, credential stores, keychains, `.env` files.
- Remotes: the kit never pushes, publishes, or deploys anything.

## Interaction with project-level config

Claude Code's precedence already does the right thing: project `.claude/` and
`CLAUDE.md` override user-level config where they overlap. The kit is designed
around that — it fills in *everywhere else* and loses every conflict on
purpose. A project that ships its own skill or command with the same name wins
inside that project.

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

A `CONFLICT` line from `install.sh` means a name in this repo is already taken
in `~/.claude/` by something the kit doesn't own. Nothing was modified. Your
options, in order of preference:

1. **Rename the kit's item** (`skills/<new-name>/`, re-run `install.sh`) so
   both coexist.
2. **Keep theirs** — delete or don't-install the kit's version.
3. **Adopt it into the kit** — if the foreign file is actually yours and worth
   versioning, move its content into this repo, remove the foreign file
   yourself, and re-run `install.sh`. The installer will not do this move for
   you, by design.

If you deleted the repo (or moved it) and `~/.claude/` is full of broken links:
re-clone/restore the repo at the same path and run `bin/install.sh`, or run
`bin/install.sh --prune` from the new location — it only sweeps links that
point into *that* checkout, so links into the old path must be removed by hand
(`find ~/.claude -type l ! -exec test -e {} \; -print` lists broken links to
review).
