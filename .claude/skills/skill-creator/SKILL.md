---
name: skill-creator
description: >
  Guide for creating, validating, and packaging skills that extend Claude's capabilities.
  This skill should be used when users want to create a new skill, update an existing skill,
  validate a skill, or package a skill for distribution. Key capabilities include scaffolding
  skill directories, writing effective SKILL.md files, and running validation checks.
---

# Skill Creator

This skill provides step-by-step guidance for creating effective skills — modular packages that extend Claude's capabilities with specialized knowledge, workflows, and tools.

## About Skills

Skills are self-contained packages built around a `SKILL.md` file with optional bundled resources (`scripts/`, `references/`, `assets/`). They use progressive disclosure: metadata is always in context, SKILL.md loads when triggered, and bundled resources load on demand.

For the full anatomy, naming rules, frontmatter spec, and constraints, load `references/technical-requirements.md`.

## Skill Creation Process

Follow these steps in order. Skip a step only when there is a clear reason it does not apply.

### Step 1: Understand the Skill with Concrete Examples

Skip only when the skill's usage patterns are already clearly understood. This step remains valuable even when iterating on an existing skill.

To create an effective skill, clearly understand concrete examples of how the skill will be used. This understanding can come from direct user examples or generated examples validated with user feedback.

Example questions for an image-editor skill:

- "What functionality should the image-editor skill support? Editing, rotating, anything else?"
- "Can you give some examples of how this skill would be used?"
- "What would a user say that should trigger this skill?"

Avoid overwhelming users — start with the most important questions and follow up as needed.

**Exit criteria**: A clear sense of the functionality the skill should support, with at least 3 example trigger prompts.

### Step 2: Plan the Reusable Skill Contents

Turn concrete examples into a skill by analyzing each example:

1. Consider how to execute on the example from scratch
2. Identify what scripts, references, and assets would be helpful when executing these workflows repeatedly

**Planning examples**:

| Example Task | Analysis | Resource |
|-------------|----------|----------|
| "Rotate this PDF" | Same rotation code every time | `scripts/rotate_pdf.py` |
| "Build me a todo app" | Same boilerplate every time | `assets/hello-world/` template |
| "How many users logged in?" | Same schema discovery every time | `references/schema.md` |

For architectural patterns (sequential orchestration, multi-MCP coordination, iterative refinement, context-aware tool selection, domain-specific intelligence), load `references/skill-patterns.md`.

**Exit criteria**: A list of reusable resources to include — scripts, references, and assets.

### Step 3: Initialize the Skill

Skip if the skill already exists and only iteration or packaging is needed.

When creating a new skill from scratch, run the `init_skill.py` script to scaffold the directory:

```bash
python3 scripts/init_skill.py <skill-name> --path <output-directory>
```

**Expected output**:

```
Success! Skill 'my-skill' created at: <output-directory>/my-skill

Created structure:
  my-skill/
  ├── SKILL.md              (edit frontmatter and instructions)
  ├── scripts/
  │   └── example.py        (replace or delete)
  ├── references/
  │   └── example.md        (replace or delete)
  └── assets/
      └── .gitkeep          (add output assets here)
```

The script validates that the name is kebab-case and contains no forbidden words ("claude", "anthropic"). After initialization, customize or remove the generated template files as needed.

### Step 4: Edit the Skill

When editing a skill (newly generated or existing), remember the skill is being created for another instance of Claude. Focus on procedural knowledge, domain-specific details, and reusable assets that would help another Claude instance execute tasks more effectively.

#### Start with Bundled Resources

Begin implementation with the reusable resources identified in Step 2: `scripts/`, `references/`, and `assets/` files. This step may require user input (e.g., brand assets, API documentation, templates).

Delete any example files from initialization that are not needed.

#### Write SKILL.md

Structure SKILL.md following this recommended outline:

1. **Frontmatter** — `name` (kebab-case) and `description` (what + when + capabilities)
2. **Title and purpose** — 1-2 sentence overview
3. **When to Use** — Specific trigger conditions
4. **Do NOT Use When** — Anti-patterns and out-of-scope requests
5. **Workflow** — Numbered steps with script/reference callouts
6. **Error Handling** — Common failure modes and recovery steps
7. **Output format** — What the final deliverable looks like (if applicable)
8. **References** — Pointers to bundled resources with context for when to load them

For the description formula (What + When + Capabilities), good/bad examples, and trigger optimization, load `references/description-guide.md`.

For naming rules, frontmatter field constraints, and the full technical spec, load `references/technical-requirements.md`.

#### Writing Style

Write all instructions using **imperative/infinitive form** (verb-first), not second person. Use objective, instructional language:

**Good**: "To rotate a PDF, execute `scripts/rotate_pdf.py` with the file path."
**Bad**: "You should run the rotation script on the PDF file."

#### Actionability Rule

Every instruction should be actionable — Claude must be able to execute it without guessing. Avoid vague directives.

**Good**: "Load `references/schema.md` and identify the table matching the user's query."
**Bad**: "Consult the relevant documentation as needed."

#### Negative Triggers

Include a "Do NOT Use When" section to prevent false activations:

```markdown
## Do NOT Use When

- The user is asking about general coding help (not skill-specific)
- The request is for a one-off task that doesn't need reusability
- Another skill already handles the requested functionality
```

#### Resource References

Every bundled resource must be explicitly referenced in the SKILL.md workflow. Use this phrasing pattern:

- `Load references/file.md for [specific context]`
- `Execute scripts/tool.py with [arguments]`
- `Copy assets/template/ to [destination]`

### Step 5: Package the Skill

Once the skill is ready, validate and package it using the `package_skill.py` script:

```bash
python3 scripts/package_skill.py <path/to/skill-folder>
```

Optional output directory:

```bash
python3 scripts/package_skill.py <path/to/skill-folder> --output ./dist
```

The script runs two phases:

**Validation checks** (errors block packaging):
- `SKILL.md` exists with exact casing
- YAML frontmatter present with `---` delimiters
- `name` field exists, is kebab-case, has no forbidden words
- `description` field exists, has no XML angle brackets
- Folder name is kebab-case

**Quality warnings** (non-blocking):
- Folder name matches frontmatter `name`
- Description under 1024 characters
- Description includes trigger conditions ("should be used when")
- SKILL.md under 5000 words
- No README.md in skill folder

If validation passes, the script creates `<skill-name>.zip` in the output directory, excluding hidden files (`.git`, `.DS_Store`, etc.).

### Step 6: Test and Iterate

After packaging, test the skill and iterate based on results.

#### Quick Iteration Checklist

1. **Trigger test** — Try 3+ prompts that should activate the skill and 2+ that should not
2. **Workflow test** — Execute a full workflow and verify all steps are followed
3. **Edge case test** — Test with unusual inputs or error conditions
4. **Comparison test** — Compare output quality with and without the skill

#### Iteration Signals

**Undertriggering** (skill doesn't activate when it should):
- Add more trigger scenarios and synonyms to the description
- Include user-friendly language alongside technical terms
- Expand "When to Use" with more conditions

**Overtriggering** (skill activates when it shouldn't):
- Narrow the description scope with more specific conditions
- Strengthen the "Do NOT Use When" section
- Replace generic trigger words with domain-specific terms

**Instructions not followed** (skill activates but behaves incorrectly):
- Add concrete examples and expected outputs to workflow steps
- Break complex steps into smaller sub-steps
- Add explicit script/reference callouts where Claude is improvising

For the full testing methodology, success metrics, and performance baselines, load `references/testing-and-iteration.md`.

For problem/solution tables and phase-by-phase checklists, load `references/troubleshooting-checklist.md`.
