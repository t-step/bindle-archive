---
description: Audit this repo for license compliance (deps, vendored code, fonts, assets, datasets, snippets).
argument-hint: [--deps-only|--assets-only|--fonts-only|--strict|--include-dev|--sbom|--report-only]
---

<!--
This is a slash command. When the user types /license-audit <args>, this whole
file becomes the prompt. The arguments are available as:
  $ARGUMENTS   all args as one string
-->

Use the license-compliance-auditor skill to audit this repository for license compliance.

Parse the following arguments as scope decisions:
- `--deps-only`: audit dependencies only; skip vendored code, fonts, and assets
- `--assets-only`: audit assets (images/audio/video/models/datasets) only; skip dependencies and fonts
- `--fonts-only`: audit fonts only; skip all other phases
- `--strict`: treat any critical/high findings as a nonzero exit (for CI)
- `--include-dev`: include dev-only dependencies in the scan (default: exclude)
- `--sbom`: use any available CycloneDX SBOM generator to enhance coverage
- `--report-only`: generate reports and stop; skip the issue-creation question

Arguments provided: $ARGUMENTS

Follow the skill's terminal-first workflow: run the audit phases sequentially, keep findings in memory, and render the terminal report before writing files. Include the issue-creation confirmation gate — only ask about GitHub issues after the terminal report, and only create issues with explicit user confirmation.
