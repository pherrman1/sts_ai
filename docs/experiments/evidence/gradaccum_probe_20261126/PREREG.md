# Proposal #3 offline probe: gradient accumulation x LR (pre-registered 2026-11-26 ~07:35 CET, before any arm ran)

Baseline: frozen ckpt 1635474 (amber_scratch, 128x4, net + AdamW state), live loss weights from its args.
Live LR at that ckpt = 3e-5 (3e-4 x anneal final 0.1), batch 1024, clip 1.0 (live grad norm ~3 => always clipped).
Prior evidence: gradient noise scale B_simple ~18.5k (gradnoise_20261125) >> 1024.
Data: Test B slices (no new seeds). Train: 200 uniform batches x 1024 rows = 204,800 rows drawn without replacement
from the 3,000 seen runs (430k rows, window ending at step 1635474). Every arm sees the identical batch sequence.
Eval: 300 fixed unseen runs (later window, ckpt 1679639 era), live total loss + parts, before / mid / end.

Run on the GPU during a training pause (07:52-08:07 CET); identical to the partial CPU run through batch 90.
Arms (equal rows, compute-neutral): A 1024 @ 3e-5 (control, live) | B accum 4 (4096) @ 6e-5 (sqrt LR)
| C accum 4 @ 1.2e-4 (linear LR) | D 1024 @ 6e-5 (LR-only control).

Metric: L = live weighted total loss on unseen (row-weighted mean over runs). Paired bootstrap over the 300 runs.
delta = max(0.25 * |L_base - L_A|, 0.0005 * L_base).
Decision:
- Accumulation helps (=> propose a 15-min live test to Philipp) iff the best of B/C has L_X <= L_A - delta AND
  L_X <= L_D - delta/2 AND the 95% CI of (L_A - L_X) > 0.
- LR alone helps iff L_D <= L_A - delta with CI > 0 and neither B nor C beats D by delta/2 (=> report; LR is a
  separate variable / own proposal).
- Otherwise: no measurable effect => negative result to ledger, no live change.
Guard: an arm whose final-outcome CE on unseen is > 0.5 % worse than A's cannot be adopted.
Limits: 204,800 rows ~ 2 min of live training; offline fine-tune on already-trained data; CPU fp32 (live bf16);
1024 batches as 4 x 256-row chunks (policy-loss normalisation per chunk).
