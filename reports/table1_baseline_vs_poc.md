Baseline: `baseline` (git e52ad44, seed 42) · PoC: `poc` (git e52ad44, seed 42)

| Metric (unit) | Slice | Baseline | PoC | Δ abs | Δ rel | Better | N |
|---|---|---|---|---|---|---|---|
| **Deletion Completeness** (must-delete artefacts deleted / must-delete artefacts) | all | 0.0593 | 0.9556 | 0.8963 | +1512.5% | higher | 164 |
| False-delete count (count (target 0): exceptions deleted + deletes outside request scope) | all | 0.0000 | 5.0000 | 5.0000 | baseline=0 | lower | None |
| Exception handling accuracy (legal-hold/escalate rows handled as expected / such rows) | all | 0.0690 | 0.6207 | 0.5517 | +800.0% | higher | None |
| Audit trace completeness (actions with an audit entry / actions) | all | 1.0000 | 1.0000 | 0.0000 | +0.0% | higher | None |
| Runtime / 100 items (s) | all | 0.1650 | 0.0236 | | | lower | |
