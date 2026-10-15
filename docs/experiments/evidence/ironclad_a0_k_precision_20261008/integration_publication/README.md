# Publication checkout integration

**Result: `FOCUSED_PUBLICATION_INTEGRATION_PASS`.** Source
`0734f3d1ef2aa76c2c1a7026f9dafbb52464587e` configured and built successfully in
the separate publication checkout. All **27 selected CTests passed in one
invocation, with no skips**, followed by a passing existing bounded
`combat_knowledge_neutrality_test` fixture. No repair or source change was
needed during these publication checks.

The publication checkout is
`/home/philippherrmann/.codex/worktrees/ironclad-research-handoff-20261008/sts_lightspeed`
(P). The preserved research checkout remains
`/home/philippherrmann/.codex/worktrees/ironclad-overnight-20261008/sts_lightspeed`
(R), detached at `08863cc6547ca0c9d51e08482f6bd7aafab37a92`. All writes from
these checks went to P's build and integration-evidence directories. R was
read only for identity verification.

## Commands and checks

[Configure receipt](configure_receipt.json), [build receipt](build_receipt.json),
[CTest receipt](ctest_receipt.json), and
[observer-neutrality receipt](combat_knowledge_neutrality_receipt.json) preserve
the exact argument arrays, environments, exits, timestamps and raw-log hashes.
All four commands exited 0. The clean Debug build used six compiler jobs:

```sh
/home/philippherrmann/.local/bin/cmake --preset linux-gcc-debug
/home/philippherrmann/.local/bin/cmake --build build/linux-gcc-debug -j6 --target \
  one_combat unit-test silver-public-pair-probe combat-knowledge-neutrality-test \
  rest_recall_filter_test full_hp_rest_filter_test remove_obtain_weight_test \
  native_ooc_card_win_rank_test native_ooc_shop_features_test \
  test_ooc_public_futures combat_transition_runtime_probe
```

CTest ran through `bash tools/seed_guard.sh` using the absolute installed CTest
path, `--test-dir build/linux-gcc-debug --output-on-failure -j2 --timeout 180`,
and the exact anchored 27-name regex recorded in its receipt. It wrote the
separate `publication-0734f3d1/ctest.xml`; elapsed CTest time was 75.51 seconds.

| Coverage | Passing CTests |
|---|---:|
| Public-future, shop, Recall, full-HP REST, removal and card-ranking fixtures | 6 |
| Silver searcher/wire/semantic actions, combat knowledge and E2C observer scope | 5 |
| CTM escape/capability/Lizard synthetic checks and native contract/runtime loaders | 9 |
| OOC MCTS adapter and CTM offline score rows | 2 |
| GEN2 policy/producer and teacher/learned-stop contracts | 4 |
| E3 synthetic self-test | 1 |
| **Total** | **27** |

The existing observer-neutrality fixture ran separately through the seed guard:

```sh
bash tools/seed_guard.sh build/linux-gcc-debug/combat_knowledge_neutrality_test
```

The new upstream leaf-sampling and root-prior fixtures are inside
`silver_searcher`; they establish the tested sampling neutrality, zero-weight
prior neutrality and favored-edge behavior. This evidence does not claim that
a nonzero uniform root prior is neutral. The public pair probe compiled, but
no bound SPEC, canary or evaluation mode was executed. No `silversynthgen`
collection, synthetic replay corpus or experimental game cohort was run.

The runtime reused `/usr/bin/python3` 3.12.3, NumPy 2.5.1, Pandas 3.0.5 and
PyTorch 2.5.1+cu121. No dependency was installed. CUDA visibility was empty;
OMP/OpenBLAS/MKL threads were each 1. Inherited `STS_*` settings were removed
before registered CTest settings applied. Temporary files and bytecode stayed
under P's build directory. The C++20 standalone-fixture repair already present
in the publication source passed here without further modification.

## Publication identity and preserved research identity

[PUBLICATION_INTEGRATION_RESULT.json](PUBLICATION_INTEGRATION_RESULT.json),
SHA256 `55626b5c1417ad5832a3511fcddb65b0a57c90dde4c0c2c1cee52999a0c2f39c`,
binds all four receipts, all 27 individual outcomes, eleven built executables,
affected source hashes and the post-check frozen-artifact verification.

The publication Debug `one_combat` SHA256 is
`1190fb1f7d52a83789e5cd3c2ff14fde8d8c79d2f277cdbfc34b539446fe1213`.
This is a new executable identity. It does not inherit gameplay qualification
from the frozen GEN2 producer or the earlier RemoveLow confirmation binary.

Frozen identities were resolved using **`freeze.root`, which points to R**,
not by substituting P for the original directory. All 21 frozen artifact-map
entries and separately bound producer/teacher files matched: **23 unique files
unchanged**. The policy was already in the artifact map. In particular:

| Seed guard | SHA256 |
|---|---|
| Frozen R | `764f071ef7a7f8c30367641904a9c24ba807189b3197aadccca2b6b53eb6bd06` |
| Publication P, including the upstream synthetic-mode addition | `4506d4495283d5b59c037e5f95d2299af39d54db07e8a2300c6135ced9271ca6` |

The original freeze was not changed to use P's newer guard. Its frozen binary
directories, closed confirmation results and protected TEST were untouched.
Raw publication logs/JUnit are under
`P/build/linux-gcc-debug/publication-0734f3d1/`.

These local integration checks do not constitute an efficacy analysis or an
authoritative GitHub `Linux GCC` CI pass. The K-precision primary remains
**`EXECUTION_BLOCKED`**. The earlier integration attempts at source `61b9616`
remain preserved separately, including their repaired test harness failure.
