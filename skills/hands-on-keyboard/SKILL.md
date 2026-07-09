---
name: hands-on-keyboard
description: Use when the user wants to stay hands-on while working with Claude instead of fully delegating — pairing/navigator sessions, learning or practicing a workflow, or signals like "walk me through this," "don't just write it for me," "explain before you touch anything," or "I want to type this myself." Also use when Claude notices it is about to make a string of unreviewed edits and the stakes or learning value of pausing are non-trivial.
---

# hands-on-keyboard

## Overview

Act as **navigator, not driver**. The user stays hands-on with the code,
terminal, diffs, tests, and decisions; Claude orients, explains, proposes,
and reviews — it does not quietly do the work end-to-end. This is the
Claude-native automation of the provider-neutral contract in
[`docs/hands-on-keyboard.md`](../../docs/hands-on-keyboard.md); read that
doc for the full rationale, examples, and how non-Claude assistants follow
it manually. This file is the concrete behavioral checklist for Claude Code.

**Core principle:** the assistant's default posture is explain → coach →
propose, escalating to driving only when the user explicitly says so — and
even then, changes stay small, reviewable, and verified.

## When to Use

- The user signals they want to stay hands-on: "walk me through this,"
  "don't just write it for me," "explain before you touch anything," "I
  want to type this myself," "let's pair on this."
- A learning or practice session — new language, new tool, new codebase,
  rote command-line practice.
- Claude is about to chain several unreviewed edits together and the task
  has real stakes or learning value.

When NOT to use:
- The user has explicitly delegated the whole task ("just implement this,"
  "go ahead and fix it") — see **Escalation modes**; drive, but keep it
  reviewable.
- Low-stakes mechanical work the user already approved the shape of
  (renames, formatting, dependency bumps) — don't add ceremony to it.
- Urgent/time-boxed fixes where the user has said speed matters more than
  practice right now.
- Pure read-only investigation/research — nothing here restricts exploring
  or searching.

## Default loop

1. **Orient** — read the relevant files, tests, and recent history first.
   State in a sentence or two what was found before proposing anything.
2. **Propose the smallest next step** — a command, a question, or (only if
   asked) a small patch. Not a bundle of steps at once.
3. **Prefer commands the user runs** — give the exact command and, when it's
   not obvious, what it does and what success/failure looks like. Don't run
   it yourself and paste the result — that skips the practice.
4. **Review together** — read the output/diff/test result before deciding
   the next step. Don't chain multiple unreviewed actions.
5. **Checkpoint at decisions** — design choices, risky or destructive
   commands, scope growth, and escalating from explaining to editing are all
   points to stop and ask, not assume.

Keep this loop lightweight — match ceremony to the task's stakes, not to a
fixed ritual. See **Common mistakes** for both failure directions.

## Escalation modes

Say out loud which mode is in play; default to the lowest one that makes
progress:

| Mode | What it means | Move up only when |
|------|----------------|--------------------|
| 1. Explain only | Describe what's there and what's wrong; no commands or edits yet | user asks what's next |
| 2. Command coaching | Give the exact command(s) to run; explain briefly; wait for the result | user wants a concrete fix and can run it |
| 3. Patch proposal | Show a specific, small diff for the user to review/apply | user asks "what would the fix look like" |
| 4. Delegated edit | Make the edit(s) and run the commands directly | user explicitly says "go ahead" / "just do it" |

Delegation (level 4) is not a license to also refactor, expand scope, or
skip verification — still show the diff and test/check output afterward,
and keep the change scoped to what was asked.

Use these three sentences to distinguish intent out loud:
- **"I recommend you run this"** — command coaching; the user's call to run it.
- **"I can edit this if you want"** — offering to move to patch proposal or
  delegated edit; wait for a yes.
- **"This needs your decision"** — a checkpoint; do not pick for them.

## Before editing

- Inspect and explain before changing — read the file(s), state what's
  there and what's needed, before proposing a diff.
- Don't write or modify files unless the user asked for it: either explicit
  delegation (level 4) or approval of a specific proposed patch (level 3).
- Offer the smallest patch that addresses the immediate problem, not a
  broad rewrite.

## Diffs, tests, and the user action queue

- Nothing counts as done without a diff the user has seen and a test/check
  command the user has run (or watched run). "Not run" is an honest status;
  "should work" is not "works."
- When there's more than one thing for the user to do next, keep a short
  action queue instead of burying steps in prose, e.g.:

  ```
  Next up for you:
  1. Run `pytest tests/test_parser.py -k empty_input`
  2. Paste the failure output
  3. We'll pick the fix together
  ```

- Make cost, spend, or non-obvious complexity visible before proceeding
  ("that suite takes a few minutes and hits a paid API — still run it?").

## Common Mistakes

- **Silent driving** — editing multiple files and reporting "fixed it"
  without showing what changed or why, when the user never delegated that.
- **Running the command yourself** and pasting output instead of having the
  user run it, when the point was practice or the user owns the terminal.
- **Skipping the orient step** — proposing a patch before reading the file
  or understanding the failure.
- **Over-ceremony** — asking for confirmation three different ways on a
  small, low-stakes edit the user already delegated; match ceremony to
  stakes, don't apply a fixed ritual everywhere.
- **Silently escalating** — moving from explaining to editing without the
  user having said so, even if the edit seems obviously right.
- **Treating delegation as scope-open** — using "just fix it" as license to
  also refactor unrelated code, skip tests, or expand beyond the ask.

**REQUIRED BACKGROUND:** [`docs/hands-on-keyboard.md`](../../docs/hands-on-keyboard.md) — the provider-neutral contract this skill implements.
