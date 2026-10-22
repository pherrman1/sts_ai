# STS_OOC_MCTS_LEAF_HEART1_VALUE_WEIGHT: smoke and flag-off identity (2026-10-22)

Binaries: this branch at `955ab99f` (`one_combat` sha256 `353ca004…`) and main `4de6c3fe` (`0e961f90…`), both
`linux-gcc-release` in the cloud. Seed 111144995 (value-head block), `heartoutcomegen 1 SEED OUT policy` with the
§621 arm-A environment ([tools/smoke_run.sh](tools/smoke_run.sh): student_sel prior `cf6bf7fb…`, learned Silver
stop, fast-root cap 1024) except `STS_OOC_MCTS_SIMS=256` and `STS_OOC_MCTS_LEARNED_STOP=0` to keep each run near
4 minutes. Head: M0.3 s0 (`ee8337a2…`). `STS_OOC_MCTS_TRACE` on.

| run | binary | leaf | rc | wall s | outcome | heart1 value leaf evaluations / fallbacks |
|---|---|---|---|---|---|---|
| q-main-off | main | X2-B | 0 | 269 | act 4, floor 56 | 0 / 0 |
| q-new-off | branch | X2-B | 0 | 271 | act 4, floor 56 | 0 / 0 |
| q-main-head | main | head alone | 0 | 185 | act 3, floor 50 | 10,873 / 0 |
| q-new-head | branch | head alone | 0 | 188 | act 3, floor 50 | 10,873 / 0 |
| q-new-w1 | branch | head, `_WEIGHT=1` | 0 | 188 | act 3, floor 50 | 10,873 / 0 |
| q-new-blend015 | branch | blend, `_WEIGHT=0.15` | 0 | 258 | act 3, floor 50 | 9,947 / 0 |

- **Identity:** q-main-off vs q-new-off and q-main-head vs q-new-head: all decision and outcome lines of the policy
  JSONL identical (394 and 367 lines); the header differs only in its own CTM file name; CTM rows, trace actions and
  support trace identical; the summary trace differs only in `mctsWallSec`/`mctsCpuSec`. q-new-w1 equals q-new-head
  the same way; its header also records `STS_OOC_MCTS_LEAF_HEART1_VALUE_WEIGHT=1` in `policy.ooc_mcts.environment`.
- **Blend:** banner `leaf_heart1_value=… leaf_heart1_value_weight=0.150000`, config `"leafHeart1ValueWeight":0.150000`;
  footer `complete` and `integrityPassed` (all six runs). One seed, so the outcomes say nothing about strength.
- **Startup checks** (rc 1, `[live OOC MCTS startup failure]`): `_WEIGHT=0`, `1.5`, `0.1x` and empty give "must be in
  (0, 1]"; `_WEIGHT=0.15` without `STS_OOC_MCTS_LEAF_HEART1_VALUE` gives "requires STS_OOC_MCTS_LEAF_HEART1_VALUE".
- At the full §621 configuration (4096 simulations, learned OOC stop 0.99) only the banner was checked (`run` mode);
  the A/B's frozen smoke covers that configuration.
