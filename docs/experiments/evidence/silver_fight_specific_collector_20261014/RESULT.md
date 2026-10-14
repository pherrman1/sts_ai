# §467 Collector-specific Silver prior: result (2026-10-14)

Pre-registration `../PREREG.md` (sha 626db522), data run frozen at 1518989b, binary ad90e698, gen-4 prior 3ebeab9d.
Analysis code ft.py 603e1c3b, merge.py 5e95ff28 (as pinned).

## Data
4 workers (Philipp 09:23Z), 640/640 units rc 0, no stalls; seeds 95000000-95002559 each once; 282,417 roots in
7,968 recorded Collector fights (0 invalid); 261,348 multi-action roots after `pack --drop-no-fight`.
Merged with the 52,950 old Collector roots of the gen-4 pack: 314,298 roots (train 187,297 / val 63,423 / test 63,578).

## Primary (PREREG): old Collector fold-4 roots (9,711, the RESULT.md test set), fine-tuned minus gen 4
| run | d CE [95% CI] | CE gen4 -> ft | top-1 |
|---|---|---|---|
| **primary, lr 2e-4** | **-0.0125 [-0.0157, -0.0094]** | 1.4411 -> 1.4287 | 46.3 -> 46.8% |
| lr 1e-4 | -0.0123 [-0.0151, -0.0097] | | 46.3 -> 46.9% |
| lr 5e-4 | -0.0110 [-0.0150, -0.0071] | | 46.3 -> 46.6% |
| 25% of new train seeds | -0.0063 [-0.0088, -0.0039] | | |
| 50% of new train seeds | -0.0086 [-0.0115, -0.0059] | | |
| old data only (RESULT.md) | -0.0030 [-0.0039, -0.0020] | | |

Gate: d <= -0.0062 with CI below 0 -> **CANDIDATE** (about two gen-3 -> gen-4 steps on this fight).
Secondary, new fold-4 roots (53,867): -0.0189 [-0.0207, -0.0173], top-1 47.3 -> 48.4%. The CI treats the
unperturbed and perturbed copies of a seed as separate clusters (2 per seed), so it is slightly narrow.
Scaling (old test roots): 0 / 25 / 50 / 100% of new data -0.003 / -0.006 / -0.009 / -0.0125, not yet flat.

## Model
`model-collector467.pt`, native `combat_policy_mlp_collector467.txt` (128/64, same format as gen 4);
native parity pass (164 roots, max |logit diff| 1.3e-6). Fine-tune best epoch 6, 121 s on 4 cores.

## Next (needs Philipp's go)
Online Collector-only paired check: gen 4 vs this prior as the Silver tree prior in Collector fights only.
**Inference:** offline gains of this size have not always shown online (§460 gen 3 vs gen 1 NOT_SHOWN).
