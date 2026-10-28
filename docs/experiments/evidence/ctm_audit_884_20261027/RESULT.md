# #884 CTM audit: result (2026-10-28)

**Verdict: `NOT_SHOWN`. Stop (the #884 decision rule).** At 144 searched A20 map roots, the CTM's picks lose
nothing measurable when the same leaf rollouts play their combats with production Silver. The primary cross-fitted
regret is +0.0010 [−0.0024, +0.0040] in calibrated Heart-kill probability per root. Fight by fight, the CTM forecasts
production Silver well on the states the search actually visits. It slightly over-predicts deaths at elites and bosses
and is about 4 HP optimistic after won boss fights.

## Run

- Plan [PLAN.md](PLAN.md), frozen in `515b4df` before any cohort replay; Philipp's go 2026-10-27 20:37Z.
- Code: the observer at `f5279cf` (binary `aa2adb3c…`); after container restarts killed the first launches, `98e7d0c`
  added resume (a restarted replay skips roots whose complete audit row exists; binary `edee4395…`). The audit code is
  otherwise identical: the first 25 rows come from `aa2adb3c`, the rest from `edee4395`.
- Cohort: the 16 already-used §683 MAP seeds `111374100`–`111374115` (the #881 cohort), [replay_unit.sh](replay_unit.sh)
  via [run_cohort.sh](run_cohort.sh): §683 MAP configuration, `STS_CALLING_BELL_CARD_RNG_FIX=0`, N = 16 rollouts per
  action, every second searched root, top 3 actions by visits, production Silver at base 10,000. No new seeds.
- **Trace check:** all 16 replays reproduce their §683 MAP trace row for row, to the end of the game
  ([trace_check.txt](trace_check.txt)). The observer does not change play.
- 144 audited roots (acts 1/2/3: 58/48/38; none in Act 4), 226 action pairs,
  37,215 imagined combats. Silver arm 69,600 CPU-s (19.3 CPU-h), CTM arm 74 CPU-s. No combat was unsupported.
- Two act-3 roots of seed `111374114` (decisions 162 and 172) hit `replay_child_timeout` in the observer child and
  have no audit row; they are not in the 144.
- The four seeds relaunched at 23:42:18Z record env SHA `e80ceb7` (repo HEAD at launch) but ran the resume binary
  `edee4395`, committed 3 s later as `98e7d0c`.
- Raw rows and replays: share `ctm-audit-884/ctm-audit-884-replays-98e7d0c.tar.gz` (sha256 `960900a8fc7646ae…`);
  [report.json](report.json) is `tools/analyze_ctm_audit.py report.json cohort/A-*.audit.jsonl` (seed bootstrap 2,000,
  seed 884).

## Decision level (leaf values in calibrated Heart-kill probability)

| Measure | Value |
| --- | --- |
| **Cross-fitted regret of the CTM arm's pick, under Silver combats (primary)** | **+0.0010 [−0.0024, +0.0040]** |
| Best action differs between arms (CTM vs Silver) | 34.7% [27.1, 43.2] |
| Split-half flip within one arm (noise null): CTM / Silver | 43.8% / 40.3% |
| Material reversals (in-sample regret > 2 paired SE) | 4.2% [1.9, 7.0] |
| Cross-fitted signed sibling error E = D_ctm − D_silver, oriented on the CTM's side | −0.005 [−0.015, +0.007] |
| Pairs whose Silver gap is > 2 SE: sign flips | 6 of 31 (19%) |
| Slope of D_ctm on D_silver (attenuated by noise in D_silver) | 0.52 [0.37, 0.66] |
| Median \|D_silver\| / median SE(D_silver) at N = 16 | 0.019 / 0.028 |

- The two arms disagree on the best action less often than two halves of the same arm do. Disagreements are
  rollout noise, not CTM error.
- The in-sample regret (+0.010) and the in-sample oriented E (+0.019) are selection-biased: each arm's best action
  is picked and scored on the same streams. Cross-fitting removes that bias, and both move to about zero.
- The CI bounds the CTM's cost at about 0.4 pp of Heart-kill probability per audited map root. Most map-root sibling
  gaps (median 0.019) are below one N = 16 standard error, so the audit can rule out large errors, not small ones.

## Combat level (silver arm: the CTM's forecast of each imagined combat vs production Silver's outcome)

| Room | Fights | P(death) predicted / observed | HP given a win: Silver − CTM mean | Error variance / CTM variance | PIT mean |
| --- | --- | --- | --- | --- | --- |
| monster | 11,364 | 0.49% / 0.60% | −0.03 ± 0.07 | 1.10 | 0.50 |
| elite | 5,026 | 3.97% / 3.00% | −1.05 ± 0.20 | 1.07 | 0.49 |
| boss | 1,675 | 12.1% / 11.0% | −4.42 ± 0.50 | 1.12 | 0.44 |
| event | 482 | 2.25% / 1.45% | −0.85 ± 0.57 | 1.03 | 0.49 |
| all | 18,547 | 2.53% / 2.21% | −0.69 ± 0.08 | 1.09 | 0.49 |

- Death calibration by predicted bin: 0–2% 0.17/0.16%, 2–5% 3.3/1.8%, 5–10% 7.2/4.9%, 10–20% 14.5/12.9%,
  20–50% 29.8/28.3%, ≥ 50% 72/68%. Brier 0.0145, log loss 0.053. The CTM leans slightly pessimistic on deaths in
  the 2–10% range (mostly elites).
- HP spread: the observed error variance is 1.09 times the CTM's own predictive variance, so about 9% of the HP
  error is model error and the rest is the fight's randomness. Bosses have the largest model share (1.12) and a
  4.4 HP optimistic bias (PIT mean 0.44).
- Self-check (ctm arm, the CTM's own draws against its expectation): deaths 2.46% / 2.45%, HP −0.17 ± 0.08, variance
  ratio 1.03. Expectation and sampler agree.

## Interpretation

- The active CTM does not measurably reverse OOC map-root rankings. Combat-level errors exist (boss HP after a win
  about 4 HP too high; elite deaths about 1 pp too high). They are small next to the per-fight randomness, and the
  rollout leaf averages them out across siblings.
- This fits §699 (#883): the CTM's death draw dominates rollout3 sibling-difference variance. Map-root sibling
  decisions are noise-limited (median gap below one SE at N = 16), not CTM-bias-limited.
- It also fits §701: the bot's HP gap to the expert is in combat play itself, which the CTM reproduces faithfully
  (it models today's Silver), not a CTM forecasting error.
- **Inference:** a better CTM is not the lever for map decisions. Variance reduction (#883) and larger effective N
  are. The #885 conditional CTM data experiment is not triggered.

## Limits

- Only map roots are audited, because the A20 default searches only map roots. Under `STS_OOC_MCTS_SCREENS=all`, card,
  rest and relic roots would also read the CTM; this audit says nothing about them.
- Top 3 actions by visits; every second root; N = 16. Act 4 is not covered.
- The Silver arm is a reference, not the truth: the M0 leaf calibration was fit on CTM-resolved rollouts, and Silver
  combats inside rollouts redraw the hidden future.
- Roots within a game are correlated; the CIs resample seeds (16 clusters).
