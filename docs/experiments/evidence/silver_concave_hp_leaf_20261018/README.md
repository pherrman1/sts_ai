# Concave-HP Silver victory leaf, paired 3-fight continuations at A20 (2026-10-18)

Pre-registration: [PREREG.md](PREREG.md). Campaign for `tools/cloud/worker.sh`: [campaign.manifest](campaign.manifest),
[units.txt](units.txt) (240 seeds, 16 workers), [run_unit.sh](run_unit.sh); worker brief [BRIEF-worker.md](BRIEF-worker.md).
Analysis: `python3 tools/analyze_concave_hp_leaf.py docs/experiments/evidence/silver_concave_hp_leaf_20261018 OUT.json <extracted tars>`.

## Result: NOT_SHOWN (ledger §TBD)

All 240 units rc=0; `verify.txt` shows all 16 tars OK (`tools/cloud/verify_campaign.py`), hashes in `tars.sha256`,
raw tars on the share at `/mnt/project-files/silver-leaf-eval/endstate-ab/`. 2,651 states (130 terminal source
states dropped, 0 invalid rows). Analysis output: `result.json`.

| contrast (leaf copy − base, 3 fights, seed bootstrap 95%) | k = 2.7 (primary) | k = 1.35 |
|---|---|---|
| A20 floor model (`altFloor`) | **+0.057 [−0.141, +0.263]** NOT_SHOWN | +0.127 [−0.106, +0.367] NOT_SHOWN |
| A20 win model | −0.003 [−0.008, +0.003] | +0.003 [−0.003, +0.008] |
| survived the 3 fights | +0.008 [−0.005, +0.020] | +0.012 [−0.002, +0.026] |
| HP at the next battle | +0.10 [−0.76, +0.97] | +0.55 [−0.32, +1.43] |
| start HP ≥ 90% (n = 1,021), floors | +0.230 [−0.005, +0.486] | +0.199 [−0.055, +0.494] |
| start HP < 45% (n = 185), floors | −0.008 [−0.821, +0.786] | −0.289 [−1.146, +0.572] |
| pairs with identical outcome | 654 | 795 |

Descriptive prices under this policy (student_sel OOC, A20 floor model, ratio of means; HP slope 0.066 floors/HP
[0.047, 0.086]): non-Fairy potion **5.0 HP-eq [1.8, 8.1]** (formula 11), max HP **1.08 HP per point [0.53, 1.66]**
(formula 2), gold **0.011 HP per gold [−0.064, 0.070]** (formula 0.25). Win-model prices are uninformative (HP slope
CI includes 0). None of these was a pre-registered decision.

Smoke seeds 111197676–111197677 used; reviewer seeds 111197680–111197682 used.
