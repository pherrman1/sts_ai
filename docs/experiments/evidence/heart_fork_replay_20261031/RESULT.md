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
- **The in-game children stay low.** 64.4%, about 10 pp below both unperturbed in-game groups (74-75%). Fresh, they
  sit 4.5 pp below the forks (66.4% vs 70.9%).
- Together with §728 this leaves two readings that this data cannot separate:
  - a modest real effect of the perturbed states, about −4 pp fresh,
  - plus an in-game penalty of a few points for the children.
- §726's −7.6/−10.6 pp should not be read as a clean causal effect of the perturbations. For V_A4 training, perturbed
  rows remain usable only as noisy labels.
- Power: the per-entry CI half-width is about ±0.05, so a rebuild loss of up to about +8 pp is not excluded at its
  upper end.

Caveat: as in #923, the replay does not carry gold or card misc.
