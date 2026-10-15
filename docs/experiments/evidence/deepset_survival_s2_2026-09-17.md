# Nonlinear frozen survival decoder (S2, 2026-09-17)

Decision: **`S2_NONLINEAR_DIAGNOSTIC`**. The matched nonlinear decoder recovers
some of the S1b gap, but the remaining regression is still clearly large.

## Protocol

After merged PR #213 (`7370ccdd35a79e5b55991e646fe3587762f02718`), the frozen
S1b-normalized Attention and DeepSets embeddings were passed to identical
fresh decoders:

```text
Linear(64,64) -> ReLU -> Linear(64,1)
```

Both arms used the same seed, initialization, batch permutations, FP32 AdamW
recipe, 12-epoch limit, gradient clip, and earliest strict VALIDATION NLL
selection. Only decoder parameters were trained. TEST encoding, inference, and
scoring remained zero.

## Results

| Metric | A: Attention | B: DeepSets | B relative to A |
|---|---:|---:|---:|
| Validation NLL | 0.059702005 | 0.072428763 | **+21.3171%** |
| Brier | 0.017818585 | 0.021705111 | **+21.8116%** |
| ROC-AUC | 0.980277 | 0.969554 | diagnostic |
| Accuracy at 0.5 | 0.975459 | 0.969924 | diagnostic |

The DeepSets NLL gap improves from S1b's `+29.4618%` to `+21.3171%`, an
8.1447-point reduction. Important slices remain above the stop threshold:
death NLL `+17.6745%` and low-pre-HP NLL `+20.9588%` on `756` rows / `292`
deaths. Arm A selected epoch 10; Arm B selected epoch 12.

## Conclusion

Nonlinear decoding recovers meaningful interactions, but it does not make the
victory-distilled general DeepSets representation survival-competitive under
this matched decoder. With a remaining NLL/Brier gap above `10%` and similarly
large death/low-HP regressions, stop trying to decode survival from this frozen
general `z`. The next clean route is a survival-specific DeepSets encoder
trained on all TRAIN combats, including deaths, optionally with the Attention
specialist as a soft teacher.

No TEST, runtime, gameplay, OOC MCTS, encoder fine-tuning, native export, or
promotion work occurred.

**Knowledge impact:** current research status and experiment evidence only;
runtime defaults and qualified components remain unchanged.
