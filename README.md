# Bindle

Bindle is my personal, portable agentic-workflow kit. It started as
`claude-kit`, a Claude Code toolkit, and now keeps that Claude workflow intact
while adding a small interoperability foundation for Codex.

Bindle is not a fake universal abstraction. Claude Code and Codex have
different installed surfaces, so Bindle documents what maps cleanly and keeps
provider-specific assets provider-specific.

## Provider support

Claude Code support is the mature path today:

```
skills/<name>/SKILL.md   ->  ~/.claude/skills/<name>      Claude skills
agents/<name>.md         ->  ~/.claude/agents/<name>.md   Claude subagents
commands/<name>.md       ->  ~/.claude/commands/<name>.md Claude slash commands
global/CLAUDE.md         ->  ~/.claude/CLAUDE.md          Claude global instructions
CLAUDE.md                     (not installed)             Bindle project guidance for Claude
```

Codex support is intentionally narrower:

```
global/AGENTS.md         ->  <explicit-codex-home>/AGENTS.md
AGENTS.md                     (not installed)             Bindle project guidance for Codex
```

On this machine, lowercase `~/.codex` is the local Codex configuration
convention, so examples use that as an explicit target. Bindle does not claim an
undocumented Codex global install standard.

Claude skills are not automatically Codex skills. Claude slash commands are not
automatically Codex commands. Claude agents are not automatically Codex agents.
The standing contract (with a per-provider capability matrix) is in
[docs/provider-interop.md](docs/provider-interop.md); the Codex-side guide is
[docs/using-bindle-with-codex.md](docs/using-bindle-with-codex.md).

## Install

Claude remains the default for backward compatibility:

```bash
bin/install.sh
bin/install.sh --provider claude
bin/install.sh --provider claude --prune
```

Install Codex global guidance only into an explicit target directory:

```bash
bin/install.sh --provider codex --codex-home ~/.codex
bin/install.sh --provider all --codex-home ~/.codex
```

For tests or alternate Claude targets, `--home DIR` still means the Claude home:

```bash
bin/install.sh --home /tmp/claude-home
```

Re-run anytime. The installer is idempotent and conflict-safe.

## Ownership boundaries

Bindle is a good citizen: it only creates, updates, or removes symlinks that
point back into this repo. Anything else in an installed surface is foreign and
left untouched.

- **No clobbering:** a real file or foreign symlink at a destination is reported
  as `CONFLICT`.
- **Safe prune:** `--prune` removes only broken symlinks pointing into this repo.
- **Provider-specific install:** Claude surfaces go under the Claude home;
  Codex Phase 1 installs only `global/AGENTS.md` to the explicit Codex target.

The full contract is in [docs/ownership-boundaries.md](docs/ownership-boundaries.md).

## Add Claude-native assets

Claude skills, agents, and slash commands keep their Claude-native format,
frontmatter, trigger conventions, and install layout.

```bash
bin/new.sh skill   my-skill      # -> skills/my-skill/SKILL.md
bin/new.sh agent   my-agent      # -> agents/my-agent.md
bin/new.sh command my-command    # -> commands/my-command.md

$EDITOR skills/my-skill/SKILL.md
bin/install.sh --provider claude
```

Each `_template` file documents the required Claude frontmatter. A skill's
`name:` must match its folder and an agent's must match its filename;
`bin/check.sh` enforces this as a Claude-provider regression check.

## Session continuity

The kit carries context across sessions with Claude slash commands and portable
plain-Markdown notes:

- `/session-start` — orient: repo state, project profile, last session's
  notes/handoff, validation gates. Read-only.
- `/session-end` — write a durable session note: commits, checks actually run,
  decisions, risks, deferred work, candidate workflow improvements.
- `/handoff` — one self-contained prompt a future session can start from cold.
- `/project-profile` — durable project facts; repo export only on explicit
  request, sanitized.

Notes prefer `BINDLE_NOTES_DIR`, then the deprecated `CLAUDE_KIT_NOTES_DIR`, then
`~/.bindle`. Existing `~/.claude-kit` data is not moved automatically; keep using
the alias or migrate by hand when you choose. See
[docs/notes-home.md](docs/notes-home.md). The provider-neutral contract behind
these commands — usable from Codex too — is
[docs/session-notes-format.md](docs/session-notes-format.md).

## Hands-on-keyboard mode

A collaboration mode that keeps the user driving — hands on the code,
terminal, diffs, and tests — with Claude acting as navigator rather than an
autonomous implementer. The `hands-on-keyboard` skill applies it in Claude
Code; the provider-neutral contract (roles, escalation modes, how to follow
it manually from Codex or another assistant) is
[docs/hands-on-keyboard.md](docs/hands-on-keyboard.md).

## Checks and tests

```bash
make check
make test
bin/test-install.sh
```

`make check` wraps `bin/check.sh`. It still validates Claude-specific
conventions for `skills/*/SKILL.md`, `agents/*.md`, and `commands/*.md`.
Codex files are direct instruction files and are not required to pass Claude
skill, agent, or slash-command frontmatter checks.

`make test` runs installer tests for Claude install, explicit Codex install,
`--provider all`, conflict safety, and prune safety.

## Developing Bindle

Read [CONTRIBUTING.md](CONTRIBUTING.md) before adding or changing assets. This
repo uses branch-and-PR discipline, small reviewable changes, and verification
before completion. Do not push unless explicitly asked.

## Make targets

`make help` lists the shortcuts: `check`, `test`, `install`, `hooks`,
`new ARGS="skill x"`, and `release BUMP=minor`. The scripts in `bin/` remain the
source of truth.

## Sharing

Share reusable workflows through Git at the right level: a shared workflow repo,
a provider-native project surface such as `.claude/` for Claude Code, or direct
provider instructions where appropriate. Do not copy whole user config
directories around. Personal preferences stay personal; private notes are never
promoted automatically. See [docs/sharing-skills.md](docs/sharing-skills.md).

## Versioning

Bindle is versioned as a whole with Semantic Versioning. The current version
lives in `VERSION`, and `bin/release.sh` cuts an annotated local tag. It never
pushes.
