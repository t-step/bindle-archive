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

Every open issue should carry one `type:` label and one `status:` label.
Label names include the space after the colon.

| Facet    | Labels                                                                                                                       | Meaning                                            |
| -------- | ---------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------- |
| type     | `type: feat`, `type: bug`, `type: chore`, `type: docs`                                                                       | `feat` renders as a task; others as issues by kind |
| status   | `status: triage`, `status: brainstorming`, `status: ready`, `status: in-progress`, `status: blocked`, `status: probationary` | Workflow state; unlabeled = todo                   |
| priority | `priority: now`, `priority: normal`, `priority: someday`                                                                     | Urgency (high / normal / low)                      |
| —        | `question`                                                                                                                   | Marks an open question, not a work item            |

Done is expressed by **closing** the issue, not by a label.

## Conventions

- One issue per PR-able unit of work, matching the existing
  branch-and-PR discipline (`feature/<x>` branches, no direct commits to
  `main`).
- Milestones are release-scoped (`v0.3.0`, `v0.4.0`, …). Assign an issue to
  a milestone when it is committed to that release.
- Keep `status:` labels current when starting/blocking work — the dashboard
  reads them live; a stale label is a lie on the cockpit.
- The CHANGELOG remains the release record. Closing an issue does not
  replace its CHANGELOG entry.
