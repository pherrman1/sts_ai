# §486 OOC MCTS with heart1 vs V4 as the tree prior, paired by seed (pre-registration, 2026-10-15)

Philipp, 2026-10-15 08:21Z: "Open a new thread which takes care of testing the heart1 adapter with our framework";
09:12Z: "do 128 seeds on a0 and a20. but with the ooc mcts and once the heart1 as a prior, and the other time with our
v4 as the prior. prior should be used inside the tree and for their rollouts for rollout3. then use 32 workers";
09:56Z decision card "Speed up first"; 10:08Z: "okay maybe no prior in the rollout, finish your speedup and give me
the expected cpu hours". So the prior changes inside the tree only; rollouts stay as they are in both arms. Frozen
with the run commit, binary hash and weights hash before launch; independent pre-launch review.

## What is known (baseline)
- heart1 is daniel-ziegler's released PPO out-of-combat policy for silverbot (`heart1.pt`, sha256 `deaba59d…`). In its
  own engine it cleared act 3 in 64/200 A20 games (32.0% [25.9, 38.8]) and killed the Heart in 86/100 A0 games
  (`/mnt/project-files/az-loop-research/heart1-repro/`).
- In our engine, as the direct OOC policy (`STS_OOC_HEART1`, no search), a 36-unit smoke (`smoke.tar.gz`, seeds
  74071950–967) cleared act 3 in 8/13 A20 seeds against 2/13 for our V4 stack. **Inference:** promising, not evidence.
- Our best OOC configuration is OOC MCTS `combo` (§433 at A0; §458 at A20 with the A20 CTM, now the default at A20
  through ADR-0033). Its tree prior has always been V4. §441: a uniform prior plus uniform leaf policy was WORSE than
  `combo` (−7.8 pp), so the prior matters.
- The adapter (#552) is a native port with checked logit parity on early-game states. This change adds the prior
  hook and an exact (bit-identical logits) AVX forward pass, about 2.1x faster.

## Hypotheses
- H1: OOC MCTS with heart1 as the tree prior reaches further at A20 than with V4 as the prior (mean paired floor
  difference > 0).
- H2 (key secondary): it clears act 3 more often at A20.
- H3 (secondary): the same at A0.

## Arms (paired by seed, same binary, `arm_env.sh`)
- Both: §433 `combo` literally (the §422 base: exact-10k Silver via the bestbench budget, V4 OOC gates at margin 1.0,
  `STS_COLLECT_KEYS=0`, `STS_REST_WIN=0`, `STS_STOP_AFTER_ACT=3`; live OOC MCTS with 4096 simulations, `WIDEN_K=4`,
  `WIDEN_ALPHA=0.75`, 3 leaf combats, native leaf, `TEMPERATURE=1`, `CPUCT=1.5`, `MAX_DEPTH=32`, visits root
  selection, early stop), plus `STS_OOC_PUBLIC_FUTURES=8`. No CTM variables: the automatic stack, which at A20 is the
  calibrated `pathb-a20` stack with active Lizard (ADR-0033; §458 used its pre-§470 version). Rollouts in both arms:
  `STS_OOC_MCTS_LEAF_POLICY=v4`, the ordinary chain. All other settings are the run commit's defaults (ADR-0030..0040, including ADR-0039 potion reward swap and ADR-0040 Silver rollout card table).
- `v4`: `STS_OOC_MCTS_PRIOR=policy` (V4 logits).
- `heart1`: `STS_OOC_HEART1=heart1.bin` (sha256 `1e92f2a6…`) and `STS_OOC_MCTS_PRIOR=heart1`. Where V4 covers a node's
  candidates (the existing `sourcePriorCovered` rule, unchanged), heart1's logit replaces V4's for each source
  primitive (a primitive behind several heart1 tokens takes its best token; grouped candidates keep the mean, as for
  V4); softmax at temperature 1 as for V4. Nodes heart1 does not encode, or where a source has no heart1 token
  (Match and Keep, Bonfire Spirits, unmapped events), keep the V4 prior; their share is reported
  (`heart1_prior_fallbacks`). Real decisions the search does not own fall back to the same chain in both arms.
  Keys stay off in the tree (dropped candidates), as in `v4`.

## Seeds and runs
- A20 seeds 107000000–107000127, A0 seeds 107001000–107001127 (`COHORTS`). One `bestbench 10000 1 ASC SEED` unit
  per seed, arm and ascension through `tools/seed_guard.sh` (`run_unit.sh`), 512 units. 32 cloud workers
  (`NWORKERS`, Philipp 09:12Z), each running 4 seeds of each cohort in both arms, 4 units at a time.
- Smokes: 74071950–74071973 in this thread (direct policy 950–967; OOC MCTS timing 970–973).
- Unit timeout: 4 h per unit, about 4x the slowest expected unit (a heart1-prior A0 run, about 65 min). Issue #544's endless Silver loop
  does not throw, so a hung unit ends at rc 124. Workers let the timeout fire and never kill units themselves.
- Dropped seeds: a `[bestbench-seed-failure]` (rc 1, no row) or a timeout (rc 124) drops that seed from both arms
  and lists it. An ascension is INVALID if more than 1% of its seeds are dropped (here: more than 1 of 128), if any
  other unit fails, or if a log lacks its arm's markers (`[heart1] loaded` and `prior=heart1` for heart1,
  `prior=policy` and no heart1 load for v4, `leaf_policy=v4` for both) (`tools/analyze_heart1_ab_486.py`).

## Analysis (`python3 tools/analyze_heart1_ab_486.py report.json DIR...`)
- **Primary (A20):** mean paired floor difference heart1 − v4, paired seed bootstrap 95% CI (10,000 resamples, RNG
  seed 486 + ascension). **IMPROVED** if the lower CI > 0, **WORSE** if the upper CI < 0, **NOT_SHOWN** otherwise.
- **Key secondary (A20):** act-3 clear difference with its CI (same resample indices, same labels), discordant pairs
  and exact McNemar p.
- **Secondary (A0):** the same two statistics with their labels.
- Descriptive: reached act 3, clears given act 3 reached, deaths by act, boss deaths, end HP, seconds and MCTS CPU
  per run, MCTS-owned and fallback shares, support aborts, prior builds, and heart1's share of prior builds.
- No multiplicity correction; all statistics are reported. 128 seeds give a floor CI of roughly ±2–3 floors at A20
  (**Inference** from §458's ±3.3 at 128 seeds), so only a large effect will separate.

## Decision rule
- A20 floors IMPROVED → heart1 is the candidate tree prior for OOC MCTS (stage 2 of the accepted plan, e.g. ExIt
  with heart1 as prior). Defaults are Philipp's separate call; this run changes none.
- NOT_SHOWN on floors but clears IMPROVED → reported as such; Philipp decides.
- WORSE or NOT_SHOWN on both → the V4 prior stays; the ledger records the result.

## Cost (timing smoke, seeds 74071972 A0 and 74071973 A20, 4 units at a time on 4 cores)
- V4 prior: A0 388 s (died floor 33), A20 481 s (died floor 40). heart1 prior: about 5x slower per OOC decision
  (A20: 52 decisions in 16 min against 140 in 8 min; partly overlapping a build).
- **Inference:** about 40 min per A20 and 65 min per A0 run with the heart1 prior, 8 and 11 min with V4; about
  225 + 40 ≈ 265 core-h in all; on 32 workers about 2–2.5 h of runs per worker plus the build.
