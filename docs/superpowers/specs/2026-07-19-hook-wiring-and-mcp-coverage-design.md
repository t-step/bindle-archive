# Hook wiring and MCP coverage — design (#264)

Closes the two holes recorded when `global/hooks/nested-notes-guard.py` was
built: MCP write tools bypass it, and the wiring hardcodes a checkout path so a
repo move silently disables it.

## Problem

The guard enforces the maintainer-facing-prose rule by inspecting `gh`
invocations in Bash command strings. Two gaps shipped with it.

**MCP write tools bypass it.** The guard reads `tool_input.command` and matches
`gh` subcommands. A GitHub write performed through an MCP tool never carries a
command string, so the rule is enforced on one of two available paths. No GitHub
MCP server is configured in this environment today — the roster is Gmail,
Calendar, Drive, codegraph, Vercel — so this is a latent hole, not one currently
being exercised. It reopens the day one is installed, with no signal.

**The wiring hardcodes the repo path.** `~/.claude/settings.json` invokes:

```
test -f /Users/<user>/Developer/bindle/global/hooks/nested-notes-guard.py \
  && python3 /Users/<user>/Developer/bindle/global/hooks/nested-notes-guard.py \
  || true
```

The `|| true` is the silent-disable: move or rename the checkout and every write
passes unguarded, with nothing reported. The two session hooks
(`session-start-context.py`, `session-end-breadcrumb.py`) carry the same
hardcoded path under a bare `python3 <abs path>` — a different failure mode, the
same root cause. All three are in scope: leaving two on the broken pattern means
the next repo move reopens this bug under a different filename.

A guard that fails silently on relocation, and covers one of two write paths, is
weaker than its presence implies.

## Design

### 1. Stable indirection for hook paths

`bin/install.sh` symlinks each `global/hooks/*.py` to `~/.claude/hooks/<name>.py`,
using the same `ln -s` directory-symlink pattern it already applies to skills,
commands, and agents. Consequences match the existing install model: an edit in
the checkout is live immediately for every session, and a repo move is repaired
by re-running `bin/install.sh`.

`bin/install-session-hooks.sh` writes `~/.claude/hooks/<name>.py` into
`settings.json` rather than checkout-absolute paths, keeping its current
preview-unless-`--apply` behavior and idempotence.

**`settings.json` remains user territory.** `install.sh` still never writes it,
per `docs/ownership-boundaries.md`; only the explicit
`install-session-hooks.sh --apply` does, and only with the operator's answer.

**The `|| true` goes.** Claude Code's documented PreToolUse contract is that
**only exit code 2 blocks** a tool call; exit 1 is an explicit *non-blocking*
error — surfaced in the transcript, with the tool call proceeding. So a hook
whose script has gone missing exits 1, says so visibly, and blocks nothing. That
is exactly the "fails loudly rather than silently" #264 asks for, at no risk of a
bricked session, so the suppression has no remaining justification. Combined with
the stable symlink it should essentially never fire.

The command becomes a bare `python3 ~/.claude/hooks/nested-notes-guard.py`.
Doctor (§3) remains the place a configuration problem is *diagnosed*; the exit
code is what makes it *noticed*.

### 2. Generic tool_input parsing in the guard

The guard grows a front-end that reads `tool_name` and normalizes both shapes
into the same `(owner, body)` pair:

- **Bash** — unchanged: parse `tool_input.command`, extract owner via `-R/--repo`
  or a `repos/<owner>/` API path, extract body from `--body`, `--body-file`, or
  `-f body=`.
- **MCP** — for a `tool_name` matching `mcp__.*github.*`, read the structured
  `tool_input` fields directly: `body` for prose, `owner` (falling back to a
  `repo` of the form `<owner>/<name>`) for ownership.

Everything downstream is shared and unchanged: the `↪` marker test, `SHORT_BODY`,
the `nested-notes-exempt` marker, footer exclusion, and the `OWNER` check. The
matcher in `settings.json` becomes `Bash|mcp__.*github.*`.

**Unparseable input fails closed on the write path.** If `tool_name` is a GitHub
MCP tool whose name is write-shaped (`create`, `update`, `comment`, `review`) and
the front-end cannot locate a body or an owner, the guard **denies**, naming the
escape in its reason: use the `gh` path via Bash, or add the
`nested-notes-exempt` marker. Read-shaped GitHub MCP tools and every non-GitHub
tool allow.

This deliberately departs from the guard's existing "can't judge → allow" stance
for unreadable `--body-file` targets. That case is a `gh` command the guard *did*
parse, where only the file was unreachable; this case is the write path #264
exists to cover, arriving in a shape the guard does not recognize. Passing it is
the precise failure this issue was filed about.

The cost is real and worth stating: when a body cannot be parsed, the exempt
marker inside it cannot be read either, so such a tool is hard-blocked until the
guard learns its schema. Accepted because the blast radius today is zero (no
GitHub MCP server is configured), the failure is loud and one commit from fixed,
and a guard that silently passes what it cannot read is worse than one that
stops and says so.

### 3. Doctor reporting

`bin/doctor.sh` reports, for each hook Bindle ships:

| Condition | Report |
|---|---|
| Configured in `settings.json`, path resolves to this checkout | OK |
| Configured, path resolves elsewhere | warn — names the resolved target |
| Configured, path does not resolve | warn — "re-run `bin/install.sh`" (the hook also exits 1 loudly at call time) |
| Not configured | informational — the session hooks are opt-in by design |

Doctor is the diagnosis channel; the hook's own nonzero exit is the detection
channel. Neither alone is sufficient — an exit-1 notice says something is wrong,
doctor says what and how to fix it.

## Testing

`bin/test-nested-notes-guard.sh` (15 cases today) gains MCP-shaped input cases:
compliant body, bare-prose body that must be denied, exempt marker, sub-
`SHORT_BODY` body, non-`domattioli` owner, a write-shaped tool with an
unparseable body that must be **denied** (§2's fail-closed rule), and a
read-shaped tool that must allow.

**Mutation pass, per the repo rule that a new gate must be proven failable:**
stub out the MCP branch and confirm every new negative assertion flips to
failing. An assertion that still passes with the branch removed was vacuous.

`bin/doctor.sh`'s new check gets fixture coverage for the dangling-symlink case —
the failure this design exists to surface.

## Non-goals

- No change to the guard's compliance heuristic. The `↪` leaf remains the signal;
  this is not a full outline lint, and #264 does not ask for one.
- No change to which repos the rule covers (`OWNER = "domattioli"`).
- No automatic writing of `settings.json` by `install.sh`.
- No new hooks. This is wiring and coverage for the three that exist.

## Acceptance mapping

| #264 item | Where |
|---|---|
| decision recorded on MCP write-tool coverage | §2 — extend generically, with the rationale that the hole reopens silently otherwise |
| wiring survives a repo move, or fails loudly | §1 — both: survives via the `~/.claude/hooks/` symlink, and a dangling path now exits 1 visibly instead of being swallowed by `\|\| true`; §3 — doctor names the fix |
| `bin/doctor.sh` reports hook configured but not reachable | §3 |
