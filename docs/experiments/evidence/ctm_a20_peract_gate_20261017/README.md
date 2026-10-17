# Per-act boss death-logit shifts for the A20 CTM: offline gate (2026-10-17)

Requested by Philipp on 2026-10-17 at 16:18Z ("yes to per act boss shift offline gate"), following CTM audit
finding 2. No ledger § has been claimed yet; recording it in the ledger is a separate step.

- **Pre-registration:** [PREREG-PERACT.md](PREREG-PERACT.md), sha256 `47f72819…`. It was written to
  `/mnt/project-files/ctm-a20/peract-gate/` before the decision corpus was scored.
- **Fit:** [fit_peract_validation.py](fit_peract_validation.py), run during the audit. Rows: Stage 1 VALIDATION boss
  rows (`room_class == BOSS`), with uncalibrated scores. Resulting death-logit shifts: act 1 −0.4747, act 2 −0.2371,
  act 3 +0.0720.
- **Decision corpus:** the fresh Stage 4 main corpus, the same as the §470 decision step.
  - Rows: 76,406 rows from 3,999 seeds, `none.jsonl` sha `690eef72…`, rebuilt from `ctm-a20/stage4/w*.tar.gz` in path
    order.
  - Scores: uncalibrated scores (manifest `704f2a58…`) from `one_combat ctmscorerows` at main `79263192`. They are
    byte-identical to the §443 re-gate candidate scores, sha `5499878a…`.
- **Gate:** [gate_peract.py](gate_peract.py), producing [result.json](result.json). The verdict is **PASS** on all
  four criteria:

| Boss rows | n | Incumbent bias (§470 global) | Candidate bias (per act) | NLL, candidate − incumbent [95% CI] |
|---|---|---|---|---|
| all | 8,742 | −0.0040 | −0.0036 | −0.0025 [−0.0039, −0.0011] |
| act 1 | 3,658 | +0.0142 | −0.0035 | −0.0015 [−0.0039, +0.0007] |
| act 2 | 2,587 | +0.0070 | +0.0003 | −0.0002 [−0.0009, +0.0005] |
| act 3 | 2,497 | **−0.0423** | −0.0079 | −0.0064 [−0.0100, −0.0028] |

- Not a criterion: the 541 rows with a boss encounter in room class OTHER (Act-1 bosses fought from Act-3 events) get
  NLL +0.0020 under the candidate.
- PASS allows a runtime implementation: a manifest field with per-act shifts, the Heart excluded. That implementation
  needs its own review. Making it the default is Philipp's call. No runtime change is made here.
