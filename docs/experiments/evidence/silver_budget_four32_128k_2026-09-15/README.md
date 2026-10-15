# Four Silver budget schedules at 128k lazy GC, paired 32 seeds

The user selected 128k lazy GC for this comparison and requested four fixed
schedules: flat 1k, 1/2/5k for normal/elite/boss, flat 10k, and 10/20/50k.
All four arms used `STS_SILVER_REUSE_CAP=131072`. No source or model changes
were made for the experiment.

## Frozen configuration and accepted design

Source checkout / runtime metadata SHA:
`53a3ba36cb58876f192167162587eacae7c89556`.
Same release executable byte-for-byte as the preceding cap comparison;
executable implementation `2b29e9723a00b9dc6fcea45507e4dcf86c968cde` passed
Linux GCC CI. Intervening commits changed evidence only. Both SHAs and binary
hash are recorded, rather than treating runtime metadata as build provenance.
Model hashes and final binary/model immutability checks passed.

Paired seeds **16–47**, 32 per arm, 128 whole-run executions total; A0, Ironclad,
project-fair RNG, keys OFF, native OOC, learned leaf OFF, OOC MCTS OFF, allocated
reuse, static fight budgets, Silver adaptive OFF and learned SIM_ADAPT OFF.
Four OpenMP workers; arms executed sequentially in the order shown below.
Only fight-budget values, caller base sims and output paths differ.
`STS_SILVER_EXACT_ROOT_BUDGETS=1` prevents the old extra boss multiplier.

Existing `fightSims` routes ELITE rooms to the elite setting and BOSS /
BOSS_TREASURE rooms to boss; other rooms, including event fights, use normal.
The authoritative budget routing is `apps/one_combat.cpp::fightSims` followed
by the exact-budget path in `SilverLiveBackend.cpp::configFor`. Every recorded
root adds exactly its configured simulations, including private transaction
subdecisions. Startup logs confirm the three configured room tiers.

Hypothesis: added compute or a targeted elite/boss schedule may improve
outcomes, with possible non-monotonic policy and memory/cap effects.
The four arms, seed set and analysis rule were fixed before launch. Report
all six paired comparisons; no tuning, extra arms or seeds after outcomes.
This is an exploratory budget comparison, not a default/model qualification.
These seeds were not in the preceding N16 cap comparison (0–15); no prior
outcomes were pooled. Prior cap/1k artifacts do not supply this matched
four-arm N32 configuration and sample, so new collection was required.

## Results

|Budget schedule|Wins|Mean floor|Mean final HP|Mean sec/run|Added simulations (M)|Cap fallback|Process RSS (GiB)|
|---|---:|---:|---:|---:|---:|---:|---:|
|Flat 1k|17/32 (53.125%)|47.4375|24.7500|2.6514|15.136|0|0.270|
|1/2/5k|20/32 (62.500%)|47.9062|35.5938|6.6184|31.432|0|1.205|
|Flat 10k|21/32 (65.625%)|48.5000|34.4062|31.3633|150.920|0|2.436|
|10/20/50k|24/32 (75.000%)|47.9375|38.8438|81.4606|313.860|252|4.341|

All four producer exits are zero, all 32 seeds occur once in each CSV,
and all budget/cap/RNG/model/metadata checks pass. All per-combat telemetry
conversion, semantic-resolution, transaction and knowledge failure counters
are zero. RSS is whole-process peak across four workers, not one searcher.

The 1/2/5k arm finishes one win behind flat 10k at about 21.1% of its average
runtime and 20.8% of added simulations. This is an attractive descriptive
cost/outcome point, not proof of equivalent quality. The highest schedule
has the most observed wins, three above flat 10k, at about 2.60 times average
runtime and 2.08 times simulations. Final HP mixes winners and losses, and
final floor also reflects the loss distribution; neither is root regret.

## All six paired outcome comparisons

A-only / B-only counts are discordant wins, with B the arm after the arrow.
Exact two-sided discordant-pair tests are included; the final column applies
Bonferroni correction across the six prespecified pairwise comparisons.

|Comparison A → B|Win difference (pp)|A-only/B-only|Exact p|Six-pair adjusted p|
|---|---:|---:|---:|---:|
|Flat 1k → 1/2/5k|+9.375|2/5|0.453125|1.000000|
|Flat 1k → Flat 10k|+12.500|2/6|0.289062|1.000000|
|Flat 1k → 10/20/50k|+21.875|2/9|0.065430|0.392578|
|1/2/5k → Flat 10k|+3.125|2/3|1.000000|1.000000|
|1/2/5k → 10/20/50k|+12.500|2/6|0.289062|1.000000|
|Flat 10k → 10/20/50k|+9.375|3/6|0.507812|1.000000|

None establishes superiority after accounting for six comparisons. Even
flat 1k → 10/20/50k has exact p=0.06543, adjusted p=0.39258. The existing
unadjusted paired-bootstrap interval for that comparison is [+3.125,+40.625]pp;
that favorable interval is not a simultaneous six-comparison gate and
does not override the small-sample exact/multiplicity uncertainty. All six
raw deterministic bootstrap/Wilson reports are preserved, not just favorable
comparisons. No root-regret or additional confirmation run was performed.

## Cap and resource behavior

Flat 1k and 1/2/5k have no cap-pressure candidates or cap fallback. Flat 10k
has two candidates under cap pressure, both rescued, and no cap fallback.
At 10/20/50k, there are 1,122 pressure candidates: 870 rescued and 252 retained
reachable-cap fallbacks. Maximum allocated nodes are 12,756 / 65,917 / 134,873 /
202,041 in schedule order. Search batches can overshoot the cap before reroot.
The highest schedule therefore combines added compute with more frequent
collection/fresh fallback; this is an operational comparison at fixed cap,
not isolated unlimited-memory budget quality. Dynamic dedup and fallback
continue successfully; the experiment does not replace graph-invariant tests.

Peak RSS is 283,156 / 1,263,848 / 2,554,200 / 4,552,240 KiB. Runtime and peak
RSS are descriptive measurements on this host. Trajectories, survival and
number of decisions differ, so sec/run is not fixed-work search throughput.
Sequential execution order, scheduling and thermal effects remain limitations.
No permanent memory infrastructure was added; each arm uses external time-v.

## Reproduction and knowledge impact

`provenance.json` records explicit environments, guarded commands, clean-source
SHA, binary/model hashes, seeds, timings and exits. `run.py` is the original
non-overwriting runner; do not rerun into preserved outputs. Raw result CSVs,
sidecars, compressed logs/decision CSVs, timing observations and paired-seed
CSV are preserved. `analyze.py` is seed-free and accepts compressed inputs:

```sh
python3 docs/experiments/evidence/silver_budget_four32_128k_2026-09-15/analyze.py
```

The six `<arm>_vs_<arm>.txt` files are generated by repository-root
`paired_analysis.py`, strict pairing and its fixed bootstrap seed.
Artifact hashes bind the packet; re-running the saved analyzer reproduces
summary and paired-seed files. No extra seeds, broad sweep, training, model
or frozen-teacher requalification. 128k is the chosen configuration for all
four arms; this study does not compare 32k or qualify its teacher dependencies.
Knowledge impact: exploratory budget/cost/cap research status and ledger;
no production budget or scientific model contract changes.
