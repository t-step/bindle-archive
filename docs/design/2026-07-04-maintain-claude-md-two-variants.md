# Design: `maintain-claude-md` — two honest variants (claude-kit + DomI)

**Date:** 2026-07-04 · **Status:** Approved design, pre-implementation
**Targets:** `thomas-estep/claude-kit` (generic) + `DomI` (governance ecosystem)
**Source (archived draft):** `~/Developer/Valence-archive/.claude/skills/maintain-claude-md/SKILL.md` (v0.1-draft)

## Problem

`maintain-claude-md` scaffolds, updates, and lints `CLAUDE.md` — the file Claude Code
reads at every session start. A v0.1 draft exists but is unshipped and has real gaps:
its lint **executes** scaffolded commands (unsafe), it can't see monorepo/nested
`CLAUDE.md` layouts, and — the failure that motivated this work — it does **not**
detect a loader-stub `CLAUDE.md` whose `@`-include points at a missing file. That exact
bug once left a repo (Valence) with a root `CLAUDE.md` that loaded nothing.

We want to (a) improve the core skill and (b) contribute it to two toolkits that each
have their own norms and anti-vendoring rules.

## Anti-duplication verdict (verified against DomI HEAD, 2026-07-04)

No live DomI skill scaffolds, lints, or maintains `CLAUDE.md`. `maintain-claude-md`
fills an empty niche that DomI's own tooling already reserves for it. Three
**complementary** hooks must be respected, not broken:

1. **`introspect`** (`skills/introspect/SKILL.md:129`) promotes a lesson seen in 3+
   corpus entries *into* `CLAUDE.md` via `maintain-claude-md`. introspect is the
   upstream feeder; our **update mode** is the receiving end. → update-mode's
   lesson-append format must accept what introspect emits.
2. **`speckit-plan`** (`skills/speckit-plan/SKILL.md:147`) edits the
   `<!-- SPECKIT START/END -->` markers in `CLAUDE.md`. → our init scaffolds that
   block; update/lint must preserve its exact marker format byte-for-byte.
3. **`sync-from-domi`** devendor audit already hard-codes `maintain-claude-md` as
   **DomI-owned** and flags any consumer that vendors it (#330). → the DomI copy lives
   in DomI's `skills/`, never vendored into a consumer repo.

Adjacent but non-overlapping: `write-readme` (README), `skill-creator`/`skill-review`
(skill authoring), `speckit-constitution` (constitution).

## Architecture — two independent variants, one conceptual core

The init/update/lint mode-bodies are shared prose. Two separate `SKILL.md` files diverge
only in frontmatter and governance framing. No sync machinery, no vendoring (both repos
forbid it). They are honestly different artifacts for different audiences.

| | **claude-kit variant** | **DomI variant** |
|---|---|---|
| Path | `skills/maintain-claude-md/SKILL.md` | `skills/maintain-claude-md/SKILL.md` |
| Frontmatter | plain `name` + `description` (starts "Use when…", 3rd person) | + `version:`, `benchmark:`; MANIFEST block; version-history line |
| Governance lint (#4) | **softens** → "link your constitution, don't copy" | **enforces** → link `speckit-constitution` output; fail on copied governance |
| Section shape | template: Overview / When to Use (+ NOT) / Quick Reference / Implementation / Common Mistakes | Article VIII: single-line trigger `description`; When to Use / When NOT (≥2) / Hard Stops (exact abort msgs) / Limitations / Version History |
| Status | **draft** (marked in CHANGELOG) + 1 documented RED baseline | Article VIII-compliant + `tests/benchmark.md` row |
| Companion files | — | `tests/benchmark.md` |

**Why two variants, not one shared source:** the governance-lint behavior genuinely
differs (enforce vs soften), so a single artifact would have to be conditional. Two
honest files is more truthful and matches each repo's philosophy — claude-kit = "my
portable personal layer, no ecosystem coupling"; DomI = "governance source of truth."

## The improved core (all six, shared by both variants)

1. **Loader-stub / include integrity lint (flagship).** Lint resolves every `@include`
   and every markdown/doc-router link target; **FAIL** (not warn) when a loader-stub
   `CLAUDE.md` points at a missing file. Dogfood target: Valence's own root
   `CLAUDE.md` = `@.claude/CLAUDE.md` stub.
5. **Monorepo / nested support.** Recognize + scaffold the root-loader-stub +
   `apps/*/CLAUDE.md` include pattern; lint walks the whole tree, not just the root file.
6. **Static command checks only.** For `## Commands`, verify binary-on-PATH and
   referenced-file-exists **statically**; never execute a scaffolded command. (Replaces
   the source's "run each command snippet in a dry-run.")
4. **Defer-don't-duplicate lint.** Flag `CLAUDE.md` prose that restates governance
   (SemVer / branch policy / release process) that belongs in a linked constitution.
   This is the divergence point: DomI variant enforces (link `speckit-constitution`),
   generic variant softens to "link, don't copy."
2. **Anti-bloat.** Byte-budget lint check on the "hot core"; update-mode gains a
   "graduate stale lessons / session-history → `docs/`" action so the append-only
   sections don't grow unbounded.
3. **Rule rationale.** Encode "each hard rule names its why"; the init interview asks
   for the rationale behind each hard rule, and lint warns on unexplained hard rules.

**Preserve interaction points:** keep the `<!-- SPECKIT START/END -->` marker format
byte-aligned with `speckit-plan`; keep update-mode's lesson format compatible with
`introspect` promotion.

## DomI governance changes

- **Amend spec 001 (`specs/001-maintain-skills/spec.md`).** Descope skill 2 entirely:
  mark `maintain-env-instructions` **Superseded** — it targets the retired
  `CLAUDE_INSTRUCTIONS` / `instructions.sh` mechanism; the live path is
  `scripts/instructions_on_start.sh` + the `act-autonomously` / `bootstrap-vm` skills.
  Retitle 001 to the single remaining skill; drop US2/US4/FR-011–020 and skill-2
  entities/criteria, or move them under an explicit "Superseded — not implemented" note.
- **MANIFEST (`MANIFEST.md`).** Once `skills/maintain-claude-md/SKILL.md` lands in DomI,
  flip the entry from the `v0.1-draft` placeholder ("will be added to this repo in spec
  001") to a real registered skill entry with the shipped version + benchmark row.

## Phasing (feeds the implementation plan)

- **Phase A — core authoring.** Write the improved mode-bodies once; produce both
  variants' `SKILL.md`. Includes the one RED baseline write-up for the loader-stub fix.
- **Phase B — claude-kit.** On `feature/maintain-claude-md-skill`: add
  `skills/maintain-claude-md/SKILL.md`, update `CHANGELOG.md [Unreleased]` (minor bump,
  marked draft), run `make check` / `bin/check.sh`. No push.
- **Phase C — DomI.** On a `feature/` branch: add `skills/maintain-claude-md/SKILL.md`
  + `tests/benchmark.md`, amend spec 001, update MANIFEST, run DomI's skill checks. No
  push.

## Constraints / decisions

- **No push, no PR-merge this session** — operator handles pushes/deploys.
- **claude-kit branch discipline:** never commit to `main`; `make check` must pass; never
  `--no-verify`. (Enforced by a `no-commit-to-branch` hook + `bin/check.sh` name match.)
- **claude-kit TDD:** ship as an explicitly-marked **draft** (CONTRIBUTING sanctions
  this) with one documented RED baseline for the loader-stub fix; the full multi-subagent
  pressure loop is deferred follow-up.
- **Benchmark metric (DomI variant):** the metric the skill improves, e.g.
  `claude-md-loader-stub-breaks-per-repo` (a broken loader-stub reaching a session).

## Out of scope

- `maintain-env-instructions` — dropped completely.
- Any cross-toolkit sync/vendor mechanism (rejected: both repos forbid vendoring).
- Running the full RED→GREEN→REFACTOR pressure loop with subagents (deferred).
- Pushing branches, opening PRs, or merging.
