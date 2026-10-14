# ADR-0035: Silver's situational leaf terms are on by default

Date: 2026-10-14
Status: accepted

## Context

Silver's terminal score (`SilverSearcher::evaluateEndState`) used fixed weights in every fight. PR #533 added four
situational changes:

- `STS_SILVER_A20_BOSS_HEAL_FIX`: no act-transition heal credit after the first A20 act-3 boss, which the engine
  follows directly with the second boss (a correctness fix, default on from the start).
- `STS_SILVER_FINAL_FIGHT_LEAF`: in a run-ending fight every win scores `winBonus + root maxHp`, and a loss gets no
  potion or cheat-death credit.
- `STS_SILVER_NO_LOSS_POTION_CREDIT`: no 5.5-per-potion credit on any loss.
- `STS_SILVER_RELIC_HEAL_LEAF`: victory HP includes the Meat on the Bone / Burning Blood / Black Blood heals.

Evidence (exact-10k Silver, V4 OOC policy, OOC MCTS off):
- §466, act-3 boss replays: final-fight leaf +0.05 pp [−1.27, +1.38], NOT_SHOWN; deaths holding potions 105 → 0.
- §468, whole runs, all four vs legacy, 500 paired seeds each: A0 Δwin −2.6 pp [−6.4, +1.2] NOT_SHOWN; A20 Δfloor
  −1.29 [−2.42, −0.19] WORSE, wins 52 → 71 (+3.8 pp [+0.6, +7.0]); more act-1 deaths (paired 50 vs 26).
- §474, whole runs, heal fix + final-fight leaf only: A0 +0.8 pp [−1.2, +3.0], A20 Δfloor 0.00, both NOT_SHOWN.

On 2026-10-14 (16:23Z, thread "Situational Silver leaf evaluation") Philipp decided: "i want them default in. then
merge."

## Decision

- Native Silver (`NativeSilverBackend`) runs with all four terms on when the variables are unset. Each variable's `0`
  restores the legacy term; `1` equals the default; any other value is fatal.
- With `STS_SILVER_FINAL_BOSS_BINARY=1` and `STS_SILVER_FINAL_FIGHT_LEAF` unset, the final-fight leaf is off (the
  binary objective replaces it); setting both to 1 stays fatal.
- The live wire path (`searchContextFromWire`) applies the heal fix, no loss potion credit and the relic heal leaf.
  The wire carries no keys, so it applies the final-fight leaf only to the Heart.
- `SilverSearchContext` struct defaults stay off, so unit tests and tools that build their own context are unchanged.
- Teacher manifests (`wholecombatgen` loader): a `final_fight_leaf`, `no_loss_potion_credit` or `relic_heal_leaf`
  field, when present, must match the effective option. Older teachers record none of them and are not checked.

## Consequences

- Every native Silver run plays differently from before. Reproducing earlier results needs
  `STS_SILVER_FINAL_FIGHT_LEAF=0 STS_SILVER_NO_LOSS_POTION_CREDIT=0 STS_SILVER_RELIC_HEAL_LEAF=0` (and
  `STS_SILVER_A20_BOSS_HEAL_FIX=0` for pre-#533 A20 runs); comparisons against controls from an older binary must set
  them in the new arm or rerun the controls. Frozen teachers from before this ADR do not record the terms; replaying
  them as frozen needs the same `=0` settings, which the loader cannot enforce.
- The controls (`base` arms) of §466, §468 and §474 used all four terms off; comparisons against them need all four
  variables `=0`.
- The CTM and Silver priors were trained on legacy-leaf play and may lag until retrained (**Inference**).
- **Unverified:** a playing-strength gain. §468 (the same bundle) was NOT_SHOWN at A0 and WORSE on A20 floors, with
  more A20 wins; the default follows Philipp's decision, not a passed gate.

## Evidence

Ledger §466, §468, §474 (`docs/experiments/ledger-06.md`); evidence
`docs/experiments/evidence/silver_final_fight_leaf_466_20261014/`, `silver_leaf_combo_468_20261014/`,
`silver_leaf_split_471_20261014/`; `docs/knowledge-base/investigations/2026-10-14-silver-situational-leaf.md`.
