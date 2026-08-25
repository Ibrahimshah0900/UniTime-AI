# Domain learning-event contract

UniTime-AI is fully functional without an ML model. The `learning_events` table is an append-only source of auditable, future offline learning signals; it does not train, select, host, or invoke a model and it never participates in hard safety decisions.

## Stored fields

Every event records a constrained event type, academic term, entity type and pseudonymous entity key, optional pseudonymous subject key, actor role, outcome label, source, context schema version, JSON context, and timestamp. Stable keys are SHA-256 namespace keys derived from internal identifiers. Direct user IDs, names, emails, registration numbers, passwords, and temporary credentials are forbidden in JSON context by the write service.

Current strong domain signals include:

- student enrollment and drop, including whether the add produced a live conflict;
- clash-report submission, verified resolution, rejection/invalidity, and duplicate classification;
- deterministic recommendation selection and transactional resolution apply;
- resolution undo and redo;
- safe manual room/time changes;
- academic-term archival.

The existing `resolution_learning_events` table remains the narrower candidate-ranking feature/outcome store described in `RANKER_CONTRACT.md`. Domain events complement it; they do not duplicate PII or authorize probabilistic resolution.

## Offline export

From the repository root:

```powershell
python scripts/export_learning_events.py data/learning-events.json
python scripts/export_learning_events.py data/learning-events.csv --term-id 1
```

Both formats declare schema version `1.0`. Exported subject/entity keys are pseudonymous stable linkage keys. A project owner must still review any dataset manually before later offline experimentation. No performance metric may be claimed from demo or tiny data.
