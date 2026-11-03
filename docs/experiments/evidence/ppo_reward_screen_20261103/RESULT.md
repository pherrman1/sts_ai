# PPO reward screen 2: result, 2026-11-03

Pre-registration: [PREREG.md](PREREG.md). Analysis: `analyze.py` on `s2res.tgz`, which unpacks to
`s2res/<ARM>/games-NNNN.csv`, `loop.json`, `loop-0030.json`, `config.json`, `stalled_seeds.txt`, plus
`futility.json`, `result.json`, `serve.log` and `ram.txt`. The bundle was copied from the PC learner's run directory
after SERVE_DONE (sha256 `2f575565…f37a`, 920,139 bytes). `result.json` holds the numbers; re-running `analyze.py` on
the unpacked bundle in a cloud container gives an identical `result.json`.

**Verdict: CRIT_PRE (critic pre-trained on screen 1's games) is PROMISING, +0.74 pp [+0.18, +1.32], just above the
bar of 0.52 pp. PBRS_FLOOR, PBRS_STATE and ACT_BONUS are NOT_SHOWN.** No shaped or denser reward helped; all three
lean below the control.

## Run
- **Schedule:** arms frozen 2026-11-03 10:58 CET; learner served 10:59-19:52 CET (SERVE_DONE), no pause, no restart.
  The first `serve` call in `serve.log` exits with an argument error (`--keep-state` before the positional
  arguments); the corrected call started before any update.
- **Setup:** start net heart1 (CRIT_PRE: `critpre.bin` `94d0d1a3…`), combat K15, binary `71cfd280`, RUN_COMMIT
  `da82e08e`, 24 cloud actors (W1-W24, all WORKER_OK) and the learner on the PC (RTX 3060 Ti, `--micro-batch 192`).
- **Completeness:** all six arms are complete, 60/60 iterations. Every arm has 30,720 games with 512 distinct seeds
  per iteration, and the seed set 111470000-111500719 is identical in every arm (paired).
- **Futility look** (iterations 20-29, after update 30, `futility.json`): every arm CONTINUE (CRIT_PRE +0.99
  [+0.20, +1.78], PBRS_FLOOR +0.50, PBRS_STATE +0.30, ACT_BONUS −0.52 [−1.26, +0.24]; control 7.86%). No arm stopped.
- **Fork point for the architecture screen (#974/#978, design B):** BASE `state-0030.pt` sha256
  `cd1c90c6ec81e37dd1ce54b2691b8ff95b0ba249521c89fbc58f4174863728a1`, `loop-0030.json`
  `70d0a8cf40a6e32a4fdaac99ce6a687bd00ddeb866a9b4eff82efa930b0a0e2a`, `net-0030.bin`
  `f7fd6086e9073cf2599cb9c957e49e526fcd36f3c9598c85b97bf4c8e038a998`.

## Stalls (combat > 1,000 decisions, counted as losses)

Two stalled games, both in BASE_S1 (`traj-0023-p2`: 111482055, `traj-0046-p1`: 111493711), at most 1 per part, so no
arm is INCOMPLETE. 111493711 lies in the primary window; the sensitivity D drops it from every arm and changes no
verdict (largest shift < 0.01 pp).

## Primary metric: Heart kills, iterations 40-59

10,240 paired seeds (111490480-111500719). Control C = (BASE + BASE_S1)/2 = 8.03% (BASE 7.72%, BASE_S1 8.33%).
Run noise |BASE_S1 − BASE| = 0.61 pp, PROMISING bar (√3/2)·0.61 = 0.52 pp. 95% seed bootstrap, 10,000 resamples.

| Arm | Heart % | D vs C (pp) | 95% CI | Sensitivity D [CI] | Verdict |
|---|---|---|---|---|---|
| **CRIT_PRE** | 8.77 | **+0.74** | [+0.18, +1.32] | +0.74 [+0.17, +1.31] | **PROMISING** |
| PBRS_STATE | 7.89 | −0.14 | [−0.70, +0.42] | −0.14 [−0.69, +0.42] | NOT_SHOWN |
| PBRS_FLOOR | 7.71 | −0.32 | [−0.86, +0.23] | −0.32 [−0.87, +0.22] | NOT_SHOWN |
| ACT_BONUS | 7.53 | −0.50 | [−1.04, +0.06] | −0.50 [−1.05, +0.05] | NOT_SHOWN |

Four comparisons, no multiplicity correction (none was pre-registered). CRIT_PRE clears the noise bar by 0.22 pp, so
the PROMISING verdict is a narrow pass.

## Secondary

**Heart rate per 10-iteration block** (in-sample, sampled play at temperature 1; seeds are the same in every arm
within a block but differ between blocks, so a change between blocks is not paired):

| Arm | 0-9 | 10-19 | 20-29 | 30-39 | 40-49 | 50-59 |
|---|---|---|---|---|---|---|
| BASE | 7.97 | 7.93 | 7.91 | 6.97 | 7.56 | 7.89 |
| BASE_S1 | 8.22 | 7.60 | 7.81 | 7.42 | 8.61 | 8.05 |
| PBRS_FLOOR | 8.32 | 7.75 | 8.36 | 7.56 | 7.25 | 8.16 |
| PBRS_STATE | 8.05 | 8.11 | 8.16 | 7.48 | 7.89 | 7.89 |
| CRIT_PRE | 8.38 | 7.73 | 8.85 | 8.09 | 8.95 | 8.59 |
| ACT_BONUS | 8.30 | 7.60 | 7.34 | 7.07 | 7.58 | 7.48 |

Iterations 0-4 play heart1's policy in every arm (3 value-only warm-up updates; net-0003, used by iteration 4, still has
heart1's policy tensors, and the arms diverge from iteration 5) and give identical games: 8.91% on 2,560 seeds
(binomial SE 0.56 pp). CRIT_PRE has the highest rate in 5 of 6 blocks (not in 10-19).

**Training statistics** (`loop.json`, policy iterations):

| Arm | mean approx-KL | entropy first → last | value loss (it 40-59) | mean value / return at iteration 4 |
|---|---|---|---|---|
| BASE | 0.0113 | 0.215 → 0.236 | 0.0053 | 0.206 / 0.170 |
| BASE_S1 | 0.0120 | 0.215 → 0.260 | 0.0060 | 0.205 / 0.169 |
| PBRS_FLOOR | 0.0117 | 0.216 → 0.256 | 0.0054 | 0.143 / 0.088 (shaped) |
| PBRS_STATE | 0.0117 | 0.216 → 0.242 | 0.0057 | 0.143 / 0.088 (shaped) |
| CRIT_PRE | 0.0110 | 0.215 → 0.264 | 0.0063 | 0.143 / 0.147 |
| ACT_BONUS | 0.0110 | 0.215 → 0.268 | 0.0092 | 0.364 / 0.366 |

Every arm's policy moves by about the same amount (KL ~0.011 per update) and its entropy rises. At the first policy
update the control critic's mean value is above the mean λ-return by ~0.04 (heart1's critic was trained on the
original's reward and starts at ~0.57; 3 warm-up iterations do not close the gap). The λ-return bootstraps from that
critic, so the gap to the Monte Carlo target is larger than 0.04: iteration 4's games are identical in every arm, so
its Monte Carlo return is the same for all, and CRIT_PRE's λ-return there is 0.147 vs the controls' 0.170. CRIT_PRE's critic is calibrated from the
start. By iterations 40-59 every critic is calibrated in its mean (mean value = mean return within 0.003).

## Interpretation (Inference)
- **Screen-level hypothesis: a calibrated critic start helps; a reshaped reward does not.** PBRS changes only what
  the critic has to fit (V − Φ). With both potentials the critic still starts off (PBRS arms at iteration 4:
  value 0.143 vs shaped return 0.088), and the arms do not beat the control. The act/key bonus adds a target that is
  not the Heart kill and leans worse.
- **Whether CRIT_PRE learns beyond heart1 or only declines less is open.** Its last-third rate (8.77%) is
  −0.14 pp from heart1's rate on the warm-up seeds (8.91%), and the control's (8.03%) is −0.88 pp. Both comparisons use
  different seeds (unpaired); with binomial SEs of ~0.56 pp (warm-up) and ~0.27 pp (last third) alone, the control's
  gap is ~1.4 SE, before any seed-block variation. Both readings fit the data: (a) the controls drift down under a
  miscalibrated early critic and CRIT_PRE avoids that, or (b) all arms stay near heart1 and CRIT_PRE gains a little.
  G1 (final net vs heart1 on fresh paired seeds) decides.
- Whole-run noise is again ~0.6-0.8 pp (screen 1: 0.82), so single-run differences below ~0.5 pp stay unresolved.

## Decision
- **CRIT_PRE is the candidate critic setup** for the next pilot, as pre-registered. Its net is not used anywhere
  before G1 confirms it: CRIT_PRE's `net-0060` vs heart1, policy alone, Silver 1,000, 2,048 fresh paired A20 seeds
  (~23 core-h; needs Philipp's typed go and new seeds).
- **Rewards:** stay `heart` (1{Heart}). PBRS with the floor or state potential and the act/key bonus are not adopted.
- **Architecture screen (design B):** forks from BASE after update 30 as planned; its PREREG notes that a PROMISING
  CRIT_PRE needs an amendment that restates CRITIC_SEP and VAL_SPARSE against the pre-trained critic start.
- No default change.
