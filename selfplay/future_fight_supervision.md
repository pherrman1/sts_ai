# Future-fight supervision

The meta policy should not use a hand-maintained card tier for upcoming fights.
Instead it should ask, for every counterfactual choice, whether the resulting
run clears the fights that matter next.  The first implementation adds this
signal to paired card-reward branches; the shared `FutureFightProbe` in
`apps/one_combat.cpp` can be attached to the equivalent rest, shop, event, and
path branches when their direct-action datasets are extended.

## What is known versus simulated

- The current act boss, next normal encounter queue, next elite queue, complete
  reachable map, and burning-elite location are already represented in the
  simulator state/features.
- A normal encounter is not simply an IID generic fight: Act 1 draws its first
  three normal combats from the easy pool, Acts 2/3 draw their first two from
  theirs, then use hard pools; the previous two normal encounters cannot recur.
  The simulator's `monsterList`/offset preserves this queue.
- Elite identity is a three-way act pool with no consecutive repeat; the boss
  identity is fixed for the act.  Their concrete moves, ascension scaling,
  relic interactions, potions, and combat policy are evaluated by the existing
  combat simulator, not approximated here.
- Unknown rooms must remain simulated.  Their monster/shop/treasure/event
  chances evolve after every unknown room, and event eligibility depends on
  act, floor, HP, gold, relics, and the consumed event pools.  `GameContext`
  carries these mutable pools and probabilities, so copied branches preserve
  the relevant rules.

Sources: [map generation](https://slaythespire.wiki.gg/wiki/Map_Generation),
[monster encounter rules](https://slaythespire.wiki.gg/wiki/Monsters),
[elites](https://slaythespire.wiki.gg/wiki/Elites),
[bosses](https://slaythespire.wiki.gg/wiki/Bosses), and
[events](https://slaythespire.wiki.gg/wiki/Events).

## Labels

For every card and skip branch, a full continuation emits six values:

- `branchNextCombatSeen`, `branchNextCombatPassed`
- `branchNextEliteSeen`, `branchNextElitePassed`
- `branchNextBossSeen`, `branchNextBossPassed`, `branchFutureComplete`

`Passed` means the continuation reached and won that fight.  An avoided elite
is marked unseen and excluded from the elite loss; dying before the next combat
or boss is a failed required-survival outcome.  Branches retain common future
RNG and the same search policy, exactly as the existing paired full-run label.
`branchFutureComplete` prevents a deliberately bounded rollout from being
mistaken for a death before an unobserved boss.

`train_card_cf.py` learns three auxiliary survival logits from those labels
alongside the existing centered full-run action value.  This keeps the full-run
objective as the policy target while directly shaping its representation around
near-term survival.  `VCARD_ACTION_SURVIVAL_W` is an opt-in serving blend for
experiments; it is zero by default until a paired gameplay gate validates it.

Use `bash selfplay/run_future_fight_collection.sh N_RUNS SEED_OFFSET [TAG]`
after rebuilding `one_combat.elf`.  It deliberately creates a new CSV because
the completed reliability/adaptive datasets predate these columns.
