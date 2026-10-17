# V1 blended Silver leaf: offline gate (pre-registration)

Written 2026-10-17 22:19Z (share file mtime 22:19:03Z) before any blend score was computed. Philipp's go:
"okay versuche mal v1 zu machen" (community-scan thread, 22:14Z). Offline only:
no gameplay seeds are driven; the corpus is the frozen §397 corpus.

## Question

§397 Gate A showed a learned leaf V **replacing** one SimpleAgent rollout (R1) is
not better (regret +0.37 [−0.01, +0.74]). AlphaGo-style blending was never
tested in native Silver: does `B = (1−α)·R1 + α·V` on the same probe child beat
R1, and how does it compare with spending a second rollout (R2)?

## Data, features, models

- Corpus `corpus-450376c8` (§397), features re-extracted with
  `one_combat silversynthfeatures` on main `623a8b60` (the archived feature rows
  were not kept). Folds, groups, labels, terminal handling, regret and
  concordance exactly as `tools/silver_synth_gates.py gatea` / GATES-PREREG.md.
- Models retrained with the unchanged §397 recipe (`silver_synth_gates.py train`):
  `vcont-natpert` (primary), `vroll-natpert` (secondary).
- α chosen on natural **validation fold 3** groups from
  {0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9} by mean regret (ties: smaller α),
  separately per model. Test = natural fold 4, reported once.

## Gate

- **PASS (primary, vcont-natpert blend)**: on natural test, mean(regret_B − regret_R1)
  has seed-clustered 95% CI upper bound < 0 AND concordance(B) > concordance(R1).
- Reported, not gating: R2 = mean of first two rollouts (cost reference: one extra
  rollout), regret_B − regret_R2 with CI, R4, the vroll blend, perturbed fold 4,
  and a sanity check that the retrained V reproduces §397's V-alone numbers
  within ~0.3 regret.
- Interpretation rule: a PASS whose B is not at least as good as R2 (CI of
  B − R2 upper bound ≤ +0.1) means a blend buys no more than a second rollout;
  the next step would then only be justified if V is cheaper than a rollout.
- PASS allows proposing a native implementation (default-off env switch) and a
  CPU-matched fight-level A/B on the act4replay / ctmsilvergen harness; that
  needs Philipp's go and a frozen seed block. FAIL closes V1 (ledger negative).
