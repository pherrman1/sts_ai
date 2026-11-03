# PPO architecture screen (pre-registration, 2026-11-02)

**Status: DRAFT, updated 2026-11-03 after screen 1 (§748).** Not launched. Needs (1) the implementation PRs under
"Prerequisites", each reviewed, (2) review K of this document, (3) Philipp's typed go with a worker count, (4) the
reward screen (screen 2) finished, because both screens use the single PC GPU learner. Written at Philipp's request (2026-11-02, "think
about the architecture of our ppo net"); design reasoning in
[a20-ppo-plan.md](../../../knowledge-base/research/a20-ppo-plan.md) ("Decision net") and the 2026-11-02 literature
follow-up ([ppo-and-combat-leaf-literature.md](../../../knowledge-base/research/ppo-and-combat-leaf-literature.md),
(A) items 8-10). Screen 1 (`ppo_recipe_screen_20261101`, §748) found no PROMISING arm, so the base recipe is screen 1's
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

Design A: eight arms, 16 actor parts, 16 workers. Design B (chosen): the six change arms in `arms.txt`, 24 actor parts.

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
decided as B below: fewer arms that run later and reuse screen 2's controls.

**Design choice: B (Philipp, 2026-11-03 10:37 CET, decision card).** A stays as the written fallback.
- **A, as written:** 8 arms × 30 iterations from net-0000, fresh controls. ~±0.9 pp; self-contained.
- **B, continuation:** every construction above is policy-preserving from *any* net, so the six change arms start
  from screen 2's BASE learner state after update 30 (screen 2 runs fresh BASE and BASE_S1 from heart1 for 60 × 512 on
  the hardened learner code of #973, seed block 111470000-111500719, frozen in its PREREG). They use screen 2's
  saved BASE learner state at that point (`serve --keep-state 30`: `~/ppo-screen2/BASE/state-0030.pt` and
  `net-0030.bin`, sha256 in screen 2's RESULT; Adam moments of new tensors start at 0) and play iterations 30-59 on
  screen 2's seeds for those iterations, evaluated on iterations 40-59 as screen 2. The controls are screen 2's BASE
  and BASE_S1, reused under ADR-0064's control-reuse rule: the P1 binary with zero-initialised inputs replays 32 of
  those seeds and every game must be identical before any change arm runs; a failed sentinel forces fresh
  BASE/BASE_S1 continuations. Six arms instead of eight, ~±0.6 pp (screen 2's estimate), and later iterations,
  where the policy has drifted from heart1. Requires screen 2's BASE learner state after update 30 to be kept on
  the PC and its sha frozen in `screen.manifest`; the learner code must be screen 2's (#973), so P2 must not change
  BASE's updates. Under B this screen plays no seeds of its own beyond the sentinel; the reserved block above stays
  reserved for A or for fresh controls.

**Binding under B (overrides the sections above where they differ; `arms.txt` is design B).**
- **Fork point.** Screen 2 (#975) runs `serve --keep-state 30`, which copies BASE's `state.pt` right after update 30
  (the update trained on iteration 29's games) to `~/ppo-screen2/BASE/state-0030.pt`: net-0030, Adam moments and
  iteration counter 30. That file and `net-0030.bin` are the fork point; screen 2's RESULT records their sha256 and
  this screen's `screen.manifest` repeats them. #975 must be merged and the serve started with `--keep-state 30`
  before screen 2 reaches update 30; otherwise this design falls back to a fresh-Adam fork from `net-0030.bin`
  (recorded as an amendment, re-reviewed by K) and the six arms keep their seeds.
- **Arms:** IN_DECK, IN_RUN, DEPTH6, CRITIC_SEP, AUX, VAL_SPARSE, learner seed 0. Each arm's start state = the fork
  point with the arm's construction (arms table) applied to net-0030; existing Adam moments are kept, new tensors
  get zero moments. P2 provides this as `ppo_cloud.py init STORE ARM --fork-dir ~/ppo-screen2/BASE --fork-at 30
  --local ~/ppo-screen2 ... -- <arm flags>` on the PC, which writes the arm's `state.pt` at iteration 30, its
  `net-0030.bin` and loop.json, puts BASE's iteration-30 parts into the store as the arm's, and records every sha256
  in the arm's config (`fork`).
- **Iterations 30-59, warm-up 0, screen 2's layout:** 512 games per iteration in 4 parts of 128, seed base
  111470000, iteration i plays exactly screen 2's seeds of iteration i. Under `--pipeline 1` iteration i is played
  by net-(i−1), so iteration 30 was played by BASE's net-0029, before any arm change exists: every arm's iteration
  30 games equal BASE's. They are not replayed; each arm's update 31 trains on BASE's kept iteration-30 `parts/`
  (copied, sha256 in the manifest). The arms' own games start at iteration 31 (net-0030 of the arm). 6 arms × 4
  parts = 24 actor parts.
- **Binaries and engine drift.** DEPTH6, CRITIC_SEP, AUX and VAL_SPARSE change only the learner; their actors run
  screen 2's binary (sha256 `71cfd280e121…22d1`) and environment unchanged. IN_DECK and IN_RUN need the P1 binary,
  which is built from defaa930 (the code commit that produced binary 71cfd280, screen 1 `screen.manifest`; screen 2
  uses the same binary) with only P1's diff applied (a build branch, not main), so no
  engine change merged after that commit (e.g. #970, #976) enters; its sha256 goes in the manifest. If a P1 build
  on that commit is not possible, every default-on engine flag merged after it is pinned to `=0` in these arms'
  env, listed in the manifest.
- **Actor sentinel (ADR-0064 §2, IN_DECK and IN_RUN only).** Before those arms run: the P1 binary replays 32 of
  screen 2's BASE iteration-30 seeds with BASE's net-0029, once as stored and once extended by each input arm's
  zero-initialised construction. Every trajectory line (each decision with its logp, and the game line) and every
  outcome must equal screen 2's BASE record. A failure stops IN_DECK and IN_RUN (the four learner-only arms go on)
  until a fixed binary passes.
- **Learner check (all arms).** P2 with all arch flags off, started from `state-0030.pt` and trained on BASE's
  iteration-30 `parts/` on the PC GPU with screen 2's settings, must reproduce screen 2's BASE `net-0031.bin`
  sha256 exactly. If screen 2's own learner code does not reproduce its net-0031 bit for bit on a rerun, the bar is
  instead: P2's max |Δparameter| to net-0031 is no larger than that rerun's. A failure stops the screen.
- **Controls:** screen 2's BASE and BASE_S1 over iterations 30-59, as played (screen 2's PREREG never
  futility-stops them). If screen 2 is aborted before both reach iteration 59, design B is void and A is used.
- **Primary metric:** Heart-kill rate over iterations 40-59 (20 × 512 = 10,240 seeds, screen 2's primary window),
  D = arm − BASE paired by seed, 95% seed bootstrap (10,000 resamples). Noise floor = |BASE_S1 − BASE| on the same
  window. PROMISING / WORSE / NOT_SHOWN as above. Because each arm shares BASE's first 30 iterations, arm − BASE
  varies less than BASE_S1 − BASE (an independent run), so the noise-floor condition is conservative.
- **Screen 2 outcome:** if screen 2 has a PROMISING arm, B still forks from screen 2's BASE (not from the winner);
  combining is S1's job.
- **Workers and cost:** 6 arms × 29 played iterations × 512 games ≈ 89,000 games ≈ 140 core-h (5.5 s/game, DEPTH6
  more), learner 6 × 29 updates on the PC GPU; worker count with Philipp's go.

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
- P2 (learner; design B also needs `ppo_cloud.py init --fork-dir/--fork-at/--local` and the learner check under
  "Binding under B"): `ppo_train.py` flags `--extra-blocks N` (identity-initialised), `--critic separate`,
  `--aux-heads floor,act4 --aux-weight 0.1`, `--value-sparse 3`; `ppo_cloud.py init` applies the arm's construction
  once and records the resulting net sha per arm. The native export (`to_bin`) holds the policy net only (depth
  included); the separate critic and the aux heads live in the learner's `state.pt`, which the critic secondary
  reads (a critic copy in the .bin would roughly double each actor download). Unit tests: each construction reproduces BASE's logits bit-for-bit on cov8 before training;
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
review K's verdict, as in screen 1. A change to an arm's construction or to the base recipe restarts that arm on the
same seeds.

- 2026-11-03 (before launch, no games played): base recipe resolved to screen 1's BASE (§748); screen 2 dependency,
  power note and open design choice A/B added; schedule after screen 2.
- 2026-11-03 10:37 CET (before launch): Philipp chose design B; "Binding under B" added. Fork point stated as
  screen 2's `state-0030.pt` (after update 30, `serve --keep-state 30`).
- 2026-11-03 (before launch), review K FAIL fixes: sentinel uses net-0029 (pipeline lag) and compares trajectory
  lines; iteration-30 games reused from BASE's parts; fork state = #975's `state-0030.pt` with a fallback; `arms.txt`
  rewritten for B; P1 built on screen 2's binary commit (engine drift); learner bit-for-bit check; screen 2 abort
  case restated.
- 2026-11-03 (before launch), P2 implementation: the fork command is `init --fork-dir/--fork-at/--local` (not
  `--from-state/--construct`); critic and aux tensors stay in `state.pt`, not in the native .bin (semantics
  unchanged).

**Knowledge impact.** `a20-ppo-plan.md` "Training recipe" row "net size, start" points here; results go to the
ledger as one entry and to the plan page; an ADR only after S1 and G1.
