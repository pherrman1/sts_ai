# Integrity/combat hypotheses

All candidate quality statements require a repaired public-information
baseline. These are ranked mechanisms, not successful findings.

| ID | Question and competing explanation | Evidence | Single intervention and controls | Distinguishing result / decision | Cost, owner, status |
| --- | --- | --- | --- | --- | --- |
| I1 | Are native OOC decisions using actual hidden encounters? Alternative: caller already redraws them. | Direct real-gc fallback chain and 12,528 floor-tree / 1,370 win-tree splits across four hidden features; no redraw on call paths. | Opt-in common sampled encounter futures before candidate scoring; models/schema/all other settings fixed. | Hidden-only changes must leave candidate scores/actions identical; state/RNG unchanged. Required integrity gate, separate from win-rate benefit. | Small implementation + deterministic fixture, strategy; running. |
| C1 | Does final-boss resource/shaped-loss utility hurt actual Act-3 wins? Alternative: useful tactical guidance outweighs misalignment. | evaluateEndState values leftover potions, death saves, gold/maxHP, speed, and loss turns at final boss; actual endpoint is binary victory. | Opt-in A0 Act3 boss only victory100/otherwise0, fixed exact10k search and public Bflat. | First fixture confirms objective dominance/default neutrality; paired discovery actual-win gain earns development evaluation, regressions reject. Final result still needs reserved confirmation. | Minimal patch, no new model, integrity implements and strategy reviews; running. |
| I2 | Does native shop planning score impossible deck sizes? Alternative: redundant deckSize column is intentionally ignored. | nativeShopPlan increments deckSize for relics and misses removal decrement; floor model has 4,123 deckSize splits. | Opt-in repair of card-add/removal arithmetic only; compare synthetic model decisions with legal successor feature vectors. | Baseline failing / repaired passing deterministic fixture establishes defect; paired gameplay determines strength, not bug existence. | Small fixture/patch, strategy; proposed. |
| C2 | Are Bprod losses caused by premature learned stops? Alternative: terminal objective or preparation dominates. | Historical Bflat difference was uncertain; current stop model and mechanics need fresh comparison. | Public Bprod versus public Bflat, same models/OOC; retain per-root steps and stop categories. | Current paired full-run difference and matched-entry replay classify budget headroom; do not infer from more steps alone. | Baseline wave already required, coordinator; proposed. |
| C3 | Are difficult roots harmed by one search trajectory rather than total compute? Alternative: poor entries remain poor for all fair searches. | Existing bossrescue347 supports independent planner seeds and exact source reproduction; #425 mixed 10k/40k rescue. | At matched current entries compare independent-search ensemble to one search with equal total simulations, semantic-action alignment fixed. | Independent continuation evaluation must favor ensemble beyond seed-clustered uncertainty; same rollout-selected futures cannot evaluate it. | Moderate implementation/capture cost; defer unless current loss-linked case, integrity; proposed. |
| C4 | Does 32,768-node graph compaction discard useful structure at hard roots? Alternative: fresh search is beneficial or only root budget matters. | NativeSilverBackend compacts on reroot when nodeCount reaches fixed cap and resets if still over cap. | One opt-in cap policy at fixed exact budget, only after current tree profiles show repeated cap hits near supported failures. | Retained structure plus paired actual outcome improves; memory/steps reported. Counterexamples/negative current evidence reject before broad sweep. | Targeted profile first; no broad #400 tuning, integrity; proposed. |

Rejected as campaign novelty: global OOC MCTS presumed stronger; broad
Silver exploration/widening sweep; global v_win terminal replacement or
hallway potion price reduction. Current source/history already contradict
those starting assumptions (#417, #400, #422 respectively).

The deployed learned-stop model is `gbt-770201c31f7b`, default threshold
0.0323, compiled in NativeSilverStopModel.cpp. A changed terminal score
distribution must not silently inherit this model's qualification. C1 is
therefore exact-budget only and fails startup if learned/adaptive/stop-trace
mode is requested.
