# Issue 37: PVNet dead-monster token layout differs between training and inference

- **Status:** closed
- **Tier:** High
- **Last verified:** 2026-08-05
- **Source:** code review 2026-08-05; `train_combat_pvnet.py` vs `combat_pvnet_parity.py`

## Symptom

The PVNet trainer **skipped** a monster-slot token whenever no row in the
batch had that slot alive (`if not alive.any(): continue`), so the token count
was batch-composition-dependent (e.g. 13 vs 14 tokens for single-monster
fights). The exported/C++ convention (`combat_pvnet_parity.py:181-190`) appends
a zero token for all-dead slots (fixed 14-token layout). Consequences:
(a) train-time forward ≠ inference-time forward on any state with a dead slot;
(b) the same state maps to different inputs depending on its batchmates.

## Evidence

- `train_combat_pvnet.py:193-200` (skip) vs `combat_pvnet_parity.py:181-190`
  (zero token) and `run_pvnet_gate.sh` ("14-token layout" note).

## Why it matters

The parity harness validates C++ against the zero-token convention, so this
mismatch was invisible — every PVNet model trained to date (§72 replication,
§101 parity, §102 payoff gate) had a train/inference representation mismatch
in any fight with dead slots.

## Candidate fix direction

Always emit all 5 monster tokens; zero-fill all-dead slots (matching parity).

## Relevant code

- `train_combat_pvnet.py::SharedEncoder.build_tokens`

## Resolution (2026-08-05)

Fixed in the 2026-08-05 code-review working tree. Rerun required if the PVNet
channel reopens: retrain → re-parity → re-gate (rerun-ledger row "PVNet
heads/layout").
