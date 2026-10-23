# Silver leaf head: cleaner labels or more data? (offline and 3-source smokes, 2026-10-23)

Question (Philipp, 2026-10-23 14:28Z, after §656 paused the leaf line): "Should we just retrain with cleaner ooc
labels? Or do we need more data for leaf model?"

**Answer: neither fixes what failed.** Halving the runs of the same label costs about 1 RMSE point, and adding the
other campaign's runs (about twice the roots) gains 0.4. A per-state label (Silver's own searched value at each root)
orders exact leaf values better than any earlier head and wins first fights even without a playout, but in the
3-source smoke every new net still scores below production, mostly in boss fights; the intervals exclude zero only for
the searched-value net. All heads so far learned from states that playout-driven Silver reached; one explanation, not
tested yet, is that a search that trusts the head goes elsewhere.
The doc "Leaf evaluation for Silver" (https://claude.ai/artifact/P8536tUChd5XLo1gV6kfbu) has the same results in its
sections "Measured since: what limits the head" and "Measured since: a label per state instead of per fight".

Exploratory and offline: no new seeds, no workers, no code change. Every number below reads existing data or replays
existing seeds (Part B first fights 111333000-099, smoke sources 111339997-999, exact leaves of 111149600-649).

## 1. What limits the fit (`diag_heads.py`, `diag2.py`)

Both silver-leaf-a20 packs rebuilt byte for byte (`build_pack.sh`): a20prod (production combat, 777,993 roots, sha256
47efc292...) and a20 (first campaign, 736,347 roots, 408a864c...). Folds by seed % 5 as `train_head_a20.py`: 0-2 fit,
3 early stop, 4 test; reference-change roots excluded. Label z = the fight's end score / 100, the same for every root
of a fight. The `frozen` variant is the a20prod recipe and reproduces its committed report exactly (23.71, stop fold
23.461). `e2e` trains the same layers with the trunk (g7f_E's state, monster and encounter embeddings) trainable too,
started from g7f_E (`g7f_E/model.pt` from data branch claude/silver-gen7-act4-data, sha256 90821b50...).

Fold-4 RMSE against the end score (Silver points; noise bound = Silver's root value with each row's mean bias
removed):

| roots | noise bound | frozen (a20prod) | frozen, half the runs | end to end | end to end, half | end to end, both packs |
|---|---|---|---|---|---|---|
| all | 18.8 | 23.7 | 24.6 | 20.0 | 21.1 | 19.5 |
| hallway | 9.8 | 15.9 | 16.7 | 10.9 | 12.2 | 10.5 |
| elite | 17.7 | 22.1 | 23.3 | 17.8 | 19.1 | 17.3 |
| boss | 27.4 | 33.6 | 34.6 | 30.7 | 31.7 | 30.2 |
| Act 3 | 18.6 | 26.7 | 28.0 | 20.4 | 22.1 | 20.1 |
| Act 4 | 35.5 | 37.6 | 38.8 | 36.4 | 38.0 | 35.5 |
| turn 6+ | 13.4 | 27.8 | 28.9 | 23.9 | 25.4 | 24.7 |

A bigger head on the frozen trunk (128-256-256-1) is no better (23.9); trunk regularisation does not help (20.2).
Reruns of the same variant agree within 0.01 (CPU training is not bit-reproducible). Files:
`results/diag_round1.*` (frozen, frozen50, frozen25, frozenbig, e2e, e2e50), `results/diag_round2.*` (PACK2 = the a20
pack in the fit folds: frozen_both, e2e_both, e2e_reg, e2e_reg_both, e2e_reg50), `results/diag_saved.*` (e2e and
e2e_both saved for export).

## 2. A label per state (`diag2.py` with `LABEL=q`, `label_check.py`)

`LABEL=q` trains on Silver's root value (qchosen: the most visited edge's Q after the 10,000-simulation search), a
different value for every root. The end-to-end net fits it to 16.9 points RMSE (frozen trunk 21.8;
`results/diag_q.*`). Against outcomes that label is pessimistic (`results/label_check.txt`): Silver's root value
is 12.4 points below the end score on average, 20.0 at turn 0, 13.9 at turn 1, 10.6 at turn 2 and 5.1 from turn 6 on;
7.9 in hallway fights, 18.1 in boss fights, 23.6 in Act 4. So the q-trained nets predict outcomes worse (fold-4 RMSE
25.9 against 20.0 for the z-trained net).

## 3. Exact leaf values (`leaf_exact.py`)

The 69,734 search leaves of the exact capacity test (first fights 111149600-649, exact value under Silver's objective;
`/mnt/project-files/exact-combat-research/leaf-value/ct/labels_all.jsonl.gz`), the native forward in numpy. A pair
counts when its exact values differ by at least 1 point; same turn = one fight and config at one leaf turn
(`results/exact_leaves.txt`):

| head | trained on | RMSE | bias | same-turn pairs in order | cross-turn pairs in order |
|---|---|---|---|---|---|
| a20prod (frozen trunk) | end score | 6.22 | +4.43 | 0.774 | 0.811 |
| end to end | end score | 4.72 | +2.26 | 0.771 | 0.813 |
| frozen trunk | searched value | 5.34 | +2.85 | 0.764 | 0.788 |
| end to end | searched value | 3.70 | -0.22 | 0.808 | 0.820 |
| capacity test (frozen trunk) | these exact values, in sample | 3.01 | +0.14 | 0.876 | 0.889 |

The capacity-test head (`/mnt/project-files/exact-combat-research/leaf-value/heads/ct.txt`, sha256 5a4a2209..., as in
`../leaf_head_turn_penalty_20261022/PREREG.md`) was trained on the exact values of these same fights' leaves, so its
row is an in-sample ceiling (`results/exact_leaves_ct.txt`). The end-to-end searched-value head's bias by leaf turn
runs from -1.6 (turn 2) to +3.2 (turn 6), so its label was not shifted by turn: offsets of 20 points at turn 0 down to
5 at turn 6 would act like a large turn penalty.

## 4. First fights (`run_ff.sh`, exact_combat_solver)

Part B fights 111333000-099 (300 fights), change in exact regret per fight against the playout leaf, mean backup /
max backup (`prod` / `prod@mb=4`; `results/first_fights/`; a20prod's column is its committed Part B run,
`../silver_leaf_a20_prod_20261022/results/partb_analysis.txt`, which the `ref` rerun here reproduces):

| leaf | a20prod | end to end, end score | end to end, searched value |
|---|---|---|---|
| head alone, no playout | -0.07 / +0.18 | -0.02 / +0.48 | -0.27 / -0.28 |
| 50/50 with the playout | -0.33 / -0.33 | -0.21 / -0.23 | -0.17 / -0.16 |
| 50/50, 1 point per turn | -0.26 / -0.21 | -0.10 / -0.16 | -0.08 / 0.00 |
| 50/50, 1 point per turn, win-now cap | -0.17 / -0.17 | -0.16 / -0.12 | -0.02 / -0.08 |

Standard errors 0.04-0.06, up to 0.38 where an end-score head stalls. The searched-value head alone lengthens Jaw Worm
fights less (3.6 turns against 2.5 for the playout; a20prod's head 4.5; `results/first_fights/qe2e_outcome.txt`).
The end-to-end net on both packs (`e2eb`) behaves like `e2e` (`results/first_fights/e2eb_analysis.txt`).

## 5. 3-source smoke (`smoke/run_smoke.sh`)

The fight-level A/B harness of §656 (`ctmsilvergen` armset leafhead, sources 111339997-999, R = 2, every 3rd hallway
fight plus elites and bosses), production control at 10,000 simulations only, one_combat 83de6c12... (the A/B's
binary). `smoke/analyze2.py` is the A/B's `analyze.py` with two arms; on the archived a20prod smoke it reproduces
-4.285 (`results/smoke/prev_reproduction.json`). Score per fight, head10000 - base10000 (`results/smoke/`; the
first row is main's `../silver_leaf_head_ab_20261022/smoke/analysis.json`):

| leaf | score per fight [95% CI] | fights won | hallway fights | Act 1 | boss fights (10), score each |
|---|---|---|---|---|---|
| a20, 50/50, 1 point per turn, win-now cap (§656's candidate; its PREREG) | -0.8 [-16.3, +2.6] | -1 pp | +8.3 | -3.8 | -11.7 |
| a20prod, 50/50, 1 point per turn (§655) | -4.3 [-16.1, -0.6] | -2 pp | +6.6 | -4.6 | -22.0 |
| end to end on the end score, 50/50, 1 point per turn | -2.0 [-16.8, +1.3] on 42 fights; a stall aborted source 111339999 | -1 pp | +1.3 (17 fights) | -3.5 | -13.3 (8 fights) |
| the same with the win-now cap | -8.6 [-18.5, +2.5] | -4 pp | +8.3 | -3.9 | -48.8 |
| end to end on the searched value, 50/50, no penalty | -2.7 [-3.5, -2.1] | -1 pp | +7.0 | +2.1 | -28.5 |
| the same head alone, no playout, no penalty | -39.8 [-48.3, -33.9] | -11 pp | -13.4 | -9.4 | -136.3 |

The intervals are §656's bootstrap over the 3 source seeds, which allows only 10 distinct resamples, so they are
rough. They exclude zero for a20prod and both searched-value rows; the analysis labels those WORSE and the other three
NOT_SHOWN. The stall: `native Silver backend: stall: exceeded 1000 decisions seed=111339999 floor=35 encounter=40`.

Every head scores lower in boss fights. All but the head alone gain in hallway fights (+1.3 to +8.3 per fight; two
of those five intervals exclude zero). The Act 1 gains of the first-fight tests (Act 1 hallway fights) do not carry
over: here only the searched-value head at 50/50 gains in Act 1 (+2.1 [+0.4, +3.6]), and it loses in Act 3 (-7.1)
and bosses. Alone, the searched-value head lost both replays of the Heart fight, ended both replays of one Collector
fight at 12 HP where production ended at 75 and 50, and lost one replay of the other Collector fight (production 7
and 12 HP); its simulations cost 0.24 of production's.

## 6. Reading

- Per-fight labels cannot rank two states of one fight; fitting them better (end to end) lowers the error but does
  not order leaves better. Halving the runs costs about 1 point; adding the other campaign's runs (about twice the
  roots, a different campaign) gains only 0.4.
- Silver's searched value ranks states better and makes the head usable without a playout in first fights, yet no
  net beats production in the smoke. What every head shares there is the loss in boss fights; the Act 1 gains show
  only in the first-fight tests.
- What the heads also share are their training states (Silver's roots under playout search). One explanation, not
  tested yet: a search that trusts the head steers into states its training never had. A next step would train on
  the states the head's own search reaches, labeled there by production's playout search, and repeat; that needs a
  generator change, a seed block and workers.

## 7. Files and commands

Nets and checkpoints (not in git): `/mnt/project-files/exact-combat-research/leaf-value/label-data-20261023/`
(`nets/*.txt` = trunk files (combat_policy_mlp_v2 with g7f_E's other lines byte-identical) and
silver_value_head_v1 heads; `checkpoints/*.pt` = the diag2.py SAVE=1 checkpoints; `SHA256SUMS`; raw first-fight
jsonl `ff_raw.tgz`, raw smoke rows `smoke_raw.tgz`). Main sha256: q_e2e_head.txt c2c7418e..., q_e2e_trunk.txt
4efed23e..., e2e_head.txt 0d05e8b6..., e2e_trunk.txt 1000d9c0....

From the repo root, with `W` a work directory holding the packs and `g7f_E/model.pt`:

    W=$W docs/experiments/evidence/silver_leaf_label_data_20261023/build_pack.sh prod   # and: ... a20
    cd $W
    python3 $E/diag_heads.py a20prod_pack.npz g7f_E/model.pt out                       # round 1, all 6 variants
    PACK2=a20_pack.npz VARIANTS=frozen_both,e2e_both,e2e_reg,e2e_reg_both,e2e_reg50 \
      python3 $E/diag2.py a20prod_pack.npz g7f_E/model.pt out2
    SAVE=1 PACK2=a20_pack.npz VARIANTS=e2e,e2e_both python3 $E/diag2.py a20prod_pack.npz g7f_E/model.pt saved
    LABEL=q SAVE=1 VARIANTS=frozen,e2e python3 $E/diag2.py a20prod_pack.npz g7f_E/model.pt savedq
    python3 $E/export_e2e.py g7f_E/model.pt REPO/models/combat_policy_mlp_g7f_E.txt saved/e2e.pt e2e_trunk.txt e2e_head.txt
    python3 $E/export_frozen.py savedq/frozen.pt q_frozen_head.txt
    python3 $E/parity.py g7f_E/model.pt saved/e2e.pt dump.jsonl     # dump: exact_combat_solver ... --leaf-head-dump
    python3 $E/label_check.py a20prod_pack.npz saved savedq
    python3 $E/leaf_exact.py LABELS.jsonl.gz a20prod=TRUNK:HEAD e2e=TRUNK:HEAD qe2e=TRUNK:HEAD
    python3 $E/leaf_exact.py LABELS.jsonl.gz \
      ct=REPO/models/combat_policy_mlp_g7f_E.txt:/mnt/project-files/exact-combat-research/leaf-value/heads/ct.txt

(`E` = this directory, `REPO` = the repo root.) First fights, from the repo root (`ref`, `e2e`, `e2eb` and `qe2e` the
same way, modes as in `results/first_fights/*_analysis.txt`):

    $E/run_ff.sh BIN $W/ff qe2e "none,hblend:qe2e:0.5/1,hblend:qe2e:0.5,head:qe2e,hblend:qe2e:0.5/1+cap" \
      "qe2e=$W/q_e2e_head.txt" $W/q_e2e_trunk.txt

Smokes, from the repo root: `W=$W [BLEND=1] TP=0 $E/smoke/run_smoke.sh TAG HEAD TRUNK WINCAP` (e2e_tp: blend 0.5,
TP 1, WINCAP 0; e2e_tp_cap: WINCAP 1; qe2e_b05: blend 0.5, TP 0, WINCAP 0; qe2e_head: blend 1, TP 0, WINCAP 0).

The scripts ran from a scratch directory with fixed paths; the committed copies take the paths as arguments or `W`,
otherwise unchanged. Besides those, `build_pack.sh` and `smoke/run_smoke.sh` copy fixed, content-addressed share
inputs: `/mnt/project-files/bin-cache/one_combat-<sha256>` and `/mnt/project-files/rollout-student-494/studentc.bin`.
Parity: on 300 dumped first-fight leaves the solver's trunk and value match the PyTorch net within 1.2e-5 points
(`results/parity.txt`).

Provenance: exact_combat_solver sha256 20a81523... built from 6a8de838 (#826's head; its solver code is main's),
one_combat 83de6c12... (the §656 A/B binary, code 75afdee0), pack binaries f4cc0752... (code 28e281f1) and
13055711... (code a8fd1fd5), student C rollout policy `/mnt/project-files/rollout-student-494/studentc.bin`
(eff2f74f...). CPU only, 4 cores.
