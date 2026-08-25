# UniTime-AI ranker preparation contract

UniTime-AI is fully functional without an ML model. Hard scheduling constraints remain deterministic and authoritative. This contract prepares data and interfaces for possible manual research later; it does not select, train, evaluate, deploy, or host a model.

## Safety boundary

The candidate pipeline is ordered and cannot be reversed:

1. Generate duration-preserving institutional time slots.
2. Simulate each move without mutating the database.
3. Apply deterministic policy, structural-clash, enrollment-backed student-conflict, report-overlap, group, and global-risk checks.
4. Put any hard failure in `REJECTED`. Rejected candidates never reach a ranker.
5. Classify remaining candidates as `SAFE`, `CONDITIONALLY_SAFE`, or `INSUFFICIENT_DATA` based on available metadata.
6. Pass only the PII-free `CandidateFeatures` contract to the configured ranker.
7. Accept only a bounded score and explanatory components from the ranker. The ranker cannot return status, actionability, a timetable mutation, or a hard-check override.
8. At execution, regenerate and hard-check the candidate under the timetable write lock. A stale or newly unsafe candidate is rejected regardless of rank score.

`INSUFFICIENT_DATA` candidates are visible for data-quality review but cannot be executed. `CONDITIONALLY_SAFE` candidates require an explicit coordinator confirmation. A future ML ranker must not change either rule.

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

`score` must be an integer from 0 through 100. Unknown fields are rejected. The production default is `deterministic_weighted` version `1.0`, which is a transparent rule-based baseline—not an ML model.

## Learning events and outcome labels

Only real coordinator actions create append-only learning events:

- candidate application → `accepted`
- undo → `undone`
- redo → `redone`

Each event freezes the PII-free feature vector, ranker identity/version, score, candidate safety status, and event time. Undo/redo append events; they do not rewrite prior evidence.

## Offline export

Export manually reviewed JSON:

`python scripts/export_ranker_dataset.py --format json --output data/exports/ranker-dataset.json`

Export CSV:

`python scripts/export_ranker_dataset.py --format csv --output data/exports/ranker-dataset.csv`

Use `--term-id <positive-id>` to scope an export. Exports omit database user/report/change identifiers and identity/schedule text. `example_id` is generated only for the export.

Before any future training, the project owner must manually review the dataset and label meaning, choose an offline evaluation design, train in Google Colab, and compare against the deterministic baseline. No model may be integrated unless it materially improves ranking under a valid evaluation, and deterministic hard constraints must remain authoritative.
