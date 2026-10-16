# Frozen Arm C nonlinear value head (§496)

User authorized trying a nonlinear value head and asked whether more data is
needed and whether X2-B is the right target for Heart kills. This new bounded
development experiment preserves all §494/495 outcomes and frozen artifacts.
The baseline is §495 PR570 head `b36b8c965e4df7036c2911b009626bd746ee253c`.

## Hypothesis and one intervention

The existing frozen Arm C pooled representation may encode useful nonlinear
value information that its affine head cannot extract. Alternative: limited
source diversity, missing features or the bootstrapped target—not head
capacity—limits generalization. Replace only the offline value readout with
TRAIN-standardization → Linear(64,64) → ReLU → Linear(64,1), 4,225 parameters.
The original Arm C checkpoint, encoder, policy head and normalization are not
updated. No X2-B input, residual or imitation loss is supplied to this head.
X2-B is a comparator; the supervised target is the collected continuation mean.

## Reuse and custody

Reuse exactly the audited §495 pooled-feature cache SHA256
`78c2d95ead3b158eeb67e17d4df0874b727304597057525b3d3076e8a03632aa`,
parent result SHA `ccd9ca840b9601b8361dbeac14e5fa9d5fe80b543651878f8fb3dbba44db66df`,
and parent freeze SHA `8c0f03ceb73cb0075dc72d96711365e7f3c94612a2825426d920b531746692f9`.
Verify cache/row-custody bindings and the original completed §494 TV archive's
per-source archive/receipt/capture chain using the unchanged reviewed reader.
The ordered rows and coverage must match the audited parent exactly. No encoder
recomputation or new game seeds are needed. Other interrupted cohorts, old V4
targets, Opus targets, and §493 outcomes are excluded.

TRAIN remains 110164000..039 (40 sources, 18,570 rows, 663 groups), VALIDATION
110164040..047 (8 sources, 2,721 rows, 114 groups). The consumed TEST remains
retired: neither its archive contents nor its hash is read by this tool.
Original C checkpoint SHA must remain
`53739a4375380001fce0323935c187906b5c1d5efd65691f9d75f2dd8884e020`.
The cache includes the reviewed empty-choice companion repair; target rows were
unaltered and companion outputs excluded. Original encoder input limitations
(including ignored extra public battle/memory fields) remain.

## Fixed fit and learning curve

One architecture, two initializations (0,1), and fixed TRAIN prefixes of 10,
20 and 40 sources: exactly six fits. The smaller subsets are data-quantity
diagnostics only; **only 40-source runs may supply the selected model**.
Fit standardization using each TRAIN prefix only. Use equal-source raw MSE,
AdamW lr0.001 / weight_decay0.001, shuffled minibatches up to512, exactly1,000
optimizer updates per fit. Full validation every50 steps; select minimum raw
source-balanced VALIDATION MSE over only40-source runs/checkpoints, ties in
encounter order. Same optimizer-step budget makes learning-curve compute
comparable; prefixes are not randomized replicated dataset-size estimates.
No adaptive extension, architecture/optimizer grid, seed replacement or retry.

Local CPU/GPU allowed; two CPU threads, deterministic operations, float32
network, no TF32. Validation target/aggregation retains float64. External
`timeout --signal=TERM --kill-after=10s 600s` enforces one10-minute campaign cap,
with cooperative internal checks and exclusive fit-started latch. Freeze the
independently reviewed source, tool, runtime, corpus, original model and cache
identities before fitting and verify unchanged identities again before outputs.

Report complete fixed-grid history, train/validation MSE gaps and prefix curves,
clamped sibling concordance/regret vs X2-B and §495 affine head, and model hashes.
Preserve a full PyTorch head state plus exact JSON tensors/normalization buffers.
This new head is not loadable by the current affine-only native C loader; native
integration is outside scope. Result is **VALIDATION_ONLY** regardless of sign;
no fresh qualification, gameplay pilot, speed claim, default promotion or RL loop.

## Heart-target boundary

Executed OOC code uses the Heart objective for simulated terminal wins, but
nonterminal rollout3 continuations stop at X2-B. The labels are means of64
CTM/Arm C continuations, not observed full-run Heart outcomes. More sources can
improve estimation/generalization of this surrogate; more of the same targets
cannot establish Heart calibration. Eventual outcome-based value learning and
fresh outcome evaluation require a separately authorized protocol. X2-B fidelity
is not the objective, and beating it offline is not itself proof of Heart strength.

Knowledge impact: research status and evidence for nonlinear frozen-feature
readout and data-quantity diagnostics; no production or native behavior change.
