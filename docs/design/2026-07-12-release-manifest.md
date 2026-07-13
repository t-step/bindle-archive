# Design: release manifest with provenance

Resolves the design half of issue #33. Status: **approved design, ready for
planning/implementation**. Unlike the #31/#35 doc-sized contracts, the
implementation here is real code (`bin/release-manifest.py`, a `bin/release.sh`
change, tests) plus one reference doc — not a contract doc that is itself the
implementation.

## Problem

Bindle cuts local, unpushed releases (`bin/release.sh`) but produces no
structured record of what a release actually shipped. As the toolkit becomes
executable personal infrastructure with real consumers (`bin/doctor.sh` now
reads machine-readable capability data via `install-manifest.tsv`), it should
be possible to answer, from one file: which commit was released, which
capabilities and provider assets shipped, which checks were run, which tool
versions produced the release, and what changed since the previous version.

## Goals

1. `bin/release.sh` produces a deterministic manifest as an additive step —
   no restructuring of its existing tag-cutting behavior.
2. The manifest is drawn from `capabilities.json` and `install-manifest.tsv`
   programmatically — never hand-duplicated.
3. A release fails before any commit is made if the manifest cannot be
   generated consistently.
4. The manifest is committed alongside `VERSION`/`CHANGELOG.md` in the
   existing `Release vX.Y.Z` commit — durable, versioned, git-blameable
   history, consistent with how those two files already work.
5. Documentation explains how to inspect and verify a release manifest.
6. `docs/product-boundary.md`'s stale "Later" triage for #29/#33 gets
   corrected in the same PR, with the evidence that unlocked it cited.

## Non-goals

- No automatic publishing of GitHub releases (issue's own non-goal).
- No artifact signing or provenance attestations — `self_checksum` (below)
  is a plain content hash for tamper-evidence, not a signing model. No keys,
  no identities, no verification-of-authorship claim.
- No capability-level diff engine between releases. This is the first
  manifest ever generated — there is no prior manifest to diff against yet.
  "Previous version and changelog range" is satisfied by embedding the
  previous version string and this release's own CHANGELOG section text,
  not by computing an added/removed/changed-maturity diff. A diff engine is
  a natural follow-up once a second manifest exists, not part of #33.
- No ongoing `make check` drift-check of `RELEASE-MANIFEST.json` against
  current HEAD. Unlike `install-manifest.tsv` (a live projection of current
  `capabilities.json`, correctly drift-checked every commit),
  `RELEASE-MANIFEST.json` is a point-in-time record of a past release — it
  is *expected* to diverge from a fresh regeneration the moment any commit
  lands after the release. Its consistency is enforced only at the moment
  `bin/release.sh` cuts a release (see Determinism below), not continuously.

## Architecture

`bin/release.sh` gets one new step, inserted after the existing
`bin/check.sh` / `bin/test-install.sh` verification calls and after
`VERSION`/`CHANGELOG.md` are rolled, but before `git commit`:

1. Run `bin/release-manifest.py --emit --version "$new" --previous "$cur"`
   twice in a row (in-memory; the first pass writes nothing) and diff every
   field except `timestamp`. A real mismatch aborts the release before any
   file is written or commit made — this is the mechanical enforcement of
   "a release fails if the manifest cannot be generated consistently."
2. Write `RELEASE-MANIFEST.json` to the repo root.
3. `git add VERSION CHANGELOG.md RELEASE-MANIFEST.json`, commit
   `Release vX.Y.Z` as today, then tag. Still no push.

`bin/release-manifest.py` is a new, small, stdlib-only Python script
mirroring `bin/check-inventory.py`'s style. It:

- reads `capabilities.json` for the capability snapshot;
- reads `install-manifest.tsv` for provider-specific installed surfaces;
- shells out to `git`/`bash`/`python3`/`shellcheck`/`shfmt` for tool
  versions (`--version`; optional tools report `"not installed"` rather than
  erroring, matching `bin/check.sh`'s own graceful degradation);
- extracts this release's `CHANGELOG.md` section by locating the two `## [`
  headers that bound it;
- computes `self_checksum` (SHA256 over the canonical JSON with that field
  blanked before hashing).

All emitted arrays are sorted by a stable key (capabilities by `name`,
installed surfaces by `(provider, category, name)`, tool versions by key) so
ordering can never itself be a source of a false-positive
regenerate-and-diff mismatch.

## Manifest schema (`RELEASE-MANIFEST.json`, repo root)

```json
{
  "generated_by": "bin/release-manifest.py — do not edit by hand",
  "version": "0.4.0",
  "previous_version": "0.3.0",
  "commit_sha": "<HEAD at manifest-generation time — the parent commit, not the about-to-be-created release commit, which does not exist yet>",
  "timestamp": "2026-07-12T21:03:00Z",
  "changelog": "## [0.4.0] - 2026-07-12\n\n### Added\n...",
  "capabilities": [
    {
      "name": "...",
      "type": "skill",
      "provider": { "claude": "installed", "codex": "untested" },
      "maturity": "tested",
      "version_introduced": "0.1.0"
    }
  ],
  "installed_surfaces": [
    {
      "provider": "claude",
      "category": "skill",
      "name": "...",
      "src": "skills/.../SKILL.md",
      "dest": "~/.claude/skills/.../SKILL.md"
    }
  ],
  "verification": [
    { "command": "bin/check.sh", "exit_code": 0 },
    { "command": "bin/test-install.sh", "exit_code": 0 }
  ],
  "tool_versions": {
    "git": "2.43.0",
    "bash": "5.2.26",
    "python3": "3.12.1",
    "shellcheck": "0.9.0",
    "shfmt": "not installed"
  },
  "self_checksum": "sha256:..."
}
```

`verification` records command + exit code only. By the time
`bin/release-manifest.py` runs, `bin/check.sh` and `bin/test-install.sh` have
already succeeded (`bin/release.sh` runs under `set -euo pipefail` and would
have aborted on a nonzero exit) — the field is a truthful provenance record,
not a live pass/fail signal captured mid-flight. Nothing about the acceptance
criteria requires capturing full stdout/stderr, and doing so would bloat the
manifest with tool chatter irrelevant to "what shipped."

## Determinism & failure semantics

`timestamp` is the one field explicitly exempt from the determinism
guarantee (wall-clock time necessarily differs between two runs). Every
other field must be a pure function of repo state at generation time. The
regenerate-and-diff check in `bin/release.sh` (Architecture, step 1) is the
concrete mechanism that proves this on every real release — a mismatch
(flaky read, nondeterministic array ordering, an environment difference
mid-run) is caught and aborts the release before `VERSION`/`CHANGELOG.md`/
the manifest are ever committed.

## Documentation

New `docs/release-manifest.md`, same shape as `docs/capability-inventory.md`
(schema reference table + "how do I inspect/verify a release" guide): what
each field means, how to recompute `self_checksum` by hand, and a pointer to
the regenerate-and-diff behavior as the "why you can trust this" story.
`README.md`/`CONTRIBUTING.md` get a one-line cross-link, matching how
`capability-inventory.md` is linked today — no structural rewrite of either.

## Capability inventory classification

`bin/check-inventory.py`'s fuzzy-candidate set is `bin/*.sh` **and**
`bin/*.py` (confirmed in `check_completeness_fuzzy`), so `bin/release-manifest.py`
needs a `capabilities.json` row (type `script`). `bin/test-release-manifest.sh`
is auto-excluded by the existing `^bin/test-.*\.sh$` rule — no row needed.
`docs/release-manifest.md` needs a row (type `contract`) or an explicit
`not_a_capability` ledger entry with a reason, decided when the doc is
drafted.

## Testing

New `bin/test-release-manifest.sh`, following `bin/test-check-inventory.sh`'s
fixture-repo shape (`check()` helper, throwaway `--root`-pointed fixture
repos, pass/fail tally). Covers: happy path against a minimal fixture repo;
missing/malformed `capabilities.json`; missing `install-manifest.tsv`; a tool
reported "not installed"; and the regenerate-and-diff logic itself (inject a
source of nondeterminism and confirm it's caught, not silently accepted).
Added to `Makefile`'s `test:` target alongside the existing `bin/test-*.sh`
list.

## docs/product-boundary.md correction

The doc's 2026-07-10 triage classifies #33 (and #29, which has since
shipped) as **Later**, gated on "a consumer materializes for a manifest
(dashboard, doctor, or an external tool needs machine-readable capability
data)." `bin/doctor.sh` now reads `install-manifest.tsv` (generated from
`capabilities.json`) via `bin/lib/manifest.sh` — this is exactly that
trigger, already fired but not yet reflected in the doc. This PR includes a
small correcting commit: remove/update the #29 Later bullet (shipped), move
#33 out of Later with the `doctor.sh` evidence cited, per the doc's own
"revise this document in its own PR with the evidence cited" instruction.

## Rollout

- `Makefile`: add `bin/test-release-manifest.sh` to `test:`.
- `CHANGELOG.md`: one `Unreleased` bullet for the manifest feature (issue
  #33).
- `capabilities.json`: new `script` row for `bin/release-manifest.py`;
  `docs/release-manifest.md` classified (`contract` or ledger).
- Branch: `feature/33-release-manifest` off `main`, one PR, closes #33. The
  `product-boundary.md` correction lands as a separate commit in the same
  PR — small, directly evidenced by this same work, not worth a second
  review cycle.
- No changes to `bin/release.sh`'s tag-cutting behavior beyond the one
  additive step; no push; no signing.
