# Phase F plan — policy-head search distillation (5.7.1 + 5.7.2 only)

Status: **ACTIVE handoff plan (2026-08-04) for a new session.** Not yet
executed — this is the plan to run. Scope: action-plan items 5.7.1 (produce
improved policy targets `π_target(a|s) ∝ exp(Q_search(s,a)/τ)`) and 5.7.2
(train the policy head toward those targets). **5.7.3 (the iterative
play→search→train→repeat loop) is explicitly out of scope.** Record the
outcome in EXPERIMENTS.md (next § number — the combat-side agent used
§97–§99; the map-DAG wave used §100; check the tail before writing), the
decision log, and tick the action-plan items when done.

## 1. Why this wave

- §100 falsified the map-DAG encoder on the current labels: offline MAP
  ranking improved (q_top1_map 0.506, val_pol_ce 0.426) with **no gameplay
  transfer** — the §62 lesson repeats: "better absolute prediction does not
  identify the causal best route". The falsification points at the label
  horizon/quality (K=3 one-ply counterfactuals) or the **policy objective**,
  not the encoder. Phase F attacks the objective: the policy head currently
  trains on one-hot `chosen` (behavioral imitation); search distillation
  trains it on the counterfactual search values instead.
- §96 already established the risk to measure: every Q_win gate arm lost to
  the V3 legacy reference (39.8%), and the regret gate was ≈ baseline. Phase
  F's question is narrower: **does a policy trained on
  softmax(labelWon/τ) beat one trained on one-hot chosen, in the gate?**
- The Tier-B labels already ARE the per-action search values (K=3
  counterfactual continuations + bootstrap, futures=1, sample-all → every
  action row has `labelWon`). **No datagen is required for the first
  experiment.**

## 2. Current state (verified 2026-08-04)

- Corrected training data: `build/strategic_qwin_cal.csv` (7.57 GB, 809,146
  rows, 1,295 seeds; the truncated trailing line was fixed in §96). Every row
  carries `labelWon` (sample-all; `q_n` == all val rows in the trainer
  output). Z-scored state: `selfplay/models/ooc_strategic_qwin_cal_state.bin`
  (byte-size reuse; **do not trust it after a killed trainer** — see §7).
- Models: `ooc_strategic_qwin_cal.{pt,native}` (V5, md5 3ac8343d…, best epoch
  40: val_pol_ce 0.4671, policy top-1 0.797, q_brier 0.041, q_cal_max 0.065);
  `ooc_strategic_qwin.{pt,native}` (biased labels, md5 a8a323c0…);
  `ooc_strategic_map_enc.{pt,native}` (V6 map-DAG, falsified, opt-in).
- Trainer: `train_strategic.py` — group-CE on one-hot `chosen` (line ~"policy
  CE" in `train_batch_loss`), Q_win BCE + aux heads, per-screen value heads,
  `STRAT_EPOCHS/STRAT_PATIENCE/STRAT_BATCH/STRAT_QLAMBDA/STRAT_DEVICE`,
  GPU default (check the `device: cuda` line). **No soft-target support yet.**
- Exporter: `export_strategic.py` (V3/V5/V6 magics, numpy-vs-torch parity).
  The `pol` head is already written to every artifact.
- C++: `apps/ooc_strategic_net.h::OocStrategicNet` has
  `predictPolicyLogit(state, actionBits, cats, actionType, screen)` (raw
  logit, no sigmoid) — **defined but not consumed by any gate**. The one-ply
  gates use `predictActionValue` (Q). Regret-gate machinery
  (`regretGateChoose`/`regretGateTail`, `STS_OOC_STRATEGIC_GATE=regret`,
  per-screen heuristic runners `regretHeur*`) exists from §96.
- Recorded-block protocol (§6): fair, A0, 1,000 sims, seeds 126700–126827
  (128), `STS_FAIR=1`, paired via `paired_analysis.py` against
  `build/gates_ref_m1.csv` (V3 legacy full stack m1.0, **39.8%**). Existing
  arms on the same block: flags-off baseline `build/tierb_gate_base.csv`
  (21.1%); §96 margin arms `build/qwin{,_cal}_m*.csv`; regret arms
  `build/regret_cal_e*.csv`. The **GCP server is used by another agent — run
  locally** (12 threads ≈ 90 s per config; 8 configs ≈ 15 min).
- The other agent's combat-side wave (§97–99) made **V4@3,000 sims on the
  256-block** (45.3%) the new recommended baseline; the V3@1k 128-block
  reference above remains the paired protocol for this wave.

## 3. Step 1 — π_target diagnostic (5.7.1a, local, ~10 min, no code)

On `build/strategic_qwin_cal.csv` (use the `need`-column read from the
trainer; groups = seed×1e6+decIdx):

1. Per decision group with ≥2 rows: `label_argmax = argmax(labelWon)` vs
   `chosen` — report **agreement(label_argmax, chosen)** overall and per
   screen (MAP/REWARDS/SHOP/REST/EVENT/CARD_SELECT/TREASURE/BOSS_RELIC).
2. Soft-target determinacy: at τ ∈ {0.3, 1.0, 3.0}, report the softmax
   margin (`p1 − p2`) and entropy distribution over groups.
3. Also report `q_top1`-style agreement: `argmax(softmax(labelWon/τ))` vs
   `argmax(labelWon)` (how much the soft target top-1 differs from the hard
   argmax at each τ).

**Decision gate:** if agreement(label_argmax, chosen) ≥ ~0.90 overall, the
search targets barely disagree with behavior → the distillation has little
to add; record and stop. Otherwise proceed. This single number also frames
the A/B interpretation (§96's arms suggest the label argmax is NOT aligned
with behavior; the diagnostic quantifies it).

## 4. Step 2 — K=6 deep targets (5.7.1b, local, ~2–4 h, conditional)

Only if Step 1 shows real disagreement. Deeper search values = less
bootstrap-inherited label noise (§95's isotonic map only corrects the
bootstrap bias, not the short-horizon truncation):

```bash
STRATEGIC_BRANCH_FIGHTS=6 STRATEGIC_BRANCH_SIMS=150,100,50,40,30,25 \
  ./build/one_combat strategicgen2 500 1000 0 build/strategic_qwin_k6.csv 200000
```

- Knobs: `STRATEGIC_BRANCH_FIGHTS` (default 3), `_SIMS` (default
  150,100,50 — one per fight; extend to 6 entries), `_FUTURES` (keep 1 —
  §84: futures=1 optimal). Fresh seeds 200000+ avoid overlap with §94's
  datagen. Native OOC is serverless; the run needs no v_server.
- This also closes the §95-deferred **K=6 calibration-transfer validation**
  (the isotonic map applied at K=3 cutoffs must hold at K=6 cutoffs) — run
  `check_vwin_calibration.py --ckpt <k6-model> build/strategic_qwin_k6.csv`
  after Step 4's training.
- **Cheaper fallback if time is short:** skip Step 2 and run Step 3/4 on the
  existing corrected labels (the labels' K=3 values ARE the Q_search input —
  the point of Step 4 is the objective, not the horizon). Step 2 is the
  follow-up that strengthens the signal, not the gate for Step 4.

## 5. Step 3 — implementation (5.7.2)

**Trainer (`train_strategic.py`):**
- New env `STRAT_DIST_LAMBDA` (default 0.5) + `STRAT_DIST_TAU` (default 1.0).
  Policy loss becomes `(1−λ)·CE(one-hot chosen) + λ·CE(softmax(labelWon/τ))`
  over each group's rows (stable logsumexp, same group machinery as the
  existing policy CE). λ=0 must reproduce today's numbers exactly.
- New metric `dist_top1` (policy argmax vs soft-target argmax) in
  `evaluate()`; keep `policy_top1` (behavioral) and `val_pol_ce` (early-stop
  criterion unchanged).
- Everything else identical (Q head, aux heads, per-screen values, freeze/
  init knobs from §100 unchanged).
- Smoke: `STRAT_DEVICE=cpu` 2-epoch run on a CSV slice before the GPU run.

**Gate arm (C++):**
- `apps/one_combat.cpp`: env `STS_OOC_STRATEGIC_SCORE=policy` (default `q`):
  the one-ply gates score candidates with `sigmoid(predictPolicyLogit(...))`
  for V5/V6 (probability scale, so the existing `STS_OOC_STRATEGIC_MARGIN`
  probability-point semantics apply) instead of `predictActionValue`.
  `predictPolicyLogit` already exists in `apps/ooc_strategic_net.h` — do not
  add a new method. Margin path and regret-gate fallback must stay
  byte-identical when the env is unset.
- Verify: `./build/test`, V5 legacy bit-identity, 8-seed smoke where the
  policy-score arm differs from the Q arm.

## 6. Step 4 — paired A/B (local, ~30 min)

Recorded 128-seed fair block, six gates ON
(`STS_OOC_STRATEGIC_{REST,EVENT,SHOP,TREASURE,BOSS_RELIC}=1`), `STS_FAIR=1`,
`OMP_NUM_THREADS=12`, `bestbench 1000 128 0 126700 <out>.csv`:

| arm | config |
|---|---|
| Q-gate (existing §96 arm) | `STS_OOC_STRATEGIC_NN=ooc_strategic_qwin_cal.native`, score=q, m ∈ {0.01, 0.03, 0.05, 0.10} — reuse `build/qwin_cal_m*.csv` |
| distilled-policy gate | same model, `STS_OOC_STRATEGIC_SCORE=policy`, same margins (4 new runs) |
| reference | `build/gates_ref_m1.csv` (39.8%) |

Pre-registered success criteria: (1) distilled-policy gate ≥ Q-gate on wins
per margin (paired); (2) any flip candidate must beat the reference on 128
**AND** hold on 256 (the 256-block is `seeds 126700–126955`, ~7 min/config)
— otherwise stay opt-in. Report the 4-policy comparison
(heuristic / Q-gate / policy-gate / regret-gate) with `paired_analysis.py`.

## 7. Risks, lessons, and traps

- **§96/§100 context:** the same labelWon signal made every Q_win gate arm
  lose to the V3 reference; Step 1 exists to quantify whether the soft-target
  objective can beat one-hot on that signal. A flat or negative A/B is a
  legitimate, recordable outcome — the falsification chain (encoder →
  objective) completes either way.
- **Killed trainer → corrupt `_state.bin`:** a killed `train_strategic.py`
  can leave a byte-size-valid but corrupt `_state.bin` that a rerun silently
  reuses (the §100 tell: the frozen base's value_mae read 7.57 instead of
  1.7388). After any kill, `rm` the `_state.bin` (rewrite ≈ 10 min) or verify
  a frozen-model metric against the source run.
- **GCP server is in use by another agent — do not ssh/scp to `sts-test`.**
  Everything here runs on the desktop (RTX 3060 Ti, 12 threads).
- **Do not touch the other agent's §97–99 content** (combat-side wave) when
  appending EXPERIMENTS.md; renumber your own entry if the tail changed.
- Do not re-open the map-DAG encoder (falsified, §100) or the M1/M2 map
  overrides (§91/§93). Do not implement 5.7.3.
- `predictPolicyLogit` returns the **raw logit** — sigmoid before applying
  probability-point margins, or the gate will not fire.
- Do not change the early-stop criterion or the Q/aux losses; the A/B must
  isolate the policy objective.

## 8. Recording (definition of done)

- EXPERIMENTS.md: new § entry (date, config, model hashes, seeds, regime,
  margins, per-arm tables, CIs via `paired_analysis.py`, verdict) — mirror
  §96/§100 format.
- Decision log: `YYYY-MM-DD-phase-f.md` with the decisions/findings.
- Action plan: tick 5.7.1/5.7.2 (with the verdict), keep 5.7.3 unchecked.
- KB: update `docs/knowledge-base/architecture/out-of-combat.md` (the
  score-source env + soft-target loss) and its Last-verified line; link this
  plan's outcome. Update `evaluation/current-baselines.md` only if a flip
  happens.
- `git diff --check`; commit only intended files; the other agent may be
  editing shared docs concurrently — stage explicitly.
