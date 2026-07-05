---
name: license-compliance-auditor
description: Use when auditing a repository for license compliance — reconciling the declared license against dependencies, vendored code, submodules, fonts, bundled assets, datasets, and copied snippets; classifying risk and obligation gaps; never giving legal conclusions.
---

# license-compliance-auditor

## Overview

Orchestrate whatever license/dependency scanners are actually installed plus
direct file inspection, reconcile everything found against the repo's own
declared license, classify risk per finding, and preserve uncertainty as a
reported gap rather than a guess. This skill never concludes legality — it
produces evidence-backed risk findings for a human/legal reviewer.

## When to Use

- Auditing a repo (or a PR) for license compliance across dependencies,
  vendored/submoduled code, fonts, images/audio/video/models/data, and
  copied snippets.
- Before a release, an open-sourcing decision, or an acquisition/vendor
  review that needs a license-risk inventory.
- Operator asks for a "license audit", "license compliance check", or "am I
  exposed on licensing".

When NOT to use:
- A single quick question like "is MIT compatible with Apache-2.0?" or "what
  does this one LICENSE file say?" — just answer it directly.
- Legal advice or a compliance sign-off — this skill stops at risk
  classification; see `references/human-review-boundaries.md`.

## Safe-Execution Rules

- **Never install a scanner or package manager.** Only use tools already
  present (`references/tool-map.md` has the fallback for each one that's
  missing).
- **Never touch the network** to "resolve" a license (no fetching a
  package's registry page, no scraping a license text off the web). Work
  from what's in the repo plus locally installed tool output.
- **No legal conclusions, ever.** Findings state risk and likely obligation
  gaps with evidence — never "this repo is/isn't in compliance." See
  `references/human-review-boundaries.md`.
- **Always report coverage gaps.** A missing scanner or an unresolvable
  license is a `coverage` entry with an install hint, never a fabricated
  finding.

## Workflow Checklist

Work terminal-first: run the phases below, keep findings in memory as you
go, and only write the `.md`/`.json` reports once the full pass is done.

1. **Preflight** — confirm the repo root and whether this is a full audit or
   a scoped one (see Options below). Run `python3 scripts/detect_tools.py`
   to see what's installed before assuming any scanner is available.
2. **Dependency scan** — per ecosystem found, use the installed scanner or
   its manifest/lockfile fallback. Read `references/tool-map.md` first —
   it lists the scanner, its fallback, and the install hint per ecosystem.
3. **Vendored code / submodules / SPDX headers** — run
   `python3 scripts/inventory_repo.py <root>` to enumerate vendored dirs,
   `.gitmodules` entries, and `SPDX-License-Identifier` headers, then
   inspect each hit.
4. **Fonts** — for every font file `inventory_repo.py` reports, read
   `references/font-license-cheatsheet.md` before classifying (OFL/RFN,
   web-embed vs. vendored, icon-font layering are all easy to get wrong).
5. **Other assets** (images/audio/video/models/datasets) — read
   `references/asset-license-cheatsheet.md` before classifying; remember
   public availability is not redistribution permission.
6. **Provenance gaps** — review the `provenance_markers` inventory hits
   (copied-snippet cues) and anything with no discoverable license at all;
   record as unclear-provenance rather than guessing.
7. **Obligation layer** — for each finding, work through
   `references/obligation-checklist.md` to fill in `unmet_obligation`,
   `evidence`, and `review_notes` using its risk-framed phrasing (likely,
   appears to — never an assertion of noncompliance).
8. **Risk classification** — assign `risk_level` and `compatibility_risk`
   per `references/risk-taxonomy.md`; when they'd differ, the finding's
   `risk_level` takes the higher of the two.
9. **Assemble + normalize** — build the findings JSON (schema in
   `references/output-schema.md`) and run it through
   `python3 scripts/normalize_findings.py` to canonicalize SPDX ids and
   backfill required fields.
10. **Terminal report** — render and read the terminal summary before
    writing files (see Scripts below); it's the action-oriented view,
    not a full dump. The terminal output should include a short prioritized
    next-actions list and the non-legal-advice disclaimer line, since the
    script's summary points to the written reports for full detail.
11. **Written reports** — write `license-compliance-report.md` and
    `license-compliance-findings.json` to the target directory.
12. **Optional issue workflow** — only after the closing question is asked
    and answered; see the Issue-Creation Gate below.

## Scripts

All scripts are Python 3 stdlib-only; run from the skill directory (or with
a relative/absolute path to it) as `python3 scripts/<name>.py ...`.

```bash
# 1. See what scanners/package managers are actually installed
python3 scripts/detect_tools.py

# 2. Enumerate license-relevant files under a repo root
python3 scripts/inventory_repo.py <root>

# 3. Normalize the model-assembled findings document to the stable schema
#    (reads a file path arg, or stdin if omitted)
python3 scripts/normalize_findings.py findings.json > normalized.json

# 4. Render the terminal summary + write the two report files into <out_dir>
python3 scripts/render_report.py normalized.json <out_dir>

# 5. Only after explicit confirmation (see gate below): write grouped
#    local issue drafts (never calls gh or the network)
python3 scripts/issue_drafts.py normalized.json license-compliance-issues
```

## Report Outputs

- `license-compliance-report.md` — full markdown report (executive summary,
  declared-license baseline, coverage, reconciliation table, human/legal
  review items, limitations, disclaimer).
- `license-compliance-findings.json` — the machine-readable findings
  document.
- Schema and exact section/column order for both: `references/output-schema.md`.

## Options / Flags

Apply these as scope decisions during preflight and inventory, not as
literal CLI flags on the stdlib scripts above:

- **Include/exclude dev dependencies** — dev-only dependencies are lower
  risk (rarely distributed); scope them in or out explicitly and note the
  choice in `coverage`.
- **SBOM** — if a CycloneDX generator is already installed for a detected
  ecosystem, treat it as a coverage enhancement, not a requirement (see
  the SBOM section of `references/tool-map.md`); never install one.
- **Scan-only-deps / -assets / -fonts** — a scoped run may cover just one
  phase; still report the phases that were skipped as `not-checked` in
  `coverage` rather than omitting them silently.
- **Strict CI mode** — treat any `critical`/`high` finding as a nonzero
  exit for the calling process/CI job.
- **Report-only** — run through phase 11 and stop; skip the issue-creation
  question entirely.

## Issue-Creation Gate

Issue creation is **never automatic**:

1. Print/deliver the terminal report first.
2. End with a single closing question: "Would you like me to propose
   GitHub issues for the high-priority findings?"
3. If yes, propose a **grouped plan** first (one group per finding type —
   dependency, vendored, font, asset, etc.) and get explicit confirmation
   on the plan itself.
4. Only after that confirmation, and only when `gh` is authenticated
   (`gh auth status`) **and** a GitHub remote exists, create issues via
   `gh issue create`.
5. Otherwise (no confirmation, no `gh`, no GitHub remote), write local
   drafts instead: `python3 scripts/issue_drafts.py <findings> license-compliance-issues`.

## Legal Boundary

Every report carries the disclaimer verbatim: "Automated license detection
is a starting point, not legal advice." What this tool can and cannot say,
and the specific categories that must be escalated rather than decided
(cross-copyleft compatibility, linking/deployment triggers, trademark
scope, snippet substantiality, and more), are defined in
`references/human-review-boundaries.md` — read it before phrasing any
finding that touches one of those categories.

## Progressive Disclosure — Read These References When…

| Reference | Read it when… |
| --- | --- |
| `references/tool-map.md` | Starting the dependency scan, or a scanner is missing and you need its fallback/install hint. |
| `references/output-schema.md` | Assembling findings, or unsure of a field name/report section order. |
| `references/risk-taxonomy.md` | Assigning `risk_level`/`compatibility_risk`, or a finding could plausibly sit at two levels. |
| `references/obligation-checklist.md` | Filling in `unmet_obligation`/`review_notes` for any specific obligation type. |
| `references/font-license-cheatsheet.md` | A font file turns up in the inventory. |
| `references/asset-license-cheatsheet.md` | An image/audio/video/model/dataset turns up in the inventory. |
| `references/human-review-boundaries.md` | Phrasing any finding, and always before the issue-creation question. |

## Common Mistakes

- **Guessing a license from a package name or README blurb** instead of
  recording it as a coverage gap — see `references/tool-map.md`'s rule.
- **Asserting noncompliance** instead of "likely" / "appears to" — breaks
  the legal boundary in `references/human-review-boundaries.md`.
- **Skipping fonts/assets** because they have no manifest entry — they're
  exactly the blind spot the cheatsheets exist for.
- **Creating GitHub issues without the confirmation gate**, or without
  checking `gh auth status` and a GitHub remote first.
