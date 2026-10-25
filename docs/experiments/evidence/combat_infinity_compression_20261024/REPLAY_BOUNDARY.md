# Counterfactual replay boundary and minimal next design

The offline gate passes, so OOC_COMPRESSION_HEADROOM_LOW is **not** the result.
The strongest clean reward-skip intervention is frozen in INTERVENTIONS.json:
seed111101326,13 specified non-engine reward groups, structural31 ->18. No
counterfactual or oracle execution occurred. The reviewed historical capture
at b94a96da is the retained control; it was not rerun.

The exact historical executable has no supported way to install this multi-step
skip-only intervention into its Heart/Student-C/MCTS real-run loop. Source
inspection at d8fd2a105a8d establishes:

- apps/one_combat/run_driver.cpp:424–552: runFullRunOOC runs the Heart key/rule/
  Student-C/MCTS chain directly; no manifest/forced-semantic-action input is read
  before dispatch. STS_OOC_DECISION_TRACE and STS_OOC_MCTS_ROOT_TRACE are outputs.
- apps/one_combat/strategic_gen.cpp:504–559,706–718: STRATEGIC_MCTS_FORCE exists,
  but only in strategicgen2. Unforced real-run steps use deployedOocPolicyStep,
  which calls runFullRunOocPolicyStep directly (run_driver.cpp:391–405), bypassing
  the historical top-level Student-C/MCTS dispatch. Its MCTS evaluations are
  separate diagnostic searches; primitive decision indices also differ.
  Using it would silently substitute the control policy. Forcing all historical
  downstream actions would violate natural downstream policy and path freedom.
- apps/one_combat/ooc_mcts_adapter.cpp:2900–2946,2973–3068: replay/stability probes
  require A20 native4096 rollout3 V4 teacher and explicitly reject heart1 prior/
  leaf policy. Stability additionally pins seed87000000 and its fixed leaf plan
  (lines122–163). They are not a receipt-compatible intervention route here.
- apps/one_combat/semantic_pilot.cpp:39–80,165–182: semantic pilot uses a different
  A0 source loop and forces one sibling before a bounded continuation, not13
  scheduled overrides under the historical full-run controller.
- forkLeafReplay (ooc_mcts_adapter.cpp:275) is an internal isolation primitive,
  not an external CLI callback that can be configured in the exact executable.
- STS_FORCED_MOVE is only listed in environment diagnostics; no source read
  implements an OOC manifest override.

No new flags were invented, no debugger/preload injection was attempted, and no
current policy or alternate generator was passed off as the historical control.
There is therefore no honest counterfactual trajectory result, active-pool delta,
survival tradeoff, candidate or certified kill to report from this task.
None of the four requested empirical decision labels is established: headroom
is not low, while the other three require an executed intervention.

## Smallest proposed design, not implemented

A research-only one-shot skip-manifest runner, **not a beam search**:

1. Reuse the frozen source/model setup and runFullRunOOC. Install a narrowly
   scoped pre-dispatch callback only from a research entry point; ordinary
   production execution leaves the callback unset.
2. Match seed + act/floor + exact public reward-group semantic identity from
   INTERVENTIONS.json; enumerate with enumerateOocSemanticActions, verify the
   exact SKIP_CARD_REWARD sibling, execute with executeOocSemanticAction. At most
   the13 frozen triggers, each at most once. No dynamic additions or target
   selection using later states, outcomes or oracle results.
3. If no trigger matches, execute the existing historical controller unchanged.
   Do not repair path/deck/decisions; log unmatched triggers and engine loss or
   death. Preserve the original public/OOC capture paths and single run receipt.
4. Reuse existing witness adapter only after a materially compressed actual
   state exists; K4 and all bounds remain untouched. No repeated branch futures,
   alternate seeds, rollbacks, beams, value ranker or new simulator.

This requires an explicit execution-contract decision: adding an entry point/
callback produces a **different executable hash**. It cannot truthfully satisfy
“use the exact historical binary” merely by sharing source. A no-intervention
parity qualification would also be new execution, beyond the instruction that
the existing control needs no rerun. Neither was implemented or launched.
The bounded accounting and a reviewable frozen intervention are complete; stop
at this runtime/authority boundary rather than invent a counterfactual result.
