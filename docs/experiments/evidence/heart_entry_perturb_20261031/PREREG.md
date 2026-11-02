# Heart-entry perturbation labels: causal data for an all-feature Heart-entry value (pre-registration)

Status: FROZEN 2026-10-31 before launch; prelaunch review PASS (32d9ccb5, disclosures 2ee649de). Philipp: "Yes go"
(19:14Z) to "start with 16 workers once the review passes". Philipp (2026-10-31): a value model that sees cross-fight
interactions in general, not one hand term per relic like §724's Incense term ("Let's go plan", 14:06Z). Issue #914.

## Idea
Observational outcomes are too noisy to learn effects like §723/§724's Incense phase (59% of the Act-4 outcome is luck,
§720; relic counters added nothing to V_A4, §722). Causal labels are cheaper: change one thing in a Heart-entry state,
play the Heart with the same seeds as the unchanged control, and the outcome difference is that change's effect.
This campaign produces such labels for every state field act4replay can carry. Stage B (separate pre-registration,
offline) fits a Heart-entry value on all features with these labels; stage C gates it as Silver's Shield & Spear leaf
with §724's paired S&S → Heart chain.

## Design (stage A)
- Bases: §721's Heart-entry records (last act-4 MAP state on floor 55, after Shield & Spear and its rewards) from run 1
  and the key-rules, expert-anchored, gumbel-qcap and card-rule campaigns: 4,822 records without repeats, 4,253
  distinct states; 1,000 drawn with seed 20261031 (`tools/make_variants.py`, `variants.tar`).
- Each base gets 16 variants: k = 0 the recorded state (control), k = 1 the same state on a second battle seed
  (reseed: the outcome noise of an unchanged state), k = 2..15 one change each, the operator drawn uniformly among those that apply: HP up or down by 5-30% of max
  HP; max HP ±3..10 (a gain heals as much); a potion removed, added (empty slot) or swapped (types by Heart-entry
  frequency); a combat relic counter (Incense Burner, Nunchaku, Ink Bottle, Pen Nib, Happy Flower, Sundial, Lizard Tail,
  Omamori, Girya) set to another valid value; a relic removed or added (by Heart-entry frequency, not held); a card added
  (by Heart-entry deck frequency, upgrade as drawn), removed or upgraded. All variants carry the whole state the record
  has: deck with upgrades and card misc (new `deckMisc` in act4replay: Searing Blow's upgrade count), relics with
  counters, potions and slots, HP, max HP. Not carried, the same in every variant: bottled cards (the record has no
  bottle index), gold (no use in the Heart; §726 found gold feeds the combat prior), map.
- Disclosed after the prelaunch review (generator as frozen): 50 potion_swap variants swap a potion for the same type
  (no-ops, identical to the control); hp_down is drawn about twice as often as hp_up (1,712 vs 823), because "hp" at
  full HP becomes hp_down; relic_add draws the relic's counter uniformly, including spent values (Lizard Tail, Omamori,
  Girya at 0), and applies no on-pickup effects, so some relic_add labels have a true effect of about 0.
- Play: `one_combat act4replay`, one fight per (base, variant): battle seed 111384000 + I (used block §696) for every
  variant except the reseed, which uses 111382000 + I (used block §691); no new seeds. All variants on the first seed
  share its battle and planner seed. One replicate: the smoke showed that one state change usually changes the whole
  fight, so a second replicate of the same variant adds little over more bases. Silver as §723/§724: learned stop (gbt-0cac7cc64364, ≤ 10k per root, no boss
  extension), one-action roots unsearched, Act 4 strong off, node reuse cap 262,144, g7f_E root table and prior.

## Stage A checks (fixed; `analyze.py`)
A base counts if its unit ended with rc=0 and all 16 fights are valid. CIs: bootstrap over source seeds (10,000, seed
20261031).
- **Determinism** was checked in the smoke (the identical state on the same seed gives the identical fight, 4/4).
- **Sign checks** on the paired effect kill(variant) − kill(control): expected + for HP up, potion added, card
  upgraded, max HP up; − for HP down, potion removed. Each is consistent (CI on the expected side), unresolved, or
  INCONSISTENT (CI on the wrong side).
- **Labels usable** = no INCONSISTENT sign. Otherwise stage B does not start until the cause
  is found (cf. §726's sign anomaly).
- **Co-reported:** how often the outcome flips against the control after reseeding only vs after one change; reseed
  − control kill (should be ≈ 0); control kill rate; mean effect over all perturbations; effect per operator; Incense counter
  changes against §723's table (slope, correlation); CPU.
- Output `labels.csv` (base, source seed, variant, operator, battle seed, won, HP left, turns, CPU) for stage B.

## Stage B and C (planned, pre-registered separately before fitting)
B: a Heart-entry value on every state field (deck counts by card and upgrade, misc, relics with counters, potions by
type and slots, HP, max HP), trained on all labelled fights with CV grouped by source seed; scored on held-out bases'
paired differences (does it predict variant − control better than Silver's leaf formula?). C: the value as Silver's
S&S win leaf in §724's paired S&S → Heart chain; primary Heart kill on − off, on all S&S states and on Incense runs.

## Cost
1,000 bases × 16 variants = 16,000 Heart fights. Smokes (`SMOKE.md`): ≈ 83 CPU-s each → ≈ 370 CPU-h, ≈ 6 h on 16
workers × 4 lanes. Needs Philipp's typed go and worker count.
