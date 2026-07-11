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

**Status: HOLDS 6/6, but the RED arm did not establish a failing baseline —
see "What this run does and doesn't establish" below.**

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
