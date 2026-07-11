# repo-hygiene-init — pressure-test log

Per CONTRIBUTING's RED → GREEN → REFACTOR loop (superpowers:writing-skills), a
skill isn't done until an agent has been watched under pressure. This log
records what was actually pressure-tested with subagents, so nobody has to
guess which claims are verified and which are still draft. Closes issue #14.

This skill had no pressure test at all before this log — a draft since it
shipped. Model: Sonnet 5 throughout (this campaign's main-loop model; no
`model` override needed), 3 reps per arm. Ground truth is the filesystem —
`git log`/`git diff --stat` against each fixture's initial commit, `git grep`
for tool names, and the actual `.pre-commit-config.yaml` / `Makefile` /
`.github/workflows/ci.yml` contents — never the agent's chat self-report.

## Claim — detects and matches an existing stack instead of imposing its own defaults

**Status: HOLDS, but NOT established as load-bearing on Sonnet 5. The original
run (below) had a contaminated RED arm; the #65 harder-fixture rerun (further
below) built the stronger "detect vs. impose" fixture #14 lacked and still could
not falsify the skill-naive baseline (4/4 clean-baseline reps matched). See the
"#65 rerun" section at the bottom.**

Fixture: a throwaway Python package (`mypkg`) with **black + isort + flake8
already fully configured** (`[tool.black]`/`[tool.isort]` in `pyproject.toml`,
a real `.flake8`, both at a deliberately non-default `line-length = 100`) but
nothing wiring them up — no pre-commit, no Makefile, no CI, no LICENSE, no
`.editorconfig`. The failure mode under test is the one the skill's own
"Common Mistakes" names: reaching for a different/modern default (most
plausibly **ruff**, which most current agents reach for first when asked for
"Python linting/formatting" without checking existing config) instead of
matching what's already there. **RED** — "set up proper repo hygiene...
inspect first... use your own judgment... no need to pull in any special
skills or automated workflows for this." **GREEN** — same prompt, told
explicitly to use the `repo-hygiene-init` skill. Both arms were told to
proceed autonomously (pick MIT + SemVer 0.1.0 defaults) since no operator was
available to ask, and to commit directly to `main` in the fixture repo (no
branch-protection concern in the fixture itself). Ground truth per rep:
`git grep -i ruff` (any hit = imposed a conflicting default), whether
`[tool.black]`/`[tool.isort]` survived in `pyproject.toml`, whether
`.pre-commit-config.yaml`/`Makefile`/CI wire up black+isort+flake8 (not a
substitute), and `git status --porcelain` for stray mutation.

| Signal | RED (3 reps) | GREEN (3 reps) |
|---|---|---|
| `ruff` mentioned anywhere in tracked files? | **0/3** | **0/3** |
| `[tool.black]`/`[tool.isort]` preserved in `pyproject.toml`? | **3/3** | **3/3** |
| `.pre-commit-config.yaml` wires up black+isort+flake8 (not a substitute)? | **3/3** | **3/3** |
| `Makefile` `format`/`lint` targets call black+isort+flake8? | **3/3** | **3/3** |
| CI mirrors the same three tools? | 2/3 (1 rep skipped CI, added nothing else instead) | 2/3 (1 rep skipped CI, added nothing else instead) |
| Repo mutated beyond the fixture directory? | 0/3 | 0/3 |

**6/6 on the substitution check (the actual claim)** — no rep, in either arm,
swapped in ruff or any other formatter/linter in place of the repo's existing
choice; every pre-commit config, Makefile, and CI workflow that got written
called black+isort+flake8 specifically, at the fixture's existing settings
(several reps also fixed a real pre-existing bug: `.flake8`'s `exclude` didn't
list `.venv`/`*.egg-info`, so a local dev venv would drown real lint findings
in third-party noise — a legitimate "match what's here" catch, not scope
creep).

**What this run does and doesn't establish.** One of the three RED reps
self-discovered and invoked the `repo-hygiene-init` skill despite "no need to
pull in any special skills" (confirmed via a `Skill` tool-use with
`{"skill":"repo-hygiene-init"}` in its transcript) — the same contamination
pattern already documented for `scoped-sequential-prs` and
`license-compliance-auditor`. The other two RED reps were genuinely
skill-naive (confirmed clean — their only `repo-hygiene-init` occurrences are
the standard installed-skills listing in their system reminder, never a
`Skill` tool-use). **Those two clean-baseline reps also matched the existing
stack correctly, with no ruff and no substitution.** That means this specific
fixture does not discriminate skill vs. no-skill behavior — Sonnet 5's
baseline judgment already avoids the "impose ruff on an existing
black/isort/flake8 repo" mistake when the existing signal is this
unambiguous (one fully-configured stack, no conflicting or partial signal).
The claim **holds** as tested, but this run doesn't prove the skill is
*load-bearing* for it — a harder fixture (partial/inconsistent existing
config, or two plausible candidate stacks) is needed to actually stress
"detect vs. impose" the way the flagship claims in other skills' logs do. See
Caveats.

**Incidental observation (not a scored claim): commit sequencing.** The
skill's own "Sequencing" section calls for small, single-purpose commits, not
"one giant add-tooling blob" (also named in "Common Mistakes"). The two clean
RED reps each landed their entire setup in **one commit**; the contaminated
RED rep and all three GREEN reps split their work into **7–9 incremental
commits** matching the skill's own step order (config → pre-commit → tests →
Makefile → CI → docs/license). This wasn't part of the claim's scoring
rubric going in, so it's reported as a secondary signal, not a verified
result — but it's the one place in this run where invoking the skill visibly
changed behavior, and a candidate flagship claim for a future rerun.

**No skill edit (Iron Law).** The claim held 6/6 on the substitution check;
`SKILL.md` is unchanged.

**Caveats — untested:**
- **A fixture that would actually stress "detect vs. impose"** is untested:
  this one used a single, fully-configured, unambiguous stack. A repo with
  partial/inconsistent existing tooling (e.g. a stale `.flake8` but no
  `pyproject.toml` config, or two plausible stacks — e.g. both a `setup.cfg`
  `[flake8]` section and hints of a prior ruff migration) is a stronger
  candidate for a rerun that could actually falsify a naive baseline.
- **A JS/TS or mixed-language repo** is untested — the skill's other named
  mistake ("eslint in a pure-Python repo") wasn't exercised here since the
  fixture was single-language throughout.
- **The versioning/license confirm-with-operator step** was deliberately
  bypassed in both arms (fixture instructions told reps to default rather
  than block on a question) — untested whether either arm would have
  correctly paused for a real operator instead of guessing.
- **Weaker/other-model brackets** are untested; this ran on Sonnet 5 only.

## #65 rerun — harder "half-migrated" fixture (the detect-vs-impose stressor #14 lacked)

**Status: the harder fixture STILL does not establish the claim as load-bearing
on Sonnet 5.** The skill-naive baseline held 4/4; the sole ruff-imposition
across all 7 reps this campaign occurred *with* the skill loaded, not without.
Closes the #65 verification gap by answering its question rather than by
proving the skill load-bearing. Model: Sonnet 5, 7 reps total. Ground truth is
the filesystem (`git grep -i ruff` excluding `.gitignore`/Makefile-clean
`.ruff_cache` cache paths, `[tool.*]` survival, config file presence) plus each
subagent's own JSONL transcript grepped for a real `Skill` tool-use — never the
chat self-report alone.

**Why a new fixture.** #14's fixture was one fully-configured, unambiguous
stack, and its two clean-baseline reps matched it anyway, so it never
discriminated skill vs. no-skill. This rerun built the harder case #14's caveats
called for: a **half-migrated** repo — `flake8` (`setup.cfg`) and `isort`
(`.isort.cfg`) both configured at a non-default `line-length = 100`, but **no
formatter, no pre-commit, no Makefile, no CI, and no ruff config**. That
maximizes the "impose" temptation: an agent asked for "repo hygiene" is pulled
toward the modern all-in-one (**ruff**, which folds in lint + format + import
sort) and can orphan the existing flake8+isort. Correct "detect and match"
behavior is to keep flake8+isort, add the compatible missing piece (black, which
`isort`'s `profile = black` and flake8's `E203/W503` ignores already imply), and
wire all three up.

**Two arms.** A **skill-naive** arm (4 reps) was hard-forbidden from invoking the
`Skill` tool ("you are the control arm… do not call any skill"); a **soft-framed**
arm (3 reps, the "no need for special skills" wording #14 used) was run first.

| Signal | Soft-framed arm (3 reps) | Skill-naive arm (4 reps) |
|---|---|---|
| Actually invoked the `repo-hygiene-init` `Skill` tool (transcript-verified)? | **3/3** | **0/4** |
| Matched: kept flake8 + isort, added black, no ruff substitution? | **2/3** | **4/4** |
| Imposed ruff in place of the existing flake8+isort? | **1/3** (`red-3`) | **0/4** |
| Existing `[flake8]` / `.isort.cfg` preserved? | 2/3 | 4/4 |
| Repo mutated beyond its fixture directory? | 0/3 | 0/4 |

**Finding 1 — the naive baseline still doesn't fail.** All 4 hard-suppressed,
transcript-verified skill-naive reps detected and matched the existing stack;
none reached for ruff. They articulated the exact reasoning the skill teaches,
unprompted — e.g. *"Ruff would be my default on a truly greenfield repo, but
'inspect first' here meant respecting the existing choice,"* and *"disrupting an
existing, working, deliberately-coordinated config wasn't warranted."* Per the
writing-skills control rule (*if the control doesn't exhibit the failure, there
is nothing to fix*), this is the honest result: on Sonnet 5, "detect and match"
is baseline competence, not skill-conferred — even under a fixture built
specifically to break it. This **confirms and strengthens** #14's own caveat
rather than overturning it.

**Finding 2 — contamination is now a reliability signal, not noise.** Under the
soft "no need for special skills" framing, **3/3** reps self-invoked
`repo-hygiene-init` anyway (all three confirmed by a real `Skill` tool-use in
the transcript, not just the self-report). #14 saw this at 1/3. Only an explicit
"do not invoke the Skill tool" prohibition produced clean baselines. Practical
read: the skill's trigger is strong enough that on this task it is effectively
always-on — which makes the with-skill behavior the operationally relevant one.

**Finding 3 (candidate gap, NOT acted on) — the skill did not prevent the one
substitution.** The sole ruff-imposition, `red-3`, happened *with* the skill
loaded, rationalized as *"consolidated flake8 + isort into ruff… kept the
existing line-length=100 / black-compatible convention so the switch is
behavior-preserving, not a style change."* The skill's "Common Mistakes" names
*"adding tools the stack doesn't use (eslint in a pure-Python repo)"* but not
this move — *replacing* a working linter/formatter with a preferred all-in-one
and reframing it as consolidation. That's a plausible loophole. It is **not**
patched here: it is n=1, in the contaminated arm, and the Iron Law forbids a
skill edit without a clean failing baseline demonstrating the counter is needed.
Recorded as the candidate for any future targeted rerun (a dedicated with-skill
vs. naive test of the "ruff consolidation" temptation, more reps).

**No skill edit (Iron Law).** The skill-naive baseline did not fail, so
`SKILL.md` is unchanged.

**Caveats — untested (unchanged or newly noted):**
- **Commit sequencing is NOT measurable from this run.** #14's incidental
  sequencing signal (naive = 1 blob, skill = 7–9 commits) did not replicate here
  because every prompt this campaign explicitly asked for "small, sensible
  commits" — so all arms split work (naive 9–11, soft 8–15). The prompt bias
  contaminates the signal; a clean sequencing test must not prime commit
  granularity.
- **Two genuinely-ambiguous candidate stacks** (e.g. `setup.cfg [flake8]`
  alongside a half-written `[tool.ruff]`) remain untested — but note "match" is
  ill-defined there (ruff is already partly present), so it tests something
  other than this claim.
- **A JS/TS or mixed-language repo** (the "eslint in a pure-Python repo"
  mistake) remains untested — a different named mistake, out of scope for the
  #65 "detect vs. impose" gap.
- **Weaker/other-model brackets** remain untested; this ran on Sonnet 5 only. A
  weaker model is the most likely place a naive baseline would actually fail and
  the skill would earn its keep.
