# Attention FP16 AMP bounded optimizer-step confirmation

Baseline: `c13d5d94d6a2fe38bc9f55595bf4acde362eb43e`. This offline
implementation confirmation uses the requested training step on that baseline
plus the AMP implementation. Trainer source SHA-256:
`68f6463206f4881b6612a1dcd1320889e80f307f181cb6ab096c9f8c432760a2`.
No simulator execution, new data, TEST selection, or broad quality profiling.

## Protocol and provenance

- GPU: NVIDIA GeForce RTX 3060 Ti; PyTorch 2.5.1+cu121.
- Real prepared artifact: `/tmp/sts-phase2-attention-audit-20260913`.
- Corpus SHA-256: `74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde`.
- `prepared.npz` SHA-256: `2badbb85ccd8329bcb886d50ef8a0b9b1bd2c043fda9445de9f9c2e7a4b6f9a5`.
- Prepared manifest SHA-256: `13b2c91fd0ced713f8c429bbf8995ceb58b6e3e57d1555de42f5e67d7f9a389f`.
- Supported TRAIN rows only; training seed 20260912; 8 Torch threads.
- Batch 2,048; four warm-up steps, 30 measured optimizer steps per mode/family.
- Identical initial weights and batch membership/order in each FP32/AMP pair;
  initial-weight hashes and batch-order hash are in the raw JSON. Each mode
  recreates the model and resets the same training seed, including CUDA RNG.
- AdamW(lr=1e-3, weight_decay=1e-4), dropout, trimmed padding, losses, and norm
  clip 1.0 unchanged. CUDA float16 autocast covers forward/loss only;
  GradScaler starts at 16,384, unscales before clipping, then steps/updates.
- Complete step timing includes existing per-batch loss transfer to CPU and
  synchronizes CUDA at timing boundaries. Peak allocated memory is reset
  after warm-up and reported in decimal GB. FP32 runs before AMP in each pair;
  this is a short confirmation on a shared desktop GPU, not a latency survey.
- Game-seed count, ascension, simulations, searcher, OOC, and RNG regime:
  not applicable; entirely offline optimizer steps on prepared TRAIN arrays.

## Results

| Family | FP32 examples/s | AMP examples/s | Speedup | Step ms FP32 → AMP | Peak allocated GB FP32 → AMP |
| --- | ---: | ---: | ---: | ---: | ---: |
| Phase-2 | 19,112 | 37,489 | 1.962× | 107.16 → 54.63 | 1.318 → 0.921 |
| Point control | 18,938 | 40,870 | 2.158× | 108.14 → 50.11 | 1.316 → 0.920 |

Both exceed the prespecified >1.5× confirmation criterion. Each family's first
AMP optimizer step has finite loss and gradients, initializes optimizer step
counters to 1, and advances the scaler growth tracker to 1 at scale 16,384.
All 34 losses per family/mode are finite; final AMP scale remains 16,384.

## Raw evidence

The exact executed command (from the candidate worktree) was:

```bash
PYTHONPATH="$PWD" python3 /tmp/sts-attention-amp-confirmation-20260913/confirm.py \
  > /tmp/sts-attention-amp-confirmation-20260913/confirm.log 2>&1
```

Preserved runner, stdout, and full JSON:
`/home/philippherrmann/sts_sweep/runs/attention-amp-confirmation-20260913/`.

- `confirm.py` SHA-256: `d12f299970e018e28d156e35f01140c06f101d317f9bb312cf00b55d965eec56`.
- `confirm.log` SHA-256: `970f0308b2f6b52f03e8c0f7e753a0113e16aa53f854c7c22609fd963cf3dc16`.
- `result.json` SHA-256: `7e6c0c6e8ce01303a2c7cd36a9d3c956064a43b1a585fc5a7e476278dfc4772f`.

## Interpretation boundary

This proves bounded optimizer-step speedup and successful AMP updates on this
GPU. It does not prove bitwise equivalence, identical epoch selection or final
checkpoints, or scientifically equal quality. The accepted six-epoch
TRAIN/VALIDATION comparison supplied in the handoff was not repeated here and
supports only absence of obvious degradation. FP32 remains the historical
reproduction mode; future scientific candidate/control A/B runs must use the
same precision. Validation/TEST evaluators remain FP32.
