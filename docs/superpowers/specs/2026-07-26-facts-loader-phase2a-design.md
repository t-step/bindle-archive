# Portable facts loader — Phase 2a design

**Status:** proposed
**Date:** 2026-07-26
**Issue:** #422 (Phase 2a; coupled to #423)
**Supersedes nothing.** Continues `docs/superpowers/specs/2026-07-23-converge-facts-store-design.md`.

## Problem

Phase 1 froze the canonical `facts/` format and made `profile.md` a runbook +
pointer index, so the on-demand tail now lives in `facts/<slug>.md` files. Every
mechanism that *surfaces* that tail is still missing:

- `/session-start` loads `profile.md`, the latest session note, and the latest
  handoff. It never enumerates `facts/`. A shed fact reaches context only if a
  pointer in `profile.md` happens to catch the agent's eye and it spends a read.
- The Claude Code harness injects the `MEMORY.md` **index** and nothing else —
  measured 2026-07-25, in a symlinked *and* a real `memory/` dir. Fact bodies are
  never auto-injected. So "Claude gets this for free" is false for bodies, and no
  agent has proactive access to the shed tail today.

Phase 1 therefore traded a monolith that loaded everything for an index that
loads nothing. That is the right trade only if something closes the gap; this is
that something.

The operator decided (2026-07-26, on #422) to build this loader **before**
choosing between the symlink and the drift-check for the store. This design
depends on neither: it reads the vault `facts/` directory directly, which exists
under both outcomes.

## Constraints

1. **Same behavior for both agents.** The 50/50 Codex constraint from the parent
   design is unchanged. The loader lives in Bindle's command layer, which Codex
   runs through the interop layer, so Claude and Codex get identical retrieval.
   Nothing here may depend on harness behavior.
2. **Do not re-create the monolith.** Loading every fact body every session is
   exactly the pathology Phase 1 removed. The loader must load the *index*
   wholesale and *bodies* selectively.
3. **Selection is the model's job; enumeration is the script's.** Bindle does not
   ship a relevance ranker. A bash keyword-scorer would be a worse retriever than
   the model reading one-line descriptions, and it would need its own tests,
   thresholds, and failure modes. The script lists; the model chooses.
4. **Read-only toward the notes home.** The loader never writes a fact, never
   bumps `modified`, never repairs frontmatter. Writing stays with `/session-end`;
   validation stays with #423.
5. **Degrade silently.** No notes home, no `facts/` dir, or an empty one is the
   normal state for a fresh project. The loader reports nothing and blocks
   nothing — the same posture as the session hooks.

## Design

### `bin/facts-index.sh` — deterministic enumeration

A read-only script that prints one line per fact, cheapest-possible form:

```
<slug><TAB><type><TAB><description>
```

- Resolves the notes home the same way the rest of Bindle does
  (`$BINDLE_NOTES_DIR`, deprecated `$CLAUDE_KIT_NOTES_DIR`, `~/.bindle`), and the
  project slug via `<bindle>/bin/slugify.sh` — no second slug rule.
- Reads only frontmatter `name`, `metadata.type`, and `description`. It never
  reads a fact body, so its cost is bounded by fact *count*, not fact size.
- Skips `MEMORY.md` (the harness's own index, not a fact).
- Exit 0 and no output when the directory is absent or empty. A malformed fact is
  listed with its slug and an empty description rather than skipped — an
  invisible fact is worse than an ugly line, and #423 is what makes it loud.

At ~100 facts this is ~100 short lines: comparable to what `profile.md`'s pointer
sections already cost, and it replaces prose pointers rather than adding to them.

### `/session-start` — a selection step

A new step, after the profile/session/handoff reads and before the summary:

1. Run `bin/facts-index.sh`.
2. Against the session objective (the command's existing `$ARGUMENTS`, or the
   next-step proposed by the latest handoff), select the facts whose
   descriptions bear on it.
3. Read those fact bodies — **at most 5**, and none at all when the session has
   no objective and no handoff next-step to aim at.
4. Name them in the ≤15-line summary, so the operator sees what was loaded and
   can say "not that one."

Step 3's cap is the whole budget story: index always, bodies rarely, and a
visible list of what was pulled.

### Relationship to `profile.md` and `MEMORY.md`

Three surfaces, no restatement, unchanged from the parent design: `profile.md` is
the curated hot core an agent always loads, `MEMORY.md` is the harness's flat
auto-index, and `facts/` is the store both point into. The loader adds a fourth
behavior — *selective body loading* — and no fourth copy of anything.

## Verification

Per `docs/pressure-testing-protocol.md`, graded on the transcript, not the
self-report. Claims this design must earn before the skill loses its **draft**
marker:

- **C1** — With an objective that a shed fact bears on, a session loads that fact
  body and cites it. RED arm: the same session without the loader step does not.
- **C2** — With an objective unrelated to the shed target fact, a session loads
  **strictly fewer bodies than the cap** and states each loaded fact's bearing on
  the objective (the cap is not a quota to fill). **Reworded 2026-07-26 (#457),
  after the pilot, from "unrelated to every fact … loads no fact bodies."** The
  original wording is unmeetable against a real store: process facts (branch
  protection, review rules, publication surfaces) bear on *any* objective, so
  "unrelated to every fact" is not a state a populated notes home admits. The
  pilot's C2 rep loaded two such facts, each with its bearing stated, and was
  recorded a FAIL under the old wording. See `PRESSURE-TESTS.md` Claim 9 for the
  full record — including the fact that the threshold moved after the result was
  known.
- **C3** — With no objective and no handoff next-step, no bodies are loaded.
- **C4** — With no notes home at all, `/session-start` completes and says nothing
  about facts.

`bin/facts-index.sh` gets a `bin/test-facts-index.sh` suite over throwaway
fixture notes homes (absent dir, empty dir, well-formed facts, a fact with
malformed frontmatter, `MEMORY.md` present). `git add` the suite before trusting
the discovered-suite count.

## Out of scope

- **Phase 2b — the store decision** (symlink vs. two stores plus a drift check).
  Deliberately deferred; this loader is unregretted under either.
- **The frontmatter lint (#423).** The loader tolerates malformed facts and makes
  them visible; enforcing the schema is that issue's job.
- **Any derived index (SQLite or otherwise).** Markdown stays canonical; at ~100
  facts a `grep`-speed enumeration is not a bottleneck.
- **Writing or repairing facts.** `/session-end` owns writes.
- **Ranking, embeddings, or scoring in Bindle code.** See constraint 3.

## Open calls Bindle owns

- **The body cap (5).** Chosen to be visibly small; the pressure-test C2 arm is
  what would show it is wrong in either direction.
- **Whether `/session-end` also consults the index** to notice that a fact it is
  about to write already exists. Plausible, unscoped here.
- **Whether the loader eventually replaces `profile.md`'s pointer lists** — if the
  index is loaded every session anyway, a pointer list is a second copy of the
  same slugs. Not touched in 2a: it would change the seven-section contract.

## Success criteria

- `bin/facts-index.sh` enumerates a real notes home correctly and its suite is
  discovered and green.
- `/session-start` names the facts it loaded, loads none when nothing is relevant,
  and is silent on a machine with no notes home.
- C1–C4 recorded in `skills/session-continuity/PRESSURE-TESTS.md` at the repo's
  rep bar, or the change stays marked **draft**.
- No fact content is duplicated into `profile.md`, `MEMORY.md`, or the command.
