# Pre-registration: Silver rollout root table vs the ADR-0040 card table (A20, fight level)

Status: draft, waiting for Philipp's authorization of the run size and an independent review. Thread "Distilled
playout card picker" (Philipp, 2026-10-17 16:36Z: "run the models once for each root / turn, value all cards and
just play the highest value cards").

## Question

Does a card-play order that sees the fight state make Silver's greedy leaf rollouts better at equal CPU? The
§479 table (ADR-0040 default) gives every card one fixed score; the audit found that any fixed table matches
Silver's own card choice at most ~48.8% at A20 (37% in act 3), with no gain from splitting by fight, turn or act.

## Intervention (code `b4bfa618`, option default off)

`roottable<b>`: at every searched root, gen-6 E (`combat_policy_mlp_g6_E.txt`, sha256 `ca9bd7f2…`, the Silver
prior) scores each distinct card (id, upgrade) in hand, draw and discard pile as "play it now" at the root state;
every playout of that search plays cards in that order. Cards made during a playout keep their ADR-0040 entry,
shifted to the same scale. The rollout's category rules (zero-cost first, block check, AoE) are unchanged.
`greedy<b>` is production (ADR-0040 table). One prior call per root; no per-step network.

## Design

`one_combat ctmsilvergen` at Ascension 20, armset `roottable`, the §479 harness otherwise unchanged
(`run.sh`, `env.sh` here): plain Silver 10k source runs with keys off (the harness requires it, so no Act 4),
all boss, elite and event fights plus about one normal fight in three, replayed from the same pre-fight states
with R = 2 combat-RNG redraws per arm. Arms: `greedy2500`, `roottable2500`, `greedy2650`, `roottable2650`,
no tree prior.

- Seeds: sources **111158100–111158227** (128), smokes 111158000–111158099.
- Size: 128 sources on one 4-core container, 4 shards. Smoke-based estimate: about 2–3 hours wall. **Needs Philipp's
  authorization.**

## Outcome, analysis, decision rule

Fight score as §479 (0 on death, else 53 + HP + 11·potions + 0.25·gold + 2·maxHP), replicate mean per fight,
paired per fight, 95% bootstrap over source seeds (10,000 resamples, RNG seed 0), escapes excluded as in §479
(`analyze.py`, a copy of `analyze_479.py` with this run's arms).

- **Primary (CPU-matched):** `roottable2500 − greedy2650`. Smoke: the root table costs about 4% more CPU per
  simulation (longer playouts), so greedy gets 6% more simulations.
  - lower bound > 0 → `ROOTTABLE_HELPS`: next step is an A20 whole-run test with the student C out-of-combat
    stack (separate authorization), plus a per-turn refresh variant.
  - upper bound < 0 → `ROOTTABLE_HURTS`: stop.
  - otherwise `NOT_SHOWN`: stop; the option stays research-only and off.
- Also reported (descriptive): CPU per simulation and per fight ratios with bootstrap CIs (the primary label holds
  only if `roottable2500` CPU per fight ≤ `greedy2650`'s upper CI; otherwise the run is reported as not
  CPU-matched); `roottable2500 − greedy2500`, `roottable2650 − greedy2650`, per room class, win rate, HP lost,
  mean rollout length.

## Known limitations

- Source runs use the harness's frozen out-of-combat policy, not student C; fights are only a state sample.
- No Act 4 / Heart fights (harness requires keys off).
- The prior was trained on A0 gen-6 roots and on hand cards only; off-hand cards are scored out of
  distribution.
