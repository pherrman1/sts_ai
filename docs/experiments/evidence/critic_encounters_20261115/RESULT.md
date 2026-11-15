# Privileged encounter lists in the offline critic (issue #1050 stage 0): RESULT

Pre-registration: [PREREG.md](PREREG.md) (review K PASS on 75cdc2d1, 2026-11-15 18:05 CET,
`/mnt/project-files/reviews/pr1059-review.md`). Run on the PC (pop-os, CPU only, nice 10) 2026-11-15 18:14-19:21 CET,
after Philipp's go in the thread (18:14 CET). Offline only: no seeds, no games, no workers, no GPU; the PG16H24 learner
ran alongside untouched.

Raw records (transport ref `ppo-xfer/critic-enc-results` = `8cb758ab`, parentless, copied here): `report.json`,
`gbm.json`, `gbm_enc.json`, `gbm_run.json` (model meta incl. vocab), `check_encounters.json`, `commands.log`,
`run.sh`, `run.stdout`. The xgboost `.ubj` models stay on the PC in `~/critic-enc-out/`.

## Provenance

- Code: worktree `~/sts-critic-enc` at `75cdc2d1` (the reviewed head), `/usr/bin/python3`, xgboost 3.4.0, numpy 2.5.1,
  scipy 1.18.0. Encounter table `critic_encounters_long_c_220_419.json.gz` sha256 `21e81001…c7ad63` (ref
  `ppo-xfer/critic-enc` = `bcc11d75`).
- Data as §761: test LONG_C 0400-0419 (800 parts, 10,400 games, 515,422 act-1 decisions), train 0220-0399 (7,200 parts),
  `--per-game 8`, **`--game-frac 1.0`** for all three fits (no RAM fallback, no kill; MemAvailable stayed > 22 GB).

### Exact commands (review note N1)

```
critic_ceiling.py check-encounters --parts <LONG_C 0220-0399> <LONG_C 0400-0419> --encounters TABLE
critic_ceiling.py fit-gbm --train <0220-0399> --exclude-from <0400-0419> --per-game 8 --game-frac 1.0 --threads 4 --workers 4 --out gbm.json
  ... same + --encounters TABLE --enc-scope act --out gbm_enc.json
  ... same + --encounters TABLE --enc-scope run --out gbm_run.json
critic_ceiling.py evaluate --test <0400-0419> --gbm gbm.json --extra-gbm gbm_enc=gbm_enc.json --extra-gbm gbm_run=gbm_run.json
  --encounters TABLE --contrast gbm_enc:gbm --contrast gbm_enc:online_cal --contrast gbm_run:gbm --contrast gbm_run:gbm_enc
  --rule encounters --enc-ev-margin 0.03 --train-seeds-from <0220-0399> --out report.json
```

The full paths are in `commands.log` and `run.sh`.

## Gate and fits

- `check-encounters` on all 8,000 parts: ok. 104,000 games, 11,338,165 act 1-3 net decisions checked (399,904 in act 4),
  each `obs.v2.fought` equal to the table's consumed prefix and the recorded boss equal to the table's. Most consumed
  in one act: normals 11 / 10 / 10, elites 6 / 6 / 6, so no list ran out.
- Fits (941,186 train / 49,129 val rows each, identical rows):

| GBM | features (enc_*) | best iteration | val log loss | wall |
| --- | --- | --- | --- | --- |
| gbm | 1,399 (0) | 1871 | 0.3825 | 525 s |
| gbm_enc (scope act) | 1,718 (319) | 1742 | 0.3839 | 625 s |
| gbm_run (scope run) | 1,892 (493) | 2066 | 0.3841 | 656 s |

  gbm reproduces §761's GBM primary (best iteration 1871, val 0.3825, same test scores below).

## Primary result: **NO_GO**

Per scope (AUC / EV against the Heart outcome, all test decisions):

| Estimator | First decision | Act 1 | Act 2 | Act 3 | Act 4 | All |
| --- | --- | --- | --- | --- | --- | --- |
| online_cal | 0.526 / 0.002 | 0.671 / 0.072 | 0.782 / 0.219 | 0.825 / 0.315 | 0.817 / 0.282 | 0.784 / 0.243 |
| gbm | 0.511 / 0.000 | 0.662 / 0.063 | 0.785 / 0.224 | 0.833 / 0.331 | 0.839 / 0.318 | 0.782 / 0.242 |
| gbm_enc | 0.522 / 0.001 | 0.661 / 0.061 | 0.785 / 0.223 | 0.832 / 0.329 | 0.839 / 0.319 | 0.781 / 0.241 |
| gbm_run | 0.521 / −0.000 | 0.659 / 0.061 | 0.785 / 0.223 | 0.833 / 0.332 | 0.839 / 0.318 | 0.781 / 0.242 |

Paired game-cluster bootstrap, Δ EV [95% CI] (2,000 resamples, seed 20261106):

| Contrast | First decision | Act 1 | Act 2 | Act 3 | Act 4 | All |
| --- | --- | --- | --- | --- | --- | --- |
| gbm_enc − gbm | +0.0005 [−0.0007, +0.0018] | **−0.0012 [−0.0022, −0.0002]** | −0.0016 [−0.0042, +0.0010] | −0.0021 [−0.0072, +0.0029] | +0.0006 [−0.0074, +0.0084] | −0.0015 [−0.0032, +0.0004] |
| gbm_enc − online_cal | −0.0008 [−0.0029, +0.0014] | **−0.0107 [−0.0150, −0.0065]** | +0.0035 [−0.0042, +0.0113] | +0.0140 [+0.0023, +0.0253] | +0.0364 [+0.0179, +0.0564] | −0.0025 [−0.0077, +0.0029] |
| gbm_run − gbm | −0.0005 [−0.0029, +0.0020] | −0.0014 [−0.0037, +0.0011] | −0.0011 [−0.0049, +0.0028] | +0.0003 [−0.0046, +0.0050] | +0.0001 [−0.0075, +0.0082] | −0.0006 [−0.0030, +0.0017] |
| gbm_run − gbm_enc | −0.0010 [−0.0032, +0.0013] | −0.0002 [−0.0024, +0.0022] | +0.0005 [−0.0032, +0.0041] | +0.0024 [−0.0020, +0.0069] | −0.0004 [−0.0077, +0.0073] | +0.0008 [−0.0013, +0.0029] |

Rule checks (act 1): gain over gbm ≥ 0.03: **no** (−0.0012); its CI above 0: **no**; gain over online_cal CI above 0:
**no** → **NO_GO**. Log loss, descriptive: gbm_enc − gbm act 1 +0.0007 [+0.0000, +0.0013], all +0.0008
[−0.0002, +0.0018].

## Interpretation

- **Inference:** given the public state, which normal encounters and elites still lie ahead in the act explains no
  measurable share of the Heart outcome in this model class. The act-1 EV gain is bounded above by +0.0002 (95%
  CI), two orders of magnitude below the +0.03 bar; even at the run's first decision, where the whole act-1 list
  is unknown to the public critic, the gain is +0.0005 [−0.0007, +0.0018]. Adding the later acts' lists and bosses
  (gbm_run) does not help either.
- The slightly negative act-1 difference fits 319 extra sparse features that carry no signal: the boosting rounds
  spent on them cost a little elsewhere (val log loss 0.3839 vs 0.3825).
- gbm_enc's gains over online_cal in acts 3-4 are the public GBM's own (§761, descriptive): gbm_enc − gbm there is
  −0.0021 and +0.0006.
- A plausible mechanism (**Inference**, not tested): the agent routes around elites and hallway fights by sight of
  the map, an encounter's difficulty mostly shows up as HP the record already carries, and a 20% Heart outcome is
  decided mostly after act 1.
- Limits: one model class (GBM with position/count indicators), encounter identities only (no HP rolls or move
  RNG), the Heart outcome only. A net might use the lists better, but the GBM's flat gain at 941k rows gives no
  reason to expect a +0.03 effect.

## Decision

NO_GO for step 1 of #1050: no asymmetric critic with encounter lists. Step 2 via the privileged critic (issue
comment) is dropped with it, as the revised order there says. Independent of this, confirming §758's counters-only
price table on new seeds remains open. No default change.

## Cost

About 70 min of PC CPU (3 fits 30 min, evaluate 36 min, gate 5 min), no GPU, no seeds, no cloud core-hours.
