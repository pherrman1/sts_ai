# Dynamic campfire price, stage 0b (N = 128): result (2026-10-28)

**Verdict: STOP under the frozen rule.** Gates (a) and (d) fail. At N = 128 the actEnd price separates Rest from
the best Smith by more than 2 paired SE at 44% of rest sites (gate 50%; 29% at N = 32). Only 26% of its
Rest/Smith disagreements with student_sel clear 2 SE (gate 50%; 12% at N = 32). Gates (b) and (c) pass again.

The main finding is that more rollouts shrank the gaps instead of sharpening them. The mean |Rest − best Smith|
fell from 0.030 to 0.024 Heart-kill probability, while the median SE halved (0.017 → 0.0097). Most of stage 0's
gaps were noise. At most rest sites the price is close to indifferent between resting and smithing.

## Run

- Frozen plan `942da294` (gates written before any result). Same binary as §695 (`38bd5a71`, sha256
  `46001555a23d53c8…`), run from a detached checkout of `38bd5a71`; student_sel `cf6bf7fb…`. All 128 `.env`
  files record `STS_EXECUTABLE_GIT_SHA=38bd5a71…`.
- Same 128 §683 MAP seeds (111374100–111374227), `STOP_AT_ACT4=1`, `STS_OOC_CAMPFIRE_PRICE_N=128`, 4 lanes
  (`run_all.sh`). No new seeds. The container restarted once; the 12 unfinished games were rerun from the start.
- **Trace check:** all 128 replays reproduce their §683 MAP trace (`trace_check.txt`, 128 MATCH).
- Same 732 priced sites in acts 1–3 as §695 (665 with a Smith); the same 45 forced-Ruby sites are unpriced.
- Raw rows: share `campfire-price-stage0/replays-n128-38bd5a71.tar.gz` (sha256 `5bb672660460028e…`) and
  `analyze-n128.json`.

## Gates (actEnd price)

| Gate | N = 128 | N = 32 (§695) | Threshold | |
| --- | --- | --- | --- | --- |
| (a) \|Rest − best Smith\| > 2 SE | 44.4% | 29.3% | ≥ 50% | FAIL |
| (b) Spearman(Rest − Smith, HP fraction) | −0.51 [−0.58, −0.45] | −0.44 | ≤ −0.2, CI < 0 | PASS |
| (c) price class ≠ played class | 31.2% | 32.8% | ≥ 10% | PASS |
| (d) Rest/Smith swaps > 2 SE | 25.7% of 175 | 12.2% of 189 | ≥ 50% | FAIL |

The rollout3 leaf price (reported, not gated): separable 57.3%, Spearman −0.54, disagreement 26.9%, swaps
separable 35.8% of 159.

## Same sites, N = 32 vs N = 128 (`compare.json`)

- Both prices pick the same class at 77.6% of sites; Rest − Smith correlates at 0.78.
- Of the 195 sites separable at N = 32, 97.9% keep their sign at N = 128. Separable sites are real; the problem is
  how few of them are disagreements.
- Median SE ratio 0.52 (theory for 4x N: 0.5).

## By HP band (N = 128)

| HP / max HP | Sites | Played: rest | Price: rest | Mean Rest − Smith |
| --- | --- | --- | --- | --- |
| < 40% | 105 | 100% | 70% | +0.017 |
| 40–60% | 155 | 85% | 53% | +0.004 |
| 60–80% | 197 | 43% | 38% | −0.008 |
| ≥ 80% | 242 | 7% | 14% | −0.024 |

## What is at stake (inference, model units, not causal)

Summed over the 175 Rest/Smith swaps, the price's |Rest − Smith| is 3.1 Heart-kill probability units across 128
games: at most about 2.4 pp Heart kills per game if the price were right everywhere, and 1.3 pp counting only the
45 separable swaps. That is the model's own valuation, not a measured effect. It is also at or below what a
1,024-seed paired A/B resolves (about ±2 pp). In the 40–60% band, where the bot rests far more than the expert
(85% vs 13%), the price is almost indifferent (+0.004).

## Interpretation

- **Scientific result:** STOP. A rollout price at this precision cannot pick Rest vs Smith reliably at most real
  sites, because the true gap at most sites is about 1–2 pp. Where it disagrees with student_sel the stakes are
  small. The bot's high rest rate at 40–60% HP looks cheap under this model, not a big leak.
- **Not tested:** whether a different value model (for example the CTM expectation, or a value head trained on
  rest-site outcomes) sees larger gaps. A campfire fork experiment (stage 1) would measure the causal effect
  directly but, given the ≤ 2.4 pp ceiling above, would need a very large sample.
