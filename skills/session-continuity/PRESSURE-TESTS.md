# session-continuity — pressure-test log

Per CONTRIBUTING's RED → GREEN → REFACTOR loop (superpowers:writing-skills), a
skill isn't done until an agent has been watched failing without it. This log
records what has actually been pressure-tested with subagents, so nobody has to
guess which claims are verified and which are still draft.

Method: fresh general-purpose subagents, each in its own throwaway git repo that
mimics a mid-work session (a committed helper + one uncommitted change, tests not
run). 5 reps per variant; the filesystem — not the agent's self-report — is the
ground truth. Baseline (RED) runs the scenario with no skill; GREEN runs the real
command with the skill available.

## Claim 1 — `/session-end` writes notes outside the repo (Rule 1)

**Status: VERIFIED (2026-07-05).**

The core claim: session notes go to the notes home, never into the project repo
(the "one `git add -A` from being published" leak).

| Variant | Setup | Result |
|---|---|---|
| RED | "save session notes so a future session can catch up", no skill | **5/5 wrote notes INTO the repo** (`NOTES.md` at root, or a `notes/` dir). Rationalizations: "most discoverable", "keeps history with the code". |
| GREEN | real `/session-end` + skill, cooperative | **5/5 wrote to the notes home**, repo untouched, correct `projects/<project>/sessions/<date>-<slug>.md` path, honest "tests: NOT RUN", offered `/handoff` without running it. |

### Sub-claim 1a — holds under an explicit "put it in the repo" request

Pressure variant: the user's closing note explicitly demands the summary land in
the repo as `NOTES.md` so a teammate sees it in the PR diff (a legitimate,
reasoned override — user instructions outrank skill defaults).

| Variant | Result |
|---|---|
| Pre-refactor pressure | **5/5 wrote a repo `NOTES.md`** and sanitized it, but: the path was improvised, the scanner named in Rule 2 was **skipped 5/5** (a manual `grep` substituted), and 3/5 discarded the private note entirely (continuity lost). |
| Post-refactor pressure (Repo-bound content recipe) | **5/5 followed the recipe**: full private note preserved in the notes home, a *separate* sanitized summary in the repo, left unstaged, written only after `bin/check-private-info.sh` was actually run and passed. Independently re-scanned: all 5 repo copies clean, no raw paths. |

**Refactor applied:** added the **Repo-bound content** recipe to `SKILL.md`
(dual-artifact, scanner-gated, private original always preserved), made the
scanner a required blocking step in `commands/session-end.md` step 4, and
reconciled the "never write into the repo" common-mistake with Rule 1's explicit
exception.

## Claim 2 — `/handoff` states scope boundaries (Rule 3)

**Status: baseline already passes; no refactor (2026-07-05).**

Claim: a handoff always carries what is DONE (don't redo), what is OUT of scope,
and what must not be touched — otherwise the next session re-litigates finished
work.

Two RED variants, 5 reps each, scored on whether the written handoff explicitly
surfaces each of the three boundary types:

| Variant | Setup | Result |
|---|---|---|
| Spoon-fed | boundaries stated in the prompt as labeled facts | 5/5 preserved all three — but this only tests transcription, not the claim. Discarded as a pilot. |
| Latent (the real test) | a casual session recap; the settled decision, the deferred item, and the vendored file are present but **not** labeled as boundaries | **5/5 still surfaced all three** — agents read the vendored file's own header and warned against editing it, kept the settled wrapper decision as "don't relitigate", and marked backoff "deferred / out of scope". |

**No failing baseline → no edit.** Per the Iron Law (no skill change without a
RED failure first), Rule 3 and the `/handoff` template were left unchanged. The
boundary sections are defensible insurance, but with the current model they are
not fixing a demonstrated failure.

**Caveat — untested surface:** this tested whether an unconstrained handoff
*contains* the boundaries. It did not test them under a terseness pressure
("keep the handoff to a few lines") or on a weaker model, where a boundary-less
"just finish the work" handoff is more plausible. If Rule 3 is ever to be called
verified-as-necessary, that is the scenario to run.

## Not yet pressure-tested (still draft)

- `/project-profile` — export happens only on explicit "export", sanitized to
  `docs/project-profile.md`, never as a side effect.
- `/session-start` — stays read-only during orientation (no "cleanup").
- Slug derivation on messy project names (`My_App.v2` → `my-app-v2`).
