# Runtime security & privacy contract

The contract for **executable and automatic Bindle assets** — anything the
kit installs that runs code, and especially anything that would run
*without a per-run human decision* (session hooks, background steps).
Resolves issue #30; per [product-boundary.md](product-boundary.md),
no automatic runtime behavior may ship before it complies with this doc.

How this relates to the neighboring contracts:

- [privacy-boundaries.md](privacy-boundaries.md) governs **tracked-file
  content** — what may land in Git. Its scanner cannot see runtime
  behavior.
- [ownership-boundaries.md](ownership-boundaries.md) governs **what may be
  touched at all** — owned symlinks, the notes home, never foreign files.
- This doc governs **runtime information flow**: what executes, when, what
  it reads, where its output goes, and how you turn it off.

## Capability classes

Every executable asset is classified by the most sensitive thing it does.
Higher classes need more explicit human involvement.

| Class | May do | Default rule |
|---|---|---|
| C0 read-only local diagnostics | stat/read files, report | may run automatically once documented |
| C1 local mutation of owned surfaces | write owned symlinks, notes home, temp dirs | allowed when documented; anything outside owned surfaces requires per-write confirmation |
| C2 repository mutation | commits, file edits in a repo | never automatic — always a human-initiated action |
| C3 transcript / note access | read session transcripts or note *contents* | never automatic; automatic assets may handle **paths, never contents** |
| C4 network access | any request leaving the machine | never by default; each use documented and approved (see below) |
| C5 external-system mutation | `gh` writes, pushes, publishes | never automatic; explicit per-action human approval |

The single C4 carve-out: read-only queries through a user-authenticated
local CLI (e.g. `gh issue list`) may appear in an automatic asset **only
if** its capability card names the exact command, nothing from the local
machine is sent beyond the query itself, and the asset degrades silently
when the tool is absent, unauthenticated, or offline.

## Capability cards (the shipping gate)

An asset that executes automatically cannot ship without a **capability
card** in its documentation. The card states:

- **trigger** — the exact event (e.g. Claude Code `SessionStart:startup`);
- **inputs** — every piece of information it receives or reads;
- **outputs** — what it emits or writes;
- **storage** — where outputs live (must be an owned surface);
- **retention** — how long outputs persist and who deletes them (plain
  user-owned files; no hidden rotation);
- **failure behavior** — must degrade to the manual workflow, never block
  or corrupt a session;
- **disable / uninstall** — the exact command or edit that turns it off;
- **confirmation** — which of its actions, if any, require per-run
  approval;
- **capability class(es)** from the table above.

No card, no ship. A review of the card is part of the PR that introduces
the asset. (If the capability inventory of issue #29 is adopted, these
fields join its schema; until then the card lives in the asset's doc.)

## Current inventory (2026-07-21)

**Automatic assets: six hooks under `global/hooks/`** — two session hooks and
four `PreToolUse` guards. All are opt-in: `bin/install.sh` only symlinks them,
and nothing runs until `bin/install-claude-hooks.sh --apply` wires it.

All six carry a card, below (#392). Five of them shipped without one and were
carded retroactively; writing those five surfaced two facts this document had
not recorded, both stated in the cards themselves rather than smoothed over.
One of them was then removed in #396:

- **`codegraph-chaining-guard.py` used to read session transcript content**:
  a C3 exception that #392 carded after the hook had already shipped. #396
  removed that read. The hook now keys one small temp-state file by a hash of
  `transcript_path` and never opens the transcript, so it is C1.
- **`label-hygiene-guard.py` makes authenticated `gh` reads**, which is the C4
  carve-out and requires a card naming the exact commands. It had none.

Neither is a new capability — both are what the shipped code has been doing.
What was missing was the disclosure this document makes the condition of
shipping.

### Card — `global/hooks/git-push-merged-branch-guard.py`

- **trigger** — Claude Code `PreToolUse`, matcher `Bash`, only when the
  command contains `git push` at a command position.
- **inputs** — the tool call's `command` string and `cwd`; the current branch
  via `git symbolic-ref`; the PR state via exactly
  `gh pr view <branch> --json state,mergedAt,number`. Nothing from the local
  machine leaves it beyond that branch name.
- **outputs** — either a deny decision with a reason, or a one-line stderr
  notice for a `CLOSED` PR. Nothing else.
- **storage** — none. It writes no file.
- **retention** — none; there is nothing to delete.
- **failure behavior** — fails OPEN. An absent, unauthenticated, offline or
  slow `gh` allows the push silently; so does an unparseable command or a
  non-git `cwd`.
- **disable / uninstall** —
  `bin/install-claude-hooks.sh uninstall --guard git-push-merged --apply`.
- **confirmation** — none required; it only ever denies or allows a call the
  agent already initiated, and mutates nothing itself.
- **capability class** — C4 under the read-only carve-out (one authenticated
  `gh` read per push, degrading silently). Never C5: it performs no write.

### Card — `global/hooks/nested-notes-guard.py`

- **trigger** — Claude Code `PreToolUse`, matcher `Bash|mcp__.*github.*`. Acts
  on maintainer-facing GitHub prose only: a `gh pr`/`gh issue`
  `create|edit|comment|review` (or a `gh api` call against `issues/`/`pulls/`)
  that carries a body flag, whose owner resolves to `domattioli`, that carries
  no exemption marker, and whose effective body exceeds 200 characters after
  footer lines are stripped. The MCP GitHub tools are matched by tool name.
- **inputs** — the tool call's `tool_name`, `cwd`, `command`, and for the MCP
  path `tool_input.body`, `owner` and `repo`. The owner is inferred with
  `git remote -v` when no `-R/--repo` flag is present. When `--body-file` is
  used, **it reads that file** — the prose about to be published, supplied by
  the same tool call. It opens no transcript, no notes-home file, and no
  repository file.
- **outputs** — a deny decision with a reason, or nothing. No stderr. Exits 0
  either way.
- **storage** — none.
- **retention** — none.
- **failure behavior** — asymmetric by design, and the asymmetry is the point.
  The **Bash** path fails OPEN: malformed stdin, a failed `git remote -v`, an
  unresolved owner, or an unreadable `--body-file` all allow the call. The
  **MCP** path fails CLOSED: a missing or unreadable body, or an unresolved
  owner, denies — the MCP tools take the body inline, so an unreadable one
  means the guard is being bypassed rather than defeated by the environment.
- **disable / uninstall** —
  `bin/install-claude-hooks.sh uninstall --guard nested-notes --apply`.
- **confirmation** — none required; it denies or allows a call the agent
  already initiated and mutates nothing.
- **capability class** — C0. It reads only local files handed to it by the
  call it is judging, writes nothing, and makes no network request: the `gh`
  and MCP commands it inspects are never executed by the hook.

### Card — `global/hooks/session-start-context.py`

- **trigger** — Claude Code `SessionStart`, matcher `startup|resume`. The
  matcher is enforced by the wiring; the hook itself only checks that the event
  is `SessionStart`.
- **inputs** — stdin's `hook_event_name`, `cwd` and `session_id`; the current
  commit and repo root via `git rev-parse HEAD` and
  `git rev-parse --show-toplevel`; the existence of `bin/session-context.sh`,
  which it then runs with `--cwd <cwd>` and whose stdout becomes the injected
  context. Per rule 2 that script yields **pointers** — notes-home resolution,
  the *paths* of the latest session note and handoff, open issue lines, a git
  summary. Neither the hook nor its marker ever opens a note or a transcript.
- **outputs** — a `SessionStart` `additionalContext` block on stdout, and only
  when the context is non-empty. No stderr. Always exits 0.
- **storage** — one marker file, `<tmpdir>/bindle-session-<session_id>.json`,
  holding exactly the repo root, the head SHA, and a start timestamp. No note
  content, no transcript, no command history.
- **retention** — the marker is consumed and deleted by
  `session-end-breadcrumb.py` at the end of the same session. If the session
  never ends cleanly the file remains in the system temp directory, where the
  OS reclaims it; it is plain JSON, user-owned, and safe to delete by hand at
  any time.
- **failure behavior** — fails OPEN and silently, always. Malformed stdin, a
  non-git `cwd`, an absent `session-context.sh`, a subprocess error, a 5- or
  10-second timeout, or an unwritable temp directory each end in a silent
  return with no context injected and the session fully usable.
- **disable / uninstall** — `bin/install-claude-hooks.sh uninstall --apply`
  (the bare form manages both session hooks).
- **confirmation** — none required; it injects context and writes one temp
  marker, both inside owned surfaces.
- **capability class** — C1: a temp-file write plus local reads. Not C3 — it
  handles note *paths* only, never contents, which is rule 2 holding exactly
  where it was written to hold.

### Card — `global/hooks/session-end-breadcrumb.py`

- **trigger** — Claude Code `SessionEnd`, no matcher. Acts only when `cwd` is
  inside a git repository; anywhere else it returns, since there is nothing
  durable to record.
- **inputs** — stdin's `hook_event_name`, `cwd`, `session_id` and `reason`; the
  repo root and branch via `git`; the commit count for the session via
  `git rev-list --count <head_sha>..HEAD`; the project slug via
  `bin/slugify.sh`; and its own start marker from the temp directory. It
  resolves the notes home from `BINDLE_NOTES_DIR`, then the deprecated
  `CLAUDE_KIT_NOTES_DIR`, then `env.BINDLE_NOTES_DIR` in
  `~/.claude/settings.json` (read-only, for that one key), then `~/.bindle`. It
  opens no session note, no handoff, and no transcript.
- **outputs** — none at all: no stdout, no stderr, always exit 0.
- **storage** — appends **one line** to
  `<notes-home>/projects/<project>/breadcrumbs.log`: timestamp, repo, branch,
  commits made. This is the only file any Bindle hook writes outside the temp
  directory, and it is inside the user's own notes home.
- **retention** — append-only and never rotated or truncated by Bindle: the log
  grows one line per session and is deleted only by you. It is plain text in a
  directory you own. The session-continuity skill states the boundary this
  depends on — a breadcrumb is not a session note, and `/session-start` does
  not read it back as context.
- **failure behavior** — fails OPEN and silently. Malformed stdin, a non-git
  `cwd`, a missing `slugify.sh` (a lowercase fallback is used), a missing or
  corrupt marker (the commit count becomes `unknown`), or an unwritable notes
  home each end in a silent return. It never blocks session termination.
- **disable / uninstall** — `bin/install-claude-hooks.sh uninstall --apply`.
- **confirmation** — none required; the single write lands in the notes home,
  an owned surface, and its shape is fixed by this card.
- **capability class** — C1: one append to an owned surface, plus local reads.
  Not C3 — it records *that* a session happened, never anything said in it.

### Card — `global/hooks/label-hygiene-guard.py`

- **trigger** — Claude Code `PreToolUse`, matcher `Bash`. Acts only when the
  command contains `gh `, carries no `label-hygiene-guard: inert` marker, and
  runs in a repo whose root holds `docs/issue-tracking.md` (the contract gate —
  in any other repo the hook returns silently). The command is split at shell
  command positions and each segment matched against `gh issue close`,
  `gh pr merge`, `gh issue edit`, or a `gh api` call setting `state=closed`.
- **inputs** — the tool call's `tool_name`, `command` and `cwd`; the repo root
  via `git rev-parse --show-toplevel`; the existence (never the contents) of
  `docs/issue-tracking.md`. Then, over the network:
  `gh issue view <n> --json labels,state` and
  `gh pr view <n> --json body,commits`. The second reads PR body text and
  commit messages to find closing keywords. Nothing local is transmitted
  beyond the issue or PR number. It opens no transcript and no notes-home file.
- **outputs** — a deny decision with a reason, or a one-line stderr warning
  (`could not verify … — labels NOT checked. Run bin/check-issue-labels.sh
  afterward.`) on any fail-open path. Silent on a clean allow. Exits 0 either
  way; the decision travels in the JSON, not the exit code.
- **storage** — none.
- **retention** — none; there is nothing to delete.
- **failure behavior** — fails OPEN, loudly. Malformed stdin, a non-git `cwd`,
  a repo without the contract file, an absent or unauthenticated `gh`, a
  non-zero `gh` exit, unparseable JSON, or a 15-second timeout all allow the
  call; every verification failure prints the stderr warning above. The
  doctrine is stated in the hook: a false allow is a stale label, a false deny
  is an unmergeable PR during a GitHub outage.
- **disable / uninstall** —
  `bin/install-claude-hooks.sh uninstall --guard label-hygiene --apply`. A
  single call can also be exempted with the `label-hygiene-guard: inert`
  marker, which disarms the guard for that command only and leaves a greppable
  record.
- **confirmation** — none required; it denies or allows a call the agent
  already initiated and mutates nothing.
- **capability class** — C4 under the read-only carve-out: the two `gh`
  commands named above, both reads, degrading silently. Never C5 — it makes no
  `gh` write. **Note the ceiling:** as a `PreToolUse` hook it can only see
  agent-initiated closes, so a merge performed in the GitHub web UI never
  reaches it. That is a coverage limit, not a failure mode — the sweep in
  `bin/check-issue-labels.sh` exists because of it (#355). That sweep is the
  backstop, and the ceiling stands: moving the correction to PR-open (#395) was
  designed three ways and refuted each time — the offending label is typically
  re-added *seconds after* the PR is opened, so a PR-open rule does not see it.

### Card — `global/hooks/codegraph-chaining-guard.py`

- **trigger** — Claude Code `PreToolUse`, matcher `.*`, so the hook sees every
  tool call. It acts only on a CodeGraph call — an `mcp__*codegraph*` tool, or
  a Bash command matching `codegraph … explore` — that carries no `cg-chain-ok`
  marker, and only when the immediately preceding observed tool use for the
  same transcript path was itself a CodeGraph call.
- **inputs** — the tool call's `tool_name`, `tool_input`, and
  `transcript_path`. It uses only the transcript *path* as a state key, hashed
  before it becomes a filename. It does not open the transcript and never reads
  message prose, thinking blocks, tool results, or file content. Nothing leaves
  the machine.
- **outputs** — a deny decision with a reason, or nothing. No stderr. Exits 0
  either way.
- **storage** — one JSON file per transcript path under the system temp
  directory, or under `BINDLE_CODEGRAPH_GUARD_STATE_DIR` when set for tests.
  The record stores the last observed `tool_name`, `tool_input`, and an update
  timestamp. Writes are atomic temp-file replaces.
- **retention** — stale files older than 24 hours are removed opportunistically
  on each hook invocation. A file may remain longer if the hook never runs
  again, but the next run attempts cleanup.
- **failure behavior** — fails OPEN. A missing, non-string, or unreadable
  `transcript_path`, unreadable or malformed state file, unwritable temp
  directory, malformed stdin, or cleanup failure allows the call. It imports no
  `subprocess` at all, so it has no subprocess failure mode, and transcript
  size does not affect its cost because the transcript is never opened.
- **disable / uninstall** —
  `bin/install-claude-hooks.sh uninstall --guard codegraph --apply`. A single
  intended chain can be allowed with the `cg-chain-ok` marker.
- **confirmation** — none required; it denies or allows a call the agent
  already initiated and mutates nothing.
- **capability class** — **C1**: local temp-state mutation plus local reads of
  hook input. Not C3 — it handles a transcript path, never transcript contents.

Executable-on-request assets, classified:

| Asset | Class | Notes |
|---|---|---|
| `bin/doctor.sh` | C0 | zero writes by design |
| `bin/check.sh`, `bin/check-private-info.sh`, `bin/slugify.sh` | C0 | read/report only (self-tests use temp files) |
| `bin/test-install.sh`, `bin/test-check.sh`, `bin/test-check-frontmatter.sh`, `bin/test-doctor.sh` | C1 | temp fixtures only; never the real environment |
| `bin/install.sh` | C1 | owned symlinks only, per ownership-boundaries |
| `bin/new.sh`, `bin/release.sh` | C2 | repo-local writes, human-invoked; release never pushes |
| `bin/notes-home.sh` | C1 | `status` is read-only; `set`/`migrate`/`reset`/`init-denylist` preview by default and write only on explicit confirmation (`--apply`/TTY yes). Its `~/.claude/settings.json` writes follow rule 7 below verbatim — validate, back up, touch only `env.BINDLE_NOTES_DIR`, show the diff — even though it is not a hook. `init-denylist` writes only a comments-only template inside the notes home, never overwrites, and refuses to follow a `$BINDLE_DENYLIST` override outside it |
| `/session-*`, `/handoff`, `/project-profile`, `/workflow-review`, `/promote-insight`, `/notes-home` commands | C1/C3 | human-invoked; write to the notes home; note *contents* stay out of repos per privacy-boundaries |

Skills and commands are instructions interpreted by the provider, not
programs Bindle executes — but when they direct the agent to run one of
the scripts above, that script's class applies.

## Rules for hooks (the issue #21 gate)

1. **Opt-in only.** Hook installation is its own explicit command — never
   part of default `bin/install.sh`. Installing Bindle must never silently
   add automatic behavior.
2. **Pointers, not payloads.** A hook may pass *paths* to notes, handoffs,
   or transcripts; it must never inject or copy their *contents*. Reading
   contents is the in-session agent's decision, visible to the user.
3. **Transcripts are off-limits.** Where the provider hands a hook a
   transcript path, a Bindle hook does not open it. It may use the path as a
   pointer or state key; it must not read, copy, parse, store, or transmit the
   transcript contents.
4. **No network, with the C4 carve-out above** (documented, read-only,
   authenticated-CLI queries that fail silent).
5. **Fail open, quietly.** A hook that errors must leave the session fully
   usable and the manual workflow intact — a broken hook may cost the
   convenience, never the session.
6. **Inspectable.** Where the provider stores hook config (Claude Code:
   the `hooks` block of `~/.claude/settings.json`), the installing command
   must show the exact change before making it, and the uninstall path
   must remove exactly that change. `bin/doctor.sh` grows a hooks section
   when hooks exist, so inspection never requires reading provider config
   by hand.
7. **Settings writes are surgical.** Provider settings files are foreign
   territory per ownership-boundaries: back up first, touch only the keys
   named in the card, show a diff, require confirmation.

## Auditing and disabling automatic behavior

- **Inspect:** every automatic asset is listed in this doc's inventory and
  reported by `bin/doctor.sh` (once any exist). If it isn't in both
  places, it's a bug — file it.
- **Disable one asset:** follow its card's disable line (one command or
  one settings edit — cards may not require multi-step teardowns).
- **Disable everything:** removing Bindle's hook entries from the provider
  settings plus `bin/install.sh --prune` must return the machine to
  fully-manual operation with no residue beyond user-owned notes.

## Non-goals

- Securing the underlying model provider: what Claude Code or any
  assistant does with context it already has is governed by that product,
  not by Bindle.
- Formal security certification or sandboxing — this is a personal kit's
  written discipline, enforced by review and tests, not a security
  boundary against a hostile actor.
