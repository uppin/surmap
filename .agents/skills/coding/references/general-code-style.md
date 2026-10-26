---
description:
---
See the repo [README.md](../../../../README.md).

## Comments

A comment answers **why**, and is written only when the code cannot say it itself.

- **Write one when the reason is not visible in the code**: a constraint, a non-obvious trade-off,
  a workaround for a named bug, an invariant a caller must keep, why the obvious approach was
  rejected.
- **Skip it for self-explanatory code.** A comment that restates what the next line does
  (`// create the user`) adds nothing. If the code is hard to follow without one, improve the names
  or extract a function first, and comment only the *why* that is still left.
- **Doc comments follow the same rule.** We don't write API documentation comments (JSDoc, rustdoc,
  docstrings) that describe what a function does; a doc comment is there only to carry a *why*.
- **"What changed" and "how we got here" are not *why*.** Narration (`// now uses X instead of Y`)
  and process references (red/green phases, changeset sections, step numbers) belong in the commit
  message and the changeset, not in the code.
- The `TODO` / `FIXME` markers README.md requires for temporary code — including `TODO(pr-<k>)`
  stack stubs — are not affected.
