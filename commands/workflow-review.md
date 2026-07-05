---
description: Review recent session notes/profiles/handoffs for recurring friction and promotable patterns
argument-hint: [project, or "all"]
allowed-tools: Bash(ls:*), Bash(date:*)
---

<!-- The loop and routing table: claude-kit's docs/iterative-improvement.md.
     Notes-home conventions: the session-continuity skill. -->

Review accumulated session experience and surface what should change in the
toolkit, the projects, or the notes themselves. Scope, if given: "$ARGUMENTS"
(a project slug, or "all"; default: the current repo's project).

**Read-only.** This command produces findings and recommendations — it never
edits skills, commands, project repos, or notes. Promotion happens later,
one insight at a time, via `/promote-insight`.

Steps:

1. Read the `session-continuity` skill; resolve the notes home. For the scoped
   project(s), read `profile.md` and the recent `sessions/` and `handoffs/`
   files (aim for the last ~5–10 sessions per project; say how many you read).
2. Look across them — patterns need repetition, so weigh anything that
   appears twice or more:
   - repeated manual steps that could be a command or script;
   - repeated validation commands that should be a documented gate;
   - recurring failure modes (same bug class, same broken assumption);
   - prompts/approaches that worked well — and ones that produced bad results;
   - project-specific rules living in notes that belong in that project's
     CLAUDE.md or `.claude/` (recommendation only — never edit that repo);
   - reusable procedures stable enough to become shared skills;
   - personal preferences that belong in personal global config, not skills;
   - private notes that must NOT be promoted anywhere;
   - stale or misleading instructions (in profiles, skills, or docs);
   - candidates for deletion or simplification — shrinkage counts.
   Also collect the "candidate workflow improvements" sections the session
   notes already wrote — they are pre-vetted signals.
3. Report findings as a ranked list, each with: the evidence (which
   notes/sessions, how many times), the proposed classification per
   claude-kit's `docs/iterative-improvement.md` routing table, and the
   concrete next action.
4. End with: "To act on one: `/promote-insight <finding>`" — and remind that
   anything leaving the notes home gets sanitized and user-confirmed first.

If there are no notes yet (or too few to see repetition), say so and stop —
don't invent findings.
