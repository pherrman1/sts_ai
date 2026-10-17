# Controlled A0 Ritual coverage pilot v2 (scaled sources) — result (2026-10-17)

**Classification: `PILOT_COVERAGE_INCONCLUSIVE`**, but only because of the
four **Smoke** cells. All eight natural/Brew cells meet every preregistered
threshold in both TRAIN and VALIDATION.

## Frozen packet

- Source `5e282b6c3e063b9346d0af9d7e8ab1e83bdc4eee`, `--packet v2`; executable SHA-256
  `d02d4a1da1081b1dd3190f1eddacb7cc1f6b350fa02cd39ca3e93662b423da0b` (unchanged from v1).
- Recipe SHA-256 `8939d754d0970b4fbe236da6a6b58e52e417a166e2cffd6000ea2b75fa69ab9d`; 40 TRAIN + 20 VALIDATION
  sources disjoint from v1 × 12 cells = 720 units ([PROTOCOL.md](PROTOCOL.md)).
- Independent read-only review PASS ([review.json](review.json)); Philipp's approval in
  [resource-approval.json](resource-approval.json).

## Result ([result-summary.json](result-summary.json))

- 720/720 units valid, no stop, 1,306 s wall on eight workers.
- 2,906 Writhing targets (FAST 1,932, STANDARD 974); 2,876 victories, 30 escapes;
  106 targets excluded as `active_tail_without_bloom`.
- **175/2,906 targets (6.0%) show positive permanent Dagger growth.**
- Positive source groups per cell (TRAIN / VALIDATION; thresholds 3 / 2):

| Cell | natural | brew | smoke |
|---|---|---|---|
| base single | 8 / 3 | 4 / 4 | **1 / 1** |
| base double | 12 / 5 | 13 / 8 | **0** / 4 |
| upgraded single | 6 / 4 | 4 / 4 | **0 / 1** |
| upgraded double | 9 / 5 | 13 / 8 | **1** / 3 |

- The only six missing coverage entries are `cellPositive` for the Smoke cells
  (4 TRAIN, 2 VALIDATION). `actualRoutePositive`, `doubleOrdinalPositive`,
  `cellTargets` and named potion-use coverage are all met.
- Raw rows and the full unit ledger (467M) stay local under
  `build/ritual-coverage-pilot-v2-20261017/` (`result.json` SHA-256 `64039b583546e256b11da19a7bedb5a5fa56cb7f435a3315291485a589ff407e`,
  `freeze.json` `e9b2d2c066f11e5b2ffd17bebd4b3b15394f0dd60c7c422d0980c706dc513cd5`, `unit-ledger.json` `7e5c586c6ac7b0f7461174a7d4c0ef82a155ec2bcdef5983a350b6608b897f87`).

## Interpretation

Scaling sources fixed the v1 shortfall for natural and Brew belts: positive
Dagger growth is ~6% per fight and now replicates across many independent
TRAIN and VALIDATION sources. A forced Smoke Bomb in the belt almost
suppresses Dagger growth; why (escape choice, or Silver playing differently
with an escape option) is not established here. Per the protocol this licenses
nothing by itself: no fit, qualification or support change was made. A
reviewed Ritual-only fit could be designed for the non-Smoke cells, with
Smoke-holding Writhing states kept excluded or studied separately.
