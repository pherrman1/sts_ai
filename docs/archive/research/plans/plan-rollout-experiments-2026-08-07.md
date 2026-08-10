# Plan: rollout-leaf experiment continuation (B1 turn-beam, A2 dynamic α, A3 policy filter)

Date: 2026-08-07. Status: **ARCHIVED**. This is historical experiment design,
not current execution guidance. See `docs/knowledge-base/evaluation/current-research.md`.

## 1. Program status

The deployed combat leaf is `α·VNet(s0) + (1−α)·R` (Searcher3 fair,
§126 config, α=0.3, `build/v_combat_honest.txt`), where R is the terminal
outcome of one stochastic rollout (~14 actions avg). The rollout-ideas
program tested leaf-estimator variants; all gates below are paired 256-seed
@1k/64p on the §126 config vs `build/vnet_all_a03_1k.csv` (50.4%, block
126700–126955, full V4 gate stack, fair, S3−belief−chain, 64p, 24 threads).

**Closed lines (do not revisit without a new premise):**

| line | env / config | verdict | evidence |
|---|---|---|---|
| policy-prior rollout sampling | `STS_S3_ROLLOUT_POLICY` | −7.0pp (sig) | §124c |
| policy prior v2 (retrained) | `STS_POLICY=v2` | −2.0pp (null) | §127 |
| rollout caps (heuristic endpoint) | `STS_ROLLOUT_CAPS` | −5.9pp (sig) | §119 |
| K-rollouts, averaged, backprop once | `STS_S3_ROLLOUT_K` | K=2@500 −1.2pp, K=2@1000 −2.0pp (null), K=10@100 −14.8pp (sig) | §133 |
| one-turn bootstrap | `STS_S3_ROLLOUT_TURN_STOP=1` | −16.4pp (sig) | §133 |
| quantile-R GBM leaf | `STS_VNET=v_combat_quantile.txt` | −12.9…−18.4pp (sig, all tested α: 0.3/0.5/0.7) | §133 (2nd) |
| direct utility-R GBM leaf (same-recipe §134 ablation) | `STS_VNET=v_combat_utility_direct.txt`, α0.1 | −12.1pp (sig) | §134 |

**Learned constraints (the premise of the remaining lines):** the rollout
does not need to be stronger or smarter — a mediocre stochastic rollout
provides low-bias comparisons; a systematic (policy-driven) one compounds
errors MCTS learns confidently (§124c/§127). Tree size and long-horizon
**terminal grounding** are load-bearing: halving the tree at equal rollout
work is neutral, a 10× smaller tree collapses win rate by −14.8pp, and
stopping the rollout after one turn is worse than the pre-vnet §119 caps
were (§133). The α0.3 blend's rollout share is not variance-bound. Any new
arm must keep (a) full multi-turn continuation and (b) the terminal
outcome as the endpoint.

## 2. B1 — tactical turn-beam rollout (NEXT, `STS_S3_TURN_ROLLOUT`)

> **Status note (2026-08-07, §134 audit):** NOT implemented in that session.
> As written, B1 simultaneously requires beam pruning and forbids scoring
> partial beam states ("Do NOT score intermediate card states"), which is not
> a complete algorithm — pruning needs intermediate scores. It needs a
> revised spec (e.g. score complete turns only, prune between turns) before
> any implementation; see decision log
> `2026-08-07-experiment-132-133-audit.md`. A1/A4/quantile-R/direct-R lines
> are all closed (§133/§134).

User-approved design (scorer (b), complete-turn scoring):

- In `BattleScumSearcher3::playoutRandom`
  (`src/sim/search/BattleScumSearcher3.cpp`): at PLAYER_NORMAL states,
  beam-search card sequences to END_TURN (width default 8–16, depth = hand
  size) and **score complete candidate turns only, after the monster turn
  resolves** — all candidates are copies of the same state, so draw order
  and monster RNG are shared (common-random-numbers for free).
- Score: `S = w1·ΔHP_enemy − w2·ΔHP_player + w3·kills + w4·persistent_setup
  − w5·potion_use` (env-configurable weights; setup = powers/strength/status
  deltas). "Defend, Defend, End Turn" must rank correctly against a heavy
  intent without a block heuristic — that is what post-END_TURN scoring
  buys. Do NOT score intermediate card states (HP rarely moves mid-turn).
- Execute the best sequence, continue to the next hand → **multi-turn
  rollout** (mandatory: A4 proved one-turn stopping loses −16.4pp).
- Non-PLAYER_NORMAL steps (CARD_SELECT etc.) fall back to the current
  weighted pick. Terminal states end the rollout as today.
- Hand-authored scorer is a rollout heuristic (same class as the existing
  `rolloutWeight`), not a learning objective — flag it in the KB.
- **B1c follow-up (parked):** VNet only on the final 2–4 beam survivors
  instead of a heuristic on all 16 — only if B1's cost is a problem.
- Gate: 256-seed paired @1k/64p vs `build/vnet_all_a03_1k.csv`; searchdiag3
  before/after for `avgRolloutLen` (expect longer, more purposeful
  rollouts). Env stays opt-in default-off; smoke 8 seeds @300 + structural
  equality (`STS_S3_TURN_ROLLOUT` unset = byte-identical).

## 3. A2 — dynamic α by rollout length (`STS_VNET_ALPHA_LEN`, opt-in)

Blend site `BattleScumSearcher3.cpp` (the `g_vnetAlpha` branch in `step()`):
α becomes a lookup over the rollout's action count L. Pre-registered table
{≤2: 0.1, 3–5: 0.2, 6–10: 0.4, >10: 0.6}. L distribution check via
searchdiag3 (baseline avgRolloutLen ~14, so most leaves sit in the >10
bucket). Rationale: a rollout that terminates in ≤2 actions is trustworthy
(low α); a long random continuation is not (high α). Only run AFTER B1 —
B1 reshapes the L distribution this table conditions on. Follow-up if
positive: learn α from more features offline (rollout length, turn,
encounter, HP, tree depth) using the `fit_vwin_calibration.py` pattern.

## 4. A3 — policy-filtered rollout (LAST, `STS_S3_ROLLOUT_FILTER`, opt-in)

Prior gets veto/ranking power, not control: compute the GBM prior
(`computeEdgePriors`, same machinery as §124b), drop the bottom X%
(default 50) of actions, sample **uniformly** among the survivors.
Variant: quartile weights 3/2/1 (pre-registered follow-up). Directly
addresses §124c's diversity-collapse failure. Caveats: ~2.4× cpu (per-step
prior evals, §124b), and the tracked prior is stale (v2 retrain was null,
§127) — a stale prior can still order obviously-bad vs decent actions, but
if A3 is null the prior-based line is dead. Demoted: two prior warnings
already exist, and B1/A4 results may close it entirely.

## 5. Parked (not in scope unless asked)

- **B2 paired-sibling rollouts (common RNG across all children at first
  expansion):** structural tree change (all children get +1 visit);
  caution precedent: `warmStartRootCRN` was −14.1pp (§106). Revisit only
  if a future result shows R-variance between siblings is the binding
  error.
- **Frontier-trained rollout policy (idea 3):** new datagen (expensive
  teacher search at rollout/frontier states) + tiny GBM/MLP. Big line;
  only if B1's quality is promising but its cost is prohibitive.

## 6. Protocol reminders

- Config (both arms): `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0
  STS_S3_CHAIN=0 STS_S3_PARTICLES=64`, full V4 gate stack
  (`STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native`,
  REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1, `STS_OOC_STRATEGIC_MARGIN=1.0`),
  vnet default ON α0.3, block 126700–126955, asc 0, 24 threads,
  `bestbench <sims> 256 0 126700 <out.csv>` on sts-test (nohup; gates
  sequential to keep cpu-s/run clean).
- Local smoke: 8 seeds @300 + structural equality + searchdiag3
  (`avgRolloutLen`/`rolloutActions`); `ctest` 5/5; `git diff --check`.
- Analysis: `paired_analysis.py build/vnet_all_a03_1k.csv <cand.csv> ctl cand`
  (win%, floor, HP, cpu, discordance, CIs).
- Recording: EXPERIMENTS.md entry (next free §134 — note the other agent
  reused §133 for the quantile gate; use a fresh number and reference
  disambiguated titles), decision-log entry, `combat-search.md` rollout
  section, env stays opt-in default-off with banner provenance.
- GCP: box `sts-test` via `gcloud compute ssh … --zone=europe-west3-c
  --project=sts-ai-502709` (native gcloud at `~/google-cloud-sdk/bin` on
  this Linux machine, NOT the Windows gcloud.cmd); sync sources with
  per-file `gcloud compute scp` (multi-file scp silently fails); build
  `cmake --build build -j 24` in `/home/philippherrmann/sts_sweep`.

## 7. Rejected alternatives (from the planning session)

- Scorer (a) reuse of the leaf heuristic `100·(0.7·hpR+0.3·(1−eR))` for
  turn selection — rejected (user): too crude for card sequencing (HP
  rarely moves mid-turn; ignores block/setup/lethal).
- Scorer (c) VNet-scored beam (16 vnet calls/sim) — rejected for the first
  gate: erases the computational point of rollouts; parked as B1c on 2–4
  survivors only.
- K evals backpropagated as K visits — rejected (user): changes PUCT
  exploration; averaging + single visit isolates variance reduction.
