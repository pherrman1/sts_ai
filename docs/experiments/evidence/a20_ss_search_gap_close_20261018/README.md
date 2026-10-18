# Shield and Spear search gap vs heart1: last probes and closure (2026-10-18)

Evidence for the ledger entry "Shield and Spear search gap vs heart1's engine: line closed" in
`docs/experiments/ledger-06.md`. Same 32 recorded A20 Shield-and-Spear entry states as §528, 3 copies each, 10,000
exact sims, `one_combat act4replay` via `tools/seed_guard.sh`, two paired seed blocks (111130904–999 first,
111130200–295 replication). Binaries: `t*` at 07362d02 (main c196d8e6 merged), `c1` at 40d71721 (main after #647), each with a local
switch, default off.

Env (all arms): `STS_FAIR=1 STS_SILVER_SEARCH=1 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_REUSE_CAP_MODE=allocated
STS_SILVER_ADAPTIVE=0 STS_SILVER_VNET_LEAF_DIRECT=0 STS_SILVER_LEARNED_STOP=0 STS_COLLECT_KEYS=1`.

| file | arm |
|---|---|
| `t0_*.csv` | default |
| `t1_*.csv` | `STS_SILVER_ROLLOUT_SURROUNDED_TARGET=1`: rollout attacks keep the faced monster under Surrounded |
| `t2_*.csv` | `STS_SILVER_ROLLOUT_SURROUNDED_TARGET=2`: rollout attacks the monster with the larger frontal intent |
| `c1_*.csv` | `AUDIT_CLAIRVOYANT_ROOT=1`: the search root is the live state (true draw order, rolled intents) |

Patches (not merged, not proposed): `surrounded_target.patch`, `clairvoyant_root.patch` (that binary without the env
reproduced the `t0` outcomes, won and final HP, on all 192 fights), `pile_stats100.patch` (counts root draw-pile observations).

heart1-engine comparison rows (9 copies per state) are on the share:
`/mnt/project-files/audit-2026-10-17/f1-act4replay/heart1-engine/h1_ss_10k.csv` and `h1_ss_more.csv`.
HP lost counts the full entry HP for a death; paired differences are per state with a 20,000-draw bootstrap.
