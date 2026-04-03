---
name: llm-council
description: "Run any question, idea, or decision through a council of 5 AI advisors who independently analyze it, peer-review each other anonymously, and synthesize a final verdict. Based on Karpathy's LLM Council methodology. MANDATORY TRIGGERS: 'council this', 'run the council', 'war room this', 'pressure-test this', 'stress-test this', 'debate this'. STRONG TRIGGERS (use when combined with a real decision or tradeoff): 'should I X or Y', 'which option', 'what would you do', 'is this the right move', 'validate this', 'get multiple perspectives', 'I can not decide', 'I am torn between'. Do NOT trigger on simple yes/no questions, factual lookups, or casual 'should I' without a meaningful tradeoff. DO trigger when the user presents a genuine decision with stakes, multiple options, and context suggesting they want it pressure-tested from multiple angles."
---

# LLM Council

Run a question through 5 independent advisors with different thinking lenses, have them peer-review each other anonymously, then synthesize a final verdict. Adapted from Andrej Karpathy's LLM Council methodology.

## When to Run

Good: decisions where being wrong is expensive, genuine tradeoffs, strategic pivots, positioning choices, resource allocation.

Bad: factual lookups, creation tasks ("write me X"), processing tasks ("summarize this"). If there's one right answer, just answer it.

## The Five Advisors

| # | Advisor | Thinking Style |
|---|---------|---------------|
| 1 | **The Contrarian** | Finds what's wrong, missing, or will fail. Assumes a fatal flaw exists and hunts for it. |
| 2 | **The First Principles Thinker** | Strips away assumptions. Asks "what are we actually solving?" Rebuilds the problem from ground up. |
| 3 | **The Expansionist** | Finds upside everyone else misses. What could be bigger? What's undervalued? Ignores risk. |
| 4 | **The Outsider** | Zero context about the user's field. Responds purely to what's in front of them. Catches curse of knowledge. |
| 5 | **The Executor** | Only cares: can this be done, and what's the fastest path? "What do you do Monday morning?" |

**Natural tensions:** Contrarian vs Expansionist (downside vs upside). First Principles vs Executor (rethink vs just do it). Outsider keeps everyone honest.

## Council Session Workflow

### Step 1: Frame the Question

**A. Scan workspace for context** (~30 seconds max):
- Read `CLAUDE.md`, `memory/` folder, any referenced files
- Check for prior council transcripts to avoid re-counciling same ground
- Find 2-3 files that give advisors specific, grounded context

**B. Frame the question** as a clear, neutral prompt including:
1. Core decision or question
2. Key context from user's message
3. Key context from workspace files (business stage, constraints, numbers)
4. What's at stake

Don't add opinion or steer. If too vague, ask ONE clarifying question, then proceed.

### Step 2: Convene the Council (5 sub-agents in parallel)

Spawn all 5 advisors simultaneously. See [references/prompts.md](references/prompts.md) for exact templates.

Each advisor gets their identity, the framed question, and instructions to lean fully into their perspective (150-300 words, no hedging, no preamble).

### Step 3: Peer Review (5 sub-agents in parallel)

Collect all 5 responses. Anonymize as Response A-E (randomize mapping to prevent positional bias).

Spawn 5 reviewers in parallel. Each sees all 5 anonymized responses and answers:
1. Which response is strongest and why? (pick one)
2. Which has the biggest blind spot? What is it missing?
3. What did ALL responses miss?

See [references/prompts.md](references/prompts.md) for reviewer template. Keep reviews under 200 words.

### Step 4: Chairman Synthesis

One agent gets everything: original question, all 5 de-anonymized advisor responses, all 5 peer reviews.

Chairman produces the verdict with this exact structure:

```
## Where the Council Agrees
[Points multiple advisors converged on independently — high-confidence signals]

## Where the Council Clashes
[Genuine disagreements. Both sides. Why reasonable advisors disagree.]

## Blind Spots the Council Caught
[Things that only emerged through peer review]

## The Recommendation
[Clear, direct. Not "it depends." A real answer with reasoning.]

## The One Thing to Do First
[Single concrete next step. Not a list. One thing.]
```

The chairman CAN disagree with the majority if the dissenter's reasoning is strongest.

### Step 5: Generate HTML Report

Save as `backtesting/learnings/reports/council-report-{YYYYMMDD-HHmmss}.html`.

Single self-contained HTML file with inline CSS containing:
1. The question at top
2. Chairman's verdict prominently displayed
3. Agreement/disagreement visual showing advisor positions
4. Collapsible sections for each advisor's full response (collapsed by default)
5. Collapsible section for peer review highlights
6. Footer with timestamp

Style: white background, subtle borders, system font stack, soft accent colors per advisor. Professional briefing document aesthetic.

Open the HTML file after generating so the user sees it immediately.

### Step 6: Save Transcript

Save as `backtesting/learnings/reports/council-transcript-{YYYYMMDD-HHmmss}.md`.

Include: original question, framed question, all 5 advisor responses, all 5 peer reviews (with anonymization mapping revealed), chairman's full synthesis.

## Output

Every session produces two files:
```
council-report-{timestamp}.html     # visual report for scanning
council-transcript-{timestamp}.md   # full transcript for reference
```

## Key Rules

- **Always spawn all 5 advisors in parallel** — sequential spawning wastes time and creates bleed
- **Always anonymize for peer review** — prevents deference to certain thinking styles
- **Chairman can override majority** — if the lone dissenter has the strongest reasoning, side with them
- **Don't council trivial questions** — one right answer = just answer it
