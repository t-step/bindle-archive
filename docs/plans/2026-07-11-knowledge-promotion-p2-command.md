# Packet 2 — the /promote-knowledge command

Implements the Claude automation of `docs/knowledge-promotion.md` (created
by packet 1 — a forward reference, so not a link here) per
[`docs/design/2026-07-11-knowledge-promotion.md`](../design/2026-07-11-knowledge-promotion.md)
(issue #81, wave 1).

## 1. Objective

Create `commands/promote-knowledge.md`: a slash command that runs the full
contract workflow — resolve, read evidence after the cursor, generate and
screen candidates, propose ≤5 exact diffs as a promotion report, apply only
what the user confirms, advance the cursor — with no dependency on any
agent.

## 2. Why this packet exists

The contract (packet 1) is followable by hand; this packet is the Claude
Code automation layer, mirroring how `/workflow-review` and
`/promote-insight` automate `docs/iterative-improvement.md`.

## 3. Dependencies

Packet 1 merged/committed on this branch (the command references
`docs/knowledge-promotion.md` and consumes its §7 shapes verbatim).

## 4. Exact scope

One new command file, one `capabilities.json` row, one `capabilities.json`
field update, one CHANGELOG line.

`commands/promote-knowledge.md` frontmatter:

```yaml
---
description: Promote project evidence into the living project map — propose, confirm, write
argument-hint: [project slug; default = current repo's project]
allowed-tools: Bash(ls:*), Bash(date:*), Bash(wc:*), Bash(mkdir -p:*), Bash(git rev-parse:*), Bash(gh issue view:*), Bash(gh pr view:*)
---
```

Command body — instruct Claude to execute exactly these steps (the file is
the prompt; write them as numbered instructions the way
`commands/session-end.md` does):

1. Read the `session-continuity` skill for notes-home resolution; read
   `docs/knowledge-promotion.md` — it is the contract; on any conflict
   between this command and that doc, the doc wins and the conflict is a
   bug to report.
2. Resolve the project: `$ARGUMENTS` if given, else the current repo's
   top-level directory basename (`git rev-parse --show-toplevel`; plain
   `pwd` outside a repo) piped through `bin/slugify.sh` when the Bindle
   repo is reachable, else the documented slug rule by hand.
3. Read `projects/<project>/map.md` if present; note the cursor. If
   absent, this is a bootstrap run (contract §cursor semantics).
4. Enumerate evidence newer than the cursor: `sessions/*.md`,
   `handoffs/*.md` by date-stamped filename, `profile.md` by mtime. If
   none: report "nothing new since <cursor>", stop — write nothing.
5. Read the evidence. For issues/PRs the notes reference, `gh issue view` /
   `gh pr view` read-only when `gh` is available; skip silently otherwise.
   **Read-only toward every repo — no exceptions.**
6. Generate candidates and screen them with the contract's six promotion
   rules and the volume guard; classify every surviving and non-surviving
   item into the contract's candidate schema (candidates / rejected /
   deferred / relitigation).
7. Present the promotion report: for each candidate the exact proposed map
   edit (a minimal diff against a named entry or a new entry in a named
   section), numbered 1–N (N ≤ 5; bootstrap exempt up to the size budget);
   then Rejected (one line + rule each), Deferred (one line + what's
   missing), Relitigation flags. State the ranking used.
8. Confirmation: ask the user to reply `all`, `none`, or a list of numbers.
   Apply exactly the confirmed subset as minimal Edit operations on
   `map.md` — never regenerate the file, never touch lines outside the
   named entries. On bootstrap with `none`, still create the map skeleton.
9. Advance the cursor line to the newest processed session note and update
   `updated:` — announced, not asked (contract rule). If the user
   interrupted before step 8 completed, write nothing at all.
10. Close with a one-line summary: N promoted, M rejected, K deferred,
    cursor now at `<file>`. Remind: wrong-kind insights (operational
    facts) go to `/promote-insight`; workflow friction to
    `/workflow-review`.

**Repository-compliance note** (pre-existing registration gate — see
packet 1's compliance note for the enforced field rules; paste verbatim,
no inventory knowledge needed):

```json
{
  "type": "command",
  "name": "promote-knowledge",
  "path": "commands/promote-knowledge.md",
  "description": "Promote accumulated project evidence into the living project map (docs/knowledge-promotion.md contract): propose at most five exact diffs, confirm, write, advance the cursor.",
  "maturity": "draft",
  "mutation": ["disk"],
  "provider": {"claude": "installed", "codex": "manual"},
  "version_introduced": "0.3.0"
}
```

`mutation` is a validator enum ({disk, network, external}); `disk` records
that the command writes files (the notes-home map). The row is
registration only — the actual write-scope rules (map.md only, confirmed
content only) live in `docs/knowledge-promotion.md` and this command.

Also update the packet-1 contract row's `provider.claude` from `"manual"`
to `"installed"` (keeps that row honest now that automation exists; not
gate-enforced).

CHANGELOG line under `### Added` (mark draft — pressure tests are
packet 4):

```markdown
- `/promote-knowledge` command (draft, pending pressure tests): runs the
  knowledge-promotion contract end-to-end for one project (issue #81,
  wave 1).
```

## 5. Explicit non-goals

- No agent file, no delegation logic beyond a placeholder-free inline
  analysis (packet 3 adds the scout integration paragraph).
- No `knowledge.md` / wave-2 writes; rung-6 candidates must be reported as
  deferred, never written.
- No session-end/session-start integration; no hooks; no cadence
  automation.
- No edits to `commands/workflow-review.md`, `commands/promote-insight.md`,
  or any existing command — the cross-references live inside the new
  command only.
- No installer or Makefile changes: `commands/*.md` is already an installed
  category; the new file rides the existing mechanism.

## 6. Expected files to add or modify

| File | Change |
|---|---|
| `commands/promote-knowledge.md` | new |
| `capabilities.json` | +1 command row; contract row `provider.claude` → `installed` |
| `CHANGELOG.md` | one `### Added` line |

## 7. Interfaces and data shapes

All consumed from the contract (packet 1 §7): map template, entry grammar,
cursor semantics, candidate schema, report format, ranking rule. This
packet defines nothing new; if implementation reveals a missing shape, the
fix goes into `docs/knowledge-promotion.md` first, then the command.

Confirmation grammar (the one interface this packet owns): the command
accepts exactly `all`, `none`, or a whitespace/comma-separated list of the
presented numbers; anything else → re-ask once, then treat as `none`.

Proposal rendering (also owned here): each numbered proposal shows the
complete entry text as it would appear in the map (fenced), plus its anchor
— the target section and, for `update`/`supersede` actions, the existing
claim line being modified with its old field values quoted. No unified
diffs; the fenced entry *is* what gets written on confirmation.

## 8. Step-by-step implementation plan

1. Confirm clean `git status --short`; branch
   `docs/81-knowledge-promotion-design`.
2. Write `commands/promote-knowledge.md` per §4 (frontmatter exact; body as
   numbered instructions; keep to the tone/length of
   `commands/session-end.md` — under ~90 lines).
3. Apply the two registration changes from §4's compliance note and the
   CHANGELOG line.
4. `make check`, `make test`.
5. Smoke-run manually (see §12) against a throwaway notes home.
6. Commit: `feat: /promote-knowledge command (draft) — map promotion loop (#81)`.

## 9. Acceptance criteria

- The command file exists, parses (frontmatter valid per `make check`'s
  frontmatter gate), and instructs all ten steps of §4 without contradicting
  `docs/knowledge-promotion.md`.
- Running it in a fixture notes home (§12) produces: a report with ≤5
  numbered proposals, application of only the confirmed subset, a cursor
  advance, and zero writes outside `map.md`.
- `none` on a bootstrap run still yields the skeleton map with cursor.
- The command never runs a mutating `gh`/`git` command and never writes
  into a project repo.
- `make check` + `make test` green.

## 10. Required tests

`make check` / `make test` (structural), plus the §12 smoke run. Full
behavioral scenarios are packet 4; do not build fixtures here beyond the
throwaway smoke run.

## 11. Failure and edge cases

- No notes home → `mkdir -p` per contract; proceed as bootstrap.
- `gh` absent/unauthenticated → skip issue/PR enrichment silently (contract
  step 5).
- Map hand-edited into an unexpected shape (missing section header) →
  re-add the header with the next confirmed write; never reorder.
- Map at hard cap → proposals must pair addition with a removal, else be
  deferred.
- User replies something unparseable at confirm → re-ask once, then `none`.
- Interrupt mid-run → no writes (including cursor).

## 12. Manual validation steps

```bash
export BINDLE_NOTES_DIR=$(mktemp -d)
mkdir -p "$BINDLE_NOTES_DIR/projects/demo/sessions"
# two synthetic notes: one consequential decision, one operational fact
# (copy the fixture text from packet 4 §fixtures if already written)
```

Run `/promote-knowledge demo` in a Claude session; verify: report shape,
`none` → skeleton map + cursor; re-run → "nothing new"; confirm-one →
exactly that entry added; `unset BINDLE_NOTES_DIR` afterwards. The real
notes home must never be touched — verify `~/.bindle` mtimes unchanged.

## 13. Paste-ready implementation prompt

```
You are working in the Bindle repo on branch docs/81-knowledge-promotion-design.
Read docs/plans/2026-07-11-knowledge-promotion-p2-command.md,
docs/knowledge-promotion.md, and docs/design/2026-07-11-knowledge-promotion.md
in full. Implement packet 2 exactly: commands/promote-knowledge.md per the
packet's §4, the capabilities.json row + contract-row provider update, and
the CHANGELOG line. The contract doc wins any conflict. Validate per the
packet's §12 with a throwaway BINDLE_NOTES_DIR — never touch the real notes
home. Run make check and make test; commit
"feat: /promote-knowledge command (draft) — map promotion loop (#81)" only
if green. Do not push. Do not create agents, fixtures, or wave-2 content.
```

## 14. Recommended model strength

Strong for the command body (it encodes judgment rules); the JSON/CHANGELOG
edits are mechanical.

## 15. Weaker-model safety

A mid-strength model can implement this safely *because* packet 1 fixed all
shapes — the command is a faithful transcription of the contract into
command-file form. Verify with the §12 smoke run scored on the filesystem,
not the transcript.

## 16. Definition of done

§9 all green, one commit, nothing pushed, real notes home untouched.
