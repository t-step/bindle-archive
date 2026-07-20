# CodeGraph chaining guard — design

**Status:** proposed
**Date:** 2026-07-19

## Problem

`global/CLAUDE.md:26` gates CodeGraph on a 6+-file threshold. It landed in
`3b0f707` on 2026-07-16. Six days of Valence transcripts say the rule is not
changing behavior.

Measured over all Claude Code transcripts under
`~/.claude/projects/-Users-thomasestep-Developer-Valence/`, recursively
(275 calls; token figures are `chars/4` proxies, consistent within the series):

| | pre-rule (≤07-16, n=71) | post-rule (≥07-17, n=204) |
|---|---:|---:|
| p50 tokens/call | 5,668 | 5,572 |
| calls at the ~5.8k cap | 48% | 42% |
| total spend | 388,759 | 1,099,270 |
| next tool is an edit | 3% | 1% |
| search or Read within 3 calls | 69% | 84% |
| another CodeGraph call within 3 | 61% | 46% |

Total: **1,488,028 tokens across 275 calls, 4 of which (1%) were followed by an
edit.** The flat-fee cost model the rule is built on is confirmed exactly. What
the rule has not done is reduce the calls.

Post-rule spend splits by caller:

| agent | calls | tokens | had the rule in context? |
|---|---:|---:|---|
| `Explore` | 93 | 504,441 | **no** — built-in `Explore`/`Plan` skip CLAUDE.md by design |
| `general-purpose` | 53 | 286,340 | yes |
| main session | 50 | 266,846 | yes |
| `fork` | 8 | 41,642 | yes |

Two conclusions, both load-bearing:

1. **`Explore` is the single largest consumer (46% of post-rule spend) and is
   structurally unreachable by CLAUDE.md.** No amount of editing
   `global/CLAUDE.md` will ever reach it.
2. **The other 54% had the rule and behaved identically** — same chaining, same
   84% grep-anyway rate, same ~1% termination into an edit. Prose lost where it
   was present.

So the remedy cannot be more prose. It has to be a mechanism the harness
enforces, which for tool calls means a `PreToolUse` hook.

Caveat on (1): rule availability is inferred from documented `Explore`/`Plan`
behavior, not observed. CLAUDE.md injection is not persisted in transcript
records, so transcripts can neither confirm nor refute it for any agent. The
design does not depend on the inference — the guard reaches every agent
regardless of what any of them can read.

## What the guard enforces

**Allow the first CodeGraph call. Deny when the immediately preceding tool call
in the same transcript was also a CodeGraph call.**

This targets chaining specifically, which is the measured pathology: another
CodeGraph call is the single most common successor to a CodeGraph call (78 of
204 post-rule), 61 of 98 transcripts made 2+ calls, 11 made 6+, and the worst
single subagent made 13 calls for 67,792 tokens.

It deliberately does **not** try to enforce the 6+-file threshold itself. A hook
cannot know how many files an agent would otherwise have opened; that judgment
stays in CLAUDE.md prose, where it is at least correct even if under-obeyed. The
hook enforces the one thing that is mechanically decidable from the transcript
and that accounts for the largest share of waste.

### Scope

Both invocation paths, mirroring how `nested-notes-guard.py` covers both Bash
`gh` and GitHub MCP:

- MCP: `tool_name` matching `mcp__.*codegraph.*`
- Bash: a `command` containing `codegraph explore`

### Escape hatch

A `cg-chain-ok` marker anywhere in the query or command allows the call through.
Chained calls are sometimes right — a genuinely wide orientation sweep across
several subsystems is exactly the case CodeGraph wins. The marker makes that an
explicit, greppable assertion rather than a silent default, the same shape as
`nested-notes-exempt`.

## Mechanism

The hook is scoped by matcher to CodeGraph tools only, so it never observes the
intervening tool calls it needs in order to judge "consecutive". Two ways to get
that information:

**Rejected: a state file keyed on session.** Requires matching `.*` to record
every tool call, which pays Python startup on every single tool use in every
session, for a guard that fires on a handful of them. It also introduces stale
state, concurrency between parallel subagents sharing a session id, and a
cleanup problem.

**Chosen: read the transcript.** `PreToolUse` input carries `transcript_path`.
The guard reads the tail of that JSONL, finds the most recent prior `tool_use`
entry, and denies if it was also a CodeGraph call. No state to persist, nothing
to clean up, no cross-session leakage, and it works identically inside subagent
transcripts because each subagent has its own transcript file. The transcript is
already the authoritative record of what just happened.

Reading is bounded — the guard scans only the last N lines, since the answer only
ever depends on the most recent tool call.

## Failure posture: fails OPEN

An unreadable, absent, or unparseable transcript **allows** the call.

This is the opposite of the choice `#264` made for the nested-notes MCP path, and
the contrast is intentional. That guard fails closed because passing a write it
could not judge was precisely the hole it was filed to close — the cost of a
false allow there is unreviewable prose landing on a maintainer-facing issue.

Here the asymmetry runs the other way. The cost of a false allow is ~5.5k
tokens. The cost of a false deny is a blocked legitimate orientation query, in
a subagent, mid-task, with a confusing error. This is an efficiency gate, not a
correctness gate, and an efficiency gate that can wedge real work is worse than
one that occasionally leaks.

Per `#264`, the wire-up carries no `|| true`: only exit code 2 blocks a
`PreToolUse` call, so a missing hook already fails visibly without blocking
anything.

## Files

| file | change |
|---|---|
| `global/hooks/codegraph-chaining-guard.py` | new — the guard |
| `bin/test-codegraph-chaining-guard.sh` | new — self-test |
| `bin/install-session-hooks.sh` | register the new `PreToolUse` entry |
| `bin/doctor.sh` | report its wiring alongside the nested-notes guard |
| `capabilities.json` | record the capability; `make check` reconciles |
| `global/AGENTS.md` | fix the contradicting Codex guidance (below) |

## Companion fix: `global/AGENTS.md` drift

`global/AGENTS.md:80-89`, inside a `CODEGRAPH_START`/`CODEGRAPH_END` marker
block, still instructs:

> reach for it BEFORE grep/find or reading files

That is the pre-measurement advice and the direct opposite of
`global/CLAUDE.md:26`. Codex sessions are being told to do the thing this repo
measured as wasteful. Rewrite the block to the 6+-file threshold so the two
global-guidance files agree.

The block is marker-delimited and may be vendor-regenerated; if it is, the fix
will need to move upstream or the markers will need to be dropped. Noted, not
solved here.

## Testing

`bin/test-codegraph-chaining-guard.sh`, following the hermetic pattern of
`bin/test-nested-notes-guard.sh` — synthesized `PreToolUse` payloads plus
synthesized transcript fixtures in a temp dir, never a real transcript.

Cases:

- no prior tool call → allow
- prior tool call is a Read → allow
- prior tool call is a CodeGraph MCP call → **deny**
- prior tool call is a Bash `codegraph explore` → **deny**
- prior CodeGraph call with `cg-chain-ok` in the current query → allow
- prior CodeGraph call, then a Grep, then this call → allow (not consecutive)
- transcript path missing → allow (fails open)
- transcript malformed / not JSONL → allow (fails open)
- non-CodeGraph tool → allow (untouched)

**Mutation pass**, per the repo rule that a new gate must be proven failable:
invert the consecutive check and confirm the deny cases flip to allow.

## Open, deferred

The counterfactual A/B — same question answered CodeGraph-first vs grep-first,
with grep-exhaustive as recall ground truth — remains unrun. This design
measures CodeGraph's cost and its chaining behavior; it still does not measure
what the grep path would have cost on the same questions. Deferred by decision,
not by oversight.
