# 2026-08-08 — B1 tactical turn-beam rollout (STS_S3_TURN_ROLLOUT) implemented opt-in

Date: 2026-08-08
Session/task: Implement the B1 line of `plan-rollout-experiments-2026-08-07.md`
(§2) with the user-approved scorer-(b) complete-turn design: beam-search card
sequences to END_TURN at PLAYER_NORMAL rollout states, score only complete
turns after the monster turn resolves, multi-turn continuation.

## Decision

Implement `STS_S3_TURN_ROLLOUT` (opt-in default-off) in
`BattleScumSearcher3::playoutRandom`: a deterministic beam search
(`turnBeamSearch`) over card/potion sequences to END_TURN, pruning between
depths by first-N truncation (`STS_S3_TURN_BEAM_WIDTH`, default 8) with no
intermediate card-state scoring, and scoring complete turns with the
hand-authored heuristic
`S = w1·ΔHP_enemy − w2·ΔHP_player + w3·kills + w4·persistent_setup
− w5·potion_use`
(`STS_S3_TURN_SCORE_W1..W5`, defaults 1.0/1.0/50.0/10.0/30.0). The best
complete turn is executed on the rollout state and the rollout continues to
the next hand. Unset/`=0` is byte-identical pre-B1 behavior. The scorer is a
rollout heuristic (same class as `rolloutWeight`), not a learning objective.

## Rationale

- The §134 audit rejected the original B1 spec as an incomplete algorithm
  (beam pruning needs intermediate scores while the spec forbade scoring
  partial states); the revised spec scores complete turns only and prunes by
  deterministic first-N truncation, which needs no intermediate scores
  (**Inference**: enumeration-order truncation is arbitrary but reproducible;
  a bias toward low hand indices is a known risk).
- Post-END_TURN scoring is what lets "Defend, Defend, End Turn" rank
  correctly against a heavy intent without a block heuristic (HP rarely moves
  mid-turn) (**Inference**, user-approved design).
- Multi-turn continuation is mandatory: A4 proved one-turn stopping loses
  −16.4pp (§133), so the beam must not stop after one turn.
- All beam candidates are copies of the same pre-turn state, giving shared
  draw order/monster RNG (common-random-numbers for free).
- Hand-authored weights are educated guesses; the pre-registered paired gate
  is the arbiter (risks: mis-ranking, lower-index bias, ~16× cpu at 300-sim
  smoke — B1c VNet-on-survivors parked for the cost contingency).

## Alternatives considered

- Scorer (a) reuse of the leaf heuristic `100·(0.7·hpR+0.3·(1−eR))` —
  rejected (user): too crude for card sequencing (HP rarely moves mid-turn).
- Scorer (c) VNet-scored beam — rejected for the first gate (erases the
  computational point of rollouts); parked as B1c on 2–4 survivors only.
- Intermediate-state scoring — rejected by the revised spec (needs a separate
  scoring design; first-N truncation avoids it entirely).

## Evidence

- `include/sim/search/BattleScumSearcher3.h` (B1 globals);
  `src/sim/search/BattleScumSearcher3.cpp` (`turnBeamSearch`,
  `scoreCompleteTurn`, `playoutRandom` branch);
  `apps/one_combat.cpp::main` (env parse + BEST banner `S3-turnBeam`).
- Structural-equality smoke: `bestbench 300 8 0 126700`, fair-S3−belief−chain
  /64p — unset vs `STS_S3_TURN_ROLLOUT=0` per-seed game outcomes identical;
  `STS_S3_TURN_ROLLOUT=1` runs 8 seeds @300 without crash/hang/assert.
- `ctest` 8/8; `git diff --check` clean.
- KB: `docs/knowledge-base/architecture/combat-search.md` (turn-beam section);
  ledger: EXPERIMENTS.md §135b (gate PENDING).

## Status and follow-up

- **Gate (2026-08-08, GCP sts-test): null, line parked.** Paired 256-seed
  @1k/64p on the full V4 gate stack vs `build/vnet_all_a03_1k.csv` (50.4%):
  **46.9% win (−3.5pp, 95% CI [−10.2, +3.1])**, floor −0.1 (CI [−1.3, +1.1]),
  HP end −4.0, at **9.3× CPU** (383.5 vs 41.2 cpu-s/run). The pre-registered
  paired gate was the arbiter; CI crossing zero at 9.3× cost closes the B1
  line (decision log risk list: mis-ranking, lower-index bias).
  `build/b1_turn_beam_1k_256.csv` (md5 6028f837224b845e63254d91062f767f);
  ledger EXPERIMENTS.md §135b updated with the full table.
- Implemented, opt-in default-off; env stays default-off. B1c (VNet on final
  2–4 beam survivors) parked — the cost contingency was premised on a
  positive signal. A2 (dynamic α by rollout length, `STS_VNET_ALPHA_LEN`)
  was gated on B1's gate reshaping the L distribution; run A2 only if a
  lightweight rollout-shape diagnostic still supports the premise.
