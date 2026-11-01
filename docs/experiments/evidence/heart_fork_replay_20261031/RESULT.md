# Result: fresh Heart replay of run-1 forks (2026-11-01)

**Verdict (pre-registered, `analyze.py`): NO_REBUILD_LOSS.** Unperturbed in-game Heart states keep most of their win
rate when rebuilt fresh. The forks win 74.4% in game and 70.9% fresh. Per entry, in game minus fresh is
**+3.1 pp [−2.5, +7.8]**, below the +8.3 pp gap of #923's controls.

Campaign: 234/234 units verified (`verify_campaign.py`: MISSING 0, BAD 0, duplicates 0, run c3ef113a, DONE 16/16,
all rc 0), 16 workers, 22:17Z-00:20Z. Results are in [results/result.json](results/result.json).

| Heart win, same 60 entries | in game | fresh (production search) |
|---|---|---|
| Run-1 forks, unperturbed, new future (234 states) | 74.4% | 70.9% |
| Pilot control, unperturbed (60) | 75.0% | 66.7% |
| Pilot children, perturbed (180, #923) | 64.4% | 66.4% |

Fresh forks minus fresh control, per entry: +4.0 pp [−5.0, +12.9].

## Reading
- **The rebuild loses at most a few points.** It does not lose the ~8 pp of #923's control gap. So the fresh
  control's 66.7% against 75% in game is mostly noise in one control per entry: its fresh replay also sits 4 pp below
  the forks' fresh replay.
- **Children vs forks** (per entry over 60 entries, rng 7, 2,000 draws; results review). All three CIs include 0:
  - fresh: −4.3 pp [−12.5, +4.2]
  - in game: −9.3 pp [−18.2, +0.3]
  - difference-in-differences (children in game − fresh) − (forks in game − fresh): −5.0 pp [−13.3, +3.8]
- So a modest real effect of the perturbed states (about −4 pp fresh) and an in-game penalty for the children
  (about −5 pp) are both possible. Neither is shown.
- §726's −7.6/−10.6 pp should not be read as a clean causal effect of the perturbations. For V_A4 training, perturbed
  rows remain usable only as noisy labels.
- Power: the per-entry CI half-width is about ±0.05, so a rebuild loss of up to about +8 pp is not excluded at its
  upper end.

Caveat: as in #923, the replay does not carry gold or card misc.
