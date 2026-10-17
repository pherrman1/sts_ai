# Shield and Spear: facing-aware rollout block check and tree reuse off (2026-10-17)

Evidence for the ledger entry "Shield and Spear rollout block check with worst-case facing, and tree reuse off"
in `docs/experiments/ledger-06.md`.

- States: the 32 recorded A20 Shield-and-Spear entry states of the A20 loss audit (`ss32.jsonl` in
  `/mnt/project-files/audit-2026-10-17/f1-act4replay/`), 3 copies each, 10,000 exact simulations per decision.
- Driver: `one_combat act4replay` (this branch, commit 36b61d62), via `tools/seed_guard.sh`.
  `battleSeed = offset + state*3 + copy`. Reruns at 36b61d62 reproduce exactly. At later main (after #625/#626) they
  reproduce only with `STS_SILVER_ROLLOUT_ROOT_TABLE=0 STS_SILVER_ROLLOUT_ACTION_CAP=0` added to the env below.
- Env (all arms): `STS_FAIR=1 STS_SILVER_SEARCH=1 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_REUSE_CAP_MODE=allocated
  STS_SILVER_ADAPTIVE=0 STS_SILVER_VNET_LEAF_DIRECT=0 STS_SILVER_LEARNED_STOP=0 STS_COLLECT_KEYS=1`.

| file | arm | seeds |
|---|---|---|
| `base_200.csv` | default (10k rows of the audit's `ss_budget.csv`) | 111130200–295 |
| `off_904.csv` | default, patched binary with the switch off | 111130904–999 |
| `on_904.csv`, `on_200.csv` | `STS_SILVER_ROLLOUT_SURROUNDED_FACING=1` | 111130904–999, 111130200–295 |
| `noreuse_904.csv`, `noreuse_200.csv` | tree reuse disabled (local hack, patch not preserved) | 111130904–999, 111130200–295 |
| `heart_base.csv` | Heart, default, 64 states × 3 copies at 10k and 30k (the audit's `heart_budget.csv`) | 111130000–191 |
| `heart_noreuse.csv` | Heart, tree reuse disabled, same states, copies and budgets | 111130000–191 |

`off_904.csv` matches the unpatched default on the same seeds row for row (96/96), so the patch changes nothing with
the switch off.

`facing_switch.patch` applies to 36b61d62 (pre-#625 main). It is not merged and not proposed. With the switch on,
Surrounded active and more than one monster alive, `SilverRolloutAgent::getIncomingDamage` returns the maximum over
the alive monsters of the incoming damage with the player facing that monster; otherwise it is unchanged.

HP lost counts the full entry HP for a death. Paired differences are per state (mean over its copies), with a 20,000
draw bootstrap over the 32 states (pooled: 6 copies per state).

Order: the 904 block ran first; the 200 block is the replication.
