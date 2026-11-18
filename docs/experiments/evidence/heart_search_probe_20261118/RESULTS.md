# Heart search probe (2026-11-18)

Question (Philipp 2026-11-18 18:50 CET, "Im Herz mehr Suche geben?"): with the current Stage 1 self-play net, does a
larger search budget in the Heart fight deal more damage or kill the Heart?

- Code: commit 312afd7291e038ecd64cf202b642be871315ff63 (main b8ac707d + `selfplay.py --heart-arms / --heart-reps`).
- Net: `~/Documents/sts/stage1/amber_scratch/ckpt_218026.pt` (step 218,026, 1,221,582 runs; the amber_scratch run was
  paused 19:44-20:01 CET for this and resumed from the same checkpoint). Loaded with `--init-net`, frozen (0 training
  steps, `--keep-full 0`).
- PC (RTX 3060 Ti), 19:44:42-20:00:49 CET, exit 0. Seeds 150100000-150101999 (2,000 runs, A0, the self-play flags of
  amber_scratch incl. `--force-keys curriculum --full-candidates 8 --explore-amber`).
- Every run that reached the Heart (795 of 2,000) stored the fight's start state; the fight was played once per arm from
  that state (same game RNG at the fight's start). Arms (full sims : fast sims : full prob : m full : m fast):
  0 = 64:16:0.25:8:4 (self-play), 1 = 64:64:1:8:4, 2 = 256:256:1:8:4, 3 = 1024:1024:1:8:4.
- `heart_probe.jsonl` (3,180 plays, sha256 fe20e603541ba9339927c9e6f1d9951e61af32a624c894801bf5d3ce45b1f16f),
  `report.json` = `python3 tools/az_bench/heart_probe_report.py heart_probe.jsonl --arms ...`, `final_metrics.json`
  = the probe's last metrics line.

| Arm | Mean damage (of 750) | Median | Paired diff vs arm 0 [95 % bootstrap] | Kills | Mean turns |
|---|---|---|---|---|---|
| 64/16 p 0.25 | 49.8 | 40 | – | 0/795 | 2.38 |
| 64 full | 57.3 | 48 | +7.5 [+5.0, +10.2] | 0/795 | 2.40 |
| 256 full | 63.6 | 51 | +13.8 [+10.7, +16.8] | 0/795 | 2.36 |
| 1024 full | 65.3 | 54 | +15.5 [+12.6, +18.6] | 0/795 | 2.34 |

No stalls. Heart entry: player HP 51.0 of 93.8 max (54 %), deck 36.4 cards, 10.2 relics. Fight length (bc.turn at the
end, arm 0): 1 = 236, 2 = 323, 4 = 164, 5 = 47; the player dies in the Heart's first big attacks in nearly every play.
Damage by entry-HP tercile (arms 0 / 1 / 2 / 3): < 41 HP 39.9 / 40.7 / 44.5 / 43.0; 41-57 HP 47.2 / 53.5 / 59.5 / 61.9;
>= 57 HP 61.5 / 76.3 / 85.1 / 89.1.
