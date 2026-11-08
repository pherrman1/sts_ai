# Silver leaf price gate D / P1 / PF: result (2026-11-08 04:10 CET)

**No candidate: P1 NOT_SHOWN, PF NOT_SHOWN; the defaults stay.**

- P1 loses Heart kills: −2.49 pp [−4.39, −0.59]. P1 is Silver's victory leaf with the stage-4 prices: non-Fairy
  potions 3.7, Fairy 47.6 on top of its death save, max HP 2.4, gold 0.12.
- PF is neutral: +0.15 pp [−1.32, +1.56], and the non-regression test (−1.5 pp margin) passes. PF is P1 with every
  non-Fairy potion back at 11.
- The potion level alone, P1 − PF, is −2.64 pp [−4.54, −0.73].

Pre-registered rules: [PREREG.md](PREREG.md). The prices come from the leaf plan's stage 4
([../leaf_stage4_offline_fit_20261108/RESULT.md](../leaf_stage4_offline_fit_20261108/RESULT.md), ledger §766).

## Run

- **Run.** Run commit b57c85c2 (main ccc53a48 plus the campaign files; build inputs equal ccc53a48), binary
  c201818cb248cef2… from the bin cache, `bestbench 1000 1 20`. 4 workers (Philipp 00:50 CET) from 00:56 to 03:55 CET.
- **Games.** 2,048 seeds × 3 arms = 6,144 games, all rc 0 with every log check. 0 dropped seeds. 0 `.env`
  mismatches: the check that each game's three leaf flags match its arm (review G-N1) was added in 863bba94 before
  any game outcome was read. By then I had checked only the rc codes, leaf banners and `.env` files of the first
  12 seeds.
- **Aborts.** 2 combat aborts, both on seed 111821505 (arms D and PF), counted as losses.
- **Verification.** `verify_campaign.py`: 2,048 units OK, 0 missing, 0 bad, 0 duplicates, one run commit, 4 of 4
  DONE.json.
- **Cost.** 32.3 core-h (mean cpu_sec/run 19.6 / 17.6 / 19.5 s in D / P1 / PF).

**Incidents (no effect on the data).**

1. **Upload retries.** On the share, some unit uploads failed once (`File exists` on a `.part` file, or a failed
   `mv`). worker.sh marked those claims `rc=upload` and re-uploaded. I checked ten such units: each has exactly one
   complete tar with three rc-0 games and the right FROZEN.txt, and no unit was played twice.
2. **Orphaned claims.** W2 lost its processes at about 03:24 CET, most likely a container reset. That left four
   claims without a heartbeat: 111821864, 111821880, 111821884 and 111821912. W1 and W2 showed no `one_combat`
   process, and no game of these units had finished. At 03:50 CET I released the four claims with the queue's own
   `failed` marker instead of waiting for the 90-min lease. W1 re-ran three of them and W4 one, as attempt a2.

## Primary (two gainer SPRTs, α 0.025 each, β 0.05, d1 +2 pp, look 64)

| contrast | n | Heart kill | d, pp [95% CI] | 97.5% CI | SPRT | verdict |
|---|---|---|---|---|---|---|
| P1 − D | 2,048 | D 25.83%, P1 23.34% | −2.49 [−4.39, −0.59] | [−4.64, −0.29] | H0 at 1,024 pairs (LLR −3.56) | **NOT_SHOWN** |
| PF − D | 2,048 | D 25.83%, PF 25.98% | +0.15 [−1.32, +1.56] | [−1.46, +1.76] | H0 at 704 pairs (LLR −3.27) | **NOT_SHOWN** |

Candidate rule: neither contrast is GO, so there is no candidate.

## Secondary (pre-registered, not a gate)

- **Non-regression, P1.** `sprt_gate.py nonregression` (d0 −1.5 pp) reaches CAP (LLR −2.78), and the bootstrap
  95% lo is −4.39, so the reading is NOT_SHOWN. Descriptively, P1 is worse than D: the 95% CI is below 0.
- **Non-regression, PF.** H1 at 1,856 pairs (LLR +2.99), and the bootstrap 95% lo is −1.32 > −1.5, so the reading
  is **NOT_WORSE**.
- **P1 − PF.** −2.64 pp [−4.54, −0.73] on 2,048 seeds.

## Descriptive

| | D | P1 | PF |
|---|---|---|---|
| Heart kill | 25.83% | 23.34% | 25.98% |
| Act-3 clear (floor ≥ 52) | 37.01% | 32.47% | 36.62% |
| final floor, mean | 38.09 | 35.96 | 37.93 |
| cpu_sec per run | 19.60 | 17.61 | 19.54 |
| games over 300 s wall / max wall | 0 / 109 s | 0 / 150 s | 0 / 115 s |

The paired differences against D:

| | P1 − D [95% CI] | PF − D [95% CI] |
|---|---|---|
| Act-3 clears, pp | −4.54 [−6.54, −2.49] | −0.39 [−1.86, +1.03] |
| final floor | −2.14 [−2.83, −1.44] | −0.16 [−0.53, +0.21] |
| cpu ratio to D | 0.898 | 0.997 |

P1 loses before the Heart: its act-3 clear rate drops by 4.5 pp, and its runs end about 2 floors earlier. That is
also why its games use less CPU.

## Interpretation (Inference)

- **§542 repeats with Heart-kill prices.** Under a different policy (net-0420 instead of student_sel) and prices
  measured on Heart kills instead of floors, a leaf that prices non-Fairy potions far below 11 again loses whole runs:
  §542's arm W, at 5.0, lost 5.9 pp of wins. The pilot's potion price, 3.6 HP, is the marginal value of one held
  potion under a policy that spends potions at 11. Used as the leaf weight, it changes how Silver spends potions,
  and that costs more than the mispricing saved.
- **What PF shows.** The other three changes (Fairy 47.6 over the death save, max HP 2.4 instead of 2.0, gold 0.12
  instead of 0.25) do not change the win rate measurably. The 95% CI rules out a gain above 1.6 pp and a loss larger
  than 1.3 pp. A Fairy worth about 70 HP to the leaf would matter only where Silver trades a Fairy against something
  else, which is likely rare in A20 fights.
- **Smoke Bomb (review G-N3).** P1's default `*=3.7` also puts Smoke Bomb at 3.7, which §542 kept at 11. Part of
  P1 − PF could come from Smoke Bomb; this run cannot separate it from the other potions.
- **For the leaf plan and the learned price head.** Prices measured as marginal values under the current policy (CRN
  forks or fight luck) are not drop-in leaf weights for potions. A price model needs a whole-run check, or labels
  measured under the leaf it will be used with (on-policy iteration). HP, max HP and gold prices near the current
  ones are safe (PF), but there is no evidence that they help.

## Decision

- No default change. `STS_SILVER_POTION_WEIGHTS`, `STS_SILVER_MAXHP_WEIGHT` and `STS_SILVER_GOLD_WEIGHT` stay
  research-only.
- Seeds used: 111820000-111822047 and the smokes 111829990-111829991. 111829992-111829999 are not played and not
  reused.

## Files

- `result.json`: analysis output.
- `analyze.log`: printed summary.
- `pairs_P1.csv`, `pairs_PF.csv`: paired Heart kills in seed order, the SPRT input.
- The unit tars stay on the share in `/mnt/project-files/silver-leaf-price-gate/units/` (2,048 × 30 KB).

To reproduce:

```
python3 tools/cloud/verify_campaign.py docs/experiments/evidence/silver_leaf_price_gate_20261108 --extract DIR
python3 docs/experiments/evidence/silver_leaf_price_gate_20261108/analyze.py DIR/out/units result.json
```
