# §471 planning smoke (seeds 74070450 A0, 74070451 A20)

Planning container, 2026-10-14 13:48Z, binary sha256 `6b2bca17…df4f` built from [CODE_COMMIT](CODE_COMMIT), through
`run_unit.sh`, both arms, one seed per unit.

| unit | rc | won | floor | end HP | seconds |
|---|---|---|---|---|---|
| base-a0-74070450 | 0 | 1 | 51 | 15/83 | 50.7 |
| end-a0-74070450 | 0 | 1 | 51 | 47/83 | 52.3 |
| base-a20-74070451 | 0 | 1 | 52 | 42/92 | 107.2 |
| end-a20-74070451 | 0 | 1 | 52 | 46/92 | 107.5 |

- The `.env` pairs differ only in `STS_SILVER_A20_BOSS_HEAL_FIX` and `STS_SILVER_FINAL_FIGHT_LEAF` (0 vs 1) and
  output paths; both arms set `NO_LOSS_POTION_CREDIT=0` and `RELIC_HEAL_LEAF=0`.
- The arms end with different HP on both seeds, so the options reach play.

Raw: `/mnt/project-files/silver-leaf-situational/smoke-471.tar` (sha256 `4d7a87e9765c66433a56db03b783724c4c9d767fa85c17417462d4c2a7b59d86`).
