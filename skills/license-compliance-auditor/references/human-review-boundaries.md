# Human review boundaries

This file is the authoritative statement of what this skill does and does not
decide. It is referenced from `risk-taxonomy.md` and `obligation-checklist.md`,
and from the report templates in `output-schema.md`. When in doubt about how to
phrase a finding, this file's framing wins.

## The non-legal-advice disclaimer

Every report carries this disclaimer, verbatim, every time:

> Automated license detection is a starting point, not legal advice.

This is not boilerplate to satisfy a formality — it reflects a real limit on
what pattern-matching over files, manifests, and headers can establish.
License compliance frequently turns on facts (how software is linked or
deployed, the history of a codebase, what a specific commercial agreement
says) that no static scan can observe.

## What the tool CAN say

- **Risk classification** — a `critical|high|medium|low|info` severity for a
  finding, per `risk-taxonomy.md`, based on the pattern observed.
- **Likely obligation gaps** — e.g. "attribution for `<component>` was not
  found," phrased as an observation about the repo's current state, per
  `obligation-checklist.md`.
- **Evidence** — the specific files, lines, manifest fields, or headers that
  support the finding, so a human reviewer can verify it quickly.
- **Confidence** — `high|medium|low`, reflecting how directly the evidence
  supports the finding (e.g. an explicit SPDX header is `high` confidence; a
  package-name heuristic is `low`).
- **Coverage** — what was checked, what wasn't, and why (scanner unavailable,
  heuristic-only detection, etc.), so gaps in the audit itself are visible.

## What the tool CANNOT say

- **Compliance verdicts.** It never states that a repo "is" or "is not" in
  compliance with a license, only that a gap "appears" or "is likely" present
  and should be reviewed.
- **Legal conclusions of any kind**, including whether a specific obligation
  is legally triggered, satisfied, or waived in this repo's specific
  circumstances.

## MUST be escalated, never decided by this tool

The following categories are explicitly out of scope for automated
determination. When one of these comes up, the finding must say so plainly
(e.g. "this is a human/legal-review determination, not one this tool makes")
rather than offering a resolved answer:

- **Version-history license drift** — whether a dependency, vendored file, or
  the repo itself changed license terms across versions/commits, and which
  version's terms actually govern the code currently in use.
- **Cross-copyleft compatibility** — whether two different copyleft licenses
  (e.g. GPL-2.0-only and GPL-3.0-only, or GPL and a share-alike CC license) are
  compatible with each other in a given combination.
- **Whether a linking/deployment model triggers LGPL/GPL/AGPL obligations** —
  static vs. dynamic linking, containerization, SaaS/network deployment, and
  similar architecture questions can shift whether these licenses' triggers
  fire, but the tool only reports the observed linking/deployment pattern as
  evidence, never a conclusion about legal effect.
- **Trademark/logo permission** — whether a specific use of a name, logo, or
  brand asset falls within nominative use or a project's trademark policy.
- **Snippet substantiality** — whether a copied code snippet is substantial
  enough to trigger copyright/license obligations at all (a threshold/de
  minimis judgment call).
- **Bespoke or commercial-use permission** — whether a specific "free for
  personal use," "non-commercial only," or custom-license asset's terms
  permit a particular repo's actual use.
- **Organizational commercial-use permission** — whether a specific
  organization's use of a tool/asset/dataset counts as "commercial" under a
  license's own (often undefined or narrowly defined) terms.
- **Anything constituting legal advice** — any determination that would
  require weighing facts against legal standards rather than reporting a
  pattern match, however confident the pattern match is.

## Confirmation flow for downstream actions

Findings can recommend next steps (e.g. "replace this dependency," "add a
NOTICE entry," "get legal review of the linking model"), but the tool never
takes an action on its own:

- Issue drafting (`issue_drafts.py`) is proposed, never automatic — the
  terminal report ends with a single closing question asking whether to
  propose GitHub issues for the high-priority findings.
- Any recommendation touching one of the "must be escalated" categories above
  should explicitly name it as a human/legal-review item in `review_notes`,
  not just imply it through severity level alone.
