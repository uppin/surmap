---
description: Inspect IDE MCP servers and diagnose loading issues
---
# Inspect IDE MCP Servers

This prompt provides instructions for diagnosing MCP (Model Context Protocol) server issues in an IDE by examining log files and providing issue summaries.

## MCP Log Locations

The concrete paths below are **Muse's**. Other harnesses store MCP logs elsewhere — check the
harness's own log directory first, then apply the same diagnostic process.

TODO: fill in the Claude Code and Codex MCP log locations once confirmed on this machine.

### Primary Log Directory Structure (Muse)
```
~/Library/Application Support/Muse/logs/[SESSION_ID]/window[N]/exthost/anysphere.claude-code-retrieval/
```

### Common Log Files
- `MCP Logs.log` - General MCP logging
- `MCP user-[server-name].log` - Individual MCP server logs
- `MCP user-git.log` - Git MCP server
- `MCP user-puppeteer.log` - Puppeteer MCP server

### Alternative Location
```
~/Library/Application Support/Muse/logs/[SESSION_ID]/window[N]/exthost/anysphere.claude-code-always-local/
```

## Diagnostic Process

### 1. Find Current Session Logs
```bash
# Find most recent session
ls -la "~/Library/Application Support/Muse/logs/" | tail -5

# List MCP logs for latest session
find "~/Library/Application Support/Muse/logs/[LATEST_SESSION]" -name "*MCP*"
```

### 2. Check Individual MCP Server Status
```bash
# View specific MCP server log
cat "~/Library/Application Support/Muse/logs/[SESSION]/window[N]/exthost/anysphere.claude-code-retrieval/MCP user-[server-name].log"
```

### 3. Common Error Patterns

#### ENOENT Errors (Command Not Found)
```
Client error for command A system error occurred (spawn npx ENOENT)
```
**Cause**: `npx` or `node` not found in the IDE's PATH
**Solution**: Install Node.js globally or fix PATH environment (see Advanced Environment Fixes)

#### Node Directory Errors
```
env: node: No such file or directory
```
**Cause**: Node.js not accessible to the IDE
**Solution**: Check Node.js installation and environment variables

#### Server Info Missing
```
No server info found
```
**Cause**: MCP server failed to start or communicate
**Solution**: Check server installation and configuration

#### Timeout Pattern (Server Starts but Times Out)
```
Starting new stdio process with command: npx -y git-mcp-server
[1 minute delay]
Client closed for command
No server info found
```
**Cause**: MCP server package installation delay via `npx -y`
**Solution**: Install MCP server packages globally to avoid installation delays

## When User Requests MCP Inspection

### For General MCP Issues
1. **Find current session**: Get the latest timestamp directory
2. **Check all MCP logs**: List and examine all MCP-related log files
3. **Identify patterns**: Look for common error types across servers
4. **Provide summary**: Categorize issues and suggest solutions

### For Specific MCP Server
1. **Locate server log**: Find the specific `MCP user-[server-name].log` file
2. **Analyze errors**: Extract error messages and timestamps
3. **Check dependencies**: Verify if required tools (npx, node) are available
4. **Suggest fixes**: Provide targeted solutions for the specific server

### Summary Format
```
## MCP Server Status Summary

### ✅ Working Servers
- [List successfully loaded servers]

### ❌ Failed Servers
- **[Server Name]**: [Error Type] - [Brief cause]
- **[Server Name]**: [Error Type] - [Brief cause]

### 🔧 Recommended Actions
1. [Priority 1 fix]
2. [Priority 2 fix]
3. [Priority 3 fix]

### 📍 Log Locations
- Main logs: [path]
- Specific issues: [relevant log files]
```

## Environment Diagnostics

### Check Node.js Availability
```bash
# From terminal (what user sees)
which node && which npx
echo "Node: $(node --version)"
echo "NPX: $(npx --version)"

# Check PATH
echo "PATH: $PATH"
echo "NVM_DIR: $NVM_DIR"
```

### Common Solutions

#### PATH Issues
- **Install Node globally**: `brew install node`
- **Fix shell integration**: Add NVM paths to shell profile
- **Restart the IDE**: Close completely and reopen from terminal

#### Permission Issues
- **Check file permissions**: Ensure log files are readable
- **Verify installation**: Confirm MCP servers are properly installed

#### Configuration Issues
- **Update MCP config**: Use full paths instead of relative commands
- **Check server versions**: Ensure compatibility with the IDE version

#### MCP Server Installation Issues
- **Install globally**: `npm install -g git-mcp-server` to avoid npx installation delays
- **Check installation**: `git-mcp-server --help` should start without hanging
- **Verify package availability**: Ensure MCP server packages are accessible

## Usage Examples

When user says "inspect MCP servers":
- Check all MCP logs in current session
- Provide comprehensive status summary
- List failed servers with specific error types
- Suggest prioritized solutions

When user says "inspect git MCP server":
- Focus on `MCP user-git.log` specifically
- Analyze git-specific errors
- Check git-mcp-server installation
- Provide targeted git MCP solutions

## Advanced Environment Fixes

### GUI Application PATH Issues on macOS

When `spawn npx ENOENT` persists despite Node.js being installed:

#### 1. Create System-Wide Symlinks
```bash
# Create symlinks in /usr/local/bin (preferred location)
sudo ln -sf /opt/homebrew/bin/node /usr/local/bin/node
sudo ln -sf /opt/homebrew/bin/npm /usr/local/bin/npm
sudo ln -sf /opt/homebrew/bin/npx /usr/local/bin/npx
```

#### 2. Configure System PATH for GUI Applications
```bash
# Add paths to system-wide PATH for GUI apps
echo '/usr/local/bin' | sudo tee /etc/paths.d/usr-local-bin
echo '/opt/homebrew/bin' | sudo tee /etc/paths.d/homebrew
```

#### 3. Set launchctl Environment
```bash
# Set PATH for GUI applications via launchctl
launchctl setenv PATH "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# Verify it was set
launchctl getenv PATH
```

#### 4. Configure Muse Shell Environment Timeout (Muse-specific)
Add to Muse's `settings.json`:
```json
{
  "application.shellEnvironmentResolutionTimeout": 30
}
```
**Purpose**: Increases time Muse waits to resolve shell environment (default is lower)
**Effect**: Allows more time for shell initialization and environment variable loading

#### 5. Verify Environment Changes
```bash
# Test symlinks work
/usr/local/bin/npx --version

# Test with minimal PATH (simulates Muse environment)
env PATH="/usr/bin:/bin" which npx 2>/dev/null || echo "npx not found in minimal PATH"
```

### Progressive Diagnosis Steps

1. **Check if Muse finds npx**: Look for `spawn npx ENOENT` vs successful `Starting new stdio process`
2. **If npx found but servers timeout**: Install MCP packages globally
3. **If servers start but fail**: Check individual server logs for specific errors

### Multi-Stage Fix Pattern

Many MCP environment issues require combination of:
1. **Environment PATH fixes** (symlinks + launchctl)
2. **Muse timeout configuration** (shellEnvironmentResolutionTimeout)
3. **Package installation fixes** (global npm installs)

### Common Verification Commands
```bash
# Check what Muse environment sees
which -a npx && which -a node
ls -la /usr/local/bin/ | grep -E "node|npx|npm"
launchctl getenv PATH

# Test MCP servers directly
git-mcp-server --help
npm list -g git-mcp-server

# Check Muse settings
grep "shellEnvironmentResolutionTimeout" ~/Library/Application\ Support/Muse/User/settings.json
```

## Implementation Notes

- Always use the most recent session timestamp directory
- Handle multiple window logs (window1, window2, etc.)
- Provide both immediate fixes and long-term solutions
- Include specific log file paths in summaries for user reference
- Apply environment fixes progressively and test between changes
- Remember that GUI applications have different PATH than terminal sessions
