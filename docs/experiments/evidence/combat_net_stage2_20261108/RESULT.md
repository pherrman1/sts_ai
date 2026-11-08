# Combat net, stage 2: result

Pre-registration: [PREREG.md](PREREG.md) (with amendment 1). Combat plan stage 2
([plan](https://claude.ai/artifact/HvTqKL592wjb21Zgb3Sho4)). Data run: [D1 campaign](../combat_net_d1_20261108/README.md).
All result files are in `results/`: the gate JSONs, plus `eval.json` and `log.jsonl` for every training run. The model
weights stay on the PC under `~/combatnet/<run>/model.pt`, with sha256 listed below.

## Data

- **D0:** stage 0's pack (sha256 `21e84331…`), 1,633,473 roots from 3,072 runs. Splits: 1,309,699 training rows and
  162,828 validation rows (h = 1).
- **D1:** campaign `combat_net_d1_20261108`.
  - Run commit 57413a53, code f0262fd1, binary 15d8c39b. 40 workers × 4 lanes, 2026-11-08 11:09–12:45 CET.
  - `verify_campaign.py`: 256 of 256 units OK, 0 missing, 0 bad, 0 duplicates, all from run 57413a53. All 1,024 runs
    are rc 0, so nothing was excluded.
  - Pack (sha256 `5b44a4bf…`): 1,024 runs, 24,335 fights, 569,059 roots (530,192 with more than one edge), 0 dropped,
    4,102 played actions matched by card copy.
  - Splits: 454,693 training rows (825 runs), 55,664 validation rows (99 runs), 58,702 gate-holdout rows (100 runs).
    Only `gate.py` read the holdout, once, after all training had finished.
- Tensorized on the PC: D0 1,633,473 rows, D1 569,059 rows.

## Training (PC, RTX 3060 Ti)

- **Code:** 47998bd2 plus #1012's device fix for the first three D0 runs (N_d0, noaux_d0, polonly_d0). ce1854ae for
  the w = 0.5 and 0.25 D0 runs. 30b212ee (= ce1854ae code) for D1 and the gate.
- **Settings:** seed 20261108, batch 256, AdamW at 3e-4 with one-cycle, bf16 autocast, length-bucketed batches.
- **Run length:** each D0 run is 3 epochs (15,348 steps, ~5.5 min). Each D1 fine-tune is 3 epochs (5,328 steps, ~2
  min).
- **Value weight (amendment 1):** sum of validation policy CE and value NLL on D0's h = 1 split.
  - w = 1: 3.249
  - w = 0.5: 3.216
  - w = 0.25: **3.172** → selected
  - Lowering w improved both heads, not only the policy.

| run | data | val policy CE | val top-1 (played) | val value NLL | death ECE | model.pt sha256 |
|---|---|---|---|---|---|---|
| N_d0 (w 1) | D0 | 1.2935 | 0.5180 | 1.9553 | 0.68 pp | `284e2090…41db` |
| N_d0_w05 | D0 | 1.2801 | 0.5270 | 1.9360 | 0.58 pp | `616c61d4…e663` |
| **N_d0_w025** (D0-only reference) | D0 | 1.2683 | 0.5361 | 1.9039 | 0.51 pp | `ce479413…e3b1` |
| noaux_d0 (w 1) | D0 | 1.3003 | 0.5125 | 2.0303 | 0.67 pp | `335e7a96…b40a` |
| noaux_d0_w025 | D0 | 1.2741 | 0.5318 | 2.0000 | 0.73 pp | `104682ee…3fdf` |
| polonly_d0 | D0 | 1.2496 | 0.5514 | (untrained) | | `085be0fc…a659` |
| **N_d1** (main net N) | D0 → D1 | 1.5311 | 0.5181 | 1.9686 | 1.08 pp | `ee405d52…9547` |
| noaux_d1 | D0 → D1 | 1.5342 | 0.5096 | 2.3845 | 2.01 pp | `8f462c13…c8f2` |
| polonly_d1 | D0 → D1 | 1.5251 | 0.5299 | (untrained) | | `3edda753…7d264` |

Validation rows: 162,828 for the D0 runs and 55,664 for the D1 runs. D1's policy CE is higher than D0's because the
targets differ: the Gumbel root's visit shares after sequential halving are spread over 16 sampled edges.

The transient value spike at step 6,000 (N_d0 at w = 1: validation value NLL 2.08 → 2.94 → 2.20) does not appear at w
= 0.5 or 0.25 with the aux heads. It does appear without them (noaux_d0_w025: 2.31 at step 6,000).

## Gate (D1 holdout: 100 runs, 58,702 roots; run-clustered bootstrap, 10,000 resamples, seed 20261108)

Main net N = N_d1, with `--ref N_d0_w025` (D0-only).

| check | N minus floor | 95% CI | pass |
|---|---|---|---|
| G1 policy CE to the teacher's visit shares, vs the g7f_E prior (54,773 multi-edge roots) | **−0.124** | [−0.131, −0.119] | yes |
| G2 value NLL, vs (encounter × HP decile) baseline (58,702 roots; net 2.110, baseline 2.271) | **−0.161** | [−0.229, −0.094] | yes |

**Verdict: STAGE3_GO.**
- The G2 baseline has 618 cells. 58,700 rows used their cell, 2 the encounter fallback and 0 the global one.
- G3 sanity: death rate 4.36% per root, ECE 0.79 pp. Reliability is close in bin 0 (53,820 rows, predicted 0.43%,
  observed 0.91%). It is too pessimistic in the middle bins, e.g. bin 5 predicts 0.55 against 0.44 observed and bin 6
  predicts 0.65 against 0.53.

### Descriptive: top-1 agreement with the Gumbel pick (`gumbelChoice`), same 54,773 roots

| net | top-1 | vs prior argmax (0.5082) | vs ref |
|---|---|---|---|
| N (N_d1) | 0.5114 | +0.31 pp [−0.12, +0.74] | vs N_d0_w025 (0.5162): −0.49 pp [−0.79, −0.19] |
| noaux_d1 | 0.5081 | −0.02 pp [−0.52, +0.49] | vs N_d1: −0.33 pp [−0.62, −0.04] |
| polonly_d1 | 0.5260 | **+1.77 pp [+1.34, +2.20]** | vs N_d1: **+1.46 pp [+1.16, +1.77]** |

- By room, N against the prior: monster 0.549 vs 0.544, elite 0.517 vs 0.515, boss 0.453 vs 0.452.
- polonly_d1 by room: monster 0.567, elite 0.533, boss 0.463.
- The gate also ran on the two ablations: noaux_d1 and polonly_d1. Both pass G1 (−0.122 and −0.131, the latter the
  best). Both fail G2: noaux +0.344 [+0.238, +0.450], and polonly +0.801 because its value head is untrained. These
  runs are descriptive only.
- **Not measured:** C++ inference time per root. There is no C++ inference path yet. Stage 3 has to measure it, and
  its equal-CPU design has to pay for it.

## Interpretation

- **N passes both floors by clear margins.** Its value head predicts the fight's end-HP class better than the
  (encounter × HP decile) table, and its death probability is calibrated to under 1 pp ECE. That is the input stage 3
  needs for a learned leaf or a risk rule.
- **The policy gain is in the distribution, not in the argmax.**
  - G1 measures cross-entropy to the teacher's visit shares. N matches that spread better than the g7f_E prior.
  - On the teacher's single pick, N's top-1 equals the prior's (+0.3 pp, not resolved), and the D1 fine-tune lowered
    it slightly against N's own D0 checkpoint (−0.5 pp).
  - The Gumbel pick includes Gumbel noise and is limited to the 16 sampled edges. Its top-1 agreement therefore has a
    ceiling well below 1 for any deterministic predictor.
- **The policy-only net is the better prior.** Without the value loss it gains +1.8 pp top-1 over the prior and +1.5
  pp over N.
  - Lowering w from 1 to 0.25 already helped both heads, but the shared trunk still costs policy quality.
  - Stage 3 should test the prior from a policy-only net and the leaf or risk rule from N, rather than one net for
    both, unless a single net is needed for inference cost.
- **The aux heads matter for the value head** (single seed). Without them, D1 fine-tuning made the value NLL worse
  than the baseline (+0.34), and the step-6,000 value spike returned. With them the value head is stable.
- Exploratory limits:
  - Single seed per configuration.
  - The value weight was chosen on D0 validation only.
  - The D1 teacher's pick is random, so top-1 numbers are lower bounds on agreement with the search's intent.

## Cost

- D1 generation: 256 units of 4 runs on 40 workers, 11:09–12:45 CET. The unit `.done` spans sum to 103 unit-hours.
- GPU: 6 D0 runs × ~5.5 min, 3 D1 fine-tunes × ~2 min and 3 gate runs, about 45 min in total.
- Tensorizing: D0 6 min, D1 ~2 min.
