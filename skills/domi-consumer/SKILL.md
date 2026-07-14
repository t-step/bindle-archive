---
name: domi-consumer
description: Use when working in (or unsure whether you're in) a repository that consumes DomI — to detect the .domi-pin, report drift status (current/behind/forked/unverifiable/malformed), and see which inherited policy categories are owned upstream. Reports; never vendors or reimplements DomI-owned policy.
---

# DomI consumer status

Run the read-only detector and interpret its verdict per
`docs/domi-consumer.md`. Never claim `current` without the detector confirming
it; never manufacture a local replacement for a DomI-owned policy.

## Steps

1. Run: `bash bin/domi-status.sh --repo <repo-root>` (default: current repo).
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
