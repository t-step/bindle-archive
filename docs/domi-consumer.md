# DomI consumer contract

Bindle's provider-neutral contract for recognizing and reporting a DomI
dependency. Bindle **reports** inherited policy; it never **reimplements** it.
DomI (`github.com/domattioli/DomI`) remains the authority for DomI-owned skills
and policy. The executable adapter is `bin/domi-status.sh`.

## `.domi-pin` detection and schema

A DomI-consumer repo commits `.domi-pin` at its root, five fields:
`upstream`, `branch`, `sha` (40-hex), `manifest_sha256` (64-hex), `pinned_at`
(ISO-8601 Z). Absence of the file means the repo is not a DomI consumer.

## Status vocabulary (mirrors DomI `check_pin.sh` exit codes)

| verdict | exit | meaning |
|---------|------|---------|
| current | 0 | pin SHA == upstream HEAD and manifest hash matches |
| behind | 1 | pin SHA != upstream HEAD |
| not-a-domi-consumer | 2 | no `.domi-pin` |
| forked | 3 | manifest hash mismatch at pinned SHA |
| unverifiable | 4 | upstream unreachable — never reported as current |
| malformed | 5 | pin format invalid |

**How Bindle evaluates this:** `bin/domi-status.sh` delegates the drift verdict
to DomI's `offline_drift_check.sh` — an **offline** comparison against a local
DomI *sibling clone*. So `current`/`behind`/`forked` are evaluated against that
local checkout, which can lag live upstream `HEAD` if it has not been fetched.
A live-upstream check (DomI's `check_pin.sh`) is a documented follow-up; until
then the detector never reports `current` unless the delegated offline check
confirms it.

## Source of truth and ownership

DomI owns the definition of every inherited policy. Bindle detects the pin,
reports the verdict, and points at DomI as the authority. Bindle may summarize
the binding categories; it may not silently manufacture a local replacement.

## Write-work gating

`bin/domi-status.sh` reports; the **consumer repo's own policy** decides any hard
stop. current → continue; behind/forked → stop repository write-work *iff* the
consumer repo's policy defines drift as a hard stop, and cite the
`sync-from-domi` path; unverifiable → degraded, never current, follow the
consumer's documented offline policy; malformed → stop and name the bad field;
not-a-domi-consumer → exit cleanly.

## Offline / unverifiable behavior

When neither DomI's scripts nor a DomI checkout are reachable, the detector
reports the pin's self-described facts and the `unverifiable` verdict. It never
upgrades that to `current`.

## Inherited-policy categories and their authority

| category (slug) | authoritative source in DomI |
|-----------------|------------------------------|
| branch-commit-discipline | `skills/git-commit-guard`, `skills/enforce-branch-policy` |
| destructive-action-hard-stops | DomI constitution / session hard-stop policy |
| context-session-management | `skills/session-resume`, spec-006 |
| delegation-dispatch | `skills/dispatch-issue`, `skills/subagent-dispatch-policy` |
| release-semver-governance | `skills/release-integrity`, spec-013 |
| issue-session-workflow | `skills/list-issues`, `skills/check-done` |
| sync-update-ownership | `skills/sync-from-domi` |

## Provider adapters

Claude and Codex both invoke `bin/domi-status.sh` and honor the same vocabulary.
The `domi-consumer` skill is the Claude-native automation; Codex follows this
contract directly.
