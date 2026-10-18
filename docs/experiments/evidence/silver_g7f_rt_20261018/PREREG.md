# Gen-7f vs g6_E as Silver prior and rollout root table: held-out Act-4 A/B at 2.5k (pre-registered 2026-10-18 ~15:00Z, before any A/B fight)

Philipp asked "can you still make gen 7 the prior?" (13:41Z) and chose "Retrain, then swap" on the card (13:44Z). The
card said: retrain on the active power features, run a short root-table check, then a default-switch PR. Ledger:
part of §517 (gen-7 prior).

## Question
g7f_E is gen 7 retrained on active power features (`combat_policy_mlp_g7f_E.txt`, sha c45dcc0a, data branch
`claude/silver-gen7-act4-data` 0168b72d; gate and parity passed). Using one model in both roles, as the A20 run
configs do (root and tree prior via `STS_SILVER_ROOT_PRIOR`, and the default rollout root table): does g7f_E win more
held-out A20 Act-4 fights than g6_E (ca9bd7f2), or fewer?

## Design
- States: the same 1,094 held-out fold-4 states as the earlier gen-7 A/Bs (sha 549bd8f5; 586 S&S, 508 Heart, 586 source
  runs). Fold 4 is held out of g7f_E's training too (same folds).
- Both arms: `silverazact4gen` on code 8c03d1df (main 05da2c07 + the generator), 2.5k sims, flat exact root budgets,
  tree prior K=8 weight 400, root bonus off, learned stop off, `STS_ACTIVE_POWER_FEATURES=1`, 8 copies per state.
  Arm A: g6_E as prior and `STS_SILVER_ROLLOUT_ROOT_TABLE`. Arm B: g7f_E in both roles. Nothing else differs.
  `run_unit.sh` fails a unit unless its log shows the root table loaded from that arm's model.
- Seeds: state i uses seed 111178200 + i in both arms (paired). Block 111178200-111179293; smoke used 111178195.
  8,752 pairs.
- Campaign: `tools/cloud/worker.sh`, 8 workers, 88 units, arm-major `units.txt` (every worker runs both arms).

## Outcome and decision rule (fixed now)
Same as `../silver_gen7_ab25_20261018/PREREG.md` (`analyze.py` copied unchanged). Primary: paired dWin = B - A, 95%
cluster bootstrap over source runs. **SHOWN** if the lower bound > 0, **HARM** if the upper bound < 0, else
**NOT_SHOWN**.
- Switch rule (stated on the card): unless the result is HARM, the default-switch PR follows. It makes g7f_E the
  bundled default root table model, and the g6_E path restores the old table. Merging stays Philipp's call. HARM: no
  switch, and the result goes to Philipp.
- Validity: as the 2.5k A/B. All 88 units rc=0 and verified, with no unpaired fights and no invalid pairs.

## Limits
Act-4 fights only. The other acts' roots changed only through the feature retrain (offline fold-4 CE: orig 1.1731 vs
g7_E 1.1750). There is no CPU difference between the arms (same network size).
