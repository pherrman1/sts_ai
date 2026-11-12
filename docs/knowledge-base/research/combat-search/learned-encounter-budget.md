# Learned simulation budget per encounter and state (design and step-B pre-registration draft)

Last verified: 2026-11-12 against main `18b6708` (ledger through §793). Research and planning only. Nothing here
authorizes a run: new seeds, workers and any gate each need Philipp's typed go. Labels: **Measured** (cited ledger
entry or artifact), **Inference**, **Unverified**.

## Question

Philipp, 2026-11-12 17:31 CET: "und ein gelerntes sim budget nach encoutner?" (go 17:34 CET). Can a model choose the
Gumbel root's simulation budget for each fight from the encounter and the entry state? It should buy more Heart kills
at equal CPU, or equal Heart kills at less CPU, than the hand-set budgets of the cheap-combat stack (§790 GP16, §792
H4, §793 PCS). The goal is the [cheap-combat roadmap](cheap-combat-roadmap.md)'s: about 40% Heart at 100-140 CPU-s
per run. There are no hand rules. The encounter is a feature, and one price knob λ trades value against CPU.

## What is known

- **Budget curve (Measured).** Heart rises about 2-2.5 pp per doubling from 2k to 8k (§779) and plateaus above 16k
  (§775, §779). Fewer root simulations everywhere costs 7-8 pp (§791). So the lever is *where* the simulations go,
  not how many.
- **Hand-set reallocation (Measured).**
  - H4 (4k in Act 1-3 hallway fights) is NOT_WORSE at 0.82× CPU (§792).
  - Act-4 prior playouts are +1.6 pp at about 2× CPU (§792).
  - Prior playouts in Act 1-3 bosses are worth about 3.9 pp (§790 against §792).
- **In-search stops (Measured).** These are the closest existing mechanisms. They stop inside one search and do not
  plan the budget of a fight.
  - The real-combat learned stop is the default (#721/#724).
  - The Gumbel learned stop was −2.34 pp, INCONCLUSIVE, and is off (§783).
  - PCS skips confident continuation roots (§793).
- **Step A, offline (2026-11-12,
  [RESULT](../../../experiments/evidence/learned_budget_offline_20261112/RESULT.md)).** It used 1,878 Act 1-3 elite
  and boss fights at 16k / 32k / 64k (4 copies each, §770 / §772 / §774).
  - Between 16k and 64k the per-fight gain shows no state-level signal above copy noise (split-half r ≈ 0).
  - Gains differ by encounter (p 0.001 with max backup).
  - Cost differs about 100× by encounter and is predictable (r ≈ 0.9).
  - A cost-aware allocation beats a uniform budget at equal CPU by 0.2-0.6 HP per fight. Most of this comes from
    the cost side.
  - From about 4.5k to 64k, 13% of the gain variance is real signal.
  - HP lost undervalues bosses, whose HP is mostly healed after Acts 1-2. There the deaths matter: about 1-3 pp per
    boss fight are avoidable.

**Inference.** A learned budget is worth testing as a **cost-aware allocation at the cheap end (1k-16k)** with a
**run-value currency**. Above 16k no state-level gain predictor can be learned from the data that exists.

## Design

**Decision.** At fight start (v1; per decision is a later refinement), pick a budget b ∈ B = {1k, 2k, 4k, 8k, 16k}
for the stack's Gumbel root (`gsh16`, max backup 4). Act 4 keeps the stack's setting in v1, because `selffights`
replays only Acts 1-3 and Act 4 is the roadmap's Track 2.

**Model.** Inputs are the entry features of step A: act, room, floor, encounter, HP, max HP, deck, upgrades, relics,
potions. It has two heads:

- u(x, b), the expected run value after the fight;
- c(x, b), the expected CPU seconds.

The policy is b\*(x) = argmax_b u(x, b) − λ·c(x, b). λ is set offline so that the predicted mean CPU per run equals
the target (a control's CPU for the gainer test). The models are small, either shrunken encounter tables or
gradient-boosted trees, monotone in b. The simplest model that is not worse in cross-fit is chosen.

**Currency (step B0, offline, before any data campaign).** The post-fight run value V(act, floor, HP, max HP,
deck size, death) is fitted as the probability of a Heart kill. It uses the existing whole-run battle traces, for
example `gumbel_wholerun_trace_20261109/results/battles.csv.gz` (46,932 battles with HP before and after and the
seed's outcome), and the per-battle data of §790 / §792 / §793. A death is V = 0. It is frozen before step B's
analysis. With it, a boss death and 10 HP after an elite are on one scale, and λ is in Heart per CPU-second.

**Implementation (later, small).** It generalizes `STS_SILVER_GUMBEL_ROOT_SIMS_HALLWAY`, a fixed budget by room
class. A flag such as `STS_SILVER_GUMBEL_ROOT_BUDGET_MODEL=<file>:<λ>` would read an exported table or tree and set
the flat budget per fight at fight start. The default is off, so the flag has no effect when unset. It is written
only after step B passes.

## Step B: per-fight budget ladder on our own states (PREREG draft, not frozen)

- **Tool.** `one_combat selffights`. The main line is a production run of the cheap stack's combat; at every arm fight
  each arm plays copies 0-3 on the same copy seeds, and the main line continues from production's copy. Arm rooms are
  `1M,2M,3M,1?,2?,3?,1E,2E,3E,1B,2B,3B` (all Act 1-3 fights).
- **Arms.** `gsh16+flat{1000,2000,4000,8000,16000}+mb4`, 4 copies each, with prior playouts as in the stack under test
  (GP16: off). Whether production plays the copies too is open (`STS_SELF_FIGHTS_PROD=main` saves about 1/6).
- **States.** 256 runs on a fresh seed range (Philipp's go). They stay out of the gate's seeds so the model is not
  scored on the runs it learned from.
- **Outcome per copy.** V(post-fight state) from B0; HP lost and death co-reported. CPU per copy.
- **Analysis (cross-fitted, folds by run).**
  - Primary: the policy's mean V per fight minus the uniform-budget frontier at the same mean CPU. The frontier is the
    piecewise-linear mix of the uniform arms. A run-clustered 95% CI is computed at two CPU points: H4's and 0.7×
    H4's.
  - Secondary: encounter table against state model, cost-only, and the split-copy oracle.
- **Decision rule.**
  - The gate is built only if the policy's CI is below the frontier at a CPU point, in the V sense, by at least
    0.3 pp Heart-equivalent per run.
  - Otherwise the result is NOT_SHOWN, goes to the ledger, and the idea is parked.
- **Cost (Inference, check by smoke).**
  - Acts 1-3 of a GP16 run cost about 100 s. The ladder sums to 31k simulations, about 1.9× of 16k. With 4 copies,
    the main line and OOC, that comes to about 9-10× per run, so about 0.25-0.3 lane-hours per run.
  - 256 runs come to about 65-80 lane-hours, about 30-40 minutes on 40 workers × 4 lanes. A 2-seed smoke comes first.
- **Coordination.** It runs only after the roadmap's current campaign (PR #1039, GP16 + H4 + PCS) has finished and
  released W1-W40. The stack under test is whatever that campaign leaves as the cheapest NOT_WORSE stack.

## Step C: whole-run gate (outline)

The learned budget (frozen model, λ for the control's mean CPU) runs on the stack against the stack itself. It uses
§775's 1,024 paired A20 seeds, with the control reused after a 32-game sentinel. The gainer SPRT is
`tools/sprt_gate.py`, ADR-0064 §742. A second arm at 0.7× CPU with a −3 pp non-regression SPRT is optional. It needs
Philipp's go and worker count.

## Open questions

- Per decision instead of per fight. The gain may sit in a few hard turns. That fits PCS and the stops better and
  is left for after v1.
- Act 4 and its prior playouts. Track 2 of the roadmap may give the data, and B could be extended to an Act-4 replay
  (`STS_ACT4REPLAY_BUDGET`).
- Distribution shift. The model learns on the stack's own states, and a budget change moves the states a little.
  A second round would refit on the gated policy's runs.
