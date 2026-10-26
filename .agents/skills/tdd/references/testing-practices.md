---
description: Testing practices, anti-patterns and test composition for SurMap
---

# Testing Practices

- The suite is the contract: a red test is a finding, not an inconvenience.
  Never skip, delete or loosen a test to make a change pass without saying
  so and recording why (see the `testing` skill and `/skip-tests`).
- Prefer failing-first for behaviour changes (the `tdd` skill's red/green
  cycle); reproduce bugs with a failing test before fixing them.
- Anti-patterns: tests that depend on order, wall-clock timing, the network
  or local files outside fixtures; assertions on implementation details;
  mocks that re-implement the thing they replace.
- Every test you write or rewrite is fluent where it aids reading: load the
  `fluent-tests` skill first, bar in
  `skills/testing/references/fluent-style.md` — even when the suite you add
  to is not fluent. Do not rewrite that suite's other tests in the same change.
