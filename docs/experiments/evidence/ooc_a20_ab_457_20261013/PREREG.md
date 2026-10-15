# §457 OOC MCTS `combo` vs OOC off at ascension 20, 128 paired seeds (pre-registration, 2026-10-13)

Philipp, 2026-10-13 16:05Z: "How the ooc MCTS A20 doing? Can we try 128 seeds A/B?", then 16:06Z: "Just do it on your
own, use 8 workers", then 16:56Z: "Just upload the files for the ctm?? Then do it in the cloud?". Frozen with the run commit and binary hash before launch; independent pre-launch review by the
coordinator. 8 cloud workers × 16 seeds × 3 arms.

## What is known at A20 (baseline)
- OOC MCTS has never played whole A20 runs. Every live OOC MCTS A/B (§384, §412, §422–§424, §427–§433, §441, §446,
  §449, §451) ran at A0. At A20 there are only decision-level checks on the gold decisions: §425 (root picks not
  shown better than the heuristic) and §426 (Lizard CTM, regret −0.40 [−0.96, +0.16]).
- **The production CTM is broken at A20.** It gets `ascension` straight from the game and was trained at A0 only.
  On 9,349 A20 combats (§443 Stage 0) it predicts 0.5% deaths against 10.5% observed, with survival NLL 1.447.
  Clamping the input to 0 is not enough: it still predicts 3.1% deaths. **Inference:** default OOC MCTS at A20 would
  price imagined fights as almost riskless.
- The A20 retrain `pathb-a20` (§443 Stage 2) has survival NLL 0.080 on held-out A20 combats, against 0.128 for the
  clamped production model. Its boss death bias is +0.015 (clamped production −0.151). It is NOT_QUALIFIED offline
  (boss bias over the ±0.01 bar, plus 2.3% refusals from missing Lizard support), so it cannot become a default. A
  Lizard refit and a fresh re-gate are under way (§443 Stage 4).
- Reference win rate: the §419 A20 stack won 16/128 with an act-3 stop (§447 control). That is a different stack
  (learned Silver stop), so it is only a reference.

## Arms (paired by seed, same binary)
- `off`: §433 `off` unchanged (the §422 base: exact-10k Silver, V4 OOC gates at margin 1.0, keys off,
  `STS_STOP_AFTER_ACT=3`, `STS_OOC_MCTS=0`), at ascension 20.
- `combo`: §433 `combo` unchanged (rollout3, 4096 simulations, `WIDEN_K=4`, `WIDEN_ALPHA=0.75`, 3 leaf combats, native
  leaf, V4 prior and leaf policy), at ascension 20, with the A20 CTM below.
- `combo_def`: the same `combo` with today's automatic default CTM stack (§435 Lizard-capable pathb-r2 fast
  `c6d56bbc…`, standard Brew fallback `b9188de0…`; no CTM variables). It gets raw ascension 20, so it prices imagined
  fights with almost no death risk (§443 Stage 0), but it has full Lizard support.
- Both arms pin `STS_OOC_PUBLIC_FUTURES=8` (the default since #496), as §451 did. `STS_WIN_NET` stays unset, so the
  leaf win model is today's default under OOC MCTS (public X2-B, ADR-0029; §449 found no difference from `v_win`).

## Treatment CTM: the A20 candidate, not the production CTM
- **Choice:** the `pathb-a20` escape candidate as is: fast `34870815…`, standard `b489e537…`, manifest `7274c5c3…`,
  with `STS_OOC_MCTS_ACTIVE_LIZARD=0`. `ctm_artifacts.txt` pins the data-branch commit (`34d4dfac`, pushed from
  Philipp's machine), the three files with their sha256, and the active-Lizard setting.
- **No Lizard refit.** §443 Stage 4 Step 1 could not run: `one_combat ctmlizardfeatures` aborts with "active-Lizard
  correction enabled without its frozen artifact metadata", because the fast artifact has no `activeLizardCorrection`
  header (chain B skipped s23). Adding one is a new pre-registered step. The candidate therefore refuses every imagined
  combat with an active Lizard Tail.
- **Smoke finding (added before freezing):** the refusals are not limited to runs that own a Tail. On smoke seeds
  74047001 and 74047002 (no Lizard Tail in the real run) 20/30 and 87/129 OOC decisions fell back to V4, all
  `active_unqualified_lizard`; on the forced-Tail seed 74047003, 32/127. **Inference:** imagined futures that pick
  up a Lizard Tail (sampled relic rewards inside the search tree) reach a refused combat and abort the whole root
  search. So `combo` is largely V4 play; that is why `combo_def` was added (Philipp's decision card, or its
  recommended option while he had not answered).
- **How those fights fall back (as §435 describes for the pre-§435 stack):** a refused imagined combat aborts that
  decision's whole root search, and the deployed V4 OOC policy decides that decision instead. Real combats are
  unaffected (Silver plays them). The share of OOC decisions decided this way (`mctsFallback`, `mctsSupportAborts`)
  is reported per arm.
- **Why:** the production CTM gets raw ascension 20 and predicts 0.5% deaths against 10.5% observed (§443 Stage 0), so
  a `combo` arm with it would search over a model that sees almost no death risk. The A20 candidate is the only model
  calibrated near A20 outcomes; its offline failures (boss bias 0.015, Lizard refusals) are small next to
  production's 0.15–0.49.
- **Scope:** this is a research arm. It does not qualify the A20 CTM and is not the §443 Stage 3b live gate; no CTM
  default changes whatever the result.
- Loading: `STS_OOC_MCTS_COMBAT_MODEL` = fast, `STS_OOC_MCTS_BREW_FALLBACK_MODEL` = standard,
  `STS_CTM_RESEARCH_CANDIDATE_MANIFEST` and `_SHA256` = the manifest (`arm_env.sh`). The analysis is INVALID unless
  every `combo` log shows `[ctm-research-candidate] candidate_id=pathb-a20` and no `off` log does.

## Seeds and runs
- Seeds 87000000–87000127, one `bestbench 10000 1 20 SEED` unit per seed and arm (384 units). Smokes 74047000–099
  (this thread).
- Smoke (before launch): seeds 74047000–003 with `run_unit.sh` (74047000 `off` and default-CTM combo; 74047001
  `off`, `combo`, `combo_def`; 74047002 `combo`; 74047003 `combo` with `STS_FORCE_RELIC=LIZARD_TAIL`). It checks that
  every arm runs at ascension 20, `combo` shows the A20 candidate banner and `combo_def` does not, and all complete.
- Stalls: a native Silver stall in a live combat is a `[bestbench-seed-failure]` (unit rc 1, no result row). Such a
  seed is dropped from both arms and listed; any other gap or nonzero rc makes the analysis INVALID
  (`tools/analyze_ooc_a20_457.py`).

## Analysis
- Primary: two comparisons, `combo − off` and `combo_def − off`, each the mean paired floor difference with a 95%
  paired bootstrap CI (10,000 reps, RNG seed 457, same resample indices). Per comparison **IMPROVED** if the lower
  CI > 0, **WORSE** if the upper CI < 0, **NOT_SHOWN** otherwise. No multiplicity correction; both are reported.
  `combo − combo_def` is descriptive. Floors are primary
  because at A20 most runs lose, so wins carry little information on 128 seeds (§447 used floors for the same
  reason).
- Key secondary: wins (paired bootstrap CI of the difference, discordant pairs, exact McNemar p).
- Descriptive:
  - deaths by act and boss deaths;
  - CTM support refusals and V4 fallback share by reason;
  - CPU s per run;
  - how many decisions differ between arms.
- Decision: no default change either way. OOC MCTS stays off by default (ADR-0027).

## Open questions (recorded, not tested here)
- **Open question:** the V4 prior/leaf policy and the leaf win model are A0-trained. §448 found the A20 V4 retrain no
  better, and §438 found no loss from a public-only refit at A20, but neither is an A20 calibration of the leaf.
