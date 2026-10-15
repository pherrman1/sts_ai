# Latest-main verification commands

Source commit: `74a8c8edf83e2f55633af43232ef19540850eb2b`.
Rebase target: `c0937d8a3756b4849ab22c1dc8caf6badeda445f`.

```sh
evidence_dir=docs/experiments/evidence/deepset_entropic_brew_hybrid_2026-09-24/latest-main-source
cmake --preset linux-gcc-release
cmake --build --preset linux-gcc-build --target one_combat combat_transition_runtime_probe one_combat_advisor live_ooc_parity_test test_live_ooc_policy live_ctm_importer_test -j 8
ctest --test-dir build/linux-gcc-release -R 'ooc_mcts_adapter|combat_transition_runtime_loader' --output-on-failure
python3 tools/verify/combat_transition_potion_specialist_parity.py \
  --probe build/linux-gcc-release/combat_transition_runtime_probe \
  --artifact /tmp/deepset-entropic-hybrid-specialist.native \
  --checkpoint /tmp/deepset-potion-specialist-20260923/W.pt \
  --fixtures tests/fixtures/combat_transition_near_full.jsonl \
  --output "$evidence_dir/parity.json"
build/linux-gcc-release/combat_transition_runtime_probe --hybrid \
  /tmp/deepset-entropic-hybrid-specialist.native \
  selfplay/models/combat_transition_near_full_except_smoke_v2.native \
  tests/fixtures/combat_transition_near_full.jsonl \
  > "$evidence_dir/mechanism.jsonl" 2> "$evidence_dir/mechanism-summary.json"
build/linux-gcc-release/combat_transition_runtime_probe --benchmark \
  /tmp/deepset-entropic-hybrid-specialist.native \
  selfplay/models/combat_transition_near_full_except_smoke_v2.native \
  tests/fixtures/combat_transition_near_full.jsonl 100 \
  > "$evidence_dir/fixed-fixture-benchmark-release.json"
```
