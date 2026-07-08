---
description: Classify one insight and route it to its home (skill, project rule, profile, gate, privacy rule) with explicit confirmation
argument-hint: <the insight, or a finding from /workflow-review>
---

<!-- The routing table and hard rules: Bindle's docs/iterative-improvement.md. -->

Take one insight and land it in the right place — or consciously drop it.
The insight: "$ARGUMENTS" (if empty, ask for it; one insight per run).

Steps:

1. Classify it as exactly one of (per Bindle's
   `docs/iterative-improvement.md`):
   - **personal preference** → the appropriate provider global file
     (`global/CLAUDE.md` for Claude, `global/AGENTS.md` for Codex);
   - **reusable Claude skill / command** → the kit's `skills/` or `commands/`;
   - **project-specific rule** → that project's `CLAUDE.md`, `AGENTS.md`, or
     `.claude/`;
   - **project profile update** → `profile.md` in the notes home;
   - **decision log entry** → stays in session notes (maybe better worded);
   - **validation gate / check** → project CI/hooks, or the kit's checks;
   - **privacy rule** → a `bin/check-private-info.sh` pattern or a denylist
     term;
   - **not worth keeping** → say why, and stop.
   State the classification and your reasoning in 2–3 lines. If it's genuinely
   two things (a skill AND a profile line), say so and handle them as two
   promotions.
2. Draft the exact text that would land: the skill/command body, provider
   guidance lines, the profile edit, the check pattern. If the source is a
   private session note, sanitize while drafting (Bindle's
   `docs/privacy-boundaries.md`): no personal paths/names/denylist terms, no
   transcript fragments.
3. **Show the draft and ask for confirmation before writing anything.** This
   holds even in an otherwise-autonomous session: promotion from private notes
   to shared/committed files is the one boundary that always gets a human
   yes. Never batch-promote.
4. On yes, apply it to its home, with the destination's own rules:
   - kit changes follow the kit's CONTRIBUTING (branch, `make check`, a new
     skill enters as a **draft** pending its pressure-test loop, CHANGELOG
     entry);
   - project-repo changes only if the user confirms *in that context* — you
     propose the diff, they own applying it unless they tell you to;
   - notes-home changes (profile, denylist) can be written directly;
   - run `bin/check-private-info.sh` on anything that will be committed.
5. Close the loop: one line on where it landed, and — if it replaced or
   obsoleted something (an old note, a stale instruction) — flag that for
   deletion too.
