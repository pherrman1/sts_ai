# Gen6 E A20 teacher follow-up: DESCRIPTIVE_COMPARISON_MEASURED

The authorized v2 follow-up completed all four fixed sources, with **14
supported matched states**, 224 redrawn Silver forecast fights and 14 exact
original-future controls. No unsupported selected states, invalid arm rows
or control mismatches occurred. The excluded canary passed with four matched
states. The exact cohort verdict is **DESCRIPTIVE_COMPARISON_MEASURED**.
This is a small descriptive diagnostic, not a population-winner or promotion
result. The incomplete first attempt is excluded.

## Identity, protocol and execution

- Clean reviewed producer: `48f0c0e51bf8742cdbf0fbaa6b4f38ff34667311`.
- Binary SHA256: `c6c8b7f146cdb932daa641b00bfee28c74fce4496389ad339feabf7e809b2944`.
- Freeze SHA256: `c2457a2415e239e26144efe91eeb4e6978a131b697ebe008a25bf001caa437be`.
- Gen6 **E**: `ca9bd7f25cd2fb5c3e82609c35077e1c55d40c3f9c3d27da8e87236997b33228`.
- CTM: unchanged PR #524 A20 candidate; all three pinned hashes in the freeze.
- [Prospective protocol](../PROTOCOL-V2.md): fresh canary `97150801`, cohort
  `97150810–97150813`, 600 CPU/900 wall seconds/source, two concurrent jobs,
  at most five attempts, no retries or extensions. Same 2k/10k conditions,
  K=8/weight 400/root bonus, paired independent futures and fixed source policy.
- Release build and seven focused CTests passed; final affected Python checks
  passed after review correction (21 analyzer tests, seven runner tests).
  Independent implementation/protocol review passed before the clean freeze.

| Source | Captured fights | Matched selected states | Final source floor | Process CPU seconds |
| --- | ---: | ---: | ---: | ---: |
| 97150810 | 27 | 6 | 51 | 88.16 |
| 97150811 | 15 | 4 | 24 | 52.77 |
| 97150812 | 5 | 2 | 6 | 8.94 |
| 97150813 | 7 | 2 | 8 | 23.92 |
| 97150801, excluded canary | 18 | 4 | excluded | 62.37 |

Total measured process CPU including canary: **236.16 seconds** (173.79 for
the cohort). Every source finished within the cap. All four original source
trajectories ended in death; these are paths for sampling combat entries,
not an A/B gameplay win-rate test. Only one source contributes Act 3 coverage.
The larger resource allowance was available but not needed by this fresh panel.

## Principal descriptive results

Each source has equal weight, as preregistered. HP is RAW persistent HP,
including combat-end healing, with death assigned zero. Forecasts are scored
against an independent original-future plain10k behavioral reference.

| Forecaster | HP RMSE | HP bias | Death Brier | CPU for forecast |
| --- | ---: | ---: | ---: | ---: |
| CTM analytic expectation | 9.246 | −0.114 | 0.014558 | 0.0795 ms |
| plain2k, four futures | 6.605 | −0.302 | 0.002604 | 0.587 s |
| gen6 E prior2k, four futures | 8.171 | −0.589 | 0.013021 | 0.622 s |
| plain10k, four futures | 6.397 | −1.297 | 0.016927 | 3.279 s |
| gen6 E prior10k, four futures | 8.276 | −0.802 | 0.005208 | 3.275 s |

CPU scopes differ: CTM is repeated input capture plus analytic expectation;
Silver is the sum of four `playoutBattle` timers, excluding copying, exit
callbacks and logging. The measured process totals cover overhead. No exact
end-to-end CTM/Silver CPU ratio is claimed. The CTM prepare-and-one-sample
timer averaged 0.0329 ms and is distinct from its 32 categorical draws.

The paired controller contrasts use the same redrawn future and planner seed
for each replicate, independently of the original reference. Positive HP
means the left condition retained more RAW HP; positive death means more deaths.

| Contrast | RAW HP difference | Death difference | Potion difference |
| --- | ---: | ---: | ---: |
| prior2k − plain2k | −0.286 | +2.083 percentage points | +0.010 |
| prior10k − plain10k | +0.495 | −2.604 percentage points | +0.073 |
| plain10k − plain2k | −0.995 | +3.646 percentage points | −0.036 |
| prior10k − prior2k | −0.214 | −1.042 percentage points | +0.026 |

The preregistered pooled summaries show the same directional contrasts:
prior2k − plain2k HP −0.821/death +3.571 pp; prior10k − plain10k
HP +0.696/death −3.571 pp. Each Silver condition has only 56 forecast fights:
plain2k/prior2k/plain10k/prior10k deaths were 9/11/12/10. These small counts
do not establish an underlying death-rate ordering.

## Interpretation and limits

**Observed:** plain2k gives lower HP error than CTM on this panel, while CTM
remains much cheaper. Going from plain2k to plain10k costs 5.59 times the
four-future search CPU and changes HP RMSE by only −0.208. Gen6 E at 2k costs
about 6% more CPU and gives no observed controller gain here; at 10k it gives
small positive HP/death contrasts, without a consistent advantage across
budgets. More simulations do not produce consistent outcome gains in these
few conditional fights.

**Inference:** plain2k is the first inexpensive Silver candidate worth carrying
into a separate OOC decision-value audit; this pilot gives no reason to pay
10k routinely or assume the prior helps at 2k. CTM remains the plausible
tool for broad cheap sampling, with exact Silver useful for selected audits
or labels. These are next-study choices, not qualified model/controller/default
changes or proof of stronger offline OOC teaching.

There are only four source clusters, uneven later-act coverage and four
Silver futures per state. Two early Act 1 sources contribute four states but
half the principal equal-source weight; that is the fixed weighting rule,
not a population-representative sample. The reference is plain10k behavior, not optimal play;
CTM/controller mismatch and Monte Carlo error remain. CTM32 and Silver4
categorical scores have different finite-sample sizes. No bootstrap, confidence
interval, significance claim, training, public-input sufficiency or OOC action
ranking verdict is made. Full forecast/non-HP/variance/per-source metrics are
in `cohort-report.json`, without selecting additional metrics after collection.

## Progress evidence

The new progress log makes phase cost visible. For the longest source,
`97150810`, the original trajectory consumed about **20.97 CPU seconds**,
CTM blocks **0.0209 seconds**, and all replay phases **66.79 seconds**.
Its slowest replay was plain10k on Donu and Deca, repeat 0: **2.69 seconds**,
32 decisions and 320,000 simulations. Completed data and active-replay records
were visible during execution, and all progress sequences/timers passed the
analyzer's consistency checks. This does not reconstruct the old failed source.

## Evidence and knowledge impact

`raw-outputs.tar.gz` preserves all top-level runtime files except the binary,
including complete CSVs, progress JSONL, manifests, latches, receipts, logs,
teacher/policy, freeze and reports. The binary and models remain in
`build/a20-teacher-comparison/gen6E-run-2/`; their hashes are frozen.
`execution-summary.json` records phase accounting and the slowest replay per
source. `SHA256SUMS` covers this packet. Independent outcome/scientific audit
passed, reproduced both reports and checked principal metrics from raw CSVs;
see `../checks/v2-outcome-review.txt`. The source/model identities and exact
seed commands are in the freeze and receipts.

Knowledge impact: the ledger and maintained research page record this completed
descriptive comparison separately from §472's failed attempt. Production
defaults and the frozen v2 protocol remain unchanged.
