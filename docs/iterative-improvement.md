# The iterative improvement loop

How repeated session experience becomes better skills, commands, docs,
profiles, privacy rules, and validation gates — **explicitly, never
automatically**. Markdown-first: the raw material is the notes home, the
output is a reviewed change to the right layer.

## The loop

1. `/session-start` — begin warm: repo state + profile + last note/handoff.
2. Do the work.
3. `/session-end` — write the session note; it ends with a **candidate
   workflow improvements** section (new skill? skill update? profile update?
   check to add? privacy rule? nothing?).
4. `/handoff` — when the work continues later or elsewhere.
5. Periodically, `/workflow-review` — read across recent notes and surface
   recurring friction and proven patterns.
6. `/promote-insight` — classify one insight and route it to its home, with
   your explicit confirmation before anything is written.
7. Keep private/session-specific detail out of every shared asset.

Cadence: `/workflow-review` is worth running after every ~5–10 sessions on a
project, or monthly across projects — often enough that patterns are fresh,
rare enough that real repetition (not one-offs) is what surfaces.

## Where an insight belongs

The whole game is routing each insight to the *narrowest layer that fully
serves it* (see [sharing-skills.md](sharing-skills.md) for the sharing side):

| Classification | Home | Example |
|---|---|---|
| personal preference | your provider global files | "lead with the answer" |
| reusable skill / command | this repo (`skills/`, `commands/`) | a debugging procedure that worked 3 times |
| project-specific rule | that project's `CLAUDE.md`, `AGENTS.md`, or `.claude/` | "never regenerate the fixtures by hand" |
| project profile update | notes home `profile.md` | a new validation gate |
| decision log entry | the project's session notes / docs | "we chose X over Y because…" |
| validation gate / check | project CI, or this repo's `bin/check*.sh` | a failure mode a script can catch |
| privacy rule | `bin/check-private-info.sh` patterns or your denylist | a term that almost leaked |
| not worth keeping | nowhere | one-off friction that won't recur |

Two distinctions the loop must preserve:

- **Stable procedures vs. evolving knowledge.** A procedure that has held up
  across sessions becomes a skill (and goes through the CONTRIBUTING
  pressure-test loop). Knowledge still moving stays in notes, where being
  wrong is cheap.
- **Personal vs. shared vs. private.** Preferences stay in personal config;
  project rules go where the project's collaborators get them; session
  narrative stays in the notes home forever.

## Hard rules

- **No automatic promotion.** Nothing moves from the (private) notes home into
  a committed file without the user explicitly confirming that specific
  promotion, having seen the sanitized text that would land.
- **No editing project repos as a side effect.** A "this belongs in the
  project's provider guidance" verdict produces a *recommendation* (or a diff to
  review), applied only when the user says so in that repo.
- **Sanitize at the boundary.** Anything crossing notes-home → repo gets the
  [privacy-boundaries.md](privacy-boundaries.md) treatment and a
  `bin/check-private-info.sh` pass.
- **Skills earn their status.** A promoted procedure enters as a *draft* until
  it passes the RED→GREEN→REFACTOR loop in
  [CONTRIBUTING.md](../CONTRIBUTING.md).
- **Deletion is promotion too.** Stale instructions, superseded profile lines,
  and skills that never fire are findings — simplify.

The "no automatic promotion" rule is pressure-tested — see
[iterative-improvement-pressure-tests.md](iterative-improvement-pressure-tests.md):
an autonomous, unattended `/promote-insight` pass wrote nothing to shared/committed
files 5/5, where a skill-less baseline batch-committed 5/5.

## Why this stays lightweight

The loop is three Markdown prompts and a folder of notes. No metrics
pipeline, no telemetry, no database (see
[sqlite-workflow-index.md](sqlite-workflow-index.md) for the deferred index).
If the loop itself starts feeling like work, that's a finding: simplify it.
