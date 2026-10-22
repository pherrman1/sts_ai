# Leaf head with a per-turn penalty on exact first fights (pre-registered, 2026-10-22)

Thread "Exact combat solving research" (leaf evaluation for Silver). Philipp 2026-10-22 21:58Z: "couldnt we try head
with a small turn punish score so it cant stall?". Fresh seeds from the coordinator (21:57Z): 111333000-111333099.

## Why

The silver-leaf-a20 head (`../silver_leaf_a20_data_20261022`: frozen g7f_E trunk, 128 -> 64 -> 1, trained on 736k A20
roots with Silver's own end score) failed its pre-registered first-fight test on the held-out replays 111149650-699:

| config | head alone | 50/50 head-playout blend |
|---|---|---|
| prod (regret per fight 0.872 with the playout) | +6.34 ± 2.29 | −0.438 ± 0.082 |
| prod@mb=4 (0.497) | +24.37 ± 7.88 | −0.254 ± 0.066 (Two Louse +0.114 ± 0.060) |

The head alone stalls: in Two Louse it keeps the last louse alive until the solver's turn cap, which scores the fight
as a loss. A win now is scored exactly by Silver's end evaluation, while every continuing leaf gets the head's value,
which runs a few points high on such states; nothing prices the extra turns. The blend passed both pooled bars but
missed the encounter cap (+0.10) in Two Louse with max backup.

## Change

`exact_combat_solver --leaf-oracles`: a suffix `/P` on `head:NAME` or `hblend:NAME:L` takes P points off the head's
value for every turn the leaf lies beyond the root (`turn(leaf) - turn(root)`), before any blend. Without the suffix
(or with `/0`) every row is unchanged: on Two Louse 111149670-672, configs prod and prod@mb=4, modes none, head:a20 and
hblend:a20:0.5 give rows identical to the test's solver binary (sha256 26806283...), and `/0` equals no suffix.

Heads: `a20` = `/mnt/project-files/exact-combat-research/leaf-value/heads/a20.txt` (sha256 049d08a2...), the
silver-leaf-a20 head; `ct` = `heads/ct.txt` (sha256 5a4a2209...), the capacity-test head (trained on exact values of
search leaves of 111149600-649).

## Tuning (seeds that never tested the a20 head)

Replays 111149600-649 (Cultist, Two Louse, Jaw Worm; 150 fights), configs prod and prod@mb=4,
`run_tp.sh BIN OUT tune 111149600 50 2 MODES a20=heads/a20.txt` with MODES = none plus the 10 candidates
`head:a20/P` and `hblend:a20:0.5/P` for P in {0, 1, 2, 4, 8} (P = 0 written without the suffix). The a20 head never
saw these fights; they trained the ct head only.

Selection (`select_tp.py`, from `analyze_oracle.py`'s JSON): the candidate with the lowest mean of its pooled paired
change against the playout (none) in prod and in prod@mb=4, among the candidates no encounter of which is worse than
+0.10 in either config; if none qualifies, the lowest overall (flagged).

## Confirmation (fresh fights)

Replays 111333000-111333099 (300 fights), configs prod and prod@mb=4, 2 shards of 50 per encounter, modes none, exact,
the selected candidate, head:a20, hblend:a20:0.5, head:ct and hblend:ct:0.5.

**Pass** (the selected candidate): pooled paired change in exact regret against the playout at most −0.10 per fight in
prod@mb=4 and below 0 in prod, and no encounter worse than +0.10 in either config. The other modes are descriptive.

Pass leads to a native default-off leaf flag (head or blend with the turn penalty) and fight-level A/Bs (Philipp's
go). Fail leads to other labels (n-step, CRN) first.

**Part B** (after the production-combat rerun `../silver_leaf_a20_prod_20261022`): its head `a20prod` (same pack and
training scripts) with the selected mode and P in place of a20, on the same fresh fights, same pass rule; plus
head:a20prod and hblend:a20prod:0.5, descriptive.

Scripts: `run_tp.sh`, `select_tp.py`; the analysis is `../silver_leaf_a20_data_20261022/analyze_oracle.py` with
`SEEDS=LO:HI`.
