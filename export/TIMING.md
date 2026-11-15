Native forward cost per root, `one_combat silverpolicymlpcheck` (built from claude/rp-vprime d064c6d = 705f7e7 C++,
Release), STS_ACTIVE_POWER_FEATURES=1, gen7f export prefix (4,000 roots, 23,685 edges), pinned to one core
(taskset -c 2), PC idle (GPU training finished), 3 repetitions each (first g7f_E run includes warm-up):

| model | h1/h2 | params | us/root (3 reps) | vs g7f_E |
|---|---|---|---|---|
| g7f_E (models/, c45dcc0a) | 128/64 | - | 6.69, 5.61, 5.53 | 1.00x (5.6) |
| V | 128/64 | 263k | 5.63, 5.63, 5.55 | ~1.0x |
| W256 | 256/128 | 530k | 10.45, 10.05, 10.09 | ~1.8x |
| L512 | 512/256 | 1.11M | 23.81, 23.82, 23.72 | ~4.2x |

W256 export parity (export_parity.py): ckpt vs artifact max |d| 9.5e-7 (20,000 val roots), artifact vs native
max |d| 1.3e-6 (4,000 roots), 0 argmax mismatches -> pass (< 3e-6). combat_policy_mlp_rp_W256.txt sha256 5aa1abae...
names.json = gen7-gpu/data/gen7f/export/names.json (silversynthreplay names, STS_ACTIVE_POWER_FEATURES=1).
