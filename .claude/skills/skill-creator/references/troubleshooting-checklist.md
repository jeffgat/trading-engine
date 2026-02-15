# Troubleshooting and Checklists

This reference provides problem/solution tables for common issues and checklists for each phase of skill development.

## Common Problems and Solutions

### Skill Won't Upload / Validate

| Problem | Solution |
|---------|----------|
| "Invalid SKILL.md" error | Verify file is named exactly `SKILL.md` (case-sensitive) |
| "Missing frontmatter" error | Ensure file starts with `---` on line 1, has `name:` and `description:`, and closes with `---` |
| "Invalid name" error | Use kebab-case only: lowercase, numbers, hyphens. No spaces, underscores, or capitals |
| "Forbidden word in name" | Remove "claude" or "anthropic" from the `name` field |
| "Description too long" | Keep `description` under 1024 characters |
| "Invalid characters in description" | Remove XML angle brackets (`<` and `>`) from description |
| Folder name mismatch | Rename folder to match the `name` field in frontmatter |

### Skill Doesn't Trigger

| Problem | Solution |
|---------|----------|
| Never activates | Check that `description` includes "This skill should be used when..." with specific conditions |
| Activates inconsistently | Add synonym trigger words and alternative phrasings to description |
| Works in tests but not production | Verify skill is properly installed/uploaded in the target environment |
| Triggers on wrong prompts | Narrow description scope; add "Do NOT Use When" section |

### Skill Triggers But Doesn't Work Correctly

| Problem | Solution |
|---------|----------|
| Skips workflow steps | Number steps explicitly; add "Follow steps in order" instruction |
| Rewrites scripts instead of running them | Add explicit "Execute `scripts/name.py`" instruction, not "implement the logic" |
| Ignores references | Use "Load `references/file.md`" phrasing with specific context for when to load |
| Produces wrong output format | Add output format specification with an example |
| Fails on edge cases | Add error handling section with specific failure modes |

### MCP Integration Issues

| Problem | Solution |
|---------|----------|
| MCP tool not found | Verify MCP server is configured and running in the target environment |
| Wrong MCP tool selected | Add explicit tool selection logic: "For X, use tool Y" |
| MCP call fails silently | Add error handling: "If [tool] returns an error, [fallback action]" |
| MCP data format unexpected | Add data transformation step between MCP call and usage |

### Large Context Issues

| Problem | Solution |
|---------|----------|
| SKILL.md too long | Move detailed content to `references/` files; keep SKILL.md under 5000 words |
| References overwhelm context | Add grep patterns so Claude can search rather than load entire files |
| Slow skill execution | Reduce reference file sizes; split large references into focused topics |
| Script output too large | Add output filtering or summarization to scripts |

## Development Phase Checklists

### Before You Start Checklist

- [ ] Clear understanding of what the skill should do (concrete examples gathered)
- [ ] At least 3 example user prompts that should trigger the skill
- [ ] At least 2 example user prompts that should NOT trigger the skill
- [ ] Identified which bundled resources are needed (scripts, references, assets)
- [ ] Confirmed no existing skill covers the same functionality
- [ ] Determined the skill category (Document & Asset, Workflow Automation, MCP Enhancement)

### During Development Checklist

- [ ] SKILL.md named exactly `SKILL.md` (case-sensitive)
- [ ] Folder name is kebab-case
- [ ] YAML frontmatter has `name` and `description`
- [ ] `name` is kebab-case with no forbidden words
- [ ] `description` follows the formula: What + When + Capabilities
- [ ] `description` is under 1024 characters with no XML brackets
- [ ] Instructions use imperative/infinitive form (verb-first)
- [ ] All bundled resources are referenced in SKILL.md workflow
- [ ] "When to Use" section is present
- [ ] "Do NOT Use When" section is present
- [ ] Steps are numbered and sequential
- [ ] Error handling section covers common failure modes
- [ ] No duplication between SKILL.md and reference files
- [ ] SKILL.md is under 5000 words

### Before Upload / Distribution Checklist

- [ ] Run `package_skill.py` validation — zero errors
- [ ] Address all warnings (or document why they're acceptable)
- [ ] Test should-trigger prompts — skill activates correctly
- [ ] Test should-NOT-trigger prompts — skill stays dormant
- [ ] Verify scripts execute without errors in target environment
- [ ] Confirm all file paths in SKILL.md are correct relative paths
- [ ] Remove unused example/template files from initialization
- [ ] No credentials, API keys, or secrets in any file
- [ ] No `.git`, `.DS_Store`, or other hidden files in distribution

### After Upload Checklist

- [ ] Skill appears in the skills list / panel
- [ ] Trigger with a basic prompt — skill activates
- [ ] Complete a full workflow — all steps execute correctly
- [ ] Test with an edge case — error handling works
- [ ] Test with an unrelated prompt — skill does NOT trigger
- [ ] Compare output quality with and without the skill
- [ ] Collect user feedback on first few uses
- [ ] Document any iteration needs discovered during testing

## Distribution Methods

### Claude.ai

Upload the skill zip file through the Claude.ai interface. Skills are available in the conversation where they're uploaded.

### Claude Code

Place the skill folder in `.claude/skills/` directory. The skill is available in all Claude Code sessions that load from that directory.

### Organization-Wide

Distribute through your organization's skill sharing mechanism. Ensure all team members have necessary MCP servers configured if the skill depends on them.

### API

Include the SKILL.md content in the system prompt when making API calls. Bundle any necessary reference content inline or provide file access paths.

## Quick Diagnostic Flowchart

```
Skill not working?
├── Won't upload/validate → Check naming, frontmatter, forbidden words
├── Doesn't trigger → Check description triggers, synonyms, "when to use"
├── Triggers too often → Narrow description, add "Do NOT Use When"
├── Wrong behavior → Check instruction clarity, step ordering, examples
├── Scripts not running → Check file paths, permissions, "Execute" phrasing
└── References ignored → Check "Load references/" callouts, file existence
```
