# Silver root ensemble-teacher audit (2026-09-18)

## Scope

This is a zero-search audit of the four existing independent teacher runs on
the same 64 ablation roots. It constructs visit-weighted action-Q ensembles:

```text
T20(a) = (nA(a) Q_A(a) + nA2(a) Q_A2(a)) / (nA(a) + nA2(a))
J50(a) = (nB(a) Q_B(a) + nB2(a) Q_B2(a)) / (nB(a) + nB2(a))
```

T20 is the candidate target and J50 is the independent judge. No replay,
gameplay capture, teacher generation, model training, or runtime integration
was performed.

## Results

| Audit | Result |
| --- | ---: |
| T20 versus J50 top-action agreement | 44/64 = 68.750% |
| T20 mean J50-regret | 0.534197 |
| Original A mean J50-regret | 0.495031 |
| T20 versus original A top-action agreement | 54/64 = 84.375% |
| T20/J50-agreement-root T20 J50-regret | 0.000000 (`n=44`) |
| T20/J50-disagreement-root T20 J50-regret | 1.709432 (`n=20`) |

On T20/J50-agreement roots, the mean best-versus-second margin is `3.120010`
for T20 and `3.057219` for J50. On disagreement roots it falls to `2.010023`
and `1.227338`. Disagreement is associated with smaller margins, but the
ensemble does not improve the aggregate J50-regret over the original A top
action.

## Harmful root

At `14/2/23/36/3`, T20 still ranks Seeing Red first, while J50 ranks Intimidate
first. T20's J50-regret is `3.034235`; the original A top action is the same
Seeing Red action and has the same J50-regret. The ensemble therefore does not
resolve the known harmful root.

## Decision

The proposed T20 ordering is not a sufficiently coherent target for the next
causal replay: it agrees with J50 on only 44 roots and is slightly worse than
the original A top action under J50 in this descriptive audit. Do not run I vs
A, train a model, or collect a larger corpus. Stop the current learned
root-ordering line pending a new target definition or evidence that addresses
the unstable/biasing Q estimates.

## Provenance

- Roots: `a63881c1cf9678252ba1aac9f4e74cb5babe233de443b9379bb6a969e11ea1f5`
- A/B labels: `25cc009f0c4d2eacc03ed88dafaa195a1b4403b955facb545fb003acb0bb3de2`
- A2 labels: `bec970927b5052392bcae188b497bffc95b19b4cc07deb9fb405ad07594acc71`
- B2 labels: `571f726b36ada305635360981a94ffc01b064f874d5b2db95355e502d33fbd13`
- Ensemble rule: visit-weighted corrected root Q, deterministic fingerprint
  tie-break only for exact equal ensemble Q.

**Knowledge impact:** current research evidence only; no model, runtime,
gameplay, or default change.
