# Paired fight-end continuations (`fightendpairgen`)

Last verified: 2026-11-08 (`ooc=ppo` and the source row's `heartKill` added for the stage-2 pilot;
pilot result and inclusion weights in ledger §763; `luck=`, `luck_identity=` and `n=0` added for E1 of the learned
price head, result in ledger §764; `rewards=` added for reward luck, result of E1-R in ledger §TBD-b).

## Purpose

Causal labels for a leaf price model (leaf plan, stage 0, thread A). PPO critics learn the level of a
state but not its 1-3 HP differences (§747, §755); causal paired labels on common random numbers do
(§731, §745, §746). This mode produces such labels for every fight of a run, not only the Heart entry:
it forks won fights at the state Silver's victory leaf values and plays each single-change copy to the
run end.

## What it does

`one_combat fightendpairgen NSEEDS SEED_START SIMS ASC OUT [OPTIONS=-] [VARIANTS=default]`
(`apps/one_combat/fight_end_pairs.cpp`; seed guard index 2).

1. **Source run.** `finishOocCounterfactual` plays the seed from Neow with `SIMS` (the same continuation
   policy the copies use). A fight-end observer (`OocFightEndObserver`, a new optional argument of
   `finishOocCounterfactual`; `nullptr` = unchanged behaviour) sees each real fight right after
   `BattleContext::exitBattle`. A won fight whose state is on the `REWARDS` screen with the run undecided
   is a fork candidate: before any reward is taken, relic heals applied. Act-3 boss wins do not reach a
   reward screen (A20 second boss, then the victory room) and are never candidates; `ineligible` in the
   source row counts them by reason.
2. **Sampling.** A reservoir of `n` forks per source run (per stratum with `strata=`), filtered by
   `rooms=` (`NORMAL`, `ELITE`, `BOSS`, `OTHER` = event fights; default the first three) and `acts=`.
   The reservoir RNG is seeded from the source seed only.
   **Weights.** A run with K eligible fight ends (per stratum) gives each of them with probability
   min(n, K) / K, and K depends on the run's own future. The base copy replays the source run exactly,
   so unweighted, forks of runs that die soon after the fight are over-sampled and the base outcome is
   biased towards a loss. Every analysis of these pairs must weight each fork by `eligible / sampled`
   of its source row (exact for `strata=none`; per stratum otherwise). In the stage-2 pilot the
   unweighted HP price even has the wrong sign (§763).
3. **Copies.** Each fork gives `base` plus one copy per `VARIANTS` token. Every change touches only its
   own field and no game `Random`:

   | Token | Change | Skip (recorded as a `skip` row) |
   | --- | --- | --- |
   | `hp:-N` | current HP − N | HP would go below 1 |
   | `pot:NAME`, `pot:*` | remove one held potion, once per distinct type | type not held |
   | `maxhp:-N` | `GameContext::loseMaxHp(N)` (current HP clipped) | max HP would go below 1 |
   | `gold:-N` | gold − N | gold < N |
   | `curse:NAME` | `Deck::obtainRaw` of the curse (no Omamori charge, no Darkstone) | deck full |
   | `ctr:RELIC:±N`, `ctr:*:±N` | shift a counter relic's `data` mod its range (`a4CounterLimit`, the `a4_perturb` table: Happy Flower/Sundial 0-2, Incense 0-5, Ink Bottle/Nunchaku/Pen Nib 0-9) | relic not held; shift leaves the value unchanged |
   | `noop` | nothing (a second base; for tests) | — |

   `default` = `hp:-3,hp:-8,hp:-15,pot:*,maxhp:-5,gold:-50`.
4. **Common random numbers.** Every copy is a `detachedCounterfactualCopy` of the fork state (same game
   RNG streams, own map), restores the OOC policy thread state captured at the fork, gets the fork's
   `PathHistory`, and plays on one continuation seed per fork (`contSeed`, splitmix of seed and fight
   index) with `finishOocCounterfactual(..., maxFights = -1, bootstrap = false)`: to the run end, no
   model bootstrap. `ooc=heart1` lets the `STS_OOC_HEART1` student take every OOC step it encodes inside
   the continuations (as `potionpriceprobe`'s EXTRA); without it the continuation is the ordinary OOC
   chain. `ooc=ppo` (needs `STS_OOC_HEART1`, `STS_OOC_HEART1_PPO=1`, `STS_OOC_MCTS=0`) plays the PPO
   net as the PPO runner's chain does: `heart1::ppoStep` before any rule, with full coverage, no key
   rule, and temperature and salt from the environment; a screen the net has no choice for falls back to
   the deployed chain. The net's counters restart with every `finishOocCounterfactual` call and are
   written as `ppo` (`decisions`, `single`, `fallbacks`, `autoGold`) in the source and copy rows.
   `ooc=heart1` (the student path: partial coverage, free relics auto-taken, then the rule chain) is
   not the PPO policy, even with a PPO net loaded.
5. **Fight luck (`luck=R`, research, default off; learned price head E1).** A fight-start observer
   (`OocFightStartObserver`, the second new optional argument of `finishOocCounterfactual`; called at the
   battle screen before Silver initializes the battle, with the fight's budget) lets the source run replay
   every one of its fights, all rooms and acts, R times: a `detachedCounterfactualCopy` of the fight-start
   state, a fresh battle seed and fresh carried streams (aiRng, cardRandomRng, miscRng, monsterHpRng,
   potionRng, shuffleRng; counters kept; `fightreplay`'s redraw, keyed by seed, fight index and replicate),
   its own `ScumSearchAgent2` with the fight's `simulationCountBase`, the battle exited as the run exits it.
   The replay restores the run's health counters and battle-exit hooks; a `CombatStateFailure` of a replay is
   recorded in its row and the run goes on. `luck_identity=N` replays the fights of the first N source seeds
   once more unchanged (replicate 0), which must reproduce the real fight (`identity`). `n=0` (no forks) is
   allowed, for luck-only runs. Source and fork rows are unchanged by `luck=` apart from the source row's
   `luck` tally and its `cost.cpuMs`/`wallMs`, which then include the replays. E1 of the learned price head
   (§764, `docs/experiments/evidence/learned_price_head_e1_20261107/`) replayed the leaf pilot's first block
   this way: the fight-end HP prices from luck and from the pilot's CRN pairs agree within noise (ratio 0.87,
   INCONCLUSIVE against the [0.67, 1.5] band).
6. **Reward luck (`rewards=1`, research, default off).** The source run logs the potion roll of every won
   fight whose reward rolls one: normal and elite fights, and act 1-2 bosses (`createCombatReward` and its
   siblings, called by `afterBattle` inside `BattleContext::exitBattle`, before the fight-end observer).
   The roll's chance is known: 40 + `potionChance` read at the fight's start, clamped to 0-100 (100 with White
   Beast Statue); `potionChance` moves by +10 after a roll without a drop and by -10 after a drop, so it can be
   negative.
   The reward has fewer than 4 items at the roll, so `addPotionRewards`' zero-chance case cannot occur. So
   `dropped - chance/100` is a luck draw for the potion price without any replay, and the drop's type is a
   draw for prices per type. Each roll is checked against the engine: `potionChance` after the reward must
   be the start value + 10 without a drop and - 10 with one. Logging only reads the state; rows are
   otherwise unchanged.
   A drop at an act 1-2 boss reward moves no later chance (`potionChance` resets at the act transition); a
   mid-act drop lowers the act's later chances, so its luck coefficient is attenuated. E1-R (§TBD-b,
   `docs/experiments/evidence/learned_price_head_e1r_20261108/`) logged E1's 8,192 runs: a Fairy drop is worth
   9.2 ± 1.6 pp of Heart kill more than another drop (about 60 HP at 0.155 pp per HP); an ordinary potion at the
   boss reward 1.9 ± 1.05 pp (about 11 HP, unresolved); no other potion type differs measurably from the rest.

## Output

`OUT` is JSONL. One `source` row per seed (source outcome incl. `heartKill`, fight ends, eligible count,
ineligible reasons, cost), one `skip` row per skipped token, one `copy` row per copy:

- position: `seed`, `fork`, `fightIndex`, `act`, `floor`, `room`, `encounter`, `variant`, `change`,
  `contSeed`;
- `outcome`: `valid`, `heartKill` (run won and its last fight was the Heart), `won` (run won; keyless
  act-3 wins count), `finalAct`, `finalFloor`, `deathFloor`/`deathAct`/`deathEncounter` (−1/"" when not
  lost), `finalHp`, `fights` played, `lastFightFloor`, `lastFightHp`, `horizon`;
- `silverSims` and `cost` (`cpuMs`, `wallMs`, `silverSimulations`, `combatDecisions`);
- `heart1`: the copy's heart1 public record at the fork (`buildPublicLeafRecord`, the `recordToJson`
  keys), so models can be fitted on network inputs;
- `state`: the plain state §732's features read (`hp`, `maxHp`, `potions`, `potionCapacity`, `deck` with
  "+", `deckMisc`, `relics`, `relicData`) plus `gold`;
- `leaf`: Silver's victory-leaf terms of the copy at default weights (HP, potion count and score at 11
  per potion, Fairy/Lizard Tail death-save HP as §732's L counts it, max HP, gold, Incense counter) and
  `silverL = hp + 2 maxHp + 11 potions + deathSave`, §732's L. Fight-local terms (win bonus, turn
  penalty) are omitted;
- `obsV2`: only when `g_fightEndPairsExtraObservation` is set (unset on main). Since #989 (LONG_B
  merged) the `heart1` record itself carries `obs.v2.run_counters` and `obs.v2.fought`, the v2 inputs of
  the LONG_B/LONG_C nets.

With `luck=`, one `luck` row per source fight, written at its end: `seed`, `fightIndex`, `act`, `floor`,
`room`, `encounter`, `budget`, `relics` (names, the order of every `relicData`), `start` (fight-start
fields), `real` (`won`, `alive`, `fields`, `state`) and `replays` (per fresh replay `r`, `battleSeed`,
`won`, `alive`, `combatOutcome`, `turns`, `cpuMs`, `simulations`, `healthFailures`, `fields`, `error` if it
threw). `fields` = `hp`, `maxHp`, `potionCount`, `potions`, `gold`, `deckSize`, `upgrades`, `misc`,
`relicData`. Identity seeds add `identity` (and `identityReplay` when it is false). The source row gets
`luck`: `replicates`, `identitySeed`, `fights`, `replays`, `errors`, `healthFailures`,
`identityChecked`, `identityMismatches`, `cpuMs`.

With `rewards=1`, the source row gets `rewards`: `rolls` (per roll `fightIndex`, `act`, `floor`, `room`,
`chance` in percent, `dropped`, `potion` when dropped, `potionCount` and `potionCapacity` before the reward is
taken, `sozu`, `inconsistent` if the engine's potion chance moved otherwise) and `inconsistent` (the count).

`OUT.manifest.json` records the arguments, `git_sha`, `executable_sha256`,
`effectiveOocPolicySpecification()`, `effectiveSilverLeafSpecification()`, whether the learned stop is
on, and every `STS_*`/`OMP_*` variable.

## Policy and environment

The copies are played by whatever `finishOocCounterfactual` plays in the process environment. For the
pilot the intended setting is §739's cheap proxy, `tools/fight_end_pairs/smoke.sh`: flat Silver 1,000
(`STS_SILVER_LEARNED_STOP=0 STS_SILVER_ACT4_STRONG=0`), `STS_OOC_MCTS=0`, student_sel (`cf6bf7fb`) via
`STS_OOC_HEART1` and `ooc=heart1`, flexible keys. Under the learned stop the `SIMS` argument does not
fix the budget (see the rollout-cost note in the ledger); keep it off for labels.

The stage-2 pilot (2026-11-07, `docs/experiments/evidence/fight_end_pairs_pilot_20261107/`) uses Philipp's
PPO baseline net-0420 instead, with `ooc=ppo` in combat B (LONG_B/LONG_C's evaluation environment): flat
Silver 1,000, learned stop and Act-4 strong off, g7f_E root and tree prior, temperature 0.

## Stage-2 pilot result (§763)

1,938 units, 15,504 A20 source runs under net-0420 (`ooc=ppo`, combat B), 61,739 forks with 6.5 copies each,
weighted by `eligible / sampled`. Every change costs Heart kill in acts 1-3. The HP slope is 0.192 pp per HP
[0.147, 0.234] (acts 1-3); the 8-HP price is −1.93 / −1.68 / −0.49 pp in acts 1 / 2 / 3, resolved at z ≥ 3 in acts
1-2 only. At that slope a potion is worth 12.0 HP (Fairy 75 HP, the others 3.6 HP), a max-HP point 2.9 HP and a gold
0.13 HP. Right after the act-1 and act-2 bosses HP is nearly free, since the act transition heals 75% of the missing
HP at A20. Per cell, 10-21% of the pairs disagree, and the pairing efficiency ρ is 0.47-0.77.

## Stage-4 offline fit (§766)

On the pilot's pairs (5 folds by unit, weighted), four global prices in HP units fit best: Fairy 47.6 on top of its
death save, every other potion 3.7, a max-HP point 2.4 and a gold 0.12 (Silver's leaf: 11, 11, 2 and 0.25), with the
HP value scaled per act (0.23 / 0.20 / 0.09 / 0.38 pp per HP). They explain the non-HP pairs better than Silver's
default leaf (+14 bp of skill [8, 20]). Prices per act are not clearly better, and no state-dependent model
(net-0420's critic, MLP heads on its trunk, LightGBM) beats the global prices: the outcome noise of one pair (about
40 pp) is too large for per-situation prices at this size, and 2.2 times more units did not improve the HP slope. In
whole runs (§767, 2,048 seeds, `evidence/silver_leaf_price_gate_20261108/`) these prices lost 2.5 pp of Heart kills
[−4.4, −0.6], while the same prices with every non-Fairy potion at 11 were neutral (+0.15 pp [−1.3, +1.6]). As in
§542, the marginal potion price is not a usable leaf weight: it is measured under a policy that spends potions at 11.

## Tests

- `one_combat fightendpairselftest` (CTest `fight_end_pairs`, labels `core;smoke`): spec parsing and
  refusals; on a fixture state every copy changes exactly its field (`plainState` diff), shares all
  fourteen game RNG streams with base, has a detached map; skip reasons at the bounds; noop rows equal
  base rows.
- `one_combat fightendpairselftest full [SIMS [DIR]]` (real continuations, seed 111459990, two forks,
  two-fight horizon): the same arguments twice give identical JSONL apart from `cpuMs`/`wallMs`; base
  played twice (across the runs) and noop vs base (within a run) give the same outcome, record, leaf
  terms, simulation and decision counts; a no-op fight-end observer leaves a run's result and fight
  list unchanged (the default-off identity of the hook). With `luck=1,luck_identity=1` the same call gives
  identical source and fork rows (apart from the source row's `luck` tally), every replicate-0 replay
  reproduces its fight, and the fresh replays differ from the real fights. With `rewards=1` the source and
  fork rows are identical apart from the source row's `rewards` log, every roll agrees with the engine's
  potion chance, and a potion type is logged exactly when one dropped.
- Fast checks also cover the `luck`, `luck_identity`, `n=0` and `rewards` options and the luck redraw (deterministic per
  seed, fight and replicate; new seed and carried streams, counters and every other stream kept; state
  unchanged).
- Off-path identity against main: `potionpriceprobe 1 111459992 50 20 OUT 2 3 8` with the main binary
  (4851f703) and this branch gives identical CSV apart from `cpuMs`.

## Cost

Smoke 2026-11-05 (`tools/fight_end_pairs/smoke.sh`, options `n=2,ooc=heart1`, default variants, used smoke
seeds 111459990-993, binary `119323af` of commit `f166386b`, four processes on a four-core cloud container):
4 source runs, 8 forks, 56 copies, 2 skips (`pot:*` without potions), all rows valid, rc 0.

- CPU per continuation at Silver 1,000 on one core: mean 9.9 s (act-1 forks 8.3 s, act 2 14.8 s, act 3
  4.5 s); a continuation that reaches the Heart costs 20-70 s, one that dies in the next fight < 1 s.
  About 24,700 Silver simulations per CPU second.
- Source run: mean 15.7 s (5-30 s).
- Row size about 3.9 KB (the heart1 record is about 2.4 KB of it).
- Stage-2 pilot projection (512 games × 4 fight ends × base + 6 ≈ 14k continuations): about 40 core-h
  at this mix, plus about 2 core-h of source runs; more if the pilot's Heart reach rate is higher than in
  these four seeds (1 Heart kill in 4 source runs).
- Stage-2 pilot (net-0420, `ooc=ppo`, combat B): 16.8 s per continuation (acts 1-4: 14.3, 19.6, 22.1, 8.0 s),
  20.7 s per source run, 3.98 forks per run and 6.48 copies per fork; 1,958 core-h for 1,938 units of 8 runs. About
  59 min wall per unit on one lane (p90 88 min, max 160 min). One failing continuation kills the whole unit
  (10 of 1,948 units ended rc 1; the repro of one of them is a `CombatStateFailure` stall).
- Label noise: the copies share RNG streams, but one different OOC decision (route, rest, shop) changes
  every later draw, so single-copy outcomes diverge widely (e.g. 111459993 fork 1: base dies on floor 29,
  `hp:-8` kills the Heart). Expected; the pilot's sample size has to carry it.

## Related

- `apps/one_combat/potion_price_probe.cpp` (battle-start forks, short horizon, model bootstrap).
- `apps/one_combat/a4_perturb.cpp` (Act-4 entry perturbations, counter table).
- Ledger §731, §732, §745, §746 (Heart-entry paired labels and fits), §739 (cheap-combat proxy).
