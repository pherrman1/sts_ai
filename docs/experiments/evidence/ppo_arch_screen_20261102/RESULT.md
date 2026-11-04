# PPO architecture screen (design B): result, 2026-11-04

Pre-registration: [PREREG.md](PREREG.md) ("Binding under B" governs; amendments up to 0fcc0abc, all K PASS).
Launch record: [screen.manifest](screen.manifest). Analysis: `analyze.py` on `archres.tgz` (the PC learner
directories' games CSVs, `loop.json`, `config.json` and stall files of the 5 arms, BASE, BASE_S1 and CRIT_PRE;
sha256 `1afb422c…23d5`, committed here as `archres.tgz`, store ref `ppo-xfer/arch` `_results/arch-results`), reproduced in the cloud from the bundle.
`result.json` holds the numbers.

**Verdict: no arm is PROMISING and none is WORSE. All five are NOT_SHOWN.** S1's architecture therefore stays BASE's
net (heart1-size, shared critic, no extra inputs or heads).

## Run
- **Authorization:** Philipp 2026-11-03 19:07 CET "Go mit 20 workern nach Screen 2".
- **Design B:** every arm forked from screen 2's BASE after update 30 (`state-0030.pt` `cd1c90c6…`, net + Adam +
  iteration), its construction applied (`ppo_cloud.py init --fork-dir`), BASE's iteration-30 games reused. The arms'
  own games are iterations 31-59 on screen 2's seeds (111485872-111500719), so every arm is paired with screen 2's
  BASE and BASE_S1, which are the controls (not rerun).
- **Binaries:** IN_DECK's actors ran `cf7d4bbb…` (defaa930 + P1's x3_deck diff only; review K's build gave the same
  sha); the other arms ran screen 2's `71cfd280…`. RUN_COMMIT 30529219 (build inputs pinned by 280702e8).
- **Pre-launch checks:**
  - Learner check: the flags-off fork's net-0031 was not bit-identical to BASE's (max |Δparam| 8.14e-4). The
    pre-registered fallback, a rerun of screen 2's own learner code (da82e08e) on the same update, gives 9.65e-4
    (a second rerun 1.07e-3), so the check PASSES via the fallback. The GPU learner is not bitwise reproducible.
  - Sentinel (IN_DECK binary, BASE net-0029 as stored and with x3 zero-init, 32 seeds of iteration 30): every
    trajectory line equal to screen 2's BASE (SENTINEL_OK). A cloud pre-check against 71cfd280 on smoke seeds
    111459990-993 also passed.
  - Cost rule (native forward, `heart1logitscheck`, one thread): IN_DECK 1.01×, DEPTH6 1.67× BASE; the other arms'
    actor net is BASE's.
- **Schedule:** 20 cloud actors and the learner on the PC (RTX 3060 Ti, `--micro-batch 192`), 2026-11-03 20:18 CET
  (first fork update) to 2026-11-04 02:01 CET (SERVE_DONE).
- **Incident:** at 21:51 CET the learner died with a CUDA out-of-memory error while another GPU process (≈2 GB,
  probably started by Steam) shared the 8 GB card. It was restarted at 23:05 CET with the same command (pid
  514403) and resumed every arm from its `state.pt`. The update that crashed (CRITIC_SEP iteration 38) had not been
  saved and was recomputed; no games were lost or replayed. The actors waited meanwhile.
- **Completeness:** all 5 arms 60/60 iterations; the 10,240 window seeds are identical in every arm and control.

## Stalls (combat > 1,000 decisions, counted as losses)

None in the five arms: no stall file was written for any arm (the bundle has `stalled_seeds.txt` only for screen 2's BASE_S1), and analyze.py counts 0 stalls each. Screen 2's BASE_S1 had 2 (111482055, 111493711); 111493711 is in the window, and the
sensitivity D drops it from every arm. It changes no verdict.

## Primary metric: Heart kills, iterations 40-59

Paired by seed against BASE over 10,240 seeds (111490480-111500719), 95% seed bootstrap (10,000 resamples). Noise
|BASE_S1 − BASE| = 0.61 pp. BASE 7.72%, BASE_S1 8.33%.

| Arm | Heart % | D vs BASE (pp) | 95% CI | Sensitivity D | Verdict |
|---|---|---|---|---|---|
| DEPTH6 | 7.98 | +0.25 | [−0.37, +0.89] | +0.25 | NOT_SHOWN |
| AUX | 7.75 | +0.03 | [−0.58, +0.65] | +0.03 | NOT_SHOWN |
| IN_DECK | 7.66 | −0.07 | [−0.67, +0.57] | −0.07 | NOT_SHOWN |
| VAL_SPARSE | 7.62 | −0.11 | [−0.71, +0.51] | −0.11 | NOT_SHOWN |
| CRITIC_SEP | 7.53 | −0.20 | [−0.82, +0.41] | −0.20 | NOT_SHOWN |

Every CI covers 0, and every |D| is below the noise floor. The CI half-widths (≈0.62 pp) are the screen's power: an
architecture effect smaller than ≈0.6 pp at 30 updates is not detectable here.

## Cost (actor seconds per part, window iterations, ratio to screen 2's BASE)

| Arm | median | p25-p75 |
|---|---|---|
| IN_DECK | 0.78 | 0.72-0.86 |
| DEPTH6 | 1.02 | 0.95-1.10 |
| CRITIC_SEP | 0.85 | 0.80-0.88 |
| AUX | 0.86 | 0.77-0.91 |
| VAL_SPARSE | 0.78 | 0.71-0.80 |

The ratios are below 1 for arms whose actors run BASE's forward exactly, so the containers of this screen were about
15-20% faster than screen 2's (Inference: different machines, as the PREREG anticipated). Against the four arms with
BASE's forward, DEPTH6's actors were ≈1.25× slower, consistent with the native 1.67× forward cost diluted by the
search's non-net work. By the pre-registered rule every arm passes (≤ 1.3); no arm is PROMISING, so the rule decides
nothing.

## Learner diagnostics

Median learn seconds per update: BASE 69, IN_DECK 65, AUX 65, VAL_SPARSE 65, DEPTH6 86, CRITIC_SEP 117. Approx-KL per
update 0.011-0.014 in every arm; policy entropy rose from 0.22 to 0.24-0.26 over iterations 30-59 in every arm
(BASE 0.236).

## Critic secondary (pre-registered, offline)

CRITIC_SEP, AUX and VAL_SPARSE vs BASE, CRIT_PRE as a reference row; §747 states rebuilt with `build_states.py`
(`meta.json` sha256 `03b0838c…`, 328,146 records), final `state.pt` critics scored with `ppo_train.py score` on the PC
GPU, `gates.py` raw mode, group `postfight`.

| Critic (final, iteration 60) | T1: −3 HP lowers V | T5: median \|1-HP price − 1\| (secant units) | positive 12-HP secant | Verdict |
|---|---|---|---|---|
| BASE | 0.734 | 1.99 | 17,687 / 20,191 | (reference) |
| CRITIC_SEP | 0.617 (−11.7 pp) | 3.25 | 16,532 | NOT_BETTER |
| AUX | 0.718 (−1.6 pp) | 2.22 | 16,730 | NOT_BETTER |
| VAL_SPARSE | 0.665 (−6.9 pp) | 2.42 | 16,502 | NOT_BETTER |
| CRIT_PRE (screen 2, reference) | 0.721 (−1.3 pp) | 1.94 | 18,174 | (no verdict) |
| heart1 (§747, for comparison) | 0.827 | 1.50 | 19,092 | |

No critic arm is CRITIC_BETTER: all three are less HP-sensitive than BASE's critic (T1 lower, T5 higher). Sigmoid mode
gives the same values to three decimals (the PPO values lie in −0.62..1.85 across the five critics, BASE's mean 0.19, a range where sigmoid changes these ratios very little). Value files:
store `ppo-xfer/arch` `_critic/values-<ARM>`; `gates.json` per arm reproduced from them in the cloud.

**Observation (Inference, not pre-registered):** every PPO critic after 60 updates is less HP-sensitive than heart1's
start critic (T1 0.83 → 0.72-0.73 for BASE and CRIT_PRE). On-policy training against a sparse 1{Heart} return seems to
flatten the critic's response to HP at post-fight states; separate trunks and sparse value targets flatten it more.
This matters for phase 4 (run-aware leaf): no PPO critic from these screens is a better leaf than heart1's.

## Decision
- S1's architecture = BASE's net; none of IN_DECK, DEPTH6, CRITIC_SEP, AUX, VAL_SPARSE is adopted.
- Per the amendment, the CRIT_PRE combination question does not arise (no PROMISING critic arm).
- No default change. Seeds: no new block (screen 2's 111485872-111500719 replayed by design); smoke seeds
  111459990-111459993 USED.
- Cost ≈ 74,000 games ≈ 115 core-h cloud + ≈ 5.7 h PC GPU learner (incl. the 1 h 14 min outage).

**Knowledge impact:** KB `research/a20-ppo-plan.md` (architecture row: net size/inputs/critic/aux not limiting at this
scale); ledger entry.
