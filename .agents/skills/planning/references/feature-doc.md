---
description:
---
## Feature Documentation Standards

## Purpose

1. Feature documents contain **high-level product requirements** with minimal technical implementation details
2. They serve as a **meeting point** between Product Manager, UX, Developer, and LLM assistant
3. Feature documents are **organized by product area** under `docs/<area>/`
4. Each document includes **acceptance criteria** with checked (completed) and unchecked (remaining) tasks

## Product vs Technical Product

### Product (End-User Facing)
**Definition**: Applications or services that end users directly interact with.

**Characteristics**:
- Has a user interface (web, desktop, mobile)
- Solves user problems directly
- Measured by user engagement and satisfaction
- UX and design are critical

**Examples**:
- **Base station**: the workstation application that builds the semantic map from sessions
- **Dashboard**: Admin interface for managing documents

### Technical Product (Developer/System Facing)
**Definition**: APIs, SDKs, libraries, or tools that developers or systems consume.

**Characteristics**:
- No direct end-user UI (or minimal dev-facing UI)
- Provides capabilities to other systems/developers
- Measured by API adoption, performance, reliability
- Developer experience (DX) and documentation are critical

**Categories**:

#### 1. **APIs** (Application Programming Interfaces)
- Expose service capabilities via HTTP/gRPC/other protocols
- Consumed by other applications or services
- **Example**: `mapping-pipeline-server` provides map processing API
- **Example**: `gotenberg-api` provides document conversion API

#### 2. **Libraries/SDKs** (Software Development Kits)
- Embedded into other applications
- Provide reusable functionality
- **Example**: `stereo-ingest` is a WASM library for map parsing
- **Example**: `surmap` NPM package

#### 3. **Tools** (Developer Tools)
- Help developers build, test, or debug
- Improve development workflow
- **Example**: MCP servers for map inspection
- **Example**: Test harness for E2E testing

#### 4. **Infrastructure** (Platform Services)
- Cross-cutting concerns
- Support multiple products/services
- **Example**: Logging, observability, BI tracking

### Documentation Focus Shift

**For Products** (User-Facing):
- Focus on **user stories** and **user workflows**
- Emphasize UX/UI requirements
- Success metrics: user satisfaction, engagement, conversion
- Feature: "User can drag signature onto document"

**For Technical Products** (Developer/System-Facing):
- Focus on **API contracts** and **integration patterns**
- Emphasize developer experience (DX)
- Success metrics: adoption, performance, reliability, error rates
- Feature: "API endpoint accepts multipart upload with retry support"

### Key Distinction: Server vs API

❌ **WRONG**: "mapping-pipeline-server is a product"
✅ **CORRECT**: "mapping-pipeline-server API is a technical product (the API consumers use)"

**The server is infrastructure, the API is the product.**

**Example**:
- Directory: `docs/<area>/mapping-pipeline-server/` (named after implementation)
- 1-OVERVIEW.md title: "semantic mapping pipeline Server API" (product name)
- Features describe: API endpoints, integrations, data contracts

## Documentation Structure

### Product Area Organization

All feature documentation is organized by product area:

```
docs/<area>/
├── base-station/        # PRODUCT: semantic map building from sessions
│   ├── 1-OVERVIEW.md          # Title: "semantic mapping pipeline Editor"
│   ├── changelog/           # One file per wrapped PRD: YYYY-MM-DD-short-description.md
│   ├── appendices/          # Technical specs, diagrams, assets
│   ├── 1-WIP/              # Feature PRD documents
│   └── *.md                 # User-facing features (signature tools, etc.)
│
├── mapping-pipeline-api/           # 🔌 TECHNICAL PRODUCT (API): Domain map API
│   ├── 1-OVERVIEW.md          # Title: "semantic mapping pipeline API"
│   ├── appendices/          # API specs, proto definitions
│   ├── 1-WIP/
│   └── *.md                 # API features (endpoints, integrations)
│
├── stereo-ingest/       # 📚 TECHNICAL PRODUCT (Library): map Native Parser
│   ├── 1-OVERVIEW.md          # Title: "map Native Parser Library"
│   ├── appendices/          # Parser specs, WASM details
│   ├── 1-WIP/
│   └── *.md                 # Library features (parsing, revisions, etc.)
│
├── gotenberg-api/           # 🔌 TECHNICAL PRODUCT (API): Document Conversion API
│   ├── 1-OVERVIEW.md          # Title: "Gotenberg API"
│   ├── appendices/          # API specs, conversion formats
│   ├── 1-WIP/
│   └── *.md                 # API features (conversion endpoints)
│
├── mcp-servers/             # 🛠️ TECHNICAL PRODUCT (Tools): MCP Development Tools
│   ├── 1-OVERVIEW.md          # Title: "MCP Servers"
│   ├── appendices/          # MCP protocol specs
│   ├── 1-WIP/
│   └── *.md                 # Tool features (inspection, testing)
│
└── infrastructure/          # 🏗️ TECHNICAL PRODUCT (Platform): Cross-Cutting Services
    ├── 1-OVERVIEW.md          # Title: "Infrastructure Services"
    ├── appendices/          # Platform specs
    ├── 1-WIP/
    └── *.md                 # Platform features (logging, BI)
```

### Directory Purposes

#### 1-OVERVIEW.md
- High-level product area description
- Core capabilities summary
- Target users and use cases
- Links to all feature documents in the area
- Integration points with other product areas
- One link to the product area `changelog/` **directory** — never to an entry inside it
- No link to anything in `1-WIP/` — not a PRD, not a changeset, not a discovery companion
  (`docs/AGENTS.md` § *Nothing links into `1-WIP/`*)

#### changelog/
- **Change History** for all features in the product area
- Tracks requirement changes and PRDs applied
- One file per wrap: `YYYY-MM-DD-short-description.md`
- Release note-style summaries (no file references to deleted PRDs)
- **Terminal — nothing links in.** No stable document (`1-OVERVIEW.md`, a feature doc, an
  `README.md`, a `README.md`) may reference an individual entry: no `See [changelog/…](…)`
  trailer, no `**Implementation**: see [changelog](…)` line, no `([changelog](…))` parenthetical,
  no "Change History" list of entries, and no **bare path in backticks** — the test is what the
  reference points at, not how it is spelled. An entry records one dated delta and is never revised, so a
  link from a document that states current behaviour goes stale the moment a later entry
  supersedes it. If a fact still matters, write the fact into the stable doc in State B. Links run
  one way: an entry may cite PRs, stable docs and other entries freely
- See [the PRD guide](/.agents/skills/pr-lifecycle/references/prd.md) for format and guidelines

#### appendices/
- Technical specifications
- Architecture diagrams
- Research documents
- Architecture diagrams and rendered map snapshots
- Reference materials
- Assets (images, sessions, etc.)

#### 1-WIP/
- **Feature PRD documents** (requirement updates)
- **Unreferenced from outside** — no stable document links into `1-WIP/`; it is found by listing it
- **See**: [the PRD guide](/.agents/skills/pr-lifecycle/references/prd.md) for complete PRD document structure and requirements

#### Feature Documents (*.md)
- Individual feature specifications
- Product requirements
- User stories and acceptance criteria
- Success metrics

## Feature Document Template

### Template Selection

**For PRODUCTS (End-User Facing)**: Use the **User-Focused Template** below
**For TECHNICAL PRODUCTS (APIs, Libraries, Tools)**: Use the **Developer-Focused Template** below

---

### User-Focused Template (Products)

Use this for: **mapping-pipeline-editor** and other end-user applications.

```markdown
# [Feature Name]

## Overview
Brief description of the feature (2-3 sentences).

## Business Context

### Problem Statement
What problem does this feature solve for end users?

### Target Users
- **User Type 1**: Description
- **User Type 2**: Description

### Success Metrics
- **Metric 1**: Target value (e.g., user engagement, task completion time)
- **Metric 2**: Target value

## Feature Requirements

### Core Functionality
List of main user-facing capabilities with brief descriptions.

### User Experience Requirements
How should users interact with this feature? What's the UX flow?

## Feature Requirements

### Core Functionality
List of main capabilities with brief descriptions.

### User Experience Requirements
How should users interact with this feature?

## Technical Requirements

### Architecture
High-level technical approach (no implementation details).

### Performance Constraints
Expected performance targets.

### Security Requirements
Security considerations.

## User Stories

### Primary Use Cases

#### Story 1: [Title]
**As a** [user type]
**I want to** [action]
**So that** [benefit]

**Acceptance Criteria:**
- [ ] Criterion 1
- [ ] Criterion 2
- [ ] Criterion 3

## Constraints and Limitations

### Scope Limitations
What is explicitly NOT included.

### Technical Constraints
Known technical limitations.

## Implementation Phases

### Phase 1: [Name]
**Status**: ✅ Complete | 🚧 In Progress | 📋 Planned
**Duration**: X weeks
**Scope**: Brief description

- [ ] Task 1
- [ ] Task 2

## Success Criteria

### Functional Requirements
- [ ] Requirement 1
- [ ] Requirement 2

### Performance Requirements
- [ ] Requirement 1
- [ ] Requirement 2

## Related Documentation
- [Link to related feature]
- [Link to technical doc]
```

---

### Developer-Focused Template (Technical Products)

Use this for: **mapping-pipeline-api**, **stereo-ingest**, **gotenberg-api**, **mcp-servers**, **infrastructure**.

```markdown
# [Feature Name]

## Overview
Brief description of the API/library/tool feature (2-3 sentences).

## Technical Context

### Problem Statement
What technical problem does this feature solve? What developer need does it address?

### Target Consumers
- **Consumer Type 1**: (e.g., the semantic map, exported map layers)
- **Consumer Type 2**: Description
- **Integration Points**: Where/how is this consumed?

### Success Metrics
- **Performance**: Target latency, throughput
- **Reliability**: Target uptime, error rate
- **Adoption**: Usage metrics, integration count

## API/Library Requirements

### Core Capabilities
List of main API endpoints, library functions, or tool features.

### Developer Experience (DX) Requirements
- API contract clarity
- Error handling patterns
- Documentation completeness
- Integration ease

## Technical Requirements

### API Contract (for APIs)
- Request/response schemas
- Authentication/authorization
- Rate limiting
- Versioning strategy

### Library Interface (for Libraries)
- Public API surface
- Type definitions
- Export patterns
- Bundling requirements

### Tool Capabilities (for Tools)
- Commands/operations available
- Input/output formats
- Configuration options

### Architecture
High-level technical approach.

### Performance Constraints
Expected performance targets (latency, throughput, resource usage).

### Integration Patterns
How do consumers integrate with this feature?

## Integration Examples

### Example 1: [Consumer Type]
```
[Code example or API call example]
```

### Example 2: [Consumer Type]
```
[Code example or integration pattern]
```

## API/Contract Specification

### Endpoints (for APIs)
- `POST /endpoint`: Description
- `GET /endpoint/{id}`: Description

### Functions (for Libraries)
- `functionName(params)`: Description
- `exportedClass`: Description

### Commands (for Tools)
- `/command`: Description
- `tool-operation`: Description

## Acceptance Criteria

### Functional Requirements
- [ ] API endpoint returns correct schema
- [ ] Library function handles edge cases
- [ ] Tool operation completes successfully

### Performance Requirements
- [ ] Response time < Xms at p95
- [ ] Library memory usage < X MB
- [ ] Tool operation throughput > X ops/sec

### Integration Requirements
- [ ] Consumer application successfully integrates
- [ ] Error handling tested
- [ ] Documentation complete

## Testing Strategy

### Integration Testing
How will consumers test their integration?

### Performance Testing
Load testing, benchmark criteria

## Related Documentation
- [API Reference](./appendices/api-reference.md)
- [Integration Guide](./appendices/integration-guide.md)
- [Related technical doc]
```

---

### Optional Sections (Both Templates)

- **Risks and Mitigation**: Known risks and mitigation strategies
- **Dependencies**: External dependencies
- **Testing Strategy**: High-level testing approach
- **Monitoring and Observability**: How to monitor the feature
- **PRDs**: Historical record of PRDs applied to this feature (see [the PRD guide](/.agents/skills/pr-lifecycle/references/prd.md))

## Acceptance Criteria Format

Use checkboxes to track completion:

```markdown
## Acceptance Criteria

### Functional Requirements
- ✅ **Completed requirement**: Description
- 🚧 **In progress requirement**: Description
- ❌ **Blocked requirement**: Description (reason)
- [ ] **Pending requirement**: Description
```

### Status Indicators
- ✅ Complete
- 🚧 In Progress
- ❌ Blocked/Failed
- 📋 Planned
- ⏳ Pending
- ⚠️ Warning/Issue

## PRDs Section Format

**Purpose**: Track the history of PRDs applied to a feature document.

**Full Documentation**: See [the PRD guide](/.agents/skills/pr-lifecycle/references/prd.md) for complete PRD section format, guidelines, examples, and benefits.

## Asset Management

### Where to Place Assets

1. **Product area appendices**: `docs/{product-area}/appendices/`
2. **Shared assets**: `docs/{product-area}/appendices/assets/`

### Asset Types
- Architecture diagrams and rendered map snapshots
- Architecture diagrams
- Flowcharts
- Screenshots
- Sample sessions
- Technical specifications
- Detailed implementation docs

### Referencing Assets

**CRITICAL RULE**: Every file in `appendices/` MUST be referenced in at least one of:
1. A feature document (in Overview, Related Documentation, or inline)
2. The product area 1-OVERVIEW.md (in an Appendices section)

Use relative paths from the feature document:

```markdown
![Architecture Diagram](./appendices/architecture.png)
[Technical Spec](./appendices/technical-spec.md)
```

### Reference Patterns

**Pattern 1: In Overview Section**
```markdown
## Overview

Brief feature description.

> **📋 Technical Specification**: For detailed implementation, see [Technical Spec](./appendices/technical-spec.md)
```

**Pattern 2: In Related Documentation**
```markdown
## Related Documentation

### Technical Specifications
- **Technical Spec**: [Implementation Details](./appendices/technical-spec.md) - Detailed proto definitions and data flows
```

**Pattern 3: In Product Area 1-OVERVIEW.md**
```markdown
### Appendices

Technical specifications and supporting documentation:

- **[Technical Spec](./appendices/technical-spec.md)** - Description of contents
- **[Architecture Diagram](./appendices/architecture.png)** - System architecture
```

**Example Pattern**: A feature document might reference `appendices/technical-spec.md` in both the Overview section and Related Documentation section for comprehensive coverage.

## PRD Document Workflow

**Full Documentation**: See [the PRD guide](/.agents/skills/pr-lifecycle/references/prd.md) for:
- When to create a PRD document
- Complete PRD document template
- PRD lifecycle and wrapping process
- Multi-feature PRD guidelines
- Preserving history and best practices

## Best Practices

### Do's ✅
- Keep feature documents focused on **product requirements**, not implementation
- Use clear, concise language
- Include visual aids (diagrams, mockups) in appendices
- Update acceptance criteria as work progresses
- Link to related features and technical documentation
- Create PRD documents for requirement updates (see [the PRD guide](/.agents/skills/pr-lifecycle/references/prd.md))
- Place features in the correct product area

### Don'ts ❌
- Don't include implementation details (code, algorithms)
- Don't modify original feature documents when requirements change (use PRDs instead)
- Don't create features in the root `docs/<area>/` directory
- Don't skip acceptance criteria
- Don't forget to update 1-OVERVIEW.md when adding new features
- Don't mix product areas

## Product Area Guidelines

Product areas should be organized by logical product groupings. Each product area should have a clear type classification.

### Creating Product Areas

**For Products (End-User Facing)**:
- **Type**: End-User Application (Web, Desktop, Mobile, Editor Module)
- **Focus**: User-facing features and workflows
- **Examples**: Editing tools, generation workflows, asset management, UI components
- **Success Metrics**: User engagement, feature adoption, task completion time, satisfaction
- **Documentation Style**: User stories, UX flows, interaction patterns

**For Technical Products (APIs)**:
- **Type**: API (REST, gRPC, GraphQL)
- **Focus**: API endpoints, integration patterns, data contracts
- **Examples**: CRUD operations, async processing, webhooks, batch operations
- **Success Metrics**: API response time, uptime, error rate, throughput
- **Documentation Style**: API contracts, integration guides, data schemas
- **Note**: Use domain-driven naming (e.g., "map API" not "map Server API")

**For Technical Products (Libraries/SDKs)**:
- **Type**: Library, SDK, NPM Package, WASM Module
- **Focus**: Reusable functionality, API surface, integration patterns
- **Examples**: Parsing, transformation, validation, utility functions
- **Success Metrics**: Adoption rate, performance, memory usage, bundle size
- **Documentation Style**: API reference, integration guides, capability matrix
- **Note**: Libraries are consumed by other products

**For Technical Products (Tools)**:
- **Type**: Developer Tools, CLI, MCP Servers, Test Harnesses
- **Focus**: Development workflows, automation, debugging
- **Examples**: Inspection tools, generators, test utilities, development proxies
- **Success Metrics**: Developer productivity, tool adoption, debugging efficiency
- **Documentation Style**: Tool capabilities, usage guides, command reference

**For Technical Products (Platform/Infrastructure)**:
- **Type**: Platform Services, Infrastructure, Observability
- **Focus**: Cross-cutting concerns, foundational services
- **Examples**: Logging, monitoring, event tracking, authentication, storage
- **Success Metrics**: System reliability, coverage, uptime, data accuracy
- **Documentation Style**: Platform capabilities, integration patterns, SLAs

## Related Rules and Commands

**Related Rules**:
- [the PRD guide](/.agents/skills/pr-lifecycle/references/prd.md) - PRD document structure and workflow for tracking requirement changes
- [dev-doc.mdc](/.agents/skills/planning/references/dev-doc.md) - Development documentation (HOW to build) that implements these feature requirements
- [the changeset structure](/.agents/skills/pr-lifecycle/references/changeset.md) - Technical changes documentation

**Related Commands**:
- `/plan-ft` - Creates feature or PRD document
- `/plan-ft-dev` - Creates changeset document from feature/PRD
- `/wrap-context-docs` - Applies PRDs to feature docs and archives them
- `/requirements-change` - Guides decision on PRD vs direct update

**Workflow Integration**:
```
Feature requirement change → PRD → Changeset → Implementation → Wrap → Updated docs
```

## Examples

### Example 1: Product Feature (End-User)
**Type**: Product (User-Facing)
**File**: `docs/<area>/my-editor/watermark-feature.md` *(example path)*
**Template**: User-Focused Template
**Assets**: `docs/<area>/my-editor/appendices/watermark-mockup.png`
**Focus**: User stories, UX flows, visual design
**Success Metrics**: User engagement, task completion time
**Update**: Add reference in `docs/<area>/my-editor/1-OVERVIEW.md`

### Example 2: Technical Product Feature (API)
**Type**: Technical Product (API)
**File**: `docs/<area>/my-api/upload-endpoint.md` *(example path)*
**Template**: Developer-Focused Template
**Assets**: `docs/<area>/my-api/appendices/upload-technical-spec.md`
**Focus**: API endpoints, integration patterns, performance
**Success Metrics**: API latency, error rate, throughput
**Update**: Add reference in `docs/<area>/my-api/1-OVERVIEW.md`

### Example 3: Technical Product Feature (Library)
**Type**: Technical Product (Library)
**File**: `docs/<area>/my-library/parser-module.md` *(example path)*
**Template**: Developer-Focused Template
**Assets**: `docs/<area>/my-library/appendices/parser-architecture.png`
**Focus**: Library API, integration examples, performance characteristics
**Success Metrics**: Parse success rate, memory usage, bundle size
**Update**: Add reference in `docs/<area>/my-library/1-OVERVIEW.md`

### Example 4: Feature PRD
**See**: [the PRD guide](/.agents/skills/pr-lifecycle/references/prd.md) for complete PRD examples and workflow
