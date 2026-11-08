# D1: Gumbel-root teacher data for the combat net (combat plan stage 2, 2026-11-08)

The D1 data set of the [stage-2 PREREG](../combat_net_stage2_20261108/PREREG.md). Philipp gave the go on 2026-11-08
at 10:54 CET with 40 workers ("lets go, but jsut use 40 workers instead of 8"). Seeds from the coordinator (10:55 CET):
111900000-111901023, smokes 111909990-111909999. No repo or PREREG use of either block was found before freezing.
Data generation only: no gameplay comparison, no default change.

## What

`one_combat silverazgen` as in `../combat_states_20261108` (the same `record_env.sh` plus `STS_AZGEN_GUMBEL_ROOT=16`),
at flat 16,000 simulations. Every fight of every run is played by production Silver under the Gumbel root
(`SilverSearcher::searchGumbelRoot`: Gumbel-top-16 over the g7f_E root prior, sequential halving, c_visit 50,
c_scale 1). That is the teacher of §770, which lost 0.88 HP per elite or boss fight less than production.
- Root rows carry the stage-0 fields plus `edges[].prior` and `gumbelChoice`.
- `run_unit.sh` additionally requires `"gumbelRoot"` in each run's manifest (rc 97 otherwise).
- 256 units of 4 natural runs (`units.txt`), queue schedule, 4 lanes per worker.

## Smoke

Seed 111869993 (stage 0's smoke block), code 5b597b0c, which has the same generator as f0262fd1:
- rc 0, 31 fights, 1,147 roots, about 0.9 s per root with the CPU shared.
- Every multi-edge row has priors and a valid `gumbelChoice`. See the PREREG.

Expected cost: about 1,024 runs × ~600 roots × 0.6-0.9 s ≈ 100-150 lane-hours, about 1-2 h on 40 × 4 lanes.

## Processing (after the run)

1. `python3 tools/cloud/verify_campaign.py docs/experiments/evidence/combat_net_d1_20261108 --extract <dir>`.
   - Units whose `.done` line has rc != 0 are excluded.
   - The tally by rc is reported.
2. `python3 -I tools/combat_net/pack_states.py D1.jsonl.gz <dir>/out/units/*/natural-*.jsonl.gz`, then
   `tensorize.py`, `train.py` and `gate.py` as in the PREREG.
