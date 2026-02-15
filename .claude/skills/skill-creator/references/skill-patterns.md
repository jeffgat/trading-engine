# Skill Patterns and Categories

This reference covers common skill categories, architectural patterns, and SKILL.md template structures to guide skill design decisions.

## Three Use Case Categories

### 1. Document & Asset Creation

Skills that produce files, documents, or media as output.

**Characteristics**:
- Heavy use of `assets/` for templates and boilerplate
- Scripts for format conversion or generation
- Output is a deliverable (PDF, image, code project, presentation)

**Examples**: `pdf-editor`, `slide-generator`, `frontend-webapp-builder`, `brand-asset-creator`

**Typical structure**:
```
skill-name/
├── SKILL.md
├── scripts/
│   └── generate.py          # Handles format conversion/generation
├── references/
│   └── format-spec.md       # Output format requirements
└── assets/
    └── template/            # Starter templates for output
```

### 2. Workflow Automation

Skills that orchestrate multi-step processes across tools and systems.

**Characteristics**:
- Focus on procedural SKILL.md instructions
- References for API docs, schemas, configurations
- Scripts for validation or data transformation
- Often integrates with MCP servers

**Examples**: `ci-pipeline`, `release-manager`, `data-migration`, `onboarding-workflow`

**Typical structure**:
```
skill-name/
├── SKILL.md
├── scripts/
│   └── validate.py          # Pre/post-condition checks
└── references/
    ├── api-docs.md           # External service documentation
    └── workflow-states.md    # State machine or step definitions
```

### 3. MCP Enhancement

Skills that extend or improve Claude's use of MCP (Model Context Protocol) servers.

**Characteristics**:
- Instructions on when and how to use specific MCP tools
- Domain knowledge that improves MCP tool usage
- Error handling and fallback strategies for MCP calls

**Examples**: `figma-to-code`, `linear-manager`, `slack-responder`, `github-reviewer`

**Typical structure**:
```
skill-name/
├── SKILL.md
└── references/
    ├── tool-usage.md         # When/how to use each MCP tool
    └── domain-knowledge.md   # Context for better tool decisions
```

## Five Architectural Patterns

### 1. Sequential Orchestration

Execute steps in a fixed order where each step depends on the previous.

**When to use**: Linear workflows like build-test-deploy, document-review-publish.

**SKILL.md approach**: Numbered steps with clear preconditions and postconditions for each step.

### 2. Multi-MCP Coordination

Combine multiple MCP servers to accomplish a task.

**When to use**: Tasks spanning multiple systems (e.g., read from Figma, write to GitHub).

**SKILL.md approach**: Define which MCP tool to use for each subtask, with data transformation steps between tools.

### 3. Iterative Refinement

Produce output, evaluate it, and improve in a loop.

**When to use**: Creative or quality-sensitive tasks (design generation, code review, content writing).

**SKILL.md approach**: Define the generation step, evaluation criteria, and refinement instructions. Include a maximum iteration count.

### 4. Context-Aware Tool Selection

Choose different tools or approaches based on input characteristics.

**When to use**: Skills that handle varied inputs (different file formats, different project types).

**SKILL.md approach**: Decision tree or conditional logic — "If the input is X, use approach A. If Y, use approach B."

### 5. Domain-Specific Intelligence

Encode specialized knowledge that improves Claude's decision-making.

**When to use**: Tasks where general knowledge is insufficient (company-specific conventions, industry regulations).

**SKILL.md approach**: Keep decision logic in SKILL.md, detailed reference material in `references/`.

## Problem-First vs. Tool-First Design

### Problem-First (Recommended)

Start with the user's problem and work backward to tools:

1. What problem does the user have?
2. What steps solve this problem?
3. What tools are needed for each step?
4. What knowledge makes each step more effective?

### Tool-First (Avoid)

Starting with available tools leads to skills that are:
- Too focused on tool mechanics rather than user outcomes
- Harder to trigger (descriptions end up tool-centric, not intent-centric)
- Less adaptable when tools change or alternatives exist

## SKILL.md Template Structures

### Minimal Template (~200 words)

For simple skills with a single purpose:

```markdown
---
name: skill-name
description: [What + When + Capabilities]
---

# Skill Name

[1-2 sentence purpose statement]

## When to Use

[Trigger conditions — what the user asks for or provides]

## Do NOT Use When

[Anti-patterns — what this skill is NOT for]

## Workflow

1. [Step 1]
2. [Step 2]
3. [Step 3]
```

### Standard Template (~500-1500 words)

For skills with bundled resources:

```markdown
---
name: skill-name
description: [What + When + Capabilities]
---

# Skill Name

[Purpose statement]

## When to Use

[Trigger conditions]

## Do NOT Use When

[Anti-patterns]

## Workflow

### Step 1: [Name]
[Instructions]
- Load `references/detail.md` for [specific guidance]

### Step 2: [Name]
[Instructions]
- Run `scripts/tool.py` with [arguments]

### Step 3: [Name]
[Instructions]

## Error Handling

[Common errors and recovery steps]
```

### Complex Template (~2000-4000 words)

For skills with multiple workflows or extensive domain logic:

```markdown
---
name: skill-name
description: [What + When + Capabilities]
---

# Skill Name

[Purpose statement]

## When to Use

[Trigger conditions by category]

## Do NOT Use When

[Anti-patterns]

## Workflow A: [Name]

### Step 1: [Name]
[Instructions with references and script callouts]

### Step 2: [Name]
[Instructions]

## Workflow B: [Name]

### Step 1: [Name]
[Instructions]

## Shared Resources

[Cross-workflow reference material and scripts]

## Error Handling

[Error tables with problem/solution pairs]
```

## Choosing a Pattern

| User Need | Category | Primary Pattern |
|-----------|----------|----------------|
| "Create a thing" | Document & Asset | Sequential Orchestration |
| "Do this process" | Workflow Automation | Sequential Orchestration |
| "Use this tool better" | MCP Enhancement | Context-Aware Tool Selection |
| "Handle different inputs" | Any | Context-Aware Tool Selection |
| "Make it high quality" | Any | Iterative Refinement |
| "Work across systems" | Workflow / MCP | Multi-MCP Coordination |
| "Follow our conventions" | Any | Domain-Specific Intelligence |
