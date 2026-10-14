# §476 evidence: gen-6 Silver MLP prior at A20 with a simulation sweep

- Pre-registration: [`PREREG.md`](PREREG.md), frozen before any evaluation seed (`SHA256SUMS`). The
  pre-launch review asked for three changes (truncated-CSV handling in the analyzer, a realistic cost
  and a 12 h shard timeout, a watcher and container-loss rerun rule); they landed in `072d0577` and the
  delta review passed. Runner [`run.sh`](run.sh), [`env.sh`](env.sh), analysis
  [`analyze_476.py`](analyze_476.py), gen-5 model copy `combat_policy_mlp_gen5.txt`.
- Code: `339da3b1` (main `e8410510` + `mlpsweep`), run from checkout `072d0577`. Release `one_combat`
  sha256 in [`BINARY_SHA256`](BINARY_SHA256); [`FROZEN.txt`](FROZEN.txt) has the binary, model and
  teacher sha256 as run. This predates the ADR-0035 Silver leaf defaults: every arm used the legacy
  terminal score.
- Run: 2026-10-14 18:46–21:00Z in one cloud container, 4 shards × 24 seeds (104000000–104000095),
  all rc 0 ([`shards.txt`](shards.txt)), 96/96 manifests, no stall, no timeout, no rerun.
- Raw: `/mnt/project-files/silver-gen6-a20-476/x476-run.tar` (sha256 in [`TAR_SHA256`](TAR_SHA256);
  checked from a second container by the coordinator session, 2026-10-14 21:04Z).
- Output: [`analysis.json`](analysis.json) from `python3 analyze_476.py analysis.json main` over the
  extracted tar.

## Exclusions
1,088 fights replayed, 1,080 valid in every arm. The 8 excluded (`invalid_arm_row`) carry 125
escape-quarantined arm rows (Smoke Bomb or a fleeing enemy) and 12 `control_state_invalid` rows.
The shard manifests count 7 control-replay mismatches, all among these 8 fights. `truncatedRows` and `incomplete_shard_abort`: 0. 636 normal fights were skipped by the one-in-three
hallway rule. Valid fights: 194 boss (87 act 1, 53 act 2, 54 act 3), 510 elite, 339 normal, 37 event.
