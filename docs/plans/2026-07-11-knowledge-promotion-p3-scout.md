# Packet 3 — the knowledge-scout agent (optional context-economy layer)

Implements the read-only scout of
[`docs/design/2026-07-11-knowledge-promotion.md`](../design/2026-07-11-knowledge-promotion.md)
(issue #81, wave 1) on top of packets 1–2.

## 1. Objective

Create `agents/knowledge-scout.md`: a read-only subagent that digests the
evidence set and returns contract-schema candidates, plus the one paragraph
in `commands/promote-knowledge.md` that delegates to it when available and
falls back inline when not.

## 2. Why this packet exists

Evidence sets grow (a bootstrap over 20 sessions is a lot of context); the
scout keeps the main session's context for the propose→confirm loop. It is
deliberately optional: packet 2's command is complete without it, so this
packet can be deferred or dropped without breaking wave 1.

**Assessment requested by the planning brief:** the scout is *not* too
complex for wave 1 — it is one agent file and one command paragraph,
because packet 1 already owns the handoff schema. It stays a separate
packet so it can slip independently.

## 3. Dependencies

Packets 1 and 2 committed (the agent returns packet 1's candidate schema;
this packet edits packet 2's command file).

## 4. Exact scope

`agents/knowledge-scout.md`, following `agents/_template.md` conventions:

```yaml
---
name: knowledge-scout
description: Use when /promote-knowledge needs the evidence set digested — reads the given notes-home files (and inline issue/PR extracts) and returns rung-classified promotion candidates per docs/knowledge-promotion.md. Read-only; never writes files; never promotes.
tools: Read, Grep, Glob
---
```

No `Bash` in `tools` — the read-only guarantee is structural, not
behavioral. Issue/PR enrichment stays in the command layer: the command
passes any `gh` output *inline* in the scout's prompt.

Agent body must specify:

- **Input contract:** the caller provides (a) the map's current entries
  (pasted or by path), (b) an explicit list of evidence file paths, (c)
  optional inline issue/PR extracts. The scout reads nothing outside that
  list.
- **What you do:** apply the contract's six promotion rules and ladder
  (read `docs/knowledge-promotion.md` — the caller passes its path; ask
  for it if missing rather than guessing rules from memory).
- **What you return:** exactly one fenced ```yaml block matching the
  contract's candidate schema (candidates / rejected / deferred /
  relitigation), nothing else after it. Rung 6 must never appear;
  cross-project material becomes a `deferred` item plus a rung-3+`transfer?`
  or rung-4+`inquiry?` candidate.
- **Hard prohibitions:** no file writes, no repo mutation, no promotion —
  the caller owns propose/confirm/write.

`commands/promote-knowledge.md` — replace the step-6 sentence "Generate
candidates and screen them…" with: generate via the `knowledge-scout`
subagent when the agent is installed, passing the input contract above;
validate that the reply parses as the contract schema; on a missing agent
or an unparseable reply, fall back to inline analysis (the packet-2
behavior) and note the fallback in the report. No other command lines
change.

**Repository-compliance note** (pre-existing registration gate — see
packet 1's compliance note; paste verbatim):

```json
{
  "type": "agent",
  "name": "knowledge-scout",
  "path": "agents/knowledge-scout.md",
  "description": "<must equal the agent frontmatter's description exactly — the validator enforces the match, as it does for commands>",
  "maturity": "draft",
  "mutation": [],
  "provider": {"claude": "installed", "codex": "unsupported"},
  "version_introduced": "0.3.0"
}
```

CHANGELOG line under `### Added`:

```markdown
- `agents/knowledge-scout.md` (draft, pending pressure tests): read-only
  candidate digester used by `/promote-knowledge` when installed (issue
  #81, wave 1).
```

## 5. Explicit non-goals

- No agent publication ceremony, no #7 first-agent decision, no
  pressure-test graduation (packet 4 tests it; #7 is a separate issue).
- No new schema: the handoff contract is packet 1's §7 verbatim. If the
  schema proves insufficient, fix `docs/knowledge-promotion.md` first.
- No scout-side `gh`, no network, no Bash.
- No changes to the installer (`agents/*.md` is an existing installed
  category; `_template.md` skipping is existing behavior).

## 6. Expected files to add or modify

| File | Change |
|---|---|
| `agents/knowledge-scout.md` | new (~40 lines) |
| `commands/promote-knowledge.md` | step-6 delegation paragraph only |
| `capabilities.json` | +1 agent row |
| `CHANGELOG.md` | one `### Added` line |

## 7. Interfaces and data shapes

Owned elsewhere: candidate schema and rules (packet 1). Owned here, and
only here:

- the scout **input contract** (map entries + explicit evidence path list +
  optional inline extracts + the contract-doc path);
- the **degradation rule**: missing agent or unparseable YAML → inline
  fallback + a "scout unavailable/fallback" line in the report. The command
  must never fail a run because the scout misbehaved.

## 8. Step-by-step implementation plan

1. Clean `git status --short`; branch `docs/81-knowledge-promotion-design`.
2. Write `agents/knowledge-scout.md` per §4.
3. Edit the single step-6 paragraph of `commands/promote-knowledge.md`.
4. Add the capabilities row + CHANGELOG line.
5. `make check`, `make test`.
6. Smoke-run per §12.
7. Commit: `feat: knowledge-scout agent (draft) + command delegation (#81)`.

## 9. Acceptance criteria

- Agent file valid per `make check`'s frontmatter gate; `tools:` is exactly
  `Read, Grep, Glob`.
- With the agent installed, a `/promote-knowledge` run over a fixture
  produces the identical filesystem outcome as the packet-2 inline path
  (same confirmed entries → same map bytes).
- With the agent file removed, the command still completes and its report
  notes the fallback.
- Scout output is one fenced YAML block matching the contract schema.
- `make check` + `make test` green.

## 10. Required tests

Structural gates plus §12. Behavioral equivalence (scout vs. inline) is
re-verified in packet 4's scenario runs — run at least scenarios 1 and 8
both ways there.

## 11. Failure and edge cases

- Scout returns prose around the YAML → command extracts the fenced block;
  if none parses, fallback (§7).
- Scout invents a rung-6 candidate → command drops it to `deferred` and
  flags the schema violation in the report.
- Evidence list empty (caller bug) → scout returns empty schema, does not
  go looking for files.

## 12. Manual validation steps

Same throwaway `BINDLE_NOTES_DIR` recipe as packet 2 §12, run twice: once
with `agents/knowledge-scout.md` installed (`bin/install.sh`), once with it
temporarily removed from the install target; diff the resulting `map.md`s —
they must be identical for identical confirmations.

## 13. Paste-ready implementation prompt

```
You are working in the Bindle repo on branch docs/81-knowledge-promotion-design.
Read docs/plans/2026-07-11-knowledge-promotion-p3-scout.md,
docs/knowledge-promotion.md, and commands/promote-knowledge.md in full.
Implement packet 3 exactly: agents/knowledge-scout.md per the packet's §4
(tools: Read, Grep, Glob — no Bash), the single delegation paragraph in the
command's step 6, the capabilities.json agent row, and the CHANGELOG line.
The candidate schema comes from docs/knowledge-promotion.md — do not
redefine it. Validate per §12 with a throwaway BINDLE_NOTES_DIR. Run
make check and make test; commit
"feat: knowledge-scout agent (draft) + command delegation (#81)" only if
green. Do not push.
```

## 14. Recommended model strength

Mid-strength is sufficient — the agent file transcribes an existing
contract; the judgment lives in packet 1.

## 15. Weaker-model safety

Safe for a weaker model with one caveat: verify the `tools:` line and the
"one fenced YAML block" output rule by reading the produced file, not the
implementer's claim.

## 16. Definition of done

§9 green, one commit, nothing pushed; packet-2 behavior unchanged when the
agent is absent.
