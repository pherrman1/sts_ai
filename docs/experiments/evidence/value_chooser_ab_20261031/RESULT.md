# Value chooser A/B result: FAIL, −15.0 pp Heart kills [−17.3, −12.7]

Campaign RUN_COMMIT 3d62ff5e (code 8f5b17d6, binary d39c2b98), 32 workers, 1,536/1,536 units verified
(`verify_campaign.py`: OK 1536, missing 0, bad 0, one run commit), 3,072 games, all rc 0. `analyze.py` at 52b29f52
(pre-registered; Heart floor fixed to 56 by the prelaunch delta review before any tar was read).

| metric | A (production) | B (V_A1/V_A2 choose) | B − A [95% CI] |
|---|---|---|---|
| **Heart kill** | 25.1% | 10.1% | **−15.0 pp [−17.3, −12.7]** |
| Act 4 reached | 41.2% | 17.1% | −24.0 pp [−26.6, −21.4] |
| Heart reached | 39.5% | 16.5% | −23.1 pp [−25.7, −20.5] |
| death in act 1 | 14.0% | 22.7% | +8.7 pp [+6.5, +10.9] |
| death in act 2 | 23.1% | 42.5% | +19.4 pp [+16.5, +22.3] |
| death in act 3 | 21.8% | 17.7% | −4.1 pp [−6.9, −1.4] (fewer runs get there) |
| final floor | 42.1 | 32.4 | −9.7 [−10.5, −8.8] |

Decision (pre-registered): **FAIL** (CI upper bound < 0).

## Secondaries
- B overrode the prior's top in 47% of its 29,330 choices: act-1 card rewards 6,668/14,391, act-1 card select
  1,628/3,652, act-1 boss relic 607/1,187, act-2 card rewards 3,624/7,808, act-2 card select 1,125/1,757, act-2 boss
  relic 287/535.
- At card rewards B skips twice as often (17.3% vs the prior's top 8.4%); when it overrides, its value gap over the
  prior's top is small (mean +0.022, median +0.011; prior ties make the 47% a slight lower bound).
- First B override: act-1 card rewards in 1,319 units (Heart kill −14.9 pp), act-1 card select in 210 (−15.7 pp);
  7 units never overrode.
- Wall B/A 0.66 (B games are shorter because they die earlier; not a cost comparison).

## Reading
V_A1/V_A2 rank the top-3 candidates by values that differ by ~0.01-0.02, well inside their own error, and override a
confident policy almost half the time. The pairwise concordance edge over the prior on rollout labels (exploratory,
nonmap_eval) did not carry to play: the labels come from CTM rollouts to act end that V itself was fitted on, while the
games are played by the real stack. This repeats §712 (value-head argmax at card rewards −17.6 pp).
