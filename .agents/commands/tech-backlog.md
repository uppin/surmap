---
description: Multi-purpose tech backlog management using GitHub issues with tech-backlog label
---
# Tech Backlog Management Command

This command manages technical backlog items as GitHub issues labeled with `tech-backlog`. It supports adding new items, listing/searching items, and viewing oldest pending work.

**Prerequisites:** GitHub MCP server must be enabled and configured (recommended), OR GitHub CLI (`gh`) as fallback.

## Command Modes

The command operates in three modes based on user intent:

### 1. Add Mode
**Trigger**: User wants to add/create a new tech backlog item

**Actions**:
1. **Gather information from user** (if not provided):
   - Title/summary of the technical work
   - Detailed description/elaboration
   - Related feature documents (docs/<area>/)
   - Related dev documents ({src,tests,docs}/*/docs/)
   - Technical context, motivation, or rationale

2. **Search for related documentation**:
   - Use `Glob` to find relevant feature docs: `docs/<area>/**/*.md`
   - Use `Glob` to find relevant dev docs: `{src,tests,docs}/*/docs/**/*.md`
   - Use `Grep` to search for relevant context in documentation
   - Ask user to confirm which documents are relevant

3. **Create GitHub issue**:
   - Use GitHub MCP `github__create_issue` tool (preferred)
   - Fallback: Use `gh issue create` command
   - Repository: Extract from git remote (typically `-private/this repo`)
   - Title: Clear, actionable summary
   - Body format:
     ```markdown
     ## Description
     [Detailed elaboration of the technical work]

     ## Context
     [Why this work is needed, technical motivation]

     ## Related Documentation
     - Feature: [link to feature docs]
     - Dev: [link to dev docs]

     ## Technical Details
     [Any specific technical considerations, constraints, or approaches]

     ## Acceptance Criteria
     - [ ] [Specific criteria for completion]
     ```
   - Labels: `tech-backlog`

4. **Confirm creation** with issue number and URL

**Example user intent**:
- "Add to tech backlog: refactor map rendering pipeline"
- "Create backlog item for improving test performance"
- "Tech backlog: extract shared logic from components"

### 2. List/Search Mode
**Trigger**: User wants to list, search, or filter tech backlog items

**Actions**:
1. **Parse user query** to extract:
   - Keywords for filtering
   - Status filter (open/closed/all)
   - Sort preference (created date, updated date)
   - Count/limit

2. **Search GitHub issues**:
   - Use GitHub MCP `github__list_issues` or `github__search_issues` tools (preferred)
   - Fallback: Use `gh issue list` command
   - Repository: Extract from git remote
   - Query format: `--label tech-backlog --search "[keywords]"`
   - State: Defaults to "open" unless user specifies otherwise
   - Sort: Default to "created" (oldest first) or "updated" based on context

3. **Display results**:
   - Issue number, title, creation date
   - Link to issue
   - Brief summary if body is available
   - Status indicators (open/closed)

**Example user intent**:
- "Show tech backlog items"
- "List tech backlog related to map"
- "What's in the tech backlog?"
- "Show closed tech backlog items"

### 3. Default Mode (No Specific Intent)
**Trigger**: User invokes `/tech-backlog` without clear add/list intent

**Actions**:
1. **List 5 oldest open items**:
   - Use GitHub MCP `github__list_issues` tool (preferred)
   - Fallback: Use `gh issue list` command
   - Repository: Extract from git remote
   - Labels: `tech-backlog`
   - State: `open`
   - Sort: `created`
   - Order/Direction: `asc` (ascending - oldest first)
   - Limit/Per_page: 5 items

2. **Display format**:
   ```
   📋 Tech Backlog - 5 Oldest Items

   1. #123 - Refactor map rendering pipeline (Created: 2025-12-15)
      https://github.com/owner/repo/issues/123

   2. #145 - Extract shared component logic (Created: 2025-12-20)
      https://github.com/owner/repo/issues/145

   [... 3 more items ...]

   Total open tech backlog items: 12
   ```

3. **Provide guidance**:
   - Suggest: "Use `/tech-backlog add` to create new items"
   - Suggest: "Use `/tech-backlog search [keywords]` to filter items"

**Example user intent**:
- Just typing `/tech-backlog`
- "What's the tech backlog status?"

## Intent Detection

**Add Intent Indicators**:
- Keywords: "add", "create", "new", "track", "record"
- Action verbs: "refactor", "improve", "extract", "optimize" (followed by description)
- Imperative mood

**List Intent Indicators**:
- Keywords: "list", "show", "search", "find", "filter"
- Question words: "what", "which", "how many"
- Plural references: "items", "issues", "tasks"

**Default (No Clear Intent)**:
- Just command name
- Vague requests like "check backlog", "backlog status"

## GitHub Integration

### Primary Method: GitHub MCP Server

**Preferred approach** - Use GitHub MCP server tools:

1. **github__create_issue** - For creating new tech backlog items
   - Parameters: owner, repo, title, body, labels
   - Returns: issue number, URL

2. **github__list_issues** - For listing tech backlog items
   - Parameters: owner, repo, state, labels, sort, direction, per_page
   - Returns: array of issues with number, title, body, created_at, state

3. **github__search_issues** - For searching with keywords
   - Parameters: query (includes repo, label, keywords), per_page
   - Returns: array of matching issues

**Advantages of MCP**:
- Native integration with Muse
- Better error handling
- Structured data responses
- No external CLI dependencies

### Fallback Method: GitHub CLI

If GitHub MCP is not available, fall back to `gh` CLI:

1. **gh issue create** - For creating new tech backlog items
   ```bash
   gh issue create --repo owner/repo --title "Title" --body "Body" --label "tech-backlog"
   ```

2. **gh issue list** - For listing tech backlog items
   ```bash
   gh issue list --repo owner/repo --label "tech-backlog" --state open --limit 5
   ```

3. **gh issue list with search** - For searching with keywords
   ```bash
   gh issue list --repo owner/repo --label "tech-backlog" --search "keywords"
   ```

### Repository Detection
```bash
# Extract owner/repo from git remote
git remote get-url origin | sed 's/.*github\.com[:/]\(.*\)\.git/\1/' | tr '/' ' '
# Returns: "owner repo" (space-separated for easy parsing)
```

### Tool Selection Logic

**Priority order**:
1. **Try GitHub MCP first**: Attempt to use MCP server tools
2. **Fall back to gh CLI**: If MCP unavailable, use gh command
3. **Report error**: If neither available, provide setup instructions

### Error Handling
- **GitHub MCP not available**: Silently fall back to gh CLI
- **GitHub CLI not available** (after MCP fails): "❌ GitHub integration not available. Please enable GitHub MCP server OR install GitHub CLI: https://cli.github.com/"
- **Not authenticated** (gh CLI): "❌ GitHub CLI is not authenticated. Run: gh auth login"
- **No issues found**: "No tech backlog items found matching your criteria."
- **Rate limit**: "GitHub API rate limit reached. Please try again later."

## Workflow Examples

### Example 1: Add Item
```
User: /tech-backlog add: refactor map rendering to use streaming approach

AI Actions:
1. Search for related docs: docs/<area>/mapping/, {src,tests,docs}/*/docs/
2. Prompt user: "Found related docs: docs/<area>/mapping/rendering.md. Include this reference?"
3. Gather more details about motivation and acceptance criteria
4. Create GitHub issue (try MCP first, fallback to gh CLI):
   - Try: github__create_issue MCP tool
   - Fallback: gh issue create command
   - Title: "Refactor map rendering to use streaming approach"
   - Body: Full description with links to docs/<area>/mapping/rendering.md
   - Labels: ["tech-backlog"] (MCP) or tech-backlog (gh CLI)
5. Respond: "✅ Created tech backlog item #234: https://github.com/owner/repo/issues/234"
```

### Example 2: List with Keywords
```
User: /tech-backlog show items related to testing

AI Actions:
1. Search for issues (try MCP first, fallback to gh CLI):
   - Try: github__search_issues with query "repo:owner/repo label:tech-backlog testing"
   - Fallback: gh issue list --label tech-backlog --search "testing"
2. Display results:
   📋 Tech Backlog - Testing Items (3 found)

   1. #178 - Improve integration test performance (Created: 2025-11-10)
      Related to: docs/architecture.md
      https://github.com/owner/repo/issues/178

   2. #192 - Add visual regression testing (Created: 2025-12-05)
      https://github.com/owner/repo/issues/192

   3. #201 - Extract test utilities to shared package (Created: 2026-01-15)
      https://github.com/owner/repo/issues/201
```

### Example 3: Default Mode
```
User: /tech-backlog

AI Actions:
1. List oldest issues (try MCP first, fallback to gh CLI):
   - Try: github__list_issues with labels="tech-backlog", state="open", sort="created", direction="asc", per_page=5
   - Fallback: gh issue list --label tech-backlog --state open --limit 5
2. Display:
   📋 Tech Backlog - 5 Oldest Items

   1. #123 - Refactor map rendering pipeline (Created: 2025-10-01)
      https://github.com/owner/repo/issues/123

   2. #145 - Extract shared component logic (Created: 2025-10-15)
      https://github.com/owner/repo/issues/145

   3. #156 - Optimize bundle size (Created: 2025-10-22)
      https://github.com/owner/repo/issues/156

   4. #178 - Improve integration test performance (Created: 2025-11-10)
      https://github.com/owner/repo/issues/178

   5. #192 - Add visual regression testing (Created: 2025-12-05)
      https://github.com/owner/repo/issues/192

   Total open tech backlog items: 12

   💡 Tip: Use `/tech-backlog add [description]` to create new items
   💡 Tip: Use `/tech-backlog search [keywords]` to filter items
```

## Best Practices

### Creating Tech Backlog Items
1. **Clear titles**: Use action verbs (refactor, extract, optimize, improve)
2. **Link documentation**: Always reference related feature/dev docs
3. **Provide context**: Explain why this work is valuable
4. **Define acceptance**: What does "done" look like?
5. **Technical details**: Include constraints, approaches, or considerations

### Managing Backlog
1. **Regular review**: Use default mode to check oldest items
2. **Prioritization**: Update GitHub issue priority/labels separately
3. **Close completed**: Mark issues as closed when work is merged
4. **Link PRs**: Reference tech backlog issue numbers in PRs

### Documentation Links
**Format for documentation references in issue body**:
```markdown
## Related Documentation
- Feature: [Semantic map](../../docs/architecture.md)
- Dev: [map Package Docs](../../mapping-pipeline/mapping-pipeline/docs/architecture.md)
- PRD: [map Performance Improvements](../../docs/mapping-pipeline/1-WIP/performance-prd.md)
```

**Use relative paths** from repository root so links work in GitHub UI.

## Output Format

### Add Mode Response
```markdown
✅ Created tech backlog item #[number]

**Title**: [Issue title]
**URL**: [GitHub issue URL]
**Labels**: tech-backlog

The item has been added to the tech backlog and is now tracked in GitHub.
```

### List Mode Response
```markdown
📋 Tech Backlog - [Filter Description] ([count] found)

[For each item:]
[number]. #[issue_number] - [title] (Created: [date])
   [Optional: Related docs if available]
   [GitHub URL]

[If many items:]
Showing [displayed] of [total] items. Use search keywords to narrow results.
```

### Default Mode Response
```markdown
📋 Tech Backlog - 5 Oldest Items

[List of 5 oldest items with numbers, titles, dates, URLs]

Total open tech backlog items: [count]

💡 Tip: Use `/tech-backlog add [description]` to create new items
💡 Tip: Use `/tech-backlog search [keywords]` to filter items
```

## Related Commands and Rules

**Related commands**:
- `/create-kb` - For creating knowledge base articles (different from backlog)
- `/plan-ft` - For planning new features (may generate backlog items)
- `/pr-wrap` - May reference tech backlog items when closing them

**Related rules**:
- [feature-doc](/.agents/skills/planning/references/feature-doc.md) - Feature documentation structure
- [dev-doc](/.agents/skills/planning/references/dev-doc.md) - Dev documentation structure
- [git-usage](/.agents/skills/pr/references/git-usage.md) - Git workflow standards

**Integration with workflows**:
- During feature planning: Identify technical debt and add to backlog
- During PR review: Note future improvements as backlog items
- During retrospectives: Convert lessons learned to backlog items

## Implementation Notes

### Tool Detection and Fallback Logic
```python
// Pseudo-code for tool selection
async function createIssue(owner, repo, title, body, labels) {
  // Try GitHub MCP first
  try {
    const result = await github__create_issue({
      owner,
      repo,
      title,
      body,
      labels: [labels] // MCP expects array
    });
    return result; // Returns {number, url}
  } catch (mcpError) {
    // MCP not available, fallback to gh CLI
    try {
      const result = await shell(
        `gh issue create --repo ${owner}/${repo} --title "${title}" --body "${body}" --label "${labels}"`
      );
      // Parse URL from gh output
      return parseGhOutput(result);
    } catch (ghError) {
      throw new Error('GitHub integration not available');
    }
  }
}
```

### Repository Auto-Detection
```bash
# Extract owner/repo from git remote
git remote get-url origin | sed 's/.*github\.com[:/]\(.*\)\.git/\1/' | tr '/' ' '
# Returns: "owner repo" (space-separated)
```

### Documentation Search Strategy
1. **Start broad**: Search all docs/<area>/ and {src,tests,docs}/*/docs/ directories
2. **Use keywords**: Extract nouns from user's description for search
3. **Confirm with user**: Don't auto-link without user verification
4. **Provide context**: Show file path and brief excerpt when suggesting docs

### Issue Body Template
```markdown
## Description
[Detailed elaboration from user input]

## Context
[Why this work is needed - technical motivation]

## Related Documentation
[Auto-discovered or user-provided doc links]

## Technical Details
[Specific considerations, constraints, or approaches]

## Acceptance Criteria
- [ ] [Criteria 1]
- [ ] [Criteria 2]

---
Created via `/tech-backlog` command
```

## Error Scenarios

### GitHub Integration Not Available
```
❌ GitHub integration not available

The tech backlog management requires GitHub integration via:
1. GitHub MCP server (recommended), OR
2. GitHub CLI

**Option 1: Enable GitHub MCP Server (Recommended)**
1. Configure GitHub MCP server in Muse settings
2. Authenticate with GitHub
3. Retry this command

**Option 2: Install GitHub CLI (Fallback)**
- macOS: brew install gh
- Linux: See https://github.com/cli/cli#installation
- Windows: See https://github.com/cli/cli#installation
- After installation: gh auth login

Alternatively, create issues manually at:
https://github.com/[owner]/[repo]/issues/new?labels=tech-backlog
```

### GitHub CLI Not Authenticated (Fallback Mode)
```
⚠️ GitHub MCP not available, using GitHub CLI fallback

❌ GitHub CLI is not authenticated

Please authenticate with GitHub:
gh auth login

Then retry this command.

💡 Tip: Enable GitHub MCP server for better integration
```

### No Repository Detected
```
❌ Could not detect GitHub repository

Make sure you're in a git repository with a GitHub remote configured.

Check: git remote get-url origin
```

### No Items Found
```
📋 Tech Backlog - No Items Found

No tech backlog items match your search criteria.

💡 Tip: Use `/tech-backlog add [description]` to create the first item
```

---

**Last Revised:** 2026-02-10
