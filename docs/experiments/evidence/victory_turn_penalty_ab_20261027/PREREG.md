# #880 Silver victory turn penalty A/B at A20: 0.4 vs 0 per turn (pre-registration)

Written 2026-10-27 before any campaign game ran. Origin: issue #880 ("Experiment: ablate Silver victory turn
penalty"). Draft PR only; the run waits for Philipp's typed authorization.

## Question
Native Silver scores a won leaf `winBonus + HP + potions − 0.4 · turn + …` (`SilverSearcher::evaluateEndState`,
`SilverEvalWeights::victoryTurnPenalty`). Ten extra turns cost 4 HP-equivalents even when HP, potions, gold and max HP
end the same. Does removing that term (equal-resource wins indifferent to combat length) improve or preserve play,
and does it make Silver play materially longer combats or stall?

## Where the term acts (preflight on main `ed2dcb2`)
- Only the won branch of the ordinary leaf. The loss/unresolved branch (including `turnSurvivalWeight` 1.5 per turn,
  no credit past turn 100) is unchanged in both arms.
- Not in the run's final fight: the final-fight leaf (`context.finalFightLeaf`, ADR-0035) scores every win the same.
  That covers the Heart, and also the last Act-3 boss when Act 4 does not follow (keys missing), so those fights are
  identical in both arms by construction. Shield and Spear and every other Act 1-3 fight use the ordinary leaf.
- The live advisor (`native_silver_advisor.cpp`) builds its own searcher and ignores the flag; the exact solver
  keeps its own weights.
- The learned Silver stop (`gbt-0cac7cc64364`) was trained on the 0.4 leaf. B shifts won-leaf values by at most
  0.4 · turns (a few HP-equivalents), so the stop fires on a slightly different value scale in B. Not corrected here
  (one variable); noted as a limitation.

## Arms (`run_unit.sh` is the source of truth)
Only `STS_SILVER_VICTORY_TURN_PENALTY` differs.
- **A (baseline):** unset = 0.4 (main's default). The banner has no `research leaf` line.
- **B (turn-neutral victory):** `STS_SILVER_VICTORY_TURN_PENALTY=0`. Banner
  `[silver] research leaf: gold=0.25 maxhp=2 victoryTurnPenalty=0 concave=0 potionWeights=off`.

Both arms are the key-rules F stack (`key_rules_ab_20261026`, flexible keys) on this branch: `heartoutcomegen … off`
(no state capture) with `STS_OOC_MCTS_SCREENS=none` (student_sel `cf6bf7fb…` alone out of combat behind the rule
chain), real combats with the learned Silver stop and exact root budgets, Act 4 strong (ADR-0060, unset = on), g7f_E
root table + prior (weight 400, tree prior K = 8), boss-only prior playouts, M0 leaf calibration and CTM defaults,
Wing Boots counter on, engine fixes explicit. `STS_OOC_DECISION_TRACE` writes one row per real combat (`turns`,
`outcome`, room class, `escaped`, pre/post state) and per OOC decision; it only reads state. No rollout, budget,
prior, survival-shaping, learned-leaf or infinite-specific change. Why not OOC MCTS on: the question is about combat
search; student_sel alone keeps OOC divergence limited to what different combat results cause, and is ~5x cheaper.

## Seeds and scale
- Campaign **111386000–111386031** (32 seeds, `units.txt`); extension **111386032–111386063** (`units-extension.txt`,
  only under the rule below); smokes **111386990–111386993** (990–991 used, `SMOKE.md`). Free in the seed ledger
  (block 111381000–111389989); no repo record uses 111386xxx; claimed with the coordinator 2026-10-27.
- One unit = one seed, A and B in sequence (order rotated by seed % 2), `run_all.sh` on this thread's 4-CPU cloud
  container, 4 lanes. Fair RNG (`STS_FAIR=1`), A20, paired common seeds.
- Cost: see `SMOKE.md`; expected ~300–450 s per game (a Heart run ~1,500 s), 64 games ≈ 6–8 core-hours ≈ 2–3 h wall.

## Readouts (`analyze.py`)
1. **Combat length per arm:** mean / median / p90 / p95 / max turns per combat, overall, won only, by room class
   (NORMAL / ELITE / BOSS) and by act × room.
2. **Paired combat comparison:** the runs are identical until the first differing trace row. When that row is a combat
   with the same pre-combat state in both arms, it is a paired comparison of the two Silver configurations: turns
   B − A, HP after B − A, potions after B − A, won A/B (bootstrap CIs over seeds), and by room class.
3. **Stalling:** combats with ≥ 30 turns, turn-cap or undecided combats (`turns ≥ 100` or outcome 0), Smoke Bomb
   escapes, and the 10 longest combats per arm.
4. **Outcomes (paired):** Heart kills (exact McNemar), Act-4 arrival, final floor (bootstrap CI), losses by act, wall.
5. **Context only:** Baalorlord's 676 Ironclad A20 runs (`expert_turns.py` on the share copy of the raw `.run` files,
   `expert_turns.json`): mean / median / p90 player turns by room class. Not a target or criterion; the bot's trace
   turn is 0-based, so `playerTurnsByRoom` adds 1.

## Decision rule (frozen)
Evaluated in this order on the 32 seeds:
- **STALL:** B has any turn-cap/undecided combat that A does not, or B has ≥ 3 more combats with ≥ 30 turns than A →
  keep 0.4; revisit turn-neutrality only for certified winning engines (issue #880).
- **WORSE:** B − A final floor 95% CI entirely below 0, or Heart kills A-only − B-only ≥ 4 → keep 0.4.
- **LONGER_ONLY:** B's mean turns per combat ≥ A's + 0.3 (or the paired first-divergence turn CI above 0) while the
  final-floor point estimate is ≤ 0 and Heart kills B ≤ A → evidence against removing the penalty globally; stop.
- **PROMISING:** final-floor point estimate ≥ +0.5 and Heart kills B ≥ A, no STALL → run the 32-seed extension, then
  propose a 1,024-seed confirmation (needs Philipp) if it still holds at 64.
- **INCONCLUSIVE:** anything else → run the 32-seed extension once; at 64 report the same readouts and stop unless a
  rule above fires.
- **SPEED-BIAS flag (descriptive):** if A's turns per combat are well below B's and the expert reference while B
  preserves outcomes, record it as support for "the baseline is speed-biased"; no default change from this run.

## Known limitations
- 32 (or 64) whole-run pairs resolve only large effects: Heart kills ±~15 pp, final floor ±~3 floors. The combat-length
  readouts are the informative part; gameplay quality is directional unless the effect is large.
- Runs diverge at the first combat whose play changes, so only that first combat per seed is cleanly paired; later
  combats are compared as distributions.
- The learned stop was fit on the 0.4 leaf (see above); B tests the term under that stop, not a retuned one.
- The run's final fight cannot differ (final-fight leaf: the Heart, or the last Act-3 boss without keys); Act-4
  differences come from Shield and Spear or earlier play.
