# Issue tracking

Bindle uses GitHub Issues as its work-tracking surface. Issues say **what**
is being worked on and its status; branches and PRs say **how**; the
CHANGELOG says **what shipped**. This doc is the contract that keeps those
three honest, and it exists because bindle is tracked by a personal project
dashboard that reads issue labels directly.

## Why

Before v0.3.0, tracking lived only in branch names, PRs, and the CHANGELOG.
That worked, but state was invisible between sessions: nothing said what was
in progress, blocked, or next without reading git. Issues make that state
explicit and machine-readable.

## Label taxonomy (load-bearing — the dashboard parses these exactly)

Every open issue should carry one `type:` label and one `status:` label, and —
unless it is in `status: triage` — one `priority:` label. Label names include the
space after the colon.

| Facet    | Labels                                                                                                                       | Meaning                                            |
| -------- | ---------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| type     | `type: feat`, `type: bug`, `type: chore`, `type: docs`                                                                       | `feat` renders as a task; others as issues by kind |
| status   | `status: triage`, `status: brainstorming`, `status: ready`, `status: in-progress`, `status: blocked`, `status: probationary` | Workflow state; unlabeled = todo                   |
| priority | `priority: now`, `priority: normal`, `priority: someday`                                                                     | Urgency (high / normal / low)                      |
| —        | `question`                                                                                                                   | Marks an open question, not a work item            |

### Label lifecycle

Done is expressed by **closing** the issue, not by a label. Three rules follow
from that, stated here because leaving them implicit is what let 62 stale labels
accumulate before the sweep in `#227`, and two more after it (`#279`, `#309`).

1. **`status:` labels scope to open issues.** Closing an issue — directly, or by
   merging a PR whose body references it with a closing keyword — must remove its
   `status:` label. A closed issue still advertising `status: ready` is a false
   row on a dashboard that reads these labels live.
2. **There is no `status: done`.** Closure already carries that information, and
   a second way to say it is a second thing to keep in sync. The label was
   retired in `#287`.
3. **Every open issue outside `status: triage` carries a `priority:` label.**
   Triage is where an issue waits to be assessed, so it is the one state where
   having no priority is honest. Anywhere else, a missing priority makes the
   queue unsortable and is invisible until someone notices.

Rule 1's merge case is the one that actually fires: both `#279` and `#309` closed
through a `Resolves #N` keyword rather than `gh issue close`.

### How the rules are enforced

Two mechanisms, and neither subsumes the other:

- `global/hooks/label-hygiene-guard.py` — a `PreToolUse` hook that denies an
  offending close, merge, or edit as it is attempted. It sees only what an agent
  does through the harness: a web-UI merge, a close typed in a terminal, or any
  transition while the hook is unwired is invisible to it.
- `bin/check-issue-labels.sh` — the repo-wide audit that covers every path,
  including the ones the guard cannot see. **It runs automatically at the end of
  every session, as step 3 of `/session-end`**, and can be run by hand any time.
  It is read-only: it reports drift and never edits a label, and a finding does
  not block the session. In a repo that does not carry this document it reports
  `NOT APPLICABLE` and exits without checking anything — these rules are this
  repo's convention, not a universal one.

The audit is what catches rule 1's merge case after the fact: `#217`, `#364` and
`#366` each closed carrying a `status:` label through a web-UI merge, and the
guard fired on none of them.

## Conventions

- One issue per PR-able unit of work, matching the existing
  branch-and-PR discipline (`feature/<x>` branches, no direct commits to
  `main`).
- Before an issue moves to `status: ready` for delegation, it should carry a
  [delegated implementation packet](delegated-implementation-packets.md) —
  bounded objective, do-not-change scope, verification, and mutation authority.
- Milestones are release-scoped (`v0.3.0`, `v0.4.0`, …). Assign an issue to
  a milestone when it is committed to that release.
- Keep `status:` labels current when starting/blocking work — the dashboard
  reads them live; a stale label is a lie on the cockpit.
- The CHANGELOG remains the release record. Closing an issue does not
  replace its CHANGELOG entry.
