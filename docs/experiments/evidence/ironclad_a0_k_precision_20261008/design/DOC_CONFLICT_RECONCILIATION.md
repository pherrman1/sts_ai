# Documentation synchronization proposal

Review only: no merge, canonical documentation edit, build, game, outcome analysis or publication was performed. The inspected task head is `54c97fd0995c043ca584e75ff6af6da2fb032cf3`; incoming main is `70f7dfe5781a25b06caca49ae404b62208a81ad9`; their base is `a4b3df35d170abba7860e8e854cc24cfd3579075`. The parent’s virtual merge tree is `d93639aea12192eda354ac5ebfc07ce45efe83b1`.

## Recommended reconciliation after closeout

Wait for dispatch completion, all game processes to stop, and hash-bound blocked accounting and its review to finish. Then synchronize the task branch with the inspected main using a conventional merge, preserving local/untracked evidence. This is task-branch synchronization, not a PR merge or default promotion. Recheck the current main identity and frozen artifacts immediately before and after; investigate any discrepancy before continuing.

Resolve the three textual conflicts as follows:

| Path | Minimum natural resolution |
| --- | --- |
| `EXPERIMENTS.md` | Combine the ledger-06 row so it mentions both §395 (the closed fair OOC campaign) and main’s §396 (E3), then §397 only when the K-precision closeout entry is ready. Retain the remaining historical index text and current-shard routing. |
| `docs/experiments/ledger-06.md` | Keep §395 verbatim, followed by main’s §396 verbatim. Append the separate K-precision attempt as §397 after final metadata accounting. Main has §396 and no §397; do not renumber either earlier campaign. The old §395 “next experiment” paragraph is a historical proposal: retain it, adding a short link to §397 rather than rewriting the original proposal as though it had already run. |
| `docs/knowledge-base/operations/ooc-label-pipeline.md` | Keep our expanded GEN2 CLI, actual-k/FUTURE_START and teacher-budget explanation, and targeted REST preflight/binding contract. Keep main’s E3 analyzer paragraph verbatim in the same GEN2 section, before or after the targeted subsection with a clear heading boundary. E3’s historical invalid-sibling filtering does not override the new K-precision experiment’s frozen all-32-source validity requirement. |

The natural ledger order is §395 → §396 → §397. §397 must say `EXECUTION_BLOCKED`, identify the timeout and final accounting, and state that neither selector choices nor a numerical primary comparison were released. Its cost totals must come from the completed metadata accounting; do not infer them from the partial source. Keep the closed RemoveLow result separate. No new E3 numerical interpretation is needed: preserve its existing published entry and links.

Simply copying main’s overlapping insertion text and concatenating ours at the same boundary does **not** make a three-way merge clean. Temporary-file `git merge-file` checks against the actual base reproduced conflicts for both ledger orderings, the main index row plus adjacent note, and both placements of the GEN2 insertions. No temporary candidate was written to a canonical path. Moving ledger entries out of order, inventing a new shard, or restructuring documentation solely to game the merge is unnecessary; the conventional post-closeout resolution is clearer.

## Frozen-artifact and source impact

All 21 `freeze.json.artifacts` entries were independently rehashed and matched. Their intersection with main’s changed paths is empty. The immutable corrected producer binary, teacher, policy and corrected runtime protocol also match and are not changed by main. The companion JSON binds every digest and all incoming changed paths. Keep the original freeze and initial freshness inventory unchanged.

Main’s shared `one_combat.cpp` and `driver_shared.h` changes add CTM feature-export modes. The adapter change bypasses initial Smoke Bomb masking for an explicitly escape-capable CTM. Further main changes are in CTM contracts/runtime/samplers and offline tooling, plus E3 analysis/tooling and documentation. **Inference:** these are outside the frozen non-MCTS policy path, but a clean textual merge is not proof of integration correctness. The experiment used the immutable `3ed91ab3` producer; the earlier final trial used `d35b42b1`. A newly merged executable has a different identity and does not inherit gameplay qualification merely from either result.

After resolving the merge, configure/build `one_combat` and `combat_transition_runtime_probe` in an ordinary integration build directory, leaving all frozen binary directories intact. The cheapest relevant checks are the new CTM capability/escape/Lizard unit tests and runtime-loader fixtures, existing `ooc_mcts_adapter` and `ctm_offline_score_rows`, GEN2 `vwin_refresh_producer_contract`/policy export, and the campaign’s public-future, shop, Recall, full-HP REST, removal and card-ranking fixtures. Run the E3 synthetic self-test rather than any corpus analysis. Reuse the repository’s guarded CTest commands for fixtures that initialize simulator states; none of these recommendations authorizes new experimental cohorts. Broaden checks only for an actual failure or remaining integration concern. GitHub’s `Linux GCC` core/smoke job remains authoritative repository CI; it is skipped on draft PRs, so a draft handoff must state that limitation rather than claim CI passed.

## Concurrent E3 allocation supplement

Main’s E3 `PREREG.md:16` explicitly reserves 55,000,000–55,000,999. Its `BRIEF-cloud.md:9–10` distributes exactly the same interval as 25 workers × 40 sources; the shell command at line 28 agrees. These are disjoint from K precision’s 610,084,200–610,084,231. The old preregistration’s four-thread 250-source wording and later 25-worker brief describe different dispatch layouts over the same fixed allocation; neither implies a collision.

This is a bounded supplement from allocation documentation on newly fetched main. It does not expand the original freeze’s claim beyond its inspected 799 prior receipts and 17 job lists, does not independently certify E3 execution coverage, and does not touch E3 TEST/raw numerical data. The supplement does not change the already-blocked primary’s status or authorize substitute sources.
