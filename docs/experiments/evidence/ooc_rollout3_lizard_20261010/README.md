# Lizard-capable CTM inside rollout3 OOC MCTS vs §422 rollout3 (ledger §423)

Plan: [PREREG.md](PREREG.md) (review PASS at `bd991730`; launch gate met and run commit frozen at `cf801ef2`).
Code `cd405b4c`, `one_combat` sha256 `39cdac96…`, candidate fast CTM
`selfplay/models/combat_transition_deepsets_pathb_r2_lizard.native` (`c6d56bbc…`), manifest `64da1776…`.
All 16 workers' `FROZEN.txt` name the same run, code, binary and model. Seeds 70000000–70000127 (the §422 cohort); control =
§422 `rollout3` results, after the [rerun of seed 70000000](RERUN-422-70000000.md) matched them byte for byte.

## Validity

128/128 units rc=0, no `[bestbench-seed-failure]`, no restarts, 128/128 pairs. Every §422 file read matches §422's
`data-sha256.txt`. All 128 logs print `[ctm-research-candidate] candidate_id=pathb-r2`, the candidate `combat_model`,
`active_lizard_correction=1`, `leafValue native`, `leafCombats 3`, `prior policy` and `simulations 2048`; every run
reports `lizardSupportFailures` 0. Hashes of the files the analysis reads: [data-sha256.txt](data-sha256.txt).

## Result ([report.json](report.json), `tools/analyze_rollout3_lizard.py`)

| | lizard | §422 rollout3 | §422 off |
|---|---|---|---|
| wins | 111/128 (86.7%) | 115/128 (89.8%) | 101/128 (78.9%) |
| boss deaths | 14 | 11 | 23 |
| seconds per run (1 CPU) | 1,075 | 936 | 57 |
| OOC decisions searched by MCTS | 97.6% | 80.2% | – |
| V4 fallback | 2.4% | 19.8% | – |
| support aborts per run | 0 | 21.8 | – |
| simulations per run | 125k | 105k | – |

- **Primary:** Δwin (lizard − rollout3) −3.1 pp, paired bootstrap 95% CI [−10.9, +4.7] → **NOT_SHOWN**.
  Discordant pairs 11 (lizard only) vs 15 (rollout3 only), exact McNemar p = 0.56.
- Δfloor +0.06 [−0.95, +1.11]; Δ end HP −3.4.
- Descriptive: lizard − off +7.8 pp [0.0, +15.6].
- The remaining 2.4% fallback has no support aborts (375 of 15,759 decisions).
- By §422 per-seed fallback share: >40% (13 seeds) lizard 11, rollout3 13; 10–40% (92) 79 vs 81; ≤10% (23) 21 vs 21.

## Reading

The fix does what it should mechanically: Lizard aborts fall from 2,764 to 0 and MCTS now searches 97.6% of decisions.
It does not win more runs. The point estimate is slightly negative, and the seeds that lost the most decisions to V4 in
§422 do not improve (11 vs 13 of 13). **Inference:** the V4 fallback on active-Tail states was not what limited
rollout3, and the composed Fairy/Brew pricing is no better than V4 on those states; a cost of about 15% more CPU buys
nothing measurable. 128 pairs cannot exclude a few points either way.

No default change (PREREG decision). The candidate stays a research artifact.

Raw data: `/mnt/project-files/ooc-rollout3-lizard/w01..w16/`.
