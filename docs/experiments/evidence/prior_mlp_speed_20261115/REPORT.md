# Faster g7f_E prior evaluation: measurements (issue #1052, 2026-11-15)

Question: can the g7f_E policy MLP (Silver root / tree prior and prior-playout argmax) be evaluated faster, with the
same model, and which speedups keep play bit-identical?

Baseline main 6126315 (after #1046 / #1047's exact kernel), preset `linux-gcc-release-x86-64-v3`. Container: 4 vCPU
Intel Xeon @ 2.1 GHz (AVX-512, AVX-VNNI) cloud VM; timings vary a few percent between runs on it.

## Data (no new game seeds)

- **Roots.** 72 boss / Act-4 prior-playout roots from §797's root rows (`/mnt/project-files/budget-ladder-roots/units`,
  seeds 111980000-111980255, data only): one random boss / Act-4 root of every fourth seed (Act 1 bosses 20, Act 2 11,
  Act 3 18, Shield and Spear 5, Heart 6) plus 12 Heart roots of other seeds. Searched with
  `one_combat rolloutpolicybench PREFIX 2000 asplayed 0` (fresh Gumbel k 16 + max backup 4 at 2,000 simulations, g7f_E
  root / tree prior, prior playouts; plays no game seed). Env: `STS_SILVER_ROOT_PRIOR` / `_ROLLOUT_ROOT_TABLE` = g7f_E,
  weight 400, tree prior K 8, active power features, the two engine fixes.
- **Recorded calls.** A local, uncommitted dump in `scorePolicyEdges` wrote predictPolicyMlp's inputs during those
  searches: every 61st call (40,552 calls, 196,075 edges, 4.84 edges per call) and, on 6 roots at 300 simulations, every
  call in order (40,367 calls).
- **Games.** Replays of §775's seeds 111378257 (died F28) and 111378263 (Heart kill) in §775's G16 + mb4 environment
  (`g16.sh` of `/mnt/project-files/combat-speed-20261114/raw`), baseline binary and new binary side by side, 4
  processes on 4 vCPU, with `STS_SILVER_GUMBEL_STOP_TRACE`.

Raw: `/mnt/project-files/prior-mlp-speed-1052/` (`raw/games_roots.tar.gz` sha256 c8fa773a..., traces, root results,
scripts; `prototype/` the dump hack and rejected variants as a diff, and the replay benches).

## Where a call's time goes (replay bench, exact kernel)

| part | µs per call |
|---|---|
| whole `predictPolicyMlp` (4.84 edges) | 2.8-3.5 |
| state layer (`policyMlpBase`, incl. the 1,766-feature nonzero scan) | 1.75-2.0 |

Inputs: 78.6 nonzero state features per call (all integers, max |x| 765), 6.9 nonzero action features per edge.
Consecutive calls of a playout change a median of 13 (mean 19.5) state features; 5% of consecutive pairs (new
playouts) change more than 48. In real searches (perf, 72 roots): state layer 15% + its nonzero scan 7%, per-edge layers
25%, feature extraction 8% of search CPU.

## Variants

| variant | exact? | per call (replay) | real searches / games | decision |
|---|---|---|---|---|
| nonzero list from the extractor's touched list (`combatNonzeroStateFeatures`) | yes, same list | - | roots 0.96-0.98x CPU, 72/72 searches identical to main (picks, sims, prior calls, playout actions); games 0.97x (95.3 vs 98.7 s) and 0.98x (418.0 vs 428.1 s) with 1,083/1,083 and 2,418/2,418 identical stop-trace rows | **adopted** (default) |
| FMA in the per-edge layers (`STS_SILVER_PRIOR_MLP_FMA=1`) | no | 1.16-1.22x; logits within 3.2e-6; 0 argmax changes on 80,919 calls | roots 0.92-0.95x CPU, all 72 picks equal at 2k; both games' search traces change (1,070 / 2,413 rows differ, 263 has 2,427 rows) | research option, default off; needs a whole-run gate |
| 16-wide AVX-512 kernels (runtime dispatch) | yes (0 of 40,552 calls differ) | 0.84-0.98x (slower) | - | rejected |
| software prefetch of the state rows | yes | no gain | - | rejected |
| skip all-zero state rows (1,003 of 1,766 rows are zero) | yes | - | never hit: no nonzero feature has a zero row | rejected |
| incremental state layer: exact double sum (rows rounded to 2^-24, integer features), updated by changed features | no (vs float), but history-independent | 1.09x on in-order calls, 0.71x on strided calls (before the touched list) | roots 0.97x CPU before the touched list, 1.06-1.12x (slower) after it; 4 of 72 searches change | rejected: the state rows are cache-warm in real playouts, so there is little to save |
| int16 layer 2 (dense madd_epi16, float layer 1) | no | slower in a scalar prototype | 1.3-7.2% argmax changes (activation scale 32 / 8) | rejected without quantization-aware training |

## Interpretation

- **Inference:** the exact kernel of #1046 is close to what this VM's vector units give. The state layer looked like
  the main lever in a random-order replay (58% of a call), but in real playouts consecutive calls touch the same rows,
  which are then in L1/L2; an incremental sum saves rows but adds bookkeeping of the same size.
- FMA is the only measured lever above ~5% and it is not exact: it changes search trajectories within a game, so its
  effect on Heart kills is unknown until a whole-run gate.
- Not tried: batching playouts in lockstep (a search change with its own gate), int8 / quantization-aware training.

Seeds: §797's 111980000-111980255 (root rows, data only); §775's 111378257 and 111378263 (replays). No new seeds.
