---
name: get-skills
description: Search and install skills from the  coding-agents-plugins marketplace. Use when the user wants to find, browse, summarize, or install marketplace skills into this project or globally. Accepts an optional search query as $ARGUMENTS.
user-invocable: true
---

> **Genericized import.** This workflow was originally written for a specific product and infrastructure. Service, artifact, dashboard and host names below are `example` placeholders — substitute SurMap's equivalents (see `README.md` and `docs/architecture.md`) before acting, and confirm any external system exists before calling it.


# Get Skills

Browse, search, summarize, and install skills from the  `coding-agents-plugins` marketplace.

## Invocation

```
/get-skills [query]
```

- **With query** — search for skills matching the topic
- **No arguments** — list all available skills

## Flow

### 1. Discover

If `$ARGUMENTS` is set, search:

```bash
muse skills add
```

If no arguments, list all:

```bash
muse skills add
```

Both commands return a JSON payload with a `skills` array. Each entry has `name`, `description`, `source`, and `installed` (`{ repo, global }`).

### 2. Present Results

Show a concise list: **name** — description. Mark already-installed ones with `(installed)`.

If no skills match a search query, say so and stop — do not fabricate results.

### 3. Act on a Selection

Ask the user which skill they want to act on. Then offer these options:

**a. Summarize** — fetch and display the full SKILL.md:

```bash
gh api --method GET \
  repos/-private/coding-agents-plugins/contents/<source>/SKILL.md \
  --jq '.content' | base64 -d
```

Where `<source>` comes from the `source` field in the JSON result (e.g. `skills/create-pr`).

After fetching, summarize: what the skill does, when to use it, and any prerequisites (auth, tools, env vars it relies on).

**b. Install to this project** — add to `project.json` for this repo only:

```bash
muse skills add
```

**c. Install globally** — add to global agent skills (available in all repos):

```bash
muse skills add
```

After installing, confirm what was added and where (project vs global).

## Notes

- `surmap skills find` and `surmap skills list` are the source of truth. Do not use `gh search code` for discovery.
- The `installed.repo` and `installed.global` flags in the JSON show what is already installed — skip reinstall prompts for those.
- Skills are standalone. For full plugin bundles (hooks, MCP, and multiple skills), the user must install the plugin manually — do not attempt plugin installation through this skill.
