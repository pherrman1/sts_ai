# Infinite-combo research direction (2026-08-08)

Status: **ARCHIVED future research direction** — investigation complete, phased plan
designed, not yet scheduled for implementation. No code changes.

## Purpose

Document a concrete, phased plan for guiding the Ironclad MCTS agent toward
discovering and executing infinite combos (Dropkick loops, Sundial energy
engines, Corruption exhaust engines). The plan emerges from a 5-investigator,
1-architect session that surveyed the codebase, training pipeline, and
external ecosystem. The core finding: all infinite mechanics are already
simulatable, but a simulator safety guard unconditionally scores genuine
winning infinites as losses — so the search literally cannot discover them.

## Relationship to active plans

| Active plan | Interaction |
|---|---|
| `plan-winrate-ideas-2026-08-07.md` | No overlap — combat search steering, orthogonal to winrate plan's training/deployment items. |
| `plan-rollout-experiments-2026-08-07.md` | Relevant: B1 turn-beam rollout (−3.5pp, parked) is the closest existing work. This plan's Phase 3a (PUCT-prior boost) targets a different channel (tree descent, not rollouts), deliberately avoiding the historically-failing rollout-modification path. |
| `plan-value-targets-2026-08-07.md` | No overlap — different label/feature work. Phase 4 (combo features in strategic training) is contingent on Phase 1-3 success and would be additive. |
| `plan-selfplay-relabeling-2026-08-07.md` | No overlap. |
| `plan-phase1-cardselect-continuation.md` | No overlap. |

## Investigation summary

Five parallel investigators examined: (1) mechanical detection in the
simulator, (2) reward signals and training objectives, (3) expert features
and search modifications, (4) external ecosystem approaches, (5) run-level
strategic model guidance. Key findings:

**The blocker:** `BattleContext::executeActions()` (BattleContext.cpp:748-768)
has a safety guard at `loopCount > 1,000,000 || turn > 500` that
unconditionally sets `Outcome::PLAYER_LOSS`. A genuine winning infinite
(e.g., Dropkick loop killing a ~200 HP enemy) is scored as a loss. The search
tree cannot discover what the reward surface never contains. Additionally,
`cardsPlayedThisTurn` is `int16_t` (Player.h:79), overflowing at 32,768
plays/turn — relevant for extended loops. The Searcher3 rollout is hard-capped
at 200 steps (`BattleScumSearcher3.cpp:799`).

**All mechanics work:** Dropkick energy/draw refund on Vulnerable
(Actions.cpp:1035), Sundial counter + 2 energy at 3rd shuffle
(BattleContext.cpp:2827-2843), Corruption free+exhaust skills (CardManager.cpp:415,
BattleContext.cpp:919), Dark Embrace/Feel No Pain on-exhaust triggers, Unceasing
Top, Velvet Choker/Normality caps. Nothing detects "infinite potential" — only
runtime safety valves.

**Existing infrastructure:** `CombatObservation::visibleHash` (Searcher3)
already includes all 8 relic counters (counter-aware). CombatVNet features
already include `sundialCtr`, `cardsPlayedThisTurn`, and per-pile per-card-id
counts. `distgen` already emits `endTurn` (fight length) as a label.
`train_combat_dist.py` already trains a turns-remaining head. `leafdiag`/`leafref`
modes capture full 1766-feature blocks — loop states are post-hoc detectable.

**No ecosystem precedent:** No production-grade runtime infinite-combo detector
exists in any STS AI project. `sts_lean` has formal cycle-closure detection
(anchored state return with accumulated damage). `scumthespire` and `bottled_ai`
use hardcoded per-card play-order heuristics and depth caps for loop prevention,
not loop exploitation.

**Historical gate pattern:** Every rollout-policy intervention tested in the
last week lost its paired gate at statistically significant levels: rollout
caps −5.9pp (§119), prior-guided rollouts −7.0pp (§124c), K-rollouts
−14.8pp at K=10 (§133), one-turn bootstrap −16.4pp (§133), turn-beam −3.5pp
at 9.3× CPU (§135b). The consistent reading: full-horizon terminal grounding
through the random rollout is load-bearing.

**Expert tables:** Dropkick obtain weight = 2 (floor), Sundial entirely absent
from ExpertKnowledge. The deployed win tree has 0/1060 splits on relic-counter
features — Sundial-based combo states are invisible to the learned value
function.

## Design

Four phases, each independently verifiable and gated before proceeding.
The key design bet: PUCT-prior multiplication (Phase 3a) modifies tree
descent, not rollouts — a channel with no historical falsification.

### Phase 1 — Simulator survival (prerequisite)

Two minimal changes to make the simulator not punish winning infinites.

**1a — Env-configurable S3 rollout step cap:**
Replace the hardcoded `200` in `playoutRandom`'s `while` condition with
`g_s3RolloutSteps` (extern int, default 200). Parse `STS_S3_ROLLOUT_STEPS`
in `apps/one_combat.cpp::main` alongside the other S3 rollout gates. Print
in the BEST stack banner. Byte-identical when unset.

**1b — Fix loop guard + progress tracker:**
Two-part fix in `BattleContext::executeActions()`:

1. Before the `PLAYER_LOSS` assignment at `loopCount > 1,000,000`: check
   `if (monsters.monstersAlive == 0) { outcome = Outcome::PLAYER_VICTORY; break; }`.
   This is a correctness fix — if all monsters died during a long action chain,
   the battle was won regardless of iteration count. Active regardless of env
   flags.

2. Add a no-progress turn tracker: track `prevTotalMonsterHp` across
   `END_TURN` boundaries. If total monster HP does not decrease for
   `STS_INFINITE_NO_PROGRESS_TURNS` consecutive turns (default 100) AND
   monsters are alive, set `PLAYER_LOSS`. Gated behind
   `STS_INFINITE_ROLLOUT=1`. Reset in `BattleContext::init()`.

**Files:** `src/sim/search/BattleScumSearcher3.cpp`,
`include/sim/search/BattleScumSearcher3.h`, `src/combat/BattleContext.cpp`,
`include/combat/BattleContext.h`, `apps/one_combat.cpp`

### Phase 2 — Mechanical combo detection

`detectComboPotential(const BattleContext& bc)` in new file
`src/sim/search/ComboDetect.cpp`. Detects the Dropkick archetype only
(most common and best-understood Ironclad infinite):

- (a) Dropkick (`CardId::DROPKICK`) accessible in hand or draw pile;
- (b) Monster is Vulnerable OR a Vulnerable-source card
  (Thunderclap/Bash/Uppercut/Clothesline/Shockwave) is in hand and playable;
- (c) Total non-exhaust deck size (hand + draw + discard, minus
  exhaust-on-play cards) ≤ 10, OR Corruption (`Status::CORRUPTION`) is
  active with skill-based draw available;
- (d) Current energy + Dropkick refund ≥ Dropkick cost.

Sets `bc.comboDetected` flag at the start of each `PLAYER_NORMAL` state.
Gated behind `STS_COMBO_DETECT=1` (default off). Read-only on BattleContext.
Future archetypes (Sundial/Corruption/Dark Embrace exhaust loops) can be
added as subsequent detector functions sharing the same `comboDetected` flag.

**Files:** `src/sim/search/ComboDetect.cpp`, `include/sim/search/ComboDetect.h`,
`include/combat/BattleContext.h`, `src/combat/BattleContext.cpp`,
`src/sim/search/BattleScumSearcher3.cpp`, `apps/one_combat.cpp`, `CMakeLists.txt`

### Phase 3 — Search steering

Two independent channels, separately gated:

**3a — PUCT-prior boost (primary, novel channel):**
In `computeEdgePriors` (BattleScumSearcher3.cpp), after standard softmax:
when `g_comboPriorBoost > 1.0 && state.comboDetected`, for every edge
whose action is Dropkick, multiply its prior by `g_comboPriorBoost` and
renormalize all priors to sum to 1. Gate: `STS_COMBO_PRIOR_BOOST` (float,
default 1.0 = off). Affects PUCT exploration only — Q-value exploitation
is untouched. This is the channel with no historical falsification (all
prior failures modified rollouts, not priors).

**3b — Rollout cap lift (secondary):**
In `playoutRandom`, when `g_comboRolloutLift && state.comboDetected`,
replace `steps < 200` with `steps < g_comboRolloutSteps` (default 5000).
Gate: `STS_COMBO_ROLLOUT_LIFT=1` (default off). Byte-identical when off.
The Phase 1b progress tracker catches non-terminating stalls. Secondary
because random action selection still has low probability of correctly
sustaining the combo — this just gives the rollout enough runway to reach
terminal.

**Files:** `src/sim/search/BattleScumSearcher3.cpp`,
`include/sim/search/BattleScumSearcher3.h`, `apps/one_combat.cpp`

### Phase 4 — Run-level strategic training (contingent on Phase 3 gate passing)

Add combo-awareness to the strategic training pipeline:

- Add `comboSeenDuringFight` boolean to `strategicgen2` output (set when
  any branch fight triggered the Phase 2 detector).
- Add derived combo-score features to the strategic feature vector:
  `dropkickInDeck × hasVulnerableSource × (1.0 / max(1, deckSize))` and
  `sundialPresent × totalExhaustCards`.
- Regenerate Tier-B labels with combo-aware combat controller
  (`STS_COMBO_DETECT=1 STS_COMBO_PRIOR_BOOST=5.0`), retrain V4 token net,
  paired-gate against the deployed artifact.

Pre-registered verdict: candidate must beat control with CI excluding
meaningful loss. If null → Phase 4 closes cleanly (the §105 one-ply-label
ceiling is confirmed for combo labels too). The §105 lesson applies: the
bet is NOT that engineered labels teach combo-value, but that adding input
features lets the model correlate deck composition with branch-fight
outcomes from the combo-aware combat controller. If the one-ply ceiling
still binds, the line closes with that evidence.

## Verification

All new env flags are opt-in, default-off, documented in the BEST stack
banner. Phase 1 must succeed before Phase 2, Phase 2 before Phase 3.

| Step | Command | Seeds | Required | What it proves |
|---|---|---|---|---|
| Build | `cmake --build build -j` | — | yes | Compiles |
| CTest | `ctest --test-dir build --output-on-failure` | — | yes | Existing tests pass |
| Phase 1a smoke | `STS_FAIR=1 STS_SEARCHER3=1 ... bestbench 1000 8 0` | 8 | yes | Default 200 byte-identical |
| Phase 1a parse | `STS_S3_ROLLOUT_STEPS=400 bestbench 1000 4 0` | 4 | yes | Env flag parses, no crash |
| Phase 1b unit | `./build/test loopguard_victory` | — | yes | Dead-monsters-at-guard → VICTORY |
| Phase 2 unit (+) | `./build/test combodetect_true` | — | yes | Detector fires on Dropkick+Vuln+thin |
| Phase 2 unit (−) | `./build/test combodetect_false` | — | yes | Detector silent on non-combo state |
| Phase 3 smoke | All combo flags, `bestbench 1000 8 0` | 8 | yes | No crash, sanity |
| Phase 3 paired gate | Control arm, `bestbench 1000 32 0 126700` | 32 | no | Baseline for comparison |
| Phase 3 paired gate | Candidate arm, same block + combo flags | 32 | no | Effect size of combo steering |
| Phase 4 | Contingent on Phase 3 gate | — | no | Strategic model combo awareness |

Phases 1-2 use unit tests and 8-seed smokes (cheapest proving checks).
Phase 3 requires a 32-seed paired gate (exploratory — no pre-registered
win-rate target, measure effect size and check for regressions). If the
candidate loses significantly (>3pp with CI excluding zero), the
PUCT-prior channel is falsified and the line closes, matching the
§119/§124c/§133/§135b pattern.

## Risks

- **HIGH — Phase 3 gate likely NULL or NEGATIVE** given the historical
  pattern. Mitigation: Phase 3a (prior boost) targets tree descent, a
  channel with no prior falsification. Phase 3b (cap lift) is secondary and
  independently toggleable. Both are narrow — activated only when
  comboDetected fires, not a blanket change.

- **MEDIUM — Dropkick-specific detector is narrow** and won't catch
  Sundial/Corruption/Dark Embrace exhaust loops. Intentional: the detector
  infrastructure (comboDetected flag, g_comboDetect gate) is designed to
  accept additional detector functions without refactoring.

- **MEDIUM — Random rollout action selection may not sustain the combo**
  even with the cap lifted. The tree descent does most of the work
  (PUCT-steered Dropkick plays), but the rollout from the leaf state may
  wander. Mitigation: the rollout only needs to not LOSE — even if it
  doesn't continue the combo perfectly, the leaf evaluation of the
  post-tree-descent state (monsters at low HP) should be favorable.

- **LOW — `battleStateHash` (Searcher2 TT) omits relic counters**, making
  TT unsound for Sundial-dependent states. Does not affect Phase 2's
  Dropkick detector or Phase 3's Searcher3 path (`CombatObservation::visibleHash`
  includes relic counters). Relevant only if Sundial detection is added later.

- **LOW — `cardsPlayedThisTurn` is int16_t** (max 32,767). An extended
  Dropkick infinite could overflow, causing undefined behavior in Choker/
  Normality checks. At A0 most enemies die in <100 plays. Deferred until
  Sundial/exhaust engine detection is added.

- **MEDIUM — Phase 4 is contingent** on Phase 3 success and the §105
  one-ply-label ceiling. Even if Phase 3 works for combat search, the
  strategic model may not learn to draft combo pieces. Pre-registered
  verdict handles failure cleanly.

## Relevant code and evidence

- `src/combat/BattleContext.cpp` — `executeActions` loop guard (:748-768),
  `onShuffle`/Sundial (:2827-2843), `triggerAndMoveToExhaustPile` (:2846-2873),
  `isCardPlayAllowed` (:731-738), `playCardQueueItem` (:908),
  Unceasing Top (:841), card implementations
- `src/combat/Actions.cpp` — `DropkickAction` (:1035), `GainEnergy`/`DrawCards`
  (:155-179), `EmptyDeckShuffle`/`ShuffleDrawPile` (:181-201)
- `src/combat/CardManager.cpp` — Corruption skill cost (:415-417)
- `include/combat/Player.h` — `sundialCounter` (:71), `cardsPlayedThisTurn` (:79)
- `src/sim/search/BattleScumSearcher2.cpp` — `battleStateHash` (:81-151,
  missing counters), `rolloutActionWeight` (:678, cap-gated), `determinize` (:446)
- `src/sim/search/BattleScumSearcher3.cpp` — `rolloutWeight` (:627),
  `playoutRandom` (:784, 200-step cap), `computeEdgePriors`,
  `enumerateActionsForNode` (:932), `applyParticle` (:72)
- `src/sim/search/CombatObservation.cpp` — `visibleHash` with relicCounters (:52-57)
- `src/sim/search/CombatValueNet.cpp` — `combatExtractFeatures` incl.
  sundialCtr (:363-370), `combatFillActionFeatures`
- `src/sim/search/ExpertKnowledge.cpp` — `getPlayOrdering`, `getObtainWeight`
- `src/sim/search/CombatCpsiNet.cpp` — `buildCpsiEntry` (:262-298)
- `apps/one_combat.cpp` — `strategicGen2`, `leafDiag`, `leafRef`,
  `termLeafBonus`, `cpsiEntryFromRich`
- `train_value_combat.py` — `VCOMBAT_TARGET`, `train_combat_dist.py` (turns head)
- `train_strategic.py`, `train_strategic_tok.py`
- External: `github.com/collinzrj/sts_lean` (formal combo semantics)
- EXPERIMENTS.md: §12 (causal per-card), §13 (deck-aware synergy), §14
  (turtle equilibrium), §109/§116 (counter insensitivity), §119/§124c/§133/
  §135b (falsified rollout interventions), §105 (one-ply label ceiling)
- Decision log: `2026-08-08-infinite-combo-investigation.md`

## Open questions

- Does any genuine lethal infinite (Dropkick vs. ~200 HP ≈ 40 plays) survive
  within Searcher3's 200-step rollout cap, or is the loop guard unreachable
  in the deployed S3 regime (200 steps cut first)?
- Does `cardsPlayedThisTurn` (int16_t) overflow before the loop guard trips?
- How often do infinite-eligible states (Sundial + draw loops, thin decks)
  appear in current datagen pools?
- Does the PUCT-prior channel escape the historical rollout-modification
  falsification pattern, or is it the same phenomenon in a different guise?

## Last verified

2026-08-08 — investigation and plan design; no implementation.
