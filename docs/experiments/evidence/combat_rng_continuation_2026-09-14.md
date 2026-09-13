# Exact combat RNG continuation audit

Baseline: `31c7a1b9adff9d55c158f5ab560f89176c0e99b3`.
Classification: **`RNG_COUNTER_DELTA_EXACT`**, with deterministic, encounter-specific
bounded replay of `miscRng`. No learned RNG target is required.

The frozen corpus contains 510,030 RAW transitions from 24,999 completed
sources; one requested source (`4102275`, process exit 134) was quarantined
without rows. SHA256:
`74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde`.
Producer: `f0bbd7721e7cc1453976ebb91ee11ebe6127a2bf`, exact-10k Silver,
project-fair, native OOC, A0. The companion manifest/provenance and complete
row/state/predictor contract are validated before counting. The current
`combat_transition_surrogate.supported_for_surrogate` supports 413,799 rows;
the audit calls this function on each row rather than duplicating eligibility.
Full machine-readable counts, integer delta histograms, native source hashes,
source identities, outcome/act/room slices and relevant encounter slices are
in [the JSON evidence](combat_rng_continuation_2026-09-14.json).

## Exact corpus results

Every table entry uses all rows in its population, including deaths.
“Changed” compares counter and both unsigned seed words exactly.

| Stream | Changed / all 510,030 | Changed / supported 413,799 | Counter changed all / supported | Counter unchanged but state changed all / supported | Counter decreased all / supported |
| --- | ---: | ---: | ---: | ---: | ---: |
| aiRng | 510,030 | 413,799 | 468,776 / 380,429 | 41,254 / 33,370 | 213,651 / 170,626 |
| cardRandomRng | 245,279 | 193,573 | 245,279 / 193,573 | 0 / 0 | 0 / 0 |
| miscRng | 116,121 | 97,154 | 116,121 / 97,154 | 0 / 0 | 0 / 0 |
| monsterHpRng | 510,030 | 413,799 | 406,304 / 332,184 | 103,726 / 81,615 | 188,539 / 154,871 |
| potionRng | 2,979 | 0 | 2,979 / 0 | 0 / 0 | 0 / 0 |
| shuffleRng | 510,030 | 413,799 | 510,030 / 413,799 | 0 / 0 | 0 / 0 |

Seed-pair changes equal the changed counts in this table. Exact unchanged
counts are population size minus changed count. The AI/monster-HP negative
counter deltas are expected resets: pre is the **GameContext before init**,
which retains the last combat's streams; init recreates these streams for the
new floor. They are not inherited-stream counter corruption.

`pre.copy().setCounter(post.counter)` matches counter, seed0 and seed1 for
**510,030/510,030 misc states and 510,030/510,030 potion states**; supported
matches are **413,799/413,799 for each**. Mismatches: zero; rates: exactly zero;
there are no mismatch examples or encounter mismatch classes to explain.

Supported misc counter-delta distribution:

| Delta | Rows |
| --- | ---: |
| 0 | 316,645 |
| 1 | 26,699 |
| 2 | 33,408 |
| 3 | 23,501 |
| 4 | 8,848 |
| 5 | 4,698 |

All supported potion deltas are zero. Across the full corpus, potion deltas
are zero on 507,051 rows and 9–88 on the 2,979 changed rows. Changes arise from
Entropic Brew, which current eligibility excludes. Outcome slices contain
491,897 victories / 18,133 deaths, including 398,415 supported victories /
15,384 supported deaths. Outcome, act and room do not introduce a different
continuation mechanism.

## Source proof and the rejection-sampling distinction

The live executable uses normal-namespace `BattleContext`, including when
Silver selects actions (`SilverLiveBackend.cpp::runSilverCombat` initializes
the live battle with `bc.init(gc)` and commits live actions). Silver's private
one-stream chance simulator does not supply these six recorded live states.

| Stream | Init | Combat mutation closure | RAW exit / continuation |
| --- | --- | --- | --- |
| aiRng | `Random(seed + floorNum)` | Monster moves/AI, summons, target choices; tracked random/boolean calls | Copies to GC; next battle recreates it; no OOC controller draws |
| cardRandomRng | `Random(seed + floorNum)` | Random cards, costs, selections, pile insertion, combat helpers, Spoon | Copies to GC; normal floor transition and next battle reset it |
| miscRng | GC copy | Only `MonsterGroup::createMonsters` and its initialization helpers | Copies to GC; exact initialization draw schedule is deterministic from encounter; next floor also resets it |
| monsterHpRng | `Random(seed + floorNum)` | Monster construction HP, Louse stats/Curl Up and emerald elite HP effects | Copies to GC; next battle recreates it; no OOC controller draws |
| potionRng | GC copy | Only Entropic Brew → `returnRandomPotion` → rarity/pool helper loops | Copies to GC; supported combats make no draw; OOC rewards/shops still need the unchanged inherited state |
| shuffleRng | `Random(seed + floorNum)` | Tracked `randomLong` seed for independent Java shuffle | Copies to GC; normal floor transition and next battle reset it |

All direct inherited-stream uses and reference helpers were inspected in
`src/combat`, `src/game/Game.cpp`, initialization/exit, and search/copy/import
boundaries. `getAncientShape`, `getGremlin`, `getLouse`, `getSlaver`,
`createShapes`, `createStrongHumanoid`, `createStrongWildlife` and
`createWeakWildlife` close the misc audit. `Monster::construct` and
`preBattleAction` do not consume misc. Later Gremlin Leader summons in
`Actions.cpp` use **aiRng**, not misc. Potion pool retries are tracked public
`random` calls; there is no raw untracked inherited-stream draw in the live
combat closure, no combat `setCounter`, and no later inherited-stream
assignment. Binary deserialization assigns exact streams; searcher particles
mutate probe copies, not these committed Silver-teacher combats.

A public int `random(range)` increments counter once and calls
`nextInt(range+1)` → bounded `nextLong(n)`, whose rejection loop may consume
multiple underlying steps. `randomBoolean`, chance boolean, floating random,
long random and `randomLong` each consume one underlying step per tracked
call. Raw `nextLong`, `nextInt`, `nextDouble`, `nextFloat`, `nextBoolean` do not
increment counter. Native `setCounter` advances with `randomBoolean` and
cannot rewind a decreased target.

The parity tests construct a valid exact seed pair with first raw output
`UINT64_MAX`. For bound **3**, used by actual combat `random(2)`, rejection
consumes extra steps while counter advances once. Native C++ and Python agree
exactly, and plain `setCounter(1)` fails. Thus the corpus's 100% counter replay
is **not an API-wide proof** that counters alone track raw steps.

The exact continuation contract therefore preserves bounded rejection:
replay the encounter's existing initialization calls from **pre.miscRng**.
The counter delta is derived from the fixed schedule length, not predicted.
All branches select monster identities without changing the misc call
schedule. The audit's `replay_misc` encodes only this small draw closure and
compares it against every stored post state, independently of post counters.
It also passes the constructed rejection fixture, where boolean advancement
fails. This reconstructs exact seed words even outside the corpus's observed
no-rejection states.

Schedules (`B` = boolean, numbers = bounded nextLong sizes):

| Encounter | Schedule |
| --- | --- |
| Gremlin Gang | 8, 7, 6, 5 |
| Small Slimes / Large Slime | B |
| Lots of Slimes | 5, 4, 3, 2, 1 |
| Exordium Thugs (already unsupported) | B, 3, B, 3 |
| Exordium Wildlife | 2, B, 3 |
| Gremlin Leader | 8, 8 |
| Four Shapes / Three Shapes | 6, 5, 4, 3 / 6, 5, 4 |
| Sphere and Two Shapes | 3, 3 |
| Three Louse / Two Louse | B, B, B / B, B |
| All other current encounters | No misc draw |

## Same-floor and intervening OOC paths

Native capture assigns increasing `fightIdx` once per real fight.
The audit groups by sourceSeed, sorts by that index, requires unique,
contiguous indices from zero, nondecreasing floors and victory before every
successor. It does not infer fight order from merged/shard arrival order.
There are **485,031 consecutive fight pairs; zero same-floor pairs**, zero
supported-origin pairs and zero pairs with both endpoints supported.

Every current `GameContext::enterBattle` call site was inspected:

- Map-node entry increments floor before normal/elite/boss combat.
- A20 Act-3 double boss explicitly increments floor and resets misc,
  card-random and shuffle before the second boss.
- Act-1/2 boss rewards lead to `enterBossTreasureRoom`, which increments floor
  and resets the same three streams before boss relic acquisition. Pandora's
  Box consumes cardRandomRng **after this reset**, so previous combat state
  cannot affect its transforms. Act-3 victory increments floor before Act 4;
  Act 4 final boss ends the run.
- Dead Adventurer, Masked Bandits, Mind Bloom, Mushrooms and Mysterious Sphere
  each enter one combat, then their regain-control callbacks return rewards
  and ultimately the map; no callback re-enters combat on that floor.
- `disableColosseum == true` prevents event eligibility. Even forced selection
  reaches a TODO `regainControl()` case, not either Colosseum combat. Monster
  encounter enum cases alone do not make a chained controller path reachable.
- Smoke Bomb resets its flag and returns to the map; supported eligibility
  already excludes visible Smoke Bomb, Entropic Brew and pre-used flag. Death
  and unresolved exits end the run; monster phase changes remain inside the
  same BattleContext, not consecutive combats.
- Save construction starts a combat; it does not follow a completed one.

The four recreated stream values are irrelevant to **normal supported
continuation**, not merely to later battle init. Other OOC reads of card-random
and shuffle (Pandora transforms, colorless event/card offers) occur after
normal floor/boss-treasure reset. No current supported same-floor chain needs
an additional guard. A future controller implementing chains must be
re-audited and may fail closed on visible event/chain eligibility before
sampling; a predicate based only on an unseen future same-floor fight is not
an acceptable pre-combat guard.

## Decision and minimal contract

**`RNG_COUNTER_DELTA_EXACT`** is the selected classification: current supported
misc and potion states reconstruct exactly. This is stronger than a learned
counter solution because the only nonzero counter delta, misc, is already
determined by visible encounter initialization. Do not implement bare
`setCounter(delta)` as a universally exact adapter.

Minimal exact continuation at the RAW boundary:

1. Copy **pre.potionRng**, including counter and both seed words.
2. Reproduce the encounter's misc initialization draw schedule from
   **pre.miscRng**, retaining native bounded rejection semantics. `delta_misc`
   is schedule length, `delta_potion = 0`; **no learned RNG target**.
3. Preserve the existing controller's floor/reset/reward behavior. The other
   four RAW post streams need no generated/predicted state for normal future
   continuation. This is not permission to fabricate them or claim full RAW
   six-stream snapshot equality.

`RNG_COPY_THROUGH_EXACT` would be false: 97,154 supported misc states change.
A visible encounter guard removing all supported misc-mutating classes would
exclude those same 97,154 rows (23.4785487640% of current support), leaving
316,645. The guard is visible through predictor globals.encounter but is
unnecessary with exact initialization replay. Proposed guard needed: **none**;
support loss: **zero**; production support is unchanged.

Implementation success and this RNG conclusion do not qualify the existing
surrogate's HP/potion/relic distribution, hidden-information model, or runtime
integration. No model, RNG head, runtime adapter, Silver configuration or
production default changed. No training, seed execution, gameplay benchmark
or collection ran. Future source/controller changes require fresh audit;
exact RAW snapshot synthesis of all six states remains outside this contract.

## Verification and raw commands

Commands ran in the fresh Codex-app-managed worktree at the baseline above:

```text
python3 tools/agent/worktree.py preflight .
  exit 0: codex-app-managed, detached, external metadata writable
python3 tools/agent/worktree.py check .
  exit 0: json=2222d386c905 pybind11=63d627c5747b
python3 -m unittest tools.test_combat_transition_rng_audit tools.test_combat_transition_contract tools.test_combat_transition_surrogate -v
  exit 0: 26 tests, OK; native parity compiles a temporary helper with g++
cmake --preset linux-gcc-debug
  exit 0: configured/generated
ctest --preset linux-gcc-test -R '^combat_transition_rng_audit_selftest$' --output-on-failure
  exit 0: 1/1 passed
python3 -m tools.combat_transition_rng_audit --corpus-manifest /home/philippherrmann/sts_sweep/runs/combat-transition-runtime-25k/combat-transition-25k.jsonl.manifest.json --output docs/experiments/evidence/combat_rng_continuation_2026-09-14.json
  exit 0: full frozen-corpus accounting; exact native states compared
bash tools/agent/doctor.sh
  exit 0: Environment doctor: all checks passed
python3 -m unittest discover -s tests -p test_repo_health.py -v
  exit 0: 2 tests, OK
python3 tools/repo_health.py --baseline 31c7a1b9adff9d55c158f5ab560f89176c0e99b3 --json
  exit 0: status pass, no hard failures
git diff --check
  exit 0
```

The bare `python` alias was unavailable, so repository commands use python3.
An initial accidental `python3 tools/agent/doctor.sh` invocation failed with a
SyntaxError; the correct shell invocation above passed. The first audit
checked plain counter replay; the final audit added the deterministic bounded
schedule and companion-provenance checks. No results selected model settings
or altered eligibility. The final JSON was compacted with the reusable `compact_result` function
after the full pass (output shaping only, no counts changed). The CLI applies
the same function automatically. It trims irrelevant non-inherited diagnostic
slices; complete six-stream totals and outcome slices are retained.

No production C++ was touched or built. The temporary native parity helper
was compiled and executed; CMake only registers the Python self-test. Full
clean-repository build/CTest belongs to GitHub Actions **Linux GCC**. Runtime
surrogate integration and scientific multi-fight qualification were not run.

Knowledge impact: exact current RNG initialization/continuation ownership and
a resolved named research blocker; routed to determinism/RNG, current research,
this evidence and ledger §237.
