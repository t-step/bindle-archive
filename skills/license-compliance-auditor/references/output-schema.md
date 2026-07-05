# Output schema: `license-compliance-auditor`

This is the canonical contract for everything the auditor produces: the terminal
summary, `license-compliance-report.md`, and `license-compliance-findings.json`. Every
script in this skill (`normalize_findings.py`, `render_report.py`, `issue_drafts.py`)
reads or writes data that conforms to what is defined here. Treat this file as the
source of truth — if a script's output disagrees with this schema, the script is wrong.

## 1. Terminal report structure

The terminal output is action-oriented, not a dump. Full detail always lives in the
`.md` / `.json` reports; the terminal points to them rather than repeating them. In
order:

1. **Repo license baseline + evidence** — the repo's declared license and where it was
   found (e.g. `LICENSE` file, `package.json` `license` field).
2. **Coverage summary** — what was checked, what was not, and an install hint for
   anything skipped because a scanner was unavailable (e.g. "install `pip-licenses` for
   deeper Python coverage").
3. **Top findings by severity** — the highest-risk items first, not an exhaustive list.
4. **Prioritized next actions** — the short list of what to do first.
5. **Files written** — paths to the markdown report and the JSON findings file.
6. **Closing prompt** — a single question: "Would you like me to propose GitHub issues
   for the high-priority findings?" Issue creation is never automatic; see
   `human-review-boundaries.md` for the confirmation flow.

## 2. Markdown report structure (`license-compliance-report.md`)

Top-level sections, in this order:

1. **Executive summary**
2. **Declared-license baseline** — the repo's own declared license plus evidence
3. **Coverage** — checked / not-checked / partial, per category, with install hints for
   gaps
4. **Reconciliation table** — one row per finding; see column order below
5. **Human/legal review items** — the items hard-flagged for human or legal judgment
   (never auto-decided; see `human-review-boundaries.md`)
6. **Limitations** — honest reliability caveats (scanner coverage bounds, heuristic
   asset/font/dataset detection, flag-only snippet provenance, etc.)
7. **Disclaimer** — the non-legal-advice disclaimer, verbatim and every time: "Automated license detection is a starting point, not legal advice."

### Reconciliation table column order (verbatim)

```
item → type → path/package → version/source → license/SPDX expression → actual usage →
compatibility risk vs repo license → unmet obligation → evidence → confidence →
risk level → recommended action
```

As a markdown table header row, the same twelve columns:

```
| item | type | path/package | version/source | license/SPDX expression | actual usage | compatibility risk vs repo license | unmet obligation | evidence | confidence | risk level | recommended action |
```

## 3. JSON findings schema (`license-compliance-findings.json`)

### Top-level document

| key | type | notes |
| --- | --- | --- |
| `schema_version` | string | version of this schema, e.g. `"1.0"` |
| `repo` | object | `{root, declared_license, declared_license_evidence[]}` — see below |
| `coverage` | array | list of coverage entries — see below |
| `findings` | array | list of finding objects — see below |
| `generated_by` | string | tool/script identity + version that produced the document |
| `disclaimer` | string | the non-legal-advice disclaimer, verbatim: `"Automated license detection is a starting point, not legal advice."` |

`repo` fields:

- `root` — string, the audited repo's root path (or identifying label).
- `declared_license` — string, SPDX id/expression for the repo's own declared license,
  or `UNKNOWN` if none was found.
- `declared_license_evidence` — array of strings describing where the declared license
  was found (file paths, manifest fields).

`coverage` entries — one per scanned category, each an object:

| key | type | required | notes |
| --- | --- | --- | --- |
| `category` | string | yes | what was scanned, e.g. `"npm dependencies"` |
| `status` | string | yes | one of `checked`, `not-checked`, `partial` |
| `method` | string | no | how it was checked (tool invocation, manual inspection, etc.) |
| `tool` | string | no | the scanner/tool name, if one was used |
| `note` | string | no | free-text context |
| `install_hint` | string | no | how to enable deeper coverage when `status` is `not-checked` or `partial` |

### Finding object

Every entry in `findings` has exactly these keys:

| key | type | notes |
| --- | --- | --- |
| `id` | string | stable id, format `F-0001`, `F-0002`, ... |
| `type` | string | one of `dependency`, `vendored`, `submodule`, `spdx-header`, `font`, `asset`, `dataset`, `snippet`, `repo-license` |
| `item` | string | human-readable name of the thing found |
| `path` | string | repo-relative path where it was found |
| `version` | string | version/revision, or `UNKNOWN` if not determinable |
| `ecosystem` | string or null | package ecosystem (`npm`, `pypi`, `cargo`, ...), null when not applicable |
| `source` | string | where the license determination came from (manifest field, license file, scanner, header, etc.) |
| `license_expression` | string | SPDX id or expression, or `UNKNOWN` |
| `usage` | string | how the item is actually used in the repo (vendored, linked, bundled asset, dev-only, etc.) |
| `compatibility_risk` | string | risk enum — see below |
| `unmet_obligation` | string | the specific obligation likely unmet, or `none` |
| `evidence` | array of strings | supporting evidence (file paths, quoted lines, URLs) |
| `confidence` | string | one of `high`, `medium`, `low` |
| `risk_level` | string | risk enum — see below |
| `review_notes` | string | free-text notes for the human/legal reviewer |
| `recommended_action` | string | the concrete next step |

### Shared risk enum

`risk_level` and `compatibility_risk` share the same enum: `critical|high|medium|low|info`. They are not independent scales — `compatibility_risk` is the risk
contribution from the license-compatibility comparison specifically, while `risk_level`
is the finding's overall severity, but both draw from this one enum.

### Worked example finding

```json
{
  "id": "F-0001",
  "type": "dependency",
  "item": "left-pad-gpl",
  "path": "package.json",
  "version": "2.3.0",
  "ecosystem": "npm",
  "source": "package.json dependencies + node_modules/left-pad-gpl/LICENSE",
  "license_expression": "GPL-3.0-only",
  "usage": "bundled into the production build, statically linked at build time",
  "compatibility_risk": "critical",
  "unmet_obligation": "source-disclosure obligation for the combined work is likely triggered by static linking under a GPL-3.0 dependency in a repo declared MIT",
  "evidence": [
    "package.json:14 lists \"left-pad-gpl\": \"^2.3.0\"",
    "node_modules/left-pad-gpl/LICENSE identifies GPL-3.0-only",
    "repo root LICENSE declares MIT"
  ],
  "confidence": "high",
  "risk_level": "critical",
  "review_notes": "Whether the build's linking model legally triggers GPL-3.0 source-disclosure duties for the combined work is a human/legal-review determination, not one this tool makes.",
  "recommended_action": "Replace the dependency with a permissively-licensed alternative, or obtain explicit legal review of the linking/distribution model before release."
}
```

### Example `disclaimer` field value

```json
{
  "disclaimer": "Automated license detection is a starting point, not legal advice."
}
```

### Example `coverage` entry

```json
{
  "category": "npm dependencies",
  "status": "partial",
  "method": "package.json + lockfile inspection",
  "tool": null,
  "note": "no SPDX-aware scanner installed; license fields taken as declared, not verified against package contents",
  "install_hint": "install a license scanner (e.g. license-checker) for deeper npm coverage"
}
```
