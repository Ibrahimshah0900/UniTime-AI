# UniTime-AI Experimental Ranker — Research v1

This bundle contains the frozen CatBoost ranking model selected during
the UniTime-AI synthetic ranking experiment.

IMPORTANT:
- Training labels are SYNTHETIC ONLY.
- This is not evidence of real university coordinator accuracy.
- Deterministic timetable safety remains authoritative.
- The model ranks SAFE and CONDITIONALLY_SAFE candidates only.
- REJECTED and INSUFFICIENT_DATA candidates must never reach inference.
- Any load, schema, feature, or prediction failure must fall back to
  DeterministicWeightedRanker.
- Do not retrain or tune this frozen research-v1 artifact using the
  locked synthetic test set.

Contents:
- model.cbm
- feature_contract.json
- validation_selection.json
- synthetic_test_evaluation.json
- manifest.json
