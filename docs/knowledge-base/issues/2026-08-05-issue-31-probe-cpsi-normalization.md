# Issue 31: probe_cpsi feeds C_psi unnormalized scalars + sigmoided quantiles

- **Status:** closed
- **Tier:** Critical
- **Last verified:** 2026-08-05
- **Source:** code review 2026-08-05; `probe_cpsi.py` vs `train_combat_cpsi.py`

## Symptom

`probe_cpsi.py` (producer of `build/strategic_tierb_probes.npy`, the 54-feature
block fused into the token-state net via `TOK_PROBES_FILE`) fed the C_psi model
**raw, unnormalized scalars** (no `scalar_mean`/`scalar_inv` z-score, while the
trainer normalized before every forward) and **sigmoided the quantile head**
output (the trainer's pinball loss operates on raw outputs, so the probe
q50/q05 slots were double-transformed, e.g. true q50 0.9 → sigmoid(0.9) ≈ 0.71).

## Evidence

- `probe_cpsi.py::run_inference` (scalars passed raw; `q = torch.sigmoid(out["quantiles"])`).
- `train_combat_cpsi.py:184-186` (z-score at train time), `:377-378,414` (stats saved).
- `train_combat_cpsi.py:282-283` (pinball on raw head outputs).

## Why it matters

All probe features consumed by the V4 token-state fusion MLP
(`strategic_tok_net.py`, `train_strategic_tok.py:51,209-214`) were
out-of-distribution and double-transformed, so §80's V4+probes A/B verdict and
`ooc_strategic_tok_probes.pt` are invalid as recorded.

## Candidate fix direction

Apply the saved `scalar_mean`/`scalar_inv` from the checkpoint before
inference; drop the sigmoid on quantiles; clip encounter ids to `[0, 127]`.

## Relevant code

- `probe_cpsi.py` (whole file)
- `train_combat_cpsi.py` (`scalar_mean`/`scalar_inv` save at export)

## Resolution (2026-08-05)

Fixed in the 2026-08-05 code-review working tree: `probe_cpsi.py` now loads and
applies the checkpoint stats, passes raw quantiles, and clips encounter ids.
See rerun-ledger row "probe_cpsi features" — §80 artifacts remain invalidated.
