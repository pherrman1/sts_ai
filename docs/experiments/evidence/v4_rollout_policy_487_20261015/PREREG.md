# §487 OOC MCTS with the V4 policy inside the rollouts, paired by seed (pre-registration, 2026-10-15)

Philipp, 2026-10-15 16:19Z: "Can you try the same 64 seeds we test on heart1 with the v4 prior but also use the v4
prior in the rollouts? 32 workers pls. Maybe make the workers just haikus to save tokens". So: A20, the §486 seeds,
V4 tree prior in both arms, and the treatment also lets V4 make the rollout decisions. Frozen with the run commit
and binary hash before launch; independent pre-launch review.

## What is known (baseline)
- Our best OOC configuration is OOC MCTS `combo` (§433 at A0; §458 at A20 with the A20 CTM, ADR-0033), V4 as the
  tree prior. §486 ran it (its `v4` arm) on these 64 A20 seeds: 10/64 act-3 clears, mean floor 42.36, 494 s per
  run.
- Rollouts (3 leaf combats, `STS_OOC_MCTS_LEAF_POLICY=v4`) play non-combat steps with the ordinary policy chain
  (`runFullRunOocPolicyStep`): fixed rule steps, the room-value heuristic `chooseMapAction` on the map
  (`STS_OOC_STRATEGIC_MAP` is off), the heuristic card-reward, shop (greedy, ADR-0032), rest and event policies, with
  the one-ply V4 **Q-head** gates (margin 1.0) overriding the heuristic on card rewards, rest/upgrade, events, shops,
  treasure and boss relics only when V4's Q beats the heuristic action by the margin. The V4 **policy head** (the
  tree prior) has never chosen rollout actions. §441: uniform rollout choices plus a uniform prior were WORSE than
  `combo` (−7.8 pp), so the rollout policy matters. V4 map gating outside MCTS lost in §91/§93/§100.

## Hypothesis
- H1 (primary): OOC MCTS with V4 policy-head rollouts clears act 3 at A20 more often than with the chain rollouts.
- H2 (key secondary): it reaches further (mean paired floor difference > 0).

## Arms (paired by seed, same binary, `arm_env.sh`)
- Both: the §486 `v4` arm literally: §433 `combo` (the §422 base: exact-10k Silver via the bestbench budget, V4 OOC
  gates at margin 1.0, `STS_COLLECT_KEYS=0`, `STS_REST_WIN=0`, `STS_STOP_AFTER_ACT=3`; live OOC MCTS with 4096
  simulations, `WIDEN_K=4`, `WIDEN_ALPHA=0.75`, 3 leaf combats, native leaf, `TEMPERATURE=1`, `CPUCT=1.5`,
  `MAX_DEPTH=32`, visits root selection, early stop), `STS_OOC_PUBLIC_FUTURES=8`, `STS_OOC_MCTS_PRIOR=policy`. No CTM
  variables (automatic `pathb-a20` stack with active Lizard). All other settings are the run commit's defaults
  (ADR-0030..0040).
- `v4` (control): `STS_OOC_MCTS_LEAF_POLICY=v4`, the chain rollouts (as in §486).
- `v4roll` (treatment): `STS_OOC_MCTS_LEAF_POLICY=prior` (new, default off). At every non-combat rollout step the
  tree's fixed rule steps run first (open chests, take reward relics and gold, take potions with belt space, leave
  an empty reward screen; ADR-0031); then, if V4 encodes the screen (`v4DecisionSupported`: rewards with a card
  reward pending, rest, shop, treasure, boss relics, events except Match and Keep, upgrade selection, and the map
  except the boss row) and its candidate actions (`v4CandidateActions`) are unique, the action with the highest V4
  policy logit (the logit the tree prior uses, before its softmax) is taken; ties take the first candidate.
  Everything else (other card selections such as removes and transforms, Match and Keep, the boss-row map step, and
  combat) stays with the chain and the CTM as today. Greedy argmax, not sampling: today's rollouts are greedy and
  §441's random rollouts lost (**Inference** that sampling would add noise, not tested here).
- The real game (decisions the search does not own) is identical in both arms; only the imagined rollouts differ.

## Seeds and runs
- A20 seeds 107000000–107000063 (`COHORTS`, the §486 seeds per Philipp). One `bestbench 10000 1 20 SEED` unit per
  seed and arm through `tools/seed_guard.sh` (`run_unit.sh`), 128 units. Both arms run fresh on the run binary; the
  §486 `v4` arm (same build inputs, `d094e012`) is a descriptive reference: the control rows are expected to
  reproduce it exactly (`--ref486`), which checks that the default-off change leaves the chain rollouts unchanged.
- 32 cloud workers (`NWORKERS`, Philipp 16:19Z), each running 2 seeds in both arms, all 4 units at once.
- Smokes in this thread: control reproduction on §486 seeds 107000049 and 107000025 (exact match), treatment on
  74072160–74072161; 74072162–74072169 reserved (README).
- Unit timeout: 8 h per unit (as §486; units take about 10 min). Issue #544's endless Silver loop does not throw, so
  a hung unit ends at rc 124. Workers let the timeout fire and never kill units themselves.
- Dropped seeds: a `[bestbench-seed-failure]` (rc 1, no row) or a timeout (rc 124) drops that seed from both arms
  and lists it. The result is INVALID if more than one of the 64 seeds is dropped, if any other unit fails, or if a
  log lacks its arm's markers (`prior=policy` and no heart1 load in both, `leaf_policy=v4` for v4,
  `leaf_policy=prior` for v4roll), a v4roll unit reports no V4 rollout steps or a v4 unit reports some
  (`tools/analyze_rollout_prior_487.py`).

## Analysis (`python3 tools/analyze_rollout_prior_487.py report.json DIR... --ref486 DIR...`)
- **Primary (A20):** act-3 clear difference v4roll − v4, paired seed bootstrap 95% CI (10,000 resamples, RNG seed
  487 + 20). **IMPROVED** if the lower CI > 0, **WORSE** if the upper CI < 0, **NOT_SHOWN** otherwise; exact McNemar
  p and discordant pairs reported. Clears are primary (not floors as in §486) because §486 found floors a poor fit
  for an act-3-stop run: a clear and an act-3 boss death end on nearly the same floor.
- **Key secondary (A20):** mean paired floor difference with its CI (same resample indices, same labels).
- Descriptive: reached act 3, clears given act 3 reached, deaths by act, boss deaths, end HP, seconds and MCTS CPU
  per run, MCTS-owned and fallback shares, support aborts, prior builds, V4 rollout steps per run, and the control
  vs §486 `v4` reproduction count.
- No multiplicity correction. With 64 pairs only a large clear effect separates (§486: +23.4 pp had CI
  [+9.4, +37.5]).

## Decision rule
- Clears IMPROVED → V4-policy rollouts are a candidate default for OOC MCTS; defaults are Philipp's separate call
  (replication on fresh seeds first is the natural next step). This run changes none.
- NOT_SHOWN → reported as such, chain rollouts stay.
- WORSE → chain rollouts stay; the ledger records the result.

## Cost
- Smoke: treatment MCTS CPU per OOC decision 3.1–5.3 s vs 2.7–4.0 s for control, so about the same cost as the
  §486 `v4` arm (494 s per run). **Inference:** 128 units about 18–25 core-h; on 32 workers about 15–30 min of runs
  per worker (the slowest of 4 parallel units, a full clear) plus a 4-min build.
