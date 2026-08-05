# Experiment rerun ledger

Last verified: 2026-08-05 against the current working tree.

Tracks experiments invalidated by code-review fixes (issues 31–46) and the
benchmark artifacts that must be re-derived before their numbers can be used
again. Rows are added when a fix lands; each row is `pending → running → done
(§ref)` and is updated by the change that completes it. "Blocked" rows stay
until the related research line reopens. Source: `docs/knowledge-base/issues/`
entries 2026-08-05; decisions recorded in
`decision-log/2026-08-05-code-review.md`.

| Issue | Invalidated experiments | Required rerun | Status |
| --- | --- | --- | --- |
| [36](2026-08-05-issue-36-tok-glob-stats-columns.md) | All V4 token-net training incl. deployed `ooc_strategic_tok_final.native` — 45.3% V4@3k baseline (§99), 7-gate stack (§81/§83), R6/R7 gates | Retrain V4 (fixed stats) → re-export → re-run simsweep + full gate stack paired against `build/simsweep_v4_3k_256.csv` | done — §108: retrain + export (parity 9e-6) + S2-paired (−2.3pp/128, −3.9pp/256, n.s.) + S3−belief−chain-paired (**−8.98pp, p=0.028, significant**). Deployed 05178ec8 stays; fixed model archived as falsified retrain |
| [41](2026-08-05-issue-41-s3live-ablation-noop.md) + [46](2026-08-05-issue-46-bestbench-append-dedup.md) | §106 `s3ablate_s2_ref` / `s3ablate_s3_ctl` arms (first aggregation used polluted append-duplicated files) | Clean re-runs of the two arms (truncating) — completed 2026-08-05; A0 43.8% and A1 49.2% reproduce exactly; A3/A5 bit-identical claims re-verified per-seed vs clean A1; §106 amended with the verification note | done (§106 re-verification note) |
| [33](2026-08-05-issue-33-vwin-calibration-split-leak.md) | Calmap selection feeding the Q_win chain: §94/§95 corrected labels, V5 qwin_cal (§96), margin sweeps, dist wave (§103), Phase F (§104), label-noise (§105), map-DAG E1 base | Re-fit calmap on fit rows only → retrain qwin_cal → downstream. The Q_win line is falsified (§104/§105); run only if it reopens. Recorded negatives stand as recorded | blocked (line closed) |
| [32](2026-08-05-issue-32-pvnet-untrained-heads.md) + [37](2026-08-05-issue-37-pvnet-token-layout-mismatch.md) | §101 parity, §72 replication (12.5%), §102 payoff gate (α=0 −7.0pp, α=1.0 +8.6pp) — trained with untrained potion/turns heads + batch-dependent dead-slot tokens | Regenerate fairgen value CSVs with rich labels (producer fixed) → retrain PVNet → re-parity → re-gate only if the PVNet channel reopens; re-measure §102 costs on an uncontended server | blocked (GPU + datagen; line closed) |
| [34](2026-08-05-issue-34-searcher3-encode-buffer-overflow.md) | None known (payoff gate used d128 `v_combat_pvnet.txt`) | Verify no recorded experiment used a d256 combat artifact | verify-only (done: none found) |
| [35](2026-08-05-issue-35-state-bin-byte-size-reuse.md) | Dist wave + label-noise trainings (`*_train.log` "reusing …_state.bin") | After the fingerprint guard: verify each log's state.bin provenance vs its source CSV; rerun only where mismatched | done — all dist-wave logs show 809,146 rows/1,295 seeds matching `build/strategic_qwin_cal.csv`; same-CSV-family reuse, benign; guard prevents future silent reuse |
| [31](2026-08-05-issue-31-probe-cpsi-normalization.md) | §80 V4+probes A/B + `strategic_tierb_probes.npy` + `ooc_strategic_tok_probes.pt` (never deployed; `one_combat.cpp` does not read `TOK_PROBES_FILE`) | Regenerate probes (fixed script) → re-run §80 A/B only if Phase-C probe integration reopens; verdict was neutral | blocked (line closed) |
| [16](2026-08-02-issue-16-pvnet-sweep-provenance.md) | PVNet 66.4% headline (already falsified-as-recorded, §72) | Re-derive only if PVNet becomes a default candidate | deferred |
| — (decision-log) | §101/§102 cost figures measured under contention | Re-measure on uncontended server | closed as superseded — §107 re-sized the operating points (1k = 9.8 cpu-s/run vs 3k = 31.3) on the promoted stack; the §102 PVNet channel is closed, so its cost rows are no longer actionable |

## Conventions

- A row is added/updated in the same change that lands its fix.
- A rerun is "done" only when its artifacts and EXPERIMENTS.md reference are
  recorded (`done (§N)`).
- Blocked rows are not closed; they carry the condition that unblocks them.
