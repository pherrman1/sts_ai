# Staged retained-root Silver threshold sweep

## Question and protocol

This is the follow-up to the current #199 retained-only `500 -> 10,000`
policy. The implementation is opt-in at reviewed source SHA
`41f26f8af92ebdb0b4f488cf1c9c5457fb057394`; production defaults were not
changed. Retained non-forced roots use cumulative checkpoints
`250,500,1000,2000,4000,8000,10000,20000,50000`. Fresh and one-action/forced
roots are held to 10,000. At each retained checkpoint the stop predicate is
`(N1-N2)/sum_i(Ni) >= tau_b`; thresholds are monotone non-increasing. The
50,000 endpoint is a terminal reference and is never an early stop.

The scalar discovery sweep ran every requested grid value as a constant
threshold across the pre-50k checkpoints, with `inf` as the endpoint sentinel:
each arm used the same fresh 32-seed block, 272--303, Ironclad A0, fair
Searcher2/native-OOC production configuration, four OpenMP workers, allocated
32,768-node reuse cap, base budget 10,000, and CTM adaptive budgeting,
convergence, OOC MCTS, and keys disabled. The separate discovery reference
ran exact 50,000-simulation roots with the same nine checkpoints and supplied
the offline action labels.

From the 2,952 retained non-forced discovery decisions, all monotone schedules
over the requested grid were enumerated offline. The three schedules maximize
mean simulation saving subject to checkpoint-to-50k action disagreement of at
most 1%, 2%, and 5%, respectively. The disagreement denominator is early
stops only; decisions that reach 50k have no early-stop disagreement.

## Discovery scalar arms, N32 each

| tau | wins | mean floor | mean HP | mean sec/run | Silver sims | exact reroot rate | cap pressure / rescued / cap fallback | peak RSS KiB | wall |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.20 | 22/32 | 46.9375 | 35.5000 | 20.686 | 112,759,000 | 8,573/13,146 = 65.2435% | 1,068 / 759 / 309 | 2,049,580 | 2:52.85 |
| 0.25 | 26/32 | 48.0000 | 41.0625 | 24.002 | 126,997,250 | 8,743/13,526 = 64.6337% | 1,375 / 955 / 420 | 2,025,120 | 3:16.55 |
| 0.30 | 24/32 | 47.9375 | 39.2812 | 26.400 | 136,694,750 | 8,647/13,489 = 64.1279% | 1,610 / 1,113 / 497 | 2,083,328 | 3:38.99 |
| 0.35 | 24/32 | 47.9375 | 33.9375 | 28.259 | 145,857,000 | 8,697/13,626 = 63.8218% | 1,843 / 1,268 / 575 | 2,085,152 | 3:50.37 |
| 0.40 | 24/32 | 47.2500 | 38.9688 | 30.125 | 154,448,250 | 8,397/13,330 = 62.9932% | 2,101 / 1,427 / 674 | 2,081,128 | 4:04.55 |
| 0.50 | 24/32 | 47.2500 | 38.5000 | 35.085 | 172,042,000 | 8,228/13,326 = 61.7347% | 2,552 / 1,712 / 840 | 2,212,708 | 4:56.09 |
| 0.60 | 22/32 | 47.8750 | 32.5938 | 38.234 | 185,837,000 | 8,069/13,317 = 60.5872% | 2,918 / 1,918 / 1,000 | 2,116,356 | 5:18.80 |
| 0.75 | 23/32 | 46.7500 | 34.4375 | 45.489 | 216,851,250 | 7,723/13,347 = 57.8675% | 3,725 / 2,356 / 1,369 | 2,132,324 | 6:16.45 |
| inf | 23/32 | 46.4375 | 36.9062 | 78.407 | 374,990,000 | 6,232/12,932 = 48.1831% | 6,967 / 4,409 / 2,558 | 2,143,792 | 10:52.95 |

The exact stop-budget distributions, all per-arm diagnostics, and raw logs are
in [sweep_summary.json](sweep_summary.json) and the `arms/` directory.

## Frozen Pareto schedules and held-out N16

| target disagreement | frozen thresholds for 250..50k | discovery mean sims | discovery mean saving | discovery early-stop disagreement |
|---:|---|---:|---:|---:|
| 1% | `inf,0.75,0.75,0.75,0.75,0.75,0.60,0.50,inf` | 19,610.60 | 30,389.40 | 19/1,933 = 0.9829% |
| 2% | `0.75,0.75,0.75,0.75,0.60,0.60,0.60,0.25,inf` | 16,548.95 | 33,451.05 | 42/2,190 = 1.9178% |
| 5% | `0.50,0.40,0.40,0.20,0.20,0.20,0.20,0.20,inf` | 11,689.87 | 38,310.13 | 117/2,350 = 4.9787% |

Held-out seeds 304--319 used the same configuration and a flat 50k reference.
The three policies were frozen before this run.

| arm | wins | mean floor | mean HP | mean sec/run | Silver sims | exact reroot rate | cap pressure / rescued / cap fallback | peak RSS KiB | wall | paired wins/losses vs 50k |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| flat 50k reference | 10/16 | 47.1875 | 34.5625 | 185.159 | 414,200,000 | 1,984/7,876 = 25.1905% | 5,217 / 1,571 / 3,646 | 2,248,448 | 13:41.47 | — |
| Pareto 1% | 8/16 | 42.6875 | 24.1250 | 42.725 | 99,191,000 | 4,354/6,912 = 62.9919% | 1,741 / 1,213 / 528 | 2,138,436 | 3:17.74 | 7 both, 1 policy-only, 3 ref-only, 5 both loss |
| Pareto 2% | 8/16 | 39.9375 | 22.6250 | 32.653 | 78,491,500 | 4,115/6,238 = 65.9667% | 1,433 / 1,090 / 343 | 2,110,216 | 2:31.00 | 8 both, 0 policy-only, 2 ref-only, 6 both loss |
| Pareto 5% | 7/16 | 41.6250 | 28.5625 | 21.760 | 57,546,500 | 4,390/6,372 = 68.8952% | 664 / 493 / 171 | 1,915,624 | 1:44.68 | 7 both, 0 policy-only, 3 ref-only, 6 both loss |

The held-out stop-budget distributions are in
[heldout_summary.json](heldout_summary.json). Every raw process exited 0;
conversion, semantic-resolution, transaction, and knowledge failure counters
were zero in the recorded telemetry.

## Decision

The staged runtime and the nine-arm compute curve are real and reproducible,
but the three selected policies do not pass a gameplay-quality promotion gate
against the held-out 50k reference in this N16 inspection: all three lose
paired wins overall, with lower mean floor and HP. **Do not promote staged
adaptive Silver or change the current #199 production default.** Keep the
existing 500→10k policy and the allocated 32,768 cap in production. The
50k-capable staged mode remains an experimental, opt-in research path.

This is a bounded N32-per-scalar-arm discovery sweep and N16 held-out
inspection, not a universal equivalence proof. The held-out run is a quality
screen; the discovery disagreement constraints are offline action-label
constraints, not gameplay guarantees.

Knowledge impact: maintained staged-search contract and experiment evidence;
no production policy change.
