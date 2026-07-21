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
   says "not run", not "passing". Settle today's date and this session's slug
   now (`<bindle>/bin/slugify.sh` — your Bindle checkout, not this repo;
   session-continuity's slug rule) — steps 4 and 5 both reuse it.
3. Label reconciliation (skip silently if there's no GitHub remote, `gh` is
   unavailable or unauthenticated, or this session touched no issues):
   - **Run the repo-wide audit first**: `<bindle>/bin/check-issue-labels.sh`
     (your Bindle checkout's copy; it audits the current working repo). It is
     read-only — it never edits a label, and a finding never blocks session-end.
     Report its verdict by exit code, and do not round any of them up to green:
     - **0** — say label hygiene is clean.
     - **1** — list every violation it printed. These are drift the session may
       never have touched, which is the point: the `PreToolUse` guard sees only
       agent-initiated transitions, so a web-UI merge closes an issue with its
       `status:` label intact and nothing catches it until this sweep. Fold them
       into the approval batch below.
     - **2** — SKIPPED. Report that nothing was verified. Never report this as
       clean; that is the failure mode `#279` cost this repo once already.
     - **3** — NOT APPLICABLE (the repo carries no `docs/issue-tracking.md`, so
       this taxonomy is not its convention). Skip the rest of this step silently.
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
4. Profile proposals — resolve before writing the note, so its outcome lands
   in the note itself. Per session-continuity's **Profile proposals queue**:
   - Read `profile-proposals.md` in `projects/<project>/` (same notes home as
     step 1) if it exists; these are pending entries carried over from
     earlier sessions (previously deferred).
   - From this session's actual work, apply the usual bar (a durable
     validation gate, safety note, recurring instruction — not something
     already in the project's own README/CLAUDE.md) to spot any new
     profile-worthy facts. Tag each with the date/slug from step 2 and the
     `profile.md` section it targets (project, common commands, validation
     gates, important docs, safety notes, recurring instructions, context
     locations). Before adding a new fact to the in-memory list, check it
     against the carried-over pending entries from this same step — if an
     existing entry already covers the same fact (even worded differently),
     don't queue a duplicate. Nothing is written to disk yet.
   - Nothing pending (no carryover, nothing new)? Record "profile: nothing
     pending" and move on to step 5.
   - **Interactive turn** (a live user will see this reply and can respond
     now): present the full combined list via the `AskUserQuestion` tool, one
     question per item, options exactly `Add` / `Defer` / `Reject` (batch at
     most 4 questions per call; issue further calls for any remaining
     items). If any answer comes back ambiguous or unresolved, don't guess —
     re-ask only those items before applying anything. Apply the answers:
     - **Add** → append the exact line to the named section of `profile.md`
       (create it first via `/project-profile`'s conventions if it doesn't
       exist yet); drop the item from the pending list.
     - **Defer** → leave the item in the pending list, untouched.
     - **Reject** → drop the item from the pending list permanently.
     Rewrite `profile-proposals.md` with whatever remains pending, or delete
     it if the queue is now empty. Record the per-item outcome for step 5.
   - **Unattended/scheduled run** (no one available to respond right now):
     skip the ask entirely. Append this session's new proposals to
     `profile-proposals.md` as pending (leave existing carried-over entries
     untouched) and record "profile: N new proposal(s) queued, unattended —
     no ask" for step 5. Never block waiting on an answer, and never write to
     `profile.md` on an unattended run.
5. Write `sessions/YYYY-MM-DD-<slug>.md` (the date/slug settled in step 2)
   containing:
   - **goal** — what this session set out to do;
   - **branch** and **commits made** (hashes + subjects);
   - **files changed** (paths only);
   - **tests/checks run** and their actual results;
   - **validation status** — green / red / not verified;
   - **decisions** — one line each, with the why (including any label
     reconciliation from step 3 and the profile-proposal outcome from
     step 4);
   - **risks** — what could bite a future session;
   - **deferred** — consciously not done;
   - **candidate workflow improvements** — answer each briefly: new reusable
     skill? existing skill to update? validation/check to add? privacy rule
     to add? nothing worth keeping? (profile updates are already resolved by
     step 4 — record the outcome, not a fresh suggestion.)
   - **next** — the single most useful next prompt.
6. Privacy pass: this note stays in the notes home, so local paths are fine —
   but confirm nothing session-private (transcripts, personal details) was
   left in *repo* files or staged changes. Flag anything you find; don't
   silently fix it.
   - If the user's closing note asks for the summary **in the repo or PR**
     (e.g. "save it as NOTES.md" / "so my teammate sees it"), do not write the
     note above into the repo. Follow the skill's **Repo-bound content**
     recipe: keep the full note in the notes home (step 5), then produce a
     *separate* sanitized summary and run `<bindle>/bin/check-private-info.sh` on it —
     block on the result — before leaving it (unstaged) in the repo.
7. Land the repo on clean `main` — do this **last**, after the note is written
   and the privacy pass, so the note captured the branch context before HEAD
   moves. Run `<bindle>/bin/session-end-land.sh` (your Bindle checkout's copy;
   it operates on the current working repo). It is attempt-if-safe: it switches
   to `main` and fast-forwards it to `origin/main` only when lossless, and
   otherwise mutates nothing. Render its verdict into your reply and fold the
   outcome into the note's **decisions**:
   - **SAFE** → it landed; report the final state and pass along any
     `git branch -d <branch>` suggestions it printed for merged local branches
     — relay them, never run them yourself.
   - **BLOCKED: <reason>** → nothing changed; relay the blocker (dirty tree,
     unmerged branch, diverged `main`, or detached HEAD) and the remediation it
     proposed, so the operator can resolve it. Do not try to force the landing.
   - **ERROR** → environment or landing problem (not a git repo, no `origin`,
     or `main` is checked out elsewhere / couldn't fast-forward); report the
     printed reason so the operator can clear it.

Reply with the note's full path and the note itself. If the user wants a
paste-ready prompt for the next session, that's `/handoff` — offer it, don't
run it.
