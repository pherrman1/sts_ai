# Expert decisions vs the A20 bot on expert seeds: result (2026-10-27)

Pre-registration: [PREREG.md](PREREG.md). Fidelity and smoke: [expert_replay_fidelity_20261026](../expert_replay_fidelity_20261026/RESULT.md).
RUN_COMMIT `84d2f15d`, binary `f91ba554…`, 16 cloud workers (started 05:56 CET, done 11:13 CET; share outage
06:06–08:40 CET idled some lanes). `verify_campaign.py`: 329/329 units OK, 658 games, all rc 0
([verify.txt](verify.txt)). Analysis: `analyze.py` → [result.json](result.json).

## Primary (pre-registered)

| | X: expert's decisions, then bot | B: bot alone | X − B |
|---|---|---|---|
| Heart kills | 66 / 329 (20.1%) | 73 / 329 (22.2%) | **−2.1 pp [−7.9, +3.6]** |
| discordant pairs | X only 45 | B only 52 | exact McNemar p 0.54 |
| Act 4 reached | 32.2% | 34.3% | −2.1 pp |
| mean final floor | 37.4 | 39.6 | −2.2 |
| mean wall per game | 493 s | 935 s | |

The expert himself won 199 of these 329 runs (60.5%). On those 199 seeds X killed the Heart 53 times, B 49 times.

**Reading:** replaying the expert's out-of-combat decisions, as far as they replay exactly, does not raise the bot's
A20 Heart rate; the point estimate is slightly negative and the CI excludes gains above +3.6 pp.

## Replay defect found in the data (reported, not corrected)

On 6 seeds the X game ended after the Act-3 boss alive and without having lost a fight (floor 52, act 3): the replay
never took the Emerald key, because those logs (older Run History Plus versions) have no `green_key_taken_log`, so the
run had no Act 4. The expert won all 6. Excluding them: X 66/323 vs B 71/323, −1.5 pp. Even if X had killed the Heart
on all 6, X would tie B (72 vs 73). The conclusion does not change.

## Where the X games went (descriptive; conditioned on X's own trajectory, so not causal)

| replay outcome | seeds | X Heart | B Heart | X / B mean floor |
|---|---|---|---|---|
| bot died while still following the log | 116 (expert won 57) | 0 | 27 | 20.8 / 38.0 |
| handed to the bot at a non-replayable decision | 198 | 57 | 42 | 46.4 / 40.1 |
| replayed through act 3 into Act 4 | 9 | 8 | 3 | 56.0 / 43.8 |
| expert's log ended (expert died), bot continued | 6 | 1 | 1 | 34.2 / 45.7 |

Of the 116 in-log runs, half ended by floor 16 (median 16, lower quartile 14); the 6 no-Emerald seeds are among
them, and 3 died outside combat (event damage). Hand-overs were at reward relics (54), shop shelves or
purchases (48), card offers (35), boss relics (26), events (15) and others.

These splits select on X's own fate (a seed lands in the first row because X died), so the large positive difference
in the second row is not evidence that expert decisions help: the same selection removes X's losses from it.

## Interpretation

- **Inference (mechanism not measured):** the expert's decisions assume the expert's combat. Played by Silver, his
  early lines (likely elites and HP-costing choices at HP he could afford) end more bot runs in acts 1-2 than the bot's
  own policy does; on balance this cancels whatever his later decisions are worth. This fits the expert-play audit (#865): the bot
  rests far more than he does; the bot's caution is partly a correct response to its weaker combat.
- **Inference:** "imitate the expert" is not a free win for the OOC policy at today's combat strength. Expert data
  remains useful as a prior or for decision types that do not trade HP for value; per-type ablations
  (`STS_EXPERT_REPLAY_TYPES`) could locate them but were not run.
- No default changes.

Seeds: 329 external expert seeds (Baalorlord run ids in `units.txt`); no 111xxxxxx seeds used.
