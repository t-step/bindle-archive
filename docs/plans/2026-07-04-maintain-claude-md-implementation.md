# maintain-claude-md Two-Variant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Improve `maintain-claude-md` (six fixes) and ship it as two honest variants — a portable draft in `thomas-estep/claude-kit` and an Article VIII-compliant skill in `DomI` — while dropping `maintain-env-instructions` and amending DomI spec 001.

**Architecture:** One conceptual core (init/update/lint modes) authored as two independent `SKILL.md` files. They share mode-bodies but diverge in frontmatter and in one lint check (#4 defer-don't-duplicate: claude-kit *warns / softens*, DomI *fails / enforces*). No sync machinery, no vendoring — both repos forbid it. Design: `claude-kit/docs/design/2026-07-04-maintain-claude-md-two-variants.md`.

**Tech Stack:** Markdown skills for Claude Code. claude-kit uses `bin/new.sh`, `bin/check.sh`, `make check`, pre-commit hooks. DomI uses Article VIII skill shape + `tests/benchmark.md` + `MANIFEST.md`.

## Global Constraints

- **No push, no PR-merge this session.** Every phase stops at a committed local feature branch. Operator handles pushes/deploys.
- **claude-kit branch discipline:** never commit to `main`; work on `feature/maintain-claude-md-skill` (already created); `make check` must pass; never `--no-verify`. `bin/check.sh` requires the skill's `name:` frontmatter to equal its folder name.
- **claude-kit description rule:** `description:` starts with "Use when…", third person, describes *when* to use, not a workflow summary.
- **DomI branch discipline:** never commit to `main`; work on a fresh `feature/` branch off `main`.
- **DomI Article VIII (verbatim from `specs/domi-constitution.md:175-181`):** YAML frontmatter `name:`, `version:`, `description:` (single-line, trigger-optimized), `benchmark:`; **Hard Stops** table with exact abort messages; **Version History** with dated entries; a `tests/benchmark.md` row per version; `MANIFEST.md` updated (version bump, benchmark) in the **same commit** as the skill.
- **Preserve interaction points:** the `<!-- SPECKIT START/END -->` marker format is owned by `speckit-plan` — scaffold/preserve it byte-for-byte; update-mode's lesson-append format must accept what `introspect` promotes.
- **Benchmark metric:** `claude-md-loader-stub-breaks-per-repo` — repos reaching a session with a CLAUDE.md that loads nothing / has a dead `@`-include. Lower is better. Baseline: the Valence incident (root `@.claude/CLAUDE.md` stub whose target was dropped in a rewrite).
- **Source of the mode-body prose:** the archived v0.1 draft at `~/Developer/Valence-archive/.claude/skills/maintain-claude-md/SKILL.md` (base to improve, not re-invent).

## File Structure

**claude-kit** (branch `feature/maintain-claude-md-skill`):
- Create: `skills/maintain-claude-md/SKILL.md` — portable variant.
- Modify: `CHANGELOG.md` — `## [Unreleased] › ### Added` bullet (draft note + RED baseline).
- Done: `docs/design/2026-07-04-maintain-claude-md-two-variants.md`, this plan.

**DomI** (branch `feature/maintain-claude-md`):
- Create: `skills/maintain-claude-md/SKILL.md` — Article VIII variant.
- Create: `skills/maintain-claude-md/tests/benchmark.md` — benchmark row per version.
- Modify: `MANIFEST.md` — replace the `### maintain-claude-md (v0.1-draft)` block with a real v0.2.0 entry.
- Modify: `specs/001-maintain-skills/spec.md` — mark `maintain-env-instructions` Superseded; retitle to the single skill.

---

### Task 1: claude-kit portable variant

**Files:**
- Create: `skills/maintain-claude-md/SKILL.md`
- Modify: `CHANGELOG.md` (`## [Unreleased]` › `### Added`)

**Interfaces:**
- Produces: the canonical mode-body prose (init/update/lint) that Task 2's DomI variant reuses with an Article VIII wrapper and the #4 lint check flipped to FAIL.

- [ ] **Step 1: Scaffold the skill folder**

Run: `cd ~/Developer/claude-kit && bin/new.sh skill maintain-claude-md`
Expected: creates `skills/maintain-claude-md/SKILL.md` from `skills/_template/SKILL.md` with `name: maintain-claude-md` pre-filled.

- [ ] **Step 2: Write the full SKILL.md**

Overwrite `skills/maintain-claude-md/SKILL.md` with exactly:

````markdown
---
name: maintain-claude-md
description: Use when a repo needs its CLAUDE.md created, updated, or checked — scaffolding a new CLAUDE.md from repo introspection, appending a dated lesson or new active-spec note after a session, or linting an existing one for broken @-includes, dead loader-stubs, stale references, unexplained hard rules, duplicated governance, or unsafe command snippets. Also when asked to run /maintain-claude-md in any mode.
---

# maintain-claude-md

## Overview

Manages the lifecycle of `CLAUDE.md` — the operational file Claude Code reads at every
session start. Three modes: **init**, **update**, **lint**. Infer the mode from context;
ask only if ambiguous. Every CLAUDE.md this skill scaffolds carries a `maintained-by`
marker so a future session knows to re-invoke the skill.

## When to Use

- Repo (or a monorepo root / app package) has no CLAUDE.md → **init**.
- A session ended with a lesson, or a new active spec was started → **update**.
- A CLAUDE.md exists and may have drifted — dead includes, stale specs, bloat → **lint**.
- User says "scaffold CLAUDE.md", "add a lesson", "lint CLAUDE.md", or "run /maintain-claude-md".

When NOT to use:
- Hand-editing prose inside an already-correct CLAUDE.md — just edit it.
- Authoring a README or a constitution — CLAUDE.md *links* those; it does not replace them.

## Quick Reference

| Mode | Trigger | Does | Never does |
|------|---------|------|-----------|
| init | no CLAUDE.md | introspect repo → interview ≤5 Qs → scaffold | overwrite an existing CLAUDE.md without asking |
| update | new lesson / spec | append-only to Lessons / Session history / SPECKIT block | rewrite or reorder existing sections |
| lint | validate | static structural + include-integrity report | execute any scaffolded command |

## Mode: init

*When:* repo has no CLAUDE.md, or user says "scaffold" / "reinitialize".

### Step 1 — Introspect the repo

Read (skip if absent, note what's missing):
- `README.md` / `pyproject.toml` / `package.json` — purpose, stack.
- `CONSTITUTION.md` or `.specify/memory/constitution.md` — governing rules.
- `PROJECT_PLAN.md` — roadmap, current phase.
- `.claude/settings.json` — model, permissions.
- `specs/` — active feature branches.

Run `git log --oneline -10` for recent activity.

**Detect monorepo shape:** if `apps/*/` or `packages/*/` exist, this is a nested layout.
The root CLAUDE.md becomes a **loader stub** that `@`-includes a shared core and points at
per-app files; each app dir gets its own focused CLAUDE.md. (See "Monorepo / nested".)

### Step 2 — Interview (only what you can't infer, ≤5 questions)

1. **Mission** — one sentence: what does this repo do?
2. **Workflow type** — how does Claude primarily help? (issue-triage / data-curation / deployment / autonomous-routine / other)
3. **Key commands** — install, test, build, release (if not in README).
4. **External dependencies** — APIs, databases, env vars Claude must know about.
5. **Hard rules — and the *why* behind each.** Do not accept a bare "never force-push";
   capture the reason ("shared branch, rewrites break others' clones"). Every hard rule in
   the scaffold names its rationale, so a future session can tell a real constraint from a
   cargo-culted one.

### Step 3 — Scaffold

Use the canonical structure. Populate from introspection + interview. Leave explicit
`<!-- TODO: fill in -->` markers for anything unprovided — never invent. For governance
that already lives in a constitution (SemVer, branch policy, release process), **link it,
don't copy it** — duplicated governance drifts.

```markdown
# CLAUDE.md

Operational reference for Claude Code sessions on {PROJECT}.

**Read at every session start (in order):** {CONSTITUTION_PATH} → {PROJECT_PLAN_PATH} → CLAUDE.md
If CLAUDE.md contradicts the constitution, the constitution wins.

<!-- maintained-by: maintain-claude-md skill (/maintain-claude-md update to add lessons, lint to validate) -->

## Doc router — for task X, read doc Y
| I need to... | Primary doc | Section |
|---|---|---|
| Mission / hard rules | {CONSTITUTION_PATH} | — |
| Install / test / release | CLAUDE.md | § Commands |
| Architecture | CLAUDE.md | § Architecture |
| A lesson learned | CLAUDE.md | § Lessons learned |
| The active spec | specs/{ACTIVE_SPEC}/ | spec.md / plan.md |

## Project overview
{MISSION_SENTENCE} Stack: {STACK}. Workflow: {WORKFLOW_TYPE}.

## Commands
\`\`\`bash
{INSTALL_CMD}
{TEST_CMD}
{RELEASE_CMD}
\`\`\`

## Architecture
{ASCII_DIAGRAM_OR_FILE_MAP}

## Key patterns
{CODE_IDIOMS}

## Hard rules
<!-- Each rule states its why. -->
- {RULE} — because {WHY}.

## Lessons learned
<!-- Append via /maintain-claude-md update. Format: ### YYYY-MM-DD — topic -->
(No entries yet.)

## Session history
<!-- One-liner per session, newest first. -->
(No entries yet.)
```

If a CLAUDE.md already exists: **STOP**, do not overwrite. Offer review/merge.

### Monorepo / nested layout

Root `CLAUDE.md` (loader stub):
```markdown
# CLAUDE.md
Root memory for {PROJECT} (monorepo). Full core: @.claude/CLAUDE.md
Per-app memory: apps/{APP}/CLAUDE.md — read the one for the app you are in.
```
Each `apps/{APP}/CLAUDE.md` is a focused file for that package. The shared core lives once
at `.claude/CLAUDE.md` and is pulled in by `@`-include. **Never leave a loader stub whose
`@`-include target does not exist** — that CLAUDE.md loads nothing (see lint check below).

## Mode: update

*When:* append a lesson, session summary, or new active spec — without clobbering.

**Lessons learned** — insert *after* the section heading + append-comment, before existing
entries (newest first). Format (matches what `introspect` promotes):
```
### {YYYY-MM-DD} — {topic}
{2–5 specific bullets: what failed, what worked, why it matters.}
```

**Session history:** `- {YYYY-MM-DD}: {one-liner}` (newest first).

**Active spec** — update the `<!-- SPECKIT START/END -->` block only; preserve the marker
lines byte-for-byte (another skill writes here too):
```markdown
<!-- SPECKIT START -->
Active spec: `{SPEC_ID}-{name}` (branch `{SPEC_ID}-{name}`). Context: specs/{SPEC_ID}-{name}/plan.md
<!-- SPECKIT END -->
```

**Rules for safe appends:** never rewrite existing sections; preserve content verbatim
(including typos/formatting); after writing, show the added lines as a brief diff.

**Anti-bloat — graduate stale detail.** CLAUDE.md is a hot core, not an archive. When
`## Lessons learned` or `## Session history` grows past the byte budget (default ~12 KB for
everything above these sections combined, or >20 dated entries), offer to move the oldest
entries to `docs/CLAUDE-history.md`, leaving a one-line pointer. Graduating is append-only
at the destination and deletion-with-pointer at the source; never silently drop content.

## Mode: lint

*When:* validate an existing CLAUDE.md. Run every check; report as a table
**check | status | detail**, then a suggested fix per ❌/⚠️. Lint is **read-only and never
executes a scaffolded command.**

| Check | Status on failure | How (static only) |
|---|---|---|
| Required sections present | ❌ FAIL | `## Doc router`, `## Project overview`, `## Commands`, `## Architecture`, `## Lessons learned`. |
| **Include integrity** | ❌ FAIL | Resolve every `@path` include and every doc-router / skill link target; FAIL on any missing file. A CLAUDE.md that is only a loader stub (an `@`-include + pointer) whose include target is absent = FAIL "loader stub loads nothing". |
| **Nested tree** | ❌ FAIL | If `apps/*/` or `packages/*/` carry their own CLAUDE.md, lint each; a root stub must `@`-include or point to them. FAIL if a referenced app CLAUDE.md is missing. |
| **Command safety** | ⚠️ WARN | For each snippet in `## Commands`: check the binary is on PATH (`command -v`) and any referenced path exists. **Never execute the snippet.** WARN on an unknown binary. |
| Defer-don't-duplicate | ⚠️ WARN | Scan prose for restated governance (SemVer, branch policy, release steps). WARN: "governance restated — link your constitution instead of copying it." |
| Rule rationale | ⚠️ WARN | Every hard rule ("never…", "always…", "MUST…") should be followed by a why. WARN on a bare imperative. |
| Byte budget | ⚠️ WARN | Hot core (everything above `## Lessons learned`) over budget (default 12 KB) → WARN: graduate detail to `docs/`. |
| SPECKIT block accurate | ⚠️ WARN | If `<!-- SPECKIT START/END -->` present, the referenced spec folder must exist. |
| Lessons dated | ⚠️ WARN | Every `###` under `## Lessons learned` starts `### YYYY-MM-DD`. |
| Stale session history | ⚠️ WARN | Entries > 90 days old flagged "review: may be stale". |
| Self-reference marker | ⚠️ WARN | `maintained-by: maintain-claude-md` present in the header/overview. |

Output example:
```
CLAUDE.md lint — {repo} — {date}
❌ FAIL  Include integrity: root CLAUDE.md is a loader stub for `@.claude/CLAUDE.md`, which does not exist — this file loads nothing.
⚠️ WARN  Command safety: `pnpm` not on PATH (checked statically; not executed).
✅ PASS  Required sections: all present.
```

## Implementation

Pure prose + the model's own file tools; no external dependencies beyond `command -v`
for the static command-safety check. All linting is read-only.

## Common Mistakes

- **Running command snippets to "check they work."** Lint is static-only; executing a
  scaffolded `release` command is how you delete a tag by accident.
- **Treating a loader-stub CLAUDE.md as fine because it parses.** A stub whose `@`-include
  target is missing loads *nothing* — that is a FAIL, not a pass.
- **Copying the constitution's SemVer / branch rules into CLAUDE.md.** Link them; duplicated
  governance drifts out of sync.
- **Letting Lessons / Session history grow unbounded.** Graduate stale entries to `docs/`.

<!--
REQUIRED BACKGROUND: superpowers:writing-skills (this skill was authored under it).
Related: a governance-aware variant lives in DomI (Article VIII) that *enforces*
defer-don't-duplicate as a FAIL; this portable variant softens it to a WARN.
-->
````

- [ ] **Step 3: Add the CHANGELOG entry with the RED baseline**

In `CHANGELOG.md`, under `## [Unreleased]` › `### Added`, insert this bullet:

```markdown
- `maintain-claude-md` skill (draft) — scaffold / update / lint `CLAUDE.md`. Lint now
  resolves `@`-includes and FAILs on a loader-stub whose target is missing (the failure
  that once left a repo loading nothing), is monorepo/nested-aware, checks command snippets
  **statically** (never executes them), flags duplicated governance, and byte-budgets the
  hot core. RED baseline: the v0.1 draft's lint PASSes a repo whose root `@.claude/CLAUDE.md`
  stub target is absent (it only checked section presence and *ran* command snippets); this
  version FAILs it. Draft pending the full RED→GREEN→REFACTOR pressure loop (see CONTRIBUTING).
```

- [ ] **Step 4: Run the checks**

Run: `cd ~/Developer/claude-kit && make check`
Expected: PASS, including `claude-kit content (frontmatter/name/links/version)` (name matches folder, description starts "Use when") and `don't commit to branch`.

If `make check` is unavailable, run `bin/check.sh` directly. Fix any reported issue and re-run until green.

- [ ] **Step 5: Commit**

```bash
cd ~/Developer/claude-kit
git add skills/maintain-claude-md/SKILL.md CHANGELOG.md
git commit -m "feat(skill): add maintain-claude-md (draft) — CLAUDE.md scaffold/update/lint

Ships the portable variant: include-integrity lint (FAIL on dead loader-stub),
monorepo/nested support, static-only command checks, defer-don't-duplicate,
anti-bloat byte budget, rule-rationale. Draft pending pressure-test.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01SVBtB45G8AjgW6t6aji2Kr"
```
Expected: pre-commit hooks pass (incl. `don't commit to branch`); commit lands on `feature/maintain-claude-md-skill`.

---

### Task 2: DomI Article VIII variant + benchmark + MANIFEST

**Files:**
- Create: `skills/maintain-claude-md/SKILL.md` (in DomI)
- Create: `skills/maintain-claude-md/tests/benchmark.md` (in DomI)
- Modify: `MANIFEST.md` (in DomI)

**Interfaces:**
- Consumes: the init/update/lint mode-bodies authored in Task 1 (reused verbatim below, with the #4 defer-don't-duplicate check flipped from WARN to FAIL).
- Produces: a registered DomI skill; MANIFEST and benchmark must land in the **same commit** as the SKILL.md (Article VIII).

- [ ] **Step 1: Create the DomI feature branch**

```bash
cd ~/Developer/DomI && git checkout main && git checkout -b feature/maintain-claude-md
```
Expected: `Switched to a new branch 'feature/maintain-claude-md'`.

- [ ] **Step 2: Write the DomI SKILL.md (Article VIII shape)**

Create `~/Developer/DomI/skills/maintain-claude-md/SKILL.md` with exactly:

````markdown
---
name: maintain-claude-md
version: "0.2.0"
benchmark: claude-md-loader-stub-breaks-per-repo
description: Scaffold, update, and lint CLAUDE.md — the file Claude Code reads at session start. init introspects a repo (monorepo/nested-aware) and scaffolds; update appends dated lessons and active-spec notes without clobbering; lint statically validates structure, resolves @-includes and FAILs on a dead loader-stub, checks command snippets without executing them, and enforces defer-don't-duplicate against the constitution. Use at repo setup, after a session that produced a lesson, or to audit an existing CLAUDE.md.
---

# maintain-claude-md

Manages the lifecycle of `CLAUDE.md` — the operational file every session reads at start.
Three modes: **init**, **update**, **lint**.

## Metadata

- **Category**: Project Setup / Documentation Maintenance
- **Use Case**: Scaffold a new repo's CLAUDE.md; append lessons; audit an existing one
- **Dependencies**: None self-contained; `command -v` for static command checks
- **Scope**: One repo tree per invocation (root + nested `apps/*` / `packages/*` CLAUDE.md)

## When to Use

- Repo (or a monorepo root / app package) has no CLAUDE.md → **init**.
- A session ended with a lesson or a newly-started active spec → **update**.
- A CLAUDE.md exists and may have drifted (dead includes, stale specs, bloat) → **lint**.

## When NOT to Use

- Hand-editing prose inside an already-correct CLAUDE.md — just edit it directly.
- Authoring a README (`write-readme`) or a constitution (`speckit-constitution`) —
  CLAUDE.md *links* those; it does not replace them.

## Failure Mode This Solves

A root CLAUDE.md is often a **loader stub** that `@`-includes a shared core. If the include
target is dropped (a rewrite, a bad move), the stub still parses but loads **nothing** — the
session starts with no instructions and no one notices. Lint's include-integrity check turns
that silent failure into a loud FAIL before the session. (Benchmark:
`claude-md-loader-stub-breaks-per-repo`.)

## Mode: init

*When:* repo has no CLAUDE.md, or user says "scaffold" / "reinitialize".

**Introspect:** `README.md` / `pyproject.toml` / `package.json` (purpose, stack);
`.specify/memory/constitution.md` (governing rules); `PROJECT_PLAN.md`; `.claude/settings.json`;
`specs/`; `git log --oneline -10`. **Detect monorepo:** if `apps/*/` or `packages/*/` exist,
the root CLAUDE.md becomes a loader stub `@`-including a shared `.claude/CLAUDE.md` core and
pointing at per-app files.

**Interview (≤5 Qs, only gaps):** mission; workflow type; key commands; external deps; and
**hard rules with the *why* behind each** — capture the rationale, not just the imperative.

**Scaffold** the canonical structure (Doc router / Project overview / Commands / Architecture
/ Key patterns / Hard rules / Lessons learned / Session history), a `maintained-by` marker,
and — for governance already in the constitution — a **link, not a copy**. Leave explicit
`<!-- TODO -->` markers; never invent. If a CLAUDE.md already exists, **STOP** and offer
review/merge (see Hard Stops).

Monorepo root stub:
```markdown
# CLAUDE.md
Root memory for {PROJECT} (monorepo). Full core: @.claude/CLAUDE.md
Per-app memory: apps/{APP}/CLAUDE.md.
```
Never leave a loader stub whose `@`-include target does not exist.

## Mode: update

Append-only. **Lessons learned** (newest first, format matching `introspect` promotion):
```
### {YYYY-MM-DD} — {topic}
{2–5 specific bullets.}
```
**Session history:** `- {YYYY-MM-DD}: {one-liner}`. **Active spec:** edit only inside
`<!-- SPECKIT START/END -->`, preserving the marker lines byte-for-byte (`speckit-plan`
writes here too). Never rewrite existing sections; preserve content verbatim; show a diff of
added lines. **Anti-bloat:** when Lessons / Session history exceed the byte budget (~12 KB
hot core) or >20 entries, offer to graduate the oldest entries to `docs/CLAUDE-history.md`
with a pointer — never silently drop.

## Mode: lint

Read-only; **never executes a scaffolded command.** Report a **check | status | detail**
table + a fix per ❌/⚠️.

| Check | Status | How (static only) |
|---|---|---|
| Required sections present | ❌ FAIL | Doc router, Project overview, Commands, Architecture, Lessons learned. |
| Include integrity | ❌ FAIL | Resolve every `@include` + link target; FAIL on any missing file; FAIL a loader-stub whose `@`-include is absent ("loads nothing"). |
| Nested tree | ❌ FAIL | Lint each `apps/*` / `packages/*` CLAUDE.md; root stub must reference them; FAIL if a referenced file is missing. |
| Command safety | ⚠️ WARN | `command -v` the binary + check referenced paths exist; never execute. |
| **Defer-don't-duplicate** | ❌ **FAIL** | Governance prose (SemVer / branch / release) restated in CLAUDE.md instead of linking `.specify/memory/constitution.md` (speckit-constitution output) → FAIL: "link the constitution, do not copy it." |
| Rule rationale | ⚠️ WARN | Hard rules must name a why; WARN on a bare imperative. |
| Byte budget | ⚠️ WARN | Hot core over 12 KB → graduate detail to `docs/`. |
| SPECKIT block accurate | ⚠️ WARN | Referenced spec folder must exist. |
| Lessons dated / stale history / self-marker | ⚠️ WARN | `### YYYY-MM-DD` dates; entries >90 days flagged; `maintained-by` present. |

## Hard Stops

| Condition | Abort message |
|---|---|
| init finds an existing CLAUDE.md | `STOP: CLAUDE.md already exists — not overwriting. Switch to review/merge or run lint/update instead.` |
| A referenced constitution path cannot be read during init/lint | `STOP: cannot read constitution at {path} — resolve the path before scaffolding governance links.` |
| A command snippet would need execution to validate | `STOP: lint is static-only and will not execute `{cmd}`; validate by inspection.` |

Per DomI Article VII: each hard stop above is a defined failure mode; the skill never
silently succeeds when a stop fires. Modes are idempotent (lint is read-only; update is
append-only with newest-first insertion).

## Limitations

- Include/link resolution is lexical (path existence), not semantic — a resolvable include
  pointing at the *wrong* file passes.
- Governance-duplication detection is keyword-based (SemVer / branch / release terms); novel
  phrasings may slip past as WARN-less.
- Byte budget is a heuristic, not a hard cap; graduating stale detail is offered, not forced.

## Integration

- `introspect` promotes a lesson seen in 3+ corpus entries *into* CLAUDE.md via this skill's
  update mode — keep the lesson format aligned.
- `speckit-plan` writes the `<!-- SPECKIT START/END -->` block — preserve its markers.
- `speckit-constitution` owns governance; this skill links it and FAILs on duplication.

## Version History

- **v0.2.0** (2026-07-04) — First shipped version (supersedes the unshipped v0.1-draft).
  Adds include-integrity lint (FAIL on dead loader-stub), monorepo/nested support,
  static-only command checks, defer-don't-duplicate (enforced as FAIL), anti-bloat byte
  budget + graduate-to-docs, and rule-rationale capture.
````

- [ ] **Step 3: Write the benchmark**

Create `~/Developer/DomI/skills/maintain-claude-md/tests/benchmark.md`:

```markdown
# Benchmark — `maintain-claude-md`

## Metric

`claude-md-loader-stub-breaks-per-repo` — number of repos reaching a session with a
CLAUDE.md that loads nothing (a loader stub whose `@`-include target is absent) or has a
dead doc-router / skill link. Lower is better; floor is 0.

## Measurement protocol

- **Fixture:** the Valence incident — a monorepo whose root `CLAUDE.md` was a loader stub
  (`@.claude/CLAUDE.md`) whose target `.claude/` was dropped in a rewrite, shipping a root
  memory that loaded nothing.
- **Procedure:** run lint against the fixture repo state before and after the drop; count
  loader-stub / dead-include breaks that reach a session (i.e., are not caught pre-session).
- **Sample size:** N=1 documented incident (Valence) + the reconstructed pre-drop state.

## Results

| Version | Date | Metric | Baseline | Observed | Delta | Evidence |
|---|---|---|---|---|---|---|
| v0.2.0 | 2026-07-04 | `claude-md-loader-stub-breaks-per-repo` | 1 (v0.1 draft lint PASSes the dropped-include stub: it checked section presence + ran command snippets, never resolved the `@`-include) | 0 (v0.2 include-integrity check FAILs the stub pre-session) | -1 (-100% on the fixture) | Valence loader-stub incident; design doc `claude-kit/docs/design/2026-07-04-maintain-claude-md-two-variants.md` |

## Not-measured versions

- v0.1-draft — unshipped; never benchmarked (this is the baseline it is measured against).
```

- [ ] **Step 4: Update MANIFEST.md**

In `~/Developer/DomI/MANIFEST.md`, replace the entire `### maintain-claude-md (v0.1-draft)` block (through its `- **Note**:` line) with:

```markdown
### maintain-claude-md (v0.2.0)
- **Purpose**: Scaffold, update, and lint CLAUDE.md files across Claude Code projects
- **Use cases**: Init a new (monorepo/nested-aware) CLAUDE.md; append dated lessons; audit an existing one for dead @-includes, unsafe command snippets, duplicated governance, and bloat
- **Key features**: init (introspect + rationale interview + loader-stub scaffold), update (append-only + graduate-stale-to-docs), lint (include-integrity FAIL on dead loader-stub, static command checks, defer-don't-duplicate enforced, byte budget)
- **Self-aware**: Generated CLAUDE.md files carry a `maintained-by` marker referencing this skill
- **Dependencies**: None self-contained (`command -v` for static command checks)
- **Benchmark**: `claude-md-loader-stub-breaks-per-repo` (v0.2.0: Valence loader-stub fixture, 1 → 0)
- **Source**: Authored in `thomas-estep/claude-kit` (portable variant); this Article VIII variant lands spec 001. Supersedes the v0.1-draft placeholder.
```

- [ ] **Step 5: Validate the DomI skill shape**

Run: `cd ~/Developer/DomI && ls skills/maintain-claude-md/ && grep -c "version:" skills/maintain-claude-md/SKILL.md`
Expected: `SKILL.md  tests/` listed; frontmatter has `version:`, `benchmark:`, `description:`. If DomI has a skill-lint or `bin/check.sh`, run it and fix any issue.

Manually confirm: Hard Stops table present with exact abort messages; Version History dated; benchmark has a v0.2.0 row.

- [ ] **Step 6: Commit (skill + benchmark + MANIFEST together)**

```bash
cd ~/Developer/DomI
git add skills/maintain-claude-md/SKILL.md skills/maintain-claude-md/tests/benchmark.md MANIFEST.md
git commit -m "feat(skill): land maintain-claude-md v0.2.0 (Article VIII) — spec 001

Article VIII variant: include-integrity lint (FAIL on dead loader-stub),
monorepo/nested support, static-only command checks, defer-don't-duplicate
enforced against the constitution, anti-bloat, rule-rationale. MANIFEST +
benchmark land in the same commit per Article VIII.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01SVBtB45G8AjgW6t6aji2Kr"
```
Expected: commit lands on `feature/maintain-claude-md`; pre-commit hooks pass.

---

### Task 3: Amend DomI spec 001 (drop maintain-env-instructions)

**Files:**
- Modify: `~/Developer/DomI/specs/001-maintain-skills/spec.md`

**Interfaces:**
- Consumes: nothing. Independent of Tasks 1-2; can be reviewed/rejected on its own.

- [ ] **Step 1: Retitle and re-status the spec header**

In `specs/001-maintain-skills/spec.md`, replace:
```markdown
# Feature Specification: Reusable Maintenance Skills for Claude Code Projects
```
with:
```markdown
# Feature Specification: Reusable CLAUDE.md Maintenance Skill for Claude Code Projects
```
And replace the `**Status**: Draft` line with:
```markdown
**Status**: In Progress (maintain-claude-md landed v0.2.0; maintain-env-instructions superseded — see note)
```

- [ ] **Step 2: Insert the supersede note**

Immediately after the `**Input**:` line (before `## User Scenarios & Testing`), insert:
```markdown

> **Superseded — `maintain-env-instructions` (Skill 2) is dropped, not implemented.** It
> targeted the retired `CLAUDE_INSTRUCTIONS` / `claude_code_env_instructions.sh` bootstrap
> mechanism. The live path is `scripts/instructions_on_start.sh` + the `act-autonomously`
> and `bootstrap-vm` skills. User Story 2 & 4, FR-011–FR-020, and the Routine / Decision
> Tree / Hard Stop entities below pertain **only** to that dropped skill and are retained
> for historical context. All remaining scope is `maintain-claude-md`, shipped as
> `skills/maintain-claude-md/` (v0.2.0).
```

- [ ] **Step 3: Verify no other task/plan file resurrects skill 2**

Run: `cd ~/Developer/DomI && grep -rn "maintain-env-instructions" specs/001-maintain-skills/`
Expected: matches only inside the historical (superseded) sections; the header + note make the drop explicit. No action needed on the retained historical text.

- [ ] **Step 4: Commit**

```bash
cd ~/Developer/DomI
git add specs/001-maintain-skills/spec.md
git commit -m "docs(spec-001): supersede maintain-env-instructions; scope to maintain-claude-md

maintain-env-instructions targeted the retired CLAUDE_INSTRUCTIONS mechanism;
live path is scripts/instructions_on_start.sh + act-autonomously/bootstrap-vm.
Spec 001 now scopes only the shipped maintain-claude-md skill.

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01SVBtB45G8AjgW6t6aji2Kr"
```
Expected: commit lands on `feature/maintain-claude-md`.

---

### Task 4: Verification sweep

**Files:** none (read-only verification).

- [ ] **Step 1: claude-kit is green and on its branch**

Run: `cd ~/Developer/claude-kit && git branch --show-current && git status --short && make check`
Expected: branch `feature/maintain-claude-md-skill`; clean working tree; `make check` PASS.

- [ ] **Step 2: DomI skill registered and committed**

Run: `cd ~/Developer/DomI && git branch --show-current && git log --oneline -3 && grep -n "maintain-claude-md (v0.2.0)" MANIFEST.md`
Expected: branch `feature/maintain-claude-md`; last two commits are the skill+MANIFEST and the spec amendment; MANIFEST shows the v0.2.0 entry.

- [ ] **Step 3: Confirm nothing was pushed**

Run: `cd ~/Developer/claude-kit && git log origin/main..HEAD --oneline; cd ~/Developer/DomI && git log origin/main..HEAD --oneline`
Expected: both show local-only commits ahead of `origin/main` (i.e., unpushed). Report the commit list to the operator for them to push.

- [ ] **Step 4: Report**

Summarize: three commits in claude-kit (design, plan, skill), two in DomI (skill+MANIFEST+benchmark, spec amendment); both on feature branches; nothing pushed; benchmark fixture = Valence loader-stub incident.

## Self-Review

**Spec coverage:** approach A (two variants) → Tasks 1+2; six improvements → all present in both SKILL.md bodies (include-integrity #1, monorepo #5, static commands #6, defer-don't-duplicate #4 [WARN in Task 1 / FAIL in Task 2], anti-bloat #2, rule-rationale #3); drop maintain-env-instructions → Task 3; MANIFEST + benchmark (Article VIII) → Task 2; interaction points (introspect / speckit-plan / speckit-constitution) → both bodies' Integration/notes; no-push → Task 4. Covered.

**Placeholder scan:** SKILL.md `{PLACEHOLDER}` tokens are intentional scaffold-template variables inside the generated CLAUDE.md, not plan gaps. No TBD/TODO in the plan's own steps.

**Type consistency:** the mode names (init/update/lint), the benchmark id `claude-md-loader-stub-breaks-per-repo`, the branch names, and the `<!-- SPECKIT START/END -->` / `maintained-by` markers are identical across Tasks 1, 2, 3, and 4.
