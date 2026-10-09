# Focused integration checks after main synchronization

**Result: focused integration passed after one test-fixture repair.** The
merged source is `61b9616ab2137d9c950f414fb8e162290d83ae5c`, incorporating main
`70f7dfe5781a25b06caca49ae404b62208a81ad9`. Configure and the targeted Debug build
passed. The first executed CTest suite passed **21 of 22** checks; the one
failing fixture passed in a separate **1-of-1** rerun after repair. All 22
selected checks therefore have passing endpoints; this was not a single
22-of-22 invocation.

These are integration and synthetic/fixture checks. No experimental game
cohort or efficacy analysis was run. The K-precision primary remains
`EXECUTION_BLOCKED`, and the earlier RemoveLow confirmation remains separate.
Local integration results do not assert a GitHub `Linux GCC` CI pass or qualify
the newly merged executable's gameplay strength.

## Preserved attempts and repair

1. [Configure](configure_receipt.json) passed with `cmake --preset
   linux-gcc-debug`; the [targeted build](build_receipt.json) passed at `-j6`.
2. The [first test launch](ctest_launch_failure_receipt.json) failed before
   CTest or a fixture started. Restricting PATH to `/usr/bin:/bin` selected the
   existing system Python but omitted CTest, installed under
   `/home/philippherrmann/.local/bin/ctest`. The inline receipt writer then
   tried to hash a nonexistent JUnit file. Its observed exit was 1; the
   original subprocess exit was not durably emitted and is recorded as
   unavailable. The raw log was preserved.
3. The [repaired launch](ctest_v2_receipt.json) used CTest's absolute path and
   completed all 22 selected checks with exit 8: 21 passed and
   `combat_transition_native_contract` failed during its temporary probe's
   compilation. The fixture hardcoded `-std=c++17`, while CMake specifies C++20
   and the included headers require C++20 defaulted comparisons.
4. The [affected-only repair check](ctest_contract_repair_receipt.json) passed
   with exit 0 in 4.62 seconds. The sole edit was
   `tests/test_combat_transition_native_contract.py:55`, changing the standalone
   compiler flag from `-std=c++17` to `-std=c++20`. Before SHA256:
   `72c5a5f39e234ee187975625b0caf0642cb93ccca2f7690eb5f3326f91e53562`;
   after: `8a51043aa1e877574daf8ea623326f6123676ce2d20d1e521df6e8dfce9682c5`.
   Independent review accepted this one-line repair. No production source or
   frozen input was changed during the checks.

## Commands and environment

Commands ran from the worktree root. Receipts retain exact argument arrays,
timestamps, exits and raw-log/JUnit hashes. The build command was:

```sh
cmake --preset linux-gcc-debug
cmake --build build/linux-gcc-debug -j6 --target \
  one_combat combat_transition_runtime_probe \
  native_ooc_shop_features_test native_ooc_card_win_rank_test \
  rest_recall_filter_test full_hp_rest_filter_test \
  remove_obtain_weight_test test_ooc_public_futures
```

The focused CTest command used the exact anchored selection below, `-j2`, and
a 180-second timeout per check. The repository's registered simulator fixtures
also retain their seed-guard wrappers; no cohort command was substituted.

```sh
TEST_PATTERN='^(rest_recall_filter|full_hp_rest_filter|remove_obtain_weight|native_ooc_card_win_rank|native_ooc_shop_features|ooc_public_futures|ctm_escape_selftest|ctm_capabilities_selftest|ctm_lizard_selftest|combat_transition_runtime_loader|ctm_research_candidate_loader|combat_transition_native_contract|ctm_escape_runtime|ctm_writhing_ritual_runtime|ctm_lizard_runtime|ooc_mcts_adapter|ctm_offline_score_rows|vwin_refresh_producer_contract|vwin_refresh_policy_export|vwin_e3_cf_selftest|teacher_schema_compat|learned_stop_teacher_contract)$'
bash tools/seed_guard.sh /home/philippherrmann/.local/bin/ctest \
  --test-dir build/linux-gcc-debug --output-on-failure -j2 --timeout 180 \
  -R "$TEST_PATTERN" --output-junit /home/philippherrmann/.codex/worktrees/ironclad-overnight-20261008/sts_lightspeed/build/linux-gcc-debug/integration-61b9616/ctest_v2.xml
```

The affected-only rerun used the same command with
`-R '^combat_transition_native_contract$'`, no `-j2`, and the distinct output
`ctest_contract_repair.xml`. Existing logs were not overwritten.

Test runtime: existing `/usr/bin/python3` 3.12.3, NumPy 2.5.1, Pandas 3.0.5 and
PyTorch 2.5.1+cu121. No dependency was installed. CUDA visibility was empty;
OMP/OpenBLAS/MKL threads were each 1. Inherited `STS_*` variables were removed
before CTest applied registered per-test settings. Temporary files and Python
bytecode used private paths under `build/linux-gcc-debug`. Exact environment
values are in the CTest receipt.

The selected checks covered six campaign fixtures (public futures, shop,
Recall, full-HP REST, removal and card ranking); CTM escape/capability/Lizard
synthetic and runtime checks; native contract/runtime/candidate loaders; the
OOC MCTS adapter and offline score rows; GEN2 policy/producer and teacher
contracts; and E3's synthetic self-test. The machine summary records every
test name and its observed result.

## Identity and custody

[INTEGRATION_RESULT.json](INTEGRATION_RESULT.json), SHA256
`093478412107f512d05ef7408f3fb5321805b1c3cf5cd8a0ff4e0c5d498d47c6`, binds all
five attempt receipts, all selected outcomes, the source/fixture hashes and
the eight built executables. The merged Debug binaries include:

| Executable | SHA256 |
|---|---|
| `build/linux-gcc-debug/one_combat` | `5c6cb7396bb70514f09765a9213a7e13f0cd0dfc983d907aa045b94cbdea6650` |
| `build/linux-gcc-debug/combat_transition_runtime_probe` | `fdc6ebec9c131374373df0e345b1345b83f62d929fe289cae15d5581fce35e9c` |

These identities are distinct from the immutable `3ed91ab3` GEN2 producer and
the earlier confirmation executable. All 21 entries in the K-precision
freeze's artifact map, plus its separately bound producer and teacher,
matched after testing: **23 unique files unchanged**, with the policy already
included in the artifact map. Frozen binary directories were untouched.

Raw logs and JUnit files are preserved under
`build/linux-gcc-debug/integration-61b9616/`. The saved first failure and
affected-only rerun remain part of the integration evidence; they do not
alter the completed blocked experiment's attempt counts or verdict.
