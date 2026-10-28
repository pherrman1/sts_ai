# #884 CTM audit: does the active CTM change OOC root rankings? (plan, frozen before the run)

## Question

Issue #884: does the active combat transition model (CTM) make errors that reverse OOC sibling-action rankings?

## Read-only preflight (current main `ed2dcb2`)

- **Where the CTM acts.** At A20 the default searches only map roots (ADR-0061, `STS_OOC_MCTS_SCREENS` unset). Every
  other screen is decided by rules or student_sel, which do not read the CTM. So in production the CTM only shapes
  map decisions: it resolves imagined combats in the tree and the three surrogate combats of each rollout3 leaf
  (`STS_OOC_MCTS_LEAF_COMBATS=3`), which then end in the M0-calibrated X2-B leaf (ADR-0057).
- **Active CTM at A20.** The `pathb-a20` stack (`STS_OOC_MCTS_A20_CTM` default on): fast
  `models/candidates/ctm_finetune_hp_pathb_a20_v1.native` (`bdbfafa6…`, ADR-0059), standard
  `selfplay/models/combat_transition_near_full_escape_pathb_a20.native` (`e338506d…`), active Lizard, per-fight
  calibration table `ctm_calibration_pathb_a20_ft_hp_v1.json` (`8c226f23…`, ADR-0058), Act-4 survival model
  (`05279b3c…`, ADR-0048). Combats the stack refuses are played by plain Silver at 500 simulations in the replay
  configuration (`STS_OOC_MCTS_UNSUPPORTED_SILVER_SIMS=500`). Outputs: P(death), a histogram of post-combat HP given a
  win, and sampled post-combat state (potions, relics, gold, max HP).
- **Existing references.** §408/§410: low-sim Silver forecasts single fights better than the CTM on every field (older
  stacks, shared hidden future caveat). §411: a Silver combat resolver inside OOC MCTS gave +3.1 pp [−3.1, +9.4] at
  matched simulations (A0, old stack). §485: on 15 selective roots Silver8 beat CTM8 by +0.021 [+0.002, +0.044] on a
  plain-10k reference (old stack). §416/§420/§421: per-card CTM strength separated card options about 7× less than
  Silver. §670/§676/§679: the current stack's per-fight calibration on real production fights (log loss 0.0711 →
  0.0660, HP MAE 8.65 → 7.59). None measured the current stack's effect on sibling rankings at production roots.

## Roots

The same cohort as #881: the 16 already-used §683 MAP seeds `111374100`–`111374115`, replayed with the campfire
stage-0 replay environment (`replay_unit.sh`, the §683 MAP configuration) plus `STS_CALLING_BELL_CARD_RNG_FIX=0`.
No new seeds. Every replay must reproduce its §683 MAP trace (trace check as in campfire stage 0); a replay that
does not is dropped and reported. Audited roots: every second searched real root with at least two unpruned
actions (`STS_OOC_CTM_AUDIT_EVERY=2`), i.e. map roots, about 20 per full game.

## Measurement (`STS_OOC_CTM_AUDIT`, play-neutral, forked child)

At each audited root, after the real search, for the three most-visited unpruned root actions
(`STS_OOC_CTM_AUDIT_TOP=3`): N = 16 rollouts of the search's own leaf (successor, then rollout3 + calibrated X2-B)
in two arms:

- `ctm`: imagined combats drawn by the search's CTM stack (exactly the search's sampler);
- `silver`: every imagined combat played by production Silver (the process's real-fight policy: learned stop, root
  prior and playouts, base budget 10,000) on the same planner RNG.

Stream r is shared by the actions and by the arms (common random numbers up to each rollout's first combat). Leaf
value, rollout policy and every search setting stay fixed; only the combat resolver differs. Every imagined combat
also logs the CTM's forecast of that entry (P(death), mean and sd of HP given a win, the drawn HP's PIT).

## Analysis (`tools/analyze_ctm_audit.py`, seed-cluster bootstrap, 2,000 resamples, seed 884)

- **Primary: cross-fitted regret.** Per root, pick each arm's best action on one half of the streams and score both
  picks on the other half of the Silver arm (both directions averaged). Its mean over roots is zero when the CTM
  arm picks as well as the Silver arm, and positive when CTM errors cost value under Silver combats.
- Secondary (descriptive): ranking reversal rate and material reversals (in-sample regret > 2 paired SE) against
  the split-half flip rate of each arm (noise null); cross-fitted signed sibling-difference error
  `E = D_ctm − D_silver` oriented on the CTM's preferred side (positive: the CTM over-states gaps it acts on);
  correlation/slope of `D_ctm` on `D_silver`; the search's own pick's regret.
- Combat level (silver arm): CTM P(death) calibration (bins, Brier, log loss) and HP-given-win bias, RMSE and
  error variance against the CTM's own predictive variance and PIT (variance ratio ≈ 1 and PIT ≈ uniform mean that
  the residual is the fight's own randomness; above 1 means model error), by room (monster, elite, boss).

## Decision rule

- `DECISION_RELEVANT` if the cross-fitted regret's 95% CI lies above 0. Then report where (room types, acts, pair
  types), whether the combat-level errors explain it, and refer to #885 (data scale, coverage, model/feature limits).
- `NOT_SHOWN` otherwise: stop (#884's decision), with the magnitude bound the CI gives.
- No training, model or default change in either case.

## Caveats fixed in advance

- The Silver arm is a reference, not ground truth: the M0 leaf calibration was fit on CTM-resolved rollouts, so the
  Silver arm's level may be off; rankings and differences are what the rule reads.
- Root actions beyond the top three by visits are not audited.
- Roots of one game are correlated; the bootstrap resamples seeds.

## Cost

Smoke on seed 111374100 (N = 8): 37–169 s per root, almost all in the Silver arm (about 0.6 CPU-s per Silver fight).
At N = 16 and every second root: about 11 CPU-h for the 16 seeds, on this thread's 4-core container.
