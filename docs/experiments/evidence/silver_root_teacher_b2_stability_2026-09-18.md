# Silver root 25k-B teacher stability probe (2026-09-18)

## Scope

This is a bounded second-teacher probe on the existing 64 A/B/G/H ablation
roots. It generated one independent 25k teacher label per root with relabel
seed `20260919`, named B2. It collected no gameplay roots and performed no
model training or runtime qualification.

## Results

Top action means the action with maximum corrected root Q.

| Comparison | Result |
| --- | ---: |
| B versus B2 top-action agreement | 42/64 = 65.625% |
| A versus A2 top-action agreement | 50/64 = 78.125% |
| Mean B-choice regret under B2 | 0.916525 |
| Mean B2-choice regret under B | 1.205270 |
| B-choice regret under B2 on agreeing roots | 0.000000 (`n=42`) |
| B-choice regret under B2 on disagreeing roots | 2.666256 (`n=22`) |
| B2-choice regret under B on disagreeing roots | 3.506241 (`n=22`) |

The stronger-budget teacher is not more stable at this population: B/B2
agreement is 65.625%, below A/A2 agreement at 78.125%. On B/B2-agreement roots,
the mean best-versus-second Q margin is `4.086776` for B and `3.853905` for B2;
on disagreement roots it is `2.862787` and `2.438551`, respectively. The
margin is therefore lower on disagreement roots, but the label instability is
not confined to negligible margins.

## Harmful root

At root `14/2/23/36/3`, B selects Havoc while B2 selects Intimidate. B's
choice has B2-regret `6.211919`; B2's choice has B-regret `9.313845`. The
original 25k-B top-two margin is `8.563779`, while B2's is `2.939522`. This
confirms that the known A/A2-stable Seeing Red error is not resolved by simply
switching to one 25k label: the two 25k teachers also disagree there.

## Decision

Do not begin the grouped learnability probe or collect a larger training corpus
from hard single-teacher top-1 labels. The existing evidence supports using
within-root Q information only after a label-stability/target policy is
resolved; it does not yet authorize choosing B or B2 as clean training truth.

## Provenance

- Roots: `a63881c1cf9678252ba1aac9f4e74cb5babe233de443b9379bb6a969e11ea1f5`
- Original A/B teachers: `25cc009f0c4d2eacc03ed88dafaa195a1b4403b955facb545fb003acb0bb3de2`
- B2 labels: `571f726b36ada305635360981a94ffc01b064f874d5b2db95355e502d33fbd13`
- B2 relabel seed: `20260919`
- B2 teacher wall time: `70.602839` seconds total, `1.103169` seconds/root mean
- Single-budget helper source blob: `8b7c0cae38372a7b624d365f5d5d83fbfa639907`
- Single-budget helper executable SHA-256: `5df8846ec9470ae7dd6948b9c78b2e54e30fe611b7ba7ef50234d4ad3461a88b`
- Underlying Silver/root provenance passed into labels: `06d9de36d1c2e07c7e0420a0752ae9a4d7fd738e`

**Knowledge impact:** current research evidence only; no model, runtime,
gameplay, or default change.
