# Package release integrity

**Status:** Contract, v1 · **Issue:** thomas-estep/bindle#59

The provider-neutral contract for answering one question about a Python
package, before any publish action: *is this release internally consistent
and safe to cut?* Version-source agreement, tag/version equality, changelog
presence, correct semver movement (including the pre-1.0 rules), track
routing for data-only changes, and a repo-supplied verification gate — all
checked mechanically where a machine can, flagged `uncertain` where only a
human can decide, and never a substitute for the repo's own release process.

This is **not** the contract for what a *Bindle* release itself shipped —
that is `docs/release-manifest.md` (#33), a different, narrower concern. It
is also not a replacement for DomI's own release-governance policy where a
repo has adopted it; see the defer rule below. And it never bumps a version,
tags a release, publishes to a registry, or otherwise authorizes anything —
see Boundaries.

## The nine checks

Copied from the design spec's ownership table (`docs/superpowers/specs/2026-07-14-package-release-integrity-design.md`).
Checks 1–8 have a corresponding verdict key emitted by the helper; check 9
is contract text only — there is no code path for it because there must
never be one.

| # | Check | Owner | Verdict key | pass / fail / uncertain |
|---|-------|-------|-------------|--------------------------|
| 1 | Change classification (breaking / additive / patch / data-only) | **Judgment** — helper never guesses | `change_classification` | `pass` if `--change-class` names a known class; `uncertain` if omitted — a human must classify. There is also a `fail` branch for an unknown class name, but it is unreachable via the CLI — `argparse`'s `--change-class` uses `choices`, so an unknown value is rejected by argument parsing before `check_change_classification` ever runs; that branch is reachable only calling the function directly as a library |
| 2 | Required version movement (incl. explicit pre-1.0 rules) | Helper, **given** a declared change class | `version_movement` | `pass` if the actual bump component matches what the class requires; `fail` if it doesn't; `uncertain` if the class, previous version, or resolved version is missing, or the class is `data-only` (routed to check 8 instead) |
| 3 | Version-source consistency (all discovered version declarations agree) | Helper | `version_source_consistency` | `pass` if every discovered source (`pyproject.toml [project]`/`[tool.poetry]`, any top-level package `__init__.py`) agrees; `fail` if they disagree; `uncertain` if no source was found at all |
| 4 | Tag consistency (proposed/existing tag == resolved package version) | Helper | `tag_consistency` | `pass` if the tag (an optional leading `v` stripped) equals the resolved version; `fail` if it doesn't; `uncertain` if no `--tag` was supplied or no version resolved |
| 5 | Changelog / release-note presence where the repo requires it | Helper | `changelog_present` | `pass` if `CHANGELOG.md` has a `[version]` section or an `[Unreleased]` section; otherwise `fail` by default, or `uncertain` if `--no-changelog-required` was passed |
| 6 | Build-metadata validation using the repo's own package tools | Helper shells out | `build_gate` | `pass` if `--build-cmd` exits 0; `fail` on any other exit code; `uncertain` if no `--build-cmd` was supplied, or the shell couldn't even run it (exit 126/127, or the subprocess call itself raised) |
| 7 | Verification gate (repo tests/checks pass) | Helper shells out | `verification_gate` | same rule as check 6, against `--test-cmd` |
| 8 | Track routing (a data-only change must not churn the package version) | **Judgment** — helper flags, contract guides | `track_routing` | only auto-checked when `--change-class data-only`: `pass` if the version stayed unmoved, `fail` if it moved; `uncertain` for every other change class (routing is not this check's job there) |
| 9 | No publication authority | Contract text — never a code action | *(none)* | there is no verdict for this because the helper never publishes, tags, or bumps anything; it only reports |

## The defer rule

The skill defers instead of running its portable checks when the target repo
declares DomI release governance authoritative. Concretely: the helper reads
`.domi-pin` at the repo root directly (no shell-out to `bin/domi-status.sh`,
which lives at the Bindle checkout root, not inside a consumer repo) and
treats the pin as authoritative once it is *well-formed* — `upstream` is set
and `sha` is a 40-hex commit — mirroring `bin/domi-status.sh`'s own
"malformed" check. There is no per-repo `owned_categories` opt-in and no
category literally named "release-integrity"; DomI's inherited-category list
is fixed, and any well-formed pin always carries the
`release-semver-governance` category (see `docs/domi-consumer.md`'s category
table, authoritative source `skills/release-integrity` upstream in DomI). So
a well-formed pin is enough to defer, regardless of the pin's drift verdict
(`current`/`behind`/`forked`/`unverifiable`) — drift affects freshness, not
category ownership; a missing or malformed pin is not authoritative and the
portable checks run normally. See the `domi-consumer` skill, which owns
`.domi-pin` detection and the drift vocabulary; this contract only reuses
its authority signal, it does not reimplement it.

## The helper contract

`skills/package-release-integrity/scripts/release_integrity.py` is stdlib-only
Python (`tomllib`, `re`, `subprocess`) with one verb:

```
release_integrity.py check --repo PATH
    [--tag TAG] [--prev-version X.Y.Z]
    [--change-class breaking|additive|patch|data-only]
    [--build-cmd CMD] [--test-cmd CMD]
    [--json] [--no-changelog-required]
```

- `--repo` — path to the target repo (default `.`).
- `--tag` — the proposed or existing release tag, compared against the
  resolved package version (check 4).
- `--prev-version` — the previously released version, needed to compute
  movement (check 2).
- `--change-class` — the declared class; omitted means checks 1, 2, and 8
  report `uncertain` rather than guess.
- `--build-cmd` / `--test-cmd` — the repo's own commands for checks 6 and 7;
  each is shelled out with a 600s timeout.
- `--no-changelog-required` — downgrades a missing changelog section from
  `fail` to `uncertain` (check 5).
- `--json` — emit the full report as JSON instead of the human-readable
  lines.

Every verdict is one of `pass`, `fail`, or `uncertain` — never anything else,
and `uncertain` is a first-class result, not an error. The report's `ready`
field is `all(verdict != "fail" for verdict in verdicts)` — see Boundaries
for what that does and doesn't promise. When the defer path fires, the
report's `mode` is `"defer"`, `verdicts` is empty, and `ready` is `None`.

**Exit codes:** the process exits non-zero **only** when at least one verdict
is `fail`. `uncertain` never fails the process — it is a "a human must
decide" signal, not an error. A deferral (`mode: "defer"`) also exits `0`;
deferring to DomI is not a failure.

## Three worked examples

### 1. Clean post-1.0 additive release

`pyproject.toml [project].version` and a matching `pkg/__init__.py
__version__` both say `2.3.0`; `--tag v2.3.0`; `--prev-version 2.2.0`;
`--change-class additive`; `CHANGELOG.md` has a `[2.3.0]` section;
`--build-cmd` and `--test-cmd` both exit 0. Verdicts:
`version_source_consistency: pass`, `tag_consistency: pass`,
`changelog_present: pass`, `change_classification: pass`
(declared additive), `version_movement: pass` (post-1.0 additive requires a
minor bump; `2.2.0 -> 2.3.0` is exactly that), `track_routing: uncertain`
(only auto-checked for `data-only` changes — this one is `additive`, so it's
not this check's job), `build_gate: pass`, `verification_gate: pass`.
`ready: True`. Note that one verdict (`track_routing`) is `uncertain` even
in this "everything's fine" example — see Boundaries on what `ready: True`
does and doesn't mean.

### 2. A data-only change that wrongly moved the version

`--change-class data-only`; `--prev-version 1.4.0`; the resolved package
version is `1.4.1` — someone bumped the patch version for what should have
been a version-unmoved data update. `version_movement: uncertain` (movement
for `data-only` is routed to check 8, not checked here directly).
`track_routing: fail` — `"data-only change moved the package version"`,
because the class is `data-only` and the version did move. `ready: False`,
and the process exits non-zero.

### 3. A repo with a valid `.domi-pin`

The target repo's root has a `.domi-pin` with `upstream` set and a 40-hex
`sha`. `detect_domi_authority()` returns `True` regardless of whether that
pin is `current`, `behind`, or `forked` — well-formedness, not freshness, is
what matters here. The report is `{"mode": "defer", "verdicts": [],
"ready": None}`; the human-readable output reads "DomI authoritative — run
DomI's release-integrity; Bindle's checks are advisory-only here and do not
replace it." The process exits `0` — deferring is not a failure.

## Boundaries

- **Never bumps a version, tags a release, or publishes anything.** The
  helper only reads and reports; every mutation stays with the repo's own
  release tooling.
- **A green check is not authorization to publish.** `ready: True` is a
  necessary signal, never a sufficient one — a human still decides whether
  to cut the release.
- **`ready: True` does not mean "all checks ran and passed."** Because
  `ready = all(verdict != "fail" for verdict in verdicts)`, a repo can
  report `ready: True` while a gate is `uncertain` — no `--test-cmd` was
  supplied, `--build-cmd` pointed at a broken command, or the change
  classification was never declared. `uncertain` is silent by design (it
  never fails the process) but it is not the same claim as "this gate ran
  and came back clean." Worked example 1 above shows this even in the
  "everything's fine" case: `track_routing` reports `uncertain`, not
  `pass`, and `ready` is still `True`. Treat an `uncertain` gate as "still
  needs a human," not as a pass in disguise.
- **Repo-local policy and inherited DomI policy win over generic Bindle
  defaults.** The defer rule above is the concrete instance of this: a
  well-formed `.domi-pin` makes this contract advisory-only, never
  authoritative, in that repo.
- **Network or tool failure degrades to `uncertain`, never to a false
  `pass` or a false `ready`.** An unrunnable `--build-cmd`/`--test-cmd`
  (missing binary, shell exit 126/127, a `subprocess` exception) reports
  `uncertain` with the failure detail attached — it is never silently
  treated as having passed.
- **Out of scope:** publishing to any registry or deploy target;
  automatically deciding whether a nuanced API change is breaking; replacing
  a repo's own release scripts; signing or provenance attestations.

## Where this fits

- `docs/release-manifest.md` (#33) is a distinct, narrower concern: it
  records what a *Bindle* release itself shipped
  (`RELEASE-MANIFEST.json`), after the fact. This contract instead checks
  whether *any* Python package release — Bindle's own or a downstream
  repo's — is internally consistent *before* it ships. Neither restates the
  other.
- The `domi-consumer` skill (`docs/domi-consumer.md`) owns `.domi-pin`
  detection, the drift vocabulary, and the inherited-policy category table
  this contract's defer rule reads from. This contract reuses that
  authority signal; it does not reimplement it.
- `skills/package-release-integrity/` is the Claude-native automation
  wrapping the helper described above; Codex or a human follows this
  contract directly against the same `release_integrity.py` script.
