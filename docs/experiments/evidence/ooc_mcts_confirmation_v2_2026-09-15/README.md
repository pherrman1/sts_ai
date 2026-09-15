# Current-main V2 OOC MCTS confirmation

Source/baseline: `48fae0465c5eb83a21a2097c94747a9494bf941f`. Binary SHA256: `80f561e0db96548de2e2747393f9215354e2b7a56aab0cd3c460262b62c6338f`. V2 CTM SHA256: `22c855e0667a58a73835505672b0ae6d03f12e9fb8d64f08893810199246e94e`. Execution receipts bind every strategic/native model hash.

Fresh common seeds `12003000..12003031` were frozen before outcomes after a zero-match census. Excluded canaries `12002997..12002999` passed. All arms used Ironclad A0, fair RNG, exact-10k Silver real combat, allocated cap 32768, adaptive off, keys off, Act-3 stop, Searcher3/direct Silver leaf off, and 12 workers. V2 CTM was imagination-only.

| Arm | Wins | Floor | HP | Sec/game | Wall sec |
|---|---:|---:|---:|---:|---:|
| V4 | 24/32 | 48.375 | 47.063 | 38.855 | 123.413 |
| MCTS-512 | 22/32 | 48.281 | 34.656 | 50.888 | 156.320 |
| MCTS-2048 rollout0 | 26/32 | 49.188 | 43.531 | 75.356 | 225.175 |
| MCTS-2048 rollout1 | 26/32 | 49.844 | 42.469 | 1747.333 | 5458.124 |
| rollout3 | 28/32 | 50.875 | 57.813 | 4114.462 | 12860.034 |

MCTS-512 versus V4: -6.25pp, deterministic paired-bootstrap 95% CI [-28.125,+15.625]pp; discordance 6 versus 8, exact paired p=0.790527. **NO_CONFIRMATION**.

Rollout3 versus V4: +12.5pp, CI [-3.125,+28.125]pp; discordance 6 versus 2, exact p=0.2890625. **PROMISING_INCONCLUSIVE**. Rollout3 is 105.89x V4 elapsed time.

Descriptive rollout3 versus MCTS-512: +18.75pp, CI [+6.25,+34.375]pp; discordance 6 versus 0, exact p=0.03125; 80.85x elapsed time.

At fixed 2048 simulations, rollout0 and rollout1 both won 26/32. Rollout0 versus V4 is +6.25pp, CI [-12.5,+25.0]pp (6 versus 4 discordant wins; p=0.753906). Rollout1 versus V4 is +6.25pp, CI [-9.375,+25.0]pp (5 versus 3; p=0.7265625). Rollout1 versus rollout0 is 0pp, CI [-18.75,+18.75]pp (4 versus 4; p=1). Rollout3 versus rollout1 is +6.25pp, CI [-6.25,+18.75]pp (3 versus 1; p=0.625). Thus the extra one-combat rollout produced no point-estimate gain over rollout0 while costing 23.19x as much; rollout3 produced only +6.25pp over rollout1 while costing 2.35x as much.

MCTS-2048 rollout0 telemetry: 5,717 OOC decisions; 4,637 MCTS-owned; 1,080 fallbacks (18.891%); 4,816,529 completed simulations; 4,682,504 saved; 4,816,548 attempts; 256,859 successful CTM samples (8,027/game); 19 unsupported/support aborts; max depth 21; zero continuation-limit aborts; 1,025.283s OOC MCTS wall time.

MCTS-2048 rollout1 telemetry: 5,849 OOC decisions; 4,654 MCTS-owned; 1,195 fallbacks (20.431%); 4,780,171 completed simulations; 4,760,887 saved; 4,780,264 attempts; 5,011,692 successful CTM samples (156,615/game); 93 unsupported/support aborts; max depth 22; zero continuation-limit aborts; 54,202.975s OOC MCTS wall time.

MCTS-512 telemetry: 5,574 OOC decisions; 4,554 MCTS-owned; 1,020 fallbacks (18.299%); 1,187,342 completed simulations; 1,144,681 saved; 1,187,351 attempts; 102,443 successful CTM samples (3,201/game); 9 unsupported/support aborts; max depth 15; zero continuation-limit aborts; 353.345s OOC MCTS wall time.

Rollout3 telemetry: 6,032 OOC decisions; 4,693 MCTS-owned; 1,339 fallbacks (22.198%); 4,826,781 completed simulations; 4,807,308 saved; 4,826,970 attempts; 13,913,281 successful CTM samples (434,790/game); 189 unsupported/support aborts; max depth 18; zero continuation-limit aborts; 130,153.697s summed per-game OOC MCTS wall time.

`analyze.py` rejects seed, provenance/config, trace/support, backend/cap, bridge and accounting drift and uses frozen seed `20260915` for 200,000 resamples. Raw evidence is under `raw/`; `sha256-index.json` binds the packet.

Final conclusion: MCTS-512 does not deserve a larger confirmation. At 2048 simulations, rollout0 and rollout1 are equally promising/inconclusive versus V4, but rollout1 buys no observed wins for 23.19x rollout0 cost. Rollout3 remains the point-estimate leader, but its +6.25pp over rollout1 is inconclusive and costs another 2.35x. If any arm receives a larger confirmation, rollout0 is the practical candidate; rollout3 is only a high-cost research candidate. None is deployment-qualified.

Knowledge impact: experiment evidence and current research status only; no gameplay, model, default, support or RNG contract changed.
