# Description Writing Guide

The `description` field in YAML frontmatter is the primary mechanism that determines when Claude activates a skill. A well-crafted description ensures the skill triggers at the right time and stays dormant otherwise.

## The Description Formula

Every description should follow this structure:

```
[What it does] + [When to use it] + [Key capabilities]
```

1. **What it does**: A clear, concise statement of the skill's purpose (1 sentence)
2. **When to use it**: Specific trigger conditions using third-person phrasing (1-2 sentences)
3. **Key capabilities**: Optional list of specific capabilities for disambiguation

## Good Examples

### Example 1: Figma Design Skill

```yaml
description: >
  Convert Figma designs into production-ready code. This skill should be used
  when the user shares a Figma URL or asks to implement a design from Figma.
  Supports React, Vue, and HTML/CSS output formats.
```

**Why it works**: Clear purpose (convert designs to code), explicit trigger (Figma URL or design request), specific capabilities (three output formats).

### Example 2: Linear Project Management Skill

```yaml
description: >
  Manage Linear issues, projects, and workflows. This skill should be used
  when the user asks to create, update, or query Linear issues, manage sprints,
  or generate project reports from Linear data.
```

**Why it works**: Broad but bounded scope (Linear only), multiple trigger conditions listed, covers CRUD operations and reporting.

### Example 3: Payment Onboarding Skill

```yaml
description: >
  Guide users through payment system setup and configuration. This skill
  should be used when the user needs to integrate Stripe, set up webhooks,
  configure pricing plans, or troubleshoot payment processing issues.
```

**Why it works**: Describes the domain (payment setup), lists four specific trigger scenarios, covers both setup and troubleshooting.

## Bad Examples

### Bad Example 1: Too Vague

```yaml
description: Helps with data tasks.
```

**Problems**: No trigger conditions, no specifics about what "data tasks" means, Claude cannot determine when to activate.

### Bad Example 2: Missing Triggers

```yaml
description: >
  A comprehensive tool for managing database migrations, schema changes,
  and data transformations across multiple database engines.
```

**Problems**: Describes capabilities well but never says when to use it. Missing "This skill should be used when..." phrasing.

### Bad Example 3: Too Technical / Contains XML

```yaml
description: >
  Processes <input> tags and transforms XML data using XSLT pipelines.
  Use when you need to parse <data> elements.
```

**Problems**: Contains XML angle brackets (will fail validation), uses second-person "you" instead of third-person, too implementation-focused rather than user-intent-focused.

## Trigger Optimization Checklist

Use this checklist to evaluate and improve a description:

- [ ] **States what the skill does** in the first sentence
- [ ] **Includes "This skill should be used when..."** with specific conditions
- [ ] **Uses third-person phrasing** (not "you" or imperative)
- [ ] **Lists at least 2 trigger scenarios** (user actions or requests)
- [ ] **Under 1024 characters** total
- [ ] **No XML angle brackets** (`<` or `>`)
- [ ] **No jargon-only triggers** — includes terms a non-expert user would say
- [ ] **Distinguishable** from other skills in the same collection
- [ ] **Covers edge cases** — includes common phrasings and synonyms for the trigger

## Trigger Word Strategy

Include words and phrases that match how users naturally ask for help:

| Instead of only | Also include |
|----------------|-------------|
| "generate PDF" | "create PDF", "make PDF", "export to PDF" |
| "refactor code" | "clean up code", "improve code", "restructure" |
| "deploy" | "push to production", "ship", "release" |

The goal is to capture the user's intent regardless of their exact phrasing.

## Description Length Guidelines

- **Minimum effective**: ~50 characters (what + when)
- **Recommended**: 150-400 characters (what + when + capabilities)
- **Maximum allowed**: 1024 characters
- **Too long**: If over 800 characters, consider whether all information is necessary for triggering (move implementation details to SKILL.md body)
