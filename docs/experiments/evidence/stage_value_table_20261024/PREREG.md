# Causal stage-value table for deck changes: pilot, Heart stage first (PREREG, 2026-10-24)

Issue [#855](https://github.com/pherrman1/sts_ai/issues/855), experiment 2 of the post-#853 OOC direction review
(`/mnt/project-files/ooc-direction-review/REPORT.html`). Philipp, 2026-10-24 22:40Z: "starte [...] einen anderen
thread der idee 2 von dem og research plan macht". **Status: Stage A authorized (Philipp 2026-10-24 23:00Z "go stufe A", 8 workers). Runs after the pre-launch review.
Stage B needs its own go.**

## Question

Can we measure, with real fights and common random numbers, what one deck change (add a card, upgrade, remove, lose
HP) does to survival at the fights we die in, precisely enough that a global table of these effects is reproducible
across decks and predicts held-out decks? This is a measurability question. Using the table online is a later,
separate experiment.

## Why, and what earlier work already says

- **#853 / review:** our value machinery is biased on deck decisions (particle arms skip cards and boss relics;
  gen-0 non-map MCTS overrides are net -13 kills even at large Q gaps). No signal we have measures the causal effect
  of a deck change.
- **§396 (E3):** a whole-run counterfactual label moves by less than about ±3 pp per card-reward decision; even a
  random card pick tied V4. Whole-run labels are too noisy per decision.
- **§416 / §421:** pricing card rewards by CTM or Silver fights against the current and next act did not beat the
  teacher. §421's Silver score skipped 24% of rewards (teacher 4%), because fights were fought from the current deck
  and HP against later pools. That is a per-state, myopic score.
- **What is different here:** (1) the interventions are applied to **real stage-entry decks** at natural entry HP,
  so the deck the card joins is the deck that actually meets the fight; (2) effects are **averaged over many decks per
  key** into a global table, so per-state noise is averaged out; (3) base and variants share battle and planner
  seeds (CRN). P300 (destire-mio/sts-ironclad-agent) used this design; their Heart-only table was net 0 online, so a
  later online use must combine early stages too. That is out of scope for this pilot.

## Offline evidence used for the design (no seeds)

From the #852 Heart replays (128 guard arm-C Heart entry decks x 8 copies, same battle seeds across arms;
`/mnt/project-files/act4-combat-strength`, `/mnt/project-files/act4-combat-reusecap`), recomputed in this thread:

| cell | Heart win | CPU s/fight | between-deck share of variance |
|---|---|---|---|
| P 10k (root prior, no prior playouts) | 57.4% | 9.0 | 0.60 |
| PP 10k | 60.8% | 58.0 | 0.59 |
| PPc 40k (production Heart since ADR-0060) | 63.3% | 247.3 | 0.58 |

- Deck-level win rates under P10 and PPc40 correlate r = 0.925; their split-half reliabilities are 0.90 and 0.88,
  so the disattenuated correlation is about 1.0. **Inference:** the cheap P10 policy ranks Heart decks the same way
  as production, at 1/27 of the CPU. P10 is the measurement policy of this pilot (deviation from production, see
  below).
- Within-deck Bernoulli variance is about 0.10. When the policy changes but the battle seed is kept, the residual
  same-seed correlation of outcomes is 0.39 to 0.46. A deck change also changes the draw order, so the CRN
  correlation under a deck change is expected to be lower (assume 0.2 to 0.4). It is measured in Stage A.
- **Power (inference):** one (deck, variant) pair at 4 seeds gives a variant-minus-base SD of about 0.37/√4 per
  deck. A typical add key gets about 65 decks (260 fight pairs): SE about 2.4 pp, about 3.3 pp per half. Gate (a)
  (split-half r ≥ 0.6) then needs a true spread of key effects of about 4 pp SD or more. §396 suggests per-decision
  effects are small, so **gate (a) may well fail**. Stage A exists to find that out for about 24 core-h instead of
  about 200.

Available stage-entry decks (guard §676, `/mnt/project-files/ctm-calibration-ab/units`, rows `*.ctm.jsonl.gz`,
`captureStatus = exactly_one`, `runValid`): Heart 217 (arm C) + 196 (arm A) = 413, of which 21 arm-A decks are
identical to the arm-C deck of the same seed and are dropped (392 distinct); act-3 boss fights 583 (C) + 539 (A).

## Design

**Stage set and order.** Heart first (Stages A and B). The act-3 boss stage (Stage C) runs only if the Heart stage
passes. It needs a small code extension (act-3 boss contexts in `act4replay`) and its own go. This is a deviation
from #855, which lists Heart and act-3 boss together; it saves the act-3 compute if deck effects are not measurable
at the Heart.

**Decks.** All 392 distinct Heart entry decks, ordered by a fixed shuffle (`random.Random(20261024)` over
`(arm, sourceSeed)`). Each deck line is built from `transition.pre` exactly as in `act4_combat_strength_20261024/
make_states.py`: deck with upgrades, relics with counters (`relicData`), bottles, potions, potion capacity, HP and
max HP. Deck halves for gates (a) and (b) are split by source seed (`sourceSeed % 2`), so an arm-A and arm-C deck of
the same run fall into the same half.

**Variants per deck (24, deterministic, `random.Random(f"{arm}-{sourceSeed}")`):**
- 12 `add:X`: X uniform without replacement over Ironclad's reward pool (red, rarity common/uncommon/rare; 72 cards),
  unupgraded. Molten/Toxic/Frozen Egg upgrade the added attack/skill/power as in the game.
- 6 `up:X`: X uniform over distinct upgradeable, not yet upgraded card names in the deck (one copy is upgraded).
- 4 `rm:X` (X may carry `+`): X uniform over distinct removable card names in the deck; one copy is removed.
  Not removable: Ascender's Bane, Necronomicurse, Curse of the Bell, and bottled cards. Removing Parasite costs 3 max
  HP. Bottle indices are remapped after the removal.
- 2 HP losses, `hp:-8` and `hp:-16` (cur HP lowered, at least 1); they give the HP exchange rate at this stage.
  (Two identical variants would replay identical fights, since base and variants share all seeds.)
- If a deck has fewer up or rm candidates, the missing slots are filled with further `add` keys.

**Fights.** `one_combat act4replay` on one line at a time (base or one variant), `SIMS 10000`, `REPLICATES 4`,
`SEED_OFFSET = BASE + 4 * deckIndex`. Base and all 24 variants of a deck therefore share battle seeds and planner
seeds (copy r uses battle seed `BASE + 4 * deckIndex + r`). Combat config = arm **P** of
`act4_combat_strength_20261024/run_unit.sh` (flat exact 10k Silver, g7f_E root prior weight 400, tree prior K 8,
greedy root-table playouts, no prior playouts, learned stop off). 25 x 4 = 100 fights per deck, about 15 min of CPU.

**Stage A (futility check):** the first 96 decks of the order (9,600 fights, about 24 core-h).
**Stage B (Heart table):** the remaining 296 decks (29,600 fights, about 74 core-h). Stage A data are part of the
final table.

## Estimands

- Per fight pair: `d = won(variant, r) − won(base, r)`.
- Per (deck, key): mean of d over the 4 copies.
- **Table entry** `δ_Heart(key)`: mean over decks of the per-deck values; SE by bootstrap over source seeds.
- Combination for later use (not evaluated as a gate here): `d log P(Heart kill) ≈ Σ_s δ_s(key) / p_s`; with only
  the Heart stage this is `δ_Heart / p_Heart`.

## Decision rules (frozen before any seed)

**Stage A futility (after 96 decks):** estimate the true spread of key effects by the method of moments over all
add/up/rm keys with at least 8 deck observations, `σ̂² = Var(key means) − mean(SE²)`, and the per-deck noise from the
data. Project the split-half r of gate (a) for the full 392-deck design. **STOP** (report FAIL, no Stage B) if the
projected r is below 0.35. Otherwise ask Philipp for Stage B.

**Heart-stage gates (after Stage B, all 392 decks):**
- **(a) Reproducibility:** over keys with at least 20 deck observations **in each half** (interpretation of #855's
  "≥ 20 observations"), the Pearson correlation of key means between the two halves is ≥ 0.6. `hp:` keys are excluded.
- **(b) Prediction:** table fitted on one half, evaluated on the other (both directions). For each held-out deck,
  Spearman correlation between the table value of its variants and their observed per-deck δ (`hp:` keys excluded;
  keys absent from the training half predicted 0). Mean over held-out decks; 95% bootstrap CI over source seeds
  must exclude 0 from below (lower bound > 0).
- **(c) Disagreement (descriptive, not a FAIL criterion):** at the card-reward roots of the #854 arm-D traces
  (`/mnt/project-files/ooc-map-only-search/units`, `type = decision` rows with candidate priors), the share of roots
  where the table's best option (skip = 0) differs from the prior argmax and its table margin exceeds 2 SE. Target
  2-10%.
- **Verdict:** PASS = (a) and (b). FAIL = (a) or (b) misses, or the Stage A STOP. INCONCLUSIVE is not used for the
  gates; a Stage A projection between 0.35 and 0.6 is reported as such.

**Reported, no rule:** base replay win rate vs observed entry outcome (fidelity, as in #852); CRN correlation of
base and variant outcomes; HP exchange rate (`hp:-8`, `hp:-16`); the top and bottom 15 keys with CIs; add vs up vs rm
spread; CPU per fight.

## After the result

- **PASS:** Stage C (act-3 boss entries, same design; code extension and its own go), then a validation subset at
  production Heart strength (PPc40) for the keys the table would act on, then a prior-anchored online screen
  (override deck roots only by table margin) as a new pre-registered experiment.
- **FAIL:** deck effects are not cheaply measurable at the Heart with our combat; do not build the act-3 stage.
  Next candidate is #856 (whole-game forks at boss relics).

## Deviations from #855 (stated up front)

- Measurement policy P10 instead of production Heart (PPc40), justified by the deck-ranking agreement above; a
  production-strength check is deferred to after PASS.
- Heart first, act-3 boss only after a Heart PASS.
- 392 decks x 4 seeds instead of 96-128 decks x 4-8 seeds: more decks reduce the deck x key heterogeneity part of
  the error, which more seeds cannot.
- `hp:-8` and `hp:-16` added as keys.

## Provenance (to be frozen before launch)

- RUN_COMMIT: the commit that carries this file's final campaign files (stated in the launch message).
  `campaign.manifest` names the code commit and the binary sha256 (v3 preset).
- Seeds (coordinator, 2026-10-24 22:51Z): battle seeds 111303000-111304567 (392 decks x 4; Stage A uses
  111303000-111303383); smokes 111308990-111308999 (111308990-993 used by the deck-0 smoke, 3 variants, rc 0, and a
  determinism rerun of the base line: identical rows).
- Variant file `variants.jsonl.gz` sha256 `ee000b604029724a067ff3b36fd48b75133f4d13e47ab92c8d46e585416322b6`
  (rebuilt byte-identically by `make_variants.py` from the guard rows; 400 distinct Heart decks, the first 392 used).
- Smoke CPU: 3.0-7.4 s per Heart fight at P10 (deck 0).
- Compute: Stage A about 15-24 core-h on 8 workers x 4 lanes; Stage B about 50-74 core-h. Worker count from Philipp.
