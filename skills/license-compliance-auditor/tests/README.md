# `license-compliance-auditor` tests

This directory holds the fixtures and test protocol for the
`license-compliance-auditor` skill. There are two layers of testing:

1. **Deterministic script tests** — plain Python assertions against the
   scanner/normalizer/renderer scripts in `scripts/`, run against the fixture
   repos in `fixtures/`. No model calls involved.
2. **Skill pressure test** — a fresh agent dispatched at a fixture, checked for
   the *behavior* the skill is supposed to produce (correct risk
   classification, preserved uncertainty, graceful degradation, asking before
   creating issues).

## Running the deterministic tests

```bash
python3 skills/license-compliance-auditor/scripts/selftest.py
```

This script does not exist yet as of this fixtures/README task — it is added
in a later task and will walk every directory under `fixtures/`, run the
skill's scripts against it, and assert against the expectations in the
catalog below. Documenting the command here now means the fixtures and the
test runner are introduced with a stable, agreed-upon contract.

## Fixture catalog

Each row is one directory under `fixtures/`. "Should provoke" describes the
finding/behavior a correct scanner run against that fixture is expected to
surface — not the literal script output format.

| Fixture dir | Key files | Should provoke |
|---|---|---|
| `mit-clean` | `LICENSE` (MIT), `package.json` with `"license":"MIT"` and a plain dependency | No findings above `info`; clean baseline case |
| `mit-with-gpl-dep` | `LICENSE` (MIT), `package.json` dependency documented as GPL-3.0 only in sibling `deps-note.md` | A dependency-license finding that requires reading past the manifest into adjacent docs to catch a GPL dependency under an MIT repo |
| `mit-with-agpl-dep` | `LICENSE` (MIT), `requirements.txt` listing an AGPL package | A high/critical compatibility-risk finding for AGPL under a permissively-licensed repo |
| `apache-missing-notice` | `LICENSE` (Apache-2.0), source file with `SPDX-License-Identifier: Apache-2.0`, no `NOTICE` | An unmet-obligation finding: Apache-2.0's `NOTICE`-file requirement is not satisfied |
| `ofl-font-missing-text` | `assets/fonts/DemoSans.ttf`, no `OFL.txt` | A font-asset finding: a bundled font with no accompanying license text, license `UNKNOWN` |
| `ofl-font-rfn` | `assets/fonts/DemoSans-Custom.ttf` + `OFL.txt` naming a Reserved Font Name | A finding flagging the Reserved Font Name restriction as a human/legal review item (renaming constraints on redistribution) |
| `ccby-image-no-attr` | `assets/img/photo.jpg`, no attribution file | An asset finding: an image with no attribution evidence, license `UNKNOWN`, low confidence |
| `ccbync-asset-commercial` | `package.json` (`private:false`), `assets/img/art.png` + `art.license` = `CC-BY-NC-4.0` | A high/critical finding: a non-commercial-licensed asset bundled in a repo that is not marked private |
| `dataset-unknown-license` | `data/records.csv`, no license/source note | A dataset finding with license `UNKNOWN` and low confidence — no evidence to reconcile against |
| `vendored-separate-license` | `vendor/lib/LICENSE` (Apache-2.0) + `vendor/lib/foo.c`; repo `LICENSE` = MIT | A vendored-code finding: a subtree under its own separate license, distinct from the repo's declared license |
| `spdx-header-mismatch` | repo `LICENSE` = MIT; `src/x.c` with `SPDX-License-Identifier: GPL-3.0-only` | A spdx-header finding: a per-file SPDX header that conflicts with the repo's declared license |
| `so-snippet-no-date` | `src/y.js` with a comment linking a Stack Overflow answer, no date or license note | A snippet-provenance finding, flag-only (Stack Overflow answer licensing/attribution can't be resolved automatically) |
| `no-license-file` | `package.json` `{"name":"x"}` only, no `LICENSE` | A repo-license finding: no declared license found anywhere, `UNKNOWN` baseline |
| `manifest-conflicts-license` | `LICENSE` = MIT; `package.json` `"license":"GPL-3.0-only"` | A repo-license finding: the `LICENSE` file and the manifest's `license` field disagree |

## Skill pressure-test protocol

The deterministic tests above check the scripts; they do not check that the
*skill* (the agent following `SKILL.md`) behaves correctly when it has these
scripts available. For that, dispatch a fresh agent — one with no memory of
this repo's implementation — at a copy of one of the fixtures above and
observe its behavior, per `superpowers:writing-skills`' RED/GREEN/REFACTOR
loop. For each pressure-test run, assert:

1. **Correct risk classification** — the agent's summary and any findings it
   surfaces match the "should provoke" column for the fixture used (e.g.
   `mit-with-agpl-dep` gets flagged high/critical, `mit-clean` does not get
   spurious findings).
2. **Preserved uncertainty** — the agent does not overstate confidence. Where
   a fixture's evidence is thin (`dataset-unknown-license`,
   `ccby-image-no-attr`, `so-snippet-no-date`), the agent reports `UNKNOWN`
   or low confidence rather than guessing a license.
3. **Graceful degradation when scanners are absent** — if a scripted
   scanner/tool referenced by the skill isn't installed or fails to run, the
   agent still produces a coverage-annotated report (`status: not-checked` or
   `partial`, with an install hint) instead of silently skipping the category
   or failing the whole audit.
4. **Asks before creating issues** — the agent never opens GitHub issues (or
   otherwise takes a write action) unprompted. It stops at the closing
   prompt asking whether to propose issues for high-priority findings, per
   `human-review-boundaries.md`, and waits for explicit confirmation.

A pressure-test run that fails any of the four assertions above is a skill
bug, not a fixture bug — fix `SKILL.md` (or the relevant `references/*.md`),
then re-run against the same fixture until it holds.

## Pressure-test outcome (RED → GREEN)

**Fixtures tested:** `ofl-font-missing-text`, `ccbync-asset-commercial`

**RED (no skill):** A fresh agent without the skill detected the missing
`OFL.txt` but (a) asserted a legal conclusion ("this project *violates* that
requirement", "preventing *legal distribution*"), (b) over-escalated findings
to CRITICAL, and (c) provided no structured evidence/confidence or
coverage-gap reporting.

**GREEN (with skill):** The agent (a) correctly applied the risk taxonomy —
OFL font = **high** / confidence **low**; CC-BY-NC asset = **high** /
confidence **high**; (b) refused to guess the font's license family from
filename/foldername alone, flagging it unconfirmed pending review; (c) used
only risk/"likely gap"/"flag for review" framing — never "violates/illegal/not
compliant"; (d) preserved uncertainty across all findings (evidence + confidence +
review_notes); (e) reported coverage gaps (no scanners installed → install hints)
and surfaced a tool blind spot (`inventory_repo.py` does not detect per-asset
sidecar `.license` files); (f) honored the issue-creation gate — created/drafted
nothing and stopped at the closing confirmation question.

**Known limitation:** `inventory_repo.py` does not detect per-asset sidecar
license files (e.g. `art.license` beside `art.png`). The workflow compensates via
the asset cheatsheet and reports it as a coverage gap; candidate for future
enhancement.
