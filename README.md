# claude-toolkit

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
claude-toolkit/
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

```bash
# A skill
cp -r skills/_template skills/my-skill && $EDITOR skills/my-skill/SKILL.md

# A subagent
cp agents/_template.md agents/my-agent.md && $EDITOR agents/my-agent.md

# A slash command  (becomes /my-command)
cp commands/_template.md commands/my-command.md && $EDITOR commands/my-command.md

bin/install.sh            # link the new item(s)
```

Each `_template` file documents the required frontmatter and the substitutions
available.

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

## Building on other sources (no vendoring)

Don't copy other people's skills in here — consume them at their level and
*reference* them:

- **Plugins** (e.g. `superpowers`, or `domattioli/DomI` as a marketplace) are
  installed via `claude plugin ...` and update themselves. Build on them by
  naming them from your own skills:
  `**REQUIRED BACKGROUND:** superpowers:test-driven-development`
  (a soft runtime pointer — nothing to install).
- This repo stays a clean *additive* layer on top of whatever base is present.
