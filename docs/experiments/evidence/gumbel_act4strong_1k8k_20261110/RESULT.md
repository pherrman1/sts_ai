# Act-4-strong budget curve in whole runs: G1, G2, G4 and G8 with Act 4 strong (result)

Pre-registration: [PREREG.md](PREREG.md). Analysis: `analyze.py` as frozen with the PREREG in the run commit 22903c21
(before any unit had finished), output `results/result.json`. Prelaunch review: J, PASS.

## Run

- Run commit 22903c21 (code 13bb97ec, binary b5090b16 from the share's binary cache), 4 lanes per worker, queue.
  35 workers ran the units; the 5 started after node-cap Test 2's tail found the queue already claimed. The first game
  started at 02:05 CET and the last ended at 05:58 CET on 2026-11-10. The 2,048 games sum to 127.4 lane-hours (G1S
  19.5, G2S 27.6, G4S 35.5, G8S 44.8; PREREG: about 100-130). The longest game took 38 min (G8S-111378648); none
  came near the 2 h timeout.
- `verify_campaign.py`: 512 of 512 units OK, 0 missing, 0 bad, 0 duplicates, all on run 22903c21, 40/40 worker DONE
  files. Claims: 512 as `.a1`, one as `.a2` (111378492, released after its heartbeat was over 6 min stale following a
  container reset; claims snapshot `results/claims.txt`, `claims/` removed after it).
- `analyze.py`: 2,048 games, 0 drops in this campaign and in the comparison arms, 0 combat aborts → evaluable.

## Replay check

**REPLAY_OK**, 512 seeds checked per arm (G1S, G2S, G4S, G8S), 0 failing. On every seed where Gk ended before Act 4,
GkS has the same Heart result, final floor, `[heart1_ppo]` line, Gumbel roots line and tree reuse line; on every seed
where Gk reached Act 4, GkS reached it too. Act-4 reach is therefore identical within each pair, and GkS − Gk is the
effect of Act 4 strong alone.

## Primary: Heart kill, 99% (Bonferroni over five)

| contrast | d | 95% | 99% | only first / only second | CPU ratio | verdict |
|---|---|---|---|---|---|---|
| G1S − G1 | +2.15 pp | [+0.59, +3.91] | [+0.00, +4.30] | 15 / 4 | 7.50× | **NO_DIFFERENCE_SHOWN** |
| G2S − G2 | +3.52 pp | [+1.56, +5.47] | [+1.17, +6.06] | 22 / 4 | 4.79× | **G2S_BETTER** |
| G4S − G4 | +3.71 pp | [+1.56, +5.86] | [+0.98, +6.64] | 26 / 7 | 2.88× | **G4S_BETTER** |
| G8S − G8 | +2.73 pp | [+0.78, +4.69] | [+0.20, +5.27] | 20 / 6 | 1.90× | **G8S_BETTER** |
| G16 − G8S | +6.05 pp | [+2.15, +9.96] | [+0.78, +11.33] | 71 / 40 | 1.62× | **G16_BETTER** |

G1S − G1's 99% lower end is exactly 0.00, not above it (PREREG: BETTER needs lo > 0). G16 is §775's G16 + mb4 on these
512 seeds; its Act-4 reach is +5.86 pp [+1.76, +9.96] above G8S's, its final floor +2.32 [+0.96, +3.68].

## Per arm (same 512 seeds)

| arm | simulations | Heart kill | reach Act 4 | kills per Act-4 arrival | mean final floor | CPU per run |
|---|---|---|---|---|---|---|
| G1S | 1,000, Act 4 strong | 24.41% | 29.69% | 82.2% | 35.31 | 136.8 s |
| G2S | 2,000, Act 4 strong | 30.66% | 36.91% | 83.1% | 37.69 | 193.4 s |
| G4S | 4,000, Act 4 strong | 33.40% | 41.80% | 79.9% | 39.35 | 249.6 s |
| G8S | 8,000, Act 4 strong | 34.38% | 42.77% | 80.4% | 39.10 | 314.8 s |
| G16 + mb4 (§775) | 16,000, Act 4 strong | 40.43% | 48.63% | 83.1% | 41.42 | 509.0 s |
| G32 + mb4 (§775) | 32,000, Act 4 strong | 39.26% | 48.63% | 80.7% | 41.40 | 863.8 s |
| G64 + mb4 (§775) | 64,000, Act 4 strong | 39.84% | 49.61% | 80.3% | 41.38 | 1,749.9 s |
| G1 / G2 / G4 / G8 (budget curve) | own budget in Act 4 | 22.27 / 27.15 / 29.69 / 31.64% | as GkS | 75.0 / 73.5 / 71.0 / 74.0% | as GkS | 18.2 / 40.4 / 86.7 / 166.0 s |
| D (§775) | 10,000, learned stop, Act 4 strong | 30.86% | 41.21% | 74.9% | 38.84 | 247.7 s |
| B1 (combat B, 1k test) | 1,000 flat | 21.88% | 33.59% | 65.1% | 36.11 | 19.1 s |

Kills per Act-4 arrival, GkS − Gk on the seeds where Gk reached Act 4 (the same seeds for both, 95%): G1 +7.2 pp
[+2.0, +12.5] (152 seeds), G2 +9.5 [+4.2, +14.8] (189), G4 +8.9 [+3.7, +14.0] (214), G8 +6.4 [+1.8, +11.0] (219).
Gumbel roots and simulations per run, GkS (Gk): G1S 478 / 1.16 M (0.44 M), G2S 523 / 1.87 M (0.97 M), G4S 553 /
2.98 M (2.06 M), G8S 542 / 4.82 M (4.04 M). Act 4 strong adds 119-163 s of CPU per run, about 350-415 s per run that
reaches Act 4.

## Secondary (95% intervals, not gates)

| contrast | Heart (pp) | CPU ratio |
|---|---|---|
| G2S − G1S | +6.25 [+2.34, +10.35] | 1.41× |
| G4S − G2S | +2.73 [−1.37, +7.03] | 1.29× |
| G8S − G4S | +0.98 [−3.12, +5.08] | 1.26× |
| G16 − G8S | +6.05 [+2.15, +9.96] | 1.62× |
| G32 − G16 | −1.17 [−5.08, +2.73] | 1.70× |
| G64 − G32 | +0.59 [−3.32, +4.49] | 2.03× |
| G1S − D | −6.45 [−10.16, −2.73] | 0.55× |
| G2S − D | −0.20 [−4.30, +3.91] | 0.78× |
| G4S − D | +2.54 [−1.56, +6.64] | 1.01× |
| G8S − D | +3.52 [−0.59, +7.42] | 1.27× |
| G1S − B1 | +2.54 [−1.37, +6.25] | 7.16× |
| G2S − B1 | +8.79 [+4.69, +12.89] | 10.13× |
| G4S − B1 | +11.52 [+7.42, +15.62] | 13.07× |
| G8S − B1 | +12.50 [+8.40, +16.60] | 16.48× |

D, G16, G32 and G64 (+ mb4) are §775's games on binary 0eabb014; §777's 32/32 sentinel showed b5090b16 replays §775's
G16 games.

## Reading (Inference)

- Act 4 strong is worth about +2 to +4 pp Heart at every budget from 1,000 to 8,000 (resolved at 2k, 4k and 8k), all
  of it through Act 4: it raises kills per Act-4 arrival from 71-75% to 80-83%, the level of §775's G16, G32 and G64
  (80-83%). It costs a fixed amount per Act-4 run (Shield and Spear at 10,000 with prior playouts, Heart at 40,000),
  which multiplies G1's CPU per run by 7.5 but G8's by 1.9.
- With Act 4 the same in both arms, the 8k → 16k step remains: G16 − G8S +6.05 pp, nearly all of it Act-4 reach
  (+5.86 pp), i.e. acts 1-3. Of §779's 8.79 pp gap from G8 to G16 + mb4, about 2.7 pp were Act 4 strong and about
  6 pp are the budget. §779's descriptive split (about 4 pp conversion, 5 pp reach) put about 1.3 pp too much on Act 4.
- The curve with Act 4 played the same way: 24.4, 30.7, 33.4, 34.4, 40.4, 39.3, 39.8% Heart at 1k, 2k, 4k, 8k,
  16k, 32k, 64k. The steps 2k → 4k and 4k → 8k are small (+2.7, +1.0, each unresolved) and 8k → 16k is large (+6.1),
  but a smooth rise of about 3.3 pp per doubling from 2k to 16k (G16 − G2S = +9.77 pp over three doublings) lies
  inside all three intervals, so the shape between 2k and 16k is not resolved. Resolved: the rise up to 16k and the
  flat part above it. The node cap does not explain the flat part at 16k (§780).
- Against D: G4S at D's CPU (1.01×) is +2.54 pp [−1.56, +6.64], G8S at 1.27× +3.52 [−0.59, +7.42], neither resolved.
  G16 + mb4 stays the only arm resolved above D (§775).

## Decision

**G1S NO_DIFFERENCE_SHOWN, G2S_BETTER, G4S_BETTER, G8S_BETTER** (Act 4 strong against Act 4 at the arm's budget),
**G16_BETTER** (16k against 8k with Act 4 strong in both). **REPLAY_OK** (512 seeds checked per arm). No default
change. No GkS matches G16 + mb4 (G16 − G8S +6.05 pp), so no new teacher or actor candidate; G16 + mb4 stays the
teacher candidate. Budget comparisons with Act 4 strong off understate an arm by about 3 pp.

Seeds: §775's 111378256-111378767 reused (no new seeds). Cost: 127.4 lane-hours.
