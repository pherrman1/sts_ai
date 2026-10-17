# Pre-registration: Silver rollout root table vs the ADR-0040 card table (A20, fight level)

Status: size authorized by Philipp (2026-10-17 17:04Z: "4 workers, 128 seeds on 4 cores"); launch waits for an
independent review PASS. Thread "Distilled
playout card picker" (Philipp, 2026-10-17 16:36Z: "run the models once for each root / turn, value all cards and
just play the highest value cards").

## Question

Does a card-play order that sees the fight state make Silver's greedy leaf rollouts better at equal CPU? The
§479 table (ADR-0040 default) gives every card one fixed score; the audit found that any fixed table matches
Silver's own card choice at most ~48.8% at A20 (37% in act 3), with no gain from splitting by fight, turn or act.

## Intervention (option default off; code commit in `run.sh`)

`roottable<b>`: at every searched root, gen-6 E (`combat_policy_mlp_g6_E.txt`, sha256 `ca9bd7f2…`, the Silver
prior) scores each distinct card (id, upgrade) in hand, draw and discard pile as "play it now" at the root state;
every playout of that search plays cards in that order. Cards made during a playout keep their ADR-0040 entry,
shifted to the same scale. The rollout's category rules (zero-cost first, block check, AoE) are unchanged.
`greedy<b>` is production (ADR-0040 table). One prior call per root; no per-step network.

## Design

`one_combat ctmsilvergen` at Ascension 20, armset `roottable`, the §479 harness otherwise unchanged
(`run.sh`, `env.sh` here): plain Silver 10k source runs whose out-of-combat choices come from distilled heart1
student C (`STS_OOC_HEART1=studentc.bin`, sha256 `eff2f74f…`, greedy, no OOC MCTS; the strategic chain only for
choices student C does not encode), with the global keys flag off (`STS_COLLECT_KEYS=0`, required by the harness) and `STS_STOP_AFTER_ACT=3`. Student C still takes Heart keys on its own (`heartKeyActionAllowed` does not mask them when keys are off), and this harness does not apply `STS_STOP_AFTER_ACT`, so a source run that holds all three keys continues to Act 4 and its Act-4 fights are replayed too (smoke: 1 of 4 sources, seed 111158023),
all boss, elite and event fights plus about one normal fight in three, replayed from the same pre-fight states
with R = 2 combat-RNG redraws per arm. Arms: `greedy2500`, `roottable2500`, `greedy2650`, `roottable2650`,
no tree prior.

- Seeds: sources **111158100–111158227** (128), smokes 111158000–111158099.
- Size: 128 sources on 4 cloud workers (`worker.sh`, `BRIEF-worker.md`), 32 sources each on 4 cores (4 shards of
  8). Binary sha256 in `BINARY_SHA256`. Uploads to `/mnt/project-files/silver-rollout-root-table/wWW.tar`.

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
- CPU match: the primary label stands only if the point estimate of the `roottable2500` / `greedy2650` CPU-per-fight
  ratio (paired over the valid fights) is ≤ 1.00. Otherwise `analyze.py` reports `cpuMatched: false` and the
  label `NOT_CPU_MATCHED`, and no promotion follows from the score contrast.
- Also reported (descriptive): CPU per simulation and per fight ratios with bootstrap CIs; `roottable2500 −
  greedy2500`, `roottable2650 − greedy2650`, per room class, win rate, HP lost, mean rollout length.

## Known limitations

- Source runs use greedy student C, not the full OOC MCTS stack; fights are only a state sample.
- Act 4 / Heart fights appear only in sources where student C collected all keys by itself; they are reported as part of `boss`/`elite` and not separately labeled.
- The prior was trained on A0 gen-6 roots and on hand cards only; off-hand cards are scored out of
  distribution.
