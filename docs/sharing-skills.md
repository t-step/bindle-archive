# Sharing workflows with collaborators

How reusable parts of a personal kit reach other people — and what stays
personal. The short version: **share through Git at the right level; never copy
provider config directories around.**

## The anti-pattern

Copying a whole `~/.claude/`, explicit Codex target, or this repo wholesale ships your
personal preferences, your private notes pointers, and your global instructions
into their environment, with no update path and no provenance. Don't. The same
applies in reverse: don't import someone's directory dump into yours.

## What goes where

| Kind of thing | Lives in | Reaches others via |
|---|---|---|
| Stable, project-agnostic Claude procedure | a skill/command/agent in a Git repo | clone + install, or a plugin |
| Stable provider-agnostic instruction | docs or provider guidance in a Git repo | project instructions, review, or explicit install |
| Project-specific Claude behavior | that project's `CLAUDE.md` / `.claude/skills/` / `.claude/commands/` | the project repo itself |
| Project-specific Codex behavior | that project's `AGENTS.md` | the project repo itself |
| Personal preferences (tone, git habits, editor) | your provider global files | never — personal by definition |
| Evolving insights, session notes, half-formed ideas | Markdown notes under `~/.bindle/` (or your notes dir) | promoted to one of the above once stable — see [iterative-improvement.md](iterative-improvement.md) |
| Secrets, tokens, private context | nowhere in Git | never |

Two rules of thumb:

- **Stable procedures become skills; evolving insights stay notes.** A note
  that keeps proving itself across sessions graduates into a skill or a
  project rule. Promotion is explicit, not automatic.
- **If it only makes sense in one project, it belongs in that project's repo**,
  where every collaborator (and every agent) gets it automatically with
  project-level precedence.

## Repo shapes

A **shared workflow kit** — a team- or community-owned repo of reusable assets:

```
shared-workflow-kit/
  skills/<name>/SKILL.md
  commands/<name>.md
  agents/<name>.md
  docs/
```

A **personal kit** (like this repo) — your selection of assets plus personal
global config:

```
personal-bindle/
  skills/  commands/  agents/     # yours + selected shared assets
  global/CLAUDE.md                # Claude personal; not for sharing
  global/AGENTS.md                # Codex personal; not for sharing
  bin/install.sh
```

A **project repo** — project-scoped Claude behavior, versioned with the code:

```
project-repo/
  CLAUDE.md
  AGENTS.md
  .claude/
    skills/
    commands/
```

## Consuming a shared kit

Prefer consuming shared assets *at their own level* rather than copying files
into your kit:

1. **As a plugin / marketplace** — if the shared repo is installable via
   `claude plugin …`, install it and reference its skills by name from yours
   (`**REQUIRED BACKGROUND:** their-kit:some-skill`). It updates itself; you
   vendor nothing.
2. **As a sibling clone** — clone it and run its installer (or symlink its
   items) so its links point into *its* checkout. Your installer and theirs
   coexist: each only owns links into its own repo, and name collisions surface
   as `CONFLICT` instead of silent clobbering (see
   [ownership-boundaries.md](ownership-boundaries.md)).
3. **Cherry-pick with provenance** — if you must copy an asset in (to modify
   it), note its origin in the file and treat it as a fork you now maintain.
   This is the last resort, not the default.

For Codex, a skill can be shared only if it is Codex-eligible — marked
`provider.codex: "installed"` in `capabilities.json`, which installs
`skills/<name>/SKILL.md` to an explicit `--agents-skills-home` target. Anything
not marked eligible has no Codex install format: share it as direct `AGENTS.md`
guidance or docs instead. Bindle defines no Codex command or agent format at
all.

## Publishing from your personal kit

When one of your skills is worth sharing: move (or copy) it to the shared repo
via a normal PR there, strip anything personal (names, paths, project
references, your preferences), and have your kit consume it back via one of the
methods above. Sanitization is on you before it leaves your machine — see
[privacy-boundaries.md](privacy-boundaries.md) and run
`bin/check-private-info.sh` on anything about to be committed.
