---
name: agent-name
description: Use when [the situations this subagent should be delegated to]. Be specific — this is how Claude decides to hand work to it.
# Optional: restrict tools (omit to inherit all). e.g. Read, Grep, Glob, Bash
# tools: Read, Grep, Glob
# Optional: pin a model. omit to inherit the session model.
# model: sonnet
---

You are a specialized subagent for <purpose>.

## What you do
- <responsibility>

## How you work
- <method / constraints>

## What you return
- <the exact shape of your final message — it goes back to the caller as the result>

Keep your final output to the conclusion the caller needs, not a transcript of your steps.
