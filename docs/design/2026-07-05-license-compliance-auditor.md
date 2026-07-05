# Design: `license-compliance-auditor` — reusable repo license-compliance audit

**Date:** 2026-07-05 · **Status:** Approved design, pre-implementation
**Issue:** [thomas-estep/claude-kit#8](https://github.com/thomas-estep/claude-kit/issues/8)
**Target:** `thomas-estep/claude-kit` (portable, installed into `~/.claude/`)

## Problem

We want a reusable Claude Code capability that audits any repository for licensing
compliance. The core value is **not** license detection — mature scanners already do
that. The value is the **reconciliation and obligation-checking layer**: gather
evidence from scanners and repo inspection, normalize to SPDX where possible, compare
each item's license and usage against the repo's declared license, identify likely
unmet obligations, classify risk, recommend next actions, preserve uncertainty, and
flag ambiguous items for human/legal review.

It must **never present legal conclusions.** It classifies risk, explains evidence,
identifies likely obligation gaps, flags items for human/legal review, and states
plainly that automated license detection is a starting point, not legal advice.

## Locked decisions (from brainstorming)

1. **Shape:** a progressive-disclosure Agent Skill **+ a thin slash command** entrypoint.
2. **Scripts:** the full deterministic suite (detect_tools, inventory_repo,
   normalize_findings, render_report, issue_drafts) plus a stdlib self-test.
3. **Language:** **Python 3, stdlib-only** — no `pip install`, present on nearly every
   dev machine, honoring "never auto-install / degrade gracefully." Falls back to
   model-driven inventory if Python is somehow absent.
4. **Build/land:** everything in **one branch/PR** — all phases, all asset categories,
   all fixtures, all scripts — pressure-tested before it is called done.

## Why this shape

- **Portability (the issue's top priority):** `bin/install.sh` symlinks the whole
  `skills/<name>/` directory into `~/.claude/skills/`, so bundled `references/` and
  `scripts/` travel with the skill and run in every audited repo — no per-project setup.
- **Right tool per job:** the workflow is phase-ordered but its value is *judgment*
  (reconciliation, risk classification, preserved uncertainty). Judgment lives in
  SKILL.md + references; boring repeatable grunt work (inventory, normalization,
  rendering) lives in deterministic scripts. Neither half does legal reasoning.
- **Command = entrypoint, not logic:** commands here are single `.md` prompt files, so
  `/license-audit [flags]` reads `$ARGUMENTS`, sets mode, and defers to the skill —
  no logic duplication.

## File tree

```
skills/license-compliance-auditor/
├── SKILL.md
├── references/
│   ├── tool-map.md               # ecosystem→scanner map, commands to try, fallbacks, install hints
│   ├── output-schema.md          # findings JSON schema + markdown + terminal report structure
│   ├── risk-taxonomy.md          # critical/high/medium/low/info + escalation rules
│   ├── obligation-checklist.md   # attribution, NOTICE, source-disclosure, patent, copyleft, trademark
│   ├── font-license-cheatsheet.md
│   ├── asset-license-cheatsheet.md
│   └── human-review-boundaries.md # non-legal-advice language; what MUST escalate
├── scripts/
│   ├── detect_tools.py           # report available scanners/pkg mgrs (never installs) → JSON
│   ├── inventory_repo.py         # enumerate manifests/lockfiles/license files/vendored/submodules/
│   │                             #   SPDX headers/fonts/assets/datasets/provenance markers → JSON
│   ├── normalize_findings.py     # mechanical: raw scanner output + model annotations → schema JSON
│   ├── render_report.py          # findings JSON → terminal summary + markdown report (deterministic)
│   ├── issue_drafts.py           # grouped findings → license-compliance-issues/*.md
│   └── selftest.py               # stdlib unittest entry; hooks into `make check`
└── tests/
    ├── README.md                 # how to run; scenario catalog; pressure-test protocol
    └── fixtures/                 # tiny synthetic repo trees (see Fixtures)

commands/license-audit.md          # thin entrypoint: /license-audit [--deps-only|--assets-only|
                                   #   --fonts-only|--strict|--include-dev|--sbom|--report-only]
```

## What belongs where

- **SKILL.md (concise, operational):** trigger description; when to use / when not; the
  terminal-first phase workflow as a checklist; safe-execution rules (no installs, no
  legal conclusions); the issue-creation confirmation gate; and progressive-disclosure
  pointers ("read `references/tool-map.md` before dependency scanning", etc.). Long
  knowledge does not live here.
- **references/ (read on demand):** the heavy, stable knowledge — scanner map, JSON
  schema, risk taxonomy, obligation checklist, font/asset cheatsheets, and the
  human-review / legal-boundary language.
- **scripts/ (deterministic, safe, stdlib-only):** inventory, tool detection, mechanical
  normalization, report rendering, issue-draft writing. Scripts may assign preliminary
  heuristic flags but **never** emit legal conclusions; the model finalizes
  reconciliation and risk from evidence.

## Data flow

1. `detect_tools.py` + `inventory_repo.py` → JSON (available scanners; repo inventory).
2. Model runs available scanners guided by `references/tool-map.md`, and reconciles each
   item's license + usage against the declared repo license.
3. `normalize_findings.py` shapes raw scanner output + model annotations into the schema.
4. `render_report.py` prints the terminal summary and writes `license-compliance-report.md`
   + `license-compliance-findings.json`.
5. On explicit confirmation, `issue_drafts.py` writes grouped drafts to
   `license-compliance-issues/` (or the model creates GitHub issues via `gh`).

## Workflow (phases, terminal-first)

Preflight (repo root, declared license + evidence, detect scanners/ecosystems/lockfiles,
report coverage limits) → software dependency scanning (direct + transitive, per
ecosystem, record evidence/confidence/review notes, handle dual-license expressions
without inventing an election) → vendored code / submodules / file SPDX headers →
fonts → other bundled assets (images/audio/video/3D/datasets) → code-provenance gaps →
obligation layer → compatibility & risk classification → **terminal report** → written
reports (`.md` + `.json`) → optional GitHub issue workflow (ask first, propose plan,
confirm, then create or draft).

## Terminal UX

Terminal-first and action-oriented (not a dump): repo license baseline + evidence;
coverage summary (checked / not checked / "install X for more"); top findings by
severity; prioritized next actions; files written; then a single closing prompt:
*"Would you like me to propose GitHub issues for the high-priority findings?"* Full
detail lives in the `.md` / `.json` reports, which the terminal points to.

## GitHub issue workflow

Never automatic. After the report, ask. On yes → propose a grouped issue plan first
(3–8 well-grouped issues, critical/high prioritized; each with evidence, affected items,
remediation, acceptance criteria, human-review note, suggested labels). Only after
explicit confirmation, and only if `gh` is installed + authenticated + a GitHub remote
exists, create via `gh issue create`. Otherwise write drafts to
`license-compliance-issues/`. Terminal reports what happened (links or draft paths).

Suggested labels: `license-compliance`, `legal-review`, `dependencies`, `assets`,
`fonts`, `documentation`, `high-priority`.

## Human-review / legal boundaries

`references/human-review-boundaries.md` is authoritative and referenced from SKILL.md.
Every report carries a **non-legal-advice disclaimer.** The tool classifies *risk* and
identifies *likely obligation gaps* with evidence + confidence — it never concludes
"compliant / non-compliant." Hard-flagged for human/legal review, never decided:

- version-specific license changes across dependency history,
- compatibility between two different copyleft licenses,
- whether a linking/deployment model legally triggers LGPL/GPL/AGPL duties,
- whether a trademark/logo use is permitted,
- whether a copied snippet is substantial enough to require attribution,
- whether a bespoke/commercial dataset or asset license permits the repo's exact use,
- whether an organization's actual commercial use is permitted,
- any determination that would constitute legal advice.

## Risk taxonomy

`critical` (likely blocking: strong copyleft/AGPL/LGPL in a permissive/commercial
distribution path, missing source obligations, asset license likely forbids intended
use) · `high` (likely obligation gap: missing attribution/license text for redistributed
assets, unknown license for a bundled dependency or dataset, unclear vendored
provenance) · `medium` (ambiguous/incomplete metadata; review before release) · `low`
(docs/NOTICE cleanup) · `info` (facts, no obvious issue). Compatibility conflicts between
the declared license and detected obligations are scored at the highest applicable
severity.

## Outputs

- `license-compliance-report.md` — executive summary, declared-license baseline, scan
  coverage + missing tools, reconciliation table, prioritized actions, human/legal review
  items, scanner evidence, limitations, non-legal-advice disclaimer.
- `license-compliance-findings.json` — stable schema documented in
  `references/output-schema.md`.
- Reconciliation table columns: item → type → path/package → version/source →
  license/SPDX expression → actual usage → compatibility risk vs repo license → unmet
  obligation → evidence → confidence → risk level → recommended action.

Supported options (documented in the skill / exposed as command flags): include/exclude
dev dependencies · emit/skip CycloneDX SBOM where tooling exists · scan-only-deps ·
scan-only-assets · scan-only-fonts · strict CI mode (critical/high → nonzero exit) ·
report-only mode (never fails).

## Test / fixture plan

Two layers, both required before "done":

1. **Deterministic script tests** — `scripts/selftest.py` (stdlib `unittest`) runs each
   script against fixtures and asserts stable JSON/report output. Hooks into `make check`
   so CI covers it.
2. **Skill pressure-test (RED → GREEN → REFACTOR per superpowers:writing-skills)** —
   dispatch a *fresh* agent at the fixtures and verify behavior: correct risk
   classification, preserved uncertainty, graceful degradation when scanners are absent,
   and that it **asks before creating issues.** Documented in `tests/README.md`.

**Fixtures** (tiny synthetic trees): clean MIT + MIT deps · MIT + GPL dep · MIT + AGPL
dep · Apache-2.0 missing NOTICE · bundled OFL font missing OFL.txt · OFL Reserved-Font-
Name concern · CC-BY image missing attribution · CC-BY-NC asset in a commercial-style
repo · dataset unknown/bespoke license · vendored code with separate license · file-level
SPDX header ≠ repo license · Stack Overflow snippet comment missing date/attribution ·
no top-level LICENSE · package manifest license conflicting with top-level LICENSE.

## Assumptions & honest reliability caveats

Stated in the report, not hidden:

- Detection quality is **bounded by installed scanners**; gaps are reported with install
  hints, **never guessed**.
- **Font/asset/dataset license detection is heuristic** (adjacent license files, package
  metadata, filenames, `@font-face` / `next/font` refs) — not content fingerprinting or
  perceptual matching. Binary assets without provenance are flagged for review, not
  classified.
- **Snippet/provenance is flag-only** (SO/gist/blog markers, URLs in comments); SO
  licensing varies by contribution date, so unknown-date items are escalated.
- Dual-license expressions (`MIT OR Apache-2.0`) are recorded in full; an elected option
  is **never invented** without clear evidence.
- Fixtures are tiny synthetic trees, not large real repos — they validate *behavior*, not
  scanner accuracy at scale.
- Python 3 stdlib-only; if Python is absent, the skill degrades to model-driven inventory
  and says so.

## Out of scope (v1)

No content-fingerprinting/perceptual asset matching; no automatic scanner installation;
no legal conclusions; no CI wiring into the audited repo (strict mode exit code is
available for the user to wire up themselves).

## Naming

Skill dir: `license-compliance-auditor`. Slash command: `/license-audit`.
