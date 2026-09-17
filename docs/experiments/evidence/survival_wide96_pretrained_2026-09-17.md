# Width-96 maxHP/HP pretraining and survival transfer

**SURVIVAL_DEEPSET_REJECTED.** One authorized two-stage run completed.

## Protocol and provenance

- Baseline: `35402d1e59ae5e9e66fe277f853f3ec62213c157`.
- Independently reviewed frozen execution SHA: `8adb4794ec22fb051014c8c638cb2fec326b7615`.
- Width-96 PR #219 encoder; unchanged embeddings, entity/global outputs 96, trunk 384→192→96.
- Pretraining copies only the verified specialist 8-D delta embedding. HP MLP104→64→304 and maxHP96→11 are fresh. Exact PR #205 teachers/output hashes, victory-only TRAIN normalization, equal-weight maxHP/HP KL, 40 epochs, batch512, AMP-FP16, AdamW LR1e-4/1e-3, WD1e-4, clip1, seed20260912 are retained.
- Pretraining population: 393,677 TRAIN / 48,590 VALIDATION victories. Earliest strict minimum mean validation teacher KL selects the encoder.
- Transfer loads only the selected encoder, including unchanged normalization buffers, into a fresh Linear(96,1). All encoder/head parameters jointly train on408,183 survival TRAIN rows;50,406 VALIDATION rows only select/score.
- Survival: FP32, AdamW LR1e-4/1e-3, WD1e-3, batch512, clip1, seed20260912, minimum12/maximum40 epochs, patience6; selection solely survival VALIDATION NLL. No auxiliary loss/control.
- External run: `/home/philippherrmann/sts_sweep/runs/survival-wide96-pretrained-20260917`.
- Complete receipt SHA256: `2f2d9ce9799f9f57d0fc93fc5fcc6c0af851ca895df7602e98343d181effa81a`.

## Results

Pretraining selects epoch 39/40, with maxHP KL 0.001547313, HP KL 0.018590566. Its diagnostic outcome is `SHARED_TRANSITION_ENCODER_GO`; this does not qualify survival or runtime. Nine AMP updates were skipped under the unchanged overflow policy. Training/evaluation took 160.28s.

Survival selects epoch 14/20 (patience); AUC 0.978287504;167,257 parameters. Epoch training/validation time totals 91.99s.

| Metric | Attention | Pretrained width-96 | Gap | Fixed gate |
|---|---:|---:|---:|---|
| nll | 0.059494425 | 0.062599011 | +5.2183% | FAIL |
| brier | 0.017815094 | 0.018578166 | +4.2833% | PASS |
| deaths NLL | 0.989065945 | 1.147493601 | +16.0179% | FAIL |
| lowPreHp NLL | 0.398080587 | 0.411121994 | +3.2761% | PASS |

Validity PASS. Speed screen skipped because survival quality rejects. TEST inference/scoring=0; no runtime/gameplay/export/promotion.

## Interpretation

Pretraining improves scratch width-96 NLL from0.065301903 to0.062599011, but the fixed NLL(+2%) and death NLL(+10%) gates still fail. Brier now passes. Versus width-64 strong-WD(0.062930815), overall NLL is slightly lower, but death behavior remains worse(+16.02% vs+7.00%). This does not qualify either candidate, isolate width alone, or prove that pairwise interactions are necessary. No further scaling or tuning follows from this run.

## Checkpoints

- Pretraining selected: `/home/philippherrmann/sts_sweep/runs/survival-wide96-pretrained-20260917/pretraining/student.pt`; SHA256 `a180803709da170c16f51f341d86793e1acc8a83881bbb1b502e81e3dfbe7f21`.
- Survival selected: `/home/philippherrmann/sts_sweep/runs/survival-wide96-pretrained-20260917/survival/selected.pt`; SHA256 `fefcc3940f06bf25d0d81a53d0ff5d7557a9251f9122c9431afb9e8e4ea6cae6`.
- The complete JSON receipt records teacher hashes, initialization/transfer hashes, populations, permutations, calibration bins, gates and environment.

## Full pretraining history

| Epoch | TRAIN maxHP KL | TRAIN HP KL | VALIDATION maxHP KL | VALIDATION HP KL | Selection |
|---:|---:|---:|---:|---:|---:|
| 1 | 0.164221489 | 0.372406772 | 0.067538014 | 0.204090982 | 0.135814498 |
| 2 | 0.047791863 | 0.168679216 | 0.024179973 | 0.147190585 | 0.085685279 |
| 3 | 0.026056883 | 0.124051323 | 0.020365106 | 0.108000267 | 0.064182687 |
| 4 | 0.023095809 | 0.097750007 | 0.018603498 | 0.087283114 | 0.052943306 |
| 5 | 0.020942439 | 0.080590936 | 0.017428306 | 0.074508722 | 0.045968514 |
| 6 | 0.018692386 | 0.069886934 | 0.016039485 | 0.065244011 | 0.040641748 |
| 7 | 0.016128349 | 0.060677688 | 0.013929710 | 0.056214544 | 0.035072127 |
| 8 | 0.013423360 | 0.054366490 | 0.010929509 | 0.052289886 | 0.031609697 |
| 9 | 0.010241061 | 0.049146374 | 0.007876743 | 0.045714182 | 0.026795463 |
| 10 | 0.007465126 | 0.045053275 | 0.005927318 | 0.043495370 | 0.024711344 |
| 11 | 0.005789823 | 0.041422003 | 0.004741558 | 0.041213608 | 0.022977583 |
| 12 | 0.004872040 | 0.038671946 | 0.003872982 | 0.036660941 | 0.020266961 |
| 13 | 0.004308293 | 0.036196110 | 0.003644930 | 0.034647102 | 0.019146016 |
| 14 | 0.003926350 | 0.034110354 | 0.003270176 | 0.033067781 | 0.018168978 |
| 15 | 0.003591023 | 0.032268758 | 0.003000283 | 0.032270513 | 0.017635398 |
| 16 | 0.003345139 | 0.030845098 | 0.002797603 | 0.031951372 | 0.017374487 |
| 17 | 0.003127614 | 0.029593382 | 0.002756461 | 0.028968603 | 0.015862532 |
| 18 | 0.002957583 | 0.028343023 | 0.002490909 | 0.027539625 | 0.015015267 |
| 19 | 0.002806002 | 0.027615475 | 0.002354059 | 0.027063186 | 0.014708623 |
| 20 | 0.002691514 | 0.026607157 | 0.002355916 | 0.026812204 | 0.014584060 |
| 21 | 0.002566590 | 0.025723630 | 0.002199876 | 0.025447128 | 0.013823502 |
| 22 | 0.002464286 | 0.025204928 | 0.002167774 | 0.025487065 | 0.013827420 |
| 23 | 0.002365549 | 0.024383664 | 0.002087346 | 0.024326338 | 0.013206842 |
| 24 | 0.002291117 | 0.023860555 | 0.002072975 | 0.024818458 | 0.013445717 |
| 25 | 0.002219385 | 0.023385091 | 0.001949068 | 0.023570833 | 0.012759950 |
| 26 | 0.002149863 | 0.022728791 | 0.001996813 | 0.022624185 | 0.012310499 |
| 27 | 0.002077828 | 0.022249145 | 0.001865534 | 0.022338871 | 0.012102203 |
| 28 | 0.002026359 | 0.021801714 | 0.001808684 | 0.022366642 | 0.012087663 |
| 29 | 0.001973299 | 0.021468587 | 0.001825616 | 0.022445567 | 0.012135591 |
| 30 | 0.001934197 | 0.020937359 | 0.001837128 | 0.021187510 | 0.011512319 |
| 31 | 0.001874297 | 0.020593939 | 0.001832911 | 0.020663506 | 0.011248209 |
| 32 | 0.001837687 | 0.020384756 | 0.001742257 | 0.021365794 | 0.011554025 |
| 33 | 0.001812190 | 0.019987900 | 0.001667228 | 0.020839714 | 0.011253471 |
| 34 | 0.001776414 | 0.019699511 | 0.001656425 | 0.022390529 | 0.012023477 |
| 35 | 0.001738327 | 0.019286405 | 0.001603883 | 0.020271894 | 0.010937888 |
| 36 | 0.001705682 | 0.019120685 | 0.001604752 | 0.020830379 | 0.011217566 |
| 37 | 0.001674025 | 0.018812956 | 0.001662453 | 0.019402229 | 0.010532341 |
| 38 | 0.001646351 | 0.018571140 | 0.001663576 | 0.018804625 | 0.010234101 |
| 39 | 0.001615760 | 0.018380163 | 0.001547313 | 0.018590566 | 0.010068939 |
| 40 | 0.001595966 | 0.018068371 | 0.001579544 | 0.019163926 | 0.010371735 |

## Full survival history

| Epoch | TRAIN NLL | VALIDATION NLL | VALIDATION Brier |
|---:|---:|---:|---:|
| 1 | 0.082396726 | 0.074805163 | 0.021731867 |
| 2 | 0.066486116 | 0.069310732 | 0.020543441 |
| 3 | 0.063967259 | 0.066934317 | 0.019818969 |
| 4 | 0.062087221 | 0.065268219 | 0.019363016 |
| 5 | 0.060570108 | 0.065634146 | 0.019337177 |
| 6 | 0.059957020 | 0.064377002 | 0.019067565 |
| 7 | 0.059092682 | 0.063584633 | 0.018793175 |
| 8 | 0.058277209 | 0.063583277 | 0.018863028 |
| 9 | 0.057740757 | 0.064042047 | 0.019145012 |
| 10 | 0.057034154 | 0.064512797 | 0.019047808 |
| 11 | 0.056361670 | 0.066184923 | 0.019284183 |
| 12 | 0.055958029 | 0.062797725 | 0.018648122 |
| 13 | 0.055231409 | 0.064594097 | 0.019338183 |
| 14 | 0.054762222 | 0.062599011 | 0.018578166 |
| 15 | 0.054068159 | 0.064383522 | 0.019115090 |
| 16 | 0.053577799 | 0.064853653 | 0.019618612 |
| 17 | 0.052976835 | 0.063982330 | 0.018788747 |
| 18 | 0.052371194 | 0.064758226 | 0.019042242 |
| 19 | 0.051715145 | 0.065173253 | 0.019105760 |
| 20 | 0.051203217 | 0.064980820 | 0.019127071 |

## All survival slices

| Slice | Rows | Deaths | Attention NLL | Candidate NLL | Attention Brier | Candidate Brier |
|---|---:|---:|---:|---:|---:|---:|
| boss | 5444 | 1169 | 0.280834377 | 0.291277468 | 0.088252187 | 0.091433555 |
| deaths | 1816 | 1816 | 0.989065945 | 1.147493601 | 0.323512346 | 0.361149460 |
| lowPreHp | 756 | 292 | 0.398080587 | 0.411121994 | 0.129600912 | 0.132143155 |
| normal | 44962 | 647 | 0.032694578 | 0.034910619 | 0.009286569 | 0.009756834 |
| victories | 48590 | 0 | 0.024752669 | 0.022052225 | 0.006389983 | 0.005774925 |

## Verification and limits

-19 focused unittest tests PASS; CTest2/2 PASS; deterministic small train/transfer test PASS from clean implementation checkout and clean CMake build. No recipe changed following these checks.
- Independent read-only implementation review PASS at the frozen SHA. Worktree preflight/check, doctor and git diff --check PASS. Exact control/teacher/output/delta hashes verified before the fit.
- Both stages completed once, exit0. Selected checkpoints reloaded during the fit; survival selected NLL exactly matches history minimum. Encoder-only transfer and fixed normalization are asserted in the execution path.
- Linux GCC was not triggered: draft PR #219 remains stacked on PR #217, while CI targets main. No CI pass is claimed for this follow-up.
- Repo-health reports existing broken documentation references to combat_budget_diag_2026-09-15/README.md and deepset_survival_lbfgs_2026-09-17.md. These unrelated links were not modified.
- Knowledge impact: negative research evidence/current status; no default or qualification change.

## Executed command

```bash
python3 tools/combat_transition_wide96_pretrain.py --experiment-sha "$(git rev-parse HEAD)" --reference-dir /home/philippherrmann/sts_sweep/runs/shared-transition-encoder-distill-20260915 --control-dir /home/philippherrmann/sts_sweep/runs/shared-transition-encoder-overflow-40-20260915 --output /home/philippherrmann/sts_sweep/runs/survival-wide96-pretrained-20260917
```
