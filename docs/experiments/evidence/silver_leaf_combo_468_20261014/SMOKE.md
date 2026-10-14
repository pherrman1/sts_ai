# §468 planning smoke (seeds 74070100 A0, 74070101 A20)

Planning container, 2026-10-14 11:25Z, binary sha256 `a45ef01e…b49e` built from [CODE_COMMIT](CODE_COMMIT), through
`run_unit.sh`, both arms, one seed per unit.

| unit | rc | won | floor | end HP | seconds |
|---|---|---|---|---|---|
| base-a0-74070100 | 0 | 1 | 51 | 130/139 | 47.1 |
| all-a0-74070100 | 0 | 1 | 51 | 114/135 | 46.6 |
| base-a20-74070101 | 0 | 0 | 33 | 0/85 | 30.5 |
| all-a20-74070101 | 0 | 0 | 23 | 0/83 | 27.6 |

- Each `.env` pair differs only in the four leaf options (base all 0, all all 1) and output paths.
- The arms' runs diverge on both seeds (different end HP / death floor), so the options reach play.
- Cost: about 47 s per A0 run and 30 s per A20 run on one core.

Raw: `/mnt/project-files/silver-leaf-situational/smoke-468.tar` (sha256 `de5bc88cc25497a3351e3adebcc63c87460e256955f027f77ef01a29fea53236`).
