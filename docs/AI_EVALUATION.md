# UniTime-AI AI / Optimizer Evaluation

## Evaluation status

- **Evaluation date:** 2026-08-30
- **Qualified application baseline:** `03a351c0824f887bf00385ea5e1e4e5add8eb7bf`
- **Model:** `catboost_research_v1`
- **Model status:** `EXPERIMENTAL_SYNTHETIC`

UniTime-AI uses a hybrid scheduling architecture:

- deterministic rules are the authoritative safety layer;
- the CatBoost model ranks only candidates that have already passed hard safety checks;
- the ML score cannot approve, execute, or make an unsafe timetable change;
- deterministic weighted ranking is the mandatory runtime fallback.

The current model was trained and evaluated using synthetic ranking labels only.
The results below demonstrate the ranking pipeline and synthetic generalization,
**not real-university coordinator accuracy**.

## Frozen synthetic test set

- **Ranking groups:** 600
- **Candidate rows:** 3,078
- **Test data origin:** synthetic only

| Metric | Deterministic baseline | CatBoost research-v1 | Improvement |
|---|---:|---:|---:|
| NDCG | 0.9557 | 0.9894 | +0.0337 |
| NDCG@3 | 0.9190 | 0.9810 | +0.0620 |
| Top-1 ranking accuracy | 0.6733 | 0.9000 | +0.2267 |
| Mean reciprocal rank | 0.8168 | 0.9475 | +0.1308 |

### Paired-bootstrap 95% confidence intervals for improvement

| Metric | Observed delta | 95% CI |
|---|---:|---:|
| NDCG | +0.0337 | +0.0298 to +0.0380 |
| NDCG@3 | +0.0620 | +0.0545 to +0.0696 |
| Top-1 ranking accuracy | +0.2267 | +0.1850 to +0.2667 |
| Mean reciprocal rank | +0.1308 | +0.1076 to +0.1542 |

These figures must not be described as production accuracy, probability of correctness, or coordinator success rate.

## Safety architecture

The model is subordinate to deterministic timetable validation.

The scheduling pipeline:

1. Generates duration-preserving candidate slots.
2. Simulates a move without mutating the live timetable.
3. Applies institutional scheduling rules.
4. Checks room, faculty, section, and structural clashes.
5. Checks enrollment-backed student conflicts.
6. Checks student conflict groups and global weighted risk.
7. Rejects candidates that fail a hard constraint.
8. Classifies remaining candidates by available evidence.
9. Sends only `SAFE` and `CONDITIONALLY_SAFE` candidates to CatBoost.
10. Uses deterministic ranking for `INSUFFICIENT_DATA`.
11. Revalidates a selected candidate under the timetable write lock before execution.

`REJECTED` and `INSUFFICIENT_DATA` candidates are never sent to the experimental CatBoost model.

The ranker can return only a bounded planning score and explanatory components. It cannot override safety status, actionability, timetable mutations, or hard-constraint decisions.

## Runtime failure policy

The frozen research-v1 artifact validates model/version/schema/order/status/checksum information. Expected ML runtime failures fall back to `DeterministicWeightedRanker`, including missing/corrupt artifacts, schema mismatch, feature incompatibility, CatBoost load failures, and prediction failures.

This means timetable safety does not depend on ML availability.

## Privacy boundary

The ML feature contract is PII-free. The model does not receive student names, registration numbers, email addresses, user IDs, course names/codes, section identity, or faculty identity.

## Acceptance evidence

Focused AI / optimizer qualification:

```text
tests/test_experimental_ranker.py
tests/test_safe_candidate_service.py
tests/test_optimizer_safety.py

27 passed in 6.12s
```

The full GitHub qualification run for the same application baseline also passed:

```text
Backend test job:     PASS
Frontend job:         PASS
PostgreSQL smoke:     PASS
Android build job:    PASS

Backend pytest:
375 passed, 4 skipped
```

## Project conclusion

UniTime-AI combines deterministic timetable-safety validation with an experimental CatBoost learning-to-rank layer. On a locked synthetic test set, CatBoost produced better ranking metrics than the deterministic weighted baseline while remaining unable to bypass deterministic safety rules.

The model remains **`EXPERIMENTAL_SYNTHETIC`**. These results are suitable for project demonstration and architecture validation, but they are not real-university production accuracy claims.
