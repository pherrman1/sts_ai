# 2026-08-07 — Counter-aware OOC pricing (5.2) closed on evidence, no retrain gate

Date: 2026-08-07
Session/task: Close-out of `plan-winrate-ideas-2026-08-07.md` §5.2
(counter-aware OOC pricing) per user decision.

## Decision

- **Close 5.2 without a retrain gate.** No win-GBM retrain, no C_psi
  rest/event term, no code change, nothing deployed.
- The counter-insensitivity of the deployed win tree (§110: 0/1,060 splits
  on counter features) is treated as the models correctly reading "no
  signal" rather than a deficiency to fix.

## Rationale

- **Diagnostic (this session):** the fresh deployed combat vnet
  (`build/v_combat_honest.txt`, 804 trees) assigns the counter features
  ~0.01% of split gain, and its training data (`build/vcombat_honest.csv`,
  287,517 honest rows) had real counter variance (Happy Flower 0-2/6,075
  nonzero, Nunchaku 0-9/7,879, Pen Nib −1..8/7,160, Sundial, Panache;
  Inserter constant-0 correctly — Defect-only relic). Two independent GBMs
  read no predictive value in counter state conditional on HP/gold/potions/
  deck.
- **Corroboration:** §116's controlled forced-Happy-Flower benchmark found
  no winrate or stall benefit from counter-aligned play; §125's
  counter-SENSITIVE evaluator (C_psi) at the combat leaf was significantly
  negative (−8.6pp).
- **Inference:** OOC decisions (rest/upgrade, events, shop, pathing) barely
  depend on counter state; the in-combat energy-tick signal counters carry
  is already visible to the deployed combat vnet (§126), and the
  combat-side counter-pricing line is closed twice (§116/§125).

## Alternatives considered

- Retrain the win GBM on the current corpus with counter columns populated
  and gate the full stack — rejected by user decision (agreement that OOC
  does not need a counter-aware model); also §108's precedent (a retrain
  gated negative) lowers the prior further.
- C_psi next-fight survival term for rest/event decisions — rejected:
  §93/§111/§125 all negative on C_psi-driven OOC/leaf decisions.

## Evidence

- `EXPERIMENTS.md` §130 (full evidence chain).
- `build/v_combat_honest.json` split-gain computation; `build/vcombat_honest.csv`
  counter-column variance (diagnostic scripts one-off, this session).
- `EXPERIMENTS.md` §110, §116, §125.

## Status and follow-up

- Recorded; plan file §5.2 marked closed. No follow-up (the counter line is
  closed on both the OOC and combat sides).
