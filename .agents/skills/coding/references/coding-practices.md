---
description:
---
# Coding Practices and Development Quality Standards

This document outlines the coding practices and quality standards that must be followed throughout development.

## Development Quality Standards

You are a Senior developer and produce quality code accordingly.

- Always strive to come up with a permanent long-term solution. Your goal is to produce reliable production and test code.
- Do not add fallbacks, unless getting consent from the User. Any fallbacks might make the system unsafe or prone to bugs.
- There shouldn't be any code branches in production code that only work for test environment. Production code behavior should be identical in both test and production environments.
- Any temporary / non-production code should be marked with FIXME or TODO annotations
- **SUPER CRITICAL** DO NOT EVER SKIP TESTS without explicit concent of the User. **NEVER!**

Also see `general-code-style.md` in this skill's `references/` folder.

## Language specific guidelines

- Python: `python-code-style.md` in this skill's `references/` folder
- Rust on WASM: `../../tech-stack/references/native-package.md`
