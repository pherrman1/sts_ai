# Settled Silver queue-item candidate: DEV pass, HOLDOUT correctness failure

- Baseline `main`: `8613f9c7811ce19a81cb731e78b6b58d01ec91ca`.
- Frozen candidate functional SHA: `44331fa511058250fee874f41057e9c59ae2daa1`.
- Release GCC binary SHA-256: baseline
  `6e4a635dce114970eb4aef6d303498da20588d1d3297abb3611c2f129defea64`,
  candidate `eca596fc92532ed26936bee909dbe9642dc10a1917e741c622e740e9ba3d276e`.
- Frozen DEV input SHA-256:
  `ab7c3298754864986c31273a0f1d23967b165fdd79a386261b680b8ad16d0eae`.
  Frozen HOLDOUT input SHA-256:
  `e8b914ad74ca0508ee6b1db329c5f454e92e7785cd60af1475d53b35a9d8af34`.
- All replays: Release GCC, `OMP_NUM_THREADS=4`, 1,000 simulations per
  decision, allocated reuse cap 32,768, adaptive/exact-lock/rho/internal FPU
  off. Each seeded command ran through `tools/seed_guard.sh`.

The first-decision seam returned 59 matched `ok` rows in each arm and five
`transactional_selection_required` rows in each arm (exit code 1). For the 59
paired roots, baseline versus candidate: nodes created 58,966 versus 58,912;
canonical hits 0 versus 7,763; summed search wall time 663,163.699 versus
645,642.076 microseconds; root visits 59,000 in both; selected edge visits
32,388 versus 32,068; first actions differed in 12/59. Retained node count
is not emitted by this seam. Wall time is a sequential local observation, not
a performance gate.

Changed paths versus baseline:

```text
EXPERIMENTS.md
apps/silver_hard_combat_replay.cpp
apps/silver_search_optimization_test.cpp
decisions/0016-silver-settled-queue-item-identity.md
decisions/README.md
docs/experiments/evidence/silver_queue_item_canonical_20260922/README.md
docs/experiments/evidence/silver_queue_item_canonical_20260922/baseline-dev.jsonl.gz
docs/experiments/evidence/silver_queue_item_canonical_20260922/baseline-first.jsonl.gz
docs/experiments/evidence/silver_queue_item_canonical_20260922/candidate-dev.jsonl.gz
docs/experiments/evidence/silver_queue_item_canonical_20260922/candidate-first.jsonl.gz
docs/experiments/evidence/silver_queue_item_canonical_20260922/candidate-holdout.jsonl.gz
docs/experiments/ledger-06.md
docs/knowledge-base/architecture/combat-search.md
include/sim/search/SilverBridge.h
third_party/silver_lightspeed/bridge/SilverStateBridge.cpp
third_party/silver_lightspeed/include/sim/search/BattleSearcher.h
third_party/silver_lightspeed/src/sim/search/BattleSearcher.cpp
```

DEV complete-fight replay returned 64/64 `ok`. Baseline versus candidate:
51 versus 52 wins; mean terminal HP fraction 0.3440911508 versus
0.3701368277; nodes/simulation 0.9246209677 versus 0.9203209877;
canonical hits 0 versus 325,595. Deterministic reroots were 1,287/1,287
versus 1,312/1,312, with zero candidate misses and zero positive-visit
selected edges without children. Stochastic sampled success was 340/881
versus 354/892; candidate misses were 541 versus 538. Cap fallbacks were zero.
All 64 action traces differed. Whole-combat node and outcome differences are
trajectory-confounded.

The one planned candidate HOLDOUT replay returned 63 `ok` rows and one
`replay_exception: selected_deterministic_state_mismatch` at case
`12100063/26`. The 63 completed cases had 49 wins and mean terminal HP
fraction 0.3674471462. The archive recorded 325,149 canonical hits across
all 64 rows, 1,091 successful deterministic attempts before the exception,
one failing deterministic attempt, 383 sampled stochastic successes among
912 attempts, 529 stochastic candidate misses, and zero cap fallbacks. The
failed row ended after three decisions, so it is not a terminal result.

The mismatch was at `CARD_SELECT` (`inputState=2`), with empty action/card
queues. The diagnostic reported equality for player, monsters, cards, RNG,
metadata, potions, and misc fields, identical hand UIDs and turn, and
`curCardQueueItem=0` (unequal). Its selected deterministic edge had 525 visits.
PR #285 intentionally kept all `CARD_SELECT` states exact, so the mismatch
correctly failed closed under that candidate's identity contract. The
`PLAYER_NORMAL`-only boundary and root-rewrite design were insufficient; this
candidate is not ready for default adoption. HOLDOUT is consumed. No second HOLDOUT run or
policy tuning was performed. The available diagnostic establishes a state
identity conflict; it does not establish whether the different historical
queue items change the selection's legal actions or downstream gameplay.

Raw archives use gzip with no stored filename or timestamp:

| Archive | SHA-256 |
| --- | --- |
| `baseline-first.jsonl.gz` | `e82b19107adc7c3dfbee7b7079451d7522692cecdf08307a90533b409e4fa67d` |
| `candidate-first.jsonl.gz` | `efe2d296ea58b0fdd95ed1582a53a79a0a8d32cf03fbfc9d2b9ac24414214852` |
| `baseline-dev.jsonl.gz` | `830f84a7ea11ac982697cd598f40b4679cd6568d94f02a329a38244d79f50b13` |
| `candidate-dev.jsonl.gz` | `ec8dadf589648c9ebcade48466f8aa4ee8826e9900be7f68ae740a6bada21e57` |
| `candidate-holdout.jsonl.gz` | `e03046aeb478e9c91e246504d5817b0f95ee212b1efa1c27e97f0343692312d6` |
