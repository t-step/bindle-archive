# SQLite workflow index — design note (not implemented)

Status: **design only, deliberately deferred.** v0.2 ships the Markdown-first
workflow with no database. This note records what an optional SQLite layer
would be *if* the Markdown notes home ever grows past what `grep` handles
comfortably — so a future session doesn't re-derive the design or, worse,
build something bigger.

## Decision: defer

The bar set for implementing in v0.2 was "obviously small, optional, and
safe". It fails today:

- The notes home is brand new — there is no corpus to index and no observed
  query pain. An index of nothing is speculation.
- Every consumer so far (session commands, `/workflow-review`) needs *recent
  files for one project* — `ls` + `grep` territory.
- A database invites schema churn while the note *shapes* are still settling.
  Markdown can be reshaped by editing prose; a schema migration cannot.

Revisit when a `/workflow-review` across many projects is measurably slow or
misses things `grep` can't express (cross-project joins, date-range rollups) —
that's the follow-up prompt at the bottom.

## What it would be

A single file, `~/.claude-kit/index.db`, maintained by one small script
(`bin/notes-index.sh`) that scans the notes home and (re)builds:

- **projects** — slug, repo path, last-seen date (project registry);
- **sessions** — project, date, goal, validation status, file path (session
  index);
- **checks** — command run, pass/fail, session (command/check history);
- **decisions** — one row per decision line, session, text (decision lookup);
- **validation_status** — latest green/red per project over time.

Everything derived, nothing authoritative: **Markdown stays the source of
truth; the DB is a disposable cache.** `rm ~/.claude-kit/index.db` must lose
nothing but query speed.

## Constraints (binding on any future implementation)

- **Optional and graceful:** every workflow works with the DB absent; scripts
  no-op with a notice when `sqlite3` isn't installed. No workflow may *write
  only* to the DB.
- **`sqlite3` CLI only** — the binary ships with macOS and most Linuxes. No
  Python/Node drivers, no ORM, no daemon, no background indexing; rebuild
  runs on demand (or at `/session-end`, best-effort).
- **No secrets, no raw transcripts** — rows hold the same sanitized fields the
  notes hold, nothing more. The DB lives in the notes home, never in a repo.
- **Schema versioning:** a `meta(schema_version)` table; on mismatch the
  script drops and rebuilds rather than migrating (legitimate because the DB
  is derived — this is the whole payoff of cache-not-store).
- **Export:** `bin/notes-index.sh --export md|json` renders query results back
  to Markdown/JSON so nothing downstream ever needs SQL.
- **Tested like the installer:** fixture notes home in a temp dir, assert
  rebuild/queries/absence-of-sqlite3 behavior, before it ships.

## Follow-up prompt (when the time comes)

> In claude-kit, implement `bin/notes-index.sh` per
> `docs/sqlite-workflow-index.md`: rebuild-from-scratch indexing of the notes
> home into `~/.claude-kit/index.db` using only the `sqlite3` CLI, schema v1
> as designed, graceful no-op without sqlite3, `--export md|json`, plus a
> fixture-based test script wired into pre-commit. Update the design note's
> status and the README. Do not add write paths anywhere else.
