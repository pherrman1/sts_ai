# PPO architecture screen (pre-registration, 2026-11-02)

**Status: DRAFT, updated 2026-11-03 after screen 1 (§748).** Not launched. Needs (1) the implementation PRs under
"Prerequisites", each reviewed, (2) review K of this document, (3) Philipp's typed go with a worker count, (4) the
reward screen (screen 2) finished, because both screens use the single PC GPU learner. Written at Philipp's request (2026-11-02, "think
about the architecture of our ppo net"); design reasoning in
[a20-ppo-plan.md](../../../knowledge-base/research/a20-ppo-plan.md) ("Decision net") and the 2026-11-02 literature
follow-up ([ppo-and-combat-leaf-literature.md](../../../knowledge-base/research/ppo-and-combat-leaf-literature.md),
(A) items 7-9). Screen 1 (`ppo_recipe_screen_20261101`, §748) found no PROMISING arm, so the base recipe is screen 1's
BASE. This screen runs after the reward screen (screen 2), not in parallel with it.

**Question.** Which changes to the decision net's inputs, depth, critic and auxiliary targets, one at a time from the
screen 1's BASE, raise the A20 Heart-kill rate of short PPO runs in our engine, and which of those stay within
the actor CPU budget?

**What this screen does not test, and why.** Width (d384, d512) and a smaller width (d128): neither can start from
heart1's weights exactly (RMSNorm normalises over the width, so zero-padding changes every activation), and a
distilled start confounds size with distillation. The size question is already answered at this data scale by G0
(§744: heart1 d256 vs student_sel d64 alone, −0.24 pp [−2.00, +1.51] on 2,048 pairs) and by the literature page's
"architecture is not the lever below ~10^5 games". Width returns as a question when a run reaches ~10^6 games
(roadmap Q2). Every arm here is constructed so that its **policy output at iteration 0 is bit-identical to BASE's**:
the arms differ only in what training can use.

**Fixed before launch.**
- **Base recipe (BASE):** screen 1's BASE: `ppo_train.py --seed 0` with every other learner option at its default
  (screen 1 `arms.txt`, §748: no arm PROMISING, S1 recipe = BASE). The resolved learner argv is written to
  `screen.manifest` before the first game; it is the same for every arm.
- **Screen 2 dependency:** if the reward screen's RESULT has a PROMISING arm, it is **not** adopted here
  automatically. This document is amended (base recipe, start net, controls) and re-reviewed by K before launch. If
  screen 2's CRIT_PRE (pre-trained critic) is PROMISING, CRITIC_SEP and VAL_SPARSE are re-stated against the new
  critic start in that amendment.
- **Start net:** screen 1's `net-0000` (heart1 `1e92f2a6` extended with zero-init inputs by
  `ppo_cloud.py init`), further extended per arm as below, all exactly policy-preserving.
- **Combat:** K15 (`actors_frozen.env` of screen 1, unchanged), ascension 20, `STS_OOC_HEART1_PPO=1`,
  temperature 1, salt = iteration. Binary: the one_combat built at the prerequisite PRs' merge commit (sha in
  `screen.manifest`); all arms share it.
- **Runner:** `tools/heart1/ppo_cloud.py` as screen 1, `--pipeline 1`, 512 games per iteration, 30
  iterations, 3 value-only warm-up iterations, 2 parts per arm.

**Arms** (`arms.txt`; one change each; learner flags are the prerequisite PR's names and may be renamed there, the
semantics below are binding):

| Arm | Change | Construction (policy-preserving at iteration 0) | Hypothesis |
| --- | --- | --- | --- |
| BASE | none | screen 1 net-0000, BASE recipe | reference |
| BASE_S1 | learner seed 1 | same | noise floor of a whole run (minibatch order and chaotic divergence; screen 1's definition, +0.82 pp there) |
| IN_DECK | deck aggregate inputs `x3_deck` (10 scalars on the fixed-observation token): counts of attacks, skills, powers, Strikes+Defends, exhaust-tagged cards, cards that draw; upgraded share; mean cost; deck size; curse count | zero-initialised FixedVec | hand aggregates learn faster than counting from tokens at 10^4 games (tabular-vs-net evidence, literature page Problem 1) |
| IN_RUN | public run inputs `x3_run` (6 scalars): card-removal price, removals bought, floors to the next boss, elite rooms reachable ahead on the current map, Wing Boots charges, free potion slots | zero-initialised FixedVec | the plan's list of public state the net does not see |
| DEPTH6 | two extra transformer blocks after block 4 | `out_proj` and `w2` zero-initialised in the new blocks (pre-norm residual blocks are then exact identities) | more reasoning steps over the token set; the single "bigger" arm |
| CRITIC_SEP | separate critic trunk | critic trunk = copy of the policy trunk at start, with its own RMSNorm and value head; the policy trunk receives no value gradient | the shared mean-pooled linear head is the thinnest part of the design; §747 and the value-flattening paper point at the critic |
| AUX | auxiliary heads on the pooled trunk: final floor / 57 (MSE) and Act 4 reached (BCE), weight 0.1 each, targets from the game line | heads zero-initialised, policy unchanged | KataGo's auxiliary-target efficiency gain (Verified in Go) |
| VAL_SPARSE | value loss on a subsample per game: each act's first decision plus 3 uniformly random decisions (seeded per game), policy loss on all decisions | learner-only change | value flattening (arXiv 2609.18708; Extracted): sparse supervision gives the critic resolution at the states that matter |

Eight arms, 16 actor parts, 16 workers.

**Seeds.** All arms play the block 111440000-111455359 (15,360 seeds; no use on main, in the ledger or in any
evidence file: the only nine-digit strings with that prefix in the repository are decimal fractions inside model
weight text files), iteration i playing 111440000 + 512 i ..., split into two parts as screen 1. Screen 2 must not use this block or the smoke block. Smokes
111459990-111460001 (12 seeds), local, before launch, not analysed. Every actor runs through `tools/seed_guard.sh`
(`ppo_loop.start_actors`).

**Cost rule (pre-registered, measured before launch).** For each arm's start net, `one_combat heart1score` on the
977 records of `ppo_s0_smoke_20261101/cov8.jsonl.gz`, 3 runs, one thread, same container: native milliseconds per
record. Recorded in `screen.manifest` per arm. An arm whose forward costs more than 1.5× BASE's is still run (DEPTH6 is
expected at ~1.5×), but **adoption into S1 requires actor CPU per game ≤ 1.3× BASE's**, from the parts' `actor_s`
meta over the last third (same containers cannot be guaranteed; the ratio is reported with its spread). CRITIC_SEP and
AUX add no actor cost (actors use policy logits only; the native loader reads tensors by name from a map and leaves
unread tensors unused, code read `heart1_policy.cpp` `Net::load`).

**Primary metric and decision.** As screen 1, verbatim: per arm the Heart-kill rate of its last third
(seeds 111450240-111455359, iterations 20-29), paired by seed against BASE, D = arm − BASE with a 95% seed bootstrap
(10,000 resamples); BASE_S1 − BASE is the noise floor. **PROMISING** if D's CI lower bound > 0 and D > |BASE_S1 −
BASE|; **WORSE** if the CI upper bound < 0; else **NOT_SHOWN**. Combat stalls count as losses with screen 1's cap
and INCOMPLETE rule (#965); the sensitivity D without stalled seeds is reported next to the primary.

**Power after screen 1 (Inference).** Screen 1 measured the whole-run noise at this scale: |BASE_S1 − BASE| =
0.82 pp, CI half-width ~0.87 pp on 5,120 paired seeds, and none of 18 recipe changes left that band. An architecture
arm that changes only what training can use is unlikely to move the Heart rate by > 1 pp in 30 updates when the
recipe arms did not, so with this design the most likely outcome is NOT_SHOWN for every arm. Two ways to buy power,
to be decided before review K (open, see "Open design choice"): more games per arm, or fewer arms that run longer.

**Open design choice (decided by Philipp before review K; recorded here as an amendment).**
- **A, as written:** 8 arms × 30 iterations from net-0000, fresh controls. ~±0.9 pp; self-contained.
- **B, continuation:** every construction above is policy-preserving from *any* net, so the six change arms start
  from screen 1's BASE net after iteration 29 (its saved learner state; Adam moments of new tensors start at 0) and
  run 30 more iterations on the seeds screen 2 uses for its BASE/BASE_S1 continuation, evaluated on iterations
  40-59 as screen 2. The controls are then screen 2's BASE and BASE_S1 continuation, reused under ADR-0064's
  control-reuse rule: the P1 binary with zero-initialised inputs replays 32 of those seeds and every game must be
  identical before any change arm runs; a failed sentinel forces fresh BASE/BASE_S1 arms. Six arms instead of eight,
  ~±0.6 pp (screen 2's estimate), and later iterations, where the policy has drifted from heart1. Requires screen
  2's continuation seeds and the screen 1 BASE learner state (on the PC, `~/ppo-screen1`) to be frozen in
  `screen.manifest`.

**Critic secondary (pre-registered, offline, no seeds).** For BASE, CRITIC_SEP, AUX and VAL_SPARSE the final net's
critic takes the §747 teacher check on the 20,677 post-fight states of `heart1_value_leaf_teacher_20261102`
(`build_states.py` output reused; `gates.py` T1 and T5 only): share of states where −3 HP lowers V, and the median
absolute 1-HP price error in secant units. **CRITIC_BETTER** if T1 rises by ≥ 5 pp over BASE's critic and T5's
median falls. This does not change the primary verdict; it decides which critic phase 4 (run-aware leaf, B2 rerun)
starts from.

**Decision.** S1's architecture = BASE's net plus every PROMISING change (two PROMISING critic arms: the larger D; a
PROMISING arm failing the cost rule is not adopted and is named). One combined confirmation run as in the recipe
screen. A PROMISING arm is a hypothesis for S1, not a default; the final net still passes G1 (2,048 fresh paired
seeds, policy alone, Silver 1,000). No ADR before S1.

**Prerequisites (implementation PRs, each with the implementation-review skill, before launch).**
- P1 (native + torch): `x3_deck` and `x3_run` FixedVec inputs in `apps/one_combat/heart1_policy.cpp` and
  `tools/heart1/ppo_model.py` (zero-init, exported always, parity by `tools/heart1/ppo_parity.py --perturb` on cov8:
  max |Δlogit| ≤ 1e-4 and a perturbation that moves logits by ≥ 1). Also the native cost measurement command.
- P2 (learner): `ppo_train.py` flags `--extra-blocks N` (identity-initialised), `--critic separate`,
  `--aux-heads floor,act4 --aux-weight 0.1`, `--value-sparse 3`; `ppo_cloud.py init` applies the arm's construction
  once and records the resulting net-0000 sha per arm; `to_bin` writes critic and aux tensors under names the native
  loader does not read. Unit tests: each construction reproduces BASE's logits bit-for-bit on cov8 before training;
  the micro-batch test still passes with every flag.
- P3 (analysis): screen 1's `analyze.py` extended with the cost ratio and the critic secondary.
- The PPO learner fixes from the 2026-11-02 loop review (seed-sorted game order, fp32 choice head, cross-file seed
  check) land before this screen if they are merged by then; if they land later, they are not applied mid-screen.
  The same holds for the learner `--compile` speed-up named in the plan (§748 follow-up): used if merged and
  validated before launch, identically in every arm. Under design B, any learner fix that changes BASE's updates
  breaks the control reuse and forces fresh controls.

**Cost (estimate, design A; B is about 6/8 of the actor cost).** Schedule: after screen 2's SERVE_DONE; screen 2
is estimated at 8-9 h from its launch, so the earliest start is the day after screen 2 launches. Actors: 8 × 15,360 games × ~5.5 s (K15 ~4 s + d256 forward ~1.3 s, G0) ≈ 190 core-h, DEPTH6
~+0.6 s per game; 16 workers ≈ 12 h wall. Learner: 8 arms × 30 updates × ~70 s ≈ 5 h GPU, CRITIC_SEP ~2× per update.
Transport: 8 × 31 nets × 24-36 MB ≈ 7 GB pushed, ≈ 1 GB of trajectories; `ppo_cloud.py cleanup` at the end.

**Amendments.** Any change after the first campaign game is recorded here with its date, the arms it affects and
review K's verdict, as in screen 1.

- 2026-11-03 (before launch, no games played): base recipe resolved to screen 1's BASE (§748); screen 2 dependency,
  power note and open design choice A/B added; schedule after screen 2. A change to an arm's construction or to the base recipe restarts that
arm on the same seeds.

**Knowledge impact.** `a20-ppo-plan.md` "Training recipe" row "net size, start" points here; results go to the
ledger as one entry and to the plan page; an ADR only after S1 and G1.
