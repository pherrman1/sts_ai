# 2026-08-04 — Combat PVNet parity fixes: 3 C++ inference bugs + offline eval harness

Date: 2026-08-04
Session/task: Phase 0 of the combat-model experiment plan (assess LLM-proposed
A–H architecture sweep). Build a trustworthy measurement pipeline before any
architecture work: fix C++/PyTorch parity, add validation split and offline
metrics, verify timing.

## Decision

1. **Fixed three C++ CombatPVNet inference bugs that made every recorded
   C++-measured PVNet result run a corrupted model:**
   - the transformer FFN applied ReLU where the trainer uses GELU
     (`src/sim/search/CombatPVNet.cpp::ffn`);
   - `buildTokens` skipped empty zones/absent relics/potions/dead monsters,
     while the trainer always emits 14 tokens (zero-padded), so token counts
     differed between training and inference;
   - `policyScore`'s final layer computed only `h[0]*W2[0]` instead of the
     full dot product over the hidden dimension — policy logits used a single
     hidden unit.
2. **Added load guards** in `CombatPVNet::load`: `entityDim` must be in
   (0, 256] (stack buffers are sized for 256) and `numHeads` must divide
   `entityDim` (silent truncation before).
3. **Built the missing parity harness**: `pvnetparity` mode in
   `apps/one_combat.cpp` + `combat_pvnet_parity.py` which rebuilds the PyTorch
   model from the exported `.txt` and writes a parity CSV (state + action +
   Python predictions). Encoder/policy/value now match to ~1e-6, including a
   D=64 variant (Identity projection path).
4. **Trainer gains a seed-grouped validation split**
   (`train_combat_pvnet.py`: `PVNET_VAL_FRAC`, deterministic rule
   `seed % 100 < 20`), optional `PVNET_TRAIN_ONLY=1` to keep val seeds out of
   training, and best-checkpoint selection by validation loss (was: min
   training loss).
5. **New offline eval harness** `eval_combat_pvnet.py`: policy CE/KL/top-1/
   top-3/expected-teacher-regret per decision group; value Brier/log-loss/
   ECE/death-BCE/quantile coverage. This is the screening metric for the A–H
   sweep.

## Rationale

- The July PVNet sweep (§72 in EXPERIMENTS.md) measured a model whose C++
   FFN, token layout, and policy head all disagreed with the trainer; any
   architecture experiment run on that pipeline would have been
   uninterpretable. Parity first was the precondition for Phase 3 screening.
   **Verified** by the new parity test: before the policy-head fix, logit
   diffs were ~1.3–2.1; after, all outputs match to 1e-6.
- Training-time assumption in the LLM's plan ("~2 hours per run") is wrong at
   this scale: 1 epoch over 55k value + 246k policy rows takes ~1 minute on
   the RTX 3060 Ti (smoke run, 2 epochs in 119 s). Screening all of A–H at 25%
   data is a matter of minutes. **Verified**.
- The fixed C++ on the tracked model at 100 sims, S3 + PVNet α=0: 3/32 =
   9.4% on seeds 126700–126731, consistent with §72's 8.6% on 128 seeds — the
   parity fixes do not visibly move the tracked model's 100-sim win rate,
   which is dominated by heuristic OOC choices at that budget. The payoff
   gate at 3k sims (Phase 1) remains the decision point.

## Alternatives considered

- Fixing Python to match C++'s sparse token layout — rejected: variable
   per-state token counts are painful in batched PyTorch; C++ matching the
   trainer's fixed 14-token layout is the training-faithful choice.
- Re-training before fixing parity — rejected: would have produced artifacts
   measured on the same broken inference.

## Evidence

- `src/sim/search/CombatPVNet.cpp`: `gelu()`, `ffn`, `buildTokens` (always 14
   tokens), `policyScore` (full dot product), `load` guards.
- `apps/one_combat.cpp::main` mode `pvnetparity`.
- `combat_pvnet_parity.py`, `eval_combat_pvnet.py` (new, root).
- `train_combat_pvnet.py`: `validation_pass`, `PVNET_VAL_FRAC`,
   `PVNET_TRAIN_ONLY`.
- `build/pvnet_parity{,_smoke,_d64}.csv`, `build/v_combat_pvnet_{smoke,d64}.txt`,
   `build/pvnet_fixcheck_s3p0_32.csv`.
- Parity results: PASS, global/pol/value max diffs <= 2e-6 (d128 and d64).
- Tracked-model val-only offline baseline (40k rows): policy CE 1.44,
   top-1 0.41, regret 0.65; win Brier 0.107, ECE 0.002.

## Status and follow-up

- Phase 0 implemented and verified. Open:
  1. Phase 1 payoff gate on the GCP server `sts-test` (S3+PVNet α∈{0,1} + S3
     control at 3k sims vs the S2@3k reference, 128 seeds 126700–126827) —
     run script prepared (`run_pvnet_gate.sh`), server needs the fixed
     binary.
  2. Phase 2 fairgen data regeneration with correct provenance.
  3. Phase 3 A–H screening on 25% data using `eval_combat_pvnet.py`.
- Knowledge-base follow-up: `architecture/training-and-inference.md` and
   `architecture/combat-search.md` should record the parity contract and the
   always-14-token layout; `evaluation/current-baselines.md` notes PVNet
   results pre-date the parity fixes.

## Update (same session, EXPERIMENTS.md §101)

- Full 128-seed §72 replication on the fixed binary (S3 + PVNet α=0,
  100 sims, seeds 126700–126827, default OOC stack): **16/128 = 12.5%**,
  floor 28.8, HP 6.4 (`build/pvnet_fixcheck_s3p0_128.csv`) vs the historical
  8.6% / 26.4 / 4.2 — directionally positive, within ~1 SE; attribution
  partially confounded by newer OOC code in the current binary.
- Cost finding: S3+PVNet ≈ 18.5 cpu-sec/run at 100 sims (~18x S2 per-sim
  cost; `computeEdgePriors` runs a PVNet forward per expanded node). Phase 1
  arms at 3k sims ≈ 49 min per arm on 24 threads — sized accordingly.
- **Caveat (cost measurement):** during part of the 128-seed replication run
  another agent occupied 6 of the 12 cores, so the run was contended; the
  18.5 cpu-sec/run and wall-time figures are upper bounds, not clean
  measurements. Not re-tested (per session note); Phase 1 should re-measure
  cost on an uncontended server before sizing the α-sweep.

## Update 2 (same session, EXPERIMENTS.md §102): Phase 1 payoff gate — NEGATIVE, A–H stopped

- Ran the gate on GCP `sts-test` (fair, A0, 3k sims, 128 seeds 126700–126827,
  default OOC stack, tracked parity-fixed PVNet, same binary for all arms).
  Per-seed CSVs `build/pvnetgate_{s2_true,s3_ctl,s3_pv0,s3_pv1}_3k_128.csv`.
- Results: S2 true 21.1%; S3 ctl 26.6% (+5.5pp vs S2, CI touches 0); S3+PVNet
  α=0 19.5% (**−7.0pp vs S3 ctl** — priors hurt at deep search); S3+PVNet
  α=1.0 29.7% (+8.6pp vs S2, CI [−0.9, +18.1]) at **14–18x per-run compute**.
- **Decision: the A–H architecture sweep is stopped** (gate rule). The PVNet
  channel closes at the 3k operating point; the neural leaf's within-noise
  gain cannot survive a fixed wall-clock comparison; the 14x per-sim cost is
  structural. Phase 2 fairgen regeneration deprioritized for this purpose.
- Process findings recorded: OpenBLAS+OpenMP oversubscription
  (`OPENBLAS_NUM_THREADS=1` required; without it 47 threads on 24 cores ran
  slower than scalar — the cost numbers in §101/§102's earlier notes were
  measured under that contention), and the arm-0 `STS_SEARCHER3` labeling
  bug in `run_pvnet_gate.sh` (fixed: arm 0 now runs without it).
- Open: S3-without-net is the only same-cost positive signal; a searcher
  question, not a model question. If combat-model work resumes, the channel
  to chase is low-sim fully-neural play, which both §72 and this gate
  currently contradict.

## Update 3 (same session, EXPERIMENTS.md §103): S2+PVNet PUCT priors — exact tie with GBM, 8x cost

- Added PVNet-prior support to Searcher2 (`BattleScumSearcher2.cpp`,
  mirrors Searcher3 preference order). Tested at 3k sims, 128 seeds:
  **27/128 both** (21.1%), dWin +0.0pp CI [−6.9,+6.9]; 199 vs 24 cpu-sec/run.
- New `policystats` C++ mode for offline prior metrics (verified against a
  Python/GPU recomputation: entropy matches to 4 decimals).
- Findings: PVNet and GBM priors are equal-quality (PVNet teacher top-1
  0.409 vs GBM 0.388) yet agree on the best action only 42% of the time —
  at 3k sims the prior barely matters. No same-cost channel; PVNet stays
  experimental-off. Mid-run 11–16% readings were noise.
