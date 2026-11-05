# Counters-only campaign (§757 follow-up)

PREREG: [PREREG.md](PREREG.md). Code: `STS_SILVER_PRICE_TABLE_LEAF=a746:counters` (this PR). States, seeds and Silver:
stage C's (`../stagec/`). Control: stage C's D/T/I runs (share `price-table-stagec/units/`), checked by 32 sentinel
D units.

## Smoke (author container, Release build of the same code, not part of the result)
Units `424 S`, `424 C`, `603 C`, three at once: rc 0, 208 / 167 / 306 s wall; C logs "… counters only"; the sentinel's
4 D rows equal stage C's (v3 binary `4ace2751…`) except the CPU columns; `analyze.py` on them: 0 bad rows, 0 dropped.
