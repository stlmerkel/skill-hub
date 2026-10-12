---
name: example-skill
description: "Example skill: replace or delete. Writes a Conventional Commits message for the currently staged changes. Use when the user asks for a commit message, says 'commit this', or wants staged work summarised before committing, even if they never mention Conventional Commits."
metadata:
  version: "0.1.0" # x-release-please-version
---

# Commit message writer

This is the example skill that ships with skill-hub. Replace it with your own, or delete the directory once your hub has real skills.

Conventional Commits matter here because release tooling reads the type prefix to decide the next version, so an accurate type is worth a moment's thought.

## Steps

1. Run `git diff --staged` to read the staged changes. If nothing is staged, say so and stop.
2. Pick the type that fits the change: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`. Use `feat` only for new behaviour and `fix` only for corrected behaviour, since those two drive version bumps.
3. Write a subject line under 72 characters, in the imperative mood: `type: what changes`.
4. If the change needs explaining, add a body after a blank line: why the change was made, not how. The diff already shows how.
5. Show the message and ask before committing.

## Example

```
fix: reject empty skill names

An empty name passed validation and produced a skill with no install path.
```
