# Current-main V2 OOC MCTS confirmation

Source/baseline: `48fae0465c5eb83a21a2097c94747a9494bf941f`. Binary SHA256: `80f561e0db96548de2e2747393f9215354e2b7a56aab0cd3c460262b62c6338f`. V2 CTM SHA256: `22c855e0667a58a73835505672b0ae6d03f12e9fb8d64f08893810199246e94e`. Execution receipts bind every strategic/native model hash.

Fresh common seeds `12003000..12003031` were frozen before outcomes after a zero-match census. Excluded canaries `12002997..12002999` passed. All arms used Ironclad A0, fair RNG, exact-10k Silver real combat, allocated cap 32768, adaptive off, keys off, Act-3 stop, Searcher3/direct Silver leaf off, and 12 workers. V2 CTM was imagination-only.

| Arm | Wins | Floor | HP | Sec/game | Wall sec |
|---|---:|---:|---:|---:|---:|
| V4 | 24/32 | 48.375 | 47.063 | 38.855 | 123.413 |
| MCTS-512 | 22/32 | 48.281 | 34.656 | 50.888 | 156.320 |
| rollout3 | 28/32 | 50.875 | 57.813 | 4114.462 | 12860.034 |

MCTS-512 versus V4: -6.25pp, deterministic paired-bootstrap 95% CI [-28.125,+15.625]pp; discordance 6 versus 8, exact paired p=0.790527. **NO_CONFIRMATION**.

Rollout3 versus V4: +12.5pp, CI [-3.125,+28.125]pp; discordance 6 versus 2, exact p=0.2890625. **PROMISING_INCONCLUSIVE**. Rollout3 is 105.89x V4 elapsed time.

Descriptive rollout3 versus MCTS-512: +18.75pp, CI [+6.25,+34.375]pp; discordance 6 versus 0, exact p=0.03125; 80.85x elapsed time.

MCTS-512 telemetry: 5,574 OOC decisions; 4,554 MCTS-owned; 1,020 fallbacks (18.299%); 1,187,342 completed simulations; 1,144,681 saved; 1,187,351 attempts; 102,443 successful CTM samples (3,201/game); 9 unsupported/support aborts; max depth 15; zero continuation-limit aborts; 353.345s OOC MCTS wall time.

Rollout3 telemetry: 6,032 OOC decisions; 4,693 MCTS-owned; 1,339 fallbacks (22.198%); 4,826,781 completed simulations; 4,807,308 saved; 4,826,970 attempts; 13,913,281 successful CTM samples (434,790/game); 189 unsupported/support aborts; max depth 18; zero continuation-limit aborts; 130,153.697s summed per-game OOC MCTS wall time.

`analyze.py` rejects seed, provenance/config, trace/support, backend/cap, bridge and accounting drift and uses frozen seed `20260915` for 200,000 resamples. Raw evidence is under `raw/`; `sha256-index.json` binds the packet.

Final conclusion: MCTS-512 does not deserve a larger confirmation. Rollout3 alone deserves consideration for one, but is not deployment-qualified and its roughly 106x V4 cost should first be reduced or explicitly accepted.

Knowledge impact: experiment evidence and current research status only; no gameplay, model, default, support or RNG contract changed.
