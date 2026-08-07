# 2026-08-07 — §132/§133 audit and same-recipe direct utility-R ablation

Date: 2026-08-07
Session/task: user-requested review of experiments 132 and 133; fix issues
found; run one narrowly scoped follow-up (faithful target-only ablation).

## Decision

1. **§132's "target-only ablation" claim is withdrawn as stated.** The
   implemented comparison changed depth (8→6), eta (0.05→0.1), rounds
   (early-stop/1500→fixed 150), objective class (weighted squared error → nine
   unweighted quantile models), and capacity (804→1350 trees) together with
   the label, so it cannot isolate the target. The 45.9 vs 10.1 EV-MAE
   headline is partly a 50·P(win) scale mismatch, not a ranking-quality
   verdict. Historical rows in EXPERIMENTS.md §132 are preserved; the
   correction is an explicit addendum (§134).
2. **§133's online verdict is preserved and revalidated with the strict
   analyzer:** quantile-R rejected at the tested α = 0.3/0.5/0.7 (point
   estimates reproduced exactly on the exact 256-seed block 126700–126955 for
   all three values: α0.3 −12.9pp, α0.5 −10.2pp, α0.7 −18.4pp); wording scoped
   to "all tested α" rather than "every α". A1's null is scoped to correlated
   same-state rollouts whose copied `BattleContext`s share initial simulator
   RNG — not fully independent environment samples.
3. **A faithful same-recipe direct utility-R GBM was trained and gated at the
   pre-registered first operating point α0.1** (R is on the larger terminal
   scale). Result: **38.3% vs deployed 50.4% = −12.1pp (95% CI [−18.8,−5.1]),
   floor −3.0, HP −5.0, discordant 83/256 — SIGNIFICANTLY NEGATIVE.** Per the
   pre-registered rule the line stops: α0.3 not tested, no promotion, no
   disjoint-block confirmation, deployed `build/v_combat_honest.txt` @α0.3
   stays. Fourth consecutive offline≠online falsification
   (§124c/§127/§133/§134).
4. **Evidence tooling hardened** so future gates fail loudly instead of
   silently tolerating bad inputs: `paired_analysis.py` is deterministic
   (fixed-seed generator per report), rejects duplicate seeds and unequal seed
   sets by default (`--allow-partial` diagnostic-only escape), and gained a
    self-test; `one_combat vnettest` is an asserting parity check (header
    contract, empty/malformed row rejection, complete-finite-token validation
    of every feature and `pyPred` cell, tolerance argument with non-finite/
    negative rejection, nonzero exit on failure); `train_value_combat.py`
    gained `VCOMBAT_TARGET=endhp|utility_r`
    + `VCOMBAT_WIN_BONUS` with an identical-recipe guarantee and a metrics
    sidecar.
5. **B1 (turn-beam) is not implemented as written.** The plan text requires
   beam pruning while forbidding intermediate-state scoring ("Do NOT score
   intermediate card states"), which is not a complete algorithm. Needs a
   revised spec (e.g. prune between complete turns) before implementation.

## Rationale

- The §132 implementation evidence (`train_vcombat_quantile.py`,
  `train_export_vcombat_quantile.py` params vs `train_value_combat.py` params)
  shows the recipe changed with the target; the recorded §132 text says "only
  the label" differs, which the code contradicts (verified).
- The deployed §126 model (`build/v_combat_honest.txt`, 804 trees, sha256
  `e69d64cf…`) must remain the benchmark basis; the quantile-R line was
  already rejected on paired gameplay (§133), which is independent of offline
  EV-MAE framing.
- Alpha 0.1 was pre-registered (not post hoc cherry-picked) because
  utility-R's expectation sits on the 0..~150 terminal scale, not the
  ~0..80 endHp scale; even so the gate is significantly negative, so no
  further operating point is warranted.
- Deterministic paired analysis: recorded CIs from the old unseeded bootstrap
  were not exactly reproducible; the strict tool makes repeated analysis of
  the same inputs identical (self-test-proven).
- **Inference:** the same-recipe ablation's outcome (R-scale regression fits R
  offline — MAE 9.73 vs quantile-R 10.10 — yet ranks tree states worse than
  the deployed endHp leaf at α0.1) supports the §133 hypothesis that the
  deployed under-scaled endHp leaf is ranking-friendly as a blended prior,
  but the mechanism is not directly measured.

## Alternatives considered

- Re-run the §132 quantile comparison with the deployed recipe (9 quantiles at
  depth 8/eta 0.05/early-stop) — rejected: the direct single-ensemble
  `utility_r` model is the smallest faithful test of the target hypothesis and
  avoids quantile-mean-EV approximation entirely.
- Gate at α0.3 first (matching §133) — rejected: α0.1 pre-registered for the
  larger R scale; §133's α curve (higher α worse) made α0.3 a worse operating
  point to establish first.
- Implement B1 "as written" — rejected: beam pruning without intermediate
  scoring is not a complete algorithm; implementing it would require an
  arbitrary hidden design decision (see plan page status note).
- Keep `paired_analysis.py` permissive (intersection + warning) — rejected:
  malformed appended CSVs could be analyzed as valid pairs and seed-set
  mismatches silently shrank the sample; a promotion gate requires exact
  pairing.
- Keep `vnettest` printing-only — rejected: successful model loading is not
  proof of inference parity; the command now fails on missing, empty,
  malformed, or out-of-tolerance evidence.

## Evidence

- `train_vcombat_quantile.py`, `train_export_vcombat_quantile.py` (depth 6,
  eta 0.1, fixed 150 rounds, 9 quantiles, 1350 trees) vs
  `train_value_combat.py` (depth 8, eta 0.05, 1500 rounds + early stop,
  weighted squared error) — the §132 recipe confound.
- `train_value_combat.py` — `VCOMBAT_TARGET` / `VCOMBAT_WIN_BONUS` parsing,
  `metrics` sidecar (`<model>_metrics.json`).
- `build/v_combat_utility_direct_metrics.json` (287,517 rows / 16,337 fights,
  best_iter 570, val MAE vs R 9.73, val MAE vs endHp 43.58) and
  `build/v_combat_control_endhp_metrics.json` (best_iter 1479, val RMSE 7.88,
  matching the §126 recipe's offline ballpark of 7.99 on the same rows).
- `export_combat_model.py` → `build/v_combat_utility_direct.txt` (611 trees,
  sha256 `a81404b5…`) / `build/v_combat_control_endhp.txt` (1500 trees,
  sha256 `9c1b6061…`); `./build/one_combat vnettest … 0.001` PASS for both.
- Gate: `./build/one_combat bestbench 1000 256 0 126700` with
  `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
  STS_S3_PARTICLES=64 STS_VNET=build/v_combat_utility_direct.txt
  STS_VNET_ALPHA=0.1` + full V4 gate stack; banner printed `[V_combat leaf
  value ON: build/v_combat_utility_direct.txt, 611 trees, alpha 0.1]`.
- `paired_analysis.py --self-test` (deterministic intervals, reordered rows,
  duplicate/unequal-set rejection, partial path, schema drift) — CTest
  `paired_analysis_selftest`.
- Strict reanalysis `python3 paired_analysis.py build/vnet_all_a03_1k.csv
  build/vq_a03_256.csv ctl quantile-a03` reproduces §133 point estimates; the
  same strict pairing on the α0.5 artifacts (`build/vnet_all_a03_1k.csv` vs
  `build/vq_a05_256.csv`) reproduces 40.2% (−10.2pp) and on the α0.7
  artifacts (`build/vnet_all_a03_1k.csv` vs `build/vq_a07_256.csv`) reproduces
  32.0% (−18.4pp), all on the exact 256-seed block 126700–126955.
- Fresh same-recipe control chain re-run locally (2026-08-07 evening):
  `VCOMBAT_TARGET=endhp STS_XGB_DEVICE=cuda python3 train_value_combat.py
  build/vcombat_honest.csv build/v_combat_control_endhp.json` → deterministic
  (`best_iter` 1479, val RMSE 7.88, `build/v_combat_control_endhp.txt` sha256
  `9c1b6061…` identical to the first run); `export_combat_model.py` → 1500
  trees + `build/v_combat_control_endhp_val.csv` (200 rows); asserting
  `./build/one_combat vnettest build/v_combat_control_endhp.txt
  build/v_combat_control_endhp_val.csv 0.001` PASS (max|diff| 1.6e-4).
  Sidecar comparison (control vs utility direct): identical rows/fights/split/
  features/params/rounds/early-stopping/device.
- `vnettest` numeric validation (2026-08-07 evening): every feature and
  `pyPred` cell must be a complete finite token (`std::strtod` with full-token
  consumption + `std::isfinite`), tolerance must be finite and non-negative;
  verified that NaN tolerance, negative tolerance, trailing-junk tolerance,
  NaN `pyPred`, and trailing-junk features all exit nonzero.
- EXPERIMENTS.md §134 (audit + ablation + gate record).

## Addendum (fix iteration, same session)

- **`vnettest` non-finite checks (2026-08-07 late):** the asserting parity
  check now also rejects (a) a feature value that overflows the native float
  feature vector — a finite double beyond float range converts to Inf, and
  (b) a non-finite native prediction or prediction difference — a malformed
  model can predict Inf/NaN, and `std::max(maxAbs, NaN)` silently leaves
  maxAbs unchanged so the row previously compared as in-tolerance and printed
  PASS. Both now exit nonzero (`apps/one_combat.cpp::main` vnettest).
  Regression coverage added: `vnettest_selftest.py --self-test` (CTest
  `vnettest_selftest`) asserts a non-finite native prediction exits nonzero
  using an MLP whose all-finite tokens overflow float in the hidden layer
  (tree leaves "nan"/"inf" are already rejected by the loader), that a
  float-overflow feature exits nonzero, that out-of-tolerance evidence exits
  nonzero, and that clean finite parity evidence exits 0.

## Addendum (fix iteration, same session)

- **`bestbench` staleness guard (issue 46 producer side):** the strict
  analyzer rejected the §134 gate CSV because `bestbench` had appended the
  256-row block twice (implementation run + verification re-run) — the known
  append-without-dedup trap (issue 46). Fixed by guarding the `bestbench` mode
  handler in `apps/one_combat.cpp::main`: it now exits nonzero with a clear
  message when the results file already contains a row for any seed in the
  requested block, instead of silently doubling every row. Self-play gate
  batches use disjoint offsets on fresh per-iteration files, so they are
  unaffected; `reprobench` appends repeats intentionally via `bestBench`
  directly. The stale gate CSV was regenerated cleanly. Issue 46 closed
  (producer guard + strict analyzer consumer).

## Status and follow-up

- Implemented. Deployed model unchanged (`build/v_combat_honest.txt` @α0.3).
- The quantile-R and direct-R lines are closed; `v_combat_quantile.txt` and
  `v_combat_utility_direct.txt` are reference artifacts only (ignored build
  outputs, not promoted).
- Follow-up: B1 requires a revised complete-turn-beam spec before any
  implementation; the offline≠online gap for value leaves remains open
  (the transformer 51-bin CE model §128/§131 still has no deployable GBM
  port).
