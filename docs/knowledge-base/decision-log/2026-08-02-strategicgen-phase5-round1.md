# 2026-08-02: Phase 5 round 1 — strategicgen all-actions + Tier-A net + one-ply gate

## Decision

Revived the archived Phase 5 plan (`docs/archive/combat-action-plan-2026-07.md`)
with a first end-to-end round: (1) `strategicgen` logs every legal OOC action
per decision with structured candidate fields and a `chosen` flag, labeled
Tier-A (terminal `won/endFloor/endHp` only on chosen rows); (2) new
`train_strategic.py` fits a joint policy (per-decision-group softmax on
`chosen`) + run-value V(s) → `10·won+endHp` net; (3) `export_strategic.py`
exports `OOC_STRAT_V1` for `apps/ooc_strategic_net.h::OocStrategicNet`; (4)
`oocOnePlyCardRewardPolicy` in `runFullRunOOC` applies each legal card-reward
action to a copy, scores the successor with V(s'), and executes the best only
when its margin over the runner-up ≥ `STS_OOC_STRATEGIC_MARGIN` (default 1.0),
else the heuristic card policy runs.

## Rationale

- **Inference:** the Phase 5 architecture needs per-action rows (5.2.3 dynamic
  scorer, 5.5 one-ply search), and the §66k/§67 verdict blamed raw `GameAction`
  bits as an action representation — so resolved candidate fields were logged
  from the start (card ids, shop items/prices, map children, event id, rest
  option, boss relic id) to avoid a datagen rerun for 5.3.3 later.
- **Inference:** Tier-A was chosen (user decision) because unchosen actions have
  no honest label; the terminal label is valid only for the chosen row. This
  makes the value head state-only and action preference comes from one-ply
  successor scoring, not from a Q(s,a) head (which needs Tier-B counterfactual
  labels).
- The margin gate is mandatory, not optional: un-gated greedy NN deployment is
  a recorded failure mode (§66m 0/64, §67 0%).

## Alternatives considered

- Tier-B one-ply counterfactual labels for all actions now — deferred; the
  machinery (`finishOocCounterfactual`) already exists, but the architecture
  should be proven on Tier A first (and the gate result now justifies Tier B).
- Extending `OocCheckpointNet` for the new heads — rejected; a new header keeps
  the checkpoint scorer's format and issue-08-verified loader untouched.
- Direct greedy NN card picks without a gate — rejected (see above).

## Evidence

- Datagen: 200 seeds → 134,832 rows / 31,870 decisions in 18s
  (`build/strategic_200.csv`). `chosen` detection via successor-fingerprint
  matching; residual ambiguity only in RNG-tied event outcomes (Mausoleum
  open-with-nothing vs leave), 2/786 in the smoke block.
- Held-out: policy top-1 0.778, value MAE 1.73, RMSE 6.06 (60 epochs, CUDA).
- Export parity: max err logit 6.6e-06, value 9.5e-05.
- Paired fair 128-seed gate (1,000 sims, seeds 126700–126827): baseline
  21.1%/37.5/8.6 (bit-identical to §68 on the new binary); candidate margin 1.0
  → 10.2%/31.5/3.7 (−10.9pp wins, floor CI [−8.1, −4.0]); margin 5.0 → 17.2%/
  33.7/7.1 (monotone: fewer overrides, less damage).
- Full record: EXPERIMENTS.md §70.

## Facts/corrections

- The rich state block is **1017** columns between `chosen` and `won` (the
  earlier `<1016>` comment was wrong; 1017 matches the checkpoint net's
  `NSTATE`).
- The trainer's group softmax must use a per-group max for logsumexp stability;
  a global max underflows to `-inf` → NaN once groups in a batch span wide
  logit ranges (fixed in `train_strategic.py`).

## Status

Closed as a round. Pipeline works end-to-end; the first net is not deployable
(recorded §70 regression) and remains opt-in (`STS_OOC_STRATEGIC_NN`). Next
candidates: more data, Tier-B labels, per-screen value heads, or applying the
one-ply gate to screens where the value head is strongest.
