# Gumbel learned stop, whole-run gate: result (2026-11-10)

Run of [PREREG.md](PREREG.md) (frozen in run commit 8fe9eb7a, code 09db3101, binary 57d7f83c; #1026, review J
PASS). Launched about 12:44 CET on 40 workers; last tar 13:56 CET.

- `verify_campaign.py`: 1,056/1,056 OK, 0 missing, 0 bad, 0 duplicates, run 8fe9eb7a, 40/40 DONE.json
  (`results/verify.txt`). Claims snapshot `results/claims.txt`; claims/ removed afterwards.
- `python3 -I analyze.py UNITS REF_UNITS results/result.json results/claims.txt`, REF_UNITS = §775's `*_low` tars
  extracted. 0 bad games, 0 env mismatches, 0 aborts, 0 dropped seeds.
- Cost 133.9 lane-h (sum of game walls; plan about 130).

## Sentinel

32 of 32 G16 games identical to §775's → **REUSE_VALID**; §775's 1,024 G16 games are the control. The same games took
1.17× §775's CPU here (other machines), which is the machine-speed correction below.

## Primary

| | G16 (§775) | G16STOP |
|---|---|---|
| Heart kill | 41.21% | 38.87% |
| Act-4 reach | 49.22% | 48.14% |
| CPU s per run | 512.1 | 455.2 |

- **d = −2.34 pp, 95% CI [−5.18, +0.39]**. 92 seeds kill only with G16STOP, 116 only with G16. One-sided 95% bounds
  [−4.69, 0.00].
- SPRT nonregression (H0 −1.5 pp, H1 0): **CAP** at 1,024 (LLR −1.21). The lower one-sided bound is below −3 pp and
  the upper one is not below 0 → **INCONCLUSIVE**.
- Secondary: SPRT gainer accepts H0 at 640 seeds (NOT_SHOWN). Act-4 reach −1.07 pp [−3.91, +1.76], final floor −0.66
  [−1.52, +0.18]. G16STOP − D (§775) +7.23 pp [+4.20, +10.25].

## Cost

- Gumbel simulations per run: **0.697×** G16's [0.676, 0.719]; roots per run 0.98×.
- CPU per run: 0.889× [0.846, 0.934] raw. Corrected by the sentinel's machine speed: **0.76×**. The correction is
  from 32 games, so it is rough.
- Learned stops: 226,742 of 585,908 roots (38.7%), leaving 28.5% of the Gumbel budget unspent. Offline it was 41.2%
  of roots and 29.0% of sims, so the online stop behaves like the offline one.
- Review note N2 (stops by boundary): the exit line counts only the stops, so a per-boundary split needs a traced
  run. It is not measured here.

## Interpretation (Inference)

- The stop saves what it promised: about 30% of the search and about a quarter of the CPU. In play it probably costs
  some Heart kills: the point estimate is −2.3 pp, and 1,024 seeds can neither rule out 0 nor rule out −5.
- For scale: §781's G8S (8k with Act 4 strong) is 6.05 pp below G16 at 0.61× the CPU. A straight budget cut to 0.76×
  CPU would cost roughly 3-4 pp on that line, so the stop sits at or slightly above the plain budget curve. That
  difference is not resolved.
- Offline, 1.05% of the roots had a different pick. Those changed picks, together with the smaller trees reused by
  the next decision, are enough to move the game outcome on about a fifth of the seeds. That is the same discordance
  as other single changes (§780: 200 seeds).

## Decision

INCONCLUSIVE. No default change; the stop stays off and G16 + mb4 stays the teacher candidate. A stricter threshold
(T = 0.02: 0.12% disagreement, about 8% CPU offline) or a stop only on boundaries after the first phase are the
options for another try. Each needs Philipp's call and its own gate.

Seeds: §775's 111378256-111379279 (no new seeds). Cost: 133.9 lane-hours.
