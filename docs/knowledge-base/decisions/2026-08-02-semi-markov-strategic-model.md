# Semi-Markov run-level strategic model

Status: Adopted (active architecture; implementation in progress)
Date: 2026-08-02
Last verified: 2026-08-02 against the current working tree.

## Decision

Run-level decisions are modeled as a semi-Markov process: combat is a
temporally extended transition between strategic decision states, and one
policy scores legal run-level actions with `logit(s,a) = f(z_state,
z_action, z_state ⊙ z_action)`. Combat stays owned by the C++ tree search;
the strategic model never mixes per-tick combat actions into its policy. A
single run-value model `V(s) = P(run victory | s)` is the shared pricing
language across screens (card reward, map, shop, rest, event, relic).
Learned overrides of heuristic decisions deploy only behind a margin gate.

## Rationale

- **Inference:** separating the time scales turns run-level learning into a
  problem with dozens of decisions per run instead of hundreds of per-tick
  combat actions, which is a substantially easier credit-assignment problem;
  it also lets the strong combat solver (Searcher3/PVNet) remain the combat
  authority.
- **Inference:** action-conditioned scoring is required because legal OOC
  actions are heterogeneous and variable in number (different card offers,
  shop items, upgrade candidates), which a fixed output head cannot express.
- **Inference:** a shared run value makes resource pricing (HP, gold,
  potions, upgrades) consistent across screens; screen-specific heads
  specialize on top of the same value signal.
- **Inference (gate):** un-gated greedy NN overrides of heuristic OOC
  decisions are a recorded failure mode (§66m, §70, §73 margin 0), so the
  margin gate is a deployment invariant, not a tuning knob.
- **Inference (hidden information):** the C++ tree search operates on the
  game RNG state, so observation safety must be enforced explicitly in
  strategic datagen and rollouts; sampling unknown outcomes is required
  rather than copying hidden seeds.

## Alternatives considered

- Step-by-step DQN over every simulator tick — rejected: per-tick rewards
  and variable action sets obscure run-level credit and mix combat into the
  strategic policy (spec §2).
- Separate networks per decision screen — rejected for the unified scorer:
  all screens need the same run value and consistent resource pricing;
  type-specific residual heads are the fallback specialization mechanism
  (§71 per-screen value heads keep a shared state encoder).
- Pure episode-level REINFORCE with a single terminal return — rejected as
  the primary method: high variance, every decision gets the same credit
  signal; PPO/GAE (§9) and Tier-B one-ply Q labels were chosen instead
  (round-3 decision).
- Terminal win/loss as the only reward — rejected for the early curriculum:
  floor/act progress is used early for density, win-only later, because
  floor-based reward alone mis-ranks lines (§6).
- Hand-authored card tiers / static relic tier lists — rejected: candidate
  scoring is learned against the actual deck and matchup instead.

## Evidence

- Phase-5 rounds 1–3: `EXPERIMENTS.md` §70 (all-actions `strategicgen`,
  Tier-A policy/value net, one-ply gate −10.9pp at margin 1.0), §71
  (per-screen value heads, gate per-seed neutral; per-screen held-out MAE
  TREASURE 0.59 / REST 0.73 / SHOP 0.97 / REWARDS 2.13 / EVENT 5.21), §73
  (Tier-B one-ply labels via `strategicgen2`, Q-head gate: +4.7pp at margin
  0.5, CIs span zero; greedy margin 0 → −3.9pp; V2 head-interleave bug
  fixed in V3 block-major export).
- Implementation: `apps/one_combat.cpp::runStrategicGenSeed`,
  `runStrategicGenSeed2`, `strategicGen2`, `oocOnePlyCardRewardPolicy`,
  `runFullRunOOC`; `apps/ooc_strategic_net.h::OocStrategicNet`;
  `train_strategic.py`; `export_strategic.py`.
- Recorded fair baseline: `EXPERIMENTS.md` §68 (21.1% / 37.5 floor / 8.6 HP
  on seeds 126700–126827, 1,000 sims, `STS_FAIR=1`); every gate round is a
  paired comparison on that block.
- Active plan with the full source specification:
  `docs/archive/ooc-action-plan-2026-08.md`.

## Consequences (observed)

- The strategic pipeline (collect → train → export → native one-ply →
  paired gate) works end-to-end; no strategic model is deployed by default;
  all learned OOC layers are opt-in behind `STS_OOC_STRATEGIC_NN` and
  `STS_OOC_STRATEGIC_Q`.
- The margin curve is non-monotone (peak at 0.5), so gate rounds sweep
  margins rather than assuming a monotone trade-off.
- Divergence from the spec: PPO (§9) is not yet used — training uses
  Tier-A behavioral + Tier-B one-ply Q labels; an A/B against PPO is
  planned.

## Superseding or invalidating evidence

- §72 invalidated the recorded PVNet 66.4% headline on the current block
  (8.6% at 100 sims) — combat-side evidence; it does not change the
  semi-Markov decision.
- §61/§62 recorded no measured gain from full-map graph encoders for paired
  card/path decisions — Phase B must re-test map graph encoding on the new
  pipeline before treating it as a gain.

## Relevant code

- `apps/one_combat.cpp` — `runFullRunOOC`, `oocOnePlyCardRewardPolicy`,
  `runStrategicGenSeed`, `runStrategicGenSeed2`, `strategicGen2`
- `apps/ooc_strategic_net.h` — `OocStrategicNet`
- `train_strategic.py`, `export_strategic.py`
- `docs/archive/ooc-action-plan-2026-08.md` — historical plan (former spec of record)
- historical session record,
  `2026-08-02-phase5-round2-per-screen-heads.md`,
  `2026-08-02-phase5-round3-tierb-q-labels.md`
