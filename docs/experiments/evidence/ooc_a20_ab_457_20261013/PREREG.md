# §457 OOC MCTS `combo` vs OOC off at ascension 20, 128 paired seeds (pre-registration, 2026-10-13)

Philipp, 2026-10-13 16:05Z: "How the ooc MCTS A20 doing? Can we try 128 seeds A/B?", then 16:06Z: "Just do it on your
own, use 8 workers". Frozen with the run commit and binary hash before launch; independent pre-launch review by the
coordinator. 8 cloud workers × 16 seeds × 2 arms.

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
  leaf, V4 prior and leaf policy), at ascension 20, with today's automatic default CTM stack (below).
- Both arms pin `STS_OOC_PUBLIC_FUTURES=8` (the default since #496), as §451 did. `STS_WIN_NET` stays unset, so the
  leaf win model is today's default under OOC MCTS (public X2-B, ADR-0029; §449 found no difference from `v_win`).

## Treatment CTM: today's default stack (changed from the draft)
- The draft picked the A20 candidate `pathb-a20`. Its files exist only on Philipp's machine, and Philipp asked for the
  run to go ahead without him, so `combo` uses the automatic default CTM stack: the production §435 Lizard-capable
  pathb-r2 fast artifact (`c6d56bbc…`) and standard Brew fallback (`b9188de0…`), no CTM variables set. That is what
  OOC MCTS does at A20 today.
- Consequence (**Inference**, from Stage 0): imagined fights are priced with almost no death risk (the model gets raw
  ascension 20; predicted death 0.5% vs 10.5% observed). This run answers "does the current OOC MCTS help at A20",
  not "does OOC MCTS with an A20 CTM help".
- A third arm, `combo` with the A20 candidate, can be added later on the same seeds as a paired extension; it needs its
  own pre-registration addendum, and its result never promotes the A20 CTM (it is NOT_QUALIFIED offline, §443).

## Seeds and runs
- Seeds 87000000–87000127, one `bestbench 10000 1 20 SEED` unit per seed and arm (256 units). Smokes 74047000–099
  (this thread).
- Smoke (before launch): seed 74047000 in both arms with the frozen worker scripts. It checks that both arms run at
  ascension 20, `combo` shows its OOC MCTS banner and the default CTM stack, and both complete; it reports s per run.
- Stalls: a native Silver stall in a live combat is a `[bestbench-seed-failure]` (unit rc 1, no result row). Such a
  seed is dropped from both arms and listed; any other gap or nonzero rc makes the analysis INVALID
  (`tools/analyze_ooc_a20_457.py`).

## Analysis
- Primary: mean paired floor difference `combo − off`, with a 95% paired bootstrap CI (10,000 reps, RNG seed 457).
  **IMPROVED** if the lower CI > 0, **WORSE** if the upper CI < 0, **NOT_SHOWN** otherwise. Floors are primary
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
