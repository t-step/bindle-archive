# Provider interoperability

This is the Phase 1 migration contract for renaming `claude-kit` to Bindle and
making the repo provider-aware without pretending every provider has the same
primitives.

## What Bindle is

Bindle is a portable agentic-workflow kit. It evolved from `claude-kit`, a
Claude Code-focused personal toolkit, but its durable value is broader:
instructions, review discipline, reusable workflows, terminal-first habits, and
safe installation boundaries.

Bindle is not a lowest-common-denominator abstraction. Provider-specific
surfaces stay provider-specific. When a concept does not map cleanly between
Claude Code and Codex, Bindle documents the difference instead of forcing a
fake adapter.

## Provider surfaces

### Claude Code

Bindle supports the existing Claude Code surfaces:

- repo-local `CLAUDE.md`;
- global `CLAUDE.md` from `global/CLAUDE.md`;
- `skills/`;
- `agents/`;
- `commands/`;
- install target `~/.claude/...`.

The current Claude install layout remains supported:

| Repo path | Claude install target |
|---|---|
| `skills/<name>/` | `~/.claude/skills/<name>` |
| `agents/<name>.md` | `~/.claude/agents/<name>.md` |
| `commands/<name>.md` | `~/.claude/commands/<name>.md` |
| `global/CLAUDE.md` | `~/.claude/CLAUDE.md` |

### Codex

Bindle supports Codex where the mapping is real:

- repo-local `AGENTS.md`;
- global/user `AGENTS.md` only when an explicit target directory is configured;
- provider guidance expressed as direct instructions.

Bindle does not assume Claude skills, slash commands, or agents are Codex
features. Phase 1 does not introduce a Codex plugin system or claim support for
undocumented Codex install paths.

When installing Codex global guidance, the installer must require an explicit
target such as `--codex-home <dir>`. On this machine, lowercase `~/.codex` is the
local Codex configuration convention, so examples may use `--codex-home
~/.codex`. That is an explicit target directory, not a claim that Codex has a
standard managed global `AGENTS.md` path.

## Shared concepts

These concepts are provider-independent and should be expressed in both Claude
and Codex guidance where appropriate:

- project instructions;
- reusable workflows;
- review discipline;
- terminal-first habits;
- small changes;
- verification before completion;
- no pushing without user permission;
- privacy and personal-info safety.

## Non-equivalences

- Claude skills are not automatically Codex skills.
- Claude slash commands are not automatically Codex commands.
- Claude agents are not automatically Codex agents.
- `CLAUDE.md` and `AGENTS.md` should share intent, but they should not be blindly
  identical.

Provider files may repeat some rules in provider-native language. That is
intentional. Drift should be managed by review, not by merging dissimilar
surfaces into one generated file.

## Install strategy

The installer should support:

```bash
bin/install.sh --provider claude
bin/install.sh --provider codex --codex-home ~/.codex
bin/install.sh --provider all --codex-home ~/.codex
```

For backward compatibility, `bin/install.sh` with no provider should keep the
existing Claude install behavior.

Claude:

- install into `~/.claude` by default;
- continue supporting `--home <dir>` for tests and explicit alternate Claude
  targets;
- install `skills/`, `agents/`, `commands/`, and `global/CLAUDE.md`.

Codex:

- install only `global/AGENTS.md` as `<codex-home>/AGENTS.md`;
- require `--codex-home <dir>` for `--provider codex` and `--provider all`;
- document that `--codex-home` is an explicit target directory;
- do not install Claude-only `skills/`, `agents/`, or `commands/`.

Conflict safety applies to every provider target:

- do not overwrite real files;
- do not overwrite symlinks pointing elsewhere;
- only replace symlinks that already point back into this repo;
- prune only broken symlinks pointing back into this repo;
- keep dry-run behavior if it is added later.

## Backward compatibility

Existing Claude usage should keep working:

- `bin/install.sh` remains a Claude install by default;
- `bin/install.sh --home <dir>` remains a Claude test/alternate-home option;
- Claude surface validation remains in `bin/check.sh`;
- Claude skills, agents, and commands keep their existing shape.

New names should prefer `BINDLE_*` and `~/.bindle`.

Deprecated aliases may remain temporarily:

- `CLAUDE_KIT_*`;
- `~/.claude-kit`.

Bindle must not silently move user data from old directories to new ones.
Migration paths should be documented and opt-in.

## Phase 1 scope

In scope:

- rename user-facing project branding to Bindle / `bindle`;
- add this provider-interoperability contract;
- update installer, checks, and installer tests to be provider-aware;
- add `global/AGENTS.md`;
- update README and docs;
- preserve Claude Code support.

Out of scope:

- full schema redesign;
- new package manager;
- external publishing;
- pushing changes;
- speculative Codex plugin system;
- automatic conversion of Claude skills, slash commands, or agents into Codex
  assets;
- silent migration from `~/.claude-kit` to `~/.bindle`.
