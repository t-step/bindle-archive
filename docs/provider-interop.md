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

Codex columns below were re-baselined 2026-07-11 against current official
Codex/OpenAI documentation (issue #56); see
[Codex capability re-baseline](#codex-capability-re-baseline-2026-07-11) below
for the per-surface detail and sources. **Codex now has native primitives for
Agent Skills, subagents, hooks, and plugins that did not exist when this
matrix was first written.** None of that changes the non-equivalence rules
above: those are Bindle's *own* Claude-format assets (`skills/`, `agents/`,
Claude hooks) not being Codex-native — Codex having its own, differently
shaped version of the same concept doesn't make Bindle's Claude assets
portable to it.

| Capability | Claude Code | Codex |
|---|---|---|
| Project guidance | native (`CLAUDE.md`) | native (`AGENTS.md`; `CLAUDE.md` read as fallback context — a Bindle/Codex-session convention, not an OpenAI-documented Codex behavior) |
| Global preferences | installed (`global/CLAUDE.md` → `~/.claude/CLAUDE.md`) | installed guidance (`global/AGENTS.md` → explicit `--codex-home` target) |
| Installer support | default provider (`bin/install.sh`) | explicit target only (`--provider codex --codex-home DIR`) |
| Skills | native (`skills/<name>/SKILL.md` → `~/.claude/skills/<name>`) | **native primitive exists** (Codex Agent Skills: `SKILL.md` with `name`/`description` frontmatter, discovered under `.agents/skills` — repo- and user-scoped, not `~/.codex`). Bindle does not install to that path today; no adapter exists yet (tracked in #57). Same underlying "open agent skills standard" family as Claude's format, but not proven byte-compatible. Per-skill portability classification and first-wave recommendation: [skill-portability-audit.md](skill-portability-audit.md) (#61). |
| Slash commands | native (`commands/`) | **no direct equivalent.** Codex's closest analog, Markdown "custom prompts" under `~/.codex/prompts/`, is officially deprecated by OpenAI in favor of skills — do not build a Bindle adapter onto a deprecated surface. |
| Subagents | native surface (`agents/`) — not currently shipped except `_template.md` | **native primitive exists**, but in an incompatible format: standalone TOML files (`name`/`description`/`developer_instructions`/`model`/…) at `~/.codex/agents/` (personal) or `.codex/agents/` (project) — not Bindle's Markdown+frontmatter `agents/<name>.md` shape. Converting would need a real per-file adapter, not a copy; out of scope per the product-boundary non-goal on automatic asset conversion. Untested. |
| Hooks | native — Bindle ships one today: `global/hooks/nested-notes-guard.py` (PreToolUse, wired manually in `~/.claude/settings.json`; `bin/install.sh` does not manage hook wiring yet) | **native primitive exists**: `hooks.json` / `[hooks]` in `config.toml`, discovered at `~/.codex/hooks.json`, `~/.codex/config.toml`, `<repo>/.codex/hooks.json`, `<repo>/.codex/config.toml`, plus plugin-bundled hooks. Different config shape and trust model (`/hooks`) than Claude's `settings.json` matcher hooks; Bindle has no Codex-hooks adapter today. Untested. |
| Plugins | not a Claude Code primitive Bindle uses | **native primitive with no Claude Code equivalent**: marketplace-installed bundles (skills + MCP servers/apps + hooks + scheduled-task templates) via `/plugins`. No corresponding Bindle capability on either provider today. |
| Session continuity | native automation (skill + `/session-*`, `/handoff`, `/project-profile`) | manual via docs/scripts ([using-bindle-with-codex.md](using-bindle-with-codex.md)) |
| Privacy scanner | `bin/check-private-info.sh` via pre-commit / `make check` / by hand | same script, run by hand |
| Slug helper | `bin/slugify.sh` (referenced by the skill) | same script, run by hand |
| Workflow improvement loop | native (`/workflow-review`, `/promote-insight`) | manual via [iterative-improvement.md](iterative-improvement.md); the promotion commands are Claude-only |

Note the subagent row honestly: `agents/` currently contains only
`_template.md`, so Bindle has an agent *surface* but no real shipped
subagents yet.

## Codex capability re-baseline (2026-07-11)

Correction of Bindle's factual model of current Codex-native surfaces,
resolving issue #56 (prerequisite for #57 and #61). No new provider
integration was implemented here — this section only records verified facts,
each against current official Codex/OpenAI documentation as the authority.
Per-surface, the five distinctions issue #56 requires:

**Agent Skills**

1. Native primitive: yes.
2. Format compatibility: same family (`SKILL.md` with `name`/`description`
   frontmatter, optional `scripts/`, `references/`, `assets/`), both built on
   the open agent skills standard ([agentskills.io](https://agentskills.io)) —
   but not verified byte-compatible; Codex also supports an optional
   `agents/openai.yaml` metadata file Claude does not use.
3. Bindle installs/supports today: no. `bin/install.sh --provider codex`
   installs only `global/AGENTS.md`.
4. Adapter required: yes — Codex discovers skills at `$CWD/.agents/skills`,
   `$REPO_ROOT/.agents/skills`, `$HOME/.agents/skills`, `/etc/codex/skills`
   (admin), or bundled system skills — never `~/.claude/skills` or a bare
   `skills/` repo dir. An install target would need to place (copy or
   symlink) compatible skills under one of those paths.
5. Tested: partially — the issue #61 audit
   ([skill-portability-audit.md](skill-portability-audit.md)) ran a
   read-only Codex discovery probe on 2026-07-11: two Bindle skills
   symlinked into a fixture's repo-scope `.agents/skills` were discovered
   by a real Codex session (official docs also confirm symlinked skill
   folders are followed). Invocation/behavior remains untested.
   Source: [learn.chatgpt.com/docs/build-skills](https://learn.chatgpt.com/docs/build-skills)
   (redirected from `developers.openai.com/codex/skills`), verified 2026-07-11.

**Subagents**

1. Native primitive: yes — built-in agents `default`, `worker`, `explorer`,
   plus user-defined custom agents.
2. Format compatibility: no. Custom agents are TOML
   (`name`, `description`, `developer_instructions`, optional `model`,
   `model_reasoning_effort`, `sandbox_mode`, `mcp_servers`, `skills.config`),
   not Bindle's Markdown+frontmatter `agents/<name>.md`.
3. Bindle installs/supports today: no.
4. Adapter required: yes, and it would be a real per-field translation
   (Markdown persona/instructions → TOML `developer_instructions` + model
   config), not a copy — treat as out of scope under the product-boundary
   non-goal on automatic asset conversion unless explicitly revisited.
5. Tested: no.
   Source: [learn.chatgpt.com/docs/agent-configuration/subagents.md](https://learn.chatgpt.com/docs/agent-configuration/subagents.md)
   (redirected from `developers.openai.com/codex/subagents.md`), verified
   2026-07-11.

**Hooks**

1. Native primitive: yes — lifecycle events `PreToolUse`, `PermissionRequest`,
   `PostToolUse`, `PreCompact`, `PostCompact`, `UserPromptSubmit`,
   `SubagentStop`, `Stop` (turn-scoped) and `SessionStart`, `SubagentStart`
   (thread/subagent-scoped), with a trust/review model (`/hooks`,
   hash-pinned trust, `--dangerously-bypass-hook-trust`).
3. Bindle installs/supports today: no — Bindle's one shipped hook
   (`global/hooks/nested-notes-guard.py`) targets Claude Code's
   `settings.json` matcher-hook shape only.
2. Format compatibility: no. Codex hooks are `hooks.json` or a `[hooks]`
   table in `config.toml`, at `~/.codex/hooks.json`, `~/.codex/config.toml`,
   `<repo>/.codex/hooks.json`, `<repo>/.codex/config.toml`, or bundled by a
   plugin — a different config shape and trust model than Claude's
   `settings.json` matcher hooks, even though several event names overlap
   conceptually.
4. Adapter required: yes, if ever pursued — and per issue #30/product-boundary,
   any new executable automation needs the security/privacy contract
   satisfied first regardless of provider.
5. Tested: no.
   Source: [learn.chatgpt.com/docs/hooks](https://learn.chatgpt.com/docs/hooks)
   (redirected from `developers.openai.com/codex/hooks`), verified 2026-07-11.

**Plugins**

1. Native primitive: yes — marketplace-distributed bundles of skills, MCP
   servers/apps, hooks, and scheduled-task templates, installed via
   `/plugins` in the CLI (also available in ChatGPT surfaces, not CLI-only).
2–4. No Bindle equivalent exists on either provider; not applicable.
5. Tested: no.
   Source: [learn.chatgpt.com/docs/plugins](https://learn.chatgpt.com/docs/plugins)
   (redirected from `developers.openai.com/codex/plugins`), verified
   2026-07-11.

**Instructions and precedence (`AGENTS.md`)**

1. Native primitive: yes (unchanged from prior model, now confirmed against
   current docs).
2. Confirmed discovery order: global scope reads
   `~/.codex/AGENTS.override.md` if present, else `~/.codex/AGENTS.md`;
   project scope walks from the Git root down to the current directory,
   checking `AGENTS.override.md`, then `AGENTS.md`, then any configured
   `project_doc_fallback_filenames`, at each level (at most one file per
   directory). Files concatenate root-to-leaf; closer files take precedence.
   Discovery stops once combined content reaches `project_doc_max_bytes`
   (32 KiB default); empty files are skipped. Instructions rebuild every
   Codex run/session start.
3. Bindle installs/supports today: yes (`global/AGENTS.md` →
   `<codex-home>/AGENTS.md`).
4. No adapter needed; this was already Bindle's model.
5. Tested: documented/inferred only — Bindle has not run an install/precedence
   integration test against a live Codex session.
   Note: the "`CLAUDE.md` as fallback context when only `CLAUDE.md` exists"
   behavior in this matrix and in
   [using-bindle-with-codex.md](using-bindle-with-codex.md) is Bindle's own
   authored guidance for a Codex-driven session to follow, not an
   OpenAI-documented Codex discovery rule — official docs describe no
   `CLAUDE.md` interaction at all.
   Source: [learn.chatgpt.com/docs/agent-configuration/agents-md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
   (redirected from `developers.openai.com/codex/guides/agents-md`), verified
   2026-07-11.

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
