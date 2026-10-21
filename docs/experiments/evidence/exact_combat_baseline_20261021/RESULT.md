# Exact expectimax vs native Silver: A20 Act-1 first fights

Final 2026-10-21 22:05Z: all 10 fights solved.
Branch `claude/project-thread-1ar9qf`, tool `exact_combat_solver` (research tooling only, built with `-DSTS_EXACT_CHANCE`).

## Result

On the first fight of 10 A20 Ironclad seeds (starter deck, no Neow), Silver agrees with the exact optimum at 97.8-98.9%
of decisions. Silver won all 10 fights in every config, and the optimum never had a higher win probability.

| config | decisions | agree with optimum | regret / fight (Silver points) | HP lost / fight vs optimum |
|---|---|---|---|---|
| prod (learned stop, g7f_E root+tree prior) | 90 | 98.9% | 0.23 | 0.28 |
| prior, flat 10k | 90 | 98.9% | 0.23 | 0.28 |
| live advisor (flat 10k, no prior) | 90 | 97.8% | 0.33 | 0.38 |
| prior, flat 2.5k | 90 | 97.8% | 0.33 | 0.38 |

The regret per fight is the sum of regrets along Silver's own trajectory, whose expectation is V*(start) − V(Silver)
(performance-difference lemma). One Silver point is about 1 HP: a win scores 53 + HP − 0.4·turn.

Only two decisions were wrong. Every other decision lost less than 0.01.

- **Jaw Worm, seed 111147001, game turn 2, 1 energy left: every config.** Silver played Strike (Q* 116.68) over Defend
  (Q* 118.98); End turn is Q* 113.98. Regret 2.29, about 2.8 expected HP. All four configs pick Strike, with visits
  favouring it about 2:1 at every budget. That points to a leaf/rollout bias, not too few simulations. It is being
  investigated in the "Silver leaf and rollout bias" thread.
- **Cultist, seed 111147000, game turn 3: live and flat 2.5k only.** Silver played Strike over Defend: regret 1.0,
  exactly 1 HP. prod and flat 10k got it right.

By encounter (prod): Cultist (4 fights) 100%, Jaw Worm 91%, Small Slimes (4) 100%, Two Louse 100%.

Small Slimes 111147005 and 111147008 went past 80M states from turn 1, so their solves start at turn 2, and their 3
turn-1 roots each are unscored.

**Reading:** these early fights show no sign that Silver plays suboptimally in a systematic way, at any budget. The
worst case is one ~3-HP mistake per Jaw Worm fight. The live advisor config costs about 0.1 HP per fight more than
prod here, which is one 1-HP mistake in 10 fights. Any suboptimal live play has to come from somewhere else: later and
harder fights, imported live states, the wire path, or leaf bias in positions like the Jaw Worm one. The sample is
small (10 fights, 90 decisions).

## Method

- **What is solved.** For each seed, the A20 Ironclad first Act-1 encounter (`GameContext(seed, 20).monsterList[0]`,
  floor 1, starter deck with Ascender's Bane, no Neow bonus). The fight is solved once, from Silver's information-set
  root state at the first searched decision. Every searched decision of every config is then looked up in that one
  solve: the exact Q of every root action.
- **Chance is enumerated exactly.** That covers draws from the unknown draw pile (a canonical multiset per draw batch
  with exact hypergeometric weights), monster move rolls (every roll 0-99 through `getMoveForRoll`), and every other RNG
  call. Unsupported draws such as Java shuffle longs fail closed.
- **Objective.** Silver's own terminal evaluation (`SilverSearcher::scoreEndState`, the live searcher's eval weights),
  maximised in expectation. The energy-waste term of the loss score is dropped (`--keep-energy-waste` restores it). It
  only affects losing leaves, and dropping it changed no root Q on the validation fight.
- **Turn cap 8.** A fight still undecided at the start of turn 9 (0-based) scores as Silver's loss leaf. Every
  reported action carries `capped`, the probability of reaching the cap under optimal continuation. It was 0 for every
  optimal action. Dominance and bounds need cap ≤ 8 (see below).

### Making it feasible

The plain memoized expectimax hit more than 45M states from turn 1 on Jaw Worm, Two Louse and Small Slimes. Three exact
reductions fixed that:

1. **Dominance pruning of end-of-turn states.** Within a turn, without chance, every line of plays is followed to its
   end. An end-of-turn state is dropped when another one in the same reachable set is at least as good in player block
   and in every monster's HP, block, Vulnerable and Weak, and equal in everything else. The comparison uses a
   projection key that merges hand into discard, since the hand is discarded at end of turn.
2. **Expectimax alpha pruning (Ballard Star1).** Upper bounds come from the win score at the current HP and turn: HP
   never rises in these fights, and Burning Blood heals only after the fight, which the score already counts. A tighter
   bound comes from memoized copies of the same state with up to 12 HP more.
3. **Cheaper state hashing** (about 2x).

Both 1 and 2 need the value to be monotone in HP and damage. Playing the same moves from the better state is at least
as good, except where the worse state dies and the better one wins. A 1-HP win must therefore beat every loss or cap
leaf. Silver pays 1.5 per turn survived and 0.4 less per turn for a win, so this holds only for caps ≤ 8.
`ExactSolver::monotone()` checks it. Both reductions are also gated to starter cards, Burning Blood only, no potions,
and the eight Act-1 weak monsters. Elsewhere the solver falls back to plain expectimax (`--no-dominance`,
`--no-bounds`).

### Validation

- Canonical draws vs order-enumerated draws: max |ΔQ| 4e-14 (Cultist).
- Memo keys: `--verify-memo` with `equalForSearch` found 0 collisions over 500k states. The hash change was checked by
  agreeing Q values.
- Pruned vs unpruned, same cap: Cultist 111147000 max |ΔQ, ΔHP, Δwin| 5e-7 (14k vs 519k states). Two Louse 111147004:
  max 6e-14 (2.2M states / 79 s vs 29.2M / 933 s, dominance only).
- Every root value is checked to be exact, not a pruning bound.

### Cost (one solve per fight, one core)

| encounter | states | time |
|---|---|---|
| Cultist | 13k-31k | ≤ 1 s |
| Two Louse | 2.2M | 77 s |
| Jaw Worm | 3.7M | 171 s |
| Small Slimes | 25.7M and 42.7M from turn 1 (002, 007); >80M for 005 and 008 | 40-80 min |

Small Slimes is slow because both slimes hit weakly. Lines that block for many turns keep high HP, so the bounds
cannot cut them before the cap. Memory is about 40 B per state. Two Slimes solves in parallel ran out of the 15 GB
cgroup on a table grow; seed 008 was restarted alone. The follow-up research thread
(`/mnt/project-files/exact-combat-research/REPORT.md`, branch `claude/project-thread-kgjoid`) has exact orderings and
bounds that cut Small Slimes about 2.7x and Two Louse about 25x.

## Caveats

- The live config is emulated in the sim backend: flat 10k, no prior, rollout root table. Live states imported over
  the wire are not covered.
- The sample is 8 first fights of one character, with the starter deck and no potions. Harder fights are out of reach
  of full enumeration: one more card type or two more monsters multiplies the state space.
- Silver's objective, not end HP, is what is optimised. `--objective hp` optimises end HP instead (0 on death).
- Seeds used: 111147000-111147009 (block 111147000-147999).

## Files

- Rows and summaries: `rows.jsonl` (share: `run10c/*.jsonl`) (one row per searched root with every action's Q, HP and win probability).
- Analysis: `python3 tools/analyze_exact_combat.py rows.jsonl` (output in `analysis.txt`).
- Jaw Worm mistake rows: `jawworm_mistake.json`.
