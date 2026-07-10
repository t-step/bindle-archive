---
description: Close out the session — write a durable session note (outside the repo) and surface candidate improvements
argument-hint: [optional note about how the session went]
allowed-tools: Bash(git status:*), Bash(git branch:*), Bash(git log:*), Bash(git diff:*), Bash(date:*), Bash(mkdir -p:*), Bash(gh issue view:*), Bash(gh issue list:*)
---

<!-- Conventions (notes home layout, slug rules, privacy):
     the session-continuity skill is the source of truth — read it first. -->

Close out this session by writing a session note to the notes home — **not**
into this repo. User's own closing note, if any: "$ARGUMENTS"

Current repo state:

- today: !`date +%F`
- branch: !`git branch --show-current`
- status: !`git status --short --branch`
- commits this branch (newest first): !`git log --oneline -15`

Steps:

1. Read the `session-continuity` skill; resolve the notes home
   (`$BINDLE_NOTES_DIR`, deprecated `$CLAUDE_KIT_NOTES_DIR`, or `~/.bindle`) and
   `projects/<project>/sessions/`; `mkdir -p` as needed.
2. Reconstruct the session honestly from the conversation and git state — what
   was actually done, not what was intended. If tests weren't run, the note
   says "not run", not "passing".
3. Label reconciliation (skip silently if there's no GitHub remote, `gh` is
   unavailable or unauthenticated, or this session touched no issues):
   - Identify issues this session touched — numbers referenced in the branch
     name, commit subjects/bodies (`#123`), or named explicitly in
     conversation.
   - For each, `gh issue view <N> --json state,labels` to see its current
     `status:` label (exact text, space after the colon — see
     `docs/issue-tracking.md` for the taxonomy) and open/closed state.
   - Compare to what the session actually did. If the work is finished,
     propose `gh issue close <N> --comment "<one-line summary>"`. If the
     `status:` label no longer matches reality, propose
     `gh issue edit <N> --remove-label "status: X" --add-label "status: Y"`
     with the exact before/after label text. Skip an issue with no proposed
     change.
   - Present every proposed command as one batch and wait for explicit user
     approval before running any of them — never run a mutating `gh` command
     unapproved.
   - Record what ran (or that nothing needed to change) — it feeds the
     session note's **decisions** section below.
4. Write `sessions/YYYY-MM-DD-<slug>.md` containing:
   - **goal** — what this session set out to do;
   - **branch** and **commits made** (hashes + subjects);
   - **files changed** (paths only);
   - **tests/checks run** and their actual results;
   - **validation status** — green / red / not verified;
   - **decisions** — one line each, with the why (including any label
     reconciliation from step 3);
   - **risks** — what could bite a future session;
   - **deferred** — consciously not done;
   - **candidate workflow improvements** — answer each briefly:
     new reusable skill? existing skill to update? project profile update?
     validation/check to add? privacy rule to add? nothing worth keeping?
   - **next** — the single most useful next prompt.
5. Privacy pass: this note stays in the notes home, so local paths are fine —
   but confirm nothing session-private (transcripts, personal details) was
   left in *repo* files or staged changes. Flag anything you find; don't
   silently fix it.
   - If the user's closing note asks for the summary **in the repo or PR**
     (e.g. "save it as NOTES.md" / "so my teammate sees it"), do not write the
     note above into the repo. Follow the skill's **Repo-bound content** recipe:
     keep the full note in the notes home (step 4), then produce a *separate*
     sanitized summary and run `bin/check-private-info.sh` on it — block on the
     result — before leaving it (unstaged) in the repo.
6. If the session produced real profile-worthy facts (a new gate, a new safety
   rule), suggest updating the profile — one line, user's call.

Reply with the note's full path and the note itself. If the user wants a
paste-ready prompt for the next session, that's `/handoff` — offer it, don't
run it.
