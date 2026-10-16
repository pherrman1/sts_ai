# §493 Arm C inside A20 Heart rollouts

**Primary verdict: `NOT_SHOWN`. Resource qualification: PASS.** All 32 fresh
paired sources (64 runs) completed. Arm C rollouts killed the Heart on 2/32 seeds,
versus 1/32 for the existing chain: +3.125 percentage points, paired bootstrap
95% CI [0, +9.375] pp, exact two-sided McNemar p=1.0. There was one C-only win,
zero chain-only wins and one shared win. This is too little discordant evidence
to establish improvement; no promotion, new distillation or cohort extension.

[Prospective protocol/amendment](PROTOCOL.md), [exact result](result.json),
[summary and custody](summary.json), [derived per-run CSV](results.csv),
[original unit receipt contents](unit-receipts.json), [frozen bundle](freeze-v2.json),
[build receipt](build-receipt-v2.json), [canary results](canary-result-v2.json),
[independent canary acceptance](canary-reviewed-v2.json),
[verification logs/receipt](verification.json).

Source was independently reviewed and frozen at
`53152577c1c1c1a70bd69581ea184e18a26b330e`; native code was unchanged from
`3c31c27641ecbe66859e4e1d7c162706a1edc2c8`.
Binary SHA256 `d13014727ca0e4385f449a6e7c4c9ee9de2b5652a5d680aa48c512c5bd079283`.
Both arms loaded exact Arm C weights (`eff2f74f…`) as tree prior. Control used
the existing `LEAF_POLICY=v4` heuristic/V4 continuation chain; treatment used the
new explicit `LEAF_POLICY=heart1` argmax on the same supported unique candidate
sets after mandatory rules, falling back to the unchanged chain when unsupported.
The legacy `prior` option still calls V4 and was not used.

Both arms received 0.25 thread-CPU seconds per OOC decision, checked between
completed simulations, with an 8,192-simulation safety ceiling and other stopping
rules disabled. This is the same completion-boundary CPU allowance, not a hard
cap or equal total CPU/run. Actual combat stayed exact-10k native Silver; CTM
rollout horizon remained three combats, native X2-B, Heart/key rules fixed.
Seeds `110162000..031`, three single-thread workers, counterbalanced arm order,
900 seconds/unit clamped to the remaining four-hour phase limit. No failures,
missing sources, replacements, retries, extensions, tuning or historical pooling.
Cohort wall time 854.38 seconds (14m14s); whole-process CPU 2,481.66 seconds
(41.36 core-minutes). All work ran locally; no cloud capacity was needed.

| Measure | Existing chain | Arm C rollouts |
| --- | ---: | ---: |
| Heart kills, primary | 1/32 | 2/32 |
| Mean final floor, descriptive | 30.875 | 33.281 |
| Reached Act 3, descriptive | 11/32 | 13/32 |
| Reached Act 4, descriptive | 6/32 | 4/32 |
| Nontrivial completed searches | 1,519 | 1,683 |
| Median completed simulations/search | 161 | 28 |
| Median search CPU | 251.50 ms | 254.74 ms |
| p95 CPU overshoot | 2.925 ms | 15.381 ms |
| Maximum CPU overshoot | 7.930 ms | 39.645 ms |
| Mean OOC search CPU/run | 11.944 s | 13.457 s |
| Mean actual-combat CPU/run | 24.807 s | 26.845 s |
| Mean whole-process CPU/run | 37.002 s | 40.550 s |

All nontrivial completed searches stopped on budget; no simulation ceiling hits
or support aborts. The resource thresholds passed unchanged. The treatment's
higher total CPU/run also reflects its different trajectory/decision count;
these are not equal-total-CPU runs. The large simulation-count difference shows
how little search this policy variant buys within the allowance, but does not
isolate a same-state per-inference cost effect.

Every model-prior build used Arm C: 169,267 control and 34,536 treatment builds,
zero fallbacks. Treatment executed 511,121 model-scored Arm C rollout decisions,
zero scoring fallbacks; control executed zero. Both had zero V4 policy-head
`prior_leaf_steps`. Boundary/singleton bypasses are reported separately and do
not masquerade as completed budgeted searches.

Version 1 completed one control canary, then stopped INCOMPLETE because the
validator incorrectly required a selected action for a normal no-search root
boundary. No treatment/cohort launched, no outcomes were inspected for tuning.
Its [original protocol](PROTOCOL-v1.md), [failure metadata](v1-stopped/canary-result.json)
and local bundle remain intact. A narrow reviewed validator repair recognizes
only the exact zero-attempt/simulation/stopping/no-action/no-execution boundary
signature. Malformed boundaries still fail. Version 2 used fresh canaries
`110161992/993`; both paired canaries and independent custody/resource reviews
passed before the cohort. No gate/model/native-code changes or pooling.

Verification: full Debug default-target build; 88/88 core/smoke tests (1062.75s);
final affected Debug checks 5/5 (4.68s); Release checks 3/3 (1.88s), including
six synthetic research tests and eight startup cases. The full suite started
before the final diagnostics-guard/log-only repair; affected checks were rerun
afterward. The scientific native implementation was unchanged by the validator
repair. Raw verification logs and hash receipts are included. Exact-head CI and
final publication review are recorded on PR #565.

**Interpretation:** the extra Heart kill and higher mean floor are exploratory
point estimates. Only one pair differs on the primary outcome. This pilot does
not qualify improved Heart strength, noninferiority, or a new default. It tests
greedy C rollouts at this allowance; sampling and larger allowances remain
untested. The previous §492 value-student result remains `NOT_SHOWN` and was
not used here. No AlphaZero-style policy iteration or model fitting occurred.

**ELI5:** C's choices may help some continuations, but they leave much less search
within the available time. Two wins versus one is not enough evidence to switch.

Raw run bundle and all original CSV/log/profile files are preserved at
`/home/philippherrmann/Documents/sts/sts_lightspeed/build/arm-c-rollout-heart-20261016-v2`.
The derived CSV and receipt contents here do not replace those hashed originals.

Knowledge impact: optional rollout/CPU-control contracts, §493 evidence and
maintained current research status; production defaults remain unchanged.
