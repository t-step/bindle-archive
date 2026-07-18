---
description: Author and review context-graph semantic proposals over the deterministic CLI (init / preview / candidates / propose / confirm / apply)
argument-hint: <init | config | preview | candidates | propose | confirm | apply> [args]
allowed-tools: Bash(python3:*)
---

<!-- Conventions and the full authority contract live in the `context-graph`
     skill — read it first. The skill is a proposal producer and interaction
     layer only; the deterministic CLI (bin/context-graph.py) is the sole
     authority for endpoint legality, candidate keys, identity, and
     acceptance. This command is a thin entry point into that skill. -->

Invoke the `context-graph` skill to run the requested verb. Argument, if any:
"$ARGUMENTS"

Ground rules — the contract, not suggestions (the skill states them in full):

- **This skill proposes; it never decides.** Endpoint legality, candidate
  keys, IDs, and acceptance belong to the CLI. Never judge legality, mint a
  key, or call a proposal a validated candidate before `propose` says so.
- **Never repair a rejected proposal** into a different valid one — surface the
  CLI's `findings` verbatim and take the user's direction.
- **Never infer project identity** from the repo or Git remote; display and
  pass through the configured `--project <slug>` / opaque `project_id`.
- **`confirm` and `apply` are mutating and need the user's explicit
  selection** — accept/reject/retire and apply are the human's call, not the
  model's.

Steps:

1. Locate the Bindle checkout (`readlink ~/.claude/commands/context-graph.md`,
   repo root two levels up from the target) so you can run
   `python3 <bindle>/bin/context-graph.py`. If missing, tell the user to run
   the CLI from their Bindle checkout by hand.
2. Read the `context-graph` skill and follow it for the named verb.
3. Default with no argument: run `preview` (read-only) and summarize the graph,
   then ask what the user wants to propose or review.
