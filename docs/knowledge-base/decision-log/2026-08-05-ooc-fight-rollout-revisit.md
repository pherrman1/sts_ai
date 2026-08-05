# 2026-08-05 — OOC fight-rollout lookahead re-gated on the §107 stack

## Task

Test the idea "for each legal action, copy the run state, simulate the next
combats, evaluate the resulting state, come back" as a **live** OOC policy on
the current recommended stack (§107, S3−belief−chain + V4 one-ply gate stack,
60.2% @3k), including a terminal state evaluator (win GBM) instead of pure
HP-safety scoring.

## Decisions

1. **Implemented `STS_ACT_FIGHT_PROBE_TERM_WIN`** (default 0 = inert): the
   existing all-OOC checkpoint oracle
   (`apps/one_combat.cpp::checkpointedActFightUtility`) prices each option's
   post-final-checkpoint state with the native win GBM
   (`g_winNet.predict(richFeatureVec(local))`, P(win) units, scale-compatible
   with the HP-safety sigmoid), blended by the flag's weight. Applies to the
   searched-checkpoint path only; predict/encounter-NN paths untouched.
2. **Implemented `STS_ACT_FIGHT_PROBE_MARGIN`** (default 0 = always fire): the
   oracle overrides a decision only when `best − second ≥ margin`, else control
   falls through to the ordinary policy stack. Rationale: greedy full-run
   oracle replacement is a recorded regression (§66j/§66m/§67) and the margin
   is the design-doc deployment contract for learned override layers.
3. **Greedy (ungated) full-run oracle is falsified on the current stack**:
   0/13 paired seeds won (baseline 8/13), with an attribution test on seed
   126706 proving the catastrophe comes from the oracle itself, not the
   terminal term (oracle+TERM_WIN and oracle−TERM_WIN both die at floor 22,
   fight 14; baseline wins).
4. **TERM_WIN was inert** in the ungated A/B (identical outcomes) — the
   P(win) term is a ~10–15% perturbation of an HP-safety-dominated utility.
5. **Margin-gated variant (m=0.15, 1k sims) is directionally negative** at
   n=62 paired seeds: candidate 19/62 (30.6%) vs baseline 33/62 (52.8%),
   paired floor+10·win delta −4.50 (SE 2.33); run **stopped at 62 seeds to
   save compute** — the estimate was stable at ≈ −4.5 since n≈28 with no
   trend toward zero, and a positive flip would require the remaining 194
   seeds to outrun baseline by ~5σ. Extrapolated 256-seed CI ≈ [−6.8, −2.2].
   Recorded as EXPERIMENTS.md §111.

## Rationale (labels)

- **Inference:** the negative direction is consistent across ungated (0/13)
  and margin-gated (17/53) arms and matches the §66j/§66m/§67 family: the
  oracle's HP-safety/win utility argmax replaces the margin-gated one-ply Q
  stack, whose per-screen heads were trained for exactly these decisions.
- **Inference:** marginal effect ∝ firing rate: m=0.15 fires on ~20–35% of
  decisions (measured on 1k-sim traces, seed 126700); the ungated arm fired on
  all and lost 100% of paired seeds, the gated arm fires less and is merely
  below baseline.
- **Unverified:** whether a much higher margin (m ≥ 0.5, firing < 10%) or a
  regret-style gate against `a_heur` would flip the sign; not measured this
  session.
- **Inference:** the win-GBM terminal term cannot rescue the design because it
  re-prices the same states the trunk already simulates; the failure is
  decision-selection, not state-pricing.

## Alternatives considered

- Act-1-only oracle (act guard): not run — §66e full-run smoke already showed
  act-1 rescue does not convert to full-run wins on the old stack.
- Teacher-label collection at scale (§66k/§67 plan): deferred; the oracle
  remains a teacher/offline-ranker tool, not a live policy.

## Evidence

- Code: `apps/one_combat.cpp` — `g_actFightProbeTermWin`,
  `g_actFightProbeMargin`, `checkpointedActFightUtility` terminal term,
  `actFightProbeAllOocPolicy` margin gate, env parses + banners.
- Gate artifacts (GCP server `sts-test`, `/home/philippherrmann/sts_sweep`):
  `build/gate_2026-08-05_termlookahead_base.csv` (3k, 60.2% — reproduces
  §107), `..._termlookahead_cand.csv` (13 seeds, 0 wins),
  `build/gate_2026-08-05_margin_base1k.csv` (1k, 56.6%),
  `..._margin_cand15.csv` (running), `build/diag_126706_ora.nohp.csv`.
- Config: `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
  STS_S3_PARTICLES=256`, V4 tok gates REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1,
  margin 1.0, seeds 126700–126955, 24 threads; oracle:
  ALL_OOC=1, MAX_CHECKPOINTS=3, CHECKPOINT_SIMS=400,200,100, FUTURES=2,
  TERM_WIN=1.0 (candidate), MARGIN=0.15 (gated arm).

## Status

- **Closed as falsified** (EXPERIMENTS.md §111): the searched-checkpoint
  oracle, with and without the margin gate, is net-negative as a live full-run
  policy on the §107 stack; the win-GBM terminal term is inert. The oracle
  machinery stays opt-in (all probe flags default off; unset behavior
  byte-identical); its validated role remains offline teacher/ranker
  (§66k/§66l/§67).
- Session note: a concurrent agent session was editing the same working tree
  (`g_terminalBonus` combat-leaf WIP, EXPERIMENTS.md §108–§110, untracked
  decision log `2026-08-05-terminal-leaf-run-value-bonus.md`); this session
  did not commit, did not touch those files, and re-synced the full tree to
  GCP from the merged working-tree state.
