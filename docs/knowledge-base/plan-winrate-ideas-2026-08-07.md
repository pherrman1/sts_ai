# Winrate improvement plan — S3-centered wave (2026-08-07)

Status: **EXECUTED through Wave 2 (2026-08-07), stop-after-Wave-2 per user
instruction; the §126 follow-up (gate-stack-distribution vnet retrain, §129)
is COMPLETE — NULL for replacement, the deployed honest-data model stays.**
Results are in EXPERIMENTS.md §124–§129 and the decision logs
`2026-08-07-winrate-wave.md` / `2026-08-07-vnet-promotion.md`
(§124b/§124c/§127/§128 are the parallel session's prior-guided-rollouts,
policy-prior-v2, and utility-net entries):

- §124 baseline wave: recorded references reproduce on the live-valid binary
  (flat @1k, +2.3pp n.s. @3k/256p); S3−belief−chain re-confirmed
  (belief+chain ON costs −11.3/−12.1pp, significant).
- §125: cPUCT (two n.s. gates, closed), STS_S3_EXPAND (mixed null, closed,
  env stays opt-in), TERM_WIN+cpsi (significant −8.6pp, closed).
- §126: **fresh honest-data V_combat leaf at α0.3 PROMOTED to default ON in
  the fair-S3 path** — three significant gates +12.5/+12.1/+12.5pp at
  ~2-2.4× cpu; 55.1% @3k/64p and 50.4% @1k/64p, the highest honest numbers
  recorded.
- §129 (this session's follow-up): gate-stack-distribution vnet retrain
  (`STS_DATAGEN_GATES`) NULL — the gated model's α optimum shifts 0.3→0.5
  but no significant winrate difference at either operating point; the
  deployed model stays.
- Executed by the parallel session against the §126 references: §3.4 policy
  prior v2 + §3.5 multi-select prior encoding (§127: NULL) and §3.3-adjacent
  prior-guided S3 rollouts (§124c: −7.0pp, closed).
- Not executed (deferred): Wave 3 (5.7.3 self-play relabeling, counter-aware
  OOC pricing) and the §4.4 belief-v2 reopening (the §125 ablation
  re-derivation re-confirmed belief/chain off, so the reopening condition
  did not fire).

Focus per session decision 2026-08-07:
**Searcher3 is the thing to improve**; S2 fair determinization work is out of
scope by choice; §122/§123 live-valid + forced-move promotions are DONE and
not re-gated here. GCP sts-test is available for gates. Every policy-affecting
item gets its own paired gate per the repo protocol; falsified lines are
recorded, never silently dropped. When execution starts, copy this file to
`sts_lightspeed/docs/knowledge-base/plan-winrate-ideas-2026-08-07.md` and log
a decision-log entry.

## 1. Current state (verified 2026-08-07, HEAD 7b1a8d2)

- Deployed S3 fair path (when `STS_FAIR=1 STS_SEARCHER3=1`): **forced-move
  contraction default ON** (§123, 0/256 diffs, −8.5% cpu) and **live-valid
  edge re-selection default ON** (§122 +§123: +5.5pp/+5.9pp win at +7.9%/+14.6%
  cpu — recorded cpu-trade call). S3−belief−chain stays the recommended
  particle config (`STS_S3_BELIEF=0 STS_S3_CHAIN=0`; 256p @3k / 64p @1k).
- Headline honest reference on block 126700–126955 with the **pre-live-valid**
  binary: **44.5% @3k/256p** (`build/honest_fix2_3k_256.csv`), **37.5%
  @1k/64p** (`build/honest_p64_1k_256.csv`) — V4 gate stack on
  (`STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native`,
  REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1, `STS_OOC_STRATEGIC_MARGIN=1.0`).
- **§123 open follow-ups adopted here:** (1) full-stack re-measurement with
  the live-valid default; (2) fairgen datagen is NOT covered by the live-valid
  default (parse order) — re-run with `STS_LIVE_VALID=1` to align the
  policy-target distribution.
- Closed lines NOT reopened without a new angle: combat VNet unconditional
  leaf (§97/§102), PVNet policy/value (§102/§103), S3 belief/chain/CRN as
  originally measured (§106 — deltas invalidated by §113, see §3.2),
  obs-keyed descent (§114), root-stability stop (§118), rollout caps (§119),
  TERM_WIN with win-tree evaluator (§116), OOC encoder/objective/label-noise
  lines (§86–88, §100, §104, §105).

## 2. Baseline wave (prerequisite for every gate below)

Fresh paired reference on the current binary with the new defaults. ~2-4 arms,
~10-13 min/arm on GCP.

| arm | config | purpose |
|---|---|---|
| B1 | full stack @3k/256p, block 126700, pair vs `honest_fix2_3k_256.csv` | new win-point reference (live-valid ON) |
| B2 | full stack @1k/64p, block 126700, pair vs `honest_p64_1k_256.csv` | new efficient-point reference |
| B3 | B2 + `STS_S3_PARTICLES=256` | confirm 64p = 256p still holds @1k on the new binary |
| B4 | B1 with `STS_S3_PARTICLES=64` | cpu probe at the 3k win point (64p might make @3k affordable per-arm, ~2-3x cheaper) |

Command shape:

```bash
STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=256 \
STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native \
STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1 \
STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0 \
./build/one_combat bestbench 3000 256 0 126700 build/<arm>.csv
```

Decision rule: B1/B2 must be within noise of the recorded references
(±3-4pp) OR set a new recorded reference; a large positive shift is itself a
result worth an EXPERIMENTS.md entry (§124). If B4 ≈ B1, use 64p @3k for all
later gates (cheaper). Record §124 and update `current-baselines.md` only if
the headline changes.

## 3. Wave 1 — S3 diagnostics and cheap knobs (local + GCP, ~1-2 h)

### 3.1 S3 searchdiag at the deployed operating point (diagnostic, no gate)

`searchdiag` now instruments S3 (rowtype A only; §122). Run the deployed
config (S3−belief−chain, live-valid ON, V4 gates, @3k, 6-8 seeds) and report:
residual illegal-stored share (was 0.10 after the fix vs 0.58 before), rollout
fraction by room/act (bosses were 0.83-0.89), visit-weighted terminal
coverage, and rollout length. **Purpose:** decides whether §4.1
(expand-on-demand) and §4.3 (boss-conditioned leaf) have measurable headroom,
and re-derives §117's numbers under the new default.

```bash
STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=256 \
STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native \
./build/one_combat searchdiag 6 3000 0 build/sdiag_s3_deployed.csv 0 0
```

### 3.2 S3 feature ablation re-derivation (belief/chain/CRN) — 4 arms, one gate

§106's deltas (removing belief +8.6pp, chain +4.7pp, CRN −14.1pp) are
**invalidated by §113** and were flagged for re-derivation "only if that
research line reopens" (§115). The line reopens: live-valid is now default,
which changes how particle divergence manifests (it was the direct cause of
the illegal-stored share). Cheap and high-information:

- arms on the B2 config: full-S3-features, −belief, −chain, −belief−chain
  (CRN included only if any arm flips positive), 256 seeds each @1k/64p.
- Pre-registered decision: if −belief/−chain are still ≥ the full-feature
  arms (paired), the deployed S3−belief−chain config stands and is re-confirmed;
  if full-S3 features tie or beat, consider flipping `STS_S3_BELIEF/CHAIN`
  defaults (needs a second gate per promotion rule). CRN re-check only if the
  implementation is touched (it was dead code until §106 wired it; §106
  measured −14.1pp — a rerun is cheap insurance against a stale verdict).

### 3.3 cPUCT sweep on the honest S3 stack

`g_cPuct` default 2.5 (`CombatValueNet.cpp`, `STS_CPUCT`). Historical §26 data
showed UCB > PUCT at 20k sims; no cPUCT sweep exists on the post-§113 honest
S3 binary. Sweep {1.0, 1.5, 2.5, 4.0, 6.0} at B2 config, 128 seeds local as a
probe; gate the best point vs B2 at 256 seeds.

### 3.4 Policy prior v2 + fairgen datagen alignment (§123 open question) — IN EXECUTION (2026-08-07)

The tracked GBM prior `build/policy_trees_c.txt` (sha256 24793bd3…) feeds
`computeEdgePriors` in the deployed S3 (PUCT). §103 showed the GBM prior ties
the PVNet policy head at 8× lower cost — the prior is the cheap place to get
better priors. Steps:

1. `fairgen` datagen with the fix: `STS_LIVE_VALID=1` (and forced-move ON)
   with `STS_FAIR=1 STS_SEARCHER3=1` — §123 notes datagen is not covered by
   the default, so the flag must be explicit. Fresh seeds (e.g. 400000+),
   N=500-1000 seeds. **RUNNING on GCP (2026-08-07, ~50 min):** 1000 seeds @
   1000 sims, seedOffset 400000, S3−belief−chain/64p, **with explicit
   `STS_VNET=build/v_combat_honest.txt STS_VNET_ALPHA=0.3`** — recorded
   deviation: the plan predates the §126 vnet promotion; the explicit env
   aligns the policy-target distribution with the deployed controller (§126's
   own datagen-alignment stance; without it, explicit STS_VNET defaults to
   α=0.5). Merged with §3.5 (see below) — the rows carry 22 action features.
2. `train_policy.py` on the new rows → export → new `policy_trees_c` v2.
   **DONE (2026-08-07, §127):** `build/policy_trees_c_v2.txt` (100 trees, 751
   feats), offline CE/KL −0.09 vs tracked on the new rows (policystats
   action-feature bug fixed to make that comparison honest).
3. Paired gate: v2 prior vs tracked prior at B2 config, 256 seeds. Also
   re-verify load-message evidence (`STS_POLICY`). **DONE (2026-08-07,
   §127): ❌ NULL — 48.4% vs 50.4% (−2.0pp, CI [−8.2,+4.3]), floor −1.5, HP
   −4.2, cpu equal; line closed per the pre-registered rule.** The better
   offline CE/KL does not transfer online (same pattern as §124c). §3.4
   closes as executed; the tracked prior stays deployed.

### 3.5 Multi-select prior encoding — IMPLEMENTED (merged into 3.4's datagen)

Priors were **uniform across GAMBLE/EXHAUST_MANY subsets** because
`combatFillActionFeatures` encoded multi-select actions identically
(`src/sim/search/CombatValueNet.cpp`; §113/§114 limitations). `STS_MULTISELECT_MODE=single|none`
was measured negative (31.6%/30.5% vs 36.3% — pruning the action space is not
the fix). **Implemented 2026-08-07:** 8 subset-content features appended to
the action block (`aSelectSize`, `aSelTotalCost`, `aSelAtk/Skl/Pow`,
`aSelUpgraded`, `aSelPlayOrder`, `aSelObtainWeight`; `kNumAction` 14→22,
derived from `kActionNames`); multi-select indices resolve against the hand,
single selects against hand/discard/exhaust pools per `CardSelectTask`,
discovery/codex contribute size only. Appended AFTER the original 14 so the
PVNet action encoder (first 14) and old GBM models (model-nfeat) are
unaffected; PVNet stride hardcodes in S2/S3 `computeEdgePriors` (were `n*14`,
would have mis-filled with the new width) and the `policystats` act buffer
fixed; `eval_combat_pvnet.py`/`combat_pvnet_parity.py` slice to 14. Retrain +
gate ride §3.4's pipeline (the running datagen already emits the 22 features
— verified locally: distinct subset combos now appear in GAMBLE/EXHAUST_MANY
rows).

## 4. Wave 2 — S3 structural (the main bets)

### 4.1 On-no-valid-edge expansion (STS_S3_EXPAND)

After live-valid, S3 still falls back to a **random rollout when no stored
edge is valid in the current determinization** (residual ~0.10 illegal-share,
§122). Instead of a rollout, expand the legal edges of the live state and
descend into them (the tree action-keyed structure is untouched — obs-keyed
descent stays closed, §114). This targets the last structural
tree/determinization mismatch, with the same expected mechanism as §122/§123
(less rollout waste, deeper honest trees).

- Env `STS_S3_EXPAND=1` (default off), implemented in
  `BattleScumSearcher3::step` next to `selectBestValidEdgePUCT`.
- Smoke: searchdiag illegal-share → ~0, invariants intact.
- Gate: B1 config (or B4 if 64p holds), 256 seeds, paired vs the §124
  reference. Decision rule per §123 promotion precedent: win ≥ flat with CI
  excluding a meaningful loss; cpu-trade call recorded explicitly (the §123
  precedent accepts ~+8-15% cpu for ~+5-6pp win).

### 4.2 TERM_WIN retry with the C_psi evaluator (§110/§116 follow-up)

§116 falsified the terminal-leaf bonus with the **win-tree** evaluator
(counter-insensitive: 0 splits on all counter features, §110). The C_psi
variant (`STS_TERM_WIN_EVAL=cpsi`) prices counter relics with the correct
sign (§110 `cpsictr` probe) and was never gated at the operating point
("benchmark at the 1k-sim operating point" — open). Issue 49 (the
multithread crash) is fixed. Ready-to-run gate: `STS_TERM_WIN=1
STS_TERM_WIN_EVAL=cpsi` at B2 config, 256 seeds, paired. Cost warning: cpsi
leaf eval ≈ 9× win-tree leaf eval (19.2 vs 1.8 cpu-sec/run at 100 sims, §110)
— expect the same 3.1×-class overhead; the gate decides whether cross-combat
setup (counter alignment, potion/HP carry) finally pays with a
counter-sensitive evaluator.

### 4.3 Boss/long-fight NN leaf conditioned on rollout usage

§117: in both regimes, **boss fights stay rollout-dominant at deep budgets**
(fair 86% rollout at 30k; vtc ≤ 0.24) while known-RNG hallway fights become
near-explicit. The unconditional combat VNet was rejected (§97/§102: α-blend
on the old stack, old vnet, 3.2-14× cpu). New angle, two parts:

1. **New labels:** train a fresh combat value net on post-§113 honest
   trajectories (ride the §3.4 fairgen datagen; `train_value_combat.py`).
2. **Conditional application:** blend the NN leaf only where
   `SearchDiagnostics` says rollouts dominate (boss encounters, act-3 rooms,
   or measured rollout length/coverage above a threshold — §117 explicitly
   called this schema feasible), never unconditionally. `STS_VNET` +
   `STS_VNET_ALPHA` + a new conditioning env (e.g. `STS_VNET_COND=rollfrac|room|off`).

Gate at B2 config first (cpu-limited), then B1 if the @1k gate is positive.
Pre-register: a null/negative at both budgets closes the leaf line for good.

### 4.4 S3 belief v2 (reopen only if §3.2 flips the verdict)

Belief reweighting measured net-negative twice (§106, §107 E1 −6.2pp at 256
particles) with the conservative implementation (uniform fallback on any
contradicting reshuffle/insert, `Belief::update`). If §3.2 re-confirms
belief-off, this stays closed. If any arm shifts, the new angle is importance
resampling + particle rejuvenation on contradiction instead of the uniform
fallback — separate env, separate gate. Do not start before §3.2's verdict.

## 5. Wave 3 — the long-pole lines (start early on GCP)

### 5.1 Self-play relabeling (5.7.3, the last unchecked action-plan item)

All strategic models (V4/V5, Q_win labels) were trained on trajectories from
**old, weaker policies** (pre-§113, pre-live-valid; the §94 datagen even
predates the honest enumerator). Hypothesis A.15 #1: the combat controller
determines the training distribution — the current controller is ~5-6pp
stronger than the one that produced the labels. Steps:

1. `strategicgen2` datagen on fresh seeds (300000+) with the **deployed
   full stack** (V4 gates ON, S3−belief−chain, live-valid default) as the
   roll-out policy, K=3/futures=1 (the optimal label contract, §83/§84).
   Target 1,000-1,500 seeds. ~26 min per 500 seeds on GCP.
2. Retrain `train_strategic.py` (V5 recipe, corrected-label pipeline §95/§96)
   → export → new artifact.
3. Paired gate of the one-ply gate stack at B2 config, 256 seeds, vs the
   tracked V4/V5 artifacts. Pre-register: this is the cleanest test of the
   distribution hypothesis; a null falsifies 5.7.3 for good (record it).

### 5.2 Counter-aware OOC pricing — **CLOSED on evidence (2026-08-07, EXPERIMENTS.md §130)**

The deployed win tree has zero counter-relic sensitivity (§110) while C_psi
prices counters correctly. Options were: (a) retrain the win GBM on the
larger current corpus; (b) C_psi next-fight survival as an additive
rest/event term. **Closed without a retrain gate**: the diagnostic showed
the fresh vnet's training data had real counter variance (Happy Flower 0-2/
6,075 nonzero rows, Nunchaku 0-9/7,879, Pen Nib, Sundial, Panache) yet the
trained model assigns counters ~0.01% of split gain — two independent GBMs
read "no signal", consistent with §116 (forced-Happy-Flower controlled
benchmark: null) and §125 (counter-sensitive C_psi leaf: −8.6pp). OOC
decisions barely depend on counter state; the in-combat energy-tick signal
the counters carry is already visible to the deployed combat vnet. No
retrain gate, no code change.

## 6. Recording and hygiene

- EXPERIMENTS.md: §124 baseline re-measurement; then one entry per gated arm
  (date, executable mode, env flags incl. every STS_* value, model paths +
  hashes, seeds, threads, regime, searcher, metric formula, artifacts).
- Decision log: `2026-08-07-winrate-wave.md` on session close; separate
  entries for any promotion decision (live-valid precedent: two gates + a
  recorded cpu-trade call before any default flip).
- KB updates: `combat-search.md` (S3 sections), `current-baselines.md`
  (only on a headline change), `training-and-inference.md` (if the prior or
  vnet pipeline changes).
- Traps: fairgen is NOT covered by the live-valid default (parse order,
  §123) — always pass `STS_LIVE_VALID=1` explicitly in datagen; never compare
  fair and known-RNG rows; verify model load messages; `bestbench` appends
  without dedup (truncate first); killed trainers corrupt `_state.bin` (verify
  frozen-model metrics before reuse); `Node`/`Edge`/searcher layout changes
  need a clean rebuild of every including translation unit.
