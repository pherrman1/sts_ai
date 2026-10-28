# Smoke (2026-10-27, seed 111374100, act 1 only via STOP_ACT=2, R = 8)

Code `8ece111d` (before the arm-order shuffle, which only reorders the arms inside the forked child).
- Capture without arms vs with all five arms: the policy JSONL (129 lines) and the CTM rows (11) are identical after
  removing timing fields, so the arms do not change play.
- 121 capture rows (reward and map roots), every arm valid, no `extraError`.
- sw differs from base on 968/968 repeats (the survival weight is applied); base had 1 death in 968 act-1 rollouts.
- First smoke attempt used `STS_STOP_AFTER_ACT=1`, which heartoutcomegen refuses ("heart outcomes require normal
  full-run Heart objective"); the run script now stops the game from outside at the first state of act `STOP_ACT`.
- CPU per arm looked order-dependent (an arm following a similar arm ran faster), hence the shuffled arm order.
