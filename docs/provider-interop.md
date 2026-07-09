# Provider interoperability

The standing contract for how Bindle supports multiple providers without
pretending they share the same primitives. It began as the Phase 1 migration
contract for the `claude-kit` → Bindle rename; the rename is done, but the
rules here are permanent, not migration caveats.

## What Bindle is

Bindle is a portable agentic-workflow kit. It evolved from `claude-kit`, a
Claude Code-focused personal toolkit, but its durable value is broader:
instructions, review discipline, reusable workflows, terminal-first habits,
and safe installation boundaries.

Bindle is not a lowest-common-denominator abstraction. Provider-specific
surfaces stay provider-specific. When a concept does not map cleanly between
Claude Code and Codex, Bindle documents the difference instead of forcing a
fake adapter.

## Non-equivalences (permanent)

These are permanent rules, not a phase:

- Claude skills are not Codex skills.
- Claude slash commands are not Codex commands.
- Claude agents are not Codex agents.
- `CLAUDE.md` and `AGENTS.md` should share intent, but they should not be
  blindly identical.

Provider files may repeat some rules in provider-native language. That is
intentional. Drift is managed by review, not by merging dissimilar surfaces
into one generated file.

What *does* travel between providers is the workflow contract underneath the
provider assets — see [session-notes-format.md](session-notes-format.md) for
the first one (session continuity). Portable workflows are specified as
docs + Markdown conventions + plain scripts; each provider automates them
with its own native surface, or follows them manually.

## Provider capability matrix

What each tool can actually do with Bindle today. This is a working map for
deciding which tool to reach for, not a scorecard — "manual via docs" is a
supported path, not a deficiency.

| Capability | Claude Code | Codex |
|---|---|---|
| Project guidance | native (`CLAUDE.md`) | native (`AGENTS.md`; `CLAUDE.md` as fallback context) |
| Global preferences | installed (`global/CLAUDE.md` → `~/.claude/CLAUDE.md`) | installed guidance (`global/AGENTS.md` → explicit `--codex-home` target) |
| Installer support | default provider (`bin/install.sh`) | explicit target only (`--provider codex --codex-home DIR`) |
| Skills | native (`skills/`) | not a Codex primitive |
| Slash commands | native (`commands/`) | not a Codex primitive |
| Subagents | native surface (`agents/`) — not currently shipped except `_template.md` | not a Codex primitive |
| Hooks | Claude-only concept; Bindle ships none today | not a Codex primitive |
| Session continuity | native automation (skill + `/session-*`, `/handoff`, `/project-profile`) | manual via docs/scripts ([using-bindle-with-codex.md](using-bindle-with-codex.md)) |
| Privacy scanner | `bin/check-private-info.sh` via pre-commit / `make check` / by hand | same script, run by hand |
| Slug helper | `bin/slugify.sh` (referenced by the skill) | same script, run by hand |
| Workflow improvement loop | native (`/workflow-review`, `/promote-insight`) | manual via [iterative-improvement.md](iterative-improvement.md); the promotion commands are Claude-only |

Note the subagent row honestly: `agents/` currently contains only
`_template.md`, so Bindle has an agent *surface* but no real shipped
subagents yet.

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
- global/user `AGENTS.md` only when an explicit target directory is
  configured;
- provider guidance expressed as direct instructions;
- provider-neutral workflow docs and scripts, followed manually — see
  [using-bindle-with-codex.md](using-bindle-with-codex.md).

Bindle does not assume Claude skills, slash commands, or agents are Codex
features, and does not introduce a Codex plugin system or claim support for
undocumented Codex install paths.

When installing Codex global guidance, the installer requires an explicit
target such as `--codex-home <dir>`. On this machine, lowercase `~/.codex` is
the local Codex configuration convention, so examples may use `--codex-home
~/.codex`. That is an explicit target directory, not a claim that Codex has a
standard managed global `AGENTS.md` path.

## Shared concepts

These concepts are provider-independent and should be expressed in both
Claude and Codex guidance where appropriate:

- project instructions;
- reusable workflows;
- review discipline;
- terminal-first habits;
- small changes;
- verification before completion;
- no pushing without user permission;
- privacy and personal-info safety;
- session continuity via the notes home
  ([session-notes-format.md](session-notes-format.md)).

## Install strategy

The installer supports:

```bash
bin/install.sh --provider claude
bin/install.sh --provider codex --codex-home ~/.codex
bin/install.sh --provider all --codex-home ~/.codex
```

For backward compatibility, `bin/install.sh` with no provider keeps the
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

Existing Claude usage keeps working:

- `bin/install.sh` remains a Claude install by default;
- `bin/install.sh --home <dir>` remains a Claude test/alternate-home option;
- Claude surface validation remains in `bin/check.sh`;
- Claude skills, agents, and commands keep their existing shape.

New names prefer `BINDLE_*` and `~/.bindle`.

Deprecated aliases remain temporarily:

- `CLAUDE_KIT_*`;
- `~/.claude-kit`.

Bindle must not silently move user data from old directories to new ones.
Migration paths are documented and opt-in.

## Standing boundaries

Out of scope for Bindle's provider story until deliberately revisited:

- a full schema redesign or new package manager;
- external publishing;
- pushing changes (the user pushes; agents don't);
- a speculative Codex plugin/skill system;
- automatic conversion of Claude skills, slash commands, or agents into
  Codex assets;
- silent migration from `~/.claude-kit` to `~/.bindle`.

Growing the portable side happens the way session continuity did: extract
the provider-neutral contract into a doc, keep provider automation
provider-native, and let each provider participate at the level it actually
supports.
