# #347 prior cost on the R seeds (2026-10-07)

Plan: [PLAN.md](PLAN.md) (frozen after independent pre-run review). Ledger §392.

## Provenance and validity

- Binary: the §390 diagnostic build `1911f044`, SHA-256 `6fa4bf5c…7677`;
  `analyze.py` checks both against every entry. C rows are the frozen §390 rows.
- `run.sh` over `selection.json` (8 sources), 4 workers, 14:28–14:47 UTC.
- All 8 sources `VALID`. Every log shows the arm's `prior` and
  `root_selection`; the chest rule fired at every chest; planner seeds match C.

## Result (`analyze.py run ../ooc_counterfactual_347_20261007/run`, [report.json](report.json))

Wins of 8 boss replays per entry (fixed flat-10k Silver, shared planner seeds):

| seed | boss | F (§388) | C | CQ (root by Q) | CU (uniform prior) |
|---|---|---|---|---|---|
| 48000024 | a2 Champ | 8 | 2 | 7 | 8 |
| 48000014 | a3 Donu & Deca | 8 | 1 | 2 | 8 |
| 48000116 | a2 Champ | 8 | 0 | 0 | 0 |
| 48000095 | a3 Time Eater | 5 | 6 | 0 (died before boss) | 6 |
| total | | 29 | 9 | 9 | 22 |

- **CQ vs C:** net 0 (per seed +5, +1, 0, -6): `INCONCLUSIVE`. CQ died before
  the act-3 boss on 48000095.
- **CU vs C:** net +13 (per seed +6, +7, 0, 0): `INCONCLUSIVE` under the
  frozen rule (needs 3 of 4 seeds positive; two seeds are unchanged).

Entry state (from `report.json`): CU entered with smaller decks than C
(24/29/28/28 vs 30/37/29/40 cards), more max HP on all four, and more
upgrades on three. All arms still mostly leave chest relics (relics gained
after a forced chest: C 3 of 11, CQ 3 of 10, CU 5 of 12).

**Inference:** a uniform prior recovered most of the F-vs-C gap on two of four
entries and changed nothing on the other two; picking the root by Q did not
help. This points at the V4 prior's steering of the visit distribution, not
at the root choice rule. It does not by itself show that a new learned prior
would do better than no prior; the #430 rollout3 look (uniform 25/32 vs policy
22/32 on 51M seeds) points the same way and was also inconclusive. Four
selected seeds, one trajectory per arm.
