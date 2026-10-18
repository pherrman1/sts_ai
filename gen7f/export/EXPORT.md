# Gen-7f g7f_E export to combat_policy_mlp_v2 + native parity (2026-10-18, local RTX 3060 Ti box, no games)

Same procedure as gen7/export/EXPORT.md, adapted to pack-g7f.npz and runs/g7f_E/model.pt.
one_combat built from a clean origin/main checkout at 05da2c07 (>= e032c04b; worktree via tools/agent/worktree.py
create --detach): cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCMAKE_POLICY_VERSION_MINIMUM=3.5 && cmake --build build --target one_combat

Script changes vs gen7/export: prep_roots.py and parity.py read pack-g7f.npz; parity.py compares g7f_E (not g7_E) and
writes parity-native-g7f.json. export_native.py unchanged. names.json regenerated with `silversynthreplay names`
(STS_ACTIVE_POWER_FEATURES=1) and is byte-identical to gen7/export/names.json.
All native runs used STS_ACTIVE_POWER_FEATURES=1:
  OC silverpolicymlpcheck W/combat_policy_mlp_g7f_E.txt W/pfx    W/native_g7f_E.txt > W/check_g7f_E.out
  OC silverpolicymlpcheck W/combat_policy_mlp_g6_E.txt  W/pfx_g6 W/native_g6_E.txt  > W/check_g6_E.out

Control: the re-exported g6_E file is byte-identical to main's models/combat_policy_mlp_g6_E.txt (sha256 ca9bd7f2...).
Result: gen7f/parity-native-g7f.json. g7f_E max |native - torch| 1.91e-6 (pass, limit 3e-6).
g6_E control max 3.10e-6 on these 4000 pack-g7f roots: one edge of 23,685 is at or above 3e-6 (logit -2.3166, relative error
1.3e-6, float32 rounding). Gen 7 got 1.91e-6 for g6_E on pack-g7 roots. The control file is byte-identical, so the model
is unchanged. The pass flag in the JSON reports this edge as is.
