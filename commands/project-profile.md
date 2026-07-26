---
description: Create or update the portable project profile in the notes home (explicit export only)
argument-hint: [update focus, or "export"]
allowed-tools: Bash(git status:*), Bash(git branch:*), Bash(git remote:*), Bash(date:*), Bash(mkdir -p:*)
---

<!-- Conventions (notes home layout, slug rules, privacy):
     the session-continuity skill is the source of truth — read it first. -->

Create or update this project's profile — the durable, portable facts a fresh
session needs. It lives in the notes home, **outside this repo**. Argument, if
any: "$ARGUMENTS"

Steps:

1. Read the `session-continuity` skill; resolve the notes home and
   `projects/<project>/profile.md`. If a profile exists, update it in place
   (preserve wording that's still true); otherwise create it.
2. Gather facts from the repo (read-only): remotes, default branch, stack,
   test/build/lint entry points, CI config, pre-commit hooks, CONTRIBUTING,
   `CLAUDE.md`, or `AGENTS.md` rules. Ask the user only for what the repo can't tell you
   (safety notes, recurring instructions).
3. Write/refresh these sections. Each section is **either** an inline runbook
   block **or** a pointer list of `[[fact]]` + one-line hook (see the
   session-continuity skill's "Fact files"). Keep gates and common commands
   inline; shed long-form safety-note and recurring-instruction prose to
   `facts/` and point at it.
   - **project** — name, repo path, one-line purpose, project type/stack;
   - **common commands** — run/build/test/lint, copy-pasteable;
   - **validation gates** — what must pass before a commit/PR, in order;
   - **important docs** — the 2–5 files worth reading first;
   - **safety notes** — branch discipline, protected areas, "never do X here";
   - **recurring instructions** — things you find yourself retyping every
     session;
   - **context locations** — where sessions/handoffs for this project live,
     plus any external context (issue tracker, design docs) by name.
   - No secrets, no tokens, no personal-life details — profiles travel.
4. Keep the inline runbook under ~60 lines. On-demand reference goes to
   `facts/` as `[[fact]]` pointers, not inline prose — profile.md shrinks as
   facts atomize. Facts the project's own README/provider guidance already
   states get a pointer, not a copy.

**Export (only when the user explicitly says "export"):** write a sanitized
copy into the repo as `docs/project-profile.md` with a header noting it is a
sanitized, shareable snapshot (generated from a private profile; personal
paths/notes removed). Sanitize per Bindle's `docs/privacy-boundaries.md` — repo-relative
paths, no personal names/denylist terms — and tell the user to review the diff
before committing. Never export as a side effect of anything else.

Reply with the profile path and its content.
