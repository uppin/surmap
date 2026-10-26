---
name: debugging
description: Investigate a live issue or unclear failure by forming hypotheses, collecting evidence, documenting findings, and narrowing the fix path. Use when the user wants root-cause analysis, structured investigation, or a troubleshooting plan before making a fix.
---

# Debugging

Investigate deliberately before changing code blindly.

## Workflow

1. Restate the symptom and likely impact.
Clarify what is failing, where it happens, and how severe it is.

2. Form a small hypothesis set.
List the most likely causes before testing anything.

3. Collect evidence.
Use logs, isolated test runs, targeted instrumentation, and minimal repro steps to confirm or eliminate hypotheses.

4. Document the investigation.
Keep a short investigation note when the work is likely to span multiple iterations or produce reusable findings.

5. End with a concrete next step.
Either propose the fix, move into implementation, or explain what extra evidence is still missing.

## Use This Source Prompt

- `.agents/commands/investigate.md`
