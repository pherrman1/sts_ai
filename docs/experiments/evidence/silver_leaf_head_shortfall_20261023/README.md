# Shortfall head: a leaf value that cannot exceed winning now (2026-10-23)

Thread "Exact combat solving research" (leaf evaluation for Silver), step 3 of the leaf-value plan (fight level),
covered by Philipp's 2026-10-22 17:08Z OK. Written before any result of the shortfall head.

## Why

The fight-level smoke of the turn-penalty candidate (`../silver_leaf_head_ab_20261022`, head `a20`, blend 0.5,
1 point per turn) found Act-2/3 fights where search with the head stops finishing the fight. Traces of four of them
show the head valuing states off the ones it was trained on above any ending they have left: against a lone Mystic
stacking Strength its value rose from 145 to 178 over 20 turns (production ends that fight at 67 HP, the head at 14
and 18), in the Collector fight it ended turns with full energy (75/50 HP against 24/1). Capping the head at the
leaf's win-now value (`STS_SILVER_LEAF_HEAD_WIN_CAP`, commit 0bbc9fdb: Silver's victory score if the fight ended at
the leaf) fixes all four (68/67, 75/59, 55/55, 40/52 HP against production's 67/67, 75/50, 55/55, 46/35) but keeps
only about 60% of the first-fight gain: exact regret change against the playout on the 300 fresh first fights
(111333000-099) -0.149 ± 0.054 (prod) and -0.174 ± 0.050 (max backup) against -0.251 and -0.283 uncapped; on the
150 step-1b held-out fights (111149650-699) -0.117 and -0.159 against -0.331 and -0.265.

A plain head has to learn the current HP, potions and the act-boss heal from the trunk's features before it can
learn what the rest of the fight costs; at a boss the label carries the 75% heal, which may be why the head reads
monster Strength (long boss fights) as good. A shortfall head learns only the second part: it predicts
d = win-now - score, how far below winning now the fight ends, and a leaf is worth win-now - max(0, d). Win-now
enters exactly, so siblings that differ in HP differ exactly, and no leaf is ever worth more than winning now.
Healing (Reaper, Feed) can end a fight above its win-now value; the clamp gives that up (counted below).

## What (pre-registered)

1. Code: `one_combat silversynthfeatures` writes each root's `winNow`; `pack_a20.py` packs it as `winnow`; a head
   file ending in `target shortfall` is a shortfall head for `STS_SILVER_LEAF_HEAD`, the leafhead armset and
   `exact_combat_solver --leaf-heads` (value win-now - max(0, head)).
2. Re-pack the step-1b units (`../silver_leaf_a20_data_20261022`, 736,347 roots) with the new extractor; the state
   blocks must equal the original pack's.
3. `train_head_shortfall.py`: head `a20sf` on the same trunk, folds and early stopping as `a20`, MSE on d / 100.
   Report fold-4 RMSE and bias of the implied value against the actual score, next to `a20` and `a20` capped at
   win-now, by act, room and turn, and the share of roots that end above their win-now value.
4. Exact first fights, the turn-penalty harness (`../leaf_head_turn_penalty_20261022/run_tp.sh`), configs prod and
   prod@mb=4: mode `hblend:a20sf:0.5/1` on the 300 fresh fights (111333000-099) and the 150 step-1b held-out
   fights (111149650-699), paired with the rows of none, `hblend:a20:0.5/1` and `hblend:a20:0.5/1+cap` from the
   same solver binary.
5. Choice of the fight-level A/B candidate: `a20sf` (blend 0.5, penalty 1) replaces the capped `a20` if, on the 300
   fresh fights, its pooled paired regret change against none is lower than the capped head's in both configs and
   no encounter is above +0.10 in either config; otherwise the capped `a20` stays the candidate.
6. Descriptive: `a20sf` on the four smoke fights (sources 111339997 fights 14 and 19, 111339999 fights 12 and 18;
   the leafhead diagnostics) next to production, the uncapped and the capped head.

The A/B itself (`../silver_leaf_head_ab_20261022`, seeds 111350000-255) gets its own pre-launch review.
