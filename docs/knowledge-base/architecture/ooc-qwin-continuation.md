# Q_win continuation plan — desktop GPU handoff (2026-08-04)

Status: **EXECUTED 2026-08-04 — Steps 1–5 complete; results recorded in
EXPERIMENTS.md §96 and the historical evidence
`2026-08-04-qwin-continuation-desktop.md`. Both swept policies are negative
(every Q_win margin point loses to the V3 legacy reference; the regret gate
stays opt-in). Do not re-execute this plan as instructions; see §96 for the
recorded outcome.**

Original handoff text (historical): the Wave A1/A2 code is committed. The
laptop reached epoch 20 of the corrected-labels V3 Q_win retrain before the
session moved to the desktop; that partial run is discarded (no checkpoint
saved). The desktop GPU machine continues from here. All training data +
artifacts below are git-ignored — they must be transferred manually.

## 1. What is already done (committed)

- **Wave A1 (Q_win objective, §94):** `train_strategic.py` trains a pure
  win-probability Q head (BCE on the soft `labelWon`), plus `q_hp`/`q_floor`
  auxiliary heads, Brier/calibration metrics, `STRAT_PATIENCE` early stop;
  `export_strategic.py` writes `OOC_STRAT_V5` (sigmoid on Q/aux); the native
  loader accepts both V3 (legacy, bit-identical — verified seed-for-seed
  against `ref_m1.csv`) and V5. Laptop CPU retrain on the BIASED labels
  produced `selfplay/models/ooc_strategic_qwin.native` (V5, best epoch 24).
- **Wave A2 (V_win recalibration, §95):** parity check first — new
  `winnettest` mode + `tools/analysis/parity_vwin.py` proved the Python tree-walk matches
  C++ `WinNet` bit-identically (max |diff| 0.0 over 200 rows). Then
  `tools/analysis/fit_vwin_calibration.py` fit Platt + isotonic maps on 216,625 terminal
  rows (seed-held-out); isotonic selected (val Brier 0.1310 vs raw 0.1512,
  max decile 0.24 → 0.08) and applied to the 684,291 censored rows →
  `build/strategic_qwin_cal.csv` (censored labelWon mean 0.4547 → 0.3369).
  The earlier "grossly miscalibrated" claim in §94 was a checker bug
  (base_score logit conversion) — corrected in the same change.

## 2. What the desktop must do next (in order)

### Step 1 — Transfer the data and artifacts (manual, git-ignored)

From this laptop to the desktop (or re-sync via the GCP server):

| file | size | purpose |
|---|---|---|
| `build/strategic_qwin_cal.csv` | 1.92 GB | **corrected training data** (the primary input) |
| `selfplay/models/ooc_strategic_qwin_cal_state.bin` | 1.83 GB | precomputed z-scored state (trainer reuses by byte-size; skip = ~10 min rewrite on the desktop) |
| `selfplay/models/ooc_strategic_qwin.native` | 1.8 MB | biased-label V5 artifact (the A/B comparator) |
| `selfplay/models/ooc_strategic_qwin.pt` | 1.8 MB | its checkpoint (optional; for metric comparison) |
| `build/strategic_qwin_cal_calmap.json` | small | the fitted map record |

`build/strategic_qwin.csv` (1.92 GB, biased labels) is optional — only needed
if you want to re-derive the §94/§95 comparison.

### Step 2 — Retrain V3 Q_win on the corrected labels (desktop GPU)

```bash
STRAT_EPOCHS=40 STRAT_PATIENCE=6 python train_strategic.py \
  build/strategic_qwin_cal.csv selfplay/models/ooc_strategic_qwin_cal
```

- Check the startup `device: cuda` line (AGENTS.md: never default to CPU on
  the GPU machine; CUDA is the intended path).
- Expected: same budget as the laptop run but ~15–30 min on the RTX 3060 Ti.
- **Success criterion:** held-out q_brier < 0.05 AND q_cal_max < 0.03, and
  policy top-1 ≥ 0.78 (the biased run: 0.792/0.474; its epoch-20 partial on
  corrected labels was already better calibrated: q_brier 0.044, q_cal_max
  0.022).

### Step 3 — Export V5 + A/B vs the biased artifact

```bash
python export_strategic.py selfplay/models/ooc_strategic_qwin_cal.pt \
  selfplay/models/ooc_strategic_qwin_cal.native
```

A/B (both on the same held-out split, from the two `_metrics.json`):
- q_brier / q_cal_max / q_mae (expect the corrected artifact to be better
  calibrated, possibly slightly worse label-fit since labels are now honest)
- **the truth-check:** re-run `tools/analysis/check_vwin_calibration.py`'s terminal-row
  comparison against **Q_win** (not V_win) before/after — this directly
  tests whether the bootstrap bias propagated into the head. (Small script
  change: predict with the exported net instead of the trees.)

### Step 4 — Probability-point margin sweep (recorded block, GCP server)

With the corrected V5 artifact, sweep `STS_OOC_STRATEGIC_MARGIN` ∈ {0.01,
0.03, 0.05, 0.10} on the recorded 128-seed fair block (1,000 sims, 24
threads), full gate stack, vs the bit-identical `gates_ref_m1.csv` reference
(39.8%). Record as §96. Reference arms: V3 legacy stack at m=1.0 (§76), and
the biased-label V5 at the same probability-point margins (isolates the
recalibration's effect).

### Step 5 — Wave B: regret gate on the new Q

- Implement `Qmax(s) − Q(a_heur) > ε` with `a_heur` identified by the
  fingerprint method (datagen-proven, one_combat.cpp:5844); RNG-tied fallback
  to the margin rule; `STS_OOC_STRATEGIC_GATE=regret` opt-in; ε ∈ {0.01,
  0.03, 0.05, 0.10}. Built for all one-ply gates + the M2 route search (which
  stays off by default).
- 4-policy comparison on the recorded block (heuristic / NN-greedy ref /
  margin gate / regret gate) + disagreement analysis and per-screen stats
  (`STS_GATE_STATS=1`).
- Flip per the pre-registered adoption rule (beat margin-gate reference on
  128 AND hold on 256); otherwise stay opt-in.

## 3. Deferred follow-ups (recorded, not this round)

- **Q_boss aux head** — needs a `strategicgen2` branch-level boss-flag label
  column (datagen extension). Remembered as follow-up (a).
- **Calibration transfer validation** — short K=6 (or full-run continuation)
  datagen on ~50–100 fresh seeds to verify the isotonic map holds on
  censored/cutoff states, not just terminal decision states.
- **V4 Q_win retrain** — the token net (V4) gets the same Q_win objective in
  a second round (V3 first, per the agreed order).
- **C++-side bootstrap recalibration** — apply the fitted map inside
  `finishOocCounterfactual` so future datagen is born calibrated.

## 4. Server workflow reminder

- `gcloud compute ssh philippherrmann@sts-test --zone=europe-west3-c` (the
  GCP working tree `/home/philippherrmann/sts_sweep` is a non-git rsync
  copy; sync `apps/one_combat.cpp` + models via `gcloud compute scp`, build
  with `cmake --build build -j 24`, run sweeps there, pull per-seed CSVs
  back for `paired_analysis.py`).
- Long runs (128/256-seed sweeps, datagen) go to the server; training goes
  to the desktop GPU.
