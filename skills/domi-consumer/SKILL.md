---
name: domi-consumer
description: Use when working in (or unsure whether you're in) a repository that consumes DomI — to detect the .domi-pin, report drift status (current/behind/forked/unverifiable/malformed), and see which inherited policy categories are owned upstream. Reports; never vendors or reimplements DomI-owned policy.
---

# DomI consumer status

Run the read-only detector and interpret its verdict per the contract
`docs/domi-consumer.md`. Never claim `current` without the detector confirming
it; never manufacture a local replacement for a DomI-owned policy.

**Where the tools live.** Both `bin/domi-status.sh` and `docs/domi-consumer.md`
are at the **root of your Bindle checkout** — the repo this skill installs from.
The installed skill directory ships only this `SKILL.md` (it is a symlink into
`<bindle>/skills/domi-consumer/`; resolve that symlink to find `<bindle>`). The
script is **not** in the installed skill directory and **not** in the consumer
repo you are inspecting — run it from your Bindle checkout, pointing `--repo` at
the consumer repo.

## Steps

1. Run the detector from your Bindle checkout:
   `bash <bindle>/bin/domi-status.sh --repo <consumer-repo-root>` (omit `--repo`
   to default to the current repo). To answer whether ONE category is
   inherited — e.g. before a release decision — add
   `--category <slug>` (a slug from the table below) instead: it prints
   `inherited=true|false|malformed` directly, no verdict-table lookup needed.
   release-captain's stop conditions use this mode.
2. Read the exit code / verdict:
   - `not-a-domi-consumer` (2) — nothing to do.
   - `current` (0) — report the source and continue.
   - `behind` (1) / `forked` (3) — if this repo's own policy makes DomI drift a
     hard stop, stop write-work and cite the `sync-from-domi` path; otherwise
     report and continue.
   - `unverifiable` (4) — report degraded status; never treat as current;
     follow the repo's documented offline policy.
   - `malformed` (5) — stop and surface the named bad field.
3. Surface the inherited-policy categories from the detector's `authority:` line
   and point at DomI as the source of truth.

DomI owns its policy. This skill detects and describes the dependency; it does
not vendor, fork, or reimplement it.
