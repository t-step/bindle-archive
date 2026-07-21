# Bindle

Bindle is my personal, portable agentic-workflow kit. It started as
`claude-kit`, a Claude Code toolkit, and now keeps that Claude workflow intact
while adding a small interoperability foundation for Codex.

Bindle is not a fake universal abstraction. Claude Code and Codex have
different installed surfaces, so Bindle documents what maps cleanly and keeps
provider-specific assets provider-specific.

## Provider support

Claude Code support is the mature path today:

<!-- GENERATED:readme-claude:BEGIN -->
```
skills/<name>/SKILL.md   ->  ~/.claude/skills/<name>      Claude skills
agents/<name>.md         ->  ~/.claude/agents/<name>.md   Claude subagents
commands/<name>.md       ->  ~/.claude/commands/<name>.md Claude slash commands
global/CLAUDE.md         ->  ~/.claude/CLAUDE.md          Claude global instructions
CLAUDE.md                    (not installed)              Bindle project guidance for Claude
```
<!-- GENERATED:readme-claude:END -->

Codex support is intentionally narrower:

<!-- GENERATED:readme-codex:BEGIN -->
```
skills/<name>/     ->  <explicit-agents-skills-home>/<name> Codex skills (eligible only, see capabilities.json)
global/AGENTS.md   ->  <explicit-codex-home>/AGENTS.md
AGENTS.md              (not installed)                      Bindle project guidance for Codex
```
<!-- GENERATED:readme-codex:END -->

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

Every install also links the public `bindle` executable, defaulting to
`~/.local/bin/bindle`. Override that with `--bin-dir DIR`:

```bash
bin/install.sh --bin-dir ~/bin
```

Install Codex assets into explicit target directories — one for `AGENTS.md`,
one for Codex-eligible skills:

```bash
bin/install.sh --provider codex --codex-home ~/.codex --agents-skills-home ~/.agents/skills
bin/install.sh --provider all --codex-home ~/.codex --agents-skills-home ~/.agents/skills
```

`--codex-home` is always required for a Codex install. `--agents-skills-home`
is required whenever any skill is Codex-eligible (`provider.codex:
"installed"` in `capabilities.json`) — which is the case today, so omitting it
exits 2 without writing anything. Diagnose the same pair with
`bindle doctor --codex-home ~/.codex --agents-skills-home ~/.agents/skills`.

For tests or alternate Claude targets, `--home DIR` still means the Claude home:

```bash
bin/install.sh --home /tmp/claude-home
```

Re-run anytime. The installer is idempotent and conflict-safe. If the executable
directory is not on `PATH`, install and doctor output include a shell-specific
remediation.

## Troubleshooting

`bindle doctor` (or `bin/doctor.sh` / `make doctor`) is the read-only diagnostic: it reports the
state of every managed destination (current / missing / stale / broken /
conflicting / possibly an earlier checkout), the notes-home resolution, and
local tool availability, with a suggested next action for every finding. It
never writes anything — repairs stay explicit (`bin/install.sh`,
`bin/install.sh --prune`, `bin/install.sh --adopt` after a repo move, or the
recovery options in
[docs/ownership-boundaries.md](docs/ownership-boundaries.md)).

## Ownership boundaries

Bindle is a good citizen: it only creates, updates, or removes symlinks that
point back into this repo. Anything else in an installed surface is foreign and
left untouched.

- **No clobbering:** a real file or foreign symlink at a destination is reported
  as `CONFLICT`.
- **Nonzero on conflict:** by default, any conflict makes the installer exit
  `1` — installation was incomplete even though nothing was overwritten. Pass
  `--allow-conflicts` for interactive use when you just want the warnings.
  See the exit codes in `bin/install.sh`'s usage header.
- **Safe prune:** `--prune` removes only broken symlinks pointing into this repo.
- **Explicit adoption:** after the repo is moved or renamed, `--adopt` relinks
  broken links left by an earlier checkout — preview and confirmation first,
  broken exact-match links only, never automatic.
- **Provider-specific install:** Claude surfaces go under the Claude home;
  Codex installs `global/AGENTS.md` to the explicit `--codex-home` target and
  Codex-eligible skills to the explicit `--agents-skills-home` target.

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
- `/notes-home` — show where the notes live, or durably relocate them (e.g.
  into an Obsidian vault) via `bin/notes-home.sh`: preview first, explicit
  confirmation before the one surgical `~/.claude/settings.json` write.

Notes prefer `BINDLE_NOTES_DIR`, then the deprecated `CLAUDE_KIT_NOTES_DIR`, then
`~/.bindle`. Existing `~/.claude-kit` data is not moved automatically; keep using
the alias, or copy with `/notes-home migrate` (never deletes the old home). See
[docs/notes-home.md](docs/notes-home.md). The provider-neutral contract behind
these commands — usable from Codex too — is
[docs/session-notes-format.md](docs/session-notes-format.md).

Opt-in (never part of `bin/install.sh`): `bin/install-claude-hooks.sh install`
wires a `SessionStart` hook that opens every session pre-oriented (via
[`bin/session-context.sh`](bin/session-context.sh)) and a `SessionEnd` hook
that leaves an automatic breadcrumb even if `/session-end` is never run.
Preview first, `--apply` to write; `uninstall` reverses it. See
[docs/session-notes-format.md](docs/session-notes-format.md#opt-in-hook-automation-breadcrumbs).

The same command wires the `PreToolUse` guards, one at a time and only when
named — `install --guard nested-notes|label-hygiene|codegraph|git-push-merged`. A bare
`install` never wires a guard, so installing Bindle cannot silently start
intercepting your tool calls; `bin/doctor.sh` reports which shipped hooks are
installed but unwired, so opt-in does not mean invisible. (Not to be confused
with `bin/install-hooks.sh`, which enables this repo's *git* hooks.)

### Hook wiring convention

`bin/install.sh` symlinks every `global/hooks/*.py` into `~/.claude/hooks/`.
A `settings.json` hook entry must name **that** path, expanded, and must not
swallow the exit code:

```jsonc
{ "type": "command",
  "command": "python3 /Users/<you>/.claude/hooks/nested-notes-guard.py",
  "timeout": 10 }
```

Two rules, both learned the hard way (#264, #312):

- **Never point an entry into the checkout.** It resolves today and silently
  stops running the moment the repo moves or is renamed. Via the symlink, a
  move leaves a dangling link that reports itself.
- **Never wrap the command in `test -f … || true`.** For `PreToolUse` only exit
  code 2 blocks a tool call, so a missing or broken hook already fails visibly
  without wedging the session — suppressing that only hides the breakage.

`bin/doctor.sh` checks both: a wired path that does not resolve, and one that
resolves *but bypasses* `~/.claude/hooks`, are each reported as findings rather
than shown green. Guards other than the two session hooks are hand-wired —
`settings.json` is yours, so Bindle diagnoses it and never writes it unasked
(see [docs/ownership-boundaries.md](docs/ownership-boundaries.md)).

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
bin/test-check.sh
```

`make check` wraps `bin/check.sh`. It still validates Claude-specific
conventions for `skills/*/SKILL.md`, `agents/*.md`, and `commands/*.md`.
Codex files are direct instruction files and are not required to pass Claude
skill, agent, or slash-command frontmatter checks. `check.sh` discovers what
to lint/self-test from repo structure (`git ls-files '*.sh'`, and any tracked
`skills/*/scripts/selftest.py`) rather than a hardcoded list — see
`SH_EXCLUDE` in `bin/check.sh` for the (deliberately narrow) exclusion point.

`make test` runs installer tests for Claude install, explicit Codex install,
`--provider all`, conflict safety, and prune safety, plus `check.sh`'s own
script/self-test discovery tests.

## Developing Bindle

Read [CONTRIBUTING.md](CONTRIBUTING.md) before adding or changing assets. This
repo uses branch-and-PR discipline, small reviewable changes, and verification
before completion. Do not push unless explicitly asked.

What Bindle is for, what it owns, and which tempting directions are
deliberately out of scope for the next releases is decided in
[docs/product-boundary.md](docs/product-boundary.md) — check proposed work
against it before starting.

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
lives in `VERSION`. Releases are cut through Release Please (which owns the
changelog and the version bump on the release PR); `bin/release.sh` remains a
legacy/fallback local cutter that tags without pushing.
