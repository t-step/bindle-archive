# Design: install compatible shared Agent Skills for Codex

**Date:** 2026-07-12 · **Status:** Approved design, pre-implementation
**Issue:** [thomas-estep/bindle#57](https://github.com/thomas-estep/bindle/issues/57)
**Target:** `thomas-estep/bindle` (installer + doctor tooling; not installed into `~/.claude/`)
**Depends on:** [#56 Codex capability re-baseline](../provider-interop.md#codex-capability-re-baseline-2026-07-11) (closed) · [#61 skill portability audit](../skill-portability-audit.md) (closed)
**Parent:** #55 (broader Codex-interop reconciliation; out of scope here)

## Problem

`bin/install.sh --provider codex` installs only `global/AGENTS.md`. Bindle
ships eight authored skills under `skills/`, two of which — `verify-then-commit`
and `fork-pr-flow` — the #61 audit classified as **shared unchanged**: 100%
provider-neutral prose, no scripts, strongest behavioral evidence on Claude,
and already confirmed discoverable by a real Codex session via a repo-scope
`.agents/skills` symlink. Codex users get none of that today; they follow the
workflow manually or not at all.

The installer must not blindly expose every Claude-oriented skill to Codex —
`maintain-claude-md` manages Claude's own memory-file format, and
`session-continuity`/`hands-on-keyboard` are deliberately Claude-native by
design (#71). Eligibility must come from explicit, per-skill metadata, not a
directory sweep.

### What is *not* the problem

Adding a *new* Codex-eligible skill after this ships requires no installer
code change — just flipping one field in `capabilities.json` (see Decision
1). The real work here is building that mechanism once, correctly, plus the
installer/doctor plumbing for the new destination.

## Locked decisions (from brainstorming)

1. **Eligibility is a `capabilities.json` field, not a new one.** Every
   skill's `provider.codex` value is currently `"manual"` or `"unsupported"`.
   `"installed"` is already a valid `PROVIDER_STATUS` enum value
   (`bin/check-inventory.py`), unused by any skill today. This design treats
   `provider.codex == "installed"` on a `type: skill` row as "symlink this
   skill for Codex too." No schema change. Wave 1 flips exactly two rows:
   `verify-then-commit`, `fork-pr-flow`. Future waves are a one-line diff.

2. **The Codex Agent Skills home is a *third* home, not `--codex-home`.**
   `--codex-home` names Codex's *configuration* home (`AGENTS.md` target,
   e.g. `~/.codex`). The officially documented Agent Skills discovery root
   (re-verified by #56) is `$HOME/.agents/skills` — a different location the
   audit explicitly warns not to conflate with `~/.codex`. A new
   `--agents-skills-home DIR` flag names it, required only when the selected
   `--provider` includes `codex` **and** the manifest actually contains a
   `codex`/`skill` row — so an AGENTS.md-only Codex install
   (`--provider codex --codex-home X`) keeps working with no new flag if a
   future edit ever drops all Codex-eligible skills back to zero.

3. **Reuse the existing manifest/symlink/prune/adopt machinery wholesale.**
   #79's `install-manifest.tsv` + `bin/lib/manifest.sh` already generalized
   `type → destination` into generated, provider/category-tagged rows.
   Codex skills are new *rows*, not a new code path — `link_item`,
   `prune_dir`, and the `--adopt` heuristic all already operate generically
   on `(provider, category, src, dest)`. The only production-code change is
   making home resolution category-aware (today it is a flat
   `provider → home` map in two places) and adding one directory group.

4. **Whole-directory symlink, unchanged.** Same "good citizen" guarantee as
   every existing install target: never overwrite a real file or a
   foreign-owned symlink; only ever create/update/remove symlinks this repo
   owns. `PRESSURE-TESTS.md` and other support files ride along for free
   (tested by the audit through a fixture symlink).

5. **Verify with a real Codex session, not just fixtures.** codex-cli
   0.143.0 is available in this environment — the same tool the #61 audit
   used for its read-only discovery probe. Fixture-based `bin/test-install.sh`
   assertions prove the installer is correct; they do not prove Codex
   actually discovers or follows an installed skill (audit's U1/U2). This
   design's testing section includes a live probe as part of implementation
   verification, run once fixture tests are green.

## Architecture

### 1. `capabilities.json` (hand-edited)

`verify-then-commit` and `fork-pr-flow`: `provider.codex` changes from
`"manual"` to `"installed"`. No other field changes (path, maturity,
mutation, version_introduced all already correct — these are pre-existing
capabilities, not new ones, so no `docs/skill-portability-audit.md` row is
needed and the #29 three-places footgun doesn't apply here).

### 2. `bin/check-inventory.py` — manifest generator

`_install_row(cap)` (returns 0 or 1 row) becomes `_install_rows(cap)`
(returns a list). Behavior:

- `global-guidance` rows: unchanged (still exactly one row, provider from
  `_GG_PROVIDER`).
- Non-`global-guidance` installable rows: unchanged Claude row is always
  emitted first (`provider="claude"`, `dest_rel` = override or `src_rel`).
- **New:** if `type == "skill"` and `provider.codex == "installed"`, also
  emit `("codex", "skill", name, src_rel, name)` — note `dest_rel` is the
  **bare skill name**, not `src_rel` (`"skills/<name>"`). This differs from
  every other row's convention (`dest_rel` relative to a *category* home
  like `$CLAUDE_HOME`) because `$AGENTS_SKILLS_HOME` **is** the skills root
  itself (`~/.agents/skills/<name>`, not `~/.agents/skills/skills/<name>`).

`build_manifest()` flat-maps `_install_rows` over all capabilities instead of
filtering `_install_row`. Sort key (`provider`, `category`, `name`) is
unchanged; `_PROVIDER_RANK`/`_CATEGORY_RANK` already cover `codex`/`skill`.

Resulting new rows in `install-manifest.tsv` (regenerated via `make
manifest`, committed):

```
codex	skill	fork-pr-flow	skills/fork-pr-flow	fork-pr-flow
codex	skill	verify-then-commit	skills/verify-then-commit	verify-then-commit
```

`bin/lib/manifest.sh`'s `each_manifest_item` reader needs no change — it
already passes `(provider, category, name, src_abs, dest_rel)` generically.

### 3. `bin/install.sh`

- New var `AGENTS_SKILLS_HOME=""` and `--agents-skills-home DIR` flag,
  parsed alongside `--codex-home`.
- New helper `codex_skill_rows_present()`: one pass over
  `each_manifest_item` checking for any `provider=codex category=skill`
  row. (Today always true; kept as a real check, not a hardcoded assumption,
  per Decision 1.)
- Validation block (next to the existing `--codex-home` requirement):
  ```
  case "$PROVIDER" in
    codex | all)
      if codex_skill_rows_present && [ -z "$AGENTS_SKILLS_HOME" ]; then
        echo "Codex skill install requires an explicit target: --agents-skills-home DIR" >&2
        echo "Example: bin/install.sh --provider codex --agents-skills-home ~/.agents/skills" >&2
        exit 2
      fi
      ;;
  esac
  ```
  followed by the same `mkdir -p` + `cd ... && pwd` absolute-path resolution
  pattern already used for `CLAUDE_HOME`/`CODEX_HOME`, but only when
  `AGENTS_SKILLS_HOME` is non-empty.
- **Category-aware home resolution.** Both `_each_expected_cb` (the
  `--adopt` prepass enumerator) and `_link_in_group` (the main linking pass)
  currently do:
  ```
  case "$provider" in claude) home="$CLAUDE_HOME" ;; codex) home="$CODEX_HOME" ;; esac
  ```
  This becomes a shared inline helper (or a small `_resolve_home provider
  category` function used at both call sites):
  ```
  case "$provider" in
    claude) home="$CLAUDE_HOME" ;;
    codex)
      case "$category" in
        skill) home="$AGENTS_SKILLS_HOME" ;;
        *) home="$CODEX_HOME" ;;
      esac
      ;;
  esac
  ```
  This is the one behavioral fix that makes `--adopt` and `--prune` work for
  Codex skills automatically — no separate adoption/prune code path.
- `install_surfaces()`: add a Codex skills directory group, guarded so it's
  a no-op when there are no eligible rows:
  ```
  codex | all)
    if codex_skill_rows_present; then
      _dir_group codex skill "Codex skills:" "$AGENTS_SKILLS_HOME" ""
    fi
    _file_group codex "Codex global instructions:" "$CODEX_HOME/AGENTS.md"
    ;;
  ```
  `_dir_group`'s `mkdir -p "$home/$subdir"` needs a small tweak to handle an
  empty `subdir` (target = `$home` itself, no trailing `/`) since
  `$AGENTS_SKILLS_HOME` has no further subdirectory the way
  `$CLAUDE_HOME/skills` does.

### 4. `bin/doctor.sh`

- New `--agents-skills-home DIR` flag (`HAVE_AGENTS_SKILLS_HOME` bool,
  mirroring `HAVE_CODEX`).
- `codex_section()` currently mixes all `provider=codex` rows into one
  block under `$CODEX_HOME`. Split so `global-guidance` stays there and a
  new `codex_skills_section()` reports `skill` rows under
  `$AGENTS_SKILLS_HOME`, gated on `$HAVE_AGENTS_SKILLS_HOME` — same
  `check_item` diagnostic (linked / current / conflict / broken /
  earlier-checkout) already used everywhere else.

### 5. Docs

- `README.md`'s generated Codex block (`DOC_ROWS_CODEX` in
  `bin/check-inventory.py`, `#78` infra) gains a templated row, matching the
  Claude block's `<name>` pattern rather than enumerating actual skills:
  ```python
  {"type": "skill", "src": "skills/<name>/",
   "dest": "<explicit-agents-skills-home>/<name>", "label": "Codex skills (eligible only)"}
  ```
  Regenerated via `make docs`; no hand-maintained skill list.
- `docs/provider-interop.md`'s hand-written Codex capability-matrix row for
  Skills (currently: "Bindle does not install to that path today; no
  adapter exists yet (tracked in #57)") gets updated to state what's
  actually installed, with real command examples.
- `docs/using-bindle-with-codex.md` gets an "Install eligible skills"
  subsection alongside the existing "Install the global guidance" one, and
  its "What Codex must not assume" list is corrected — Claude skills are no
  longer universally off-limits, only the non-eligible ones.
- `docs/skill-portability-audit.md` is left as-is (explicitly a historical
  audit record; superseded by inventory data only when #29's successor
  work says so, not by this issue).

## Data flow

```
capabilities.json (provider.codex: "installed" on 2 skill rows)
        │  (check-inventory.py --emit-manifest)
        ▼
install-manifest.tsv  (2 new codex/skill rows, dest_rel = bare name)
        │  (bin/lib/manifest.sh: each_manifest_item, unchanged reader)
        ├──────────────┬───────────────────────┐
   install.sh       install.sh --adopt      doctor.sh
   (category-aware home resolution: codex/skill → $AGENTS_SKILLS_HOME)
```

## Error handling

- Missing `--agents-skills-home` when required: usage error, exit 2 (same
  class as the existing missing-`--codex-home` case), with an example
  command in the message.
- Conflicts (a real file or foreign symlink already at
  `$AGENTS_SKILLS_HOME/<name>`): reported and left untouched, same
  `CONFLICT` mechanism as every other install target; nonzero exit unless
  `--allow-conflicts`.
- No network or external calls introduced; `mutation` stays `disk` for the
  two capabilities (no change needed there — codex install is still a local
  symlink operation, matching the existing Claude row's mutation flags).

## Testing

**`bin/test-install.sh`** (new cases, mirroring the existing Claude-skill
and Codex-global-guidance patterns already in the file):

- Codex-eligible skill installs into a temp `--agents-skills-home`
  (`verify-then-commit`, `fork-pr-flow` symlinked; support file
  `PRESSURE-TESTS.md` readable through the symlink).
- Claude-only skill excluded (`maintain-claude-md` not present at the Codex
  skills target — mirrors the existing `not_exists` assertion pattern).
- `--provider all` installs the same source safely to both `$CLAUDE_HOME`
  and `$AGENTS_SKILLS_HOME`.
- Conflict refusal, safe prune, idempotent reinstall — same table-driven
  shape as the existing Codex AGENTS.md cases.
- `--adopt` picks up a broken Codex-skill symlink from a simulated
  earlier-checkout path.
- Missing `--agents-skills-home` errors only when eligible rows exist
  (can't regression-test the zero-eligible-rows branch without a fixture
  manifest, so this is asserted against the real manifest's current state
  plus a comment noting the guard's intent).

**`bin/test-doctor.sh`**: new case asserting the skills section reports
linked/missing/conflict states under `--agents-skills-home`.

**`bin/test-check-inventory.sh`**: `_install_rows` emits both rows for a
skill with `provider.codex: "installed"`, and only the Claude row when
`"manual"`/`"unsupported"`; manifest drift guard still trips on a stale
file.

**Live Codex probe** (manual verification step during implementation, not
committed as an automated test — codex-cli availability is machine-specific):

1. Real install: `bin/install.sh --provider codex --codex-home <tmp>
   --agents-skills-home <tmp>/skills`.
2. Discovery: `codex exec -s read-only` in a scratch fixture repo, asked to
   enumerate available skills — expect both wave-1 skills listed at their
   symlink-resolved paths (repeats the audit's proven method; a `HOME`
   override attempt for genuine *user-scope* discovery, resolving audit
   uncertainty U1, is worth trying first and falling back to the
   proven repo-scope method if it doesn't pan out).
3. Invocation: a scratch fixture repo with a failing test, asked to commit —
   expect `verify-then-commit` to be followed (Codex either runs
   tests/refuses, or visibly reasons about the skill's gate) rather than
   committing straight through. This is real evidence for audit
   uncertainty U2, not a simulation.
4. Record pass/fail plainly; a failure here is a finding to fix (or to
   report honestly as an open uncertainty), not to gloss over.

## Scope

**In:** flipping the two wave-1 `capabilities.json` rows; the manifest
generator change; `install.sh` (`--agents-skills-home`, category-aware home
resolution, new directory group, `--adopt`/`--prune` reuse); `doctor.sh`
(same flag + new section); generated README block; manual doc-prose updates
to `provider-interop.md` and `using-bindle-with-codex.md`; all listed tests;
the live Codex probe as a verification step.

**Out:** wave 2 (`license-compliance-auditor`, `scoped-sequential-prs`,
`repo-hygiene-init`) and the Claude-command-reference cleanups for
`session-continuity`/`hands-on-keyboard` — separate future issues per the
audit's ordering; installing Claude slash commands, agents, or hooks as
Codex equivalents (explicit non-goals in #57); any content rewrite of
`skills/*/SKILL.md` (Phase-1 rule); `$CODEX_HOME/skills` (audit's U8 —
undocumented, not targeted); optional `agents/openai.yaml` metadata (U5,
deferred until a real session shows it's needed).

## Acceptance

- `bin/install.sh --provider codex --codex-home X --agents-skills-home Y`
  symlinks `verify-then-commit` and `fork-pr-flow` (whole directories) into
  `Y`, and nothing else Claude-only leaks in.
- `--provider all`, `--adopt`, `--prune`, and conflict-refusal all behave
  identically in shape to the existing Claude/Codex-AGENTS.md cases, now
  covering the skills target too.
- `bin/doctor.sh --agents-skills-home Y` diagnoses the new destination.
- `make check` and `make test` pass, including the new cases above.
- README and `docs/provider-interop.md` describe the installed Codex
  surfaces honestly (no "not installed today" language left for the two
  eligible skills).
- A real Codex session (live probe) discovers at least one installed skill
  and is observed following it — the issue's own stated acceptance
  criterion, closed with real evidence rather than asserted.
