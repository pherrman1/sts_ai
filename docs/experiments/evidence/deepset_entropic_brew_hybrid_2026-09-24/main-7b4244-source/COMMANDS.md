# Latest-main (#310) verification

Source baseline: `7b4244ef8af4508466e01a1a6b515c70015e6274`.

```sh
cmake --preset linux-gcc-release
cmake --build --preset linux-gcc-build --target one_combat combat_transition_runtime_probe one_combat_advisor live_ooc_parity_test test_live_ooc_policy live_ctm_importer_test -j 8
ctest --test-dir build/linux-gcc-release -R 'ooc_mcts_adapter|combat_transition_runtime_loader' --output-on-failure
python3 tools/verify/combat_transition_potion_specialist_parity.py \
  --probe build/linux-gcc-release/combat_transition_runtime_probe \
  --artifact /tmp/deepset-entropic-hybrid-specialist.native \
  --checkpoint /tmp/deepset-potion-specialist-20260923/W.pt \
  --fixtures tests/fixtures/combat_transition_near_full.jsonl \
  --output docs/experiments/evidence/deepset_entropic_brew_hybrid_2026-09-24/main-7b4244-source/parity.json
build/linux-gcc-release/combat_transition_runtime_probe --hybrid \
  /tmp/deepset-entropic-hybrid-specialist.native \
  selfplay/models/combat_transition_near_full_except_smoke_v2.native \
  tests/fixtures/combat_transition_near_full.jsonl \
  > docs/experiments/evidence/deepset_entropic_brew_hybrid_2026-09-24/main-7b4244-source/mechanism.jsonl \
  2> docs/experiments/evidence/deepset_entropic_brew_hybrid_2026-09-24/main-7b4244-source/mechanism-summary.json
build/linux-gcc-release/combat_transition_runtime_probe --benchmark \
  /tmp/deepset-entropic-hybrid-specialist.native \
  selfplay/models/combat_transition_near_full_except_smoke_v2.native \
  tests/fixtures/combat_transition_near_full.jsonl 100 \
  > docs/experiments/evidence/deepset_entropic_brew_hybrid_2026-09-24/main-7b4244-source/fixed-fixture-benchmark-release.json

# Prove CMake can configure and build a non-CTM target without OpenSSL.
cmake -S . -B /tmp/sts-no-openssl-config \
  -DCMAKE_DISABLE_FIND_PACKAGE_OpenSSL=TRUE -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/sts-no-openssl-config --target main -j 8
```

The specialist checkpoint and fallback artifact were reused unchanged. No
gameplay seeds were run; the original 64-pair evidence remains tied to frozen
executable `9ce11fdbe50f32b4b2646dd8a0803c6dc0c3f351`.
