# UniTime-AI ranker preparation contract

UniTime-AI is fully functional without ML. Hard scheduling constraints remain deterministic and authoritative. The repository now includes a frozen CatBoost `research-v1` ranker trained on synthetic labels only. It is an experimental ordering layer, not a safety authority and not evidence of real-university accuracy.

## Safety boundary

The candidate pipeline is ordered and cannot be reversed:

1. Generate duration-preserving institutional time slots.
2. Simulate each move without mutating the database.
3. Apply deterministic policy, structural-clash, enrollment-backed student-conflict, report-overlap, group, and global-risk checks.
4. Put any hard failure in `REJECTED`. Rejected candidates never reach a ranker.
5. Classify remaining candidates as `SAFE`, `CONDITIONALLY_SAFE`, or `INSUFFICIENT_DATA` based on available metadata.
6. Pass only eligible `SAFE` and `CONDITIONALLY_SAFE` candidates through the PII-free `CandidateFeatures` contract to the experimental ML ranker. `INSUFFICIENT_DATA` remains visible for data-quality review but is ranked only by the deterministic fallback.
7. Accept only a bounded score and explanatory components from the ranker. The ranker cannot return status, actionability, a timetable mutation, or a hard-check override.
8. At execution, regenerate and hard-check the candidate under the timetable write lock. A stale or newly unsafe candidate is rejected regardless of rank score.

`INSUFFICIENT_DATA` candidates are visible for data-quality review but cannot be executed. `CONDITIONALLY_SAFE` candidates require an explicit coordinator confirmation. The experimental ML ranker cannot change either rule.

## Feature input contract — version 1.0

Every feature row has `hard_constraints_passed=true` and contains no name, registration number, email, user ID, course code/name, section, or faculty identity.

| Field | Type | Meaning |
|---|---|---|
| `feature_schema_version` | string | Exact feature contract (`1.0`) |
| `hard_constraints_passed` | boolean literal | Always `true`; rejected candidates are excluded |
| `safety_status` | enum | `SAFE`, `CONDITIONALLY_SAFE`, or `INSUFFICIENT_DATA` |
| `duration_minutes` | positive integer | Actual class duration |
| `affected_students` | non-negative integer | Verified active enrollments mapped to the moved offering |
| `confirmed_conflicts_removed` | non-negative integer | Enrollment-backed conflict edges removed |
| `inferred_conflicts_removed` | non-negative integer | Explicit timetable-inference signals removed |
| `structural_clashes_removed` | non-negative integer | Room/faculty/section clashes removed |
| `conflict_groups_removed` | non-negative integer | Conflict-group reduction |
| `weighted_risk_reduction` | non-negative integer | Deterministic global risk-cost reduction |
| `day_distance` | non-negative integer | Distance in configured operating-day order |
| `time_shift_minutes` | non-negative integer | Absolute start-time displacement |
| `late_slot` | boolean | Destination starts at or after 17:00 |
| `missing_metadata_count` | non-negative integer | Number of surfaced metadata limitations |

## Ranker output contract

A ranker declares non-empty `ranker_id` and `ranker_version` values. It returns only:

```json
{
  "score": 0,
  "components": [
    {
      "signal": "transparent_signal_name",
      "value": 0,
      "explanation": "Human-readable reason"
    }
  ]
}
```

`score` must be an integer from 0 through 100. Unknown fields are rejected. The configured default is `catboost_research_v1` for eligible candidates, with `deterministic_weighted` version `1.0` as the mandatory fallback. The CatBoost raw ordering signal is mapped monotonically into the existing 0–100 planning-score range; it is not a probability.

## Learning events and outcome labels

The append-only learning pipeline now captures both outcomes and the comparison set that produced a coordinator choice:

- candidate-review API response → one `recommendation_generated` impression;
- every returned candidate → `recommendation_shown` with display position and frozen PII-free features;
- applied candidate → `recommendation_selected`;
- eligible SAFE/CONDITIONALLY_SAFE alternatives from the same observed impression → `recommendation_rejected` / `not_selected`;
- deterministic hard-filter examples → `recommendation_rejected` / `hard_constraint_rejected` and excluded from ranking labels;
- candidate application → `accepted`;
- undo → `undone`;
- redo → `redone`.

This makes future groupwise ranking research possible without storing student identity or raw schedule text. The selected-only `resolution_learning_events` export remains available for outcome analysis; `scripts/export_recommendation_choices.py` is the comparative choice export. Undo/redo append events and never rewrite prior evidence.

## Offline export

Export manually reviewed JSON:

`python scripts/export_ranker_dataset.py --format json --output data/exports/ranker-dataset.json`

Export CSV:

`python scripts/export_ranker_dataset.py --format csv --output data/exports/ranker-dataset.csv`

Use `--term-id <positive-id>` to scope an export. Exports omit database user/report/change identifiers and identity/schedule text. `example_id` is generated only for the export.

Before any future training, the project owner must manually review the dataset and label meaning, choose an offline evaluation design, train in Google Colab, and compare against the deterministic baseline. No model may be integrated unless it materially improves ranking under a valid evaluation, and deterministic hard constraints must remain authoritative.


## Experimental CatBoost research-v1 runtime

- Artifact status: `EXPERIMENTAL_SYNTHETIC`
- Algorithm: `CatBoostRanker` / YetiRank
- Training data origin: `SYNTHETIC_ONLY`
- Eligible for ML inference: `SAFE`, `CONDITIONALLY_SAFE`
- Never sent to ML inference: `INSUFFICIENT_DATA`, `REJECTED`
- Runtime mode: `CANDIDATE_RANKER_MODE=experimental_catboost`
- Emergency/manual fallback mode: `CANDIDATE_RANKER_MODE=deterministic`
- Artifact directory: `backend/ai_ranker/research_v1/`

Before first model load, the runtime verifies the frozen feature ordering, schema version, eligible/never-rank statuses, model size, and SHA-256 checksum from the manifest. Missing CatBoost, missing/corrupt artifacts, schema mismatch, invalid features, load errors, and prediction errors are treated as expected ranker runtime failures and fall back to deterministic weighted ranking. Invalid output from an explicitly injected/custom ranker is still rejected by the strict ranker contract rather than silently accepted.

Synthetic evaluation numbers in the bundle are research diagnostics only. They must never be presented as production accuracy or coordinator success probability. Real coordinator choices/outcomes should be collected through the existing PII-guarded learning pipeline before any future retraining or promotion decision.
