# Exact Silver visit-lock prospective paired A/B (N16 smoke and N32)

Date: 2026-09-16
Implementation/source SHA: `8adbfe9f6b58145c853e53248fa5979a4e1991fa`
Release executable: `build/linux-gcc-release-ccache/one_combat`
Release executable SHA-256: `b282b7662b3e128d80cc6ce8701408369d50a63a0bf1389a465c65d7488c6b8d`

## Frozen protocol

The exact-lock implementation was committed and the Release executable was
built before either gameplay arm. Both stages used fresh, contiguous paired
seeds, Ironclad A0, project-fair Silver, native OOC, four workers, exact
10,000-simulation root budgets, allocated reuse cap 131072, CTM adaptation off,
old Silver adaptive mode off, convergence stopping off, OOC MCTS off, and keys
off. Control and treatment ran sequentially on the same executable and model
files. N16 used seeds 128--143; after its mechanism/gameplay checks passed,
N32 was run as an explicitly documented approximate-threshold extension on a
new block, seeds 144--175.

Control used flat 10,000 new simulations at every decision. Treatment enabled
only `STS_SILVER_EXACT_VISIT_LOCK=1`; fresh and one-action/forced roots still
ran to 10,000, while eligible retained roots polled the same private search at
0, 250, 500, 1,000, 2,000, 4,000, 8,000 and 10,000 new simulations. A stop was
accepted only for a complete valid retained non-forced root satisfying the
strict integer rule `topVisits - secondVisits > 10000 - used`.

## N16 smoke

| Measure | Flat control | Exact-lock treatment |
| --- | ---: | ---: |
| Wins | 11/16 | 10/16 |
| Mean final floor | 48.25 | 47.00 |
| Mean final HP | 30.69 | 33.13 |
| Wall time | 138.53 s | 90.83 s |
| Silver simulations added | 79,750,000 | 52,000,500 |
| Scaling decisions | 7,975 | 7,831 |

Treatment saved 34.80% of control Silver simulations and 34.43% wall time.
It produced 4,980 exact locks, including 362 zero-new-simulation locks. The
lock budget distribution was `0:362, 250:376, 500:283, 1,000:421,
2,000:622, 4,000:803, 8,000:1,376, 10,000:3,588`. There were 392 fresh,
7,439 retained, and 278 one-action/forced treatment roots. Every early stop
was retained/non-forced, strict, complete, and exactly accounted; failure
counters were zero. The treatment had two control-only wins and one
treatment-only win, so it did not trigger the specified gross gameplay stop.

The nominal N16 compute target was 35%; treatment achieved 34.80%, marginally
below that target. Because the protocol called the threshold approximate and
all mechanism/gameplay checks passed, N32 was run as an explicitly documented
extension without tuning or seed reuse. This was not a nominal 35% compute
pass.

## N32 qualification

| Measure | Flat control | Exact-lock treatment |
| --- | ---: | ---: |
| Wins | 24/32 | 22/32 |
| Mean final floor | 48.34 | 48.78 |
| Mean final HP | 48.47 | 42.44 |
| Wall time | 243.77 s | 166.77 s |
| Silver simulations added | 146,360,000 | 104,251,000 |
| Scaling decisions | 14,636 | 14,821 |

Treatment saved 28.77% of control Silver simulations and 31.59% wall time.
It produced 9,179 exact locks, including 465 zero-new-simulation locks. The
lock budget distribution was `0:465, 250:512, 500:462, 1,000:700,
2,000:1,094, 4,000:1,541, 8,000:2,815, 10,000:7,232`. There were 825 fresh,
13,996 retained, and 472 one-action/forced treatment roots. All 9,179 locks
satisfied the strict margin check; no fresh or one-action/forced root locked,
no summary was invalid, all budget identities held, and all bridge failure
counters were zero. The paired outcomes had two control-only wins and no
treatment-only wins.

The N32 result is **`LIVE_EXACT_VISIT_LOCK_REJECTED`** for this bounded gate:
the 28.77% simulation reduction is below the handoff's approximately 40%
compute requirement. This rejects the candidate for promotion under the
declared gate; it does not establish universal gameplay harm or invalidate
the exact current-root locking proof. The feature remains default-off.

## Reproduction and files

Run the validator from the repository root:

```bash
python3 docs/experiments/evidence/silver_exact_visit_lock_pair_2026-09-16/analyze.py
```

The validator checks seed completeness, source/executable/configuration
provenance, exact-lock eligibility and strictness, zero-lock accounting,
fresh/forced controls, failure counters, paired output, and both-stage budget
totals. `n16/` and `n32/` retain raw result CSVs, sidecars, scaling traces,
logs, time receipts, paired CSVs, and paired-analysis output. `summary.json`
contains the machine-readable validation result; `provenance.json` records the
frozen launch contract and artifact hashes.

No additional seeds, arms, tuning, shadow 10k searches, default changes, or
32k-reuse-cap qualification were run. The smallest next step toward any
default decision is not another cap qualification: the exact-lock candidate
must first clear its compute gate under a separately approved design.

Knowledge impact: current research status and experiment evidence updated;
runtime defaults and production Silver policy remain unchanged.
