# context-graph — pressure tests

**Status: VERIFIED (2026-07-18, issue #186).** Three layers of evidence:

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
3. **Live-discovery behavioral reps (post-merge).** Fresh subagents in a session
   where the harness had reindexed the *installed* skill, invoking it through the
   **Skill tool** (no injected guidance), graded from raw transcripts. Confirms
   the trigger fires and the wording holds behavior end-to-end. See Layer 3.

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

## Layer 3 — live-discovery behavioral reps (post-merge, 2026-07-18)

The Layer-2 live-discovery deferral (below) is **discharged**. In a fresh session
after PR #209 merged the skill to `main` and the post-merge hook symlinked it into
`~/.claude/skills/context-graph`, the harness reindexed it and subagents discover
it through the **Skill tool** — not injected guidance. Both scenarios were re-run
as live-discovery reps and graded from the subagents' raw JSONL transcripts
(`grep '"name":"Skill"'` for a real invocation), never from their self-reports.

**Method.** Fresh `general-purpose` (sonnet) subagents, one realistic authoring
task each, the skill *not* named and no tool prohibition — the point is to see
whether the trigger fires on its own. Two-axis grade: (1) *discovery* — did the
transcript carry a real `"name":"Skill"` call loading `context-graph`
(`Launching skill: context-graph`)? (2) *behavior* — did the answer hold the
discipline the skill encodes?

**Discovery probe (1 rep).** A "review and confirm a pending candidate" task.
Transcript: exactly one `"name":"Skill"` call —
`{"skill":"context-graph","args":"review and confirm a pending candidate"}` —
plus `Launching skill: context-graph`, the only non-Bash tool. Skill discovered
and loaded autonomously. Gate passes.

**Scenario A — project identity must not be inferred (5 reps).**

| Rep | Skill tool fired | Behavior |
|---|---|---|
| A1 | yes (context-graph + notes-home) | PASS — "never derive it from repo name, git remote, or branch"; refused to guess a slug |
| A2 | yes | PASS — refused to derive slug, cited `config.py:97`, won't `init` unprompted |
| A3 | **no** (11 Bash; read SKILL.md/source directly) | PASS — refused git-remote inference |
| A4 | yes | PASS — read configured `project_slug: bindle` from `config.json`, explicitly disavowed the git remote |
| A5 | yes | PASS — refused remote/repo-name inference, resolved the slug via `config.json` lookup; ran a validate-only `propose`, no mutation |

5/5 behavior PASS; 4/5 reached the answer through the Skill tool. A3 is the honest
outlier: it never invoked the skill, answering correctly by excavating the CLI
source — the same contamination pattern Layer 2 flagged. **Environment note:** A4/A5
ran later the same day, *after* this session's dogfood `init`'d the `bindle`
project, so `config.json` now exists — they correctly read the **configured** slug
rather than hitting `config: null`, and both still explicitly disavowed git-remote
inference (the discipline holds whether or not a config is present).

**Scenario B — reserved `implements` / no silent repair (5 reps).**

| Rep | Skill tool fired | Behavior |
|---|---|---|
| B1 | yes | PASS — rejected `implements`, named `implemented_by`, refused to mint a key without real nodes |
| B2 | yes | PASS — rejected `implements` (cited endpoint-matrix fixtures), refused to `init` or invent keys |
| B3 | yes (**Skill-only, no Bash**) | PASS — quoted the reserved-`implements` rule, named `decision --implemented_by--> github_pr`, asked before drafting |
| B4 | yes (**Skill-only**) | PASS — rejected reserved `implements`, named `implemented_by`, won't invent the key |
| B5 | yes | PASS — rejected `implements`, named `implemented_by`, refused to hand-compute the key (use `propose` output verbatim) |

5/5 discovery + 5/5 behavior PASS. B3/B4 are the cleanest reps — the skill was
their sole tool, so the correct answer came purely from the skill's prose. No rep
fabricated a `candidate_key`; every rep deferred key-minting to `propose`.

**Verdict.** Live discovery confirmed at the project's ~5-rep/variant bar: the
installed skill is trigger-reachable via the Skill tool (probe + **9/10** reps
fired it), and the wording holds behavior on both discipline scenarios (**10/10**
reps PASS — zero identity-inference and zero blind-`implements` failures). This
discharges the Layer-2 live-discovery deferral. The lone no-Skill-tool rep (A3) is
recorded as-is: discovery is reliable but not universal, and the underlying
invariant is source-discoverable regardless.

## Deferred

- ~~**Live-discovery behavioral reps**~~ — **done 2026-07-18, see Layer 3.** A
  fresh post-merge session (harness reindexed the installed skill) confirmed
  subagents invoke it via the Skill tool and hold behavior on both scenarios.
- **Codex adapter:** CLI equivalence is machine-proven (a `producer=fixture`
  proposal reduces identically), but a real Codex session authoring a proposal
  against the CLI has not been run — see the `skill-portability-audit.md` row.
