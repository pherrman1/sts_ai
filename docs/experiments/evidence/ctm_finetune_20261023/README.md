# A20 CTM fine-tune on today's real fights: the HP head helps, survival does not beat the table (offline, 2026-10-23)

Philipp, 2026-10-23 20:18Z, after the CTM calibration (§670, [`../ctm_calibration_20261023/README.md`](../ctm_calibration_20261023/README.md)):
"Retraining could maybe just be a fine tune? … do it on another thread in parallel". At 20:32Z he set the yardstick:
CTM quality is judged on prediction precision, not on win rate. So this is an offline study only: out-of-sample
death log loss and won-fight HP error, by act × room and per elite/boss, on the same rows, folds and held-out set as
the calibration. No games were played and no seeds were run.

## Data and split (the calibration's, unchanged)
- **New rows.** The 97,561 real fights of the stage-3 A/B (sets A, M, S, MS) and the 6,022 fights of the stage 1–2
  games (LC, held out), rebuilt with [`../ctm_calibration_20261023/offline/extract.sh`](../ctm_calibration_20261023/offline/extract.sh):
  all five hashes match [`rows.txt`](../ctm_calibration_20261023/offline/rows.txt). Folds: source seed parity (all four
  arms of a seed stay in one fold). Each model is trained on one fold and tested on the other; the final model is
  trained on all A/B rows and tested on LC.
- **Old rows (mixed in).** 112,906 Stage-1 corpus rows of the deployed CTM's own training data (§443; data branch
  `claude/ctm-a20-data`, `ctm-a20-stage1/w01–w03.tar.gz`, `out/main-*.jsonl`, rows sha256
  `e6e33eae…` after encoding), at 25% of each batch.
- **Training rows.** Rows the deployed stack scores, without Entropic Brew (routed to the standard child) and without
  an active Lizard Tail (scored by the composition). About 10% of the training fold's seeds (hash rule in
  `_inner_split`) pick the epoch; the test fold is never used for any choice.
- Encoding reports: [`results/encode_new.json`](results/encode_new.json), [`encode_lc.json`](results/encode_lc.json),
  [`encode_old.json`](results/encode_old.json).

## What is fine-tuned ([`tools/ctm_finetune.py`](../../../../tools/ctm_finetune.py))
The deployed fast artifact `combat_transition_deepsets_pathb_a20_lizard.native` (`ae785ec2…`) is a small DeepSets
stack, so training runs on 4 CPUs in minutes; no GPU was used.
- **Survival:** the survival encoder (its own weights) and its 1×64 head, or the head alone.
- **HP:** only the HP head (max-HP-delta embedding and the 73 → 64 → 451 MLP). The HP encoder z stays frozen, because the
  maxHP head (a weight twin of it), the relic, gold and ritual heads read the same z.
- Everything else is copied byte for byte. Loss: BCE on survival, NLL of the HP class; L2 pull to the base weights
  (L2-SP); the survival and HP parts keep separate best epochs (disjoint parameters, independent losses).
- `export` writes a research candidate under id `pathb-a20` and a `ctm_research_candidate_v3` manifest (the built-in
  one with the new hashes). Load it with `STS_CTM_RESEARCH_CANDIDATE_MANIFEST(+_SHA256)`; the Act-4 survival model and
  `STS_CTM_CALIBRATION` apply to it as to the deployed stack.
- **Parity.** The tool's survival (Python, from the artifact's tensors) matches the C++ runtime's `p_death` on 1,746
  plain Stage-1 rows at a median 9e-14 (99th percentile 1.8e-7; one event fight 2.4e-3). All scores below come from
  the C++ runtime (`one_combat ctmscorerows`, [`score_ft.sh`](score_ft.sh)).

## Results
Arms on the same test rows: **CTM** = deployed stack, calibration off; **table** = CTM + the calibration table fitted
on the other fold (for LC: the shipped `ctm_calibration_pathb_a20_v1.json`); **FT** = fine-tuned net, no table.
[`compare3.py`](compare3.py) prints the tables; [`paired.py`](paired.py) gives paired seed-bootstrap intervals.

**1. Survival fine-tunes do not beat the table** (death log loss, test fold; table 0.0685 odd / 0.0684 even):

| variant (survival part) | train even → test odd | train odd → test even |
|---|---|---|
| encoder + head, lr 3e-4, 12 ep ([`cmp-even-sel`](results/cmp-even-sel.md), [`cmp-odd-sel`](results/cmp-odd-sel.md)) | 0.0714 | 0.0703 |
| same, Act-4 model off (net predicts the Heart) | 0.0711 | 0.0701 |
| encoder + head, lr 1e-3, 30 ep ([`cmp-*-e30`](results/cmp-even-e30.md)) | 0.0730 | 0.0754 |
| head only, lr 1e-3 ([`cmp-*-head`](results/cmp-even-head.md)) | 0.0788 | 0.0789 |

- FT − table, best variant: +0.0026 [+0.0012, +0.0042] and +0.0017 [+0.0002, +0.0032]. FT − CTM: −0.0020 and −0.0016.
- The survival part overfits quickly (best inner epoch 4–8 at lr 3e-4) and drifts per act: too few deaths in Act 1–2
  elites and too many late. The head-only variant collapses the Heart (0.11 predicted vs 0.37 observed).
- With the Act-4 model off, the fine-tuned net predicts the Heart better than the Act-4 model (log loss 0.441 vs
  0.451 odd, 0.472 vs 0.478 even), but worse than the table (0.406 / 0.448).
- Trained on all A/B rows, the encoder fine-tune ties the table on LC: 0.0689 vs 0.0698, FT − table −0.0009
  [−0.0038, +0.0019]; HP MAE 7.55 vs 7.60 ([`cmp-lc-allmix.md`](results/cmp-lc-allmix.md)). Twice the data helps;
  not enough to replace the table.
- Sweep (12 configurations per fold, chosen on inner validation only): [`results/sweep_inner_validation.txt`](results/sweep_inner_validation.txt).

**2. The HP head fine-tune improves HP on top of the table.** Candidate: HP head only (lr 1e-3, up to 30 epochs, L2-SP
10, 25% old rows), survival untouched; a calibration table refitted on its scores
([`tools/ctm_calibration.py`](../../../../tools/ctm_calibration.py) `fit`, same folds). Against the shipped arrangement
(old net + table), on the same rows:

| test set (fit on) | fights | death log loss | won-fight HP MAE | change [95% seed bootstrap] |
|---|---|---|---|---|
| A/B odd seeds (even) | 48,674 | 0.0685 → 0.0686 | 7.66 → 7.56 | −0.10 [−0.13, −0.06] |
| A/B even seeds (odd) | 48,887 | 0.0684 → 0.0684 | 7.67 → 7.60 | −0.06 [−0.09, −0.03] |
| stage 1–2 games (all A/B) | 6,022 | equal | 7.60 → 7.45 | −0.15 [−0.22, −0.08] |

- Without any table, the HP head alone takes the CTM's HP MAE from 8.46 to 7.74 (odd), 8.48 to 7.81 (even) and 8.23
  to 7.55 (LC), close to the table's 7.66 / 7.67 / 7.60.
- The gain sits at bosses and Act-3 elites. Held out: Act-1 bosses −0.42 [−0.69, −0.15], Act-2 bosses −0.59
  [−1.22, +0.06], Act-3 bosses −0.82 [−1.51, −0.12], Act-3 elites −0.57 [−0.84, −0.31]. Hallways and Act-1/2 elites
  move by less than 0.1. Per group: [`paired_hp_table_fit_even_on_odd.md`](results/paired_hp_table_fit_even_on_odd.md),
  [`…odd_on_even.md`](results/paired_hp_table_fit_odd_on_even.md), [`paired_final_table_heldout_lc.md`](results/paired_final_table_heldout_lc.md).
- The Heart's won-fight HP gets worse (+1.5 / +0.4 / +1.0), which has no effect (the run ends with a won Heart).
- Death predictions: the final export keeps the §470 boss shift (`--keep-boss-shift`), so its `p_death` is
  byte-identical to the deployed stack on all 103,583 fights ([`results/final_p_death_identical.txt`](results/final_p_death_identical.txt)).
  The fold models were exported without it; the refitted table absorbs that (death log loss change 0.0000 above).

## Candidate (research, nothing default)
- [`models/candidates/ctm_finetune_hp_pathb_a20_v1.native`](../../../../models/candidates/ctm_finetune_hp_pathb_a20_v1.native)
  `bdbfafa6…` (base `ae785ec2…`, only the five HP-head tensors differ), manifest
  [`…_v1.manifest.json`](../../../../models/candidates/ctm_finetune_hp_pathb_a20_v1.manifest.json) `31bb21f7…`,
  checkpoint `7e068cd3…` (share: `/mnt/project-files/ctm-finetune/`), fit receipt [`runs/final/fit.json`](runs/final/fit.json).
- Its table [`models/candidates/ctm_calibration_pathb_a20_ft_hp_v1.json`](../../../../models/candidates/ctm_calibration_pathb_a20_ft_hp_v1.json)
  (`8c226f23…`), fitted on all A/B fights scored by the candidate. C++ = tool: `parity` on LC and A, 30,072 fights
  without an active Lizard Tail, death within 1e-7, mean won-fight HP within 1.9e-6.
- Use offline: `STS_CTM_RESEARCH_CANDIDATE_MANIFEST=models/candidates/ctm_finetune_hp_pathb_a20_v1.manifest.json`,
  `…_SHA256=31bb21f7ace7e3cd440136cf0799dbae1e0fbc2964d00bfa7bac8e21124e0a5c`,
  `STS_CTM_CALIBRATION=models/candidates/ctm_calibration_pathb_a20_ft_hp_v1.json`, and the artifact path as
  `ctmscorerows` FAST. **Open:** the OOC MCTS stack loads the fast artifact from a fixed path, so playing with it
  needs a small path switch first.

## Caveats
- The rows predate today's engine fixes #831, #833, #835 and #836 (a few fights change slightly).
- `STS_ACTIVE_POWER_FEATURES` does not reach the CTM: its input is the pre-combat run state (no combat powers). Scoring
  ran with `=1` anyway.
- One training seed per configuration; epoch selection on ~4,800 inner rows (~150 deaths) is noisy for survival.
- Lizard-Tail and Brew rows were not trained on; their HP comes from the composition or the standard child. The
  Lizard r models were fitted on the base survival; survival is unchanged in the candidate, so they still fit.

## Commands (as run, from the repo; `W` = scratch, `R` = the five row sets)
```
bash ../ctm_calibration_20261023/offline/extract.sh $R           # five hashes match
one_combat ctmscorerows old.jsonl old.off.csv FAST STD 1         # deployed stack, scored flags for the old rows
python3 tools/ctm_finetune.py encode $W/new.npz $R/A.jsonl:off/A.csv $R/M.jsonl:off/M.csv $R/S.jsonl:off/S.csv $R/MS.jsonl:off/MS.csv
python3 tools/ctm_finetune.py encode $W/lc.npz $R/LC.jsonl:off/LC.csv ; … encode $W/old.npz old.jsonl:old.off.csv
bash sweep.sh even ; bash sweep.sh odd                           # 12 configurations per fold (results/sweep_inner_validation.txt)
python3 tools/ctm_finetune.py train --base FAST --base-sha ae785ec2… --new new.npz --old old.npz --old-share 0.25 \
    --seeds even|odd|all --epochs 30 --lr 0 --survival-head-only --hp-lr 1e-3 --l2sp 10 --l2sp-hp 10 --out DIR   # HP candidate
python3 tools/ctm_finetune.py export --base FAST --base-sha ae785ec2… --checkpoint DIR/finetune.pt --out ft.native \
    --manifest-out manifest.json [--keep-boss-shift]
bash score_ft.sh DIR OUT [act4off]                               # C++ scores of A M S MS LC, calibration =0
STS_CTM_CALIBRATION=zero.json one_combat ctmscorerows …          # the zero-table scoring the refit needs
python3 -I tools/ctm_calibration.py fit TABLE OFF,ZERO … --seeds even|odd|all
python3 -I compare3.py tools/ctm_calibration.py TABLE_OTHER_FOLD odd|even OUT.json OFF,ZERO,FT …
python3 -I paired.py tools/ctm_calibration.py SEEDS TABLE_A OFF_A,ZERO_A+… TABLE_B OFF_B,ZERO_B+…
```
Runs: [`runs/`](runs/) (fit receipts with every epoch's inner-validation losses, export receipts, manifests). Score
CSVs: `/mnt/project-files/ctm-finetune/scores.tar.gz`, `scores-final.tar.gz` (hashes
[`results/scores_final.sha256`](results/scores_final.sha256)). Reference scores (CTM off/zero) are the calibration's,
`/mnt/project-files/ctm-calibration/scores/` (all 15 hashes match `scores.sha256`). The fine-tuned arm's
scores are byte-identical between a `one_combat` built at main `a8b80139` and one at #838's head `ffc1228c`.
