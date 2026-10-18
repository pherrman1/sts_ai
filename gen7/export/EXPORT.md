# Gen-7 g7_E export to combat_policy_mlp_v2 + native parity (2026-10-18, local RTX 3060 Ti box, no games)

one_combat built from a clean origin/main checkout at 29e18fc2 (worktree via tools/agent/worktree.py create --detach):
  cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5 && cmake --build build --target one_combat

Scripts here are copies of main's docs/experiments/evidence/silver_prior_arch_20261014/scripts/{export_native,prep_roots}.py
with only the sys.path / pack path changed (arch_dev.py imported as `arch`, silver_az_mlp.py from this branch root,
pack-g7.npz instead of pack-g4.npz). parity.py is new: compares native vs torch logits and writes parity-native-g7.json.

Commands (W = work dir, D = this branch root, OC = build/one_combat run from the repo root):
  OC silversynthreplay names W/names.json          # identical to the feat lines of the shipped g6_E file
  cd W; export STS_TOOLS=D
  python3 prep_roots.py                            # 4000 fold-4 roots of pack-g7.npz, default_rng(123)
  python3 export_native.py D/runs/g7_E/model.pt   combat_policy_mlp_g7_E.txt names.json roots.bin pfx
  python3 export_native.py D/results/g6_E/model.pt combat_policy_mlp_g6_E.txt names.json roots.bin pfx_g6   # control
  OC silverpolicymlpcheck W/combat_policy_mlp_g7_E.txt W/pfx    W/native_g7_E.txt
  OC silverpolicymlpcheck W/combat_policy_mlp_g6_E.txt W/pfx_g6 W/native_g6_E.txt
  python3 parity.py

Control: the re-exported g6_E file is byte-identical to main's models/combat_policy_mlp_g6_E.txt (sha256 ca9bd7f2...).
Result: gen7/parity-native-g7.json (max |native - torch| 2.39e-6 for g7_E, 1.91e-6 for g6_E; limit 3e-6).
