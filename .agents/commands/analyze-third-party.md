---
description: Analyze third-party projects for structure and issues
---
## Analyze Third-Party Project

This command enables comprehensive analysis of external projects.

**For technology stack decisions, see `.agents/skills/tech-stack/references/tech-stack.md` rule.**

## Input Handling

### Git Repository Analysis
Clone to tmp directory:
```bash
git clone <url> tmp/<project-name>
```
Use project name from URL as directory name.

### Local Directory Analysis
- Verify path exists and is accessible
- Use provided path directly

## Analysis Workflow

### 1. Initial Discovery

**List root directory:**
```bash
ls -la <project-path>
```

**Identify key files:**
- `pyproject.toml` - Python projects
- `Cargo.toml` - Rust projects
- `requirements.txt` - Python projects
- `go.mod` - Go projects

**Read README:**
- Project overview
- Setup instructions
- Known issues

**Examine config files:**
- CI/CD configurations
- Build tools
- Test frameworks

### 2. Dependency Analysis

**Parse dependency files:**
- External libraries used
- Version constraints
- Potential conflicts
- Deprecated dependencies
- Security vulnerabilities

**Separate analysis:**
- Production dependencies
- Development dependencies
- Build dependencies

### 3. Code Quality Assessment

**Code Structure:**
- Source organization
- Architectural patterns
- Separation of concerns
- Test coverage and structure

**Potential Issues:**
- Common anti-patterns
- Error handling approaches
- Security vulnerabilities
- Performance bottlenecks

### 4. Technology Stack Analysis

**Framework/Language Specific:**

**Python/C++ (the shape SurMap meets in SLAM and vision libraries):**
- Check `tsconfig.json`
- Identify build tools
- Examine testing frameworks

**Rust:**
- Examine `Cargo.toml`
- Workspace structure
- Feature flags

**Python:**
- Check `requirements.txt`
- Virtual environment setup

**CI/CD and Deployment:**
- GitHub Actions, GitLab CI, etc.
- Docker configurations
- Deployment scripts

### 5. Environment and Compatibility

**Common CI/CD Problems:**
- Missing system dependencies
- Environment variable requirements
- Platform-specific issues (Linux/macOS/Windows)
- Version compatibility problems

**Build and Runtime Issues:**
- Compilation dependencies
- Runtime library requirements
- Font and system resources (map/image processing)
- Network access requirements

### 6. Specific Issue Analysis

**For issues like "0-byte outputs in CI":**
1. Compare CI vs local environment setup
2. Check system dependency installation in CI
3. Examine error handling in core functionality
4. Look for silent failures in stream/file operations
5. Check environment-specific resource requirements

## Report Structure

```markdown
## 📊 Third-Party Project Analysis

### Project Overview
- **Name**: [project-name]
- **Source**: [git URL | local path]
- **Type**: [Python/C++/Rust/etc.]
- **Purpose**: [main purpose]

### Technology Stack
- **Language**: [primary language and version]
- **Framework**: [main framework]
- **Build Tool**: [webpack/cargo/etc.]
- **Test Framework**: [jest/vitest/etc.]

### Architecture
**High-Level Structure:**
- Source: `src/` or `lib/`
- Tests: `tests/` or `__tests__/`
- Configuration: [list key configs]

**Patterns Identified:**
- [Architectural pattern 1]
- [Pattern 2]

### Dependencies

#### Production Dependencies
- dependency1: ^version (notes)
- dependency2: ^version (notes)

#### Development Dependencies
- dev-dependency1: ^version

**Issues Identified:**
- ⚠️ dependency-X is deprecated
- 🔴 security-vulnerability in dependency-Y

### Issues Found

#### 🔴 Critical
- **Issue 1**: Description
  - File: `path/to/file.ts:line`
  - Impact: [description]
  - Solution: [recommendation]

#### ⚠️ Warnings
- **Issue 1**: Description
  - Solution: [recommendation]

#### ℹ️ Info
- **Observation 1**: [description]

### Code Quality

**Strengths:**
- [Positive aspect 1]
- [Positive aspect 2]

**Areas for Improvement:**
- [Issue 1]
- [Issue 2]

### CI/CD Analysis

**CI Configuration**: [GitHub Actions | GitLab CI | etc.]

**Potential Issues:**
- Missing system dependencies
- Environment-specific problems
- [Other issues]

### Recommendations

1. **High Priority**:
   - Recommendation 1
   - Recommendation 2

2. **Medium Priority**:
   - Recommendation 3

3. **Nice to Have**:
   - Recommendation 4

### Integration Considerations

**To integrate this project:**
1. Step 1
2. Step 2
3. Dependencies to add to our project

**Potential Conflicts:**
- [Conflict 1]
- [Conflict 2]

### References
- README: [path]
- Documentation: [URLs]
- Issues found: [specific references with line numbers]
```

## Output Format Examples

**Python Project (worked example: evaluating a SLAM/vision library):**
```markdown
### Technology Stack
- **Language**: Python 3.11+ with a C++ native core
- **Framework**: none — a library with a native binding, like RTAB-Map
- **Build Tool**: uv
- **Test Framework**: pytest

### Dependencies
**Production:**
- numpy: ^1.26
- (native binding provided by the system install, not PyPI)

**Issues:**
- ⚠️ Using deprecated enzyme for testing
- 🔴 Security vulnerability in dependency X
```

**Rust Project:**
```markdown
### Technology Stack
- **Language**: Rust 1.75
- **Build System**: Cargo
- **Workspace**: Multi-crate workspace

### Dependencies (Cargo.toml)
**Production:**
- tokio = "1.35"
- serde = "1.0"

**Issues:**
- ⚠️ Some dependencies have newer versions available
```

## Best Practices

✅ **Do:**
- Clone to tmp directory for git repos
- Analyze all key configuration files
- Identify security vulnerabilities
- Check for deprecated dependencies
- Compare CI vs local environment
- Provide specific file references with line numbers
- Categorize issues (Critical/Warning/Info)

❌ **Don't:**
- Don't clone to production directories
- Don't skip dependency analysis
- Don't ignore CI/CD configurations
- Don't provide vague recommendations
- Don't skip README examination

## Related

**Rules**: `.agents/skills/tech-stack/references/tech-stack.md`
