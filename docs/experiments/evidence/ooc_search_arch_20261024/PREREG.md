# OOC search architecture A/B/C pilot at A20: MCTS vs particle root search vs particle beam (pre-registration)

Written 2026-10-24 before any campaign game ran. Design handoff: Philipp's thread message of 2026-10-24 12:59Z
(a ChatGPT spec he adopted), implemented in this thread.

**Authorization:** Philipp, 2026-10-24 12:59Z: "just do it here ... Use 8 workers for testing." 64 paired A20 seeds ×
3 arms on 8 cloud workers.

## Question
Does OOC planning benefit from replacing PUCT's repeated tree visitation with explicit stochastic future sampling
(B − A), and does keeping several contingent plans improve on that (C − B)? C − A asks whether sparse
policy-guided scenario planning is a better architecture than today's MCTS. This is a **screen**, not a qualification.

## Arms (`run_unit.sh` is the source of truth)
Only `STS_OOC_MCTS_SEARCH_MODE` differs. Everything else is one frozen config: today's A20 search stack (the §676
guard / §661 config) with student_sel as tree prior and rollout policy (`cf6bf7fb…`), rollout3 leaf, tree rules,
learned Silver stop with exact root budgets for real combats, g7f_E root table and prior, boss-only prior playouts,
keys on, the default CTM (§679 HP-head fine-tune + its table), CTM rows on.
- **A `mcts` (control):** OOC MCTS 4096 sims, cPUCT 1.5, widening 4/0.75, learned OOC stop 0.99, 25% full-budget
  roots, fast roots capped at 1024. Not retuned.
- **B `particle`:** at every searched (non-singleton) root, each legal root action is forced once on each of
  **P = 64** particles and valued by the same leaf A's root children get on their first visit (the CTM resolves a
  combat on the edge, then the rollout3 continuation under student_sel, then the value head). Particle i of every
  action shares its transition stream (the hidden-world resample and CTM draws) and its leaf stream: common random
  numbers. Root value = particle mean; the highest mean is played. No visits, PUCT, widening or stops.
- **C `particle_beam`:** B's root stage on the same particles, then a beam of **width 8** over plans. A plan is a root
  action plus, at each of up to **D = 3** later nontrivial decisions, the rank (**K = 2**: first or second) of the
  action the tree prior puts there; each particle applies the rank to its own state, so particles with equal public
  states act alike and diverge only after their states differ (a contingent policy, never a clairvoyant action
  sequence). Single-action steps are taken automatically; branching stops at terminals, unsearchable states and once
  the particle has played 3 combats after the root edge. Leaves get the rollout's combats minus those played, so
  every plan is valued at B's horizon (root edge + 3 combats, then the next map). Plans are scored by particle mean;
  the best 8 survive each level; the best final plan's root action is played.
- P, width, K and D are frozen here and will not be tuned on these outcomes.

**Leaf / value head (all arms):** rollout3 ending in the SR_crn_r2_s2_ep20 value head (sha256 `28523fb5…`,
`claude/az-gen2-data` `gen2/value-sr-crn/weights/SR_crn_r2_s2_ep20/student.bin`; §649, the ranking-selected head
that replicated across seeds) blended with X2-B at its selected **w = 0.1**
(`STS_OOC_MCTS_LEAF_HEART1_VALUE` + `_WEIGHT`), with the M0 per-act calibration given explicitly
(`STS_OOC_MCTS_LEAF_CALIBRATION=-2.5384,-2.9227,-3.6523,-3.6334:1.0535`), as arm MS of §661. Why: Philipp asked for
the strongest standalone value head rather than raw X2-B; no newer head exists (ledger through §679). M0 must be
passed explicitly because the ADR-0057 default turns off when a head is set; with it a leaf speaks calibrated
Heart-kill probability, consistent with death = 0 and kill = 1. **Caveat:** this head was never qualified online
(§661's MS used SR_w1, not this head); A is therefore today's search stack with this leaf, not the production default.
The comparison between arms is unaffected because all three share the leaf.

## Implementation (code `febd4814`, research option, default unchanged)
`OocParticlePlanner` (`src/sim/search/OocParticlePlanner.cpp`) over the existing `OocGenerativeModel`; the adapter
(`OocGameContextModel`) supplies candidates, prior, CTM edges and the leaf exactly as for MCTS, plus two hooks
(`edgeCombats`, `evaluateLeafAfterCombats`). No second simulator. Real-play state and RNG are only touched through
the executed root action, as with MCTS (all planning runs on detached snapshots).

Pre-launch checks (results in `SMOKE.md`):
- CTest `ooc_particle_planner` (toy models): exact replay, CRN (root gap = the true action gap), P = 1 = the single
  continuation of particle 0's published streams, beam(1,1) = B's choice, non-anticipativity (equal public
  histories with different hidden rewards decide alike; a revealed reward lets them diverge), pruning, horizon.
- Real roots (`STS_OOC_MCTS_SEARCH_COMPARE=1`, rows only): identical candidate sets for all planners; hidden-world
  invariance of candidates and prior (two hidden-future resamples of the root); P = 1 equals the manual single
  continuation; beam(1,1) keeps B's pick; B's root stage on a fresh model equals C's (replay).
- Default and `mcts` mode reproduce main `413e85d6` (same game record on a smoke seed).

## Seeds and scale
- Campaign: **111302000–111302063** (64 seeds; free block 111301024–111309999 per the seed ledger, not used by the
  running act-4 combat-strength campaign, which uses 111395000–111396023 and 111398100–111399123). One unit = one seed
  with A, B, C in sequence (order rotated by seed % 3) on one lane.
- Smokes and root replay: 111309990–111309999.
- 8 workers × 4 lanes, queue schedule.

## Endpoints
- **Primary:** Heart kills per arm, paired: B − A, C − A, C − B with exact discordance counts (exact McNemar p) and a
  95% seed-bootstrap CI.
- **Secondary:** Act-4 arrival (same pairing), kills per Act-4 arrival, mean final floor (paired difference), deaths by
  act.
- **Search:** searched roots, share of picks off the prior argmax, selection margins (chosen minus runner-up by the
  planner's own score: A's Q gap, B's particle mean gap, C's final plan-score gap), OOC-planning CPU per root and per
  game, simulated transitions and leaf evaluations per root, whole-run wall per arm.
- **Same-root disagreement** (B vs A, C vs A, C vs B, each vs the prior argmax) from the root replay (`roots.py`),
  since paired games share roots only until their first different choice.

## Decision rule (Philipp's spec, frozen)
Screen, not qualification; 64 seeds cannot resolve ±2 pp.
- B or C clearly disastrous (materially fewer Heart kills plus worse floors / Act-4 arrivals): **STOP** that arm.
- A new arm with **≥ 4 more Heart kills than A** and no obvious secondary regression: **PROMISING**.
- B/C roughly tied with A but dramatically simpler/faster or with substantially cleaner margins: keep it alive.
- C clearly beats B: contingent future search adds value. B ≈ C > A: prefer B (the beam is unnecessary).
- B ≈ A and C ≈ A: **STOP**, do not expand because the result is weak.
- Promising but unresolved: extend the same frozen experiment to 256 paired seeds without retuning.
Recommendation will be one of STOP, EXPAND B, EXPAND C, KEEP MCTS.

## Known limitations
- Equal CPU is not required (spec); B is several times cheaper than A per root, C costs more than A's fast roots.
- C's plan class is "policy rank per level", the coarsest contingent policy; it cannot express "rank 1 on card
  rewards but rank 2 on maps" within one level.
- B/C ignore A's learned stop, fast/full budget split and root lock; the policy-target capture in the game record
  (A's PUCT visits) is meaningless for B/C (visits = particles).
- The leaf head was never qualified online (see above).
