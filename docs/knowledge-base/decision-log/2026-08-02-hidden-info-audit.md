# 2026-08-02 — Hidden-information boundary audit (plan 5.6.4, spec §A.14)

Date: 2026-08-02
Session/task: Track B3 audit of the hidden-information boundary: strategic rollouts/evaluations may see only what the player sees; unknown outcomes must be sampled from conditional distributions, never copied from the true future seed. Paths audited: strategic datagen branches, one-ply gates, Searcher3 fair machinery, GameAction visibility, BattleContext entry/exit.

## Decision

Audited all five paths against spec §A.14. Verdicts: the fair-play search machinery in `src/sim/search/*` is clean and deterministic; the strategic layer in `apps/one_combat.cpp` has two genuine §A.14 leaks (exact future encounter ids as model features; counterfactual branches continuing from a full copy of the true run RNG streams) that are outside this session's fix scope (another agent owns `apps/one_combat.cpp`, and this track may only fix `src/sim/search/*`). No code fix was applied; findings are recorded here and in `determinism-and-rng.md`.

## Findings per path

| # | Path | Verdict | Evidence (file:line) |
| --- | --- | --- | --- |
| 1a | `runStrategicGenSeed2` branches | **leak** (out of scope) | `apps/one_combat.cpp:5729` `GameContext branch = detachedCounterfactualCopy(pre);` then `finishOocCounterfactual` — branch plays the live run's true future: true `monsterList`/`eliteMonsterList` (not resampled), true event/merchant/treasure draws |
| 1b | `detachedCounterfactualCopy` | clean on aliasing / carries true streams | `apps/one_combat.cpp:3569` — all `GameContext` RNG streams are value members (`include/game/GameContext.h:164-177`), the copy does not alias the live run; only `map` is a `shared_ptr` and it is deep-copied. The copy continues from the live stream state, so the branch's future is the live run's true future |
| 1c | `datagen2` card/rest CF, `pathcf`, `oocnextgen` branches | **leak** (out of scope) | `apps/one_combat.cpp:4646`, `4722`, `4487`, `4179` — same pattern, no encounter resampling |
| 1d | `actFightProbe*` branches | partial mitigation | `apps/one_combat.cpp:3599` `resampleRemainingActEncounters` resamples hidden normal/elite queues from the conditional pool (no-repeat rule), `3676-3678` and `4350-4353`; act boss deliberately kept (repo treats boss as public). Non-combat streams (events/shops/treasure) stay true-future in those branches too |
| 2 | one-ply gates (`oocOnePly*Policy`) | **clean** (default Q path) / **risk** (V2 fallback) | `apps/one_combat.cpp:3111-3457` — `predictActionValue` on the pre-decision state only; no RNG, no post-action state in the default path. The `STS_OOC_STRATEGIC_Q=0` fallback (`3158`, also `2359`) executes the action on a probe copy and scores the successor, which determinizes the true post-choice draw (event outcomes, chest contents) — non-default, flagged |
| 2b | gate + training features | **leak** (out of scope) | `apps/one_combat.cpp:2877-2892` (`richRow`) and `2987-3002` (`buildTokState`) feed the exact next 3 normal encounters and the next elite id into the model at every strategic decision — hidden identity, not the pool distribution |
| 3 | Searcher3 fair particle/belief machinery | **clean** | `src/sim/search/BattleScumSearcher3.cpp:35-64` `applyParticle` overwrites all six combat streams + draw order from the particle; `101-109` `reseed()` = hash(agentSeed, visibleHash, decisionIdx) — no true stream enters a search world; `src/sim/search/CombatObservation.cpp:265-298` particles sampled from that rng only; `src/sim/search/ScumSearchAgent2.cpp:74-123` `playoutBattleFair` |
| 3b | Searcher2 fair determinization | documented limitation | `src/sim/search/BattleScumSearcher2.cpp:299-307` `determinize` replaces draw order + shuffle/card-random streams only; `aiRng`, `miscRng`, `monsterHpRng`, `potionRng` stay concrete under `STS_FAIR=1` (already documented in `determinism-and-rng.md`) |
| 3c | TREASURE_ROOM policy | **risk** (in scope, not fixed) | `src/sim/search/ScumSearchAgent2.cpp:278` `stepOutOfCombatPolicy` reads hidden `gc.info.chestSize` (pre-rolled at room entry, `src/game/GameContext.cpp:1064-1081`) for the CURSED_KEY open/skip choice. A player cannot see chest size before opening. Not fixed: changing the rollout heuristic alters benchmark policy behavior; conservative flag |
| 4 | `GameAction.cpp` strategic legality | **clean** | `src/sim/search/GameAction.cpp:282-325` validity reads only visible state (map, rewards, shop, rest, event options, chest open/skip); event option effects are sampled **after** the choice (`gc.chooseEventOption`, `src/game/GameContext.cpp:2437+`); `setupEvent` pre-rolls only offer draws the real game also pre-rolls at event generation (`src/game/GameContext.cpp:850-1081`) |
| 5 | `BattleContext` combat entry/exit | **clean** | `src/combat/BattleContext.cpp:17-93` `init` derives combat streams from public `seed+floorNum` (plus `gc.miscRng`/`potionRng`); `475-535` `exitBattle` propagates only realized post-battle state (HP/gold/deck/potions/streams); loop guard is `outcome != UNDECIDED`; no auto-use or hidden back-propagation |

## Fixes applied

None. All clear §A.14 violations found are in `apps/one_combat.cpp` (outside this track's ownership and the `src/sim/search/*` fix scope); the single in-scope finding (3c) is a policy heuristic where a fix would change rollout behavior — flagged, not fixed, per the conservative mandate.

## Verification

Build2 (`cmake --build build2`) passes for `one_combat`, `main`, `test`,
`small-test`, `parity_test`; `ctest --test-dir build2` 5/5. Reproduction of
the audited modes on 2-3 seeds with the freshly built build2 `one_combat`
binary, run twice each, byte-identical CSVs:

- `strategicgen2 2 100 0` (STRATEGIC_SAMPLE_ALL=1, branch sims 60/40/30): 1220 action rows, deterministic. **Inference:** branch machinery (copy + `finishOocCounterfactual`) never perturbs the live run; branch RNG derives only from public values (seed, decIdx, f) plus copied streams.
- `fairgen 2 200 0 eps=1.0`: 393 value + 1750 policy + 53 OOC rows, all deterministic (Searcher3 particle seeding = hash(agentSeed, visibleHash, decisionIdx)).
- `oocnextgen 2 100 0` (branchSims 40): deterministic.

Note: while this audit ran, Track B1's uncommitted `apps/one_combat.cpp`
edit (shop beam search) briefly did not compile in build2 (undefined
`oocShopBeamPolicy`, const-qualification error, missing `<unordered_set>`);
it now builds cleanly and the audited functions are not part of that diff.
The verification above used the current, freshly built binary.

## Confirmation

No path in `src/sim/search/*` copies the true future seed into a search or evaluation world: Searcher3 `applyParticle` overwrites all six streams and the draw order; Searcher2 `determinize` overwrites draw order + shuffle/card-random; `Belief` samples particles from a rng seeded only by visible observation, `agentSeed`, and `decisionIndex`. The strategic counterfactual branches in `apps/one_combat.cpp` **do** continue from a copy of the true run RNG state (1a/1c) — that is the flagged leak, not fixed here.

## Status and follow-up

- Implemented: audit + report + KB update; no code changes.
- Open follow-up (needs `apps/one_combat.cpp` owner): replace exact future encounter features (`nextFight0..2`, `nextEliteId`) with the conditional pool distribution or drop them; resample hidden event/shop/treasure draws in CF branches (extend `resampleRemainingActEncounters`); decide boss-identity visibility (repo currently treats the act boss as public; §A.14 lists exact encounter identity as hidden); decide the `STS_OOC_STRATEGIC_Q=0` successor-probe path.
- Open follow-up (this track): decide whether `ScumSearchAgent2::stepOutOfCombatPolicy` TREASURE_ROOM should stop reading hidden `chestSize` (sample from the conditional distribution instead) — policy change, benchmark impact, deferred.
