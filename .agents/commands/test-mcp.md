---
description: Generic MCP testing with dynamic tool discovery
---
# MCP Testing Rule - Generic Dynamic Testing

## Purpose
Rapidly test any MCP server during development with isolated, clean environments and dynamic tool discovery. The harness automatically discovers server capabilities and generates appropriate tests without hardcoded knowledge about specific MCP servers.

## When to Use This Rule
- User mentions testing MCP servers
- User wants to verify MCP tool functionality
- User needs to debug MCP server implementations
- User says "@test-mcp" or requests MCP testing

## Core Principles

### 1. **MCP-Agnostic Design**
- No hardcoded knowledge about specific MCP servers (map, etc.)
- Dynamic discovery of available tools and their schemas
- Auto-generation of valid test arguments based on JSON schemas
- Generic test patterns that work with any MCP server

### 2. **Discovery-First Approach**
- Always start by discovering what tools are available
- Inspect tool schemas to understand required arguments
- Generate valid example arguments automatically
- Test tools based on their actual capabilities, not assumptions

### 3. **CLI-Driven Configuration**
- All test specifications passed via CLI arguments
- Support for inline JSON test configurations
- No embedded test knowledge in the harness itself
- Complete flexibility for any MCP server type

### 4. **Isolation-First Testing**
- **CRITICAL**: Never modify the local repository during testing
- All file operations should happen in temporary directories
- Use test fixtures and sample files, not production code
- Preserve repository state - testing must be non-destructive

## Actions When This Rule is Invoked

### 1. **Identify Target MCP Server**
- Ask user for server path if not provided
- Default to most likely server based on context
- Validate server file exists

### 2. **Determine Test Mode**
Ask user to choose (or use default):
- **`discover`**: Show available tools and their schemas with example args
- **`basic`** (default): Smoke test - initialize, list tools, test first tool
- **`tool`**: Test specific tool with provided or auto-generated arguments
- **`comprehensive`**: Test all discovered tools systematically
- **`interactive`**: REPL mode for manual testing

### 3. **Ensure Testing Isolation**
**BEFORE running any tool tests:**
- Create temporary directory for test operations
- Use test fixtures (sample sessions, text files) instead of production files
- For tools requiring file paths, use `/tmp/` or test fixture paths
- **NEVER** pass production repository paths to tools that modify files

### 4. **Execute Test Command**
Run the appropriate test command (all commands auto-build dependencies):

**⚠️ IMPORTANT: Always use absolute paths to avoid path resolution issues**

**⏱️ TIMEOUT REQUIREMENT: Always use --timeout 600000 (10 minutes) for tool tests to handle long-running operations like astra server startup**

**📋 OUTPUT REQUIREMENT: Always provide or meaningfully summarize the actual MCP tool results - never just report "test passed" without showing what the tool returned**

```bash
# Get absolute path (recommended first step)
realpath packages/your-mcp-server/dist/index.js

# Discovery mode - show what's available
mcp-test $(realpath packages/your-mcp-server/dist/index.js) --discover

# Basic smoke test (recommended)
mcp-test $(realpath packages/your-mcp-server/dist/index.js) --basic

# Test specific tool with inline args (ALWAYS include 10-minute timeout, use temp/test files)
mcp-test $(realpath packages/your-mcp-server/dist/index.js) --test-tool "tool_name" --args '{"file_path": "/tmp/sample-session/left.png"}' --timeout 600000

# Test multiple tools with JSON config (ALWAYS include 10-minute timeout)
mcp-test $(realpath packages/your-mcp-server/dist/index.js) --test-config '{"tools": [{"name": "tool1", "args": {...}}]}' --timeout 600000

# Comprehensive testing of all tools (ALWAYS include 10-minute timeout)
mcp-test $(realpath packages/your-mcp-server/dist/index.js) --comprehensive --timeout 600000

# Interactive mode
mcp-test $(realpath packages/your-mcp-server/dist/index.js) --interactive
```

**Alternative: Set absolute path variable**
```bash
# Define server path once
SERVER_PATH=$(realpath packages/your-mcp-server/dist/index.js)

# Then use it
mcp-test $SERVER_PATH --discover
mcp-test $SERVER_PATH --basic
```

### 5. **Report Results**
- Show test execution status
- Highlight any failures with details
- Display discovered tool schemas when relevant
- **Provide or summarize tool output**: Always include actual MCP tool results
- **For large outputs**: Summarize key metrics (e.g., "446 text elements extracted", "3.2MB image rendered")
- **For small outputs**: Include full JSON response or key data
- Provide recommendations for fixes
- Suggest next steps

## Command Templates

### Generic MCP Server Testing
```bash
# Quick discovery (recommended first step)
mcp-test $(realpath packages/mcp-server/dist/index.js) --discover

# Basic smoke test (auto-builds)
mcp-test $(realpath packages/mcp-server/dist/index.js) --basic

# Test specific tool with custom args (auto-builds, 10-minute timeout, safe test file)
mcp-test $(realpath packages/mcp-server/dist/index.js) --test-tool "inspect_structure" --args '{"file_path": "/tmp/sample-session/left.png"}' --timeout 600000

# Test all tools comprehensively (auto-builds, 10-minute timeout)
mcp-test $(realpath packages/mcp-server/dist/index.js) --comprehensive --timeout 600000

# Build test harness only
mcp-test:build
```

### Safe Testing Practices
```bash
# CRITICAL: Always create temporary test files before testing
mkdir -p /tmp/mcp-test
cp tests/fixtures/sample-session/left.png /tmp/mcp-test/
echo "Hello World Test" > /tmp/mcp-test/sample.txt

# Use temporary paths in all tool arguments
mcp-test $SERVER_PATH --test-tool "extract_detections" --args '{"session_path": "/tmp/mcp-test/sample-session"}' --timeout 600000

# For tools that create files, ensure they write to temp locations
mcp-test $SERVER_PATH --test-tool "create_report" --args '{"output_path": "/tmp/mcp-test/output.txt"}' --timeout 600000

# NEVER use production repo paths for tools that modify files
# ❌ BAD: --args '{"file_path": "packages/important-package/src/index.ts"}'
# ✅ GOOD: --args '{"file_path": "/tmp/mcp-test/sample.ts"}'
```

### Path Resolution Helpers
```bash
# Check if server file exists
ls -la $(realpath packages/your-mcp-server/dist/index.js)

# Get absolute path from any directory
SERVER_PATH=$(realpath packages/your-mcp-server/dist/index.js)
echo "Server path: $SERVER_PATH"

# Alternative if realpath not available (macOS/Linux)
SERVER_PATH=$(cd packages/your-mcp-server/dist && pwd)/index.js

# Windows (if using Git Bash)
SERVER_PATH=$(cygpath -w "$(realpath packages/your-mcp-server/dist/index.js)")
```

### Development Workflow Integration
```bash
# Set server path variable for convenience
SERVER_PATH=$(realpath packages/your-mcp-server/dist/index.js)

# After implementing a feature - discover capabilities
mcp-test $SERVER_PATH --discover

# Test new tool specifically (10-minute timeout)
mcp-test $SERVER_PATH --test-tool "new_tool_name" --args '{"param": "value"}' --timeout 600000

# Before committing changes (10-minute timeout)
mcp-test $SERVER_PATH --comprehensive --timeout 600000

# Debug failing tool with verbose output (10-minute timeout)
mcp-test $SERVER_PATH --test-tool "failing_tool" --debug --verbose --timeout 600000
```

## Expected User Interactions

### User Says: "@test-mcp"
**Response**:
```
I'll test the MCP server for you safely without modifying your repository. Let me start with discovery.

Setting up safe testing environment:
mkdir -p /tmp/mcp-test
SERVER_PATH=$(realpath packages/your-mcp-server/dist/index.js)
mcp-test $SERVER_PATH --discover

This will show all available tools and their required arguments. Any file operations will use /tmp/mcp-test/ to avoid repository changes.
```

### User Says: "@test-mcp inspect_session_structure"
**Response**:
```
Testing the inspect_session_structure tool safely with a temporary test file. Let me discover its schema and run the test.

Setting up safe test environment:
mkdir -p /tmp/mcp-test
cp tests/fixtures/sample-session/left.png /tmp/mcp-test/

Commands:
SERVER_PATH=$(realpath packages/your-mcp-server/dist/index.js)
1. mcp-test $SERVER_PATH --discover
2. mcp-test $SERVER_PATH --test-tool "inspect_session_structure" --args '{"session_path": "/tmp/mcp-test/sample-session"}' --timeout 600000
```

### User Says: "@test-mcp [server-path]"
**Response**:
```
Testing MCP server safely with basic smoke test and tool discovery:

Setting up isolated test environment:
mkdir -p /tmp/mcp-test
SERVER_PATH=$(realpath [server-path])
1. mcp-test $SERVER_PATH --discover
2. mcp-test $SERVER_PATH --basic

All tests will use temporary files to avoid modifying your repository.
```

## Error Handling

### If mcp-test-harness package doesn't exist:
```
❌ MCP Test Harness not found!

The testing infrastructure needs to be set up first:
1. Create common-testing/mcp-test-harness/ package
2. Implement the test runner according to docs/<area>/mcp-test-harness.md
3. Install dependencies: uv sync --group dev
4. Add test-mcp scripts to root package.json

Would you like me to help set up the test harness?
```

### If server path doesn't exist:
```
❌ MCP Server not found: [path]

Common path resolution issues:
1. Using relative paths instead of absolute paths
2. Test harness running from different working directory
3. Server not built (missing dist/ files)

Quick fixes:
# 1. Always use absolute paths and setup safe testing
mkdir -p /tmp/mcp-test
SERVER_PATH=$(realpath packages/your-mcp-server/dist/index.js)
mcp-test $SERVER_PATH --discover

# 2. Check if file actually exists
ls -la $(realpath packages/your-mcp-server/dist/index.js)

# 3. Build server if missing
cd packages/your-mcp-server && uv run pytest -q

# 4. Find available MCP servers in repo
find . -name "index.js" -path "*/dist/*" | grep -E "(mcp|server)"

# 5. CRITICAL: Setup test files before testing tools that require files
cp {common,common-testing,mapping-pipeline,onboard-detection,surmap,packages}/*/public/example-*/* /tmp/mcp-test/ 2>/dev/null || true

Available MCP servers in this repo:
[List discovered .ts/.js files that might be MCP servers]
```

### If tool discovery fails:
```
❌ Tool Discovery Failed

Issues found:
- Server failed to initialize
- No tools found or tools/list failed
- Invalid tool schemas returned

Recommendations:
1. Check server implementation
2. Verify MCP protocol compliance
3. Run with --debug for detailed logs

Next steps: mcp-test [server-path] --basic --debug
```

### If tool test fails:
```
❌ Tool Test Failed: [tool-name]

Issues found:
- [specific error details]
- Arguments used: [actual arguments]
- Expected schema: [tool schema]

Recommendations:
1. Check tool implementation
2. Verify argument validation
3. Test with different arguments

Next steps: mcp-test [server-path] --test-tool "[tool-name]" --args '{...}' --debug
```

## Integration with Development Workflow

### Discovery-First Development
```
Great! Let's safely discover what tools your MCP server provides:

Setting up isolated test environment:
mkdir -p /tmp/mcp-test
SERVER_PATH=$(realpath packages/your-mcp-server/dist/index.js)
mcp-test $SERVER_PATH --discover

This will show all available tools, their descriptions, and example arguments. Any testing will use /tmp/mcp-test/ to protect your repository.
```

### After Implementing New Tool
```
Perfect! You've implemented [tool-name]. Let's test it safely:

Setting up test environment:
mkdir -p /tmp/mcp-test
# Copy any needed test files here
SERVER_PATH=$(realpath packages/your-mcp-server/dist/index.js)
1. First, let's see its schema: mcp-test $SERVER_PATH --discover
2. Then test it safely: mcp-test $SERVER_PATH --test-tool "[tool-name]" --args '{"session_path": "/tmp/mcp-test/sample-session"}' --timeout 600000
```

### Before Committing
```
Before committing, let's run comprehensive tests on all tools safely:

Setting up comprehensive test environment:
mkdir -p /tmp/mcp-test
cp {common,common-testing,mapping-pipeline,onboard-detection,surmap,packages}/*/public/example-*/* /tmp/mcp-test/ 2>/dev/null || true

SERVER_PATH=$(realpath packages/your-mcp-server/dist/index.js)
mcp-test $SERVER_PATH --comprehensive --timeout 600000

This will test every discovered tool with auto-generated valid arguments using temporary files only.
```

### During Debugging
```
To debug the [tool-name] issue safely:

Setting up debug environment:
mkdir -p /tmp/mcp-test
# Copy relevant test files for debugging
SERVER_PATH=$(realpath packages/your-mcp-server/dist/index.js)
1. Discover the schema: mcp-test $SERVER_PATH --discover
2. Test with debug logs: mcp-test $SERVER_PATH --test-tool "[tool-name]" --args '{"session_path": "/tmp/mcp-test/sample-session"}' --debug --verbose --timeout 600000
3. Try interactive mode: mcp-test $SERVER_PATH --interactive
```

## Output Interpretation

### Successful Discovery Output
```
✅ MCP Server Discovery Results

📊 Server Info:
- Name: example-mcp-server
- Protocol Version: 1.0.0
- Capabilities: [list]

🛠️ Available Tools (3):
1. tool_one
   Description: Does something useful
   Arguments: {"file_path": "string", "options": "object"}
   Example: {"file_path": "sample-session/left.png", "options": {}}

2. tool_two
   Description: Another useful tool
   Arguments: {"input": "string"}
   Example: {"input": "sample text"}

💡 Next steps:
- Test specific tool: mcp-test $SERVER_PATH --test-tool "tool_one" --args '{...}'
- Test all tools: mcp-test $SERVER_PATH --comprehensive
```

### Successful Test Output
```
✅ MCP Test Results

📊 Summary:
- Initialized: ✅
- Tools Discovered: ✅ (3 tools found)
- tool_one: ✅ (120ms)
- tool_two: ✅ (85ms)

🎉 All tests passed! Server is working correctly.

💡 Next steps:
- Continue development
- Run comprehensive suite before committing
```

### Large Output Handling Example
```
✅ MCP Test Results - extract_detections_with_ocr

📊 Performance Metrics:
- Reconstruction: 1,050ms (session fixtures loaded)
- OCR Processing: 4,988ms (tesseract.js extraction)
- Total Time: 6,039ms

📝 OCR Results Summary:
- Text Elements Extracted: 446 individual words
- Average Confidence: 96%+ (high accuracy)
- Sample Text: "Lorem", "ipsum", "dolor", "sit", "amet", "consectetur"...
- Coordinate System: map frame (metres) with precise centroids

🔍 Example Element:
{
  "text": "lorem",
  "confidence": 0.9633,
  "bounding_box": {"x": 1353, "y": 2628, "width": 129, "height": 38}
}

✅ Complete pipeline validated: session → reconstruction → segmentation → 446 object points extracted
```

### Failed Test Output
```
❌ MCP Test Results

📊 Summary:
- Initialized: ✅
- Tools Discovered: ✅ (3 tools found)
- tool_one: ❌ Invalid arguments
- tool_two: ⏭️ Skipped due to dependency

🔍 Failure Details:
tool_one: Argument 'file_path' is required but was not provided
  Schema: {"file_path": {"type": "string", "description": "Path to file"}}
  Provided: {}

🛠️ Recommended Actions:
1. Check tool argument validation
2. Update test with required arguments
3. Verify schema matches implementation

💡 Quick fix command:
SERVER_PATH=$(realpath packages/your-mcp-server/dist/index.js)
mcp-test $SERVER_PATH --test-tool "tool_one" --args '{"file_path": "sample-session/left.png"}' --debug
```

## Best Practices

### 1. **Repository Safety First (CRITICAL)**
- **NEVER** modify files in the production repository during testing
- Always create `/tmp/mcp-test/` directory for test operations
- Use test fixtures and sample files, not production code
- Verify all file paths point to temporary locations before testing

### 2. **Always Discover First**
- Start with `--discover` to understand capabilities
- Never assume what tools are available
- Use discovered schemas to generate valid tests
- Respect the actual tool implementations

### 3. **Use Safe Test Arguments**
- Let the harness generate valid arguments from schemas
- Override with specific values when testing edge cases
- **ALWAYS** use `/tmp/mcp-test/` paths for file operations
- Copy test fixtures to temp directory before testing

### 4. **Test Incrementally**
- Start with basic smoke test
- Test individual tools during development
- Run comprehensive tests before commits
- Use interactive mode for exploration

### 5. **Leverage Generic Patterns**
- The harness works with any MCP server
- No need for server-specific knowledge
- Focus on MCP protocol compliance
- Reuse patterns across different servers

### 6. **Handle Test Output Appropriately**
- **Always provide results**: Never just say "test passed" without showing what happened
- **Large outputs**: Summarize key metrics and show representative samples
- **Small outputs**: Include complete results or key data points
- **Performance data**: Always include timing information when available
- **Validation metrics**: Show confidence scores, element counts, file sizes, etc.
- **Representative samples**: For data extraction tools, show example extracted elements

---

## Critical Safety Summary

**🛡️ REPOSITORY PROTECTION IS MANDATORY**

1. **✅ ALWAYS DO**: Create `/tmp/mcp-test/` for all file operations
2. **✅ ALWAYS DO**: Copy test fixtures to temp directory before testing
3. **✅ ALWAYS DO**: Use `/tmp/mcp-test/` paths in all tool arguments
4. **❌ NEVER DO**: Pass production file paths to tools that modify files
5. **❌ NEVER DO**: Test with important repository files as targets

**Example Safe Testing Flow**:
```bash
# 1. Setup safe environment
mkdir -p /tmp/mcp-test
cp {common,common-testing,mapping-pipeline,onboard-detection,surmap,packages}/*/public/example-*/* /tmp/mcp-test/ 2>/dev/null || true

# 2. Test safely
SERVER_PATH=$(realpath packages/mcp-server/dist/index.js)
mcp-test $SERVER_PATH --test-tool "process_file" --args '{"session_path": "/tmp/mcp-test/sample-session"}' --timeout 600000

# 3. Repository remains unchanged ✅
```

This rule enables rapid, isolated MCP testing with dynamic discovery that works with any MCP server implementation while providing clear, actionable feedback and maintaining complete separation from repository state.