---
name: repo-hygiene-init
description: Use when setting up a new or bare repo, or when asked to add "repo hygiene", tooling, automation, pre-commit, editorconfig, linting/formatting, a Makefile, a LICENSE, a README, or to pick a versioning scheme — bootstrapping the baseline quality scaffolding a project should have.
---

# repo-hygiene-init

## Overview

Bootstrap the baseline hygiene a repo should have: consistent formatting, automated checks, contributor conventions, and a lightweight release path. Aim for **robust without a heavy release ceremony** — automation that catches problems, not process that slows every change.

## When to Use

- New repo, or an existing one missing pre-commit / lint / formatting / a Makefile.
- Operator asks for "repo hygiene", "tooling and automation", "set this up properly".
- Before opening a project up to other contributors.

When NOT to use:
- The repo already has these and the ask is a specific tweak — just do the tweak.

## Do this first: detect, don't assume

Inspect the repo before adding anything. Match the existing stack and don't duplicate what's there.

```bash
ls -a; cat pyproject.toml package.json 2>/dev/null; ls .github/workflows 2>/dev/null
```

Then confirm the versioning scheme with the operator (they have a preference) before wiring release automation.

## The hygiene checklist

| Piece | Purpose | Notes |
|-------|---------|-------|
| `.editorconfig` | Consistent whitespace/charset across editors | Language-agnostic; safe default |
| Formatter | Zero-debate formatting | `ruff format`/`black` (py), `prettier` (js/ts) |
| Linter | Catch bugs & style | `ruff` (py), `eslint` (js/ts) |
| `.pre-commit-config.yaml` | Run format+lint before every commit | Pin hook versions; add an autoupdate workflow |
| `no-commit-to-branch` hook | Block direct commits to `main` — force branch + PR | From `pre-commit-hooks`; `args: [--branch, main]` |
| `Makefile` | Memorable entrypoints (`make check`, `make test`) | Scripts are source of truth; targets save keystrokes |
| `.gitattributes` | Line endings, linguist, export-ignore | Prevents CRLF churn |
| `LICENSE` | Legal clarity | Ask the operator which; don't guess |
| `README.md` | What/why/install/usage | Lead with what it is and why it exists |
| CI workflow | Run the same checks on PRs | Mirror `make check` / the pre-commit hooks |
| CHANGELOG + versioning | Track releases | See below |

## Versioning: pick one, keep it light

Ask the operator which flavor; default recommendation for libraries is **SemVer with a `0.x` phase** (breaking changes allowed via minor bumps while `0.x`). Single-source the version (see the `version-single-source` pattern) so tag, package metadata, and `__version__` never diverge. Keep a Keep-a-Changelog `CHANGELOG.md`.

## Sequencing

1. Detect existing stack; confirm license + versioning choice with the operator.
2. Add config files (editorconfig, gitattributes, formatter+linter config).
3. Add `.pre-commit-config.yaml`; run it once across the repo and commit the reformat as its own commit.
4. Add Makefile targets that wrap the real commands.
5. Add CI mirroring those checks.
6. Add README + LICENSE + CHANGELOG.

Each step is a small, reviewable commit — not one giant "add tooling" blob.

## Common Mistakes

- **Adding tools the stack doesn't use** (eslint in a pure-Python repo). Detect first.
- **One massive commit** mixing reformat + config + docs. Separate the noisy reformat commit.
- **Guessing the license or version scheme** — both are operator decisions.
- **Unpinned pre-commit hooks** — pin versions and add an autoupdate workflow instead.
