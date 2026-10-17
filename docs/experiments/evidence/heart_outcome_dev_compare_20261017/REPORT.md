# §501 — development value-head comparison: result

**REPRESENTATION_LOSS_SIGNAL; EARLY_WEIGHTING_NOT_SHOWN; MORE_SOURCES_SIGNAL
(fragile).** Adding a 37-value public scalar/count block to the frozen Arm C
pooled features lowers VALIDATION visitation BCE by 0.0236 and raises AUROC from
0.669 to 0.725. Upweighting act-1 states does not fix early bias. The learning
curve still falls with sources, but its top end is noisy. Development evidence
on reused TRAIN/VALIDATION only: no TEST, encoder forward, game seeds, native
integration or default change. [Protocol](PROTOCOL.md) was committed (263025f,
secondary sibling note ae39f38) before any fit.

## Run

Source `ae39f38`, Philipp's machine (RTX 3060 Ti, 2 CPU threads, deterministic
CUDA float32, TF32 off), exit 0, 79.7 s wall (archive read 23.2 s, 14 fits plus
analytics 49 s). Tests 18/18 OK ([log](python-tests.log)). Arm A reproduces the
§500 selected treatment: 0.45341093 vs 0.453411 (|Δ| 6.8e-8). Custody: the §498
cache, normalisation, import audit and archive hashes are unchanged before and
after ([started](started.json), [command](command.json),
[raw artifact hashes](raw-artifacts.json), [result](result.json)).

## VALIDATION (360 sources, 56,704 states, 47 wins)

| Arm | Width | Visitation BCE | Brier | AUROC | Source-bal. BCE | Δ BCE vs A, 95% |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Constant 126/1080 | – | 0.49873 | 0.15551 | 0.500 | – | – |
| A equal | 64 | 0.45341 | 0.14116 | 0.669 | 0.35397 | – |
| B act-1 ×2 | 64 | 0.45169 | 0.14122 | 0.675 | 0.35196 | −0.0017 [−0.0092, +0.0055] |
| C pooled + public | 101 | **0.42983** | **0.13425** | **0.725** | **0.33688** | **−0.0236 [−0.0414, −0.0062]** |
| D public only | 37 | 0.44878 | 0.14011 | 0.660 | 0.35508 | −0.0046 [−0.0255, +0.0161] |

Intervals: 10,000 paired source-cluster resamples, descriptive, not adjusted for
checkpoint selection or reused validation. C's Brier delta −0.0069
[−0.0134, −0.0007]. TRAIN visitation BCE: A 0.382, C 0.345, D 0.405.

Early landmarks, mean bias in pp (landmark AUROC):

| Arm | Start | Act 1 floor ≥ 8 | Act 1 floor ≥ 16 |
| --- | ---: | ---: | ---: |
| A equal | −1.09 (0.525) | −2.32 (0.501) | −4.18 (0.514) |
| B act-1 ×2 | −4.85 (0.538) | −2.46 (0.534) | −5.15 (0.552) |
| C pooled + public | −2.69 (0.492) | −2.79 (0.584) | +2.25 (0.618) |
| D public only | −1.21 (0.478) | −0.83 (0.503) | +1.69 (0.561) |

B makes all three biases more negative, so it fails its rule even though its
BCE is within the margin. C's aggregate gain does not come with uniformly
smaller early bias: floor 16 improves (4.18 → 2.25 pp in absolute value), and
start and floor 8 get slightly worse. Early-act ranking stays weak in every arm.

Learning curve (arm A recipe, selected VALIDATION visitation BCE, draws 0/1):
135 sources 0.4909/0.4919; 270 0.4696/0.4643; 540 0.4476/0.4638; 1,080 0.4534.
The rule fires (mean at 540 is 0.4557, ≥ 0.002 above 1,080), but draw 0 at 540
beats the full fit. Most small-subset fits select their first checkpoint (step
100), so the fixed 2,000-update schedule with checks every 100 updates
under-resolves them. **Inference:** BCE clearly falls from 135 to about 540
sources. Whether 540 → 1,080 still helps is not resolved by two draws.

## Encoder audit, confirmed against silverbot 84ab3ea

Read-only check of `silverbot/network.py` on Philipp's machine matches the
protocol. Relic counters, the public battle encounter, memory-game slots and
act are not trunk inputs; act is only implied by floor and boss. The fixed
observation is HP, max HP, gold, floor, boss, toSelectCount, ascension and three
key flags. The value input is a masked mean over all observation and choice
tokens after `value_head_norm` (network.py:618–622).

## Interpretation (as pre-registered) and limits

The representation signal argues for an explicit scalar/count channel next to
the pooled features (or later trunk fine-tuning, which can also move the policy)
before relying on more data alone. D alone is not distinguishable from A, while C beats both,
so **Inference:** the two inputs carry complementary information. Set sizes and HP/gold, which mean pooling dilutes, are
plausible carriers (Unverified). This run does not decompose the 37 values. The
act-1 reweighting idea is not supported. Data still matters at the low end.

None of this qualifies a search leaf. §502 found the §498 head near chance at
ranking sibling actions. The four selected heads are exported in
[heads/](heads/) (JSON in the §498 head layout, SHA256SUMS) for §502's sibling
harness; that scoring is descriptive and changes no verdict here.

§502 scored the four selected heads on its 777 TRAIN+VALIDATION §494 sibling
groups (PR #582): concordance with 64-rollout means is 0.507 (A), 0.520 (B),
0.521 (C) and 0.530 (D), against X2-B 0.601 and one rollout3 0.565. Every
head − X2-B upper bound is ≤ −0.040. C's outcome-BCE gain does not carry over
to ranking sibling actions; no arm shows search utility. A candidate
built on arm C needs the fresh sealed confirmation cohort from the new
collection; the consumed §499 TEST is excluded.

Raw checkpoints and predictions stay in
`/home/philippherrmann/Documents/sts/sts_lightspeed/build/heart-outcome-dev-compare-20261017-v1`.
No independent review has run yet.
