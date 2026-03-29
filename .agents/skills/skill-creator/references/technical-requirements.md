# Technical Requirements for Skills

This reference covers naming rules, frontmatter specifications, field constraints, skill anatomy, and the progressive disclosure design principle.

## Naming Rules

### SKILL.md File

- The file **must** be named exactly `SKILL.md` (case-sensitive)
- `skill.md`, `SKILL.MD`, `Skill.md`, and any other casing will fail validation
- There must be exactly one `SKILL.md` per skill folder

### Skill Folder Name

- Must use **kebab-case**: lowercase letters, numbers, and hyphens only
- No spaces, underscores, or capital letters
- Valid: `pdf-editor`, `brand-guidelines`, `my-tool-v2`
- Invalid: `PDF_Editor`, `my skill`, `MyTool`, `pdf__editor`

### Forbidden Content in Skill Folders

- No `README.md` inside skill folders (SKILL.md serves this purpose)
- No hidden files in distribution packages (`.git`, `.DS_Store`, etc.)

## YAML Frontmatter Specification

Every SKILL.md must begin with YAML frontmatter delimited by `---`:

```yaml
---
name: my-skill-name
description: What this skill does. This skill should be used when [trigger conditions]. Key capabilities include [list].
license: MIT
compatibility: Claude Code, Claude.ai
metadata:
  version: "1.0"
  author: Your Name
---
```

### Required Fields

#### `name`

- Must be kebab-case (same rules as folder name)
- Must **not** contain the words "claude" or "anthropic"
- Should match the containing folder name (warning if mismatch)
- Examples: `pdf-editor`, `brand-guidelines`, `data-pipeline`

#### `description`

- Must be under **1024 characters**
- Must **not** contain XML angle brackets (`<` or `>`)
- Must describe **what** the skill does and **when** to use it
- Use third-person phrasing: "This skill should be used when..." not "Use this skill when..."
- See `references/description-guide.md` for the description formula and examples

### Optional Fields

#### `license`

- License identifier or reference (e.g., `MIT`, `Complete terms in LICENSE.txt`)

#### `compatibility`

- Where the skill works (e.g., `Claude Code`, `Claude.ai`, `API`)

#### `metadata`

- Arbitrary key-value pairs for version, author, tags, etc.
- All values should be strings

## Security Restrictions

- Skills must not include credentials, API keys, or secrets
- Scripts should not make network requests unless explicitly required by the skill's purpose
- Skills should not attempt to modify system files or configurations outside their scope
- Avoid storing sensitive data in assets or references

## Skill Anatomy

Every skill consists of a required `SKILL.md` file and optional bundled resources:

```
skill-name/
├── SKILL.md (required)
│   ├── YAML frontmatter metadata (required)
│   │   ├── name: (required)
│   │   └── description: (required)
│   └── Markdown instructions (required)
└── Bundled Resources (optional)
    ├── scripts/          - Executable code (Python/Bash/etc.)
    ├── references/       - Documentation loaded into context as needed
    └── assets/           - Files used in output (templates, icons, fonts, etc.)
```

### Scripts (`scripts/`)

Executable code for tasks that require deterministic reliability or are repeatedly rewritten.

- **When to include**: When the same code is being rewritten repeatedly or deterministic reliability is needed
- **Example**: `scripts/rotate_pdf.py` for PDF rotation tasks
- **Benefits**: Token efficient, deterministic, may be executed without loading into context
- **Note**: Scripts may still need to be read by Claude for patching or environment-specific adjustments

### References (`references/`)

Documentation and reference material loaded as needed into context.

- **When to include**: For documentation that Claude should reference while working
- **Examples**: Database schemas, API documentation, domain knowledge, company policies
- **Benefits**: Keeps SKILL.md lean, loaded only when Claude determines it's needed
- **Best practice**: If files are large (>10k words), include grep search patterns in SKILL.md
- **Avoid duplication**: Information should live in either SKILL.md or references, not both

### Assets (`assets/`)

Files not loaded into context, but used within the output Claude produces.

- **When to include**: When the skill needs files that will be used in the final output
- **Examples**: Templates, images, icons, boilerplate code, fonts, sample documents
- **Benefits**: Separates output resources from documentation, enables use without loading into context

## Progressive Disclosure Design Principle

Skills use a three-level loading system to manage context efficiently:

| Level | Content | When Loaded | Size Target |
|-------|---------|-------------|-------------|
| 1. Metadata | `name` + `description` | Always in context | ~100 words |
| 2. SKILL.md body | Instructions + workflow | When skill triggers | <5,000 words |
| 3. Bundled resources | Scripts, references, assets | As needed by Claude | Unlimited* |

*Unlimited because scripts can be executed without reading into context window.

**Design implication**: Keep SKILL.md lean and procedural. Move detailed reference material, schemas, and examples into `references/` files. Keep only essential procedural instructions and workflow guidance in SKILL.md.

## Field Constraints Summary

| Field | Required | Max Length | Format | Restrictions |
|-------|----------|-----------|--------|-------------|
| `name` | Yes | — | kebab-case | No "claude" or "anthropic" |
| `description` | Yes | 1024 chars | Plain text | No XML brackets; must have what + when |
| `license` | No | — | String | — |
| `compatibility` | No | — | String | — |
| `metadata` | No | — | Key-value map | Values should be strings |
| SKILL.md body | Yes | 5000 words | Markdown | — |
