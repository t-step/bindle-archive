# Skill portability audit

The evidence-backed classification of every authored skill under `skills/`
for cross-provider (Claude Code / Codex) portability, resolving issue #61.
Audited 2026-07-11 against the Codex capability re-baseline in
[provider-interop.md](provider-interop.md#codex-capability-re-baseline-2026-07-11)
(issue #56, verified the same day).

Ownership boundaries of this document:

- **Issue #57 owns installation.** This audit changes no installer, doctor,
  or provider-configuration behavior; it tells #57 which skills are eligible
  and why. Nothing here is an install.
- **Issue #29 owns the general machine-readable capability inventory.** The
  matrix below is a narrowly scoped, human-maintained precursor covering
  *skill portability only* — see [Relationship to #29](#relationship-to-29).
- Per [product-boundary.md](product-boundary.md) and the repo's Phase 1 rule
  ("Claude assets remain Claude-native"), no skill content was rewritten for
  this audit. Cleanup items are named, not performed.

## Method

Every skill directory under `skills/` was inspected directly (no
classification from names or file shape alone): frontmatter, full SKILL.md
prose, all support files (`scripts/`, `references/`, `tests/`,
`PRESSURE-TESTS.md`), plus systematic scans for provider-specific strings
("Claude", slash-command names, `~/.claude` paths, `settings.json`,
`superpowers:` references, tool names, `gh` usage), cross-skill references,
and references escaping the skill directory. Installer (`bin/install.sh`),
checker (`bin/check.sh`), doctor (`bin/doctor.sh`), and installer tests
(`bin/test-install.sh`) were read for install/ownership semantics.

Every claim below carries one of four evidence labels:

- **tested** — verified by running something in this audit or by an existing
  recorded test (unit tests, `make check`, `PRESSURE-TESTS.md`);
- **documented** — asserted by current official provider documentation (as
  re-baselined by #56) but not exercised by Bindle;
- **inferred** — follows from tested/documented facts but has an untested
  step in the chain;
- **unknown** — no evidence either way.

Non-destructive verification performed for this audit (no real user home or
provider settings touched; fixtures in the session scratchpad only):

1. **Frontmatter shape** — all 8 skills have exactly the `name`/`description`
   frontmatter Codex Agent Skills documents as required, with `name` matching
   the directory (`make check` green; **tested**, format level only).
2. **Whole-directory symlink preserves support-file resolution** — a skill
   directory symlinked into a fixture `.agents/skills/` resolves both
   intra-directory references (`references/`, `scripts/`) and
   parent-relative references (`../../docs/…`), because POSIX resolves `..`
   against the symlink *target*. `scripts/detect_tools.py` executed correctly
   through the symlink (**tested**). A **copy** install would break any
   reference escaping the skill directory (**inferred** from the same
   mechanics).
3. **Read-only Codex discovery probe** — `codex exec -s read-only`
   (codex-cli 0.143.0) in a throwaway fixture repo with `verify-then-commit`
   and `fork-pr-flow` symlinked into `<fixture>/.agents/skills/`, asked only
   to enumerate available skills and their discovery paths. **Result: both
   skills appeared in the session's available-skills list, reported at their
   symlink-resolved repo paths** — a real Codex session discovers Bindle
   skills through whole-directory symlinks at repo scope (**tested**).
   Official docs additionally state Codex "supports symlinked skill folders
   and follows the symlink target" (**documented**, re-verified 2026-07-11
   against [learn.chatgpt.com/docs/build-skills](https://learn.chatgpt.com/docs/build-skills)).
   This is a *discovery* check, not behavioral parity — one superficial
   invocation proves a skill is visible, not that it works.

## Summary

- **Skills audited: 8** (every authored skill: `fork-pr-flow`,
  `hands-on-keyboard`, `license-compliance-auditor`, `maintain-claude-md`,
  `repo-hygiene-init`, `scoped-sequential-prs`, `session-continuity`,
  `verify-then-commit`), plus
  `skills/_template/` (not an authored skill; excluded from install and
  checks by the `_*` skip in `bin/install.sh` and `bin/check.sh` —
  classified **not applicable**).
- **Recommended dispositions:** 5 shared unchanged (Codex side untested at
  the behavior level), 3 provider-specific (`session-continuity` and
  `hands-on-keyboard` — Codex consumes the portable doc contracts, not the
  skills, per the [#71 wording decision](#decision-on-provider-specific-wording-71);
  `maintain-claude-md` — Claude-native subject). See the honest split per
  skill — several "shared unchanged" rows still carry Codex-side unknowns.
- **Highest-confidence shared candidates:** `verify-then-commit`,
  `fork-pr-flow` — zero provider-specific prose, no scripts, strongest
  behavioral evidence on Claude, and covered by this audit's live Codex
  discovery probe.
- **Blocked by provider-specific assumptions:** `maintain-claude-md` (its
  subject *is* Claude Code's memory file), `session-continuity` (prose
  assumes the four Claude slash commands), `hands-on-keyboard` (prose is
  addressed to "Claude" throughout, by design as the Claude-native adapter
  of a portable contract).
- **External dependencies:** `gh` CLI (`fork-pr-flow` core steps,
  `license-compliance-auditor` optional gated step), the `superpowers`
  skill ecosystem (soft "REQUIRED BACKGROUND" pointers in
  `verify-then-commit` and `scoped-sequential-prs`), the Bindle repo
  checkout itself (`session-continuity` → `bin/slugify.sh`,
  `bin/check-private-info.sh`; `hands-on-keyboard` → `docs/hands-on-keyboard.md`).
- **Major unknowns:** no Bindle skill has ever been *invoked* by a real
  Codex session (discovery ≠ behavior); byte-level format compatibility
  beyond `name`/`description` is documented-family-only; whether Codex
  tolerates extra top-level files in a skill directory
  (`PRESSURE-TESTS.md`, `tests/`) is unknown.

## Decision on provider-specific wording (#71)

Resolves issue #71 (parent #55; settles the wave-2 question in #57) for the two
skills the matrix flagged as blocked on provider-specific prose. The audit
named three options: (1) neutralize the wording in place; (2) keep the
two-layer design (portable doc + Claude adapter skill) and give Codex only the
doc; (3) a per-provider variant. Option 3 is out per
[product-boundary.md](product-boundary.md) — asset conversion is a stated
non-goal.

**Decision: option 2 for both skills.** Codex consumes the already-shipped
portable contracts — [session-notes-format.md](session-notes-format.md) and
[hands-on-keyboard.md](hands-on-keyboard.md) — and these two SKILL.md files
stay Claude-native and unchanged. Neither is shipped to Codex as a skill.

Rationale:

- Option 1 requires first amending the standing Phase 1 rule ("Claude assets
  remain Claude-native — do not rewrite `skills/*/SKILL.md` … to make them
  provider-neutral"). That is a deliberate product change, out of scope for a
  cleanup issue; #71 explicitly forbids the drive-by edit.
- The two-layer design already exists and works: each skill's portable
  contract is a shipped doc, and
  [using-bindle-with-codex.md](using-bindle-with-codex.md) already tells a
  Codex session how to follow it manually. No Codex-side capability is lost by
  withholding the skill.
- **U7 resolved (`session-continuity`):** the only thing sharing the skill
  would add over the doc is implicit triggering — low value against the cost
  of neutralizing four Claude-command references and collapsing the two-layer
  design. Not worth it today.
- `hands-on-keyboard` self-describes as "the Claude-native automation of the
  provider-neutral contract"; re-wording it would erase a deliberate design
  statement, not fix stale prose.

Reversibility: if the owner later retires or amends the Phase 1 rule, option 1
becomes available and both rows can move to shared-after-cleanup. Nothing here
forecloses that — it records that today's compliant, lower-risk choice is
option 2.

## Skill matrix

Legend: **F** format compatibility, **C** Claude support, **X** Codex
support, evidence labels as above. "Shared unchanged" always means "no
content change needed" — it does not assert Codex behavioral parity, which
is untested for every skill.

| Skill | Purpose | Owner / source of truth | F: format | C: Claude status | X: Codex status | Invocation assumptions | Runtime dependencies | Evidence level | Disposition | Required cleanup / follow-up |
|---|---|---|---|---|---|---|---|---|---|---|
| `domi-consumer` | Detect a DomI-consumer repo and report drift status by invoking `bin/domi-status.sh`, then interpret the verdict per `docs/domi-consumer.md` | Bindle (portable contract already exists separately: [domi-consumer.md](domi-consumer.md)) | yes (frontmatter only; added after this audit's 2026-07-11 pass, not re-run against it) | installed, **draft** — not pressure-tested | untested | implicit trigger; invokes `bin/domi-status.sh` (bash, provider-neutral) and reads its exit code / verdict | `bin/domi-status.sh` (portable bash detector, no Claude-only primitive), `docs/domi-consumer.md` (contract) | Claude: draft/untested · Codex: untested | **portable** (thin wrapper over a portable bash detector; no Claude-only primitive) | none required — reassess once pressure-tested and a Codex invocation is attempted |
| `verify-then-commit` | Gate every commit on tests+typecheck+lint green | Bindle | yes (tested, Claude; documented, Codex) | installed + pressure-tested (10/10, 10/10, Sonnet 6/6) | **discovered by a real read-only Codex session via repo-scope symlink (tested, this audit)**; invocation untested | implicit trigger via description; none provider-specific | none (prose only); soft pointer to `superpowers:verification-before-completion` | Claude: tested · Codex: discovery tested, behavior unknown | **shared unchanged** | none required |
| `fork-pr-flow` | Fork/owned-repo PR targeting, push discipline, no self-merge | Bindle | yes (tested, Claude; documented, Codex) | installed + pressure-tested (5/5 self-merge refusal + in-situ arm) | **discovered by a real read-only Codex session via repo-scope symlink (tested, this audit)**; invocation untested | implicit trigger; none provider-specific | `gh` CLI for PR steps (degrades to advice); git remotes | Claude: tested · Codex: discovery tested, behavior unknown | **shared unchanged** | none required; #57 should detect `gh`, not vendor it |
| `scoped-sequential-prs` | Split big work into ordered, scope-isolated PRs with a 3-step contamination gate | Bindle | yes (tested, Claude; documented, Codex) | installed + pressure-tested (6 claims, Sonnet+Haiku, gate REFACTORed twice) | untested | implicit trigger; step 2 says "See superpowers:using-git-worktrees" | git, worktrees; soft deps: `superpowers:using-git-worktrees`, pairs-with pointers to `fork-pr-flow`/`verify-then-commit` | Claude: tested · Codex: unknown | **shared unchanged** | none required; degraded (not broken) without superpowers — document in #57 |
| `repo-hygiene-init` | Bootstrap baseline repo hygiene (pre-commit, lint, Makefile, CI, license, versioning) | Bindle | yes (tested, Claude; documented, Codex) | installed + tested (HOLDS 6/6; RED arm did not establish a failing baseline) | untested | implicit trigger; none provider-specific | suggests common tools (pre-commit, ruff, prettier) but detects before adding | Claude: tested (weaker RED) · Codex: unknown | **shared unchanged** | fix dangling `version-single-source` pattern reference (defined nowhere in the repo) |
| `license-compliance-auditor` | Evidence-backed license-risk audit; scripts + references; never legal conclusions | Bindle | yes (tested, Claude; documented, Codex) | installed + unit-tested scripts + pressure-tested (3 claims, Sonnet) | untested; scripts run stdlib-only through a symlink (tested locally, outside any Codex session) | implicit trigger; Claude also has a `/license-audit` command *wrapper* (command→skill; the skill does not need the command) | Python 3 stdlib only; optional gated `gh`; all references resolve inside the skill dir (tested through symlink) | Claude: tested · Codex: unknown (script layer provider-neutral: tested) | **shared unchanged** | none required; largest support-file surface — best test case for #57's symlink requirement |
| `session-continuity` | Notes home, session notes, handoffs, profiles — the privacy-safe cross-session memory | Bindle (portable contract already exists separately: [session-notes-format.md](session-notes-format.md)) | yes (tested, Claude; documented, Codex) | installed + pressure-tested (4+ claims incl. Haiku/Sonnet reruns) | untested | prose asserts "The `/session-start`, `/session-end`, `/handoff`, and `/project-profile` commands all follow these conventions" — Claude slash commands with **no Codex equivalent** (Codex custom prompts are deprecated) | Bindle repo checkout for `bin/slugify.sh` + `bin/check-private-info.sh` (conditional, degrades with a stated fallback); notes home dir | Claude: tested · Codex: unknown | **provider-specific** (Codex uses the doc, [#71](#decision-on-provider-specific-wording-71)) | **resolved #71 → option 2:** no wording change; Codex follows [session-notes-format.md](session-notes-format.md), skill stays Claude-native |
| `hands-on-keyboard` | Navigator-not-driver collaboration mode; escalation ladder | Bindle (portable contract already exists separately: [hands-on-keyboard.md](hands-on-keyboard.md)) | yes (tested, Claude; documented, Codex) | installed + pressure-tested | untested | implicit trigger; prose addresses "Claude" 6× including the description — deliberate: the file self-describes as "the Claude-native automation of the provider-neutral contract" | `../../docs/hands-on-keyboard.md` (escapes the skill dir; resolves through a symlink install — tested; breaks on copy install) | Claude: tested · Codex: unknown | **provider-specific** (deliberate two-layer design, [#71](#decision-on-provider-specific-wording-71)) | **resolved #71 → option 2:** no wording change; Codex follows [hands-on-keyboard.md](hands-on-keyboard.md), skill stays the Claude adapter |
| `maintain-claude-md` | Init/update/lint a repo's CLAUDE.md | Bindle | yes (tested, Claude; documented, Codex) | installed + pressure-tested (6 claims) | untested; **not recommended** | invocable as `/maintain-claude-md` (Claude skill-as-command surface); description references that invocation | none beyond file tools + `command -v` | Claude: tested · Codex: unknown | **provider-specific (Claude-only)** | none — the managed artifact (CLAUDE.md, `@`-includes, `.claude/settings.json`, loader stubs) *is* Claude Code provider surface; a Codex install would be misleading, not merely stale wording |
| `skills/_template/` | Authoring scaffold for new skills | Bindle | placeholder frontmatter (name ≠ dir by design) | never installed (`_*` skip, tested by inspection of `bin/install.sh`) | never installed | n/a | n/a | tested (skip logic read) | **not applicable / unsupported** | none — repo tooling, not an installable skill |

## Per-skill notes beyond the matrix

Only what the matrix cannot carry:

- **`verify-then-commit`** — the single cleanest portability case: one file,
  zero "Claude" occurrences, zero scripts, generic vocabulary ("subagent",
  "pre-commit hook", "operator") that both providers' sessions can follow.
  The `superpowers:` pointer is a soft reference by repo convention
  ("soft runtime pointer, no install needed" — `skills/_template/SKILL.md`);
  on a machine without superpowers it reads as a named principle, not a
  broken dependency. Incidentally, on this machine the superpowers skills
  are *also* present on the Codex side via the Codex plugin marketplace
  cache — machine-specific, not assumable.
- **`fork-pr-flow`** — `gh` is an environmental dependency, not a provider
  one (Claude sessions need it too). Absence degrades the skill to correct
  advice the user executes manually. #57 should surface "gh missing" as a
  doctor-style diagnostic, not block install.
- **`scoped-sequential-prs`** — the contamination gate is plain
  `git diff`/`grep`; nothing provider-shaped. The worktree step leans on
  superpowers for *mechanics* but states the requirement ("one worktree per
  PR") inline, so a session without superpowers can still comply.
- **`repo-hygiene-init`** — its Claude evidence is the weakest of the eight
  (the RED arm's baseline did not fail, so the test proves "holds with the
  skill", not "the skill causes the improvement"). That caveat is about
  effectiveness, not portability.
- **`license-compliance-auditor`** — the workflow says "run from the skill
  directory (or with a relative/absolute path to it)"; through a
  whole-directory symlink this held in local testing. Its `tests/` and
  fixture tree ride along in any whole-directory install; whether Codex
  ignores or chokes on ~40 extra files in a skill directory is an unknown
  worth one cheap probe in #57.
- **`session-continuity`** — the portable *contract* is already shipped
  separately ([session-notes-format.md](session-notes-format.md)) and
  [using-bindle-with-codex.md](using-bindle-with-codex.md) already tells a
  Codex session how to follow it manually. What sharing the *skill* would
  add on Codex is implicit triggering. The cleanup is real but small: four
  passages reference the Claude commands as the implementation
  (`SKILL.md` lines 13–14, 50, 90); everything else in the file is
  provider-neutral. Whether the cleaned skill should *replace* or *defer to*
  the doc contract is a design decision for the cleanup issue, not this
  audit.
- **`hands-on-keyboard`** — mirror image of `session-continuity`: the
  portable contract lives in [hands-on-keyboard.md](hands-on-keyboard.md)
  and the skill is explicitly the Claude adapter. Re-wording it
  provider-neutral would collapse a deliberate two-layer design (portable
  doc + provider adapter) unless done knowingly. It is classified
  provider-specific *by current content and stated intent*, not by
  installation path — the underlying workflow is fully portable and already
  has its portable artifact.
- **`maintain-claude-md`** — the one skill that is Claude-native by
  *subject*, not by wording: it manages Claude Code's own memory file,
  `@`-include semantics, `.claude/settings.json`, and session-start loading
  behavior. A Codex session could mechanically execute it (nothing in it
  requires a Claude tool), but installing it for Codex would offer Codex a
  workflow about another provider's config surface. If a real need appears
  ("Codex maintains the CLAUDE.md for the Claude sessions that share the
  repo"), that is a deliberate future decision.

## First-wave recommendation for #57

**Wave 1: `verify-then-commit` and `fork-pr-flow`.** Two skills, not eight —
optimizing for defensibility, not catalog size.

Why these two qualify:

- prose is 100% provider-neutral today — no cleanup PR gates the wave;
- no scripts, no support-file resolution risk (single SKILL.md each,
  plus PRESSURE-TESTS.md);
- strongest behavioral evidence on Claude (both survived adversarial
  pressure campaigns, recorded in their `PRESSURE-TESTS.md`);
- both were visible to this audit's read-only Codex discovery probe (see
  per-skill matrix rows);
- they encode the owner's two most safety-relevant disciplines (never
  commit unverified, never push/self-merge), so a Codex session gaining
  them has the highest value-per-skill.

Cleanup required first: none.

Required installer behavior (restating #57's own requirements as they apply):

- symlink the **whole skill directory** into the user-scope Codex Agent
  Skills location verified by #56 (`~/.agents/skills/<name>` — distinct
  from `~/.codex`, which is Codex *configuration* home);
- same conflict-safety and ownership semantics as Claude installs (never
  overwrite real files or foreign symlinks; prune only own broken links);
- explicit target override for tests (never the real user home in CI);
- an explicit allowlist (classification metadata), not a directory sweep —
  this audit's matrix is the source for that list until #29 lands.

Required tests (fixture-home only):

- Codex-eligible skill installs into a temp skills root; Claude-only skills
  (at minimum `maintain-claude-md`) are excluded;
- support files resolve through the symlink (assert
  `<home>/.agents/skills/<name>/PRESSURE-TESTS.md` readable — and for any
  future wave-2 skill with `scripts/`, execute one);
- conflict refusal, prune safety, idempotent re-install, `--provider all`
  parity — mirroring the existing Claude cases in `bin/test-install.sh`.

Real-provider verification still needed (this is #57's acceptance
criterion, deliberately not claimed by this audit):

- a real Codex session **discovers** the installed skill from
  `~/.agents/skills` (this audit only probed repo-scope
  `<cwd>/.agents/skills` discovery, read-only);
- a real Codex session **invokes** one installed skill and observably
  follows it (e.g. refuses to commit on a red test in a fixture repo);
- confirm extra top-level files in the skill directory don't break
  discovery.

**Explicitly deferred from wave 1** (defensible wave 2 candidates, in
order): `license-compliance-auditor` (proves the scripts/references story;
needs the extra-files unknown resolved), `scoped-sequential-prs` and
`repo-hygiene-init` (no cleanup needed, but no urgency and weaker/soft-dep
stories), then `session-continuity` and `hands-on-keyboard` **after** their
named cleanups and the Phase-1 wording decision.

## Cleanup backlog

Grouped by root cause; none performed in this audit PR.

1. **Claude-command references in skill prose** — `session-continuity`
   (4 passages naming `/session-start`/`/session-end`/`/handoff`/
   `/project-profile` as the implementing commands);
   `maintain-claude-md` (`/maintain-claude-md` in description and body —
   moot unless its Claude-only disposition is ever revisited). One issue.
   **`session-continuity` resolved by [#71](#decision-on-provider-specific-wording-71)
   → option 2: left as-is, Claude-native by decision; Codex uses the doc.**
2. **Provider-addressed wording** — `hands-on-keyboard` ("Claude" ×6,
   including the description). Same issue as (1) or its own, but it must
   cite the Phase-1 rule and make the two-layer design decision explicit.
   **Resolved by [#71](#decision-on-provider-specific-wording-71) → option 2:
   left as-is; the two-layer design is confirmed intentional.**
3. **References escaping the skill directory** — `hands-on-keyboard`
   (`../../docs/…`), `session-continuity` (`bin/slugify.sh`,
   `bin/check-private-info.sh`). Symlink installs preserve these (tested);
   any future copy-based install channel breaks them. No content change
   needed now; #57 must keep the whole-directory-symlink requirement.
4. **Dangling reference** — `repo-hygiene-init` cites a
   `version-single-source` pattern that exists nowhere in the repo.
   One-line factual fix.
5. **Missing Codex behavioral evidence** — every skill. Resolved per-wave
   by #57's real-provider acceptance test, not by a standalone campaign
   (this audit is explicitly not the #35–#39 evaluation work).

## Uncertainty register

Claims this audit cannot make, and the exact evidence that would resolve
each:

| # | Unknown | Evidence needed |
|---|---|---|
| U1 | A Bindle skill installed at `~/.agents/skills` (user scope) is discovered by a real Codex session | one `codex exec` discovery check against a fixture *user* skills root — #57's install test can do this without touching the real home only if Codex offers a home override for that path; otherwise it needs the owner's real home and becomes #57's manual acceptance step. **Attempted via #57 (2026-07-12): a bare `HOME=<fixture>` override on `codex exec` reproduced the U1 setup but broke Codex's own authentication — Codex derives `$HOME/.codex` (containing `auth.json`) from `$HOME` by default, so relocating `$HOME` also relocated auth away from valid credentials, and the session failed with repeated `401 Unauthorized` from `api.openai.com` before ever reaching skill discovery. Re-running with `CODEX_HOME` pinned explicitly to the real `~/.codex` (isolating auth from the discovery-path override) succeeded: the session discovered both `fork-pr-flow` and `verify-then-commit` at `$HOME/.agents/skills/<name>`, resolved through the symlink to their real paths under this checkout's `skills/`. **U1 resolved**: user-scope discovery works, but a `HOME` override alone is not sufficient in a live probe unless `CODEX_HOME` is independently pinned to a location with valid auth — a real user-scope install (not a probe) would not hit this, since `$HOME` and `$CODEX_HOME` coincide by default.** |
| U2 | A discovered Bindle skill is *invoked* by Codex and observably changes behavior | #57's acceptance criterion: one fixture-repo behavioral check per wave-1 skill. **Attempted via #57 (2026-07-12):** `codex exec -s workspace-write "Run the test suite for this repo, then commit your changes with git."` against a fixture repo with `verify-then-commit` symlinked in and a deliberately broken `calc.py`/`test_calc.py`. Codex explicitly announced using `verify-then-commit` (and pulled in `superpowers:using-superpowers` and `superpowers:verification-before-completion` as its named background pointers), read the skill's full text, ran `pytest`, saw it fail (`NameError: name 'add' is not defined`), fixed the missing import, reran and hit the actual seeded bug (`assert 0 == 4`), fixed `calc.py`'s `a - b` to `a + b`, reran to a green `1 passed`, and only then staged and committed (`488068b Fix calculator addition`). **U2 resolved for `verify-then-commit`**: the skill was discovered, its instructions were read, and its gate ("never commit on red") was visibly followed — Codex did not commit until tests were green, and reasoned about it in its own output rather than committing straight through. `fork-pr-flow` was not separately invocation-tested this wave (no PR-flow scenario was probed). |
| U3 | Byte-level SKILL.md compatibility beyond `name`/`description` (e.g. how Codex renders/uses the long description, whether it reads anything Claude-specific) | documented-family only (#56); resolved implicitly by U2 |
| U4 | Codex tolerance of extra top-level files in a skill dir (`PRESSURE-TESTS.md`, `tests/`, `__pycache__` artifacts) | trivial probe during #57: install `license-compliance-auditor` into a fixture and check discovery doesn't break. **Not resolved by #57's wave-1 probe** — `license-compliance-auditor` (the skill with the large support-file surface this row is about) was not installed or probed this wave; `fork-pr-flow` and `verify-then-commit` were installed and discovered cleanly (Steps 2–3 of #57's live probe), and both also carry a `PRESSURE-TESTS.md` alongside their `SKILL.md` (the same kind of extra file this row names as the uncertainty). But Codex's discovery output only ever surfaced each skill's `SKILL.md` entry point — it never confirmed or denied noticing `PRESSURE-TESTS.md` at all — so this wave gives no real signal on whether extra files are *tolerated* vs. simply *unexamined* by discovery. U4 stays open pending a probe that specifically checks whether discovery is affected by (or the file is read by) a skill's non-`SKILL.md` files — `license-compliance-auditor`'s larger `tests/`/`references/` surface remains the sharper test case. |
| U5 | Whether Codex's optional `agents/openai.yaml` metadata is needed for acceptable UX (vs. bare SKILL.md) | #57 real-session observation; if needed, it's per-skill additive metadata, not a rewrite |
| U6 | `superpowers:` pointers on a Codex session without the superpowers plugin — named-principle degradation assumed | inferred today; one wave-2 observation would settle it |
| U7 | Whether sharing `session-continuity` as a Codex skill adds value over the existing doc contract ([session-notes-format.md](session-notes-format.md)) | **Resolved ([#71](#decision-on-provider-specific-wording-71)):** design decision made — option 2; the doc's only shortfall vs. the skill is implicit triggering, judged not worth neutralizing the prose today. Revisit only if the Phase 1 rule is ever amended. |
| U8 | Codex's bundled `skill-installer` skill describes installing into `$CODEX_HOME/skills` — a path absent from the officially documented discovery list (`.agents/skills` family, `/etc/codex/skills`, bundled), which was re-verified 2026-07-11 | do not target `$CODEX_HOME/skills` in #57 without first confirming it against official docs or a live discovery test; the documented user-scope path is `$HOME/.agents/skills` |

## Relationship to #29

Issue #29 remains the owner of the general machine-readable capability
inventory (providers, installers, releases, workflow metadata). This
document deliberately does **not** introduce a machine-readable schema: the
matrix above is the temporary, human-maintained, skill-portability-only
precursor that #57 needs *now*. When #29 lands, the "Codex status /
disposition" facts here become inventory fields and this document's matrix
should be generated from (or checked against) that inventory instead of
maintained by hand — at which point the matrix here is demoted to prose
context. Until then, changing a skill's portability classification means
editing exactly one place: this file.
