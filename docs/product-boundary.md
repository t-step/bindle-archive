# Product boundary (v0.3–v0.4)

The near-term product-boundary decision for Bindle, resolving issue #34.
Scope: the next one or two minor releases. This is a decision document —
when a proposed change conflicts with a line here, the change waits or the
boundary is revisited explicitly (see "Revisit triggers"). It builds on the
standing contracts in [provider-interop.md](provider-interop.md) and
[ownership-boundaries.md](ownership-boundaries.md) and does not restate them.

## Decision

- **Primary product role:** personal workflow infrastructure — a
  version-controlled kit that installs, documents, and safely operates a
  small collection of reusable human–agent collaboration workflows.
- **Primary user:** the repo owner. Bindle is single-user by design;
  collaborators consume individual workflows through the documented sharing
  paths ([sharing-skills.md](sharing-skills.md)), not by adopting the kit.
- **Primary job:** make the owner's working discipline — branch/PR flow,
  verification before completion, session continuity, privacy safety —
  reliable and portable across sessions and supported coding assistants,
  without depending on memory or habit.

Secondary roles are subordinate to that job:

- *Interoperability layer:* real, but intentionally narrow — documented
  contracts plus per-provider adapters, never a universal abstraction.
- *Behavior-shaping laboratory:* the pressure-test discipline exists to
  verify the owner's workflows, not as a general research platform.
- *Managed Claude environment:* Claude Code remains the mature provider
  implementation; "dotfiles for Claude Code" is the foundation, not the
  ceiling — but new capability is justified by the workflow job above, not
  by Claude-environment completism.

A capability earns a place in Bindle when it improves the owner's recurring
workflow along at least one of: reliability, safety, portability,
maintainability, or diagnosability. "Interesting" is not admission.

## Owned surfaces

Bindle owns, and its releases are accountable for:

1. **Claude-native assets** — `skills/`, `commands/`, `agents/`,
   `global/CLAUDE.md` — in their provider-native format.
2. **The installer and its guarantees** — `bin/install.sh` symlinks,
   conflict safety, ownership test, prune semantics, exit codes.
3. **Provider-neutral workflow contracts** — the `docs/` contracts
   (session-notes-format, hands-on-keyboard, iterative-improvement,
   sharing, privacy, ownership, provider-interop) that define what a
   workflow *is* independent of any provider's automation.
4. **Verification tooling and records** — `bin/check.sh`, the test
   scripts, the pressure-test method and each skill's
   `PRESSURE-TESTS.md`.
5. **Privacy guardrails** — `bin/check-private-info.sh`, `.gitleaks.toml`,
   the privacy-boundaries contract.
6. **The session-continuity data model** — the notes home (`~/.bindle`),
   its layout and formats.
7. **The issue-tracking label contract** — `docs/issue-tracking.md`.

## Provider boundary

- **Stays provider-native:** skill/command/agent files and their
  frontmatter, trigger conventions, and install layout; any runtime
  automation (hooks, slash commands); provider precedence behavior.
  Per [provider-interop.md](provider-interop.md), non-equivalences are
  permanent — Bindle documents differences instead of forcing adapters.
- **Can be a portable contract:** the workflow underneath the automation —
  expressed as Markdown docs plus plain scripts. Session continuity is the
  template: contract in `docs/session-notes-format.md`, Claude automation
  in commands, Codex participation manual via docs. New portable surface
  grows the same way: extract the contract into a doc first, then let each
  provider automate at the level it actually supports.

## Operational definitions

- **Portable:** a workflow is portable when its contract is plain Markdown
  plus at most dependency-free scripts (bash / Python stdlib), and a person
  or assistant with no Bindle-specific runtime can follow it end-to-end
  from the doc alone. Test: a Codex session, given only the doc and the
  repo, can execute the workflow manually.
- **Provider-neutral:** a document or script is provider-neutral when it
  assumes no provider primitive (skills, slash commands, subagents, hooks,
  plugins) exists, and mentions provider automation only as an optional
  adapter. Anything that requires a provider primitive is provider-native
  by definition, however generic its prose.
- **Supported (provider surface):** the installer installs it to an
  explicit, documented target, conflict-safely, with coverage in
  `bin/test-install.sh`, and it has an honest row in the provider
  capability matrix. "Manual via docs" is a supported participation level;
  an undocumented or untested install path is not supported, whatever the
  README implies.
- **Mature vs. experimental:** an asset is *mature* when it has passed (or
  baseline-passed) the CONTRIBUTING pressure-test loop with results
  recorded; otherwise it is a *draft* and must be labeled as such in the
  CHANGELOG. Provider-wise, Claude Code is the mature implementation;
  Codex is a supported-but-narrow adapter, not a peer.

## Explicit non-goals (v0.3–v0.4)

Tempting directions that are out of scope until a revisit trigger fires:

1. **Runtime orchestration** — no workflow engine, agent orchestrator, or
   execution runtime. Workflows run inside a provider's session; Bindle
   supplies the discipline, not the loop.
2. **Autonomous model routing** — no automatic model selection or
   cost-based dispatch. Delegation guidance may exist as documentation;
   choosing a model stays a human decision.
3. **Universal asset conversion** — no automatic translation of Claude
   skills/commands/agents into other providers' formats, and no
   lowest-common-denominator asset schema.
4. **A standalone evaluation platform** — the per-skill pressure-test
   discipline is the owned QA method. A reusable eval harness, suites, and
   scoring schemas are research until recurring need is demonstrated (see
   Admission criteria).
5. **Distribution and registry features** — no package manager, no
   external publishing, no multi-user install story. Sharing stays at the
   documented Git levels.
6. **Automatic runtime behavior before a safety contract** — no hooks or
   other install-time automation that executes without user initiation
   until the security/privacy contract for executable assets exists
   (issue #30 gates issue #21).
7. **Speculative schemas** — no manifest, index, or machine-readable
   inventory without a real, present consumer.

## Admission criteria

- **A new workflow (skill/command/contract):** admitted when it addresses
  friction observed in the owner's real sessions (notes or
  `/workflow-review` evidence, not hypotheticals), doesn't duplicate an
  existing asset, and enters as a draft until pressure-tested.
- **A new provider surface:** admitted when the mapping is real (the
  provider natively has the primitive), the installer can reach it
  conflict-safely via an explicit target, `test-install.sh` covers it, and
  the capability matrix row is honest about what doesn't map.
- **Executable automation (hooks, background behavior):** admitted only
  after the security/privacy contract exists; must be read-only or gated
  on explicit user approval per action; failure must degrade to the manual
  workflow, not block it.
- **A manifest or schema:** admitted when at least one consumer exists
  today (a tool in this repo, the dashboard, or a diagnostic) that would
  read it immediately — and starts as the smallest format that consumer
  needs.
- **Evaluation infrastructure:** admitted when the manual pressure-test
  loop has demonstrably failed to serve at least three recorded, recurring
  needs (e.g. rerun cost, cross-model comparison, regression detection),
  and then enters as plain scripts over fixtures, not a platform.

## Near-term sequence

For the next one or two minor releases, in order:

1. **Boundary and ownership** — this document (#34).
2. **Correctness and reliability floor** — installation recovery after a
   repo move (#24); any small installer/check defects that surface. (The
   other known correctness defects — #23, #25, #26, #27 — already landed
   via PRs #40–#44.)
3. **Read-only diagnosis** — `bindle doctor` (#28), subsuming #24's
   detection story; read-only, no auto-repair.
4. **Safety contract for automation** — the security/privacy contract for
   hooks and executable assets (#30), as a doc.
5. **Ship v0.3.0** (#9) once the above are landed and the CHANGELOG is
   honest about draft status.
6. **v0.4 candidates, in this order and only behind their gates:** hooks
   for session continuity (#21, gated on #30); small provider-neutral
   contracts for composition/precedence (#31) and delegation profiles
   (#32) as docs; capability inventory (#29) and release manifest (#33)
   once the owned capability set is stable and a consumer exists.

Evaluation work (#35–#39) and the remaining pressure-test chores sit
behind these — see the triage below.

## Backlog triage (2026-07-10)

Every open issue at decision time, classified against this boundary.
Format: *category — rationale; prerequisites; delegable to a weaker
worker?; minimum verification.* No open issue is a duplicate or needs
closing; three get reshape notes. Categories: **Now** (directly advances
the near-term boundary), **Next** (after named prerequisites), **Later**
(plausible, not needed within two minors), **Research** (needs evidence
before committing).

**Now (v0.3.0):**

- **#34** — this document. Not delegable; verify: `make check`, acceptance
  criteria met.
- **#24** repo-move recovery — the one remaining correctness bug in the
  ownership test. No prerequisites (pair detection with #28; the fix
  itself stays conservative — preview before adopting ownership). Not
  delegable (safety-design decisions). Verify: new `test-install.sh`
  move/recovery cases, `make test`.
- **#28** `bindle doctor` — read-only diagnosis is the cheapest reliability
  win and #24's natural detection surface. Reshape note: defer `--json`
  until a real consumer exists (see Admission criteria). Partially
  delegable (check scaffolding, not check selection). Verify: doctor tests
  against temp provider homes; never touches the real environment.
- **#30** security/privacy contract — doc-sized; hard gate for #21. Don't
  block on #29 (add inventory fields only if #29 lands). Not delegable.
  Verify: `make check`; #21 can cite it for every trigger/data-access row.
- **#9** cut v0.3.0 — after the above land. Partially delegable
  (`bin/release.sh` is mechanical; the go/no-go is the owner's). Verify:
  `make check` + `make test` green, CHANGELOG honest about drafts.

**Next (v0.4 window):**

- **#13** pressure-test `fork-pr-flow` — the only remaining *daily-driver*
  draft, and PR #41 changed it without a recorded test. No prerequisites.
  Partially delegable (reps are mechanical, scoring is not). Verify:
  filesystem-scored results in `PRESSURE-TESTS.md`.
- **#21** session-continuity hooks — gated hard on #30; soft prerequisite
  #22 (establishes the settings.json write pattern). Not delegable
  (foreign-config writes). Verify: opt-in install path tested, ownership
  boundaries updated, degrades silently.
- **#22** `/notes-home` — real friction (nothing sets `BINDLE_NOTES_DIR`
  today); settings.json writes must follow ownership rules (backup,
  one key, confirm). Partially delegable. Verify: script tests against a
  temp settings file, `make check`.
- **#31** composition/precedence contract — doc-sized, grounded in at
  least three real overlaps among existing workflows; feeds #38 and any
  eval policy. Not delegable. Verify: `make check`; the examples resolve
  today's actual overlaps.
- **#32** delegation profiles — doc-sized; can already encode the recorded
  Opus/Haiku pressure-test evidence; prerequisite for #39. Not delegable.
  Verify: `make check`; existing workflows can request a profile without
  naming a model.
- **#7** first agent — the surface exists with only a template; admission
  criteria apply: needs a friction-justified candidate, enters as draft.
  Choice not delegable; drafting partially. Verify: pressure-tested or
  marked draft.

**Later:**

- **#29** capability inventory — schema with no present consumer; unlocks
  when #28's `--json` or #33 needs it and the capability set is stable.
  Population is delegable once the schema is set. Verify: CI validates
  referenced paths; one manual table generated from it.
- **#33** release manifest — depends on #29; valuable once releases have
  consumers beyond the owner. Partially delegable. Verify: deterministic
  output, fails on inconsistency.
- **#11** spec-captain — fits the portable-workflow pattern but is a
  full contract + skill + pressure-test unit; needs friction evidence and
  capacity after the v0.4 items. Not delegable. Verify: per CONTRIBUTING.
- **#18** SQLite notes index — correctly self-gated ("when grep starts to
  hurt"); design doc exists. Largely delegable when triggered. Verify:
  self-tests; Markdown stays canonical.
- **#14 / #15 / #17** pressure-test chores (repo-hygiene-init,
  license-compliance-auditor, maintain-claude-md lint checks) — QA debt on
  rarely-run or low-blast-radius surfaces; batch when convenient.
  Partially delegable. Verify: `PRESSURE-TESTS.md` records.
- **#16** Sonnet bracket reruns — real gap, someday-priced; batch with the
  next campaign. Partially delegable. Verify: appended per-skill logs.

**Research (behind the evaluation revisit trigger):**

- **#35** eval policy/taxonomy/schema — the policy half ("when to stop,
  which brackets") is cheap and useful; the machine-readable result schema
  has no consumer until #36 exists. Reshape option: split those halves.
- **#36** eval harness — this *is* the platform the boundary defers;
  admitted only after three recorded needs the manual loop couldn't serve.
- **#37 / #38** routing + composition/e2e suites — behind #36 (and #31 for
  #38).
- **#39** weaker-model delegation evals — behind #32 and #36; interim
  path: #32's doc records the existing cross-model evidence as a decision
  record without new infrastructure.

The `priority: now` labels that #35, #36, and #39 carried predate this
boundary and were re-set to match it.

## Revisit triggers

Concrete evidence that justifies reopening this boundary:

- **A second real user** adopts the kit (not a shared skill — the kit),
  which breaks the single-user assumption behind privacy, notes, and
  install defaults.
- **A third provider** with a real native surface worth adapting, or
  Codex gaining primitives (skills/commands) that make today's "narrow
  adapter" stance wrong.
- **Three or more recorded eval needs** the manual pressure-test loop
  could not serve — unlocks the evaluation-infrastructure criteria above.
- **A consumer materializes for a manifest** (dashboard, doctor, or an
  external tool needs machine-readable capability data) — unlocks #29/#33.
- **Recurring multi-workflow conflicts in real sessions** (precedence or
  composition failures recorded in notes) — justifies promoting #31 from
  doc-sized contract to something larger.
- **The safety contract (#30) proves insufficient** for a hook Bindle
  actually wants — justifies rethinking whether automation belongs in the
  kit at all.

When a trigger fires, revise this document in its own PR with the evidence
cited — don't stretch the boundary silently.
