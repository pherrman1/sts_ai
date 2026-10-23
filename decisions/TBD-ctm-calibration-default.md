# ADR-TBD: The A20 CTM stack applies the per-fight calibration to today's Silver by default

Date: 2026-10-23
Status: accepted

## Context

- **The check** (§670, `docs/experiments/evidence/ctm_calibration_20261023/`). Over the 97,561 real fights of the
  stage-3 A/B, the deployed A20 CTM stack (`pathb-a20` with the Lizard correction, the §470 boss shift and the
  ADR-0048 Act-4 model) predicts too many deaths at most bosses: the Heart 0.486 against 0.370 observed, Act-1 bosses
  0.093 against 0.050. It also predicts too much HP loss in Acts 2–4; after a won Act-3 boss fight its HP is 19 too
  low.
- **The table.** `models/candidates/ctm_calibration_pathb_a20_v1.json` (sha256 `359619f7…`, 34 groups, fitted by
  `tools/ctm_calibration.py`, λ = 2) shifts each group's death logit and scales its HP losses. It predicts held-out
  fights better:
  - out of sample, death log loss 0.0731 → 0.0685 and won-fight HP error 8.46 → 7.66;
  - on the 256 held-out stage 1–2 games, 0.0733 → 0.0698 and 8.23 → 7.60, with the Heart at 0.358 predicted against
    0.337 observed (0.458 before);
  - weak spots: Act-1 bosses got worse on the held-out games (log loss 0.2016 → 0.2107), and below 20 HP Act-3 fights
    look safer than they are (0.43 predicted against 0.47 observed).
- **The criterion.** On 2026-10-23 at 20:32Z Philipp argued that the CTM should be judged by its precision, not by
  winrate: winrate follows from good labels, which need a precise CTM. At 20:44Z he chose "Default on + 512-seed
  guard" on the card "Adopt the CTM calibration on precision, and with what play check?": the default now, a 512-seed
  A20 guard against the old CTM, and only a clear loss sends it back to off. At 20:45Z he authorized the 512 seeds on
  8 workers, and at 22:11Z on 16.
- **Play so far.** A 10-seed smoke of the A/B script leaned against the calibration (Heart kills 3 without, 2 with;
  `SMOKE.md`). Ten seeds are no evidence.

## Decision

- With `STS_CTM_CALIBRATION` unset, every CTM runtime of the built-in A20 stack applies the bundled table. Both
  conditions must hold:
  - the runtime's identity equals the built-in calibrated `pathb-a20` manifest (`00bb4da6…`, §470), as when it loads
    without a research manifest;
  - its Act-4 survival model is the ADR-0048 default (`STS_CTM_ACT4_SURVIVAL_MODEL` unset), because the table's Act-4
    groups correct that model.
- The table is looked up next to the executable first (an installed live release's `models/candidates/`), then under
  the working directory. Its sha256 must be `359619f7…`; a missing file or other bytes are fatal. It is loaded once per
  process, when the first such runtime is built, and logs `[ctm-calibration] table=… sha256=… groups=34
  scope=pathb-a20`.
- Other runtimes are unchanged: the A0 stacks, research candidates under another identity, and every runtime when
  `STS_CTM_ACT4_SURVIVAL_MODEL` is set. A research manifest that keeps the candidate id `pathb-a20` with other
  artifacts, such as the fine-tuned `ctm_finetune_hp_pathb_a20_v1`, is another identity; its own table is set by path.
- `STS_CTM_CALIBRATION=0` restores the uncalibrated CTM.
- A path stays the research option (§670): that table applies to every runtime of the stack it names.
- **Live advisor.** Its A20 stack applies the bundled table under the same rule and reports it as
  `ctmStack.ascension20.calibration` (`off` with `=0`). An explicit path is refused, as before.
- `tools/live_game_runtime.py` copies the table into qualified-CTM releases and pins its sha256 in the manifest as
  `ctmCalibrationSha256`.

## Consequences

- **Play changes** at A20 under OOC MCTS wherever the search imagines a fight with the A20 CTM: offline runs, data
  generators on the production OOC stack, and live play after a reinstall, which needs Philipp's typed OK. Real
  combats are Silver's and do not change.
- **Older runs** reproduce with `STS_CTM_CALIBRATION=0`. Freeze files must record the setting.
- `ctmscorerows` on the A20 natives now reports calibrated predictions; `=0` reproduces the raw CTM. A retrained or
  fine-tuned CTM is compared against the raw CTM with `=0`.
- **The guard** (`docs/experiments/evidence/ctm_calibration_20261023/PREREG.md`): 512 paired A20 seeds
  (111392000–111392511), `=0` against the default. If it comes out WORSE (the CI's upper bound below 0), a PR turns
  the default off. Otherwise the default stays. A loss of about 2 pp would mostly go unnoticed at this size.
- **Unverified:** a playing-strength gain.
- **Coupling.** The table was fitted on the predictions of these exact artifacts with the §470 shift and the ADR-0048
  Act-4 model, on fights before the 2026-10-23 engine fixes (#831, #833, #835, #836). A retrained CTM or Act-4 model
  needs a refit; the bundled table does not follow it.

## Evidence

§670 (`docs/experiments/evidence/ctm_calibration_20261023/`: README, `offline/`, SMOKE.md, PREREG.md), PR #838, and
this change's equivalence check (`docs/experiments/evidence/ctm_calibration_default_20261023/`).
