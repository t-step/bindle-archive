---
description: Show, set, migrate, or reset the Bindle notes home (point it at an Obsidian vault)
argument-hint: [status | set <path> | migrate <path> | reset]
allowed-tools: Bash(readlink:*), Bash(bin/notes-home.sh status:*)
---

<!-- Conventions (notes home layout, resolution order, privacy):
     docs/notes-home.md and the session-continuity skill are the source of
     truth. The script enforces the surgical-settings-write contract
     (docs/runtime-security-privacy.md rule 7); this command's job is to keep
     the human's explicit confirmation in the loop. -->

Manage where Bindle session workflows keep their notes. Argument, if any:
"$ARGUMENTS"

Ground rules — these are the contract, not suggestions:

- **Every write needs the user's explicit yes, this session.** `set`,
  `migrate`, and `reset` run in preview mode first; only after the user
  confirms the shown diff/plan do you re-run with `--apply`. Never start
  with `--apply`, and never treat an earlier approval as covering a new
  write.
- `status` is read-only and needs no confirmation.
- The env setting takes effect **next session** — say so whenever it changes.

Steps:

1. Locate the Bindle checkout: `readlink ~/.claude/commands/notes-home.md`
   and take the repo root two levels up from the target. If the link or
   checkout is missing, stop and tell the user to run `<bindle>/bin/notes-home.sh`
   from their Bindle checkout by hand (the manual fallback always works).
2. Parse the argument: default to `status`; otherwise `set <path>`,
   `migrate <path>`, or `reset`.
3. `status`: run `<bindle>/bin/notes-home.sh status` and relay the result — where the
   notes home resolves, why, whether it's persisted in
   `~/.claude/settings.json`, and what's in it.
4. `set <path>`: run `<bindle>/bin/notes-home.sh set <path>` (preview). Show the user
   the planned settings diff and any warning verbatim — especially the
   git-repo warning; if it fired, make sure they've read it before asking
   anything else. Ask for an explicit yes/no. On yes, re-run with `--apply`
   and relay the backup path, the next-session notice, and the optional
   shell-profile line. Offer `migrate` as the natural follow-up (setting the
   variable does not move existing notes).
5. `migrate <path>`: run the preview, show the copy/skip plan, get an
   explicit yes, then `--apply`. Remind the user the old home is left
   untouched and deleting it is their call, later.
6. `reset`: preview, show the diff, explicit yes, `--apply`, and relay the
   fallback resolution note.
