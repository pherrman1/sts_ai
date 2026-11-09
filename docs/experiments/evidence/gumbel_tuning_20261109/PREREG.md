# Gumbel teacher tuning: factorial screening of ten search parameters plus Gumbel MuZero below the root (pre-registration)

Status: draft (frozen with the run commit of each stage, see `campaign.manifest`). Plan:
[Gumbel-Teacher Tuning-Experiment](https://claude.ai/artifact/MgXd6w69yBdNMVgfqHjhfz). Philipp asked on 2026-11-08
(~23:00 CET) to rethink the teacher's parameters ("double progressive widening numbers and max backup value, also
sequential halving progress and how much noise gets added by gumbel") and to add Gumbel MuZero's selection below the
root as an arm ("okay dann sollten wir das auch testen, also auch als arm aufnehmen"). At 23:54 CET he approved the
plan's four recommendations (factorial design, D0 seeds, control g16 + mb4, 40 workers): "jup mach alles wie du
recommendest. aber maybe erst nachdem der andere thread die winrate auf 40 workern gemacht hat, also erst in ein paar
stunden." Stage 1 therefore starts only after the full-run win-rate test on 40 workers has finished.

## Question

The Gumbel teacher (§770, §772, and the max-backup run of #1017) uses Silver-production and paper defaults for every
setting except budget and max backup. Which of ten root and tree parameters change the HP the teacher loses per
elite or boss fight at 16,000 simulations, and in which direction? Does Gumbel MuZero's deterministic non-root
selection beat UCB below the root?

## Design

- **Control (ctl):** `gsh16+flat16000+mb4`, §772's best 16k arm (Gumbel root k 16, c_visit 50, c_scale 1, flat 16,000
  simulations, max backup from 4 visits; below the root production UCB 25/25, prior weight 400, tree prior from 8
  visits, widening C 3.7028 at both chance node kinds, exponents 0.52389).
- **Screening design (`design.py` → `arms.tsv`):** a 2^(10−5) fractional factorial of resolution IV, 32 arms d01-d32.
  Base factors A-E in standard order, F = ABCD, G = ABCE, H = ABDE, J = ACDE, K = BCDE (the script checks resolution
  IV and orthogonality). Levels are symmetric around the control on a log scale, except noise and halving, where the
  control sits at one end:

  | Factor | Part | Control | Low | High |
  | --- | --- | --- | --- | --- |
  | A k (root candidates) | `gsh<K>` | 16 | 8 | 32 |
  | B c_scale | `gcs<X>` | 1 | 0.5 | 2 |
  | C Gumbel noise scale | `gnz<X>` | 1 | 0 (top-k by prior) | 1 |
  | D halving budget | `ghb` | equal | equal | back-loaded (phase p gets 2^p / (2^P − 2^p) of what is left) |
  | E max backup from M visits | `mb<M>` | 4 | 2 | 8 |
  | F UCB exploration, decision and chance children | `ucb<X>` | 25 | 12.5 | 50 |
  | G prior bonus weight | `pw<X>` | 400 | 100 | 1,600 |
  | H tree prior from N visits | `tp<N>` | 8 | 2 | 32 |
  | J widening C at end-turn chance nodes | `wet<X>` | 3.7028 | 1.85 | 7.4 |
  | K widening C at other chance nodes | `wch<X>` | 3.7028 | 1.85 | 7.4 |

  The letters skip I, as `design.py` and `arms.tsv` do; the plan document calls the two widening factors I and J.
  These letters (J, K) are the ones used in the analysis and the RESULT.

- **Gumbel MuZero arm (gnr):** `gsh16+flat16000+mb4+gnr`. Below the root, decision nodes select
  argmax_a [π′(a) − N(a)/(1 + ΣN)], π′ = softmax(logit + (c_visit + max N)·c_scale·q̂), logits from the node's tree
  prior (uniform below its visit threshold), q̂ the completed Q (the child's selection value, v_mix for unvisited
  edges with the node's mean value standing in for the value net), min-max normalized as at the root. Chance nodes
  are unchanged. gnr is not in the factorial because it makes F and G inactive.
- **Code (commit 9279ce26, binary e5ba1aad; run commit = the one that fills in the manifest):** the new arm parts are thread-local research overrides: without them every search
  is unchanged, and a part at its default value searches exactly as without it (equivalence check below). New:
  `GumbelRoot::noise`, `backLoaded`, `nonRoot`, `SilverSearcher::selectGumbelNonRoot`,
  `g_nativeSilverPriorWeightOverride`, the `one_combat selffights` mode, and the shared `FightCopies` code that
  expertfights now uses (moved, not changed).
- **Fights (`one_combat selffights`):** A20 production runs (student_sel out of combat through the production chain,
  production Silver with the learned stop) on D0's seeds (111860000-111863071, stage 0 of the combat plan; no new
  seeds). Every fight of acts 1-3 is played by production copies until the first win (copy 0 on the game's battle
  seed, as expertfights). The arm fights are the elite and boss fights. Each arm plays copies 0-3 of an arm fight on
  the same copy seeds (seed, floor, copy). The Baalorlord set stays untouched until stage 4.
- **Scout:** one `SEED 3 scout` unit per seed for seeds 111860000-111860499 (production: the main line, and the arm `prod` on copies 0-3 of every elite and boss fight). It fixes the fights
  per seed, the packages and the unit plan, and is the reference for the reproduction check.
- **Packages (`make_units.py`, by seed order over the scouted seeds with rc 0; every scout unit must have finished,
  otherwise the script stops, so a lost unit cannot shift the packages):** screening = the first seeds whose
  elite and boss fights reach 1,200; its design subset = the first of them whose fights reach 300; combination = the
  next seeds to 600; confirmation = the next to 1,200. `packages.tsv` is committed with the stage-1 units.
- **Stage-1 units:** design seeds play the 32 design arms, ctl and gnr; the other screening seeds ctl and gnr.
  One unit per (seed, act, arm set[, copy selection]); arm sets are packed so a unit is projected under 50 min
  (production CPU per copy × 16,000 × decisions / simulations × 1.5 per arm copy, plus the main line), long fights
  split per copy. `STS_SELF_FIGHTS_PROD=main`:
  production plays only the main line's copies.

## Endpoints and analysis (fixed; `analyze.py screen`)

- **Definitions:** as §770/§772. HP lost per copy = entry HP − exit HP, 0 exit HP on a loss, floor-51 exits inverted
  for the Act-4 heal; an arm's value per fight = mean over the 4 copies; intervals = seed-clustered bootstrap, 10,000
  resamples, seed 20261109.
- **Merging and drops:** copies merged per (seed, floor, arm, copy); a copy seen twice must be identical
  (`conflicts`). Units with rc != 0 are excluded. A fight missing any copy of any arm of its package
  (`missing_arm`) or with an invalid copy is dropped, so the design stays balanced on every fight it uses.
- **Reproduction (gate for the pairing):** every unit's production copy 0 equals the scout's (won, exit HP, exit max
  HP, turns, decisions, simulations, potions used), and its fights up to its act are the scout's. Two rates: the
  share of compared copy-0 fights equal to the scout's (a fight the scout lacks counts as differing) and the share of
  units whose fights are the scout's. Both must be ≥ 99% (`reproduction_gate`); otherwise the result is NOT_PAIRED,
  every verdict reads NOT_PAIRED and the contrasts are reported only descriptively (`descriptive_verdict`).
- **Main effects (primary):** for each factor, mean over the design fights of (mean of the 16 design arms at the
  high level − mean of the 16 at the low level), 95% interval. ACTIVE when the interval excludes 0 (better level =
  the sign); otherwise INACTIVE. No correction across the ten factors: screening chooses what stage 2 combines, and
  only stage 3 decides.
- **gnr (primary):** gnr − ctl on every screening fight, 95%: GNR_HELPS (hi < 0), GNR_HURTS (lo > 0),
  GNR_INCONCLUSIVE.
- **Secondary:** two-factor interactions by alias group (resolution IV aliases pairs with pairs); curvature = mean of
  the 32 design arms − ctl, reported raw and adjusted: the control sits at the +1 end of C and the −1 end of D, so
  the raw value also holds −½·main(C) + ½·main(D), and the adjusted one adds ½·main effect × control level back for
  C and D; each design arm − ctl; mean CPU per copy by arm.

## Later stages (rules fixed now, arms filled in from the results)

- **Stage 2, combination (600 fresh fights, `analyze.py combine`, 95%):** ctl plus at most 6 arms built from stage 1:
  (1) every ACTIVE factor at its better level, the others at the control; (2) (1) with the factor of the largest
  |main effect| one more step in its better direction (k ×2 or ÷2, the others ×2 or ÷2, noise and halving have no
  further step); (3) (1) with the two largest one step further; (4)-(6) (1)-(3) with gnr if GNR_HELPS, otherwise
  without gnr and with the next factor stepped. The pick is the arm with the lowest mean HP lost (ties: fewer changed
  parameters). Stage 2 is a pick, not a test.
- **Stage 3, confirmation (1,200 fresh fights, `analyze.py confirm`, pre-registered here):** the pick at 16,000 vs ctl
  and the pick with flat64000 vs `gsh16+flat64000+mb4`, each 97.5% (Bonferroni over the two). Primary: pick − ctl at
  16k, hi < 0 → TUNED_TEACHER_BETTER; lo > 0 → TUNED_TEACHER_WORSE; lo > −0.3 → NO_TUNING_GAIN; otherwise
  INCONCLUSIVE. 64k is reported with the
  same rule as secondary.
- **Stage 4, test set (once):** the pick at 16k on §711's Baalorlord runs through `one_combat expertfights` (§772's
  units and copy seeds), compared with §772's `gsh16+flat16000+mb4` arm. Reported in the ledger; nothing is tuned on
  it afterwards.
- No default changes on any result. Each stage's campaign starts only after Philipp's go (given for the plan on
  2026-11-08 23:54 CET, with a short note to him before stages 2-4).

## Smoke and equivalence (local, 4 cores, 2026-11-09 CET)

- **Unit test:** `apps/test` `testSilverGumbelRoot` (extended for noise 0, back-loaded halving and gnr, including a
  check that gnr changes the visits and values below the root against plain UCB on the same seed) passes.
- **After the port onto main 117844bc (binary e5ba1aad):** the equivalence check below gives 71 of 71 copies equal
  again, and the scout unit of 111860000 and the arm unit `111860000 1` (ctl, gnr, d01, d02) equal the pre-port runs
  in every field except `producerSha` and the per-copy `combatNetPriors` from #1016 (0 everywhere).
- **Default-valued parts change nothing, the refactor changes nothing:** `one_combat expertfights` on §772's
  Baalorlord run 1697737447 act 1 with `gsh16+flat16000+mb4` and with
  `gsh16+flat16000+mb4+gcs1+gnz1+ucb25+pw400+tp8+wet3.7028+wch3.7028` (every new part at its control value), compared
  with §772's own unit output: 71 copies (production copies, both arms, §772's arm), 0 differ (won, exit HP, exit max
  HP, turns, decisions, simulations, potions, Gumbel root records), sync points equal.
- **selffights is deterministic:** the main line of seed 111860000 through act 3 (29 fights, end floor 52) is identical
  in two runs, and identical again in the scout unit with the `prod` arm (29 of 29 fights). In all 11 arm fights the
  `prod` arm's copy 0 equals the main line's copy 0.
- **Arm units reproduce the scout:** `111860000 1` with ctl, gnr, d01, d02 (all four act-1 arm fights) and
  `111860000 3 … 51:0` (Donu and Deca copy 0 only): the main line equals the scout's on every fight; rc 0. Seed
  111860001's run ends at the act-1 boss (production loses all four copies); its scout unit has 4 arm fights.
- **Cost per arm copy:** CPU over production's on the same copy 1.8-1.9× on Donu and Deca, 3.8-7.4× on the act-1
  fights (production's learned stop searches 3,100-9,300 simulations per decision, the arms 16,000). Per simulation
  the arms cost 0.95-1.64× production (mean 1.26×), gnr and tp2 no more than ctl beyond ~15%. `make_units.py` therefore
  projects an arm copy as production's CPU × 16,000 × decisions / simulations × 1.5 instead of a fixed ratio.

## Cost

- **Scout:** 500 units; a run through act 3 took 828 s (111860000, 613 s of it the `prod` copies), a run that ends
  in act 1 100 s. Estimate ~80 lane-h, under 1 h on 40 workers × 4 lanes.
- **Stage 1:** projected by `make_units.py` from the scout; the projection (`units_screen_projection.tsv`) and lane-h
  are recorded here before the stage-1 launch. Plan estimate ~550 lane-h (~3.5 h on 160 lanes).
