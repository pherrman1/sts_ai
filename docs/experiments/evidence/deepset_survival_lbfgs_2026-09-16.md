# Converged linear survival probe (2026-09-16)

Decision: **`S1_LINEAR_PROBE_DIAGNOSTIC`**. This is a convergence diagnostic,
not a new preregistered acceptance gate.

## Question

Does the frozen DeepSets survival gap in PR #211 persist after optimizing the
linear survival readout essentially to convergence? Arm A uses the existing
frozen Attention survival embedding; Arm B uses the existing frozen corrected
DeepSets embedding. No encoder was retrained, no nonlinear decoder was added,
and validation was evaluated only after fitting on TRAIN.

## Protocol and provenance

- Baseline after merged PR #211: `e82810f8486d4ad47b62b074ebcfdcb307fa9f17`.
- Full-batch PyTorch L-BFGS with strong-Wolfe line search, maximum 500 iterations,
  maximum 1,000 evaluations, history size 20, gradient tolerance `1e-9`,
  change tolerance `1e-12`, and identical L2 `1e-4` for both arms.
- Fresh A/B heads used the same initialization (`fd275d8d…322c5e`).
- TRAIN: `408,183` rows / `19,986` sources. VALIDATION: `50,406` rows /
  `2,496` sources. TEST encoding, inference, and scoring: `0`.
- Existing PR #211 embeddings and representation artifacts were reused;
  no new embedding generation or encoder training occurred.

## Results

| Metric | A: Attention | B: DeepSets | B relative to A |
|---|---:|---:|---:|
| Validation NLL | 0.059344385 | 0.079102747 | **+33.2944%** |
| Brier | 0.017767452 | 0.023381218 | **+31.5958%** |
| ROC-AUC | 0.980664 | 0.962402 | diagnostic |
| Accuracy at 0.5 | 0.975380 | 0.967980 | diagnostic |

The previous fixed-12-epoch probe had a `+40.2899%` NLL gap, so convergence
removed `6.9955` percentage points of relative degradation. The important
slices still regress: observed-death NLL `+37.6878%`, and low-pre-HP NLL
`+41.4150%` on `756` rows / `292` deaths.

The probes reached finite states after only `69` / `68` closure calls and about
`0.30` / `0.15` seconds. This makes the remaining gap unlikely to be explained
solely by the arbitrary 12-epoch stopping rule, while not proving that a
nonlinear decoder or survival-specific encoder cannot recover the information.

## Boundary

This result supports proceeding to S2, the matched tiny nonlinear `64→64→1`
ReLU survival decoder, before changing the encoder. It does not qualify or
reject any runtime architecture, and it includes no TEST, gameplay, OOC MCTS,
fine-tuning, native export, or promotion work.

**Knowledge impact:** current research status and experiment evidence only;
runtime defaults and qualified components remain unchanged.
