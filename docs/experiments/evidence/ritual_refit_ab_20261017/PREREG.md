# Ritual-refit CTM vs deployed CTM in A0 OOC MCTS, paired by seed (pre-registration, 2026-10-17)

Philipp, 2026-10-17 12:01Z: "make sure the bug fix with the dagger is default. lets do 64 seeds a/b on 8 workers."
Frozen with the run commit, binary hash and arm files before launch; independent pre-launch review.

## Baseline
- §507: the deployed A0 CTM Ritual heads predict ~0.5% Dagger growth on corrected Writhing rows vs 7–10% observed.
  The refit (`pathb-r2-ritual-refit`, owner override of the non-Writhing margin) predicts 6.2% vs 8.3%, and it
  lifts the `writhing_ritual_intersection` refusal.
- In the deployed stack, a refused imagined combat aborts that decision's whole OOC MCTS search, and the V4 policy
  decides instead. The Silver fallback (`STS_OOC_MCTS_UNSUPPORTED_SILVER_SIMS`) is opt-in and off here, as it is in
  the live mod.
- The Ritual Dagger simulator fix (#585, `be38c4a6`) is unconditional in this binary, so both arms have it.

## Arms (paired by seed, same binary, `arm_env.sh`)
Both arms use the §488 `studentc` stack at ascension 0, with Arm C (student C, `eff2f74f…`) as the OOC MCTS tree
prior. They also use explicit A0 CTM paths with active Lizard. The arms differ only in that CTM pair:
- `control`: the deployed pathb-r2 pair.
- `ritual`: the refit pair, with its research-candidate manifest.

One `bestbench 10000 1 0 SEED` unit per seed and arm, through `tools/seed_guard.sh` (`run_unit.sh`, 8 h timeout).
Seeds 111000800–111000863 (the coordinator's block); smokes use 111000864–899. Eight single-thread local workers
(`launch.sh`).

## Expectation and power
The arms can differ only on runs where the OOC search imagines a fight while a Ritual Dagger is in the deck. Most A0
runs never obtain one. Expect most pairs to be identical, which gives low power. The descriptive outcome matters most.

## Endpoints
- Primary: act-3 clears (`won`, `STS_STOP_AFTER_ACT=3`), McNemar on discordant pairs.
- Secondary: paired mean floor difference, with a 95% paired bootstrap CI (10,000 reps, RNG 20261017).
- Descriptive:
  - Runs holding a Dagger, and identical vs divergent pairs.
  - OOC MCTS aborts by reason, from the `.mcts.csv` traces. `writhing_ritual_intersection` should appear only in
    `control`.
  - Wall time.

## Decision rule
- Make the refit the default A0 stack only if the primary is not worse, and every `ritual` unit runs rc=0 with no
  new abort reasons.
- Otherwise report and keep the deployed default.
- This is Philipp's call either way. No default change happens in this experiment.
