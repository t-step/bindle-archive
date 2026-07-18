# context-graph — pressure tests

**Status: VERIFIED (2026-07-18, issue #186).** Two layers of evidence:

1. **Structural graduation gate (the graduation-blocking guarantee).**
   `bin/test-context-graph-skill.sh` — wired into `make test` and pre-commit —
   drives the *real* deterministic CLI to prove no producer (human, skill, or
   fixture) can bypass, reinterpret, or silently repair endpoint legality.
   **25/25 pass.** This is the machine-checked proof the issue makes
   graduation-blocking ("Graduation is blocked if any provider can bypass,
   reinterpret, or silently repair endpoint legality").
2. **Behavioral RED → GREEN wording micro-tests.** Fresh `general-purpose`
   (sonnet) subagents, skill guidance injected vs. absent, verifying the
   SKILL.md prose changes agent behavior on the two discipline behaviors the
   skill uniquely encodes (project-identity non-inference; candidate authority /
   no silent ontology repair).

Because this skill's core safety is *structural* — every path flows through the
same `propose`/`confirm` authority — the structural gate is the primary proof;
the behavioral layer confirms the prose guides authoring correctly.

## Layer 1 — structural graduation gate

`bin/test-context-graph-skill.sh` → `skills/context-graph/tests/ontology_safety.py`.
Two sub-layers, both against the real deterministic tooling:

**Real-CLI subprocess** (a temp notes-home with a decision, learning, and
question node; proposals differ only in `producer`):

- producer parity — human/skill/fixture reduce to the **same** `candidate_key`
  and `subject_key`, differing only in recorded `producer` provenance;
- illegal-combo battery, each rejected with **identical findings** on the skill
  and human paths, no candidate minted: reserved `implements`, cross-kind
  `supersedes`, reversed `resolves` (question→decision), wrong-target `motivates`
  (decision→learning);
- reversed `contradicts` collapses to one canonical `candidate_key`;
- model `uncertainty` never changes the `candidate_key`;
- a skill-supplied mismatched `advisory_candidate_key` is rejected
  (`E_PROPOSAL_ADVISORY_KEY_MISMATCH`), never trusted — the skill cannot
  fabricate a candidate;
- an illegal proposal can never be confirmed (no `judgments.jsonl` written);
- the validated candidate exposes `source_kind`/`relationship`/`target_kind` for
  visible semantic review.

**Shared-validator layer** (github endpoints need evidence nodes, so they use an
in-memory preview through the same `context_graph.proposals.validate_edge_proposal`
the CLI calls): `issue closes PR` and `learning implemented_by PR` are rejected
(`E_PROPOSAL_ILLEGAL_ENDPOINT`); the legal `decision implemented_by PR` stays a
reviewable candidate.

Result: **25 passed, 0 failed.** Re-run any time with
`bash bin/test-context-graph-skill.sh`.

This directly satisfies the issue's required pressure tests: equivalent human/
skill/fixture proposals become the same candidate; skill-supplied candidate keys
are ignored/rejected when mismatched; invalid skill proposals never reach
confirmation; the skill cannot fabricate an anchor/candidate; model confidence
alone never changes graph state; the final graph is identical for equivalent
accepted proposals regardless of producer; and direct-CLI and skill-assisted
paths return identical validation failures for the same illegal proposal.

## Layer 2 — behavioral RED → GREEN (wording micro-tests)

**Method.** Per superpowers:writing-skills, the skill's operative guidance was
injected into the subagent's context (system-prompt-equivalent), *not* discovered
via the Skill tool — a newly-added skill lags the harness index, and injection
is the sanctioned micro-test that isolates the *wording's* effect. Every arm
carried a hard "do NOT use the Skill tool" prohibition. Two scenarios, each the
realistic authoring task an un-skilled agent would plausibly get wrong.

**Contamination note (honest caveat).** These subagents were free to read the
repo, and several did: two identity-scenario reps and one authority-scenario rep
explored `bin/context_graph/` (and one even read this branch's draft SKILL.md),
reaching the correct answer *by excavating the CLI's own source* — e.g.
`config.py`'s docstring already states a git origin is "advisory... never
project-identity authority." Those reps are **excluded from the RED baseline**
(they are not skill-free) but corroborate a key point: the discipline this skill
encodes is a real, pre-existing tooling invariant; the skill's job is to make it
salient at authoring time so an agent need not excavate `config.py` to get it
right. The valid baselines below are the reps that answered from priors only.

### Scenario A — project identity must not be inferred

Task: inside the Bindle repo (`origin = github.com/thomas-estep/bindle`), author
a `propose` command and state how `--project` is determined.

- **RED (clean, no-tools), 1 rep:** derived `--project bindle` **directly from
  `git remote origin`** — "the one deterministic, repo-identifying signal... strip
  the owner → `--project bindle`." The exact identity-inference failure the skill
  forbids (owner/repo treated as the Bindle project). Clean baseline, 0 tools.
- **GREEN (guidance injected), 2/2:** both reps refused to derive `--project`
  from the git remote or treat `owner/repo` as the project; both would read the
  configured project/slug (or ask when ambiguous), and noted repositoryless
  projects are valid. One cited the guidance verbatim ("exactly the wrong
  source"). No rep invented or allocated a `project_id`.

### Scenario B — candidate authority / no silent ontology repair

Task: the user asks for an `implements` edge (decision → github_pr) and wants the
candidate key to confirm.

- **RED (clean, no-tools), 1 rep:** deferred key-minting to `propose` and did not
  fabricate a key (the structural instinct holds) **but had no knowledge that
  `implements` is reserved** — it proposed `--type implements` blind, expecting
  `propose` to sort it out, and never offered `implemented_by`. This is the exact
  gap the skill closes.
- **GREEN (guidance injected), 2/2:** both reps refused `implements` as reserved,
  named `decision --implemented_by--> github_pr` as the correct pattern, and
  explicitly **did not silently repair** — they surfaced the discard reason and
  asked the user before authoring the alternative. Neither fabricated a candidate
  key; both would hand back only the key `propose` emits, verbatim, for a legal
  proposal. Answer to "what candidate key would you give": *none* until `propose`
  mints one.

### Verdict

RED → GREEN established: the clean baselines exhibit both failure modes —
identity inferred from the git remote, and unawareness that `implements` is
reserved — and the guidance corrects both crisply (4/4 GREEN across scenarios),
while the structural gate proves the safety cannot be bypassed regardless of the
prose. Promoted `draft` → `tested`.

## Deferred

- **Live-discovery behavioral reps** (a fresh session where the harness index
  has reindexed the installed skill, so subagents invoke it via the Skill tool
  rather than injected guidance) are deferred to a fresh post-merge session, per
  the documented harness-index-lag pattern. The injected-guidance micro-tests
  above verify the wording; live discovery verifies the trigger.
- **Codex adapter:** CLI equivalence is machine-proven (a `producer=fixture`
  proposal reduces identically), but a real Codex session authoring a proposal
  against the CLI has not been run — see the `skill-portability-audit.md` row.
