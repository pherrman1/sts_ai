# Boss-relic forks with real combats as an OOC referee/teacher: pilot (PREREG draft, 2026-10-25)

Issue [#856](https://github.com/pherrman1/sts_ai/issues/856), experiment 3 of the post-#853 OOC direction review
(`/mnt/project-files/ooc-direction-review/REPORT.html`, section 4). Philipp, 2026-10-25 09:09Z: "kannst du ein thread
mit idee 3 öffnen, nachdem idee 2 auch gefailed ist?" **Status: draft, not authorized. No seed has been played. Smoke,
Stage A and Stage B each need Philipp's typed go and worker count.**

## Question

At act-1 and act-2 boss-relic roots of real A20 default games, if every option (three relics and skip) is played to
the end of the game with the production stack and the same run seed, does a per-relic table fitted on these forks
pick better than the production pick (student_sel's argmax, `by=heart1_screen` since ADR-0061) on held-out sources?

## What earlier work says

- **§396 (E3, 2026-10-08, older stack, V4 teacher):** whole-run counterfactual labels at boss relics: a random relic
  was −9.0 pp against the teacher's pick, F2 (GBM on those labels) +1.2 pp [−2.7, +5.0]. Boss-relic choices matter;
  a fitted table did not beat a good teacher.
- **§684 (#855):** single deck changes at the Heart are below CRN resolution (key spread τ = 0); HP is measurable
  (16 HP ≈ 4.7 pp). Boss relics are larger interventions than one card, so a spread is plausible, not shown.
- **§683:** extra Act-4 arrivals convert weakly into kills, so **Heart kills are the primary endpoint**, Act-4
  arrival secondary (deviation from #856, which allowed either).
- **#853 / review:** our leaf skips boss relics 25% of the time against 0% for the prior; the forks are a test of
  that disagreement with an unbiased referee.
- **P300 `relicfork` → `relicu`:** +3 pp in their simulator (not comparable).

## Offline facts from #854 (no seeds; arm MAP = today's OOC policy before Act 4 strong, 1,024 games)

- Act-1 root in 86.6% of games, act-2 root in 64.6%; 22 distinct boss relics offered.
- The production pick almost never skips (4 of 1,548 roots). Pick rates per relic when offered range from 0.89 down to
  0.00 (three relics are never taken, five below 0.07): student_sel has a sharp ordering. The forks test it.
- MAP wall 435 s per game (Act 4 under the learned stop).

## Design

- **Sources:** one A20 default game S per seed (`heartoutcomegen 1 SEED OUT off`, the #854 production env with the
  A20 map-only default (ADR-0061) and Act 4 strong (ADR-0060); `run_unit.sh` lists every flag and checks the banners).
- **Forks:** research option `STS_OOC_FORCE_BOSS_RELIC=ACT:CHOICE` (this PR, default off). A fork replays the same
  seed and stack up to S's act-ACT boss-relic root, takes CHOICE, and plays to the end. S itself is the fork of the
  option it took. Forks branch only from S's roots (no nested forks); an act-2 root exists only when S reached it.
- **Why replay and not `finishOocCounterfactual`:** that continuation plays the old deployed chain, not the
  production OOC stack (map MCTS, student_sel, Act 4 strong). Replay keeps every per-run state the driver holds.
- **Fork validity:** every fork's OOC decision trace must equal S's trace row for row before the root, and its root
  row must show the forced choice (`forks.py check`, rc 89 otherwise). A fork that fails is a determinism failure, not
  data; it blocks the stage until explained.
- **CRN:** all options share the run seed; after the root the games diverge naturally. This is fair because the forks
  are training/referee data only, never used at play time.
- **Games per source:** 1 + 3 × P(act-1 root) + 3 × P(act-2 root) ≈ 1 + 2.6 + 2.0 ≈ 5.6.

## Estimands and analysis (`analyze.py`, frozen with this file)

- Outcomes per option: Heart kill (primary), Act-4 arrival, Heart entry HP (reported).
- **Table:** root fixed-effects OLS `y_rj = a_r + u_key + e` with `u_SKIP = 0`, keys = relic names pooled over acts
  (per-act tables reported only). SEs by bootstrap over source seeds.
- **Spread:** method of moments over keys with ≥ 8 appearances, `τ̂² = Var(û) − mean(SE²)`. Projected split-half r of
  the full design: `τ̂² / (τ̂² + mean SE² × n_A / 256)`.
- **Override (full design only):** 2-fold cross-fit by `seed % 2`. Training fold: table, empirical-Bayes shrinkage
  toward 0 with the fold's τ̂². Held-out roots: take the shrunk-best option when it beats the production pick's shrunk
  value by more than 0.03, else the production pick. Gain per source = Σ over its roots of
  `y(rule pick) − y(production pick)`, read directly off the forks (no new A/B needed for this gate).

## Stages and decision rules

- **Smoke (2 seeds):** S + all forks; fork checks pass; S replayed twice is identical; CPU per game measured.
- **Stage A (futility):** first 128 sources. **STOP** if the projected split-half r on Heart kills is < 0.35.
  Otherwise ask Philipp for Stage B. Reported: τ̂, CRN correlation of options within a root, production pick minus
  the mean of the alternatives, skip outcomes, Act-4 numbers.
- **Stage B:** sources 129–512. **PASS:** cross-fitted Heart-kill gain per source, 95% bootstrap CI (10,000 resamples
  over sources, RNG 20261025) with lower bound > 0. **FAIL:** point estimate ≤ 0. Otherwise INCONCLUSIVE.
  Act-4 gain reported, not a gate.

## Power (simulation, `analyze.py` on synthetic roots; inference)

Assumptions: 23 boss relics (22 observed), Heart rate 0.25, within-root option correlation 0.4 (from §569's discordance), root rates
0.88 / 0.66, production pick = argmax of the true effect plus noise of the same size (a decent prior). τ below is the
SD of relic effects on the uncorrelated part; the effective spread is about 0.6 τ.

| τ (effective) | P(STOP) at Stage A 128 | P(STOP) at 256 | P(PASS) at 512 | P(PASS) at 1,024 |
|---|---|---|---|---|
| 0 | 0.93 | 0.93 | 0.00 | 0.00 |
| 0.05 (3 pp) | 0.80 | 1.00 | 0.00 | 0.00 |
| 0.08 (5 pp) | 0.62 | 0.53 | 0.00 | 0.00 |
| 0.12 (7 pp) | 0.30 | 0.17 | 0.05 | 0.25 |

**Reading:** with a decent production pick, the override gain is small (+0.7 pp per source at 512, +1.7 pp at 1,024
even at a 7 pp spread) against a per-source SE of about 1.3–1.9 pp. #856's 256 sources cannot pass; 512 passes only
if relic effects are large *and* student_sel picks badly. Stage A mostly measures whether the spread is large.

## Cost (estimate; the smoke measures it)

About 600 s per game (MAP 435 s in §683 plus Act 4 strong), 5.6 games per source → about 0.9 core-h per source:
Stage A ≈ 120 core-h (≈ 1 h on 32 workers × 4 lanes, ≈ 4 h on 8), full 512 ≈ 480 core-h. Memory: one Heart
search ≈ 2.3 GB, 4 lanes fit a 15 GB container.

## Seeds (assigned by the coordinator 2026-10-25 09:40Z; repo seed guard checked before freezing)

Sources 111378000–111378511 (Stage A 111378000–111378127), smokes 111378990–111378999, inside the free block
111370020–111379989. Forks replay the source seeds (no new seeds).

## Provenance (frozen before launch)

RUN_COMMIT, code commit and binary sha256 (v3 preset) in `campaign.manifest`; student_sel.bin `cf6bf7fb…`.
