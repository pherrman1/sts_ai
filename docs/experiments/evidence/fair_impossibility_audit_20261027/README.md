# Fair-policy impossibility certificate: Stage 1 feasibility audit (issue #887, 2026-10-27)

Question (issue #887): can we exhibit two positive-probability worlds with the same observable history at a
reachable decision point and no common winning action, so that no observation-based (fair) policy wins the A20
Ironclad Heart with probability 1? Stage 1 only: read-only audit plus a no-gameplay seed census. No game was played,
no combat was searched, no seed block was consumed.

Simulator: `main` at `ed2dcb2b` (engine sources unchanged since; census built from `src/*.cpp` at that commit with
`g++ -std=c++20 -O2 -fopenmp`, binary sha256 `199063b1…`). Census source: [census.cpp](census.cpp).

## Verdict

| claim type (issue's labels) | status |
|---|---|
| (c) universal no-fair-policy certificate, whole A20 run | **Not feasible**, and in the deterministic-seed regime provably **impossible** on the tested seed range |
| (b) conditional information-set conflict | Feasible only locally (one combat, idealized chance model); existing tooling already computes the needed quantity |
| (a) empirical counterexample to the current policy | Abundant (every lost run) and uninformative for this question |

Recommendation: stop after Stage 1. The Stage 2 discovery pilot cannot produce (c) in either RNG regime (reasons
below); the only cheap informative extension is a local value-of-information computation on already recorded roots
(no new seeds), described at the end.

## 1. Two RNG regimes give two different questions

The issue asks to fix the RNG regime first. The repository has two:

- **Deterministic seed (the real game and the simulator).** A run is a pure function of the 64-bit seed and the
  player's actions. `GameContext` owns per-domain streams; every combat re-derives AI, card-random, monster-HP and
  shuffle streams from `Random(seed + floorNum)` (`src/combat/BattleContext.cpp::init`); the act map is
  `Map::fromSeed(seed, …)` (`src/game/Map.cpp`). A world is a seed; the policy's information set is the set of seeds
  consistent with its observations.
- **Fresh chance ("project-fair").** Silver never reads the battle's hidden streams and samples its own chance
  (`docs/knowledge-base/behavior/determinism-and-rng.md`); `exact_combat_solver` (`-DSTS_EXACT_CHANCE`) enumerates
  every RNG draw as an independent uniform chance node. Here "fair" means "does not exploit determinism".

## 2. Deterministic-seed regime: the observation identifies the seed at the first decision

Before the first decision (Neow) the player sees the four Neow options, the act-1 boss and the whole act-1 map
(rooms, edges, burning-elite position). The census serializes exactly that per seed and counts identical
observations (positive control: Neow options + boss alone).

| seeds | observation | distinct | collisions | file |
|---|---|---|---|---|
| 111,000,000–111,999,999 (1M consecutive) | Neow + boss + map | 1,000,000 | 0 | `census_range_111000000_1M_all.txt` |
| same | map only | 1,000,000 | 0 | `census_range_111000000_1M_map.txt` |
| 20M splitmix seeds (salt 887) | Neow + boss + map | 20,000,000 | 0 | `census_random20M_salt887_all.txt` |
| same | map only | 20,000,000 | 0 | `census_random20M_salt887_map.txt` |
| control: 100k range / 1M random | Neow + boss only | 2,250 | 97,750 / 997,750 | `*_control.txt` (Rényi-2 entropy 11.1 bits) |

Consequences:

- **Proved for any seed distribution supported on 111,000,000–111,999,999** (the range holding the current seed
  blocks): the floor-0 observations are pairwise distinct, so no two worlds share any observable history, and the
  certificate the issue asks for does not exist. Constructively, the fair policy "read the floor-0 observation,
  look up the seed, play that seed's hindsight-optimal action sequence" is a valid observation-based policy, so the
  best fair win rate equals the fraction of hindsight-winnable seeds. Fair and clairvoyant coincide.
- **Inference for the full 2^64 seed space:** zero collisions among 20M maps puts the map's collision (Rényi-2)
  entropy above about 46 bits at 95% confidence (a random function with H bits gives no collision among N draws with
  probability exp(−N²/2^(H+1))); Neow + boss adds about 11 bits. So at most a few hundred seeds typically share a
  floor-0 observation, and the first combat (monster HP rolls, opening hand order from `Random(seed + 1)`) adds far
  more than the missing bits. Two seeds sharing a history into a meaningful decision would be an astronomically rare
  collision, so any loss bound from such a pair is negligible (not computed): the issue's own warning against
  numerically useless bounds applies.
- In this regime the only nontrivial question is whether **hindsight-unwinnable** seeds exist. That is a different
  problem (no information argument) and is the one the community has worked on: OohBleh with gamerpuppy (author of
  sts_lightspeed) and ForgottenArbiter proved seed `18ISL35FYK4` unwinnable for the **Silent at A18+** (forced
  floor-6 Lagavulin; a relaxation that ignores HP and gives the player full shuffle control still loses)
  ([reddit, 2022-02-28](https://www.reddit.com/r/slaythespire/s/U6aYt5QCRy); earlier search
  [PC Gamer, 2020-07-21](https://www.pcgamer.com/uk/does-an-impossible-slay-the-spire-seed-exist-this-players-doing-the-maths/)).
  No Ironclad proof was found.

## 3. Fresh-chance regime: a whole-run certificate needs a full-game loss proof

Here any finite sequence of chance outcomes has positive probability, so "no fair policy wins with probability 1"
holds as soon as one positive-probability event makes every continuation lose, and an information conflict is not
even needed. But every route to a whole-run statement must certify *eventual* loss for every fair continuation:

- There is no forced common prefix beyond the Neow screen. Any earlier fair deviation (Neow choice, path, card picks)
  reaches states where the two worlds diverge observably, after which the policy plays each world separately. Ruling
  that out (the issue's "critical subtlety") requires proving loss over the remaining ~50 floors in at least one
  world for every deviation: at least a loss proof over all states reachable from some forced point,
  short of but still requiring a sound bound on a full POMDP solve. Neither exists.
- No sound whole-run loss bound exists in the repository. `exact_combat_solver` is exact for one combat and only
  under gates (starter deck, Act-1 weak monsters, turn cap ≤ 8; `apps/exact_combat_solver.cpp` header), and its
  `roots` mode certifies survival only over a 1–2 turn horizon (§623, §654,
  [endgame study](../endgame_exact_20261022/RESULT.md)). `KnownRngSearcher` (ADR-0062) is a heuristic searcher, not
  a certificate. Boss fights are mostly out of exact reach (§654 solved 53–57% of last-turn boss roots and 10% of
  second-to-last-turn boss roots within 30 s).
- The only known style of whole-run proof is the hand-made relaxation above (forced early elite, relaxed player).
  **Inference:** for Ironclad (Burning Blood, Bash, 80 HP) no forced early fight is a plausible candidate.

## 4. What is cheap and sound: local information-set conflicts

In the fresh-chance regime the exact solver already gives local (b)-type facts. The endgame study found, at the start
of the last turn of lost A20 fights, 26 of 33 solved positions where no play survives the coming enemy turn, with the
best play surviving with probability 0.076 on average (§654; REPORT §9.5). Those are "every fair policy can die here"
statements but not necessarily information conflicts (Unverified: some may be lost in every world).

The quantity that isolates the information conflict at a root h is the value of perfect information
VPI(h) = E_w[max_a P(survive | a, w)] − max_a E_w[P(survive | a, w)], where P(survive | a, w) is under the best
continuation in world w. VPI(h) > 0 with E_w[max_a …] = 1 is a sufficient local certificate that every world is survivable with hindsight but no fair action survives all of them. A sound
version needs only the existing solver run twice on recorded roots (determinized per root chance outcome, and fair),
so no new seeds and no gameplay. It remains local: conditional on reaching h, for that combat's horizon, under the
idealized chance model; it says nothing about whole-run win probability.

The measured fair-vs-known Heart gap (§692: fair Silver 51.6% vs known-RNG 73.4% at natural HP, 61.7% vs 85.7% at
full HP) is consistent with large information effects at the Heart, but the arms also differ in searcher, so it is not
a certificate either.

## Reproduce

```
find src -name '*.cpp' | xargs -P4 -I{} sh -c 'g++ -std=c++20 -O2 -fopenmp -Iinclude -Iextern -c {} -o obj/$(echo {} | tr / _).o'
g++ -std=c++20 -O2 -fopenmp -Iinclude -Iextern census.cpp obj/*.o -o census -lcrypto   # -Iextern: nlohmann/json.hpp, no submodule needed
census range 111000000 1000000 [0|1|2]     # 0 all, 1 map only, 2 Neow+boss control
census random 20000000 887 [0|1|2]
```

Cost: about 11 min on 1 core for both 20M runs (~1.3 GB RSS).
