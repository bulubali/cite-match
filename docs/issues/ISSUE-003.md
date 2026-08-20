# ISSUE-003

## Title
Semantic Matching: Density Overflow Papers Not Retried on Second-Best Candidate Sentences

## Priority
P1

## Status
Closed

## Version Found
v2.5.x (Production Validation 2026-07-27)

## Environment
- OS: Windows 11
- Input: 152 papers, 753 sentences, 101 final assignments

## Steps to Reproduce
1. Run Phase 3 matching with `MAX_PER_SENTENCE = 3`
2. When a paper matches multiple sentences, only the highest-scoring sentence is considered
3. If the highest-scoring sentence already has 3 papers assigned, the paper is routed to Floating (density overflow)
4. The paper is NOT retried on its second-best candidate sentence

## Expected Behavior
When a paper is rejected from its best-match sentence due to density limits, the matching engine should:
1. Retain the full ranked list of candidate sentences per paper (not just the best match)
2. Attempt to assign the paper to its second-highest scoring sentence
3. Continue down the ranked list until either a sentence with capacity is found or all candidates are exhausted
4. Only route to Floating if ALL candidate sentences are at capacity

## Actual Behavior
- 25 papers routed to Floating due to density overflow
- Many are high-IF papers (e.g., @minClinicalValidationWearable2023 IF=27.4, @kireevContinuousCufflessMonitoring2022 IF=35.2)
- The matching engine only records `best_score` and `best_sent_idx` — no ranked candidate list is preserved
- These papers are permanently lost from the injection plan

## Severity
- **Root Cause (Initial):** Phase 3 matching engine (`_phase3_match.py`) uses a single `best_score`/`best_sent_idx` per paper and discards all alternative candidate sentences. The density overflow check operates on sentence-level assignments after all papers have claimed their single best match. There is no fallback mechanism to reassign overflowed papers to their second-choice sentences.
- **Related Phase:** Phase 3 (Script-based matching)
- **Files Involved:**
  - `engine/matcher.py` — if it has a citation matching module
  - `engine/density_controller.py` — density control module
  - Phase 3 matching workflow

## Root Cause

`SemanticMapper._find_matches()` already produced a descending list of safe,
routed anchor matches, but `_route_review_paper()` and
`_route_research_paper()` retained only rank 1 in `CitationCandidate`.
`_enforce_sentence_limits()` then rejected candidates beyond the first three
for a target sentence without access to a second candidate.  Every such paper
became a Floating reference even when an already-ranked, semantically valid
alternative had capacity.

## Minimal Fix Applied

- Extended the existing `CitationCandidate` state with JSON-safe ranked
  alternatives and reroute trace data.  No new matcher, Phase, Framework, or
  Injector/Adapter semantic logic was introduced.
- Preserved the existing top-three rank-1 assignment for each target sentence.
  Only surplus candidates are retried through the existing ranked alternatives
  in order.
- Rerouted candidates persist `original_best_rank`, `selected_rank`, original
  and selected targets, and `sentence_density_overflow`.
- Only after every reliable same-context alternative is full does a candidate
  become Floating with `no_safe_alternative_location`, attempted count, and
  per-rank rejection reasons.
- Table candidates cannot reroute into body locations and body candidates cannot
  reroute into tables.  Protected locations were already excluded before the
  ranked list is built.
- Paragraph soft-density was deliberately not implemented: the production path
  has no stable canonical body-paragraph model, and the original ISSUE-003
  scope is sentence-overflow rerouting.

## Regression Test

`tests/regression/test_issue_003_density_fallback.py` covers:

1. Rank 1 full → rank 2 selected.
2. Ranks 1 and 2 full → rank 3 selected.
3. All ranked candidates full → traceable Floating.
4. Reroute trace fields and JSON state restore.
5. Existing/legacy citations do not consume the new-candidate quota.
6. Protected zones cannot enter fallback rankings.
7. Table candidates cannot fall back into body locations.
8. CandidateAdapter and Injector do not choose semantic alternatives.
9. Original max-three behavior remains when no alternative exists.

## Acceptance Result

PASS

- Focused/related: **36 passed**.
- Full suite: **538 passed, 3 skipped**.
- Golden Dataset: **PASS (7/7)**.
- Independent Production Regression:
  `output/issue003_production_regression_20260820_r2` completed Phase 7 using
  the formal Production Entry.  Of **40** actual sentence-overflow candidates,
  **36** rerouted to rank 2–5; **4** exhausted all reliable alternatives and
  reached Floating with `no_safe_alternative_location`.  Final Floating count
  was **8**: four exhausted-overflow, one no-routing-match, and three
  review-introduction-route failures.  No candidate was silently dropped.
- The historical 25-overflow count is not directly comparable to the current
  run's 40 initial overflows because matching and source-state behavior changed
  in intervening stabilization work; the acceptance criterion is traceable
  rerouting before Floating, not a fixed rescue count.

## Notes

- The historical accepted Release Candidate and Real User Acceptance artifacts
  were not read, overwritten, or otherwise modified by this regression.
- The initial independent run using an already-migrated Markdown artifact was
  fail-closed by Mode C because it contained a References heading without a
  static list.  It is preserved as historical evidence; the successful r2 run
  used the corresponding original input and a new output directory.
- Review protection, Floating expansion quality, non-pipe Table IF semantics,
  and paragraph soft-density remain outside ISSUE-003.
