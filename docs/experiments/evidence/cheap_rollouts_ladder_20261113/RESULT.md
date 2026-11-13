# Cheap rollouts, stage 2: result (2026-11-13)

**Verdict: NOT_SHOWN for all five candidates.** At G16's prior-playout roots (boss rooms of Acts 1-3, Shield and Spear,
the Heart), no cheaper playout policy chooses root actions as well as the g7f_E prior playout run with fewer simulations
at the same CPU. Every candidate lies above the P1 frontier, with a 99 % CI excluding 0.

Pre-registration: [PREREG.md](PREREG.md). Analysis: [analyze.py](analyze.py) → [results/result.json](results/result.json).
Delivery: [results/verify.txt](results/verify.txt).

## Run

- Seeds 111980000-111980255 (§797's 256 games), run commit 855ec92e, code f9601609, binary 5a659bd8 (campaign.manifest).
- 256 / 256 units verified OK at rc 0, 0 dropped runs, sentinel 0 differing runs (play bit-identical to §797), student
  manifests match `students/`. 137 lane-hours on W1-W40, 15:33-17:50 CET.
- 42,814 roots in 237 runs (19 runs have no boss / Act-4 root); 154 roots dropped by rule (an unmatched or unvisited
  pick). Status OK, calibration OK.
- CPU check: the new asplayed:4000 arm lies on §797's frontier after scaling (Δ +0.001 [−0.031, +0.033]); median
  machine scale 1.085 over all runs (1.099 over the 237 runs with prior-playout roots; the 19 without carry 1.0).

## All roots (Silver-Q loss vs the played 16k tree; CPU per root; r = CPU / P1 16k)

| arm | loss | CPU s | r | Δ vs P1 frontier [99 % CI] | label |
|---|---|---|---|---|---|
| P1 1k / 2k / 4k / 8k / 16k | 1.308 / 1.148 / 0.984 / 0.853 / 0.766 | 0.15 / 0.29 / 0.57 / 1.14 / 2.27 | 0.06 … 1 | frontier | |
| greedy:16000 | 1.244 | 0.33 | 0.15 | (calibration: gap 0.477 [0.417, 0.542] 95 %) | |
| greedy:64000 | 1.315 | 1.44 | 0.64 | +0.485 [+0.403, +0.583] | NOT_SHOWN |
| tt:16000 (g7f_E once per playout turn) | 0.914 | 1.37 | 0.60 | +0.079 [+0.021, +0.140] | NOT_SHOWN |
| ft1:16000 (prior in first playout turn) | 1.106 | 0.76 | 0.34 | +0.166 [+0.100, +0.239] | NOT_SHOWN |
| st:16000 (32/16 student) | 1.009 | 1.22 | 0.54 | +0.162 [+0.095, +0.235] | NOT_SHOWN |
| sttt:16000 (student once per turn) | 1.033 | 0.84 | 0.37 | +0.110 [+0.043, +0.183] | NOT_SHOWN |
| ste:16000 (per-encounter students) | 0.984 | 1.22 | 0.54 | +0.138 [+0.079, +0.199] | NOT_SHOWN |

Share of the greedy→P1-16k gap left (g): tt 31 %, ste 46 %, st 51 %, sttt 56 %, ft1 71 %. No candidate reaches
r ≤ 0.35 together with g ≤ 25 %.

## By group (Δ vs P1 frontier, point [99 % CI])

| group | roots | tt | ft1 | st | sttt | ste |
|---|---|---|---|---|---|---|
| Act 1-2 bosses | 15,266 | +0.057 [−0.006, +0.118] | +0.105 | +0.104 | +0.019 [−0.034, +0.075] | +0.084 |
| Act 3 bosses | 15,185 | +0.083 [−0.017, +0.205] | +0.231 | +0.230 | +0.158 | +0.164 |
| Shield and Spear | 5,075 | +0.157 | +0.290 | +0.257 | +0.291 | +0.249 |
| Heart | 7,288 | +0.062 [−0.023, +0.160] | +0.077 [−0.063, +0.241] | +0.077 [−0.054, +0.232] | +0.075 [−0.077, +0.259] | +0.122 [−0.018, +0.304] |
| fold 4 (held out from student training) | 9,194 | +0.145 | +0.238 | +0.307 | +0.193 | +0.211 |

No group has a candidate below the frontier in its point estimate. The 99 % CI contains 0 at the Heart (all five) and
in Act 1-2 bosses for tt and sttt, so there those groups show neither better nor worse.

## Hypernetwork upper bound (Philipp's idea, offline, not in the PREREG decision)

`tools/cheap_rollouts/tiny_oracle.py` on fold 4 of the stage-1 captures ([results/tiny_oracle_fold4.json](results/tiny_oracle_fold4.json)):
a tiny model θ[key]·φ (key = card, upgrade, target; φ = 10 scalar context features) fitted per root on half of that
root's own playout states, scored on the other half. Top-1 agreement with g7f_E: tiny 62.9 %, key-only table 56.3 %,
32/16 generalist student 64.2 % (stage 1, all fold-4 captures: a different sample set; no CIs). This tiny per-root model
family (θ[key]·φ, 10 scalar features) shows no headroom over the distilled student, which already lost here; richer
per-context models are not excluded.

## Interpretation (inference)

- The prior playout's value is not cheaply separable from its cost. Policies that keep most of its fidelity (tt, st,
  ste) cost 54-60 % of it and lose more quality than halving the prior sims does (P1 8k: 0.853 at r 0.50 vs tt 0.914 at
  0.60). The cheap ones (ft1, sttt at ≈0.35×) lose more than P1 4k at 0.25×.
- Measured CPU ratios match stage 0 (st 0.54×, sttt 0.37×, ft1 0.34×). The 2.2 µs student call is not cheap enough
  against the rest of a prior-playout simulation (state copies, game steps), and student or turn-table play is
  measurably worse per sim.
- More greedy sims did not help (point estimates greedy 64k 1.315 vs 16k 1.244; no CI on the difference): with a biased
  playout, extra search may converge on its bias.
- The cheapest lever within boss rooms remains fewer prior-playout sims; that conflicts with §790/§792 whole-run
  evidence (bosses and Act 4 buy Heart kills), so no default change follows from Q alone.
- Caveat: the reference is the played prior-playout 16k tree, which favours P1-like picks (conservative for cheap arms,
  as pre-registered).

## Decision

NOT_SHOWN by the PREREG rule. No whole-run gate. The cheap-playout line (turn table, distilled student, per-encounter
student, first-turn prior, hypernetwork tiny models on these features) is parked. Seeds 111980000-111980255 were reused
(data only). Cost: 137 lane-hours on 40 workers + ≈3 CPU-h in the thread.
