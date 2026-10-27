# #881 shared OOC root cohort (data only, never merged)

- Replays of 16 already-used §683 MAP seeds 111374100-111374115 (no new seeds; Philipp's go 2026-10-27 20:37Z).
- Code `3bfca325` (branch `claude/project-thread-041hok`), binary sha256 in `SHA256SUMS`; student_sel `cf6bf7fb…`.
- Env: `replay.env` (= `docs/experiments/evidence/ooc_sibling_noise_bias_20261027/replay_unit.sh`: the §695 replay env,
  i.e. §683 MAP config + `STS_SILVER_ACT4_STRONG=0`, plus `STS_CALLING_BELL_CARD_RNG_FIX=0`,
  `STS_OOC_CAMPFIRE_PRICE_SCREENS=all`, `STS_OOC_CAMPFIRE_PRICE_TOP=3`, N = 32). Games stopped at their first act-4 state.
- `trace_check.txt`: all 16 replays reproduce their §683 MAP trace row for row (prefix up to act 4).
- `roots.jsonl.gz`: one row per priced OOC root (1,872 roots with >= 2 priced actions; acts 1-3).
  Identity = `seed` + `decisionIndex` (the run driver's OOC decision index, as in the trace) + env + binary.
  `screen`, act, floor, HP, gold, `legalActions`, the public heart1 `record`, and for the top-3 student_sel-prior
  actions: key, label, prior, 32 `leaf` values (the search's own leaf: rollout3 + M0) and 32 `actEnd` values
  (rollout to the act's end valued by M0; deaths 0), stream r shared by all actions within a kind.
  `core: true` marks the frozen core set: up to 8 roots per type (sha1(seed:decisionIndex) order, one per seed
  first) for expensive follow-ups (#882/#884/#886).
- `replays-3bfca325.tar.gz`: raw replay traces, CTM rows, price rows, env, logs.
- 68 roots logged `OOC MCTS actions requested at leaf` (no search candidates, e.g. rule-forced sites); not in roots.
