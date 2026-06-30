# claude-kit

My personal, portable Claude Code toolkit. One local repo holding the agentic
abilities I develop — **skills, subagents, slash commands, and global
instructions** — installed into the user-level `~/.claude/` config so they work
in **every** project, regardless of what that project has (or hasn't) set up.

## The idea

Claude Code reads config at two levels: **project** (`<repo>/.claude/`) and
**user** (`~/.claude/`). The user level applies everywhere. This repo is the
version-controlled source of truth for *my* user-level layer; `bin/install.sh`
symlinks each piece into `~/.claude/` so editing a file here is live everywhere
instantly. Think "dotfiles, for Claude Code."

```
claude-kit/
  skills/<name>/SKILL.md   ->  ~/.claude/skills/<name>      reusable techniques/knowledge
  agents/<name>.md         ->  ~/.claude/agents/<name>.md   specialized subagents
  commands/<name>.md       ->  ~/.claude/commands/<name>.md slash commands (/name)
  CLAUDE.md                ->  ~/.claude/CLAUDE.md          global personal instructions
  bin/install.sh                                            symlink installer
```

Folders/files starting with `_` (templates) or `.`, and `bin/`, are ignored by
the installer.

## Install

```bash
bin/install.sh            # symlink everything into ~/.claude/
bin/install.sh --prune    # also remove links for items deleted from this repo
```

Re-run anytime — it's idempotent. Restart Claude Code (or start a new session)
to pick up newly linked items.

## Add something

Scaffold from the template with the name pre-filled, edit, then link:

```bash
bin/new.sh skill   my-skill      # -> skills/my-skill/SKILL.md
bin/new.sh agent   my-agent      # -> agents/my-agent.md
bin/new.sh command my-command    # -> commands/my-command.md  (becomes /my-command)

$EDITOR skills/my-skill/SKILL.md  # fill it in
bin/install.sh                    # link the new item(s)
```

Each `_template` file documents the required frontmatter and the substitutions
available. A skill's `name:` must match its folder and an agent's must match its
filename — `bin/check.sh` enforces this.

## Make targets

`make help` lists the shortcuts: `check`, `test`, `install`, `hooks`,
`new ARGS="skill x"`, and `release BUMP=minor`. They just wrap the `bin/`
scripts, which remain the source of truth.

## Works alongside any project

The installer is a **good citizen**: it only ever creates, updates, or removes
symlinks that point back into *this* repo. Anything else in `~/.claude/` — a
plugin, or a project-introduced system like a [DomI](https://github.com/domattioli/DomI)
pin/sync setup — is left completely untouched.

- **No clobbering:** if another source already owns a name, the installer reports
  a `CONFLICT` and leaves theirs in place. Rename yours to coexist.
- **Safe prune:** `--prune` only removes broken links pointing into this repo.
- **Precedence:** project-level config wins over user-level on conflict, so a
  project that ships its own setup overrides this toolkit where they overlap —
  your toolkit fills in everywhere else.

## Repo hygiene

Lightweight, dependency-free checks keep the toolkit clean without touching the
wording Claude actually reads.

```bash
brew install pre-commit   # or: pipx install pre-commit
bin/install-hooks.sh      # enable the pre-commit + post-merge git hooks
pre-commit run --all-files  # run every check on demand
```

Checks run through the [pre-commit](https://pre-commit.com/) framework
(`.pre-commit-config.yaml`):

- **Standard hooks** — trailing whitespace (markdown hard breaks preserved),
  end-of-file newline, YAML validity, large-file / merge-conflict / private-key
  guards, and shebang/executable consistency.
- **Managed `shellcheck` + `shfmt`** — fetched by pre-commit, so they're enforced
  even if you haven't installed them system-wide.
- **`bin/check.sh --content-only`** (local hook) — the claude-kit-specific checks:
  every skill/agent has `name` + `description` frontmatter (commands need
  `description`, and `name` must match the folder/filename), repo-relative
  markdown links resolve, and `VERSION` is valid. It only *reports* — it never
  reformats instruction text. Run without `--content-only` (or `make check`) for
  the full standalone aggregate.
- **`bin/test-install.sh`** (local hook) — installs a fixture repo into a temp
  `--home` and asserts links are created, re-runs are idempotent, foreign
  files/links are left untouched, and `--prune` removes only broken links.
- **`post-merge` stage** — re-runs `install.sh` after `git pull`, so new items
  added on another machine get linked automatically.

Bypass hooks for one commit with `git commit --no-verify`. **CI**
(`.github/workflows/ci.yml`) runs `pre-commit run --all-files` on every push and
PR. Dependabot keeps the workflow actions current; run `pre-commit autoupdate`
to bump the hook versions.

No markdown formatter/linter is used on purpose: tools like Prettier/markdownlint
reflow prose and rewrite headings, which would churn the carefully-phrased skill
and agent text. We keep `.editorconfig` for whitespace/newline norms and stop there.

## Versioning & releases

The toolkit is versioned as a whole with [Semantic Versioning](https://semver.org/);
the current version lives in `VERSION` and every release is an annotated git tag.

- **major** — breaking change to how the toolkit installs/structures itself
- **minor** — a new skill, agent, command, or capability
- **patch** — a fix or tweak to something that already exists

Jot changes under `## [Unreleased]` in `CHANGELOG.md` as you go. To cut a release:

```bash
bin/release.sh minor      # or: major | patch
git push && git push --tags
```

`bin/release.sh` refuses to run on a dirty tree or failing checks, then bumps
`VERSION`, rolls the `Unreleased` notes into a dated section, commits, and tags
`vX.Y.Z`. It never pushes — you review first. Pushing the `v*` tag triggers
`.github/workflows/release.yml`, which publishes a GitHub Release from that
version's changelog section. `install.sh` prints the installed version too.

## Building on other sources (no vendoring)

Don't copy other people's skills in here — consume them at their level and
*reference* them:

- **Plugins** (e.g. `superpowers`, or `domattioli/DomI` as a marketplace) are
  installed via `claude plugin ...` and update themselves. Build on them by
  naming them from your own skills:
  `**REQUIRED BACKGROUND:** superpowers:test-driven-development`
  (a soft runtime pointer — nothing to install).
- This repo stays a clean *additive* layer on top of whatever base is present.
