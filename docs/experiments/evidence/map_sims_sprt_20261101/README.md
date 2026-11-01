# Map-simulations non-inferiority SPRT: 1,024 vs 4,096 simulations at A20 map roots (pre-registration, 2026-11-01)

Philipp 2026-11-01 08:26Z "Go mit 24 workern", after §737 (map-root value-of-computation audit, #933): roots with
prior top ≥ 0.98 take 55% of map simulations and change 1.9% of picks; a 1,024 cap changes the pick at 3.7% of map
roots. #927 rank 6 asks for a non-regression SPRT of 1,024 vs 4,096 map simulations, band [−1.5, 0] pp Heart kills.

**Question.** Does searching every A20 map root with 1,024 instead of 4,096 simulations cost less than 1.5 pp of
Heart kills?

**Arms.** A = §727 arm A (production A20 stack, code 8f5b17d6, binary d39c2b98, RUN_COMMIT 3d62ff5e; 4,096
simulations at every searched map root, all of them full-budget roots under ADR-0061). B = the same environment
verbatim plus `STS_OOC_MCTS_FULL_ROOT_SIMS=1024` (existing flag: a full-budget root searches exactly N simulations;
learned OOC stop, gap ladder and fast-root cap untouched; at A20 only map roots search, so only they change;
`run_unit.sh`, checked by `diff` of the env lists). B runs on main `1cd21a15` (v3 binary in the manifest): its build
inputs differ from A's 8f5b17d6 only in `silver_synth_gen.cpp` (act4replay `deckMisc`, not on the heartoutcomegen
path). The worker requires build inputs equal to code_commit, so the run commit sits on current main; the sentinels
below test that this binary still plays A's games.

**Control reuse (why only 716 games are played).** A is not re-played; its 1,536 §727 records are reused
(hashes frozen in `divergence_727A.json`). **Inference (code read, confirmed by §737's review):** at a full-budget
root the 1,024-simulation search is the first 1,024 simulations of the 4,096 search (one RNG from the same
search seed, sequential simulations, no budget-dependent term, stops off). So B plays A's game until the first map
root where A's 1,024 checkpoint pick (`visits_q_id`) differs from A's played action; `divlist.py` finds that root
for each seed (652 of 1,536 seeds, 42.4%). On the other 884 seeds B's game is A's game and d = 0. This needs two
facts the campaign checks:
- **sentinels:** 64 non-diverging seeds (first 64 by sha256 of the seed string) are played in B; each must
  reproduce A's record exactly (every state record, every decision's rule/selected key, the outcome).
- **diverging units:** each of the 652 must match A row for row before the predicted root and pick the predicted
  key there.
If any unit fails either check, or any unit is missing, the reuse is invalid: verdict INVALID, no reading of the
outcome, and the fallback (playing B on the other 820 seeds, ≈ 80 core-h) goes to Philipp.

**Seeds.** None new: the 1,536 USED §727 seeds 111312000-111313535 are replayed (716 of them in B). Smokes on
111312000, 111312003, 111312009 (same seeds, author container).

**Primary.** d_i = kill_B − kill_A per seed (A20 Heart kill). Generalised SPRT, `sprt_gate.py` copied verbatim from
the sequential-gates work (branch claude/project-thread-bdusqi `7b62e61a`, not yet on main), variant
`nonregression` (d0 = −0.015, d1 = 0), α = β = 0.05, look every 64 pairs, pairs in ascending seed order, cap 1,536.
- H1 crossing → **NOT_WORSE**; H0 crossing → **WORSE**.
- No crossing by 1,536 (CAP) → fixed-sample reading: mean d with a 95% seed bootstrap (10,000 resamples):
  NOT_WORSE if the lower bound > −1.5 pp, WORSE if the upper bound < 0, otherwise INCONCLUSIVE.
- Expected size (Inference): var(d) ≈ 0.424 × 2 × 0.21 × (1 − 0.49) ≈ 0.09 (divergence share × outcome variance ×
  §685's sibling ρ), so E[n] ≈ 2,400 pairs at d = 0 and a CAP is likely; at 1,536 pairs the CI half-width is
  ≈ ±1.5 pp.
- **Stage 2 (pre-registered, same authorization):** on CAP, the same design on §683 arm MAP (1,024 used seeds
  111374100-111375123, code of 772df240, map-only full budget) as a second campaign; its pairs continue the same
  SPRT sequence after stage 1's 1,536 (cap 2,560), then the fixed-sample reading over all pairs. Not run if stage 1
  crosses.

**Secondaries (descriptive).** Act 4 reached, Heart reached (floor ≥ 56), death by act, final floor, B − A with
CIs; map simulations and wall per diverging game, A vs B (different containers, so wall is indicative only).

**Decision.** NOT_WORSE → `STS_OOC_MCTS_FULL_ROOT_SIMS=1024` (or an A20 default of 1,024 map simulations) becomes a
default candidate; Philipp decides, in its own PR and ADR, and the learned/gap stops' training scale is noted.
WORSE or INCONCLUSIVE → 4,096 stays; ledger entry either way.

**Smoke (author container, 3 lanes, before launch, on A's own binary d39c2b98).** 111312000 div, 111312003 div,
111312009 sent: all rc 0,
`full_root_sims=1024` banner; `analyze.py` on a test tar of the three: sentinel identical to A, both diverging units
identical before the predicted root and pick the predicted key; map simulations per game 22,528 vs A's 90,112;
wall 610-789 s (A: 971 s for 111312000 in §727).

**Cost.** 716 B games at ≈ 600-800 s each ≈ 140 core-h (24 workers × 4 lanes, about 1.5-2 h).
