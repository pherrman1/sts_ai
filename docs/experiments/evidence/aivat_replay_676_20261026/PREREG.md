# AIVAT replay pilot on the §676 guard: pre-registration (2026-10-26)

**Authorization.** Philipp, 2026-10-26 23:13Z (00:13 CET), thread "Shrink A/B variance with AIVAT": "go on 4 workers".

**Question.** Does subtracting fight luck measured by fresh fight replays shrink the paired per-seed SD of a real
A20 A/B as projected offline (§TBD, [aivat_fight_replay_20261026](../aivat_fight_replay_20261026/RESULT.md))?

**Data.** The 512 §676 guard seeds (111392000-111392511), both arms (A raw CTM, C calibrated CTM), from their unit
tars in `/mnt/project-files/ctm-calibration-ab/units/` (hashes in `source_tars.sha256`). No new gameplay seeds:
every fight is re-played from its recorded pre-combat state. Fresh replicates draw battle seeds from
`SEED_BASE = 676000001` hashed with (run seed, fight index, replicate), so both arms of a seed share them.

**Intervention.** `one_combat fightreplay` (PR #872 at `4da941d`), per seed: every recorded non-event fight of both
arms, replicate 0 = identity gate (recorded seed, must reproduce the recorded outcome and post state exactly),
replicates 1-4 fresh. Combat config = the §676 units' frozen env plus `STS_SILVER_ACT4_STRONG=0` (`run_unit.sh`);
binary = `code_commit` built with `linux-gcc-release-x86-64-v3` (`campaign.manifest`).

**Estimator** (`tools/aivat_estimate.py estimate`, fixed before the run): `Y_hat = Y - beta * sum_k [V(actual post_k)
- mean_r V(replay post_k,r)]` over all replayed fights, `beta = 4/5`; V = `v_661_683.xgb.json` (sha256 `8efcc81f…`,
trained by `aivat_estimate.py train` on the §661 + §683 units only; V = 0 after a death, 1 after a won Heart).
Paired C - A, seed bootstrap (4,000).

**Prediction.** Paired SD ratio (corrected / raw) 0.71 (offline projection; six comparisons 0.70-0.72). The corrected
C - A difference agrees with the raw +2.15 pp within noise (it is unbiased by construction).

**Decision rule.**
- Validity first: every identity replay must match. Any mismatch -> the affected seeds are reported and excluded, and
  the cause is found before the method is used anywhere else.
- SD ratio <= 0.80 -> the method works: propose replay correction as a secondary metric for future A/Bs (a separate
  decision for Philipp, with the cost under today's Act-4 strong Heart).
- 0.80 < ratio < 0.90 -> weaker than projected; report, no recommendation.
- ratio >= 0.90 -> NOT_USEFUL; stop the line.
- The raw-vs-corrected difference of the C - A estimate is reported with its own bootstrap CI as a bias check.

**Cost.** ~86 CPU-s of combat per run under this config (identity check on 18 runs) x 5 plays x 1,024 runs ~= 120
CPU-h: ~14 min per unit (one seed, both arms), 512 units on 4 workers x 4 lanes ~= 8 h wall plus stragglers.
