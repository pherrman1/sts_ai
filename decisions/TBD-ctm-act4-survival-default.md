# ADR-TBD: the A20 CTM stack prices Shield and Spear and the Heart with the Act-4 survival model

Date: 2026-10-18
Status: accepted

## Context

The calibrated A20 CTM stack (`pathb-a20`, ADR-0033, §470) never trained on an Act-4 row. On held-out A20 Act-4
labels it predicts a Heart death rate of 0.17 where the teacher dies 0.68 (§527). The §527 Act-4 survival model
(`models/candidates/ctm_act4_survival_trees.txt`, sha256 `05279b3c…`, opt-in via `STS_CTM_ACT4_SURVIVAL_MODEL`) is
calibrated on the Heart (0.70 predicted) but is not shown better on Shield and Spear. Its pre-registered gate is FAIL.

In the pre-registered A20 A/B (§534, 512 paired seeds, student_sel stack at 512 simulations) the model won 75 Hearts
against the control's 82. The result is NOT_SHOWN: McNemar p = 0.092, discordant pairs 3 vs 10.

On 2026-10-18 at 13:40Z, after seeing that result, Philipp chose "Default on + live" on the card "Turn the Act-4 CTM
model on by default for the A20 stack?".

## Decision

- With `STS_CTM_ACT4_SURVIVAL_MODEL` unset, every CTM runtime whose identity is the `pathb-a20` candidate takes the
  survival probability of SHIELD_AND_SPEAR and THE_HEART from the bundled Act-4 model.
  - The model is looked up next to the executable first (an installed live release's `models/candidates/`), then
    under the working directory.
  - It is loaded when that runtime is constructed, and a missing or invalid file is fatal.
- Other runtimes are unchanged, including the A0 stacks.
- `STS_CTM_ACT4_SURVIVAL_MODEL=0` restores the CTM survival head.
- A path applies that model to every runtime, as the §527 opt-in did.
- `tools/live_game_runtime.py` copies the model into qualified-CTM releases and pins its sha256 in the manifest as
  `ctmAct4SurvivalSha256`.

## Consequences

- A20 runs with OOC MCTS change from the first decision whose search reaches an Act-4 fight. Runs pinned to an older
  commit, or run with `=0`, stay as before.
- The live advisor changes only after a reinstall, which needs Philipp's typed OK.
- **Unverified:** a playing-strength gain. The A/B point estimate is −1.4 pp in Heart kills, CI [−2.7, 0.0].
- `ctmscorerows` on the A20 natives now reports the Act-4 model's survival on Act-4 rows; `=0` reproduces older
  scores.

## Evidence

§527, §534 (`docs/experiments/evidence/ctm_act4_ab_20261018/`), and PR #652.
