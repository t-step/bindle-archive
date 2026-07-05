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
Related: a governance-aware DomI variant *enforces* defer-don't-duplicate as a FAIL
(linking the repo's constitution); this portable variant softens it to a WARN.
-->
