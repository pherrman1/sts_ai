# Silver rho-racing prospective qualification

Date: 2026-09-16
Baseline `origin/main`: `3f8ca7b59c2de1ba78a2d8bab0f280f849dd6845`
PR #204: merged and contained in that baseline
Implementation SHA: `ae97d56a74a9b70ac34b87478a87de5e3a9ee893`
Release executable: `build/linux-gcc-release-ccache/one_combat`
Release executable SHA-256: `c85579fd22a9c38475a3810062cabd0a15fe6d4bc33c8ea5f9ee0dee5a476eb3`

## Stage 1: frozen offline packet

The existing PR #202 packet was reused without collecting new trajectories:
seeds 112--127, checkpoints 250/500/1,000/2,000/4,000/8,000/10,000,
discovery 112--119, and evaluation 120--127. The primary population was
retained, non-forced roots; fresh and one-action/forced roots remained at the
maximum budget. Exact locking was replayed before every soft candidate.

| Candidate | Discovery soft stops | Discovery disagreement | Discovery all-decision reduction | Selection |
| --- | ---: | ---: | ---: | --- |
| A: `rho >= 0.75` | 794 | 0.8816% | 38.8441% |  |
| B: `rho >= 0.50` and leader stable for 2 checkpoints | 1,129 | 1.5058% | 43.0299% | selected |
| C: `rho >= 0.50` and leader stable for 3 checkpoints | 1,016 | 1.6732% | 42.2733% |  |

B was selected from discovery only: it passed the <=2% and >=100-soft-stop
requirements and maximized all-decision nominal savings. It was frozen before
reading the evaluation summary.

On evaluation, B produced 1,070 soft stops with 16 disagreements (1.4953%),
2,003 exact-lock stops, and 2,143 total primary early stops. All-decision
nominal reduction was 42.7237%, versus 34.4918% for exact locking alone, an
incremental 8.2319 percentage points. Soft stops occurred at 500 (512), 1,000
(60), 2,000 (87), 4,000 (288), and 8,000 (123) new simulations. Room-level
disagreement was 2.3041% for bosses, 2.1978% for elites, 0.6494% for hallways,
and 0% for other rooms. This passed the declared offline gate as
**`RHO_RACING_OFFLINE_PROMISING`**. It is post-hoc engineering evidence, not a
pristine confirmation set.

## Stage 2: implementation

The default-off `STS_SILVER_RHO_RACING=1` mode implements the frozen B rule:
exact locking remains the first check, then a retained non-forced root may
stop when the integer visit margin satisfies `2 * (N1-N2) >= remaining` and
the same semantic leader has appeared at two consecutive positive-budget
checkpoints. Zero new simulations are exact-only. The mode owns exact locking
internally and rejects old adaptive mode, the separate exact-lock-only flag,
and paired/sequential diagnostic modes.

Focused checks cover default and rho option parsing, exact-only regression,
integer boundaries, zero/remaining-budget safety, fresh and retained roots,
exact-over-soft precedence, arbitrary budgets, sequential card-selection
transactions, and visit accounting. The first attempted live pair exposed a
missing runtime gate (`rho_racing_fired` was being computed with rho disabled);
that run was discarded. The gate was fixed, tested, the implementation SHA
was amended, and the Release binary above was rebuilt before the prospective
runs.

## Stage 3: N16 smoke

Both arms used Ironclad A0, project-fair Silver, native OOC, exact 10,000 root
budgets, allocated reuse cap 131,072, four workers, CTM adaptive off, old
Silver adaptive off, convergence off, OOC MCTS off, keys off, and seeds
176--191. The exact-lock baseline used only PR #204's mode. The treatment used
only the frozen rho mode; its sidecar reports the separate exact flag off
because exact locking is owned internally.

| Measure | Exact-lock baseline | Exact + rho treatment |
| --- | ---: | ---: |
| Wins | 11/16 | 11/16 |
| Mean final floor | 45.25 | 45.375 |
| Mean final HP | 30.50 | 32.8125 |
| Silver simulations | 46,126,250 | 41,544,000 |
| Wall time | 82.47 s | 73.20 s |
| Exact stops | 3,830 | 1,313 |
| Zero exact stops | 249 | 39 |
| Soft rho stops | 0 | 2,516 |

The treatment saved 9.9341% additional simulations and 11.2405% wall time
versus exact-only. Paired outcomes were baseline-only seed 176 and
treatment-only seed 182, for zero net additional losses. Fresh/retained/forced
roots were 371/6,146/325 for baseline and 374/6,198/340 for treatment; all
failure counters were zero. The N16 gate passed.

## Stage 4: N32 qualification

The new clean block was seeds 192--223. The three sequential arms used the
same frozen binary and configuration; only controller mode differed.

| Measure | Flat 10k | Exact-only | Exact + rho |
| --- | ---: | ---: | ---: |
| Wins | 23/32 | 25/32 | 20/32 |
| Mean final floor | 48.9375 | 49.21875 | 48.53125 |
| Mean final HP | 32.96875 | 33.96875 | 32.75 |
| Silver simulations | 150,990,000 | 103,112,250 | 89,270,750 |
| Wall time | 258.82 s | 177.52 s | 147.72 s |
| Exact stops | 0 | 9,681 | 3,067 |
| Zero exact stops | 0 | 692 | 74 |
| Soft rho stops | 0 | 0 | 6,515 |

Relative to flat 10k, exact-only reduced simulations 31.7092% and wall time
31.4118%; rho reduced simulations 40.8764% and wall time 42.9256%. Rho's
incremental reduction over exact-only was 13.4237% of exact-only simulations
and 16.7868% of exact-only wall time.

Pairwise wins were:

- rho versus exact-only: exact-only wins on 192, 197, 203, 205, and 218;
  rho has no treatment-only win, for 5 net additional losses.
- rho versus flat: flat wins on 192, 203, and 205; rho has no treatment-only
  win, for 3 net additional losses.
- exact-only versus flat: exact-only has treatment-only wins on 197 and 218;
  flat has no control-only win.

All seed, sidecar, schedule, budget, strictness, exact-priority, fresh/forced,
root-accounting, and bridge-failure checks passed. The result is
**`RHO_RACING_COMPUTE_PASS_GAMEPLAY_CONCERN`**: it met both compute gates, but
the paired gameplay point estimates show a clear adverse signal versus
exact-only. This does not establish universal gameplay harm, but it is not
strong enough to promote rho or replace the frozen #199 path. Runtime defaults
remain unchanged.

## Reproduction and artifacts

Run the validator from the repository root:

```bash
python3 docs/experiments/evidence/silver_rho_racing_2026-09-16/analyze.py
```

The raw `results.csv`, sidecars, scaling traces, logs, and time receipts are
under `n16/` and `n32/`; paired outcome CSVs and the machine-readable
`summary.json` are generated by the validator. `provenance.json` records the
baseline, PR dependency, executable, model bindings, seed blocks, common
environment, and arm differences.

No threshold, checkpoint, model, CTM, room/HP, RNG, or default tuning was done
after the first valid live seed. No further prospective seeds were run.

Knowledge impact: current research status and experiment evidence updated;
the rho mode and normal Silver defaults remain default-off.
