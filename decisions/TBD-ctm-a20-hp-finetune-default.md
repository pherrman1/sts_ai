# ADR-TBD: The A20 CTM stack uses the HP-head fine-tune with its own calibration table by default

Date: 2026-10-24
Status: accepted

## Context

- **The candidate** (§672, `docs/experiments/evidence/ctm_finetune_20261023/`).
  `models/candidates/ctm_finetune_hp_pathb_a20_v1.native` (`bdbfafa6…`) is the §470 fast artifact (`ae785ec2…`) with
  its HP head fine-tuned on the 97,561 real fights of the stage-3 A/B. Only the five HP-head tensors differ, so it
  predicts the same deaths (`p_death` byte-identical on all 103,583 fights of §670).
  - Its research manifest is `models/candidates/ctm_finetune_hp_pathb_a20_v1.manifest.json` (`31bb21f7…`).
  - Its table `models/candidates/ctm_calibration_pathb_a20_ft_hp_v1.json` (`8c226f23…`, 34 groups) was refitted on
    its scores of the same fights. The table's death shifts equal ADR-0058's, so calibrated deaths do not change
    either.
  - On the 6,022 held-out stage 1–2 fights it took won-fight HP error from 7.60 to 7.45 against ADR-0058's
    arrangement (old net + its table). The OOC stack could not load it: its fast artifact path was fixed.
- **Fresh fights.** The guard of §676 played 1,024 games (512 seeds, both arms) between 23:25Z on 2026-10-23 and
  02:21Z on 2026-10-24, after both the fine-tune and its table were frozen, so neither has seen their 24,186 real
  fights. There (this change's evidence, `docs/experiments/evidence/ctm_finetune_default_20261024/`):
  - death log loss 0.0660 for both, deaths identical;
  - won-fight HP error 7.75 → 7.59, −0.16 [−0.20, −0.12] (95% seed bootstrap); mean HP bias −0.11 → +0.04;
  - the gain sits at bosses and late elites: Act-3 bosses 16.50 → 15.40 (Awakened One 19.19 → 17.24), Act-2 bosses
    17.07 → 16.57, Shield and Spear 18.21 → 17.29;
  - the Heart gets slightly worse (18.45 → 18.58, bias +0.16 → +3.56), which the search cannot use: a won Heart ends
    the run. Two small groups get worse by less than 0.05.
- **The criterion.** On 2026-10-23 at 20:32Z Philipp set the yardstick for the CTM: precision, not winrate. On
  2026-10-24 at 07:52Z he wrote: "Merge 849. And I already told you. Don't qualify ctm by winrate but by precision,
  so the new one goes in as default". The fine-tune's author recommended the fine-tune with its own table. The ADR-0058
  table was fitted on the old net's HP and must not be paired with the fine-tune.

## Decision

- `STS_CTM_A20_HP_FINETUNE` selects the built-in A20 CTM stack:
  - unset or `1`: the fine-tune stack. This is the §470 stack (Brew fallback `e338506d…`, Lizard correction, §470
    boss shift, ADR-0048 Act-4 model) with the fine-tune as its fast artifact. Its built-in identity is the
    fine-tune's research manifest (`31bb21f7…`), embedded in the runtime byte for byte;
  - `0`: the §470 stack as before (fast `selfplay/models/combat_transition_deepsets_pathb_a20_lizard.native`, built-in
    manifest `00bb4da6…`);
  - any other value is fatal wherever the A20 stack is built. The switch is read once per process.
- Everything that builds the A20 stack follows it: the OOC MCTS A20 stack (offline runs and data generators), the
  CTM self-tests and the live advisor's release.
- An artifact that declares `pathb-a20` and loads without a research manifest resolves to the selected stack and must
  be one of its artifacts. Under the default the §470 fast artifact is refused, and under `=0` the fine-tune is
  refused, with an error that names the switch. A research manifest still names its own artifacts under either
  setting.
- **Default table.** ADR-0058's rule now holds per stack: with `STS_CTM_CALIBRATION` and `STS_CTM_ACT4_SURVIVAL_MODEL`
  unset, a runtime whose identity equals the fine-tune manifest applies `ctm_calibration_pathb_a20_ft_hp_v1.json`, and
  one whose identity equals the §470 manifest applies `ctm_calibration_pathb_a20_v1.json`, also under a research
  manifest with the same content. Each table is pinned by its sha256 and looked up as ADR-0058 says. The table
  follows the identity, not the switch, so the fine-tune never gets the ADR-0058 table by default. `0` and a path
  keep their meaning.
- The OOC MCTS banner `[ctm-a20-stack]` ends with `hp_finetune=0|1`; the run header's `ctm_a20` entry names the fast
  artifact and its sha256.
- **Live.** `tools/live_game_runtime.py install` ships the fine-tune as `models/ctm_finetune_hp_pathb_a20_v1.native`
  with its table, named in the release manifest by `ctmCalibrationName` and pinned by `ctmCalibrationSha256`.
  Validation accepts only matching pairs: the fine-tune with its table, the §470 artifact with the ADR-0058 table or
  without one, so releases installed before this change stay valid.

## Consequences

- **Play changes** at A20 under OOC MCTS wherever the search imagines a fight, through the predicted HP after won
  fights (deaths are unchanged): offline runs, data generators on the production OOC stack, and live play after a
  reinstall, which needs Philipp's typed OK. Real combats are Silver's and do not change.
- **Not measured:** playing strength. By Philipp's criterion there is no winrate guard.
- **Older runs** reproduce with `STS_CTM_A20_HP_FINETUNE=0`, and also `STS_CTM_CALIBRATION=0` for runs before
  ADR-0058. Freeze files must record the setting. Scripts that pass the §470 fast artifact to `ctmscorerows` without a
  research manifest now need `=0` (or the `00bb4da6…` research manifest); otherwise they fail with the error above.
- **Coupling.** The table was fitted on the fine-tune's predictions with the §470 shift and the ADR-0048 Act-4 model,
  on fights before the 2026-10-23 engine fixes (#831, #833, #835, #836). A retrained CTM or Act-4 model needs a refit.
- ADR-0058 still governs the §470 stack under `=0`. This decision is the one its "Next candidate" left open.

## Evidence

§672 (`docs/experiments/evidence/ctm_finetune_20261023/`), §676 (the guard), and this change's evidence
(`docs/experiments/evidence/ctm_finetune_default_20261024/`): precision on the guard's fresh fights and on the
held-out fights, offline equivalence (the default equals the reviewed research flags, `=0` equals main), and a game
check on guard seeds.
