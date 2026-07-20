# Product boundary

Affirmed through: v0.9

The standing product-boundary decision for Bindle, resolving issue #34 and
refreshed 2026-07-19 per issue #283. This is a decision document — when a
proposed change conflicts with a line here, the change waits or the boundary
is revisited explicitly (see "Revisit triggers"). It builds on the standing
contracts in [provider-interop.md](provider-interop.md) and
[ownership-boundaries.md](ownership-boundaries.md) and does not restate them.

**This document does not expire on a release schedule.** It carried the scope
"v0.3–v0.4" until 2026-07-19, and that range expired silently — no event
announced it, and roughly 200 issues were filed against a document that had
stopped applying. It is now amended only when a Revisit trigger fires, and the
`Affirmed through:` line above records the minor release it was last checked
against. `bin/check.sh` fails when that line falls behind `VERSION`'s minor, so
the lapse cannot recur unnoticed.

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
8. **Executable automation** — `global/hooks/`, the only surface Bindle
   ships that runs without user initiation. Listed separately from the
   Claude-native assets above because that is what governs it: admission
   is the "executable automation" criterion below, not the workflow one;
   non-goal 6 gates it on the safety contract in
   [runtime-security-privacy.md](runtime-security-privacy.md); and its
   install path is separate in both directions — `bin/install.sh`
   symlinks the scripts but never wires them, and wiring into
   `~/.claude/settings.json` is opt-in per hook. A release is accountable
   for hook *behavior*, not merely for the files being present: a hook
   that is symlinked but never wired has shipped nothing.

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
  CHANGELOG. Provider-wise, Claude Code is the mature implementation; Codex
  is a supported provider (still maturing) that can host provider-native
  assets — no longer a mere adapter. See the 2026-07-14 revisit below, which
  fired the Codex-primitives trigger and moved this stance.

## Explicit non-goals

Tempting directions that are out of scope until a revisit trigger fires:

1. **Runtime orchestration** — no workflow engine, agent orchestrator, or
   execution runtime. Workflows run inside a provider's session; Bindle
   supplies the discipline, not the loop.
2. **Autonomous model routing** — no automatic model selection or
   cost-based dispatch. Delegation guidance may exist as documentation;
   choosing a model stays a human decision.
3. **Universal asset conversion** — no *automatic* translation of Claude
   skills/commands/agents into other providers' formats, and no
   lowest-common-denominator asset schema. (Refined 2026-07-14: a
   Codex-native asset may be *hand-authored* as its own first-class asset,
   or installed via explicit per-asset eligibility; only automatic
   translation / adapter-generation stays barred — see the revisit below.)
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

### Upstream deferral

**Deferring to an upstream that owns a policy is in scope and preferred.
Reimplementing that policy locally is out of scope.**

Deferral preserves the capability and the boundary at once. Reimplementation is
the actual failure mode worth forbidding — the slow accretion by which a kit
that *uses* an upstream's policy becomes a second, worse copy of it.

Worked example, measured 2026-07-19 (issue #283):

| Skill | DomI references |
| --- | --- |
| `package-release-integrity` | 66 |
| `domi-consumer` | 63 |
| `release-captain` | 50 |
| the other 11 shipped skills | 0 |

Those references are deferral seams — Bindle declining to own semver governance
where a well-formed `.domi-pin` marks it inherited, and routing to the upstream
that does own it. **They are in scope and protected by this rule.** Naming them
explicitly matters because the risk here runs the direction this document does
*not* want: 50 references in one skill, added during a period no scope document
covered, read as creep to a future session or a dispatched subagent, and nothing
on paper contradicted that reading until now. A stale boundary does not restrain
this functionality; it leaves it undefended.

Corollary, consistent with the single-user decision above: Bindle serving a repo
owner who *works in* upstream-consuming repos is in scope; Bindle taking that
upstream's needs as a second product owner is not.

## Near-term sequence (v0.3–v0.4, historical)

A completed plan, retained as a record of what this boundary was used to
sequence. It is not a live plan; what is next is a milestone question, and
milestones are live where this document is standing.

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

**Status (2026-07-12): all six steps shipped.** #34, #24, #28, #30, #9,
#21, #22, #31, #32, #29, #33 are closed; v0.3.0 released 2026-07-10, and
the v0.4 candidates landed as `docs/workflow-composition.md`,
`docs/delegation-profiles.md`, `capabilities.json`/`bin/check-inventory.py`,
and `RELEASE-MANIFEST.json`/`bin/release-manifest.py` respectively (both since
retired from the release path — see #137). #35
(eval policy/taxonomy/schema, listed as Research below at decision time)
also shipped as `docs/workflow-eval.md`, unsplit — the "reshape option:
split those halves" note in the original Research entry wasn't needed in
practice. This near-term sequence is complete; no successor v0.5 sequence
has been declared yet (see the refreshed triage below for what's actually
open).

## Backlog triage

**This document does not triage issues individually.**

Per-issue state lives in GitHub labels — `status:` and `priority:`, defined in
[issue-tracking.md](issue-tracking.md). Those labels are the live record, they
are maintained as work moves, and the dashboard reads them. A static table here
would restate that live state in a form that goes stale on the next merge, which
is what happened twice below.

What this document supplies is the **admission rule** those labels are applied
against — see "Admission criteria" — plus rulings on contested calls only.

Retired 2026-07-19 per issue #283. The two dated tables below are historical:
evidence of past reasoning, not current state. They are kept because the
rationale in them is still worth reading; they are not maintained.

### Contested calls

Rulings on scope questions that were genuinely disputed — recorded so they are
not re-litigated. Routine classification does not belong here; this section
grows only when a call is actually contested, and is empty until then.

*(none yet)*

## Backlog triage (2026-07-12, historical)

Refreshes the 2026-07-10 triage below against current issue state. Of that
snapshot's 18 classified issues, 14 are now closed (all of Now and Next,
plus #14/#15/#16/#17 from Later) — see Status note above. This table
re-triages the remaining open issues plus six opened since 2026-07-10
(#55, #58, #59, #60, #80, #88). Same categories and format as before.

**Now:** none. The v0.3–v0.4 near-term sequence above is fully shipped;
no new Now-tier work has been designated pending the next planning
decision.

**Next:** #59 and #60, newly unblocked by the 2026-07-14 revisit below (the
boundary question that gated them is resolved). The remaining open issues are
either self-gated on evidence that hasn't materialized or too underspecified
to triage yet — see Later, Research, and Needs input.

**Later:**

- **#11** spec-captain — unchanged from 2026-07-10: fits the
  portable-workflow pattern but is a full contract + skill + pressure-test
  unit; needs friction evidence and capacity. Not delegable. Verify: per
  CONTRIBUTING.
- **#18** SQLite notes index — unchanged: correctly self-gated ("when grep
  starts to hurt"); design doc exists. Largely delegable when triggered.
  Verify: self-tests; Markdown stays canonical.
- **#88** knowledge promotion wave 2 (`knowledge.md`) — explicitly
  self-gated by its own design doc: "do not start until wave 1 (#84–#87)
  has real dogfood evidence." Partially delegable once triggered. Verify:
  per `docs/design/2026-07-11-knowledge-promotion.md`.

**Research (behind the evaluation revisit trigger, or a boundary
question):**

- **#36** eval harness — unchanged: this *is* the platform the boundary
  defers; admitted only after three recorded needs the manual loop
  couldn't serve. That evidence hasn't accumulated yet.
- **#37** routing + holdout suites — behind #36 (unchanged).
- **#38** composition/e2e suites — behind #36; its other named
  prerequisite, #31, has now shipped, but #36's own gate still hasn't
  fired, so #38 doesn't move yet.
- **#39** weaker-model delegation evals — behind #36; its other named
  prerequisite, #32, has now shipped, same situation as #38.
- **#55** ("Reconcile Codex interoperability and DomI-derived workflow
  dependencies") — **RESOLVED 2026-07-14.** The boundary question #55 raised
  (whether the Codex-primitives Revisit Trigger fired) was adjudicated in the
  "Revisit 2026-07-14" section below: verdict FIRED. The stance moved; the
  standing guardrails held. Its children are no longer blocked on this
  question — **#58** shipped (DomI consumer profile), and **#59** (portable
  package-release-integrity workflow) and **#60** (portable issue work loop)
  are unblocked to proceed with Codex-native participation in scope. #55
  itself is a tracking epic; close or keep it open tracking #59/#60.

**Needs input (not yet triageable):**

- **#80** ("Brainstorm truth reconciliation and the repository drift
  auditor") — the issue body is truncated mid-sentence (cuts off after
  "the evidence hierarchy used when code, tests, docs, issues, plans, and
  agent narration disagree; the"). Cannot be triaged against the boundary
  as written — the "Desired outcome" list it's building toward never
  arrives. Needs the body completed/re-filed before classification; likely
  a manual-paste truncation (same pattern previously seen on #90), not a
  tooling gap.

## Backlog triage (2026-07-10, historical)

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
- **#33** release manifest — promoted out of Later (2026-07-12): the
  "consumer materializes" trigger below has fired (`bin/doctor.sh` now
  reads machine-readable capability data via `install-manifest.tsv`,
  generated from `capabilities.json`). #29, its other prerequisite, has
  shipped. Partially delegable. Verify: `bin/release.sh` regenerates and
  diffs the manifest before committing, fails the release on inconsistency.

**Later:**

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

## Revisit 2026-07-14 — the Codex-primitives trigger (#55)

A revisit of this boundary in the shape #34 used, triggered by issue #55 and
resolved here with cited evidence. This section is the authoritative decision
record; the inline edits above (Mature-vs-experimental, non-goal #3, the fired
trigger, the backlog entry) flow from it.

### Verdict: FIRED (broad)

The Codex-primitives Revisit Trigger is adjudicated **fired**. Evidence, both
already landed and closed:

- **#56** (Codex capability re-baseline) verified against current official
  Codex/OpenAI docs that Codex has native primitives for Agent Skills,
  subagents, hooks, and plugins — recorded per-surface in
  `provider-interop.md` § "Codex capability re-baseline".
- **#57** (install compatible shared skills for Codex) shipped a real shared
  cross-provider install surface: two eligible skills install into a Codex
  Agent-Skills home via `bin/install.sh`, gated by per-skill
  `capabilities.json` `provider.codex` eligibility and covered by
  `test-install.sh`. A live Codex probe discovered both eligible skills and
  invocation-tested one (`verify-then-commit`) — which read the skill body and
  followed its commit gate; `fork-pr-flow`'s invocation was not probed this
  wave.

The second point is decisive: Bindle already shipped past the old "narrow
adapter, never a peer" stance. Recording the trigger fired makes the boundary
honest, not more speculative.

### Stance change

Codex is reclassified to a **supported provider that can host provider-native
assets** across skills, subagents, and hooks — a change from the prior
narrow-adapter stance. "Broad" means the *surface is open* — Bindle may ship
Codex-native assets as first-class, not merely document manual participation.
It does **not** claim parity, and this revisit authors no subagent/hook asset.

### Guardrails preserved (the "not a universal runtime" floor)

1. **Non-equivalence stays permanent.** A Claude asset is not a Codex asset;
   no merged/generated single-source file. Drift is managed by review.
2. **No *automatic* asset conversion.** A Codex-native subagent/hook is
   hand-authored as its own asset, or installed via explicit per-asset
   eligibility — never machine-translated from the Claude asset (non-goal #3,
   refined not deleted).
3. **No universal runtime, orchestrator, or execution loop** (non-goal #1).
4. **Hooks stay gated on the #30 safety contract, per action** (non-goal #6);
   any executable Codex automation must degrade to the manual workflow.
5. **Installer conflict-safety, explicit targets, and per-asset eligibility
   metadata** are preserved; no directory sweeps.

### Plugins — deferred

Codex's native plugin primitive has no Bindle equivalent on either provider
and no present consumer. Recorded still-out (adjudicated-deferred, not fired);
"broad" covers skills, subagents, and hooks, not plugins.

### Flow-through

- **#59** and **#60** are unblocked — Codex-native participation is now in
  scope for them, not manual-docs-only.
- **#58** already shipped; no action.
- **#55** (epic) may close now (P0/P1 shipped, boundary resolved) or stay open
  tracking #59/#60 — an operator call, not part of this doc change.

## Revisit triggers

Concrete evidence that justifies reopening this boundary:

- **A second real user** adopts the kit (not a shared skill — the kit),
  which breaks the single-user assumption behind privacy, notes, and
  install defaults.
- **A third provider** with a real native surface worth adapting, or
  Codex gaining primitives (skills/commands) that make today's "narrow
  adapter" stance wrong. **Claimed 2026-07-12** (issue #55); **FIRED 2026-07-14**
  — adjudicated in the "Revisit 2026-07-14" section below on #56/#57 evidence
  (Codex's native Agent Skills/subagents/hooks, and the shared skill-install
  path Bindle already shipped in #57). The revisit widened the provider stance
  while preserving the non-equivalence, no-automatic-conversion, no-runtime, and
  hook-safety guardrails; plugins stay deferred.
- **Three or more recorded eval needs** the manual pressure-test loop
  could not serve — unlocks the evaluation-infrastructure criteria above.
- **A consumer materializes for a manifest** (dashboard, doctor, or an
  external tool needs machine-readable capability data) — unlocks #29/#33.
  **Fired 2026-07-12:** `bin/doctor.sh` reads `install-manifest.tsv` via
  `bin/lib/manifest.sh`. #29 shipped; #33 moved to Next (see above).
- **Recurring multi-workflow conflicts in real sessions** (precedence or
  composition failures recorded in notes) — justifies promoting #31 from
  doc-sized contract to something larger.
- **The safety contract (#30) proves insufficient** for a hook Bindle
  actually wants — justifies rethinking whether automation belongs in the
  kit at all.
- **This document falls behind the release line** — the `Affirmed through:`
  line at the top names a minor older than `VERSION`'s. Unlike every trigger
  above, this one is *enforced* rather than noticed: `bin/check.sh` fails until
  the document is re-read and the line updated, or the document is amended.
  It exists because the failure it guards is the **absence** of an event —
  the other six all require something to happen, and nothing happening for
  four months is exactly how this document lapsed (#283).

  Cutting a minor release is therefore a prompt to re-read this document. A
  patch release is not; a boundary has nothing to say about a patch. Affirming
  *ahead* of `VERSION` is fine and is the intended order — `VERSION` lags
  merged work (#265), so the gate can fire late, but it cannot fire wrongly.

When a trigger fires, revise this document in its own PR with the evidence
cited — don't stretch the boundary silently.
