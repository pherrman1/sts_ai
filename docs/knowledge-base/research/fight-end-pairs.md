# Paired fight-end continuations (`fightendpairgen`)

Last verified: 2026-11-05 against the branch that adds the mode (research tooling, no ledger §).

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
   chain.

## Output

`OUT` is JSONL. One `source` row per seed (source outcome, fight ends, eligible count, ineligible reasons,
cost), one `skip` row per skipped token, one `copy` row per copy:

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
- `obsV2`: only when `g_fightEndPairsExtraObservation` is set. LONG_B's `obs.v2.*` inputs are not on
  main (branch lwvhth); a branch that has them sets this hook instead of changing the row code.

`OUT.manifest.json` records the arguments, `git_sha`, `executable_sha256`,
`effectiveOocPolicySpecification()`, `effectiveSilverLeafSpecification()`, whether the learned stop is
on, and every `STS_*`/`OMP_*` variable.

## Policy and environment

The copies are played by whatever `finishOocCounterfactual` plays in the process environment. For the
pilot the intended setting is §739's cheap proxy, `tools/fight_end_pairs/smoke.sh`: flat Silver 1,000
(`STS_SILVER_LEARNED_STOP=0 STS_SILVER_ACT4_STRONG=0`), `STS_OOC_MCTS=0`, student_sel (`cf6bf7fb`) via
`STS_OOC_HEART1` and `ooc=heart1`, flexible keys. Under the learned stop the `SIMS` argument does not
fix the budget (see the rollout-cost note in the ledger); keep it off for labels.

## Tests

- `one_combat fightendpairselftest` (CTest `fight_end_pairs`, labels `core;smoke`): spec parsing and
  refusals; on a fixture state every copy changes exactly its field (`plainState` diff), shares all
  fourteen game RNG streams with base, has a detached map; skip reasons at the bounds; noop rows equal
  base rows.
- `one_combat fightendpairselftest full [SIMS [DIR]]` (real continuations, seed 111459990, two forks,
  two-fight horizon): the same arguments twice give identical JSONL apart from `cpuMs`/`wallMs`; base
  played twice (across the runs) and noop vs base (within a run) give the same outcome, record, leaf
  terms, simulation and decision counts; a no-op fight-end observer leaves a run's result and fight
  list unchanged (the default-off identity of the hook).
- Off-path identity against main: `potionpriceprobe 1 111459992 50 20 OUT 2 3 8` with the main binary
  (4851f703) and this branch gives identical CSV apart from `cpuMs`.

## Cost

Smoke 2026-11-05 (`tools/fight_end_pairs/smoke.sh`, options `n=2,ooc=heart1`, default variants, used smoke
seeds 111459990-993, binary `119323af` of commit `f166386b`, four processes on a four-core cloud container):
4 source runs, 8 forks, 56 copies, 3 skips (`pot:*` without potions), all rows valid, rc 0.

- CPU per continuation at Silver 1,000 on one core: mean 9.9 s (act-1 forks 8.3 s, act 2 14.8 s, act 3
  4.5 s); a continuation that reaches the Heart costs 20-70 s, one that dies in the next fight < 1 s.
  About 24,700 Silver simulations per CPU second.
- Source run: mean 15.7 s (5-30 s).
- Row size about 3.9 KB (the heart1 record is about 2.4 KB of it).
- Stage-2 pilot projection (512 games × 4 fight ends × base + 6 ≈ 14k continuations): about 40 core-h
  at this mix, plus about 2 core-h of source runs; more if the pilot's Heart reach rate is higher than in
  these four seeds (1 Heart kill in 4 source runs).
- Label noise: the copies share RNG streams, but one different OOC decision (route, rest, shop) changes
  every later draw, so single-copy outcomes diverge widely (e.g. 111459993 fork 1: base dies on floor 29,
  `hp:-8` kills the Heart). Expected; the pilot's sample size has to carry it.

## Related

- `apps/one_combat/potion_price_probe.cpp` (battle-start forks, short horizon, model bootstrap).
- `apps/one_combat/a4_perturb.cpp` (Act-4 entry perturbations, counter table).
- Ledger §731, §732, §745, §746 (Heart-entry paired labels and fits), §739 (cheap-combat proxy).
