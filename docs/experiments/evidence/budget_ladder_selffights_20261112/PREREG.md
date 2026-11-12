# Learned budget step B: per-fight budget ladder 1k-16k on our own H4 states (pre-registration)

**Authorization.** Philipp, 2026-11-12 18:13 CET, in the learned-budget thread: decision card "Schritt B nach dem
PCS-Lauf" and "go mit 40 worker". This is a data run, not a gate. It changes no default and needs no further go. Any
whole-run gate that follows needs its own go.

**Background.** §794 (offline) used 1,878 Baalorlord elite and boss fights at 16k-64k. There, no learned per-fight
allocation beat a uniform middle budget at equal CPU. The open part is the cheap end (1k-16k) on our agent's own
states, in every room. There the budget curve is steeper (§779), and §792's H4 (4k in hallway fights) was
NOT_WORSE at 0.82× CPU. Design: [learned-encounter-budget.md](../../../knowledge-base/research/combat-search/learned-encounter-budget.md).

## Question

Does a budget chosen per fight from act × room, from the encounter, or from the entry state lose fewer Heart-pp than
the uniform budgets at the same CPU? The candidate budgets are 1k / 2k / 4k / 8k / 16k under the Gumbel root (k 16,
max backup 4).

## Design

- **Harness.** `one_combat selffights` ([run_unit.sh](run_unit.sh)). The main line is §792's H4 stack: G16 + mb4,
  16,000 sims, 4,000 in Act 1-3 hallway fights, no boss/elite prior playouts. Out of combat it uses net-0420 at
  temperature 0 with no OOC MCTS. The main line continues from production's copy (`STS_SELF_FIGHTS_PROD=main`).
- **Arm fights.** Every fight of the unit's act (rooms M, E, B, ?) is played under the 5 ladder arms,
  `gsh16+flat{1000,2000,4000,8000,16000}+mb4`. Each arm plays 4 copies on the same copy seeds. The arms use
  production's search settings with these overrides (prior playouts off as in the main line).
- **Units.** 768 = 256 seeds × act 1 / 2 / 3. `STS_SELF_FIGHTS_MAX_ACT=ACT` ends the run after act ACT. The main
  line is deterministic, so a seed's acts are separate processes with the same states. Act-3 units are queued first.
- **Seeds.** 111970000-111970255 (256, a fresh block that no ledger entry has used). They are frozen in `units.txt`,
  and `run_unit.sh` refuses any other seed. They stay out of any later whole-run gate.
- **Binary and code.** Code 3c85fb26, binary ca8d9d0b (§795's), with no code change. Main 6b5102f has the same
  build inputs.
- **Outcome per copy.** HP lost (entry HP minus exit HP, entry HP on a loss, floor-51 exits inverted for the Act-4
  heal), death and CPU.
- **Primary currency.** §794's frozen `currency.json`, pooled exchange table:
  - a death costs 100 · V_mean(act, room) pp;
  - otherwise the loss is dV/dHP(act, room) · HP lost, with Act 1-2 boss HP at 25%.
  - HP is co-reported.

## Analysis ([analyze.py](analyze.py), frozen with this file; `--selftest` passes)

- **Fights.** Fights of the unit's own act from rc-0 units. A fight needs all 4 copies of all 5 arms; otherwise it is
  dropped as `missing_side` and listed.
- **Uniform frontier.** The lower convex hull of the 5 uniform arms (mean CPU per fight, mean loss).
- **Policies.** All are cross-fitted with 5 folds by seed. Each picks the arm that minimizes predicted loss plus
  λ · predicted CPU, with λ set so the predicted CPU equals the target. Encounter and table cells are shrunk with
  k 20.
  - P1 is an act × room table.
  - P2 is an encounter table.
  - P3 is a ridge regression on the entry features (act, room, floor, HP, max HP, HP share, deck, upgrades, relic and
    potion counts, encounter).
- **Targets.** The CPU of uniform 4k and of uniform 8k.
- **Contrast.** Per fight: the policy's loss minus the frontier's loss at the policy's realized CPU (the same linear
  interpolation of the two hull arms for every fight). There are 6 contrasts. CIs are run-clustered bootstraps
  (10,000 resamples, seed 20261112) at 99.17% (Bonferroni, α 0.05). The per-run effect is the per-fight contrast ×
  arm fights per run.
- **Decision rule (Heart pp).**
  - **GAIN (policy@target)** if some contrast has CI upper < 0 and a per-run point ≤ −0.3 pp. The best one is
    named. A whole-run gate of that policy against H4 would follow (new go).
  - **NOT_SHOWN** otherwise. A learned budget is then parked (ledger).
- **Co-reported.**
  - Results in the HP currency.
  - Uniform loss and CPU by act × room for each budget. These are the data for a hand-free per-room budget such as
    H4 or H2.
  - The split-half r of the 1k → 16k gain.
- **Caveats.**
  - The currency is associational (§794).
  - Fight-level losses do not include later knock-on effects, such as potions used or the deck path.
  - Act 4 is not covered (selffights stops after Act 3).

## Cost and schedule (from the smoke, SMOKE.md)

See [SMOKE.md](SMOKE.md) for the measured unit times. The queue runs on 40 workers × 4 lanes, with a 90-minute lease
and a 10-hour unit timeout (rc 124 is final and is listed as a drop).
