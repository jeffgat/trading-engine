# Testing and Iteration Guide

This reference covers testing approaches, success criteria, and iteration signals for skill development.

## Three Testing Approaches

### 1. Manual Testing (Claude.ai)

The simplest approach: upload the skill to Claude.ai and test interactively.

**Process**:
1. Upload the skill (drag-and-drop or use the skills panel)
2. Start a new conversation
3. Type prompts that should trigger the skill
4. Observe whether the skill activates and follows instructions correctly
5. Test edge cases and negative triggers

**Best for**: Initial development, quick iteration, trigger testing.

### 2. Scripted Testing (Claude Code)

Use Claude Code to run structured test sequences.

**Process**:
1. Place the skill in `.claude/skills/` directory
2. Run Claude Code and issue test prompts
3. Observe skill activation and instruction adherence
4. Test with the `--print` flag for non-interactive evaluation

**Best for**: Repeatable test sequences, CI integration, regression testing.

### 3. Programmatic Testing (API)

Use the Claude API to automate skill testing at scale.

**Process**:
1. Include skill content in the system prompt
2. Send test prompts via API calls
3. Evaluate responses programmatically
4. Compare against expected outputs or criteria

**Best for**: Large test suites, A/B comparisons, quality metrics.

## Triggering Test Suite

### Should-Trigger Tests

Test prompts that should activate the skill. Include:

- **Direct requests**: The most obvious way to ask for the skill's functionality
- **Indirect requests**: Roundabout ways users might ask for the same thing
- **Partial requests**: Requests that only need part of the skill's functionality
- **Synonym requests**: Different words for the same intent

**Example for a `pdf-editor` skill**:
```
Direct:     "Rotate this PDF 90 degrees"
Indirect:   "This document is sideways, can you fix it?"
Partial:    "I need to merge these two PDFs"
Synonym:    "Turn this PDF landscape"
```

### Should-NOT-Trigger Tests

Equally important — test prompts that should NOT activate the skill:

- **Adjacent topics**: Related but out-of-scope requests
- **Ambiguous requests**: Requests that could be interpreted as in-scope but aren't
- **Overlapping skills**: Requests that belong to a different skill

**Example for a `pdf-editor` skill**:
```
Adjacent:      "Help me write a report" (content creation, not PDF editing)
Ambiguous:     "Open this file" (could be any file type)
Overlapping:   "Convert this PDF to a Word doc" (if conversion is a separate skill)
```

## Functional Testing

Once triggered correctly, verify the skill's execution quality:

### Instruction Adherence

- Does Claude follow the workflow steps in order?
- Are bundled scripts used when specified?
- Are references loaded when directed?
- Are error handling steps followed on failure?

### Output Quality

- Does the output match expectations for the given input?
- Are edge cases handled gracefully?
- Is the output format correct?

### Resource Usage

- Are scripts executed (not rewritten from scratch)?
- Are references loaded only when needed?
- Is the context window used efficiently?

## Success Criteria

### Quantitative Metrics

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Trigger accuracy | >90% on should-trigger prompts | Run test suite, count activations |
| False positive rate | <10% on should-NOT-trigger prompts | Run negative test suite |
| Instruction adherence | >95% of steps followed correctly | Manual review of outputs |
| Script usage | 100% when specified | Check if scripts are executed |

### Qualitative Metrics

- **User satisfaction**: Does the skill produce useful results?
- **Efficiency**: Is the skill faster than doing the task without it?
- **Reliability**: Does the skill produce consistent results across runs?
- **Graceful degradation**: When something goes wrong, is the failure informative?

## Performance Comparison Baselines

To demonstrate a skill's value, compare with and without:

1. **Without skill**: Give Claude the same prompt without the skill loaded
2. **With skill**: Give Claude the same prompt with the skill loaded
3. **Compare**: Execution time, output quality, step count, error rate

This comparison helps justify the skill's existence and identify areas for improvement.

## Iteration Signals and Fixes

### Undertriggering (Skill Doesn't Activate)

**Symptoms**: The skill should activate but doesn't.

| Cause | Fix |
|-------|-----|
| Description too narrow | Add more trigger scenarios and synonyms |
| Jargon-heavy description | Include user-friendly language alongside technical terms |
| Missing trigger words | Add common phrasings to description |
| Description too short | Expand with "This skill should be used when..." conditions |

### Overtriggering (Skill Activates Incorrectly)

**Symptoms**: The skill activates when it shouldn't.

| Cause | Fix |
|-------|-----|
| Description too broad | Add specificity — which inputs, which contexts |
| Missing negative triggers | Add "Do NOT Use When" section to SKILL.md |
| Overlap with other skills | Differentiate in description and add exclusions |
| Generic trigger words | Replace with domain-specific terms |

### Instructions Not Followed

**Symptoms**: The skill activates but doesn't follow the workflow.

| Cause | Fix |
|-------|-----|
| Instructions too vague | Add concrete examples and expected outputs |
| Too many steps | Simplify or split into sub-workflows |
| Conflicting instructions | Review for contradictions and resolve |
| Missing context | Add references with necessary background information |
| Steps too long | Break into smaller, actionable sub-steps |
| Assumed knowledge | Spell out domain-specific procedures explicitly |
