---
description: Promote project evidence into the living project map — propose, confirm, write
argument-hint: [project slug; default = current repo's project]
allowed-tools: Bash(ls:*), Bash(date:*), Bash(wc:*), Bash(mkdir -p:*), Bash(git rev-parse:*), Bash(gh issue view:*), Bash(gh pr view:*)
---

<!-- The contract (ladder, map format, rules, report shape):
     Bindle's docs/knowledge-promotion.md. This command automates it. -->

Promote accumulated evidence for one project into its living map. Project,
if given: "$ARGUMENTS" (default: the current repo's project).

**On any conflict between this command and `docs/knowledge-promotion.md`,
the contract doc wins — and the conflict is a bug to report.**

Steps:

1. Read the `session-continuity` skill (notes-home resolution) and
   `docs/knowledge-promotion.md` (the contract — ladder, map format,
   promotion/update rules, report shape). Today: !`date +%F`
2. Resolve the project: `$ARGUMENTS` if non-empty; else the basename of
   `git rev-parse --show-toplevel` (plain `pwd` outside a repo), slugified
   via `bin/slugify.sh` when the Bindle repo is reachable, else by the
   documented slug rule.
3. Read `projects/<project>/map.md` if it exists; note the
   `evidence through:` cursor. No map → this is a **bootstrap** run
   (contract: Cursor semantics).
4. Enumerate evidence newer than the cursor: `sessions/*.md` and
   `handoffs/*.md` by date-stamped filename, `profile.md` by mtime. If
   there is none: say "nothing new since <cursor>" and stop — write
   nothing.
5. Read the evidence. For issues/PRs the notes reference, use
   `gh issue view` / `gh pr view` read-only when `gh` is available; skip
   silently otherwise. **Read-only toward every repository — no
   exceptions.**
6. Generate candidates and screen them with the contract's promotion rules
   (novelty with the cited check target, consequence, durability,
   evidence, uncertainty, routing) and the volume guard (≤5 proposals,
   ranked per the contract; bootstrap exempt up to the map's size budget).
   When the `knowledge-scout` agent is installed, delegate this step to
   it — pass the contract-doc path, the map's current entries, the
   explicit evidence file list, and any issue/PR extracts inline; require
   back one fenced YAML block in the contract's candidate schema. If the
   agent is missing or its reply doesn't parse as that schema, fall back
   to doing this step inline and note the fallback in the report; a
   schema-violating rung-6 candidate is demoted to deferred and flagged.
   Either way, classify everything into the contract's report shape:
   candidates / rejected (with the rule) / deferred (with what's missing)
   / relitigation flags.
7. Present the promotion report. Each proposal, numbered 1–N: the complete
   entry text as it would appear in the map (fenced) plus its anchor — the
   target section and, for update/supersede actions, the existing claim
   line being modified. State the ranking used. Then Rejected, Deferred,
   and Relitigation, one line each.
8. Ask for confirmation: `all`, `none`, or a list of the presented
   numbers. Anything else: re-ask once, then treat as `none`. On a
   bootstrap run, create `map.md` once, from the contract's template with
   the confirmed entries (if any) in place. On later runs, apply exactly
   the confirmed subset as minimal Edit operations — never regenerate an
   existing file, never touch lines outside the named entries; re-add a
   missing `##` section header if the confirmed write needs it.
9. Advance the cursor line to the newest processed session note and update
   `updated:` — announce it, don't ask (contract rule). If the run was
   interrupted before step 8 completed, write nothing at all, cursor
   included.
10. Close with one line: N promoted, M rejected, K deferred, cursor now at
    `<file>`. If any candidate was rejected by the routing rule, remind:
    operational facts go through `/promote-insight`; workflow friction
    through `/workflow-review`.

The map stays private in the notes home; never copy evidence bodies into
it (one-line quotes maximum), and never write into any project repository.
