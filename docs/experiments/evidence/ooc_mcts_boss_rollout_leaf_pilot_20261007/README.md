# OOC MCTS boss-rollout leaf pilot (ledger §391, PR #430)

**Request (Philipp, 2026-10-07):** 32 seeds of OOC MCTS with no prior, the current
CTM DeepSets stack, and a leaf that is not a model: roll out with V4 decisions and
CTM fights until the current act's boss, back up 1 for a win and 0 for a loss.

## Frozen candidate

- Source `1954f100cbd2be7a243cd8c99caeacea7b09e0a8` (baseline main `04e59c53`),
  independently reviewed (two findings fixed: target the next boss after the
  searched decision; do not count a new act's start as past its boss).
- `one_combat` Release sha256 `ecb2078198ebf9b48d9051c84ba84c56a9e4292b3222de4bb16698291c245a50`,
  built independently in four cloud containers; `run.sh` refuses any other hash.
- Models: tracked `selfplay/models/ooc_strategic_tok_final.native` (V4),
  default CTM stack (`combat_transition_deepsets_lizard_t2.native` + Brew fallback
  `combat_transition_near_full_except_smoke_v2.native`, active Lizard correction),
  `models/candidates/v_win_x2b_trees.txt` (campfire/continuation only).
- Environment: `run.sh` (#417 `mcts` arm base, exact-10k Silver, learned stop off,
  act-3 stop, fair RNG, keys off) with `STS_OOC_MCTS_PRIOR=uniform`,
  `STS_OOC_MCTS_SIMS=2048`, `STS_OOC_MCTS_LEAF_VALUE=bossrollout`.
- Seeds 51000000–51000031, one process per seed, one CPU each. Seeds 000–007 ran
  in the PR thread; 008–015, 016–023, 024–031 in three extra cloud threads
  (Philipp's split). All 32 `executableGitSha` sidecars name `1954f100`; all 32
  logs end `exit 0` and print `prior=uniform … leaf_value=bossrollout`.

## Result (`report.txt`, `analyze.py run`)

| | wins | Wilson 95% | mean floor | s/game (mean / median / max) |
|---|---|---|---|---|
| boss-rollout leaf (this run) | 9/32 (28.1%) | 16–45% | 38.2 | 1,297 / 1,009 / 4,055 |
| rollout3 look, no prior (local, main `46153506`) | 25/32 (78.1%) | 61–89% | 49.6 | 1,099 / 941 / 2,940 |

Loss floors: 21, 23, 23, 24, 24, 25, 25, 30 (eight act-2 hallway deaths),
33 ×10 (act-2 boss), 41, 46, 50, 50, 50. rollout3's seven losses: 27, 40, 44,
50, 50, 50, 50.

MCTS owned 3,206 decisions, 68 root boundaries, 1 root abort
(`active_unqualified_lizard` in-tree). Inside rollouts the CTM's active-Lizard
boundary fired 9,600 times and the tail was spent there.

Chests and campfires chosen by OOC MCTS (all 32 runs): chests opened 58, left 22;
campfires: upgrade 141, rest 65, ruby key 5 (keys are off, so wasted).

## Caveats

- rollout3 ran before #424/#427 and locally; per-seed pairing is not available
  here, so the comparison is unpaired and descriptive. The 50 pp gap is far
  outside both intervals.
- Rollouts score only boss survival, not HP or resources left after it.
- The spent-tail retry makes rollouts with an active Lizard Tail pessimistic.

`run/` holds every per-seed CSV, bench sidecar, log, MCTS action and support trace.
