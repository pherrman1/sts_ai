# Optional Ruby Recall in keys-off random fallback

## Independent diagnosis

The named fair discovery root is Fprod seed 610081011, act 1 floor 12, `Fprod_2.trace.jsonl:651`. Only the root's pre/post public records and the non-outcome columns of strategic CSV row 197 were inspected. The root has 40/101 HP, unupgraded cards and no campfire-action relic. It moves directly from REST to MAP without healing or changing the deck.

The strategic record lists actions `0|1|2` with Q values `84.997|84.6851|81.0403`; its best-versus-second margin `0.311867` is below threshold `1.0`. `owned=0`, `takeIdx=-1`, `collectKeys=0` and `stopAfterAct=3` establish that the Q gate declined and the keys-off fallback controlled this decision. The trace does not serialize the Ruby key bit. Nonetheless, among the enumerated choices, REST would heal and SMITH would open CARD_SELECT, leaving Recall as the transition-compatible explanation. No source outcome or counterfactual result was used.

Source inspection confirms a policy/interface mismatch:

- `GameContext::keysEnabled` is true for ordinary generated runs and controls simulator legality. It is distinct from the policy preference `g_collectKeys`.
- `GameAction::getAllRestActions` offers Recall (primitive index 2) whenever game keys are enabled and Ruby is absent.
- `ScumSearchAgent2::stepOutOfCombatPolicy` enters `stepRandom` at this HP, because it only forces SMITH above 50 HP and REST below 15 HP when keys are off.
- `stepRandom` samples every simulator-legal action without consulting `g_collectKeys`.
- PR #431's filter is in the OOC MCTS adapter, covering TAKE_KEY and TAKE_RUBY_KEY. It does not cover the ordinary random fallback. Existing `keys_collect` fixtures test keys-on acquisition only.

## Minimal reproduction and repair boundary

`tests/rest_recall_filter_test.cpp` constructs a synthetic campfire directly using `GameContext{}`, one unupgraded Strike, HP40/101 and a MAP-return callback. It does not generate a run, map or fight. A deterministic agent RNG state selects index2 from `[REST,SMITH,RECALL]`; with the proposed flag enabled, the pre-fix implementation still acquires Ruby and the fixture fails. Coordinator compiled the fixture against the unchanged Debug source and captured exit1 with the exact failure `keys-off random REST fallback acquired optional Ruby Recall` in `build/overnight-recall-baseline-fail.log`. This confirms actual Ruby acquisition through the fallback; no game seeds were executed.

The authorized experimental repair is `STS_OOC_SKIP_OPTIONAL_RECALL=1`, default off. The shared `filterOptionalRecallActions` helper removes Recall from REST policy candidates with `g_collectKeys=false` only when another simulator-legal action exists. It is called by the random fallback and by the V4 REST gate before scoring. Preserve all other actions in their existing order; the random fallback invokes one uniform distribution over that filtered set. Unset/0 preserves the exact legacy action and RNG state. The enabled distribution has a different range; its standard-library rejection count may legitimately differ. No copied-RNG workaround or extra live distribution draw is required.

**Coverage exception:** Coffee Dripper plus Fusion Hammer, without another campfire option, can leave Recall as the sole simulator-legal action. Retain that forced legal Recall unchanged. Emitting SKIP would be illegal under the existing game state. The flag therefore removes optional key detours; it does not claim to disable game keys or prevent all key acquisition.

The isolated fixture additionally covers ordered uniform selection, default-off exact parity, keys-on behavior, keys disabled in the game, Ruby already held, resolved campfires, non-REST fallback and the forced-Recall exception. The implemented fixture also rejects empty, 2, -1, true, 01 and whitespace-prefixed flag values. Independent source review passed the initial fallback-only repair. The shared-helper extension has cpp+header diff SHA256 `ed94dabb48c78c0bea26f08ef455a4c15cc9636b71f4bc65023bb154345dc4b7`; direct helper assertions cover ordered `[0,1,2]` to `[0,1]`, unchanged forced `[2]`, and exact flag-off action identity. Independent review also passed the combined shared-helper/V4 integration and conditional teacher-policy binding. Repaired execution remains a coordinator gate.

With the shared helper connected to V4 REST scoring and the random fallback, both campaign REST owners exclude optional Recall. This scope depends on the frozen campaign profile: MCTS and REST_WIN are disabled. Other policy modes are not newly routed. Removing a candidate can change the V4 runner-up, margin and gate ownership even when V4 never selected Recall previously; this is a new policy reference and cannot reuse old numerical outcomes. Report observed key-action counts and preserve the forced-Recall exception rather than treating this flag as a blanket key prohibition.

Knowledge impact: experimental behavior and diagnostic evidence; production defaults remain unchanged. Gameplay win probability remains untested by this fixture.
