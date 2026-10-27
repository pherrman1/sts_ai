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

The expert himself won 199 of these 329 runs (60.5%).

**Reading:** with the pre-registered intention-to-treat count, X and B are indistinguishable (CI −7.9 to +3.6 pp).
A replay defect (below) biases X down on 17 seeds; corrected for it, the difference is about 0 ± 6 pp.

## Replay defect: missing Emerald key on 17 seeds (found in review; not re-run)

In 17 X games the run ended after the Act-3 boss, alive, with no Act 4 (floor 52, act 3); B has no such game. The
expert won all 17. None of the 17 logs has `green_key_taken_log` (192 of the 329 logs lack it: Run History Plus
versions before the field existed), and the replayer took the Emerald key only on the logged floor, so it never took
it. In 6 of the 17 the run ended while still following the log; in 11 the bot had taken over later in act 3, after the
key was already lost. (A first version of this note found only the 6.)

- Excluding the 17 pairs: X 66/312 vs B 66/312, **0.0 pp [−6.1, +5.8]**.
- Imputing X's own Heart rate given Act 4 (66/106) on the 17: X about +1.1 pp over B.

`apps/one_combat/expert_replay.cpp` now takes the Emerald at its first offer, and the Sapphire at the first chest with
no logged relic, when the log lacks the key field and the expert reached Act 4. This changes X games of up to 110
seeds (logs without the fields whose expert reached Act 4); re-running them needs Philipp's go.

## Where the X games went (descriptive; conditioned on X's own trajectory, so not causal)

| replay outcome | seeds | expert won | X Heart | B Heart | X / B mean floor |
|---|---|---|---|---|---|
| bot died while still following the log | 110 | 51 | 0 | 25 | 19.1 / 37.9 |
| handed to the bot at a non-replayable decision | 187 | 122 | 57 | 37 | 46.1 / 39.7 |
| replayed through act 3 into Act 4 | 9 | 9 | 8 | 3 | 56.0 / 43.8 |
| expert's log ended (expert died), bot continued | 6 | 0 | 1 | 1 | 34.2 / 45.7 |
| no Emerald key, run ended after act 3 (defect) | 17 | 17 | 0 | 7 | 52.0 / 44.9 |

Half of the 110 in-log deaths came by floor 16 (median 16, lower quartile 14); 3 died outside combat (event damage).
Hand-overs were at reward relics, shop shelves or purchases, card offers, boss relics, events and others
(`result.json`, `stopReasons`).

These splits select on X's own fate (a seed lands in the first row because X died), so the positive difference in the
second row is not evidence that expert decisions help: the same selection removes X's losses from it.

## Interpretation

- NOT_SHOWN: replaying the expert's out-of-combat decisions, as far as they replay exactly, produces no measurable
  change in the bot's A20 Heart rate (about 0 ± 6 pp after the key defect).
- In 110 seeds the bot died while still following his log, most by floor 16, where B on the same seeds killed the
  Heart 25 times. Why (his choices assuming his combat strength, or something else) was not measured.
- Per-type ablations (`STS_EXPERT_REPLAY_TYPES`) were not run. No default changes.

Seeds: 329 external expert seeds (Baalorlord run ids in `units.txt`); no 111xxxxxx seeds used.
