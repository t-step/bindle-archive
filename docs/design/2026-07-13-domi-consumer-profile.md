# DomI consumer profile and drift-status preflight (issue #58)

Status: design approved 2026-07-13. Parent: #55. Prerequisites #56, #57 both
closed. Related: #29 (capability inventory), #31 (workflow composition).

## Problem

Several repositories the maintainer works in are DomI consumers: they commit a
`.domi-pin` and inherit upstream behavior (drift blocking, branch/commit policy,
session hard stops, delegation rules, release governance). Bindle has no
first-class way to recognize that dependency. A Claude session may receive DomI
behavior through installed assets while a Codex session sees only local files
and can miss that write-work is gated or that a policy is owned upstream.

Vendoring DomI's skills or policy into Bindle would create a second, stale
source of truth. Bindle needs an **integration/profile, not a fork**: it must
*detect, report, and interoperate with* the DomI dependency while preserving
DomI as the authority for DomI-owned content.

## Core principle

Distinguish **reporting inherited policy** from **reimplementing it**. Bindle
owns only what is genuinely portable and offline-safe — `.domi-pin` detection
and field parsing. For the actual drift verdict it **delegates to DomI's own
scripts**, and where DomI is unreachable it reports a degraded status rather
than manufacturing a local replacement.

## Authoritative upstream facts (from `domattioli/DomI`)

`.domi-pin` schema (`skills/sync-from-domi/templates/domi-pin.example`), five
fields:

```
upstream: domattioli/DomI
branch: main
sha: <40-hex>
manifest_sha256: <64-hex>
pinned_at: <ISO-8601 Z>
```

DomI's `skills/sync-from-domi/scripts/check_pin.sh` defines the canonical
status contract by exit code:

| code | DomI meaning | Bindle verdict label |
|------|--------------|----------------------|
| 0 | synced (pin SHA == upstream HEAD and manifest hash matches) | `current` |
| 1 | behind (pin SHA != upstream HEAD) | `behind` |
| 2 | unpinned (no `.domi-pin`) | `not-a-domi-consumer` |
| 3 | forked (manifest hash mismatch at pinned SHA) | `forked` |
| 4 | skipped (offline / upstream unreachable — do NOT block) | `unverifiable` |
| 5 | malformed (pin format invalid) | `malformed` |

DomI also ships `offline_drift_check.sh` — a no-network sibling-clone drift
checker returning the same codes (with 4 = "no sibling clone to compare"). Both
are the delegation targets; Bindle reuses their exit-code numbers verbatim so
its detector is caller-interchangeable with DomI's own.

## Deliverables

### 1. `bin/domi-status.sh` — read-only detector

Read-only toward any target repo. Usage: `domi-status.sh [--repo <path>]`
(default target = `git rev-parse --show-toplevel` or `.`).

Algorithm:

1. **No `.domi-pin`** → `not-a-domi-consumer`, clean (exit 2). Bindle cannot
   distinguish "never a consumer" from "consumer with a deleted pin"; per #58
   it exits cleanly as not-a-consumer and leaves the create-a-pin concern to
   DomI's own onstart.
2. **Pin present** → parse the five fields. Validate `upstream` present and
   `sha` matches `^[0-9a-f]{40}$`; on failure → `malformed` (exit 5), **naming
   the offending field**. Steps 1–2 are fully offline-decidable.
3. **Report the pin's self-described facts** (always, offline-safe): upstream,
   branch, short-sha, manifest hash, pinned_at.
4. **Drift verdict — delegate, never reimplement.** Locate DomI scripts by an
   overridable ladder:
   `$DOMI_SCRIPTS_DIR` → installed `~/.claude/skills/sync-from-domi/scripts/`
   → sibling checkout (`$DOMI_LOCAL_CHECKOUT` → `../DomI` → `/home/user/DomI`).
   Run `check_pin.sh` (network + sibling); if it reports offline (code 4), fall
   back to `offline_drift_check.sh` (sibling-only); if neither is reachable →
   `unverifiable` (exit 4). Map DomI's exit code straight through. **A pin is
   never reported as `current` unless a delegated check confirmed it.**
5. **Surface inherited-policy categories + authority pointer** (static, from the
   contract's category→authority map).

Exit codes: identical to DomI's `check_pin.sh` (table above). This *is* the
"honor the same vocabulary" requirement.

`--json` machine-readable output is **deferred** (YAGNI — #58 gates it on "#29
supplies an immediate consumer"; none exists). Documented as an extension point.

### 2. `docs/domi-consumer.md` — portable contract

Sections:

- Purpose and scope (report ≠ reimplement; DomI is authoritative).
- `.domi-pin` detection and the five-field schema.
- Status vocabulary and the exit-code mapping to DomI's `check_pin.sh`.
- Source-of-truth and ownership rules (DomI owns its policy; Bindle
  detects/describes/points, never redefines).
- **Write-work gating** — Bindle *reports*; the consumer repo's own policy
  decides any hard stop. Bindle never invents a gate:
  - `current` → report the source and continue;
  - `behind` / `forked` → stop repository write-work *iff* the consumer repo's
    own policy defines drift as a hard stop; explain the canonical
    `sync-from-domi` path;
  - `unverifiable` → never claim current; report degraded status and follow the
    consumer repo's documented offline policy;
  - `malformed` → stop and identify the malformed field;
  - `not-a-domi-consumer` → exit cleanly.
- Offline / unverifiable behavior.
- **Inherited-policy category → authority map** (the seven from #58): branch and
  commit discipline; destructive-action hard stops; context/session management;
  delegation/coding dispatch; package release and SemVer governance;
  issue/session workflow requirements; sync/update ownership — each pointing at
  where in DomI it is authoritatively defined.
- Provider-adapter guidance — both Claude and Codex invoke the same helper and
  honor the same vocabulary; an adapter may summarize the binding categories and
  point to the pinned authority, but may not silently manufacture a local
  replacement.

### 3. `skills/domi-consumer/` — thin skill

Claude-native `SKILL.md` (Phase-1 rule: Claude assets stay Claude-native).
Triggers: "am I in a DomI consumer repo?", "check DomI drift/status",
consumer-repo session-start. Body: invoke `bin/domi-status.sh`, interpret the
verdict per the contract, surface inherited categories + authority. It is a thin
wrapper over a portable bash script.

The **#29 three-places rule applies**: adding this skill touches the skill dir,
a `capabilities.json` skill row, *and* a `docs/skill-portability-audit.md` row
(classified *portable* — thin wrapper over portable bash), or `make check`
fails on bound-table drift.

### 4. `capabilities.json` + `check-inventory.py`

- `script` row for `bin/domi-status.sh` (mutation `["network"]`; read-only
  toward the repo — no `disk`/`external`).
- `contract` row for `docs/domi-consumer.md`.
- `skill` row for `skills/domi-consumer` (+ the audit-table row above).
- A new top-level **`external_upstreams`** array (parallel to
  `not_a_capability`; keeps DomI out of the capability `type` enum — it is a
  dependency, not a Bindle capability), one entry:

  ```json
  {
    "name": "DomI",
    "owner": "domattioli",
    "repo": "domattioli/DomI",
    "role": "upstream workflow authority",
    "pin_file": ".domi-pin",
    "authority_for": ["branch-commit-discipline", "destructive-action-hard-stops",
      "context-session-management", "delegation-dispatch",
      "release-semver-governance", "issue-session-workflow", "sync-update-ownership"],
    "detector": "bin/domi-status.sh",
    "contract": "docs/domi-consumer.md"
  }
  ```

- `check-inventory.py` gains a small shape-validator for `external_upstreams`
  (required keys present, types correct). It is **not** part of the bijection.

## Testing — `bin/test-domi-status.sh` + fixtures

Hermetic: throwaway fixture dirs only, **never a real consumer repo** (#58).
Fixture matrix:

| fixture | expectation |
|---------|-------------|
| current pin (sha == fixture DomI HEAD) | `current`, exit 0 |
| stale pin (sha != HEAD) | `behind`, exit 1 |
| manifest mismatch | `forked`, exit 3 |
| malformed pin (bad `sha`) | `malformed`, exit 5, names the field |
| offline / no DomI reachable | `unverifiable`, exit 4, not `current` |
| non-consumer repo (no `.domi-pin`) | `not-a-domi-consumer`, exit 2 |

**Determinism strategy:** tests point `$DOMI_LOCAL_CHECKOUT` at a tiny fixture
DomI git repo (a `MANIFEST.md` committed at a known SHA) and exercise the *real*
delegation to DomI's `offline_drift_check.sh` with no network — no mocking of
Bindle's own logic. The `unverifiable` case points the locator at nothing.
Legacy-pin-shape: the current template has only one shape; noted N/A unless a
legacy variant surfaces in an active repo.

## Acceptance criteria (from #58)

- A Claude and a Codex session reach the same compact status verdict in a
  fixture, and against at least one real consumer checkout. **Caveat:** the
  real-checkout step needs an actual DomI-consumer repo present locally (Bindle
  is not one); buildable without it, final acceptance runs where one exists.
- The workflow never vendors or rewrites DomI-owned skills/policy.
- Status output identifies both the dependency and the authoritative source.
- Write-work gating follows the consumer repo's explicit policy and never
  reports an unverifiable pin as current.
- The capability inventory records DomI as an external upstream integration with
  provenance/ownership metadata.
- `make check` and `make test` pass.

## Non-goals (from #58)

Rebuilding `sync-from-domi` inside Bindle; installing the full DomI marketplace;
filing or closing downstream sync issues; making Bindle responsible for DomI's
consumer fleet; normalizing every upstream governance system into one generic
package manager.

## Risks

- The drift verdict's fidelity depends on DomI being reachable; `unverifiable`
  is a first-class state and callers must treat it as degraded, not `current`.
- DomI's script contract (exit codes, script paths) could change upstream; the
  detector depends on `check_pin.sh` / `offline_drift_check.sh` staying at their
  documented exit-code contract. The contract doc records the pinned assumption.
