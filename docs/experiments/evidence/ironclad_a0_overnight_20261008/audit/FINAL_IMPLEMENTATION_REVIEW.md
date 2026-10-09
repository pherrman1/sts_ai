# Final implementation and verification-scope review

**PASS for draft-PR handoff, with the verification limits below. No new source blocker or additional check is requested.** This is a read-only consolidation of the campaign's independent source reviews, executed verification receipts and cumulative implementation diff. It makes no final-confirmation efficacy claim. The reviewer did not inspect confirmation outputs, repeat a test, launch a game, change source or modify a frozen input.

The reviewed implementation spans `a4b3df35d170abba7860e8e854cc24cfd3579075` through `5add2413281c95a29e32846531d41353c804fd3c`. All 21 changed source/test/CMake files in the current worktree exactly equal the latter commit. The accompanying [machine receipt](FINAL_IMPLEMENTATION_REVIEW.json), SHA256 `7a98d593daf78ac778c5a48fada0b45f25c615a2244e0c7c2e8e098689d91e45`, binds the cumulative implementation diff and 235 rehashed source, documentation, review, binary, log and completed-canary input files. No hash mismatch was found.

The immutable confirmation producer is **`d35b42b1d5dc9819ec0f157027c68912bb82b8b7`**, binary SHA256 **`1dcc79169e60cc58865218cd66644dd2db61a9e9ceaafdf39c1b8a7b6600a8f5`**. Both confirmation arms use that producer; the nominated treatment is the removal-ranking flag. The later CardWinRank implementation at `5add2413`, binary `85552690f7455c40e70d08a812dd631254313a287a511b939a06afed8587e907`, is included in the research draft but is **not** the confirmation producer. Its checks must not be presented as the source identity of that trial.

## What was tested, at which source

| Source | Executed evidence inspected and rehashed | Scope limit |
|---|---|---|
| `a557ace5` | Integrated Debug build; **67/67** CTest `core\|smoke`; **2/2** additional `vwin_refresh_policy_export` and `silver_semantic_action` | This precedes FullHp, RemoveLow and CardWinRank. It is not a full-suite pass at either later producer. |
| `b229f3ff` | FullHp fixture; Recall regression; Release producer self-test; unset/off/on/bad startup and teacher-export checks; five runtime canaries | Later eligibility logic has focused, source-specific coverage. |
| `d35b42b1` | **3/3** Recall/FullHp/removal fixtures; Debug and Release builds; producer self-test; four startup/export cases; four runtime canaries | This covers the producer used for final confirmation; it does not claim a repeated broad 67-test run. |
| `5add2413` | **3/3** CardWinRank/shop/public-futures fixtures; Debug and Release builds; producer self-test; 17 startup/export cases; three runtime canaries | These checks cover the unused CardWinRank extension and its affected public scorer interface. |

The earlier broad run includes public-futures, shop bookkeeping, Recall, Silver search/wire and GEN2 producer/continuation tests. The separate public pair-probe build, check, two cost/contract canaries and completed diagnostic were independently reviewed through their own receipts; the standalone helper is not a gameplay backend or an untested implicit dependency of `one_combat`.

The source-review chain is independent across authors: strategy reviewed the integrity-authored final-boss evaluator, bounded Champ helper, removal ranking and CardWinRank helper; integrity reviewed strategy's public scorer, shop correction, targeted GEN2, Recall and FullHp changes and the coordinator's integration. Earlier review documents deliberately retain preparation-time pending gates. Later executed receipts close those gates; those historical documents should not be relabelled as final runtime receipts.

## Default-off and diagnostic neutrality

The corrected source's disabled capture and active capture agree with the earlier named source on gameplay, 123 OOC trace rows and 326 tree rows; only the process-scoped combat identifier is excluded. All 72 targeted public captures were valid. The public wire uses isolated seed zero and records the source seed only as an outer replay locator.

FullHp default-off parity covers 177 trace and 454 tree rows on the smoke source. Removal default-off parity covers that smoke and the named source's 217 trace/519 tree rows. Its enabled native-shop-only smoke remains identical, while a matched public Living Wall root exposes the intended Shrug-versus-Strike removal change. Bonfire isolation is established by source and actual-transition fixtures, not inferred from diverged trajectories.

CardWinRank default-off again matches the 177/454 smoke. Trace on/off agrees on 196 trace rows, 610 tree roots, gameplay, strategic decisions, profile counts and 50 public scorer calls. Its 20 score rows all took a card, with nine local ranking differences. **The runtime canary did not expose the skip branch**; skip preservation, ties, negative win marginals, finite-value failure and source/RNG purity are covered by the focused fixture. Timing fields and the process combat identifier are the declared parity exclusions, not arbitrary differing gameplay fields.

These are bounded integration checks, not a proof of equality for every possible state. No production default was changed. Each research flag remains off when unset, and enabled policy-changing flags are serialized into the teacher identity. Diagnostic trace flags do not silently alter that identity or add predictions/search.

## Interface risks and maintained knowledge

No uncovered material regression was found in the reviewed scope. The remaining boundaries are substantive and belong in the draft:

- Legacy native OOC defaults still expose the inherited encounter-identity features when public marginalization is off. The controlled public8 profile disables incompatible actual-RNG hypothetical paths. Public8 preserves source RNG and shares scenarios across candidates, but does not establish an exact joint posterior or retrospectively qualify historical results.
- Recall and FullHp filtering cover the declared policy owners. Forced-only Recall remains legal and retained; enabled filtering can change random bounds and the V4 margin gate. FullHp is an experimental eligibility rule, not proof that every upgrade helps.
- RemoveLow is an acquisition-weight ordering hypothesis. It preserves the existing legality/index/sort machinery and Bonfire objective, but does not newly solve upgraded basics, curses or contextual synergy. The unchanged native shop owner remains separate.
- Shop and CardWinRank use approximate feature edits. The CardWinRank returned-value checks rely on normal model-loader validation; they do not rescan arbitrary corrupted in-memory trees. The final-boss binary objective has its own A0/Act3/exact-budget guard and is not enabled in the nominated configuration.
- Targeted GEN2 is opt-in and receipt-bound. Its source replay, retained alternative set and disjoint future ranges are not a general historical replay facility. The public Champ probe supports one bounded wire state and a fresh exact-10,000 continuation controller; it does not reconstruct historical private RNG, the original retained tree, or Act-3 strength.
- Completed full-run health audits found no fatal error, descent-abort or nonterminal contract failures. They did record engine-stop and turn-limit diagnostics. Neither implementation validity nor the final packet should claim that all search safety stops were absent.

The current working snapshots of `CODE_MAP.md`, `combat-search.md`, `out-of-combat.md`, `current-baselines.md`, `environment-variables.md`, `ooc-label-pipeline.md` and `build-and-debugging.md` match these boundaries. In particular, the new combat subsection correctly separates public capture from a private snapshot and the bounded helper from the original controller. The CI documentation now matches the actual workflow's `core|smoke` selection and draft exclusion. Final staging/link and repository-health checks remain the coordinator's packaging responsibility; this review binds the inspected documentation bytes rather than approving later edits automatically.

**CI is not established by this review.** The current Linux GCC workflow skips draft pull requests. Local checks are not an authoritative GitHub Actions pass. No live-game qualification was performed, and this review authorizes neither merging nor changing defaults. Final confirmation remains blind to this audit; its complete validity and efficacy report is a separate handoff requirement.

Knowledge impact: current interface and fairness facts are reflected in the maintained KB; experiment results and negative evidence remain in the campaign/ledger packet. This review itself is an evidence-scope receipt, not a new production decision.
