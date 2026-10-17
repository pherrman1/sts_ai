# §503 Heart-outcome collection round 2: raw deliveries (data-only branch, never merge)

Copied from the project share `heart-outcome-round2/` after all 32 workers finished (2026-10-17).
Index: `heart-outcome-round2/DELIVERY-INDEX.json` (sha256 02c59f5bc966839e7704629d0227537275e3131b7b5e6a7f0e0e7d8ae601a2df),
identical to `docs/experiments/evidence/heart_outcome_round2_20261017/delivery-index.json` in PR #589.
`heart-outcome-round2/SHA256SUMS` covers every file under it.

- 2,048 sources: TRAIN 1,088 (148 Heart wins), VALIDATION 320 (33 wins), CONFIRM 640 (sealed).
- Sources with returncode 65 "root trace row does not match the live decision" were censored by a too strict
  root-trace check (Match and Keep hypothetical roots). Their outputs are complete; re-qualify them with
  `tools/heart_outcome_round2.py requalify` (fed1b9d or later). The index marks every TRAIN/VALIDATION source usable.
- `SEALED-confirm.tar.gz` archives stay sealed until Philipp opens CONFIRM once for a frozen candidate.
