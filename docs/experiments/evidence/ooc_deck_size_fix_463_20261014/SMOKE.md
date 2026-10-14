# §463 planning smoke (seeds 74063000–74063001)

Run in the planning container on 2026-10-14 with the frozen binary (sha256 `b4586cfc…95e1`, built from
[CODE_COMMIT](CODE_COMMIT)) through `run_unit.sh`, both arms, one seed per unit.

| unit | rc | won | floor | end HP | seconds |
|---|---|---|---|---|---|
| fixon-74063000 | 0 | 1 | 51 | 77/85 | 607 |
| fixoff-74063000 | 0 | 1 | 51 | 37/124 | 680 |
| fixon-74063001 | 0 | 1 | 51 | 35/85 | 446 |
| fixoff-74063001 | 0 | 1 | 51 | 35/85 | 450 |

- The two units of seed 74063000 were first stopped by the planning container's background time limit and moved
  to `out/aborted-20261014T064817Z/` by `run_unit.sh`, then rerun whole (this exercises the restart path).
- The `.env` files of an arm pair differ only in `STS_OOC_SHOP_DECK_SIZE_FIX` and the output paths.
- `[native OOC shop deck-size correction ON]` appears in both `fixon` logs and in neither `fixoff` log; every log
  shows `"simulations":4096` and `"leafCombats":3`; no `rollout_shop=greedy`.
- The arms' decision traces first differ at line 25 (74063000) and line 99 (74063001).
- `analyze_ooc_deck_size_463.py` reads both arms (2 runs each); the label is INVALID as expected for non-cohort seeds.

Raw: `/mnt/project-files/ooc-deck-size-463/planning-smoke-463.tar` (sha256 `1e0a5d546215d42dc51ed960560faa787e7e87a4e58098da927451034e93feaf`).
