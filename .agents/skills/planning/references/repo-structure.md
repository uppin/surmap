---
description: SurMap repository structure
---

# Repository Structure

```text
src/surmap/        the `surmap` package (data contracts, geometry, motion,
                   SLAM backend interface + RTAB-Map adapter)
tests/             pytest suite mirroring the package
docs/              architecture and hardware decision docs
  architecture.md  design of record
README.md          scope, development commands, hardware, model policy
pyproject.toml     build, Ruff, mypy (strict) and pytest configuration
```

- Design decisions live in `docs/architecture.md`; scope and model policy in
  `README.md`. Update them in the same change that alters the decision.
- There is one package, not a monorepo: per-area docs go under `docs/`, and
  planning documents follow the `planning` skill's PRD/changeset layout.
