---
description: Close out the session — write a durable session note (outside the repo) and surface candidate improvements
argument-hint: [optional note about how the session went]
allowed-tools: Bash(git status:*), Bash(git branch:*), Bash(git log:*), Bash(git diff:*), Bash(date:*), Bash(mkdir -p:*)
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
3. Write `sessions/YYYY-MM-DD-<slug>.md` containing:
   - **goal** — what this session set out to do;
   - **branch** and **commits made** (hashes + subjects);
   - **files changed** (paths only);
   - **tests/checks run** and their actual results;
   - **validation status** — green / red / not verified;
   - **decisions** — one line each, with the why;
   - **risks** — what could bite a future session;
   - **deferred** — consciously not done;
   - **candidate workflow improvements** — answer each briefly:
     new reusable skill? existing skill to update? project profile update?
     validation/check to add? privacy rule to add? nothing worth keeping?
   - **next** — the single most useful next prompt.
4. Privacy pass: this note stays in the notes home, so local paths are fine —
   but confirm nothing session-private (transcripts, personal details) was
   left in *repo* files or staged changes. Flag anything you find; don't
   silently fix it.
   - If the user's closing note asks for the summary **in the repo or PR**
     (e.g. "save it as NOTES.md" / "so my teammate sees it"), do not write the
     note above into the repo. Follow the skill's **Repo-bound content** recipe:
     keep the full note in the notes home (step 3), then produce a *separate*
     sanitized summary and run `bin/check-private-info.sh` on it — block on the
     result — before leaving it (unstaged) in the repo.
5. If the session produced real profile-worthy facts (a new gate, a new safety
   rule), suggest updating the profile — one line, user's call.

Reply with the note's full path and the note itself. If the user wants a
paste-ready prompt for the next session, that's `/handoff` — offer it, don't
run it.
