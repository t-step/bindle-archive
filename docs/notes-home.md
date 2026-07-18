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
    context.md                       # NEW — regenerable projection, #185 apply
    .bindle/context/
      config.json                    # NEW — authoritative, #191
      judgments.jsonl                # NEW — append-only ledger, #184
      index.json                     # NEW — rebuildable materialized graph, #185
      .lock                          # NEW — single-writer lock
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

A shell `export` only lasts for that shell, and an export inside a Claude Code
session doesn't survive to the next one. The durable mechanism for Claude Code
is the `env` block of `~/.claude/settings.json`; `/notes-home set <path>`
(backed by `bin/notes-home.sh`) writes it safely: it validates the target,
warns if the path is inside a git repo (the exact leak the notes home exists
to prevent), shows the JSON diff, and writes only after explicit confirmation
— backing the file up first and touching only the one key, since provider
settings are foreign territory per
[ownership-boundaries.md](ownership-boundaries.md) and
[runtime-security-privacy.md](runtime-security-privacy.md). The change takes
effect at the next session start. `bin/notes-home.sh status` shows the current
resolution; `reset` removes the key the same careful way.

Deprecated compatibility aliases remain supported:

- `CLAUDE_KIT_NOTES_DIR`;
- `~/.claude-kit`.

Resolution order for workflows should be:

1. `BINDLE_NOTES_DIR`;
2. `CLAUDE_KIT_NOTES_DIR`;
3. `~/.bindle`;
4. existing `~/.claude-kit` data when a workflow intentionally keeps using the
   old location.

Bindle does not silently migrate or move user data. `/notes-home migrate
<path>` copies `projects/` and the denylist to a new home after a previewed,
confirmed plan — it skips anything that already exists at the destination and
never deletes the old directory; removing that remains your call, later. Or
copy the files yourself. Either way, keep the old directory until you are
comfortable deleting it.

## Obsidian

Obsidian reads folders of plain Markdown, which is exactly what this is. To see
profiles, session notes, and handoffs in a vault, point the variable into it:

```bash
/notes-home set ~/Vaults/main/bindle     # durable, previewed, confirmed
```

That is the entire integration. Notes appear in the vault, searchable and
linkable like anything else there. If your vault syncs to a cloud service, your
session notes go with it; consider that wider blast radius before choosing the
location.
