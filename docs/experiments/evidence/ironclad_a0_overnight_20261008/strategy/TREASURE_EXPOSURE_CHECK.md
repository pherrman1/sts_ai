# Corrected-reference chest and reward-relic exposure

**DISCONFIRMED in the fixed outcome-unselected first12 reference cohort:** there is no observed free chest left closed or non-exception reward relic left behind by V4 TREASURE ownership. Source routing also prevents this particular mechanism in the controlled non-MCTS run driver. No experiment or implementation is justified by this exposure check.

The read-only check uses corrected Fprod sources610082000..011 from completed Wave2, not selected failures. All three raw trace hashes were verified against the frozen corrected atlas. `TREASURE_EXPOSURE_CHECK.json` records all39 chest roots and130 reward-relic-bearing rows with raw locators. Repeated rows are not independent offers: gold collection leaves an exception offer present for the following reward step.

| Observation | Count | Interpretation |
|---|---:|---|
| Chest without Cursed Key | 32 | All `by=chest_rule`, all transition TREASURE→REWARDS. No V4 ownership or skip. |
| Chest with Cursed Key | 7 | All opened; six V4-owned OPEN, one V4 decline then fallback OPEN. These are not free choices because they add curses. |
| Non-exception relic-bearing reward root | 112 | All `by=relic_rule`; an offered ordinary relic appears in the immediate inventory delta. No omitted offer. |
| Exception-bearing reward root | 18 | Nine repeated gold-then-relic sequences; all nine distinct exception offers eventually taken by ordinary `chain`. |

The rule's exception list remains Bottled Flame, Bottled Lightning, Bottled Tornado, Dead Branch, Tungsten Rod, Unceasing Top and Juzu Bracelet. “Exception” means **excluded from compulsory early collection**, not forbidden to collect. This distinction matters: `collectFreeOocReward` ordinarily collects gold, then any reward relic before reaching the card gate. In this non-MCTS profile, the observed Juzu, Top, bottled, Tungsten and Dead Branch exceptions are therefore taken. That is the inherited ordinary policy, not a new V4 TREASURE preference or a violation established by this inspection.

Executed routing inspected in `apps/one_combat/run_driver.cpp:249–278,284,447–456`: `openTreasureChestRuleStep` and `takeRewardRelicRuleStep` precede MCTS and the policy chain. The same checks also precede the nested full-run policy chain. `apps/one_combat/ooc_checkpoint_policy.cpp:12–39` explains ordinary exception collection; `apps/one_combat/ooc_policy.cpp:498` limits the TREASURE gate to the unopened chest screen. These two driver/reward files are unchanged from the frozen corrected producer3ed91ab3491a4cdc1a7de687b2ad87dcc7774fc0 through the current committed source, verified by a path-limited Git diff.

Concrete public locators:

- Source610082000 A1f9, idx28, `Fprod_0.trace.jsonl:36`: no Cursed Key; rule opens chest. Its earlier elite Anchor is taken at line26 by the relic rule.
- Source610082000 A3f43, idx139/140, `Fprod_0.trace.jsonl:162–163`: Juzu exception remains after gold and is then acquired through ordinary reward collection.
- Source610082010 A3f47, idx176/177, `Fprod_2.trace.jsonl:601–602`: Dead Branch follows the same gold-then-acquire sequence. This is an exposure, not proof that taking it is good or bad.
- Source610082005 A3f43, `Fprod_1.strategic.jsonl:115`: with Cursed Key the learned gate slightly prefers skip (Q78.303 versus78.2337) but its margin0.069328 declines ownership; fallback opens the chest (`Fprod_1.trace.jsonl:375`). No claim of error follows without an evaluated curse/relic tradeoff.

The historical #429 free-chest/relic omission mechanism is already intercepted before V4 here. A separate question about Cursed Key tradeoffs or whether an exception should be skipped remains possible, but this fixed cohort supplies no independently evaluated better action and authorizes no broader screen. The counts do not purport to audit all128 trajectories, live importers, arbitrary alternate policies, or the optimality of collecting each item.

Knowledge impact: completed campaign disconfirmation only; no runtime or maintained policy change.
