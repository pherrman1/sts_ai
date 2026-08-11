# Searcher3 particle-count sweep

Date: 2026-08-10

## Decision

**Inference:** 128 particles is promising, but not confirmed for promotion. Keep
64 as the gameplay default and run a confirmation gate before changing it.

## Audit

`BattleScumSearcher3::step` samples exactly one `Belief` particle per MCTS
simulation. `Belief::sampleIndex` preserves the existing uniform/equal-weight
sampling and weighted fallback semantics; the new utilization counters only
record the selected index. Thus 1,000 simulations sample 1,000 particle worlds,
with replacement, rather than traversing every particle per simulation.
Particle construction and real-boundary filtering scale with particle count,
while the per-simulation determinization remains one sampled world. Fair-path
reuse carries the tree and belief between decisions when its existing reuse gate
accepts; it does not alter the sampling rule.

## Results

Fixed configuration: fair Searcher3, A0, 1,000 simulations, real-boundary
filtering on, 24 OpenMP threads, deployed 7k combat VNet alpha 0.3, policy tree
on, PVNet/dist-VNet off, paired seeds 93100–93131. The 64/128 extension used
fresh paired seeds 93132–93163.

| particles | seeds | wins | mean floor | mean HP | CPU s/run | global collapse | mean sampled fraction |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 64 | 32 | 9/32 | 42.344 | 10.750 | 29.732 | 14.98% | 91.1% |
| 128 | 32 | 14/32 | 41.469 | 14.875 | 28.606 | 13.22% | 90.9% |
| 256 | 32 | 11/32 | 41.312 | 15.062 | 28.549 | 11.27% | 89.8% |
| 512 | 32 | 11/32 | 41.750 | 16.812 | 29.227 | 10.28% | 81.1% |

The fresh 32-seed extension produced 18/64 wins for 64p and 24/64 for 128p,
with 18 paired win flips. Aggregate collapse rates were 14.64% and 12.93%;
mean CPU was 31.07 and 30.92 seconds/run respectively. This extension is
confirmation evidence, not a promotion gate.

Collapse reduction was monotonic, but gameplay was not: 128p was best in the
initial block, while 256p and 512p did not improve on it. Mean filter CPU rose
approximately 0.24, 0.46, 0.86, 1.68 ms at 64/128/256/512 particles; mean
belief initialization was 0.016, 0.030, 0.055, 0.105 ms. Utilization remained
high at 128/256, so there is no immediate evidence that 1,000 simulations are
starving the larger beliefs. No particle×simulation interaction arm was run.

## Limitations

The existing bestbench output does not record action histories. Paired win flips
are therefore reported, but decision-level action changes after divergent
trajectories are not. The 32-seed 128p advantage is suggestive and noisy; 64p
remains the default.

Artifacts: `build/particle_sweep_{64,128,256,512}{,_diag}.csv`,
`build/particle_sweep_{64,128}_ext{,_diag}.csv`, and
`tools/analyze_s3_particle_sweep.py`.

ELI5: More guesses made the belief less likely to run out of matching worlds,
but fewer than 128 guesses did not clearly make the agent stronger. 128 guesses
looked best in this sample, so it deserves a larger check; we should not change
the default based on this run alone.