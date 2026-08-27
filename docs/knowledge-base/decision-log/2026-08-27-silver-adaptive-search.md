# Silver adaptive search allocation

Date: 2026-08-27

Baseline: PR #66 merge `9f2d67d71f095425457fdb2a91eb1a0a8660a85b`

Reviewed implementation SHA before gameplay: `3729624a683e66aba62f9f04c86c0fa80d10c08e`

## Decision

Test a single default-off two-tier Silver allocation rule: search to 1,000
simulations, compute the top-vs-second root visit-share gap, and continue the
same root to 3,700 total simulations when the gap is strictly below `0.094`.
The rule uses `STS_SILVER_ADAPTIVE=1` and
`STS_SILVER_ADAPTIVE_TOP_GAP=0.094`. It does not change Silver's evaluator,
selection, widening, reuse cap, OOC behavior, or hidden-information protocol.

## Offline evidence

The corrected PR #66 diagnostic collection contained 50 clean deterministic
joint roots. Candidate signals were evaluated one at a time:

| Signal | Benefit AUROC | Changed-action AUROC | Nonzero-regret AUROC |
|---|---:|---:|---:|
| top-vs-second visit-share gap | 0.775 | 0.852 | 0.685 |
| top child-Q gap | 0.758 | 0.837 | 0.642 |
| top visit share | 0.750 | 0.805 | 0.708 |
| visit entropy | 0.739 | 0.786 | 0.731 |
| legal-action count | 0.699 | 0.751 | 0.793 |

The selected gap threshold `0.094` is the coarse 40% escalation point. It
escalated 20/50 roots, captured 5/6 beneficial-escalation roots (83.3%),
missed 5/12 roots with 1k regret at least 0.1, and modeled 2,080 mean
simulations per decision. This meets the named objective of retaining at
least 80% of beneficial escalations at no more than 40% escalation.

On the fresh 8-seed shadow, the clean deterministic subset had 25 roots:

| Arm | Top-action agreement vs 3.7k | Mean regret | Median regret | Disagreement | Root-average simulations |
|---|---:|---:|---:|---:|---:|
| fixed 1k | 84.0% | 0.07236 | 0 | 16.0% | 1,000 |
| adaptive | 88.0% | 0.04649 | 0 | 12.0% | 1,590.6 |
| fixed 3.7k | 100.0% | 0.04562 | 0 | 0.0% | 3,700 |

The adaptive shadow used 7/32 sampled roots for escalation (21.875%); its
full-combat telemetry used 1,727,000 simulations over 998 private decisions,
or 1,730.5 per decision, with 270 escalations (27.1%). The corresponding
same-sample runtime controls were fixed nominal 1k: 1,387,000 simulations
over 1,011 decisions (1,371.9 per decision), 5.91 CPU seconds/run; adaptive:
16.11 CPU seconds/run; fixed nominal 3.7k: 5,231,800 simulations over 1,029
decisions (5,084.3 per decision), 24.42 CPU seconds/run. The nominal fixed
controls retain the repository's unchanged 3x boss multiplier, whereas the
adaptive rule is explicitly exact 1k/3.7k at every root; this runtime caveat
is why the root-level quality table is primary.

## Gameplay gate

The offline screen passed, so a 16-seed paired gate was attempted on seeds
102024--102039 with fair play, Searcher3, ordinary Silver, the same host,
thread count, model artifacts, ascension, and endpoint. The fixed-1k control
completed at 9/16 wins (56.25%), mean floor 47.5, mean ending HP 25.8, and
18.94 CPU seconds/run. The adaptive treatment aborted in both attempts with
`Silver live backend selection transaction: unsupported Silver card-select
task`; no valid treatment result exists. The first abort occurred on the
reviewed implementation SHA. A narrow uncommitted safety fallback was tested
and reverted after the same failure, so it is not part of the final tree.

This is a correctness failure for the live gate. It prevents attributing any
gameplay outcome to the allocation rule and means the rule is not promoted.
Supporting the encountered card-select surface would require a separate
semantic-bridge investigation, outside this bounded experiment. The prior
control also retained the native 3x boss multiplier while the adaptive arm
used exact 1k/3.7k budgets at every root, so that attempted gate was not a
budget-comparable fixed-budget comparison. A future paired gate must set
`STS_SILVER_EXACT_ROOT_BUDGETS=1` for both arms (with the same base `sims`
argument) to neutralize that unrelated multiplier.

The unsupported card-select task is therefore recorded as a separate live
integration blocker, not as evidence against the uncertainty signal or its
allocation rule.

## Checks and artifacts

Focused checks passed:

```text
silver_bridge_boundary PASS
py_compile_analyze_silver_adaptive PASS
analyze_silver_adaptive_selftest PASS
git diff --check PASS (only existing LF/CRLF conversion warnings)
```

The 16-seed control passed with zero conversion, semantic-resolution,
transaction, and knowledge failures. The adaptive treatment had no valid
result and therefore no win-rate comparison.

Raw artifacts are retained under the ignored `build-adaptive-release/`:

- `silver-adaptive-phase1b-20260827-root.csv` —
  `37CB10C28CA69F57B9F64C83F529CCC0F9E0BC5DB596FA1DB8BF27A117680F51`
- `silver-adaptive-phase1b-20260827-analysis-v3.json` —
  `CC0BCF7E7DA27E2B4F7828E1ACEA787FEDC890E58F6120EEEE61DAD67ED28652`
- `silver-adaptive-shadow8b-20260827-root.csv` —
  `5D8C5E5ADE167940BB85026661E9AB2AB2820C3525B929307B690FD25E9D10F4`
- `silver-adaptive-shadow8b-20260827-analysis.json` —
  `09716FEAC9AB89A8EA9F542D7B89387F9ADBA79E150D36C81F8879CA9A7BBEBB`
- `silver-adaptive-shadow8b-20260827.log` —
  `B00755133042D4557691ED53062F047D780AD7B2A534F2525EE4EE0D03D43902`
- `silver-adaptive-shadow8-fixed1k-exact-20260827.log` —
  `A8FF731C71FE3517DCE651A4CC5660AD9B378DC416B953B8136F22559BCEF0FD`
- `silver-adaptive-shadow8-fixed37k-exact-20260827.log` —
  `2DAF02EBF15062620F1A72BFB9D0D90699AA9815A1B27DDF949AA7654CF2A43D`
- `silver-adaptive-gate16-control-20260827-results.csv` —
  `BE837354544DA1831805FEA15E7684D15C2CB12619A9B12E8D9F4349250E5585`
- `silver-adaptive-gate16-treatment-20260827.log` —
  `F16989861C282369A0C3A4D3287BFBC468722CD07C0A5330DAFEADD246C92A67`
- `silver-adaptive-gate16-treatment2-20260827.log` —
  `2EC9CD8E2DA16E37BEB343C44B0FA2CEE1862352EE5133AF74F5F8D2AE2A2782`

## Verdict

**INCONCLUSIVE.** The single signal and rule pass the bounded offline screen,
but the paired live gate is invalid: the treatment aborted on an unsupported
card-select task and the attempted arms were not budget-comparable at bosses.
The rule is not promoted. Do not add a convergence controller or run a larger
gameplay sweep from this result. A future gate requires the separate
card-select bridge work, explicit exact root budgets for both arms, and the
focused reuse/sequential checks recorded by the review correction.
