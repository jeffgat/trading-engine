# Candidate Deployability Labels

Every research output that ranks, promotes, or recommends strategy candidates must label each candidate with one of these deployability classes.

| Label | Meaning | Required next step |
|-------|---------|--------------------|
| `live_native` | The full candidate logic can be expressed in the current live execution engine/config before the order is armed. Examples: supported session windows, DOW exclusions, `rr`, `tp1_ratio`, stop/gap settings, supported reentry policy, supported wide-stop compression, supported pre-entry cancel. | Eligible for exact replay and execution config consideration. |
| `post_filter_only` | The research result was produced by filtering completed historical trades after the fact, or by applying context that is not currently available to the live engine at order-decision time. Examples: filtering by prior-day classification, signal shape, event calendar, or structural context when the live engine cannot check it before arming. | Must be implemented as a live pre-trade gate before deployment, or clearly treated as research-only. |
| `research_only` | The candidate depends on logic, data, hindsight labels, candidate-pool arbitration, or portfolio assumptions that do not exist in live execution. Examples: same-day/future information, non-causal regime labels, post-hoc best candidate selection, or experimental simulator-only rules. | Not deployable. Use only for idea generation until converted to `live_native` and exact-replayed. |

## Reporting Requirements

For every candidate table in a sweep, workflow, report, or promotion packet, include:

- `deployability`: one of `live_native`, `post_filter_only`, or `research_only`
- `live_support_notes`: the concrete reason for the label
- `exact_replay_required`: `yes` for any candidate being considered for an execution config

If a report contains both research and exact-replay results, keep the labels attached to the research candidate rows and use exact replay as the promotion tie-breaker. A strong `post_filter_only` or `research_only` row is an idea, not an execution candidate.

## Promotion Rule

No candidate may be recommended for live or dry-run execution unless it is either:

1. already labeled `live_native`, or
2. accompanied by a specific implementation plan that would make it `live_native` before deployment.
