# §492 Corrected evaluation of the frozen Heart rollout student

**Verdict: `NOT_SHOWN`.** This is one user-authorized software-fault recovery
of §491 on the **same already-opened holdout**, not a fresh independent TEST.
The original `INVALID_TEST_EXECUTION` bundle, latch and failure remain intact.
[Prospective amendment](PROTOCOL.md), [exact output](test-result.json),
[gate/custody summary](result.json), [authorization](authorization.json),
[receipt](receipt.json), [freeze](recovery-freeze.json),
[selection](recovery-selection.json), [opening latch](recovery-test-opened.json),
[raw log](test.log), [verification](verification.json).

The recovery ran once under independently reviewed commit
`7834789511280c81295503dbbbb6154c7a12f18a`, using the normal corrected evaluator
with a 600-second cap. It returned zero in 8.77 seconds. Original producer source
remains `cbded890a06f4ec76ad72c8333d07df25ad54e5f`; only the evaluator variable-name
repair and documented custody references differ. Original and copied corpus,
model, runtime, binary, tool, build, selected-weight and vocabulary identities
were verified. Original custody was checked again after execution.
No new seeds, fits, tuning, reselection or additional recovery attempt occurred.

The fixed count MLP, initialization 0, epoch 22, blended 50/50 with X2-B,
retained 7,716/7,716 rows, 259 multi-action groups and all 16 sources
`110161048..063`. Every original coverage gate passes. Source means:

| Metric | Frozen student blend | X2-B | Required candidate gate |
| --- | ---: | ---: | --- |
| MSE against rollout target | 0.019559 | 0.043148 | Diagnostic only |
| Concordance | 0.618946 | 0.616721 | Gain at least 0.02: **fail** (+0.002225) |
| Decision regret | 0.025438 | 0.023040 | At most 0.90 × X2-B: **fail** (1.104×) |
| Regret-improvement 95% CI | [-0.007125, +0.002174] | — | Lower bound above zero: **fail** |
| Python encoding + inference + X2-B speedup | 1.493× | — | At least 4×: **fail** |

Prediction MSE fell 54.67%, but the action-choice improvement did not generalize
from VALIDATION. The regret point estimate is worse; the interval does not
establish either improvement or harm. A calibration/error reduction is not proof
of better sibling choices or stronger gameplay.

Measured rollout CPU averaged 944.39 µs per call. Tensor inference took 66.17 µs
(single row), feature construction 551.17 µs, and required X2-B 15.02 µs. The
14.27× tensor-only ratio omits necessary work; the complete measured Python path
is 1.49×. Batch-32 tensor time was 16.67 µs per row, also not an end-to-end/native
speed claim. Native speed is unqualified. A native port would not change this
model’s failed decision-quality gates.

Prespecified diagnostics remain descriptive: the frozen historical Opus §490
reference has MSE 0.024065, concordance 0.610301 and regret 0.026346; the scheduled
single-rollout baseline has concordance 0.553186 and regret 0.040440. The fixed
half-rollout hybrid has concordance 0.578109 and regret 0.037554. These diagnostics
do not select another candidate. BATTLE has just 132 rows from one source and
Match and Keep 28 rows from nine sources; no per-domain qualification follows.
No encoding superiority is established by this comparison.

The labels are 64-rollout3 surrogate returns ending in X2-B, not true Heart-win
probabilities. The schema's public/native parity is not qualified. No native port,
gameplay A/B, default promotion, policy iteration or cloud scale-up follows from
this negative candidate gate. Arm C was the tree prior only; V4 rollouts stayed
fixed. Heart/key collection remains enabled through the already-merged PR #562.

**ELI5:** the network predicts average rollout scores more accurately, but it
does not reliably choose better actions, and most of its Python cost is preparing
inputs. This selected student is not ready to replace rollouts.

Local recovery bundle:
`/home/philippherrmann/Documents/sts/sts_lightspeed/build/heart-rollout-distill-20261016-recovery-01`.
Weights and raw capture files remain preserved there and in the original V3 root;
they are not duplicated in Git. The original §491 tracked evidence is unchanged.

Knowledge impact: §492 records the recovery; maintained current research status
records the resulting gate failure and outstanding qualification boundaries.
