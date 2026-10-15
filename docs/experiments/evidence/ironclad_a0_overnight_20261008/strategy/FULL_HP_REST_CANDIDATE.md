# Full-health REST eligibility candidate

Recommendation: **separate bounded discovery screen warranted**, pending independent implementation review and focused runtime checks. This is an empirical policy restriction, not a simulator-legality repair or deterministic-dominance claim. No wave 2 outcome data was inspected for its design.

The motivating public source is seed 610081015, Act-3 floor 44 at 85/85 HP with legal upgrades and no Dream Catcher. The coordinator supplied the later inconclusive Offering 23/32 versus REST 17/32 contrast only as motivation; it does not qualify this rule or justify selecting an upgrade globally. The proposal was derived from the REST implementation and applies without a fitted score threshold.

## Source facts and competing explanations

`GameContext::chooseCampfireOption(0)` calls `playerHeal`, then creates a card reward only with Dream Catcher; otherwise it regains map control. `playerHeal` is a clamped HP assignment, or a no-op with Mark of the Bloom. At full health without Dream Catcher, no additional REST-choice benefit was found in the executed source.

Ancient Tea Set charges when the rest room is entered. Eternal Feather heals in `relicsOnEnterRoom`; Maw Bank's entry gold also precedes this choice. Regal Pillow only increases healing already capped at maximum HP. Those effects do not require choosing REST. Coffee Dripper removes legal REST; Fusion Hammer or a deck without upgradeable cards removes legal SMITH. The rule uses simulator legality rather than duplicating those restrictions.

The strongest mechanism is wasted full-health campfires under a learned REST gate. Competing explanations remain: the upgrade target controller can make poor choices; an upgrade can alter draw or search behavior; and some upgrades change semantics rather than monotonically adding value. For example, `doesCardExhaust` returns `!upgraded` for Limit Break, so its upgrade removes exhaust and can change exhaust synergies and future deck circulation. No source fact proves this policy wins more games.

Broad RestOff also changes damaged-player decisions and disables the learned upgrade-target gate. This candidate preserves those policies and restricts only the named full-health REST choice. It is therefore a distinct conceptual variable worthy of its own fresh paired discovery screen.

## Exact public rule and implementation

`STS_OOC_SKIP_FULL_HP_REST` is strict unset/0/1, default off. The public predicate requires all of:

- An unresolved `REST_ROOM`.
- Positive maximum HP and exact equality `curHp == maxHp`.
- No Dream Catcher.
- Simulator-legal REST and SMITH actions.

`filterFullHpRestActions` additionally requires that both legal actions occur in its supplied candidate vector. It erases REST only, keeping all remaining actions in their original order. It neither adds SMITH nor invents a legal skip. Forced/subset boundaries remain unchanged. Girya, Peace Pipe, Shovel and any eligible Recall stay in the vector.

The existing optional-Recall filter runs first, followed by this filter in the V4 REST gate and random fallback. Shared APIs are `oocSkipFullHpRestEnabled`, `oocFullHpRestExclusionApplies` and `filterFullHpRestActions`. The actual low-HP heuristic has an additional predicate guard: even a full maximum HP below 15 must reach filtered fallback rather than choosing REST directly. Damaged players below 15 retain the original direct REST behavior. The original above 50-HP heuristic already chooses SMITH when legal and is unchanged.

Removing a V4 candidate changes its runner-up margin and sometimes gate ownership even when the original best action was already SMITH. This is part of the eligibility treatment. The subsequent learned upgrade-target gate is preserved. The campaign profile has MCTS=0, REST_WIN=0 and REST_V=0; this wiring does not claim to override other independently enabled policy owners or the separate live advisor.

The filter is pure and consumes no RNG. Unset/0 preserves legacy action and RNG behavior. Enabled random fallback still makes one uniform-distribution invocation over the ordered remaining actions; changed bounds can change underlying engine draw counts. A full-health low-max-HP root newly routed from deterministic REST to random fallback can begin consuming agent RNG. That is a declared treatment effect, not hidden RNG leakage. Actual game RNG is untouched by eligibility evaluation.

## Focused proving checks and experiment boundary

`tests/full_hp_rest_filter_test.cpp` uses directly constructed public campfire states, with no generated run, map or fight. It covers legal full-health filtering, retained special-action order, common Recall composition, candidate-subset/forced boundaries, damaged/Dream/no-SMITH/no-REST/resolved/non-REST cases, positive-HP requirement, entry-only relic counters, game-state/RNG purity, actual low-max-HP policy execution and default-off action/agent-RNG equality across 64 engine states. The coordinator owns builds and execution; source preparation alone is not a test pass.

Before discovery, freeze the new producer and conditional teacher flag, require the strict startup banner, run the focused fixture and a bounded runtime receipt showing an eligible full-health campfire uses the rule. Compare with the same corrected reference, public futures 8 and optional Recall 1, changing only this flag. Use fresh paired seeds; do not relabel existing wave 2 outcomes or the targeted source's 32 futures as fresh population evidence. Report eligibility/use counts, full-run Act-3 outcomes, paired discordance and cost, including harm or nonactivation. Retain the protected final confirmation reserve and leave production defaults unchanged.

Knowledge impact: a new experimental policy hypothesis, implementation and evidence contract. The coordinator owns maintained environment/policy documentation and the final experiment ledger entry.
