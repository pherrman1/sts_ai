# Native parity (`one_combat` at this branch, linux-gcc-release)

- `ctmscorerows rows.jsonl … pathb_a20 … 0` (active Lizard off) with `STS_CTM_ACT4_SURVIVAL_MODEL` set: on all 5,123
  scored rows (344 Lizard Tail rows are unsupported without the correction), max |native `p_death` − Python| =
  7.8e-7. The HP columns (`expected_win_hp`, `log_p_post_hp`) are byte-identical to the run without the variable.
- With active Lizard on (the deployed setting), the 344 Lizard Tail rows go through the existing active-Lizard
  mechanics: the model is asked for `withoutLizard(p)` and the reserve HP input, so its own Lizard Tail feature is not
  used there. On TEST this as-deployed form scores Heart BCE 0.375 (Python form 0.381, incumbent 1.648) and Shield
  and Spear 0.294 (0.298, 0.318).
- CTest `ctm_act4_survival_parity` (16 TEST rows, 8 per fight, `tests/fixtures/ctm_act4_survival_parity.jsonl`): PASS.
