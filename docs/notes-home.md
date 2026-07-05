# The notes home (and pointing it at Obsidian)

Where the session workflow writes durable Markdown, and how to relocate it.
The full conventions live in the `session-continuity` skill; this is the
user-facing summary.

## Default layout

```
~/.claude-kit/
  private-denylist.txt                # optional; read by bin/check-private-info.sh
  projects/<project>/
    profile.md                        # durable project facts (/project-profile)
    sessions/YYYY-MM-DD-<slug>.md     # session notes (/session-end)
    handoffs/YYYY-MM-DD-<slug>.md     # future-session prompts (/handoff)
```

- Everything is plain Markdown with safe kebab-case filenames — no database,
  no daemon, no app required. `grep`/`ls` are the query language.
- The directory is created on demand; there is nothing to initialize.
- It lives **outside every project repo** on purpose: session notes are
  private by default and must never be one `git add -A` away from publication
  (see [privacy-boundaries.md](privacy-boundaries.md)).
- It is not this repo, either — claude-kit versions *capabilities*; the notes
  home holds *your data*. Back it up however you back up personal files.

## Relocating it: `CLAUDE_KIT_NOTES_DIR`

Set one environment variable to move the whole tree:

```bash
# in ~/.zshrc (or equivalent)
export CLAUDE_KIT_NOTES_DIR="$HOME/Notes/claude-kit"
```

Every session command resolves the base as `$CLAUDE_KIT_NOTES_DIR`, falling
back to `~/.claude-kit`. Nothing else changes.

## Obsidian (optional, zero integration)

Obsidian reads folders of plain Markdown, which is exactly what this is. To
see profiles, session notes, and handoffs in a vault, point the variable into
it:

```bash
export CLAUDE_KIT_NOTES_DIR="$HOME/Vaults/main/claude-kit"
```

That's the entire integration. Notes appear in the vault, searchable and
linkable like anything else there. Deliberately **not** provided: sync,
automated backlinks, templates needing community plugins, or any dependency on
Obsidian being installed — the files must stay useful as bare Markdown for a
session running `grep` over them.

One caveat: if your vault syncs to a cloud service, your session notes go with
it. That's usually what you want (they're your notes), but it's a wider blast
radius than `~/.claude-kit` — worth a moment's thought before pointing the
variable at a synced vault.
