---
name: analyze-third-party
description: Analyze an external repository or local third-party codebase for structure, dependencies, build behavior, compatibility risks, and likely failure modes. Use when the user asks to inspect another project, vendor dependency, sample repo, or unfamiliar external codebase.
---

# Analyze Third-Party

Study an external project before integrating with it or relying on it.

## Workflow

1. Identify the project entry points.
Read the README, dependency manifests, build configs, and test setup first.

2. Map the structure and stack.
Understand how the project is organized, what frameworks it uses, and what its runtime or build assumptions are.

3. Look for real integration risks.
Focus on compatibility, CI requirements, platform constraints, security concerns, and likely failure points.

4. Summarize actionable conclusions.
Report what matters for adoption, debugging, or integration, not just a directory walkthrough.

## Use This Source Prompt

- `.agents/commands/analyze-third-party.md`
