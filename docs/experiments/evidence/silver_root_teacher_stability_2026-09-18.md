# Silver root 10k-A teacher stability probe (2026-09-18)

## Scope

This is a bounded second-teacher probe on the existing 64 A/B/G/H ablation
roots. It generated one independent 10k-A teacher label per existing root with
relabel seed `20260918`. It collected no gameplay roots, used no Teacher-B
labels to construct the treatment, and performed no model training or runtime
qualification.

## Results

Top action means the action with maximum corrected 10k-A root Q, matching the
ordering definition used by the ablation's full and top-1 arms.

| Comparison | Result |
| --- | ---: |
| A versus A2 top-action agreement | 50/64 = 78.125% |
| A versus B top-action agreement | 49/64 = 76.563% |
| A2 versus B top-action agreement | 48/64 = 75.000% |
| A/B-regret mean when A and A2 agree | 1.679358 (`n=50`) |
| A/B-regret mean when A and A2 disagree | 1.291792 (`n=14`) |
| A2/B-regret mean when A and A2 disagree | 2.486354 (`n=14`) |

The A/A2 disagreement rate is therefore 21.875%: 10k-A top-1 labels are not
fully stable at this root population. The conditional means are descriptive;
they are not an independent generalization estimate.

## Harmful root

At the previously identified harmful root `14/2/23/36/3`, A and A2 both rank
Seeing Red first (`Q_A=52.560875`, `Q_A2=52.358209`). Independent B ranks and
selects Havoc (`Q_B=49.455004`), with A's and A2's selected top action carrying
the same B-regret `14.622866`. This root is stable across the two 10k-A
teachers but remains wrong relative to the stronger independent judge.

That result supports a two-part conclusion: 10k-A top-1 labels have meaningful
search noise across the full pool, and the largest known harmful example is not
explained by that noise. A direct learner of hard A top-1 labels would inherit
both sources of risk.

## Decision

Do not start the tiny learnability probe or collect a larger corpus yet. First
consider repeated-teacher consensus or a stronger-label target; the present
probe does not justify treating a single 10k-A top-1 label as clean ground
truth. The existing compact nonlinear interaction-based scorer remains a
possible future probe, but no model-training authorization is granted here.

## Provenance

- Roots: `a63881c1cf9678252ba1aac9f4e74cb5babe233de443b9379bb6a969e11ea1f5`
- Original A/B teachers: `25cc009f0c4d2eacc03ed88dafaa195a1b4403b955facb545fb003acb0bb3de2`
- A2 labels: `bec970927b5052392bcae188b497bffc95b19b4cc07deb9fb405ad07594acc71`
- A2 relabel seed: `20260918`
- A2 teacher wall time: `28.548079` seconds total, `0.446064` seconds/root mean
- Single-budget helper source blob: `df7c71820ddefff945d929c9123ff7ed8e4617a9`
- Single-budget helper executable SHA-256: `d9cbf414aa563eedab718413fadfaa6f6af81e6cb375ad059d4341ebbe56dae3`
- Underlying Silver/root provenance passed into labels: `06d9de36d1c2e07c7e0420a0752ae9a4d7fd738e`

**Knowledge impact:** current research evidence only; no model, runtime,
gameplay, or default change.
