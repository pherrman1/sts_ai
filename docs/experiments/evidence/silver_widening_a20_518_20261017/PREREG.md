# §518 pre-registration: Silver chance-node widening per category at A20 (fight level)

Status: DRAFT. Philipp asked for the screen (2026-10-17 19:07Z, thread "spire-mentor engine ideas": "yes lets
try"). Size and worker count are his call; launch waits for an independent review PASS and a frozen run commit.

## Background and question

Silver models randomness with chance nodes and progressive widening: a chance node with v visits may hold up to
ceil(C (v+1)^alpha) distinct outcomes (`SilverSearcher::wideningCap`). There are two categories: END_TURN (enemy
turn plus the next draw) and every other chance node (random targets, generated cards, mid-turn draws,
shuffles). Both use the same constants, C 3.7028 and alpha 0.52389 (`SilverSearcher.h`).

tfriedel/spire-mentor (an STS2 engine and MCTS, MIT) uses separate constants per category: end turn C 5.79,
alpha 0.44; draws C 2, alpha 0.5; other C 1, alpha 0.5. It reports +6.35 pp full-run win rate on 2,000 paired
runs from widening end of turn, with nothing gained from spending the same compute on more simulations
(their claim; not checked here).

Caps (outcomes allowed) at 100 / 1,000 / 10,000 visits:

| Setting | 100 | 1,000 | 10,000 |
| --- | ---: | ---: | ---: |
| Silver, both categories (C 3.7028, alpha 0.52389) | 42 | 139 | 462 |
| endwide end turn (C 7.4056, alpha 0.52389) | 84 | 277 | 923 |
| othernarrow / spire other (C 2, alpha 0.5) | 21 | 64 | 201 |
| spire end turn (C 5.79, alpha 0.44) | 45 | 122 | 334 |

Silver's single setting is already wider than spire-mentor's end-turn setting, and much wider than their
other-node settings. §369 (A0, 3,360 paired fights) changed alpha to 0.40 and 0.65 for both categories at
once and found no gain. No experiment has changed one category alone.

Question: at A20, does giving the two categories different constants change Silver's fight results at equal
simulations? This is screened at the fight level, as §476 and §479 were.

Competing hypotheses:
- H1, wider end turn helps. The end-turn node aggregates the enemy turn and the next hand, so more distinct
  outcomes give the next decision more accurate statistics.
- H2, narrower other nodes help. Fewer distinct mid-turn outcomes (draws, random targets) let the search go
  deeper on real decisions with the same simulations.
- H0: the current constants are on a flat region, as in §369.

## Intervention (option off by default; code commit in `CODE_COMMIT`)

New `ctmsilvergen` armset `widen518` (`apps/one_combat/combat_datasets.cpp::ctmSilverCompareGen`). It is
research-only and reachable only with `STS_CTMSILVER_ARMSET=widen518`, and it sets the existing thread-local
`g_nativeSilverSearchParamOverride` per arm. No production path changes. Arms are plain exact-10k Silver
(no tree prior, no root prior for any arm, c = 25 for both categories) and differ only in the widening constants:

| Arm | End-turn C, alpha | Other C, alpha |
| --- | --- | --- |
| `base10k` | 3.7028, 0.52389 | 3.7028, 0.52389 |
| `endwide10k` | 7.4056, 0.52389 | 3.7028, 0.52389 |
| `othernarrow10k` | 3.7028, 0.52389 | 2.0, 0.5 |
| `spire10k` | 5.79, 0.44 | 2.0, 0.5 |

Our "other" category includes draws, so the "other" arms use spire-mentor's draw setting (C 2, alpha 0.5), the
wider of its two non-end-turn settings.

The same commit ports #612's fix `40dde917` (whole-combat source runs let `STS_OOC_HEART1` play out-of-combat
choices). That fix becomes a no-op once #612 merges.

## Design

`one_combat ctmsilvergen N 20 OUT SEED teacher.json 2` with `env.sh` here. The harness otherwise matches the
#612 root-table run:
- Ascension 20, project-fair RNG, flat exact budgets, `STS_SILVER_LEARNED_STOP=0`.
- Source runs use plain exact-10k Silver. Their out-of-combat choices come from distilled heart1 student C
  (`STS_OOC_HEART1=studentc.bin`, sha256 `eff2f74f…`, greedy, no OOC MCTS). The strategic chain is used only
  for choices student C does not encode.
- The global keys flag is off (`STS_COLLECT_KEYS=0`, which the harness requires). Student C can still take
  keys on its own, so Act-4 fights appear for some sources.
- `STS_SILVER_ROOT_PRIOR` (g6_E, weight 400) is set only because the harness requires it. No arm uses a prior.
- Fights replayed: all boss, elite and event fights, plus about one normal fight in three
  (`STS_CTMSILVER_HALLWAY_EVERY=3`). Each is replayed by a 10k control, which must reproduce the source fight,
  and by every arm with R = 2 combat-RNG redraws. Every arm at a given replicate gets the same redraw and the
  same planner seed.

Seeds come from block 111180000–111189999 (coordinator): smokes 111180000–111180099, run sources from
111180100. **Size: SIZE_TBD** sources on **NWORKERS_TBD** cloud workers (4 shards each), chosen by Philipp.
`run.sh` refuses a checkout whose `apps/`, `src/`, `include/` or `CMakeLists.txt` differ from `CODE_COMMIT`,
or a binary whose sha256 differs from `BINARY_SHA256`.

## Outcome, analysis, decision rule

Analysis is frozen in `analyze.py`, a copy of the #612 script with this run's arms; its CPU-match gate is
removed because all arms use the same number of simulations.
- **Fight score:** as in §476/§479. Each replicate scores 0 on death, else 53 + HP + 11·potions + 0.25·gold +
  2·maxHP. The arm value per fight is the replicate mean.
- **Pairing and CI:** contrasts are paired per fight, with a 95% bootstrap over source seeds (10,000 resamples,
  RNG seed 0).
- **Exclusions:** a fight counts only when every arm row is valid and has R = 2 replicates. Escapes are
  excluded as in §479.

**Labels (three, all fights, score, equal simulations):**
- `endwide10k − base10k`: `ENDWIDE_HELPS` / `ENDWIDE_HURTS` / `NOT_SHOWN`
- `othernarrow10k − base10k`: `OTHERNARROW_HELPS` / `OTHERNARROW_HURTS` / `NOT_SHOWN`
- `spire10k − base10k`: `SPIRE_HELPS` / `SPIRE_HURTS` / `NOT_SHOWN`

A label is HELPS if the CI lower bound is above 0, HURTS if the upper bound is below 0, and NOT_SHOWN otherwise.
The three labels are not corrected for multiplicity; the write-up says so and does not treat a single
borderline label as decisive. A NOT_SHOWN at this size means "inconclusive at this resolution", not "no
effect".

**Descriptive:**
- `spire10k − othernarrow10k` and `spire10k − endwide10k`.
- Subsets: boss, elite, normal, act4.
- Win rate and HP lost for every contrast.
- CPU per simulation and per fight relative to `base10k`, with bootstrap CIs. Narrower widening may cost less
  per simulation, and wider widening more.

**Decision:** no default changes in any case.
- A HELPS label makes that setting a candidate for a paired A20 whole-run test with the student C stack, which
  needs separate authorization.
- If no label is HELPS, the current constants stay and the per-category idea is closed for Silver at 10k.

## Known limitations

- This is a state sample from greedy student C source runs, not the full OOC MCTS stack.
- Only 10k simulations are tested. Their reported gain was at their own deployed budgets.
- Only one pair of "other" constants is tested, and draws are not split from the other chance nodes.
- spire-mentor's +6.35 pp comes from a different game (STS2), a different search and a different starting
  setting, so it is not a prior for our effect size.
