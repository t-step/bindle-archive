# The notes home

Where Bindle session workflows write durable Markdown, and how to relocate it.
This is the user-facing summary; the provider-neutral contract (file shapes,
naming, privacy rules) is [session-notes-format.md](session-notes-format.md),
which the `session-continuity` skill automates for Claude Code.

## Default layout

New Bindle names prefer:

```
~/.bindle/
  private-denylist.txt
  projects/<project>/
    profile.md
    sessions/YYYY-MM-DD-<slug>.md
    handoffs/YYYY-MM-DD-<slug>.md
```

Everything is plain Markdown with safe kebab-case filenames. There is no
database, daemon, app, or initialization step.

The notes home lives outside every project repo on purpose: session notes are
private by default and must never be one `git add -A` away from publication.
It is not this repo, either. Bindle versions capabilities; the notes home holds
your data.

## Relocating it

Use `BINDLE_NOTES_DIR` to move the whole tree:

```bash
export BINDLE_NOTES_DIR="$HOME/Notes/bindle"
```

Deprecated compatibility aliases remain supported:

- `CLAUDE_KIT_NOTES_DIR`;
- `~/.claude-kit`.

Resolution order for workflows should be:

1. `BINDLE_NOTES_DIR`;
2. `CLAUDE_KIT_NOTES_DIR`;
3. `~/.bindle`;
4. existing `~/.claude-kit` data when a workflow intentionally keeps using the
   old location.

Bindle does not silently migrate or move user data. To migrate, copy the files
yourself, update `BINDLE_NOTES_DIR` if needed, and keep the old directory until
you are comfortable deleting it.

## Obsidian

Obsidian reads folders of plain Markdown, which is exactly what this is. To see
profiles, session notes, and handoffs in a vault, point the variable into it:

```bash
export BINDLE_NOTES_DIR="$HOME/Vaults/main/bindle"
```

That is the entire integration. Notes appear in the vault, searchable and
linkable like anything else there. If your vault syncs to a cloud service, your
session notes go with it; consider that wider blast radius before choosing the
location.
