---
name: context-graph
description: Use when reviewing, drafting, or confirming semantic relationships in a Bindle context graph, or when the user runs `/context-graph <verb>` — an optional authoring layer over the deterministic context-graph CLI (init / preview / candidates / propose / confirm / apply). It drafts proposals and drives the CLI; it is never the authority for endpoint legality, candidate keys, identities, or acceptance. Not for building the graph's deterministic tooling itself (that is the CLI, issues #180/#183/#184/#185).
---

# context-graph (optional authoring skill)

## STOP — what this skill is, and is not

This skill is a **semantic proposal producer and interaction layer** over the
context-graph CLI (`bin/context-graph.py`, epic #140). It helps a human author
and review relationship proposals and drives the CLI verbs. It is **never a
candidate authority.**

The deterministic CLI is the sole authority. The skill defers *every* semantic
decision to it and mints nothing itself:

- **Endpoint legality** is decided by `propose` (the `relationships.py`
  endpoint matrix), never by this skill.
- **Candidate keys, subject keys, dependency fingerprints, anchor targets,
  entry fingerprints, assigned IDs** are computed by the CLI, never by this
  skill.
- **Acceptance** happens only when a human runs `confirm`; model confidence,
  repeated suggestions, or explanation quality are never acceptance.

If this skill and the CLI ever disagree, the CLI wins. A proposal the CLI
rejects is rejected — never "repaired" by the skill into a different valid one.

## The skill MAY

- inspect the current deterministic graph (`preview`) and existing candidates
  and judgments (`candidates`);
- draft semantic edge proposals carrying `source`, `relationship`, `target`,
  `basis`, `explanation`, optional `uncertainty`, and `producer: "skill"`;
- present compiler-issued identity-anchor candidates **without altering them**;
- present validation results and collect the human's review selections;
- invoke the CLI's `propose`, `confirm`, and `apply` verbs.

## The skill MUST NOT

- call its own output a *validated candidate* before `propose` validates the
  proposal shape;
- compute or override canonical candidate keys, subject keys, or fingerprints;
- synthesize anchor targets, entry fingerprints, anchor candidate keys, or
  assigned IDs;
- emit deterministic graph edges (those are the compiler's, from evidence);
- treat model confidence, repeated suggestions, or explanation quality as
  acceptance;
- write judgments directly, or bypass endpoint, relationship, basis, or
  staleness validation;
- silently repair an invalid proposal into a different valid one.

## Invoking the CLI

Every verb runs the deterministic tool in your Bindle checkout:

```
bindle context <verb> --project <slug> [verb args] [--format json]
```

`--format json` is the default and is what you parse. `bindle context` defaults
the notes home from `BINDLE_NOTES_DIR`, then `~/.bindle`; pass
`--notes-home <notes-home>` for an explicit override. The direct helper
`python3 <bindle>/bin/context-graph.py ...` remains supported for compatibility
and debugging. `<slug>` identifies the project (see **Project identity** below).
Surface the CLI's own JSON findings to the user — do not paraphrase a rejection
into a softer one.

| Verb | Purpose | Skill's role |
|---|---|---|
| `init` | allocate a project identity, write `config.json` | run only on explicit user intent to create a project; never to "fix" a missing id |
| `config <status\|validate\|add-repository\|…>` | inspect/edit repository bindings | help the user pick/edit bindings; never infer identity |
| `preview` | read-only deterministic compile (#183) | inspect nodes/edges/anchors/coverage to ground a proposal |
| `candidates` | live anchors + reduced judgment ledger | show what is pending/accepted/rejected |
| `propose` | validate one proposal → candidate | the legality + key authority; see below |
| `confirm` | append one judgment under lock (#184) | run on the user's explicit accept/reject/retire selection |
| `apply` | materialize map/index/context (#185) | run on the user's explicit request |

## Authoring a semantic proposal (the `propose` flow)

1. Ground the proposal in `preview`: the `source` and `target` must be real
   node IDs in the current graph (the CLI resolves their class+kind from the
   preview — you never assert them yourself).
2. Write a `proposal.json` envelope with `producer: "skill"`:

   ```json
   {
     "source": "context-node:bindle:…",
     "relationship": "supports",
     "target": "context-node:bindle:…",
     "basis": [],
     "explanation": "why this relationship holds",
     "producer": "skill"
   }
   ```

   Optional `uncertainty` (free text) is provenance only — it never changes the
   candidate. Never set `advisory_candidate_key` to a value you computed; the
   CLI rejects a mismatched advisory key rather than trusting it.
3. Run `propose --input proposal.json`. Read `{candidate, subject_key,
   findings}`:
   - **`candidate` is null** → the proposal is rejected. Surface the exact
     `findings` (e.g. `E_PROPOSAL_ILLEGAL_ENDPOINT`,
     `E_PROPOSAL_UNKNOWN_ENDPOINT`) as the discard explanation. Do not retry
     with a silently-changed relationship or endpoints; take the user's
     direction instead.
   - **`candidate` is present** → present it for review showing **source kind,
     relationship, and target kind** (`source_kind` / `relationship` /
     `target_kind` from the candidate) so the semantics are visible. This is a
     *proposal the CLI validated*, not an accepted edge — nothing enters the
     graph until `confirm`.
4. On the user's explicit acceptance, run `confirm --candidate-key <the key
   from propose's output> --decision accepted --input proposal.json`. Use the
   CLI-emitted key verbatim — never a key you constructed. `confirm`
   re-validates against the current graph; a mismatch is the CLI's to report,
   not yours to paper over.

## Ontology safety (the endpoint matrix is the CLI's, not a copy)

The legal (source-kind, relationship, target-kind) combinations are defined by
the deterministic tooling. This skill holds **no private copy** of the matrix
as authority — it lets `propose` decide, and it applies these rules only to
avoid drafting proposals it knows the CLI will reject:

- **Never offer the reserved `implements` relationship** — it is not part of
  v1 and the CLI rejects it. Implementation attribution uses
  `decision --implemented_by--> github_pr`.
- **Reversed `contradicts` normalizes to one canonical candidate.**
  `contradicts` is symmetric; `propose` canonicalizes endpoint order, so
  `A contradicts B` and `B contradicts A` return the *same* `candidate_key`.
  Present one canonical candidate, never two.
- **Invalid combinations are discarded with the CLI's visible validation
  explanation** and never reach `confirm`.
- **Direct-CLI and skill-assisted paths return identical validation failures**
  for the same illegal proposal — because both run the same `propose`. This is
  the guarantee that no provider can bypass, reinterpret, or silently repair
  endpoint legality. If you ever find yourself deciding legality without
  `propose`, stop: that is the bug this skill exists to prevent.

## Project identity (display and pass through — never infer)

A Bindle project is identified by an **opaque `project_id`** allocated once by
`init` and stored in `config.json`, plus a human-facing `--project <slug>`. The
skill **displays and passes identity through**; it never derives or invents it.

The skill MUST NOT:

- derive project identity from the current repository or its Git remote;
- allocate or replace a `project_id` (only `init` does, on explicit intent);
- treat `owner/repo` as equivalent to a Bindle project;
- silently choose a repository for an ambiguous bare reference — ask the user;
- make repository access a prerequisite for repositoryless project operation.

The skill MAY help the user select among *configured* repository bindings
(`config add-repository` / `set-default` / `--repo-root ALIAS=PATH`). A project
with zero repositories is fully usable; every verb takes `--notes-home` and
`--project` explicitly and runs from any directory, independent of any checkout.

## CLI equivalence

This skill is a convenience, not an authority. A human can hand-write the same
`proposal.json` and run the same `propose` / `confirm` / `apply` commands and
get an identical result; a `producer: "fixture"` file does the same. The
`candidate_key` is computed from `source`, `relationship`, `target`, and
`basis` only — so equivalent human, skill, and fixture proposals reduce to the
**same** candidate, differing only in the recorded `producer` provenance. That
equivalence is what `<bindle>/bin/test-context-graph-skill.sh` proves and what
graduation depends on.
