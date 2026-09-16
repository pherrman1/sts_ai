# Sequential Silver stopping diagnostic (2026-09-16)

## Decision

**`LOGISTIC_DYNAMIC_RULE_REJECTED`** for the predeclared logistic dynamic
controller. This is evidence about a possible future sequential controller,
not a gameplay-policy change or runtime qualification. Exact visit-lock
stopping and softer empirical racing remain open follow-up lines.

The held-out logistic controller did not stop any primary decision at the 1%
or 2% risk ceilings. At the 5% ceiling it stopped 55/3,778 held-out
retained, non-forced decisions, with zero observed disagreements against the
full 10,000-simulation action and only 0.5393% nominal simulation reduction.
The frozen #199 rule (`retained + 500 simulations +
top_two_visit_gap_share >= 0.2932885906040268`) stopped 1,621 held-out
decisions, with 40.7610% nominal reduction and 1.9124% action disagreement.
The logistic rule is therefore rejected as a useful replacement for #199.

The six requested offline follow-ups are included in `analysis.json`:

1. The exact visit lock `N1 - N2 > Bmax - Bused` is evaluated from integer
   edge-visit reconstruction. On held-out retained/non-forced decisions it
   stopped 2,003/2,422 decisions, with the budget distribution
   `250:704, 500:62, 1,000:100, 2,000:196, 4,000:307, 8,000:634,
   10,000:419`, 53.8026% nominal simulation reduction, and zero observed
   action disagreements. This is an offline mathematical lock check, not a
   runtime qualification.
2. The same exact-lock budget distributions and compute savings are recorded
   separately for retained/non-forced, fresh-root, and one-action/forced
   controls, for all, discovery, and held-out evaluation seeds.
3. The exact-lock savings are reported against flat 10,000 simulations; the
   held-out primary result is 53.8026% nominal reduction.
4. Held-out empirical action-change risk falls across
   `rho=(N1-N2)/(Bmax-Bused)`: 30.0730% for `0-.1`, 13.6264% for `.1-.25`,
   6.5986% for `.25-.5`, 2.7119% for `.5-.75`, 1.4963% for `.75-1`, and
   0% for `1-2` and `2+` (row-level descriptive rates).
5. The complete held-out `rho x consecutive-same-leader` table is recorded;
   for example, the `0-.1` risk is 35.1020%, 31.2769%, 26.0437%, and
   23.3929% for leader streaks 1, 2, 3, and 4+ respectively. No soft
   threshold was tuned or promoted from these slices.
6. The frozen #199 comparison remains the result above: 1,621/3,778 stops,
   40.7610% nominal reduction, and 1.9124% offline disagreement.

Sequential stopping remains open: exact locking is promising as an offline
mechanism, while an empirical-risk racing rule still needs an independently
specified, separately qualified design.

## Protocol and provenance

- Actual current-main baseline at task start: `c371f3c29ffab07096c71fc66a4ab930e9595952`.
  The requested `77a76167865d96df776fd80794695a6937fdac3f` was an older
  parent already contained in that current main and was not used as the
  checked-out baseline.
- Diagnostic source commit: `21111b7e6af73b7f8a770b45df3d7093b17b69dc`.
- Executable: `build/linux-gcc-debug/one_combat`;
  SHA-256 `982387c0fbd1920c7d11ccd1aa825f9350c22129d493d37319d0d5141dc40b62`.
- Ironclad A0, fair Silver, native OOC, normal policy/models, four workers.
- One arm only; exact 10,000 Silver simulations per root; cumulative
  checkpoints `250,500,1000,2000,4000,8000,10000`.
- Fresh source seeds `112..127`; discovery uses `112..119` and held-out
  evaluation uses `120..127`.
- Silver reuse cap `131072`, allocated cap mode; `STS_SIM_ADAPT=0`,
  `STS_SILVER_ADAPTIVE=0`, `STS_CONVERGE=0`, `STS_CONV_ROOT=0`,
  `STS_OOC_MCTS=0`, and `STS_COLLECT_KEYS=0`.
- Every live action was the final 10,000-simulation reference action. No
  dynamic stopping was executed in gameplay and no gameplay A/B was run.

## Collection validation

The stream contains 53,228 rows for 7,604 unique decisions. Each checkpoint
has exactly 7,604 rows; every decision has the complete seven-checkpoint
schedule. The raw internal `rootVisitsAfterSearch` counter equals inherited
visits plus the cumulative checkpoint budget for all 53,228 rows. There are
17,185 fresh-root rows, 36,043 retained-root rows, and 2,114 one-action/forced
rows. The final benchmark completed all 16 seeds (68.8% displayed win rate,
average floor 48.3, average ending HP 28.9).

Stage 1 descriptive risk-event rates for retained, non-forced rows were
11.7913%, 11.5242%, 10.1274%, 8.4634%, 5.7518%, and 1.9310% at the first
six checkpoints. Fresh roots were 24.2537% overall and one-action/forced
roots were 0%; those controls are not included in the quality claim.

Stage 2 fits only one standardized logistic regression on discovery
retained/non-forced rows before 10k. No alternative model or evaluation-set
threshold tuning was performed. The complete estimator output, exact-lock
budget distributions, rho risk tables, calibration, failure slices,
frozen-rule comparison, and hashes are in
[`analysis.json`](analysis.json).

## Files

- [`analysis.json`](analysis.json) — complete offline result and estimator.
- [`sequential.csv.gz`](sequential.csv.gz) — compressed raw diagnostic stream.
- [`sequential.csv`](sequential.csv) — uncompressed raw diagnostic stream.
- [`results.csv`](results.csv) and [`results.csv.meta.json`](results.csv.meta.json)
  — per-seed benchmark receipt and runtime sidecar.
- [`run.log`](run.log) — exact collection stdout/stderr.

Knowledge impact: current research status and experiment evidence updated;
the fixed #199 rule and all Silver defaults remain unchanged. A future
`dynamicSearch(session,maxBudget)` API is not introduced by this diagnostic.
