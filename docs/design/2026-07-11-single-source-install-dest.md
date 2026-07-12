# Design: single-source the type→install-destination mapping

**Date:** 2026-07-11 · **Status:** Approved design, pre-implementation
**Issue:** [thomas-estep/bindle#79](https://github.com/thomas-estep/bindle/issues/79)
**Target:** `thomas-estep/bindle` (repo-local tooling; not installed into `~/.claude/`)
**Follows:** [#29 capability inventory](2026-07-11-capability-inventory.md) (§ Follow-ups 2)

## Problem

The rule that maps a capability's **type** to where it installs is currently
re-encoded in **three** places:

- `install.sh` — `install_claude()` / `install_codex()` (the linking loops), and
- `install.sh` — `each_expected_item()` (the read-only enumerator behind `--adopt`), and
- `doctor.sh` — `claude_section()` / `codex_section()` (the diagnostic enumerators).

Each site independently hard-codes the same facts: which repo directories hold
installable items (`skills/*/`, `agents/*.md`, `commands/*.md`, `global/CLAUDE.md`,
`global/AGENTS.md`), the `_*`/`.` skip rule, the `SKILL.md`-presence gate, and the
`type → destination-subpath` shape. `install.sh:201-208` already documents this
duplication and explains why the earlier author left it in place (byte-identical
output was the binding constraint). #29 shipped `capabilities.json`, which now
records each capability's `type` and `path` — so the mapping can be single-sourced.

### What is *not* the problem

Adding a new **item** of an existing type already requires **no installer edit** —
both scripts auto-discover items by globbing the repo. So #79's literal framing
("consume the inventory so adding a capability edits only the JSON") is already
satisfied for items. The real duplication is the **per-type mapping + enumeration
skeleton**, replicated 3×. Adding a new *type*, or changing a destination shape,
means editing all three sites in lockstep. That is what this design removes.

### The `install_destination` field

`capabilities.json`'s optional `install_destination` annotation is populated on
**zero** rows and is not CI-validated (see the caveat added in #29). This design
makes the destination **derived from type**, so the field stays an optional
per-row *override* rather than a required annotation — see Decision 4.

## Locked decisions (from brainstorming)

1. **Keep install.sh / doctor.sh dependency-free at runtime.** The headline
   good-citizen install story is "just bash, just symlinks." Neither script may
   gain a hard runtime dependency on `python3` or `jq`. This rules out having the
   scripts parse `capabilities.json` directly.

2. **`capabilities.json` is the only hand-edited source; a committed TSV manifest
   is the runtime projection.** `bin/check-inventory.py` **generates** a
   deterministic, Bash-readable manifest from the inventory. The manifest is
   committed to git and consumed by the scripts, so install/doctor need neither
   `python3` nor `jq` to run — only to *regenerate* the manifest, which is a
   developer/CI action, not an install-time one.

3. **CI fails on manifest drift.** The existing `check-inventory.py` run (already
   wired into `make check`) regenerates the manifest in memory and errors if the
   committed file differs. A stale manifest is a red build. This is what makes the
   inventory *load-bearing* for install without parsing JSON in bash.

4. **Destination is derived from type; `install_destination` is an optional
   override.** The generator computes the default destination-subpath from a row's
   type. If a row ever sets an explicit `install_destination`, the generator emits
   it verbatim and the validator checks its source exists. No row sets it today, so
   this path is latent — it satisfies #79's "wire `install_destination` into the
   path checks" without inventing usage.

5. **TSV data, not generated shell.** The manifest is inert tab-separated data read
   by a shared bash reader — never generated executable `.sh` code.

## Architecture

Four units, each independently understandable and testable.

### 1. `install-manifest.tsv` (generated, committed, repo root)

One row per **installable** item. Installable types are `skill`, `agent`,
`command`, and `global-guidance`; `script` and `contract` are never installed and
are excluded. Columns (tab-separated):

```
provider    category          name          src_rel                dest_rel
claude      skill             fork-pr-flow  skills/fork-pr-flow    skills/fork-pr-flow
claude      agent             <name>        agents/<name>.md       agents/<name>.md
claude      command           <name>        commands/<name>.md     commands/<name>.md
claude      global-guidance   claude        global/CLAUDE.md       CLAUDE.md
codex       global-guidance   agents        global/AGENTS.md       AGENTS.md
```

- `provider ∈ {claude, codex}` — selects the runtime home (`$CLAUDE_HOME` /
  `$CODEX_HOME`), so the manifest holds only **relative** paths. `--home` /
  `--codex-home` overrides and the good-citizen model are unchanged.
- `src_rel` is relative to `REPO_ROOT`; `dest_rel` is relative to the provider home.
- First line is a `#`-prefixed banner: `# GENERATED from capabilities.json — do
  not edit; run 'make manifest'`. The bash reader skips `#` lines.
- Rows are emitted in a fixed, stable order: grouped by provider then category
  (skills → agents → commands → global-guidance), items sorted by name — matching
  today's glob order so consumers reproduce existing output.

### 2. `bin/check-inventory.py --emit-manifest` (generator + drift guard)

- `--emit-manifest` writes `install-manifest.tsv` (or prints to stdout with
  `--emit-manifest -`). Projection reuses the exact skip/presence rules the
  existing bijection already applies, so generation and validation agree by
  construction.
- The **default** (no-arg) validation run gains a drift check: regenerate the
  manifest text in memory, compare to the committed file, and on mismatch emit
  `install-manifest.tsv: stale — run 'make manifest'` and exit 1. Runs inside
  `make check`.
- Stdlib-only; no new dependencies (consistent with #29).

### 3. `bin/lib/manifest.sh` (shared bash reader)

- Exposes `each_manifest_item CALLBACK` (and the manifest path), invoking
  `CALLBACK provider category name src_abs dest_rel` per data row, in file order.
  Skips `#`/blank lines. `src_abs` is composed as `$REPO_ROOT/$src_rel`.
- Sourced by both `install.sh` and `doctor.sh`. Replaces all three duplicated
  enumerators. Grouped iteration (header + `mkdir` + link-loop + `--prune` sweep
  per category, in the fixed order above) reproduces today's behavior.
- This is a new `bin/*.sh` file, so it MUST be added to `capabilities.json`'s
  `not_a_capability` ledger as machinery (peer to `check.sh`/`install.sh`) or
  `make check` fails the fuzzy-classification gate (the #29 footgun).

### 4. `bin/new.sh` (regenerate on scaffold)

After `new.sh` appends its draft `capabilities.json` row, it calls
`check-inventory.py --emit-manifest` so a freshly scaffolded item lands in the
manifest in the same step — keeping "edit only capabilities.json" true end to end.

## Data flow

```
capabilities.json  ──(check-inventory.py --emit-manifest)──▶  install-manifest.tsv
        │                                                            │
        │  (make check: regenerate + diff → drift guard)             │ (source)
        ▼                                                            ▼
   [red build on drift]                             bin/lib/manifest.sh
                                                      │ each_manifest_item
                                          ┌───────────┴───────────┐
                                      install.sh               doctor.sh
```

## Byte-identical output (the binding constraint)

`install.sh:201-208` kept the duplication specifically to preserve byte-identical
output when `--adopt` is not passed; the install/doctor test suites assert on that
output. This design preserves it: the manifest's fixed grouping and ordering
reproduce the current headers, `mkdir` calls, link lines, and `--prune` sweeps.
Verification is behavioral, not by inspection — the existing `make test` install
and doctor suites must pass unchanged. Any diff in their expected output is a
regression to fix in the reader, not to bless in the fixtures.

## Testing

- **Generator/drift** (`bin/test-check-inventory.sh`): `--emit-manifest` output is
  deterministic; the committed manifest matches a fresh regeneration; a mutated
  manifest trips the drift guard (exit 1); an explicit `install_destination`
  override is emitted verbatim.
- **Install/doctor** (existing suites): pass unchanged, proving byte-identical
  output through the shared reader — the primary safety net.
- **Reader** (`bin/lib/manifest.sh`): `#`/blank lines skipped; `src_abs`
  composition; callback arity and ordering.

## Scope

**In:** the manifest + generator + drift guard + shared reader; rewiring
`install.sh` (both linking and `--adopt` enumeration) and `doctor.sh` onto the
reader; `bin/new.sh` regen; the `not_a_capability` ledger entry; a `make manifest`
target.

**Out:** generating README / provider-interop tables (#78); installing Codex
skills (#57 — the manifest today emits only `global/AGENTS.md` for Codex, matching
current behavior); hardening `bin/*.py` classification and inter-release
`version_introduced` (#77, the sibling chore). No `SKILL.md` frontmatter changes
(Phase-1 rule).

## Acceptance

- Adding or renaming a capability requires editing only `capabilities.json` (plus
  the item itself); `install-manifest.tsv` regenerates and both scripts pick it up.
- `make check` fails when the committed manifest is stale.
- `make test` install/doctor suites stay green with identical output.
- The `type → destination` rule exists in exactly one place (the generator);
  `install.sh` and `doctor.sh` no longer encode it.
