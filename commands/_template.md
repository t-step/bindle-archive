---
description: One-line summary shown in the slash-command list
argument-hint: [arg]
# Optional: pre-authorize specific tool calls so the command runs without prompts.
# allowed-tools: Bash(git status:*), Bash(git diff:*)
# Optional: pin a model for this command.
# model: sonnet
---

<!--
This is a slash command. When the user types /command-name <args>, this whole
file becomes the prompt. Useful substitutions:
  $ARGUMENTS   all args as one string
  $1, $2       positional args
  !`cmd`       run a shell command and inline its output (needs allowed-tools)
  @path/to/f   inline a file's contents
-->

Do the following with the user's input: $ARGUMENTS

1. <step>
2. <step>
