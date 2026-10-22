# Live model inspector

Last verified: 2026-10-22 for the `STS_SILVER_STASIS_RETURN_QUEUE` pending item and the half-dead Darkling `SetMoveAction` producer fix; 2026-10-20 for the Act 4 map import; 2026-10-19 for the Lagavulin sleep import, the driver's Smoke Bomb escape wait, in-combat potion discards and exhaust-pile display resets in the driver state identity; 2026-10-18 for unadvertised out-of-combat potion discards, the reloaded boss marker in `?`-room history and the ADR-0047 card-select student in the advisor; 2026-10-17 for the live-bridge audit fixes (keys, research search stack, X2-B leaf, 10k Silver, strict driver, Silver session retention); 2026-10-17 for explicit Arm C tree-prior loading, qualified A0/A20 CTM packaging and ascension dispatch; 2026-10-01 for the issue #368 power-ID, selector, history, chest, combat-offer and forced-transition projections; 2026-09-27 for the combat final-HP panel and OOC endpoint HP; 2026-09-26 for two-offer Neow capture/import; 2026-09-25 for the native Silver evaluator; 2026-09-23 otherwise. This page describes the private integration
boundary currently present in the repository; it is not a claim that every
game boundary has a qualified live evaluator.

## Current boundary

`one_combat_advisor` is a small, read-only newline-delimited JSON process.
Its stdout contains protocol responses only; malformed input and failures are
returned as structured errors. It validates the protocol name, request kind,
session, monotonic observation sequence, observation hash, and the required
observation boundary. It never receives RNG state or controls the simulator.

Combat observations now have two separate fail-closed evaluator paths. The
existing CTM evaluator uses the public combat-entry importer when its model is
available. The `silver_player_decision_v2` evaluator imports an Ironclad
decision-0 or decision-1 Silver root, builds a main-engine search state from it
(`battleContextFromWire`), and runs a 10,000-simulation Silver decision by
default (`STS_LIVE_SILVER_SIMS`, the flat exact budget of the A20 research
stack; `1000` restores the old floor) with the native `SilverSearcher` (the same search `one_combat` uses,
ADR-0021; responses carry `"engine": "native_silver"`). The combat
panel's `Silver +9k` button raises the requested root budget to 10,000; each later
click adds another 10,000 (20,000, 30,000, ...). The advisor searches the larger
of the request and `STS_LIVE_SILVER_SIMS`, so under the default 10,000 floor the
first click changes nothing and the budget grows from the second click on. The retained Silver root is
continued incrementally, and any gameplay state change resets the next decision
to the default. The panel reports the requested budget, accumulated root visits, and
total simulations returned by the advisor.
One advisor-owned Silver session is retained for the active protocol session
and `combatEntryHash`; a matching observed successor can therefore report an
exact reroot with inherited visits. Matching considers every explored state in
the retained graph, not only Silver's selected recommendation, so choosing
another listed action also inherits its branch visits. Playing a different
physical copy of an equivalent card reroots through that branch as well and
reports `equivalentCopy: true` (ADR-0023). An observation with no retained
successor safely reports a fresh `candidate_missing` fallback. Multi-card
selections (Gambling Chip, Purity) are searched as whole subsets; the selected
subset is lowered one `choose` at a time and then `proceed`.
It returns the selected action, root action summaries containing
edge visits, `visitShare`, and selection Q only when that edge has a valid Q
value, plus the decision ordinal and reroot diagnostics.

#### Combat final-HP samples

Every OK Silver result also carries `finalHpDistribution`
(`silver_final_hp_distribution_v1`) and a `finalHp` layer on each root action
summary. Each simulation Silver runs at the current root adds one sample: the
player HP when its combat ended (tree terminal or rollout), before
post-combat relic heals such as Burning Blood, or a death. `hpCounts` share
one `0..axisMaxHp` axis (at least the root max HP); index 0 holds deaths.
Turn-cap losses, engine stops and halted rollouts are `unresolved` and are
excluded from `count`. Samples accumulate across `Silver +9k` extensions of
the same root and restart at every new root; visits inherited through a
reroot are not included, so `count + unresolved` equals the simulations run
at this root, not `rootVisits`. Root action layers partition the root layer.
`SilverOutcomeCapture` is caller-owned, default off, and only counts;
`live_silver_importer` checks that capturing leaves visits, values and the
selected action unchanged. The samples follow Silver's UCB tree policy and
rollout policy, so they are search-conditioned outcomes, not an unbiased
estimate of the eventual result of the recommended line; low-visit actions
have few samples.

The combat panel shows these samples instead of the CTM combat-entry
forecast, which remains in the protocol but is no longer displayed. The left
card shows **Sampled deaths** (share of resolved samples) and the sample
count. The right card, **HP at combat end**, draws a cyan histogram on a
fixed 0..max-HP axis with the death bar in red, a white marker at the current
HP, and the expected final HP (deaths as 0) with its change from now. Hovering
a hand card outlines, in amber on the same y scale, the samples of every
searched play of that physical card (UUID); while aiming at a monster, only
plays at that target. Hovering End Turn shows its samples. Hovering a potion
icon, or opening its menu, shows every searched use of that slot; aiming it
narrows to that target, and hovering the menu's Discard button shows the
discard. The display uses
only identity-matched responses and does not depend on the CTM model or the
response's CTM status.
Unsupported encounter, relic, information, or schema states remain explicit
`UNSUPPORTED` results; this is a diagnostic ranking display, not a gameplay
controller or a qualification of Silver policy quality. `STALE` responses
reject a second observation with an equal or older sequence in the same
session. A new process starts a new session state.

The default live OOC evaluator is `mcts_ctm`. It imports the public OOC
observation into a separate transition-capable root, uses the shared
`CombatTransitionSampler` for combat-entry chance transitions, the loaded V4
strategic model for policy priors, and the public X2-B win tree
(`v_win_x2b_public_trees.txt`, ADR-0029; releases installed earlier carry the
B0 `v_win_trees.txt`) for compact-tree leaf values. New installs copy only the
X2-B tree; `STS_LIVE_OOC_WIN_MODEL=<repo>/models/v_win_trees.txt` restores B0. The default search budget
is exactly 512 simulations. With `STS_LIVE_OOC_RESEARCH_STACK=1` (default) the
search uses the A20 research configuration of §504/§522: three leaf combats
(rollout3), PUCT 1.5, widening K 4 and α 0.75, depth 32, early stop, outcome
merging and tree rules (ADR-0031), greedy rollout shops (ADR-0032), and with
Arm C loaded the heart1full prior (ADR-0042) and the student as leaf policy.
`STS_LIVE_OOC_RESEARCH_STACK=0` restores the bare planner defaults (widening 2
and 0.5, no leaf combats, no tree rules). Responses report `searchStack`,
`collectKeys`, `leafCombats`, `treeRules` and the widening and depth settings.
Leaf combats and the student leaf policy run only when public map history is
qualified (`mapHistoryComplete`: question history, seen relics, no unrevealed
sibling card rewards); otherwise leaves still stop at the map checkpoint
(`stopAtMapCheckpoint`), and `armCLeafSteps` stays `0`.

Keys follow ADR-0041 in the advisor as in `one_combat`: `STS_COLLECT_KEYS`
(default `1`, strict `0|1`) sets the terminal objective, the rollout chain's
key step, the free-reward rule and Recall. `0` is consistent keys-off play as in
`one_combat` (no key candidates, Act-3 victory counts as a win). It does not
restore the pre-fix live mix, whose tree kept key candidates and the Heart
objective while its rollouts ran keys-off. Before any search the advisor
plays the Heart key rule (`heartKeyAction`: Emerald, Sapphire before its
paired relic, Act-3 Recall, the final-act route to the burning elite) as a
forced click (`mode=fixed_rule`). With the research stack the remaining tree
rules (`oocTreeRuleAction`: open a chest without Cursed Key, take an
unreviewed reward relic, gold, a potion with space, leave an empty reward
screen) are forced the same way; the search tree and rollouts apply them too.
A key click the live screen does not offer stops with
`HEART_KEY_RULE_UNLOWERABLE`, except on an opened card group, whose parent
rewards are projected but not clickable; there the search runs and the rule
fires on the reward screen the card choice returns to. When the search reports a fallback-eligible
`UNSUPPORTED` root and Arm C is loaded, the advisor plays student C's argmax
(`mode=heart1_fallback`, `fallbackFrom` names the reason), as the simulator's
heart1full fallback; non-UPGRADE card selects stay excluded. The
search seed is derived from the request observation hash, so repeated
observations are reproducible without importing live RNG state. V4 remains
available only as the explicit `STS_LIVE_OOC_POLICY=v4` diagnostic path; it is
not the default and is not used as a post-hoc selector.
Newly expanded reward, shop, event, and selector states are continued through
the shared bounded dependency to a resolved map checkpoint before `v_win` is
evaluated. Semantic roots outside V4's screen support use uniform source
priors; REMOVE, TRANSFORM, and non-card reward roots are not rejected merely
because V4 cannot supply their prior.
Shop card slots (0-4 class, 5-6 colorless) are tracked by card identity from
the shop's first capture. A Courier restock takes the bought card's index in
`coloredCards`/`colorlessCards`, so it inherits the slot of the card that
previously held that index in the last captured list. Card positions are not
used, because `ShopScreen.updateCards` re-derives them from the sliding rug every frame
(problem 79).

Each supported OOC candidate reports a semantic key/payload, physical live
action, Q, visit count, visit share, and prior. The selected candidate is the
visit winner, with the planner's Q tie-break. The driver and Java overlay
validate finite nonnegative statistics, a complete root visit/share
distribution, and selected-candidate consistency before displaying or
executing a choice. A selected smith, peace-pipe, shop-removal, or supported
event transaction records a session/sequence-bound pending compound plan; the
next matching selector must resolve the same physical card identity before a
selector action is emitted. Missing, ambiguous, stale, or interrupted plans
fail closed.

The Java frontend is under `mods/sts-model-inspector/`. It uses BaseMod
post-update/render subscribers and captures detached Ironclad-compatible
summary fields for actionable OOC screens and ordinary player turns. The
combat producer now emits protocol-v4 Silver roots with physical card UUIDs,
upgraded/misc/cost/retain/free-play fields, battle-lifetime stable monster
slots, dead/half-dead/escaping state, relics, potion slots, the combat entry
identity, and a centralized native mapping
boundary for runtime IDs. Card `misc` carries native special data: Searing
Blow uses its public `timesUpgraded` count, and Rampage uses the increase above
its initial base damage of 8. Vanilla stores Rampage growth in `baseDamage`,
not `misc`; temporary damage modifiers are not included in that increase.
Other cards retain Java's `misc`, including Ritual Dagger's stored damage.
Monster move-history bytes are emitted in Java's
oldest-to-newest order and translated by the native importer through the
per-monster mapping; they are never copied as native enum values. Ordinary
draw order is sorted before emission; the actual runtime order is retained
when Frozen Eye is present. Under Runic Dome, the observer omits `nextMove`,
`moveHistory`, `intent`, and `intentDamage`. A public-history observer qualifies 62 audited monster types. The roster is
Jaw Worm, Cultist, Fungi Beast, Blue/Red Slaver, small/medium Acid and Spike
Slimes, Sentry, Gremlin Nob, Centurion, Mystic, Chosen, Snake Plant, Snecko,
Spheric Guardian, Exploder, Repulsor, Maw, Nemesis, Orb Walker, Giant Head,
Donu, Deca, Spiker, Spire Growth, Taskmaster, the five ordinary gremlin types,
Book of Stabbing, Time Eater, the three Masked Bandits, Transient, Writhing
Mass, Champ, Byrd, Shelled Parasite, Guardian, Hexaghost, Lagavulin, Looter,
Mugger, Awakened One, large Acid and Spike Slimes, Slime Boss, Bronze
Automaton, Bronze Orb, Gremlin Leader, Reptomancer, Snake Dagger, Collector,
Torch Head, both lice and Darkling. Every member of
a group must qualify, retaining original physical slots and executed history
for dead members. Source-qualified births carry canonical slots, occupant
generations and local execution timelines. Replacements clear the previous
occupant's pending rolls and attack predicates before the newborn's first roll.
The thief contract separately qualifies original escaped slots. Generic card, relic, potion and power qualification still
applies; Dome does not impose a separate restricted deck.
Runic history schema 4 carries occupant identity and local timelines alongside
typed known-next and forced-override proofs, public pre-roll
inputs, roll generations and indexed attack predicates. Exact installed-source
setter sites qualify deterministic transitions and visible stuns; missing,
late, duplicate or unrelated overrides fail closed. No queued hidden move is
read. Writhing Mass retains each public reactive-roll input and only marks
Implant used after its public execution. Guardian derives the defensive
threshold from completed Twin Slams and observes the public Mode Shift break.
Hexaghost records player HP at public Activate execution to derive Divider,
and derives orb phase from the completed deterministic cycle. Spot Weakness
on a known next move checks consistency without consuming RNG.
Lagavulin records public sleep/wake transitions and qualified setter ordering.
Looter and Mugger retain a deferred direct-choice prior without reading its
outcome, with public stolen-gold bookkeeping and escaped-slot handling.
Awakened One records public half-dead/rebirth transitions while retaining the
original Cultist slots. Deferred direct choices are materialized before rollout
policy evaluation just as ordinary pending move rolls are.
Both lice and Darkling carry a finite candidate mask for their persistent
constructor damage. Public hit outcomes narrow that mask by replaying the
visible HP, block and mitigation context; blocked hits, Buffer, Intangible and
overkill retain every compatible candidate. The damage callback precedes
Buffer's queued power reduction. Each simulated world samples one surviving
candidate and retains it across attacks and Darkling's same-object regrow.
Under Dome, public wire state, knowledge events, information hashes, model
observations and retained search nodes redact that sample while preserving the
mask. Ordinary public roots retain the known scalar and canonicalize the
irrelevant belief metadata to zero.
Unknown birth sources, incomplete execution tokens and impossible damage
histories fail closed. This qualifies the installed vanilla source contract;
it does not establish gameplay quality or a live smoke of every encounter.
Spot Weakness contributes only its publicly revealed attack/nonattack predicate,
indexed to the pending roll. Fair search conditions hidden move samples on that
predicate without exposing the actual move or damage. Repeated queries retain
the same observation; earlier constraints survive subsequent hidden rerolls.
Silver wire v3 carries this information; legacy v2 is accepted only for roots
without hidden intents. Binary snapshots use v4 for occupant generations and persistent damage
beliefs. Legacy versions are readable within their representable domain. Impossible predicate constraints fail
explicitly rather than selecting a fallback move.
Sensitive player and monster powers carry the runtime `justApplied` bit when
the bounded reflection helper can read it and are rejected when it cannot.
The producer maps vanilla `RitualPower.skipFirst` to this field because that
power uses a different turn-local member name; `SlaverBlue` has stable native
`miscInfo` zero and is emitted explicitly as zero. The player-side
`Weakened` ID is an alias of native `Weak` and follows the same
`justApplied` requirement.
Raw vanilla power IDs are accepted alongside the legacy class-name aliases,
including Flame Barrier, Double Tap, Brutality, Confusion, Constricted,
Next Turn Block, DexLoss, Regeneration, Ritual, Magnetism, Mayhem and Sadistic.
Monster aliases include Shackled, Generic Strength Up Power, Painful Stabs,
Regenerate and Compulsive. The latter is a Java boolean marker; at a resolved
Writhing Mass boundary it maps to native zero pending reactive rolls.
Unawakened and Explosive are validated against monster identity and phase/move
state rather than invented status bits. Awakened One remains in native phase
zero while half-dead and gains the native minion-leader victory rule after
rebirth, so surviving Cultists do not delay victory after its final death.
Java Lagavulin has no sleep power; outside Runic Dome the importer sets native
`ASLEEP` exactly when its public intent is IDLE (move byte 5), which it rolls
only while asleep (waking sets OPEN 4 or ATTACK 3).
`STS_IMPORTER_LAGAVULIN_SLEEP_FIX=0` restores the legacy import without `ASLEEP`.
Combat capture includes
`energyPerTurn` from Java `energyMaster`; the importer adds Berserk's power
amount to this base/relic energy for native future turns. IntangiblePlayer
has an explicit false native expiry bit because vanilla always decrements it
at end of round and has no `justApplied` member. These mappings were checked
against `desktop-1.0.jar` SHA-256
`cfad868ac8d65a88e71a0bf096fb09f78811e553effe0787c5309a655e081673` and native
regression fixtures; they do not establish live whole-fight parity.
Special bookkeeping for Combust, Echo Form, Panache, Deva Form, Orange
Pellets, used-up relics, Necronomicon, and Centennial Puzzle
(`usedThisCombat`, a private static in vanilla) is serialized when its runtime field
is accessible; otherwise the importer rejects that state. Monster `miscInfo`
is similarly serialized from known runtime trackers or omitted so the importer
fails closed. Orange Pellets' played card types come from the relic's private
static `ATTACK`/`SKILL`/`POWER` flags (not a power; before live parity
problem 32 the mod looked for a power and never wrote the field); a missing
field imports as 0 (`STS_IMPORTER_ORANGE_PELLETS_FIX`). Bronze Orb Stasis uses the runtime `StasisPower.card` object to
preserve the exact physical card UUID and state, rejecting only the active-
Stasis snapshot when that field is unavailable.
The observer's post-`AbstractPlayer.damage()` patch records finalized damage
once per public damage call, preserving multi-hit event counts and the final
individual unblocked hit. The v4 importer rejects observations unless the
producer asserts this exact tracking; the old per-turn combat-damage total is
not an accepted approximation. The resolved `CardQueueItem` is captured by a
prefix on `AbstractPlayer.useCard(...)`, after vanilla resolves random
targeting and before `GameActionManager` removes the queue entry; post-update
observation is too late to retain that public item. At a card selection the
importer also accepts an optional `combat.pendingCardQueue` array: vanilla's
`GameActionManager.cardQueue` still pending at that point (not the item being
played), front first, with items in the `curCardQueueItem` shape. A malformed array fails as
`silver_card_queue_item`. The Java producer now emits this array at selectors,
including an observed empty array, and retains same-UUID generated copies in
front-first order. It verifies that the processed physical queue item has
already been removed; unknown subclasses, unsettled queues, invalid targets,
capacity overflow and unqualified end-turn/no-trigger payloads fail closed.
At a qualified Nilry's Codex end-turn choice, the producer also preserves
ordered vanilla Burn, Decay, Doubt, Shame and Regret objects still in the hand with their no-trigger
flags. The importer verifies their physical card identity, owning continuation
and exact flags. Pending block gains precede that damage; lethal damage stops
the continuation. Regret retains its trigger-time hand count. Unceasing Top is
qualified at the Codex end-turn barrier; its next-turn behavior resumes after
the end-turn queue. Other no-trigger owners/cards remain unsupported.
Java's `isEndTurnAutoPlay` flag is kept separate from the native
null-card end-turn marker. A producer-shaped Double Tap/Headbutt fixture checks
the copied continuation; Codex fixtures check choose/skip, upgraded Burn,
block order and lethal damage.
Qualified source-card selectors, standalone selectors and Toolbox capture an
ordered typed action tail: opening draws, block/energy, literal or random enemy damage,
Gambling Chip, Warped Tongs, bounded player powers, public all-enemy debuff
batches, Mark of Pain's two shuffled Wounds, Hex's shuffled Dazed for a played
non-Attack (`SHUFFLE_DAZED`, amount 1, `STS_SILVER_HEX_DAZED_QUEUE`; e.g. a
Discovery choice under Hex), Void's energy loss (`LOSE_ENERGY`, amount 1, from
`actions.unique.LoseEnergyAction.energyLoss`; e.g. Warcry drawing Void under
Evolve), and the owning card's cleanup. The importer folds `LOSE_ENERGY` into
the imported energy, as native `CardManager::draw` applies Void at the draw,
and refuses it behind a pending energy gain (`STS_SILVER_VOID_ENERGY_QUEUE`).
A potion's Discovery offer with Toy Ornithopter's heal queued behind it uses
continuation `public_actions` (`STS_SILVER_CARD_REWARD_PUBLIC_ACTIONS`); an
offer refused for pending actions carries a diagnostic `pendingActionsBlocker`.
When the public pending-action projection itself refused, the blocker ends in
`;refusal=<queue index>:<check>` (e.g. `3:batch_power_fields`), naming the
first failed check (problem 74, Toolbox's offer with Red Mask's Weak queued).
Red Skull's battle-start anonymous action (`relics.RedSkull$1`) is a no-op
unless the player is bloodied and the relic inactive. The projection omits the
no-op and otherwise sends Strength 3 as `BUFF_PLAYER` (problem 74). The blocker
names anonymous classes by their full class name.
`GAIN_ENERGY` reads its amount from `GainEnergyAction.energyGain`: the
`GainEnergyAction(int)` constructor calls `setValues(p,p,0)`, so the inherited
`amount` is always 0. A missing or out-of-range (0-99) gain refuses with check
`gain_energy_amount` (problem 84, seed 111200510: Nunchaku's GainEnergyAction(1)
behind Headbutt's put-on-top choice was exported as 0, so energy was 1 short).
Pen Nib's pending power gain/removal and Orange Pellets' player debuff removal
are qualified by their exact vanilla relic, action and recipient.
Exact vanilla action classes,
unstarted-action fields and public parameters are required. The native root
restores this observed queue directly instead of replaying a historical card;
the producer clears stale current-card bookkeeping for standalone selectors.
Source-card tails require an exact card/task owner, physical queue provenance,
unstarted cleanup flags and an observed copied-card queue; cleanup executes
once at its recorded position after effects such as Burning Pact's draw.
Observed card and action queues survive JSON envelope snapshots, including
known empty queues. Arbitrary action tails and hidden preselected random
targets still require their own contracts. Boolean monster powers are
presence states at the importer boundary, so a negative or sentinel Java amount
still sets the status bit before numeric amount validation. The stable slot
registry keeps ordinary Large Slime split children at native slots 0/1; the
separate Slime Boss layout uses 0/2. Move bytes are likewise fail-closed, with all
simulator-supported vanilla class constants independently qualified against the
installed `desktop-1.0.jar`. The native construction, public-render, import,
exact search-state parity, and one-simulation Silver-decision sweep covers all
63 reachable `MonsterEncounter` values; the focused test additionally covers
producer-shaped dynamic transitions for Large Slime split, Reptomancer summon,
Darkling Regrow, Bronze Orb Stasis, and Awakened One stage 2. The only manifest
exclusion is the `INVALID` sentinel.
The combat boundary still requires the installed runtime's waiting-for-user
phase, no current action, empty action/card/monster queues, and an unended turn.
It also excludes a combat that is ending: while the player escapes after Smoke
Bomb (`isEscaping`/`smoked`) and after `endBattle()` (`isBattleOver`) the room
stays `COMBAT` with idle queues, but native combat has already ended and
`endBattle()` has cleared the Runic Dome occupant binding, so publishing that
frame made Silver refuse with `silver_monster_occupant_binding`.
The Runic Dome tracker stamps rolls with `GameActionManager.turn`, which already
reads 1 at the combat-start roll (live seed 111194466, also after a game
restart), while the importer's global clock puts that roll at native turn 0. Its
snapshot is serialized with a default `Gson`, which omits null members such as
`knownNextMove` and `knownRollPredecessor`. The importer reads the first roll of
an unexecuted initial occupant as global turn 0 and a missing nullable member as
null (`STS_IMPORTER_RUNIC_DOME_WIRE_FIX`, default on; `=0` restores the strict
reading, which refused every first-turn Dome root).
Awakened One's Rebirth turn queues `ChangeStateAction("REBIRTH")`, whose heal
lands behind takeTurn's `RollMoveAction`. So the roll right after Rebirth sees
HP 0 of 320. The tracker accepts that one roll (Awakened One, `publicMisc` 1,
last executed move 3), and the importer accepts its `rollHp` 0
(`STS_IMPORTER_RUNIC_DOME_REBIRTH_ROLL`, default on; `=0` restores the
refusal). Phase two's first move, Dark Echo, does not depend on HP. Problem 91
(seed 111200541) refused with `silver_runic_dome_incomplete_history`.
The combat fingerprint includes the payload, so successive decisions are not
collapsed into one observation. A battle-start hook can precede encounter
population, so combat-entry and Silver-root identity are captured lazily at the
first actionable decision. A stable-boundary loss clears the displayed
observation and fences late responses from the prior decision. Advisor writes
use one bounded latest-observation slot; intermediate captures are replaceable
rather than queued without limit. It launches the advisor with a direct
`ProcessBuilder` call. The F8 panel remains diagnostic and read-only. Its top
edge sits 170 scaled pixels below the screen top, clearing the relic row.
The panels omit floor/HP text already shown in the game HUD. The lower-left
graph button exports a captured Silver or OOC MCTS tree as a timestamped HTML
file under `~/.cache/sts-model-inspector/graphs/` and opens it in the default
browser. At click time it pins the current observation and its matching ready
advisor response into a dedicated temporary snapshot, so asynchronous updates
to `latest.json` cannot change which tree the export uses;
`captureMctsGraphs=true` enables tree capture. `showAdvisorPanel=false`
hides the top-left panel while retaining the standalone graph and Silver
budget controls, `showActionRecommendations=false` hides recommendation
overlays, and `showSelectedActionSummary=false` hides the selected Silver
action line while retaining the budget and visit summary. These properties are
read from `~/.sts-model-inspector.properties` and default to their existing
visible/capture-off behavior unless set.
OOC decisions use the same dark/cyan styling as Silver, with an amber border
on the selected action. Event and Neow scores appear beside their active
buttons. Shop scores sit by each affordable card, relic, potion, removal and
leave control. Map scores bind through the same one-based `choose` indices
as the live capture (coordinates are metadata), and follow the reachable nodes' scrolled hitboxes;
offscreen nodes never acquire badges clamped onto the screen edge. Rest options
and OOC card selectors also use physical-control badges. Upgrade, remove, and
transform selectors show the shared MCTS ranking when the public selector
boundary is supported. Grid
scores hide during peek/confirmation and cull offscreen cards.
Card rewards retain scores below each card and add a separate
skip-button badge (and Singing Bowl badge when present). These screens replace
the upper-left recommendation list with inline labels and a small status footer;
other screens retain the ranked panel. Labels and badges bind to current structured choice
occurrences, not card names. Only identity-matched `live_ooc_decision_v1`
responses display scores; waiting, unsupported and error states show no
recommendation. If a scored action cannot be bound to its exact physical
control, the ranked panel remains as a fallback rather than silently hiding it.

Compound actions are represented as a source click followed by the pending
selector plan; the source score is not silently combined with a fabricated
selector score. The selector response carries an `APPLIED` compound-plan
marker after the exact target is resolved. Unsupported effects, incomplete
public continuations, and screens whose target cannot be matched remain
explicit `UNSUPPORTED` results.

In combat each scored potion gets one small badge under its top-bar icon:
the best-ranked Silver action for that physical slot (`#rank · visits`,
prefixed `Discard` when discarding ranks best), amber-bordered when it is
Silver's selection. Unscored potions get no badge, and badges hide while the
potion menu is open. The per-target and use/discard detail is in the hover
distribution instead (see *Combat final-HP samples*). Card and potion target labels
use live monster names, with indices only to distinguish duplicate names. Native
Silver slots and compact live potion targets resolve separately. Silver root summaries include
an additive `liveAction` binding for this display; unsupported lowering is
`null`. OOC full-belt replacement discards have native MCTS action bindings,
but the combat potion badge renderer does not display OOC scores. Freshness
and unsupported/error suppression apply to potion scores
as well. The overlay is presentation-only and does not change policy
or driver decisions. Combat-entry projection translates only the spent
Neow's Lament sentinel (`counter=-2`, `usedUp=true`) to native zero remaining
charges. Active charges and other relic counters remain exact; the CTM support
gate is unchanged. Workshop
and game/dependency JARs remain outside Git. The native v4 importer is
fail-closed for unknown mappings, resolving snapshots, unsupported selection
tasks or option capacities, and native mechanics absent from the pinned
simulator. Its maintained capability census is
`docs/knowledge-base/behavior/live-silver-capability-census.md`. A single
isolated search seed derived from `combatEntryHash` is retained across an
active protocol session and combat; the UUID registry is reset when either
identity changes.

## Direct live-game driver

### Start and discover the live control boundary

The canonical local live-test setup is provided by
`tools/live_game_start.sh`. It first ensures a self-contained user runtime at
`${STS_LIVE_RUNTIME_DIR:-${XDG_DATA_HOME:-$HOME/.local/share}/sts-ai/live-runtime}`,
repairs the managed inspector properties without replacing unrelated keys,
reuses an already-running modded game, or starts ModTheSpire in its own
background session, waits for MCP port `8080`, and prints the driver command.
Use:

```bash
tools/live_game_start.sh --probe
```

`--probe` performs a read-only driver dry-run after the game reaches a
command-ready screen. Use `--check` to validate without starting anything and
`--foreground` when the Codex terminal should retain the ModTheSpire process
directly. `--run -- <driver options>` starts the autonomous driver immediately
after MCP becomes available, without a separate probe or manual launch gap.
The driver's initial menu-readiness budget is 45 seconds (`--startup-timeout`);
this is a timeout, not a delay. Gameplay readiness/post-action transitions use
`--transition-timeout` (8 seconds by default). Slow rendering or ordinary
campfire animations can require a larger explicit budget; a timeout never
authorizes repeating the previous action. The chosen budget is preserved in
failure reproduction commands. Vanilla `CardCrawlGame.render()` returns before
updating the game when `getRawDeltaTime()` exceeds 0.1 seconds. Repeated slow
software-rendered frames can therefore advance an animation much more slowly
than wall time; extending the wait does not change the animation or reapply its
effect. The Wheel of Change Spin click adds 10 seconds to that wait: MCP's
screen is unchanged while Java finishes the bounce-in, spins and bounces out
(about 9 seconds) before the result dialog appears. The inspector qualifies the
Spin page (`SPIN_READY`) during the bounce-in as well, because MCP's click only
latches `buttonPressed` and Java starts the spin when the bounce ends.
A combat End Turn adds 10 seconds as well, because the monster turn plays every
queued monster action first (The Collector's turn exceeded 8 seconds on
2026-10-19). While MCP's polled screen keeps changing after End Turn, the wait
also extends to one transition timeout after the last change, capped at the
transition timeout plus 30 seconds; an unchanged screen still fails after the
transition timeout plus 10 seconds.
After a Smoke Bomb the driver waits until MCP's room phase leaves combat, with
10 extra seconds: MCP stays ready in screen `NONE`, phase `COMBAT` while the
player runs off, and the inspector publishes no combat decision in that window
(#695) but next shows the post-escape reward screen. Accepting that window as
a decision stopped two live runs with an observation boundary mismatch; a
Smoke Bomb that never leaves combat still times out.
Advisor waiting remains separately configured by `--inspector-timeout`.
It uses the seed guard and forwards arguments as an array; `--run` cannot be
combined with `--check` or `--foreground`. For a fresh run with no existing save:

```bash
tools/live_game_start.sh --run -- \
  --new-run --character IRONCLAD --ascension 0 --run-until-error
```

`--super-fast` enables an already installed `mods/SuperFastMode.jar` (mod ID
`superfastmode`). Use `--restart-game` once if the running game lacks that mod.
Its local configuration is under `~/.config/ModTheSpire/SuperFastMode/`.
The external JAR is not a repository artifact. Accelerated frame time can
expire vanilla selection actions on the frame that opens their popup: in
`ArmamentsAction`, `tickDuration()` may mark the action done before the selected
card is retrieved. Confirmation then loses the card from the active piles;
a later discard action may retrieve that stale selection in another combat.
The installed 10x configuration reproduced this during A20 live verification.
Use the ordinary launcher without `--super-fast` for integration qualification;
no speed setting is inferred from a previous session's documentation. Speed
changes remain subject to the same readiness and observation checks.

`--refresh-runtime` builds only `one_combat_advisor`, copies it and
the tracked CTM/OOC model artifacts into a new release, validates their hashes,
and atomically changes `current`. New releases package both the qualified
`combat_transition_deepsets_lizard_t2.native` primary and standard Brew
fallback, pin both hashes and the correction setting in the manifest, and
select that manifest's primary at launch. Legacy single-model manifests and
explicit standard-primary overrides remain supported. `STS_CTM_BREW_FALLBACK_MODEL`
and strict `STS_CTM_ACTIVE_LIZARD=0|1` override the qualified stack; advisor
hello/forecast and OOC responses identify the loaded artifacts and setting.
`tools/live_game_runtime.py install` (and `live_game_start.sh --refresh-runtime`)
now installs the qualified stacks by default; `--legacy-ctm` restores the old
choice. `ensure` keeps an existing legacy release, and the launcher refuses to
start on one unless `--legacy-ctm` (or `--allow-missing-ooc`) is given.
`tools/live_game_start.sh --qualified-ctm --restart-game --probe` installs
a version-2 runtime receipt containing the production pathb-r2 Lizard fast and
escape/Brew fallback pair, plus the calibrated pathb-a20 pair. The advisor uses
the A20 pair for ascension 20 and the base pair below 20, in both imagined OOC
combats and combat-entry forecasts. The native loader verifies the built-in
artifact contracts; a partial A20 configuration or research-manifest override
fails closed. `ctmStackScope` identifies the selected stack. Legacy releases
and explicit legacy overrides remain supported.
Refresh and repair preserve an explicitly selected qualified stack even if
its version field is missing or malformed while qualified receipt fields
remain. Such a receipt cannot select a cached legacy release during repair.
An explicit `STS_CTM_MODEL` suppresses automatic fallback/A20 environment
injection; dependent overrides then come only from the caller. This preserves
legacy single-model launches and explicit empty-value failures.

The frozen distilled Arm C model can be installed explicitly:

```bash
tools/live_game_start.sh --arm-c /absolute/path/to/student_sel.bin \
  --qualified-ctm --restart-game --probe
```

The installer accepts the standard card-select student `student_sel.bin`
(ADR-0047, SHA-256
`cf6bf7fb7c3147dcc5b106b1a946486e40bf27fee87c57bcc3262b5869d507c7`, data branch
`claude/heart1-distill-data` 5a7245aa `results/E_d64_sel_xin/`) or the legacy
student C (`eff2f74f57dc2f566bbd44be30988592503cc8db51e51ff1e70cd2dec4636509`;
an existing student C install keeps it until reinstalled). It
copies the weights into the stable runtime as `models/arm_c_student.bin`, and
pins them in `armCModelSha256`. Refreshes preserve this explicit selection;
repair cannot replace it with a cached legacy runtime. The launcher exports
`STS_LIVE_OOC_ARM_C` to the inspector's advisor child. Empty, missing or invalid
explicit weights fail startup. With no selection, the prior stays V4, and the
launcher refuses to start without Arm C, the CTM, the OOC, win or floor model
unless `--allow-missing-ooc` is given.

Arm C supplies the tree prior through the same native heart1 candidate mapping
as simulator OOC MCTS. With the research stack it is the heart1full prior and
the rollout leaf policy as well (see above); with `STS_LIVE_OOC_RESEARCH_STACK=0`
it is the tree prior only. With research-stack weights that carry the `x_act`
input (`student_sel.bin`), compound smith/remove/transform targets also get the
student's target prior and rollout card selects go to the student (ADR-0047;
`STS_OOC_MCTS_TARGET_PRIOR=0` / `STS_OOC_MCTS_LEAF_SELECTS=chain` in the advisor
environment turn them off); responses report `targetPrior` and `rolloutSelects`.
Root card-select screens other than UPGRADE stay excluded from the student
fallback, as in the tree. Unencoded Arm C nodes retain the existing live prior
(equal logits when reward-pity history is incomplete). Every response with a
loaded model carries `armCModel`; successful searched OOC decisions report
`prior=arm_c`, `armCPriorNodes`, `armCPriorFallbacks` and per-reason counts.
Model loading, scored prior use, live action mapping, complete-run coverage,
and gameplay quality are separate claims. This connection does not qualify
the offline Arm C rollout-policy experiment or A20 training/live parity (#506).
The qualified-stack loader is covered at both ascensions for Smoke Bomb,
HP 200, active Lizard Tail, Tail + Fairy and Tail + Entropic Brew. The A20
stack also covers Writhing Mass + Ritual Dagger. The A0 stack still refuses
that intersection, and both trained domains refuse max HP 23 (their minimum
is 24). Packaging does not remove these explicit CTM support boundaries or
qualify a model outside its trained domain.
Only validated production qualification enables Lizard correction automatically;
integration-candidate metadata requires explicit opt-in. An explicitly empty
or whitespace model override reaches the native loader unchanged and fails,
rather than being replaced by Java properties.
Launch overrides that differ from the installed manifest no longer count as a
matching active runtime. The runtime helper uses the Release build
preset (`linux-gcc-release-ccache`, with the build wrapper's matching fallback).
The helper packages the executable from the preset actually selected by the
wrapper. A running game is never silently restarted; when it is
using another release, the helper prints both identities and
requires the explicit `--restart-game` option. `--deploy-inspector` invokes the
existing Java build and atomically installs its JAR. `--allow-missing-advisor`
is only for MCP-only control. Background launch output is written to
`~/.cache/sts-live-driver/modthespire.log`, and launch identity is recorded in
`~/.cache/sts-live-driver/active-runtime.json`. The installed game artifacts
are:

```text
game directory: /home/philippherrmann/.local/share/Steam/steamapps/common/SlayTheSpire
ModTheSpire:   /home/philippherrmann/.local/share/Steam/steamapps/workshop/content/646570/1605060445/ModTheSpire.jar
MCPTheSpire:   <game directory>/mods/MCPTheSpire.jar
inspector:     <game directory>/mods/sts-model-inspector.jar
```

The active-runtime record is written only after port `8080` is verified as
owned by the exact `java -jar <ModTheSpire.jar>` process. It includes that
process's PID, Linux start ticks, and command-line hash; stale metadata is not
reported as the currently running runtime. Explicit `--allow-missing-advisor`
startup remains MCP-only and neither validates nor records a stable runtime.

Start the modded game with the MCP and inspector mods enabled:

```bash
# Equivalent manual launch when the helper is unavailable.
cd /home/philippherrmann/.local/share/Steam/steamapps/common/SlayTheSpire
/usr/bin/java -jar \
  /home/philippherrmann/.local/share/Steam/steamapps/workshop/content/646570/1605060445/ModTheSpire.jar \
  --skip-launcher --mods basemod,MCPTheSpire,stsmodelinspector
```

MCPTheSpire starts a Streamable HTTP server at
`http://127.0.0.1:8080/mcp`. It is the live game's control boundary; use its
MCP tools rather than GUI automation. The driver discovers the available
surface at startup and requires `get_screen_state`,
`get_available_commands`, and at least one supported action tool. A quick
endpoint check is:

```bash
uv run --extra live-driver python tools/live_game_driver.py \
  --dry-run --max-steps 1
```

The asynchronous inspector snapshot is written to
`~/.cache/sts-model-inspector/latest.json`. Before using an advisor response,
verify that `response.ready` is true and that `response.session`,
`response.sequence`, and `response.observationHash` match the observation (and
then correlate that observation with `get_screen_state`/`get_game_state`).
The endpoint and snapshot paths can be overridden with `STS_MCP_URL` and
`STS_INSPECTOR_PATH` when an isolated game instance is required.

The inspector launches the stable advisor configured in
`~/.sts-model-inspector.properties`. Managed keys point through the stable
`current` symlink, never into a Codex worktree:

```properties
advisor=<XDG data>/sts-ai/live-runtime/current/one_combat_advisor
ctmModel=<XDG data>/sts-ai/live-runtime/current/models/combat_transition_deepsets_lizard_t2.native
oocModel=<XDG data>/sts-ai/live-runtime/current/models/ooc_strategic_tok_final.native
```

`STS_MODEL_INSPECTOR_ADVISOR`, `STS_CTM_MODEL`, and `STS_LIVE_OOC_MODEL`
override their corresponding properties when nonempty.
`STS_MODEL_INSPECTOR_CONFIG` selects a different properties file. These
environment-first rules provide an isolated development/test escape hatch.
The learned Silver root prior is not supported by the native evaluator: the
advisor exits at startup when `STS_SILVER_ROOT_PRIOR_MODEL` is set.
For an explicit Silver tree-debug capture, launch the advisor/runtime with
`STS_SILVER_DEBUG_TREE=1`; the normal response remains unchanged when it is
unset. The optional `STS_SILVER_DEBUG_TREE_NODE_CAP` bounds the attached graph
(default `8192`). Native graph nodes report `victoryCount` 0 (the native search
does not count victories) and edges have no continuation actions. A captured `latest.json` can then be rendered with
`python3 tools/render_combat_decision.py --snapshot ~/.cache/sts-model-inspector/latest.json --output /tmp/combat-decision.html`.
For an OOC MCTS search graph, launch the advisor with
`STS_OOC_DEBUG_TREE=1` and select an OOC decision with the `mcts_ctm` policy.
Then render the matching ready snapshot with
`python3 tools/render_ooc_mcts.py --snapshot ~/.cache/sts-model-inspector/latest.json --output /tmp/ooc-mcts.html`.
The mod's lower-left graph button runs the screen-appropriate renderer and
opens the resulting HTML. Configure `graphToolsDir` in
`~/.sts-model-inspector.properties` to the repository's absolute `tools`
directory; `python` optionally overrides the `python3` executable.
`STS_OOC_DEBUG_TREE_NODE_CAP` bounds the capture (default `4096`). The graph
shows retained action nodes and sampled outcome particles, with root semantic
labels, state summaries, visits, priors, and action Q values. State IDs refer to hypothetical
search particles; they are not observed game states. Omitted edges indicate
the capture cap. The renderer validates the snapshot session, sequence, and
observation hash before producing a portable offline HTML file.
Fixture snapshots are labeled in the report. Sampled terminal losses may retain
the pre-combat HP field, which is not a post-death HP reading.
If `latest.json` remains `WAITING` after a combat observation, run
`tools/live_game_runtime.py status` and restart the game explicitly after a
runtime change. A ready response can
still be `UNSUPPORTED` for an encounter or state outside the maintained live
capability boundary; that is an advisor result, not an MCP connectivity
failure.

### Fresh-worktree workflow

An unchanged worktree reuses the installed known-good runtime:

```bash
python tools/agent/worktree.py preflight .
python tools/agent/worktree.py check .
tools/live_game_start.sh --probe
```

After changing live advisor, bridge, or relevant model code, publish the
current worktree first:

```bash
tools/live_game_start.sh --refresh-runtime --probe
```

No dotfile editing or worktree path is part of either workflow. Codex-exposed
`slay_the_spire` tools remain useful for interactive control when available,
but their absence is not a blocker: the repository driver connects directly
to `http://127.0.0.1:8080/mcp`. GUI/mouse control remains unsupported.

`tools/live_game_driver.py` is the repository-local integration/debug harness
for advancing a currently running game without a Codex or Luna turn between
actions. It connects directly to MCPTheSpire over Streamable HTTP, reads the
current screen and advertised commands, and materializes concrete MCP calls
before selecting through Silver or its deterministic fallback policy. The
optional dependencies are isolated in the `live-driver` extra:

```text
uv run --extra live-driver python tools/live_game_driver.py
```

Combat reads the matching `~/.cache/sts-model-inspector/latest.json` response
and uses Silver only when the snapshot is ready, identity-matched, and
correlated with the MCP-visible state. A Silver `OK` response must include a
structured `selectedLiveAction` lowered from the imported physical identity
and map to exactly one current candidate; zero or multiple matches stop the
driver. `--strict-silver` and `--strict-ooc` are on by default, so an explicit
`UNSUPPORTED` result stops the run; `--no-strict-silver` / `--no-strict-ooc`
let it use the deterministic fallback policy (first playable card, first
choice). That fallback chooses only among the generated legal candidates, so
no policy can invent an MCP tool name or arguments. A failed Silver search or
lowering keeps the combat's retained session; only an import failure outside
the matching combat or a process restart mid-combat leaves later roots at
`silver_missing_predecessor`. The driver
waits for `ready_for_command` before selecting and after execution, while
readiness-only changes are ignored for state identity. Combat draw/discard
pile card display caches have one additional normalization: a positive
`damage`, `block`, or `magic_number` with an explicit positive `base_*` value
is compared using that base value. MCP emits `base_*` only while the derived
value differs, and vanilla `Soul` animation completion calls
`AbstractCard.clearPowers()`/`resetAttributes()` to restore those cached values.
The driver retains intrinsic base values, UUIDs, card IDs, costs, pile order,
all hand values, HP and energy; ambiguous zero/absent values and every OOC
field remain strict. This prevents an animation-only reset from looking like
a new decision while still stopping on actual state changes. It never
refreshes or substitutes the selected action after a mismatch.
A live monster whose intent is exactly `DEBUG` is also not a decision-ready
state, even if MCP advertises readiness: vanilla initializes that sentinel in
`AbstractMonster` and replaces it in `createIntent()`. The driver waits for it
to resolve before consulting the advisor and when waiting for post-action
advance. This does not reinterpret legitimate `UNKNOWN` or Runic Dome's
`NONE`, nor dead/escaped/half-dead monster slots; later real intent changes
still fail the pre-action comparison.

Inspector correlation uses the full `get_game_state` monster records when
available because the lightweight screen uses names and filters dead slots.
Dead or escaped inspector slots are excluded before comparing the remaining
live monsters. Silver target slots are compacted through that same ordered
public monster observation before becoming MCP's 1-based living-monster index;
dead or missing targets fail closed. Potion candidates are emitted only when
MCP explicitly advertises the corresponding `can_use` or `can_discard`
capability; absent sparse fields mean unavailable. The post-action identity
includes the full game-state payload when that read tool is available, so
successful potion effects that do not change the lightweight screen still
advance correctly. Silver card-selection actions remain explicitly
unsupported until their mapping to MCPTheSpire's choice surface is qualified;
they therefore use the deterministic fallback boundary.

The default MCP endpoint can be overridden with `STS_MCP_URL` or `--mcp-url`.
Each decision is written as redacted JSONL under
`~/.cache/sts-live-driver/` (override with `--trace`). `--dry-run` performs the
read, candidate, and decision path without a mutating MCP call, while
`--max-steps N` bounds a smoke test. The driver intentionally stops on
unavailable MCP, malformed or stale inspector data, unsupported candidate
enumeration, absent or ambiguous structured Silver lowering, readiness or
transition timeout, and unexpected advisor errors.

Live current energy comes from `EnergyPanel.totalCount`; the player's
`EnergyManager.energy` field is the per-turn recharge amount and does not
decrease when a card is played.

Equivalent-copy rerooting is a lookup only. It exchanges the unique ids of one
pair of search-equivalent cards in the observed state and requires the full
search-state check to match. It does not relax `equalForSearch()`, merge
UID-distinct states in the global dedup table, or make chance-node identity
less strict.

Rest observations are emitted only while the installed campfire UI exists, is
visible, and has not selected an option. Selecting a campfire option therefore
clears the old rest observation while the option resolves.

### Autonomous OOC decisions

The versioned live OOC boundary is `boundary: "ooc"`, `ooc.schemaVersion: 1`.
`LiveOocCapture` captures only command-ready screens through MCPTheSpire's
read-only screen and choice converters. The observation contains:

- `publicState`: Ironclad class, ascension, act/floor, HP/max HP, gold, keys,
  potion capacity and five exact slots, physical deck instances with bottle
  binding, relic data, visible boss, the complete visible 15-by-7 map and edges
  (Act 4: the fixed 5-by-7 map, imported as native `Map::act4Map()`, `STS_IMPORTER_ACT4_MAP_FIX`; the elite's sole `Boss!` choice, sent as option 0, is remapped to the native Heart node option 3, `STS_IMPORTER_ACT4_BOSS_MAP_FIX`),
  current/burning-elite coordinates, exact whole-run and current-act path
  counts, completed combat floors and observed combat classes, acquired/lost relic identities, prior event
  identities, and the publicly recorded number of paid shop removals. A
  `seenRelics` list fully qualifies relic pools only when its producer marks
  the history complete; an incomplete list still excludes the offers it names
  under the relic offer prior below. The Java observer accumulates visible shop, reward and boss offers
  from a fresh Neow boundary. `RelicOfferRecorder` captures those offers before
  shop/reward input and persists the ledger with the BaseMod run-save field
  `stsmodelinspector:relicOffersV1`. Restoration validates schema version,
  seed, character, ascension and exact checkpoint floor. An unseen merchant
  makes the current projection incomplete immediately, even if the map is
  opened from that shop; revealing its offers repairs that temporary gap.
  Leaving without revealing them invalidates the history. A save without the
  field cannot recover skipped historical offers and remains incomplete.
  A separate current-act combat-class observer records whether each
  fight consumed the normal or elite encounter queue, was a fixed event fight,
  or was a boss. This ledger is part of the same identity-bound run-save
  checkpoint, suppresses duplicate observations of the same current fight,
  and resets for a fresh run. Each
  normal/elite queue entry also stores the canonical encounter identity, so
  reconstruction restores the consumed native queue prefix rather than only
  its length. Restoration validates the checkpoint against `damage_taken` and
  rejects unknown identities, conflicting floors and incomplete history.
  Loading and fade frames do not observe partially reconstructed combat rooms.
  An unrelated OOC projection exception rejects that snapshot without erasing
  validated combat history; actual combat-history contradictions still
  invalidate the ledger. This preserves a matched post-combat save through
  reward-screen reconstruction.
  Colosseum's ordered Slavers-then-Nobs fights are the sole qualified
  same-floor pair in Act 2; both are fixed event fights and consume neither
  encounter queue. Capture and save restoration preserve both entries and
  validate them against the two completed-combat metric records.
  The old seed/act TSV sidecar is not a restoration authority: repeated seeds
  and checkpoint rollback can leave stale entries in that file. Missing or
  contradictory history still fails closed with
  `PUBLIC_COMBAT_CLASS_HISTORY_UNQUALIFIED`.
  `potionChance` (multiple of 10) and `cardRarityFactor` (-40..5) are sent
  together or not at all; the live Java producer sends both. The separate
  `rewardPityHistoryComplete=true` marker additionally qualifies them for V4
  scoring; it requires both counters, and only synthetic parity fixtures set
  it, so live play never uses V4.
- `details`: current reward groups, campfire options, physical upgrade targets,
  supported event/Neow phase and options, shop slots/prices, chest state, or
  ordered boss relic offers.
  Neow phase 3 accepts exactly two early-death offers or four ordinary offers,
  with all active button slots matching the captured reward order. Import clears
  unused native Neow slots to `INVALID`; legal-action enumeration and MCTS use
  only captured offers, preserving their original option indices and live hints.
  No random offers are synthesized. Native fresh-run generation remains four
  offers. These paths have Java projection and native import/transition/search
  fixture coverage; this does not assert a new live-game qualification streak.
  Neow phases 0/1 (intro) and 99 (leave) are accepted only with the sole enabled
  slot-zero button and matching live choice. They return a forced
  `native_pass_through` action without model scoring. Differential trace mode
  rejects them with `DIFFERENTIAL_MECHANICAL_EVENT_UNREPRESENTABLE`, because
  the native simulator starts at the offer page and has no matching dialogue
  transition; this change does not qualify Neow trace replay.
- `liveChoices`: occurrence-bound native action identities and single-command
  structured MCP hints. Duplicate labels are never action identity.
- `mcpState`: the exact current MCP screen conversion used by the driver to
  reject observation/screen/offer mismatches before mutation.
- `unsupportedReason`: an explicit producer qualification boundary, when the
  live state cannot be represented exactly. Missing or malformed schema fields
  are errors, not permission to guess an action.
- `captureError`: an unexpected capture or identity failure. This always stops
  the driver, including when an unsupported reason is also present.

When a visible potion reward or affordable shop potion can refill a full belt,
the native OOC candidate set and inspector expose each held potion as a
`DISCARD_POTION` candidate. The driver lowers the selected physical slot to
MCP `discard_potion`; a fresh observation then permits taking the replacement.
Sozu excludes these candidates. Direct V4 reports
`POTION_REPLACEMENT_REQUIRES_MCTS`, because its frozen candidate set cannot
score the additional action; MCTS uses its uniform-prior fallback.

The live driver opens an unrevealed card reward after gold and freely
collectable potions in that combat reward have been collected. A visible relic
defers forced potion collection because it can affect capacity or pickup
effects. With a known public belt, the driver instead reveals the card group
and leaves both the relic and potion to the provider, avoiding a parent-reward
ordering deadlock. Visible relic/key rewards and constrained potion rewards
remain exact parent continuations while a card group is open. This also
supports manually opening a card group before collecting visible gold or relic
rewards.

Path counts derive from persisted `metricData.path_taken`, whose original map
symbols survive event-to-room conversion and save/resume. Completed combat
floors additionally come from `metricData.damage_taken`. The observed live room
class distinguishes a `?` floor that became a hallway fight from a fixed event
fight on the same map symbol: only the former advances the normal encounter
queue. The combat-class ledger is checked against completed public combat
floors without indexing `path_taken` by absolute floor. Wing Boots' public
charge counter is copied into the native root separately from frozen model
relic features. Charged ordinary Act 1–3 MAP decisions are supported by default;
the OOC evaluator identity records `wingBoots=public_exact`. Native
jump legality, charge consumption, acquire/save entry, reordered MCP choice
mapping and exhausted `-2` import have fixed-fixture coverage. An installed-JAR
fixture checks vanilla connectivity and charge initialization/reset, including
JSON recapture. Live execution of a charged jump and policy quality with these
extra choices remain unqualified. Missing or
contradictory history is unsupported. A historical unknown boss-transition marker is qualified only
after fifteen public map-room entries for that act and a matching public boss
combat floor; other unknown path symbols remain unsupported. Public metric
history conditions current-act normal/elite
encounter consumption, relic-pool membership, one-time/event membership, and
shop-removal cost. Currently visible shop, combat-reward, and boss-relic offers
are also removed from every reconstructed relic pool because native generation
consumes a relic when it is offered, not when it is acquired. Historical
shop and reward offers skipped earlier are absent from vanilla metrics.
Validated historical boss `picked`/`not_picked` metrics contribute known
exclusions without marking that global history complete. Legacy normal/elite
encounter history can be recovered only from canonical encounter identities
joined to validated resolved public path floors. An uninterrupted
fresh-run observer accumulates them from each public screen. When that
ledger is incomplete (a save from before the recorder, a mid-run install, or
an unopened shop), the importer keeps the remaining pool superset as a public
prior (`STS_LIVE_RELIC_OFFER_PRIOR`, default 1, issue #637). Native pools are
one uniform shuffle consumed regardless of identity, so given the known
exclusions the unknown future draws are a uniform sample without replacement
from that superset, which is what the per-particle pool reshuffle in OOC MCTS
samples. **Inference:** it is exact up to native redraws of relics that cannot
spawn and real pool exhaustion changing the tier fallback. Random-relic branches and downstream MAP search are then supported,
the evaluator reports `seenRelicOfferPrior=true`, and differential tracing
rejects such roots (`DIFFERENTIAL_SEEN_RELIC_PRIOR_UNREPRESENTABLE`).
`STS_LIVE_RELIC_OFFER_PRIOR=0` restores the fail-closed
`PUBLIC_SEEN_RELIC_HISTORY_UNQUALIFIED`. The
resolved `?`-room outcomes are recovered from vanilla's persisted
`path_per_floor`, checked against `path_taken`, with the current public room
allowed to complete the current floor. Continuing a save made after a boss
fight leaves `path_taken` with a second adjacent `BOSS` while `path_per_floor`
keeps one `B`: `nextRoomTransition(SaveFile)` calls `onPlayerEntry()` again
for a post-combat room that is not a rolled event, and
`MonsterRoomBoss.onPlayerEntry()` appends `BOSS` (pinned JAR bytecode; seen
in parity canary 2, seed 111194451). That one marker is skipped at the boss
floor or the following boss chest, and any further extra entry still fails
closed. Missing, contradictory or shifted
history fails closed with `PUBLIC_QUESTION_ROOM_HISTORY_UNQUALIFIED`.
Native import replays the observed outcomes using native float increments and
resets; qualified root particles preserve these exact room probabilities.
Public acquisition/loss chronology can prove whether Juzu was owned at each
room entry; a later known monster reset also removes earlier counter ambiguity.
For new ordinary transitions, a scoped observer records Juzu's public flash
inside the room roll and persists true/false/unknown conversion provenance.
A known conversion resets the monster chance; an observed non-conversion
uses the normal increment. Legacy Juzu EVENT outcomes without that evidence can instead form a finite
weighted belief over reachable monster chances. This requires ordinary vanilla
room rules, qualified Juzu ownership, the preceding-room shop flag, and proven
Tiny Chest forcing for every relevant outcome. The belief conditions on all
observed outcomes using the exact 24-bit room-roll bin counts and native float
increments. It is conditioning under the fair uniform room-roll prior, not an
exact posterior over the real run's hidden PRNG state. MCTS samples it once per
root particle and preserves the sampled counter in descendants. Direct V4 and
differential tracing reject unresolved mixtures; evaluator diagnostics label
point, finite-posterior and unqualified cases separately. Missing chronology
retains the conservative guard until a known reset. Tiny Chest's qualified
forced treasure outcome is representable.
Event capture uses source-specific phase tables, public displayed costs and
exact enabled option slots. This includes Shining Light, Ghosts, Winding Halls,
and the remaining vanilla Act 1–3 and shrine decision pages. Dead Adventurer
captures the public encounter and consumed reward categories; MCTS shuffles
only the unrevealed remainder. Direct V4 and differential replay reject that
hidden event state. Verified dialogue/result pages use their exact sole
continuation without a model. Unknown phases and contradictory public fields
remain explicit unsupported boundaries.
Ominous Forge (`AccursedBlacksmith`, initial phase 0) and Ancient Writing
(`BackToBasics.INTRO`) qualify their exact enabled option slots. Forge's
phase 2 and Writing's COMPLETE page have a verified sole Leave click; the
latter's unflagged removal grid is identified from its event owner.
World of Goop's initial `GoopPuddle.INTRO` screen projects the displayed gold
loss into native `StateInfo.goldLoss`; its fixed damage/gold reward are
validated against the native effect. Its `RESULT` page uses the same strict
one-button forced transition and differential-trace rejection as Neow.
Unopened ordinary treasure uses visible chest size and the existing MCTS
prior for correlated gold/relic-tier draws. Its Java `goldReward` and
`relicReward` pre-rolls remain hidden. The reward pity counters are captured
exactly (#636): `publicState.potionChance` is vanilla
`AbstractRoom.blizzardPotionMod` and `publicState.cardRarityFactor` is
`AbstractDungeon.cardBlizzRandomizer`. Both are determined by reward screens the player has already seen (potion
drops since the act start, card rarities since the last rare), so exporting
them is perfect memory of public history rather than hidden information
(Philipp chose this over a public-history reconstruction, 2026-10-18).
`STS_LIVE_OOC_EXACT_PITY=0` makes the importer ignore them and restores the
public-belief prior below. The exact counters change only the root counters,
root-particle sampling and the v_win leaf: the producer leaves
`rewardPityHistoryComplete` unset, so direct V4 still fails closed and the
MCTS prior at nodes Arm C does not cover stays the equal public prior. Install
the mod and the advisor from the same release; an older advisor ignores the
counters and keeps the public-belief prior. Library captures its displayed `healAmt` into
`hpAmount0`; Read uses the exact counters when present. Its visible
20-card grid imports an OBTAIN selector, preserving offer order and UUIDs,
requiring distinct class reward cards and exact Egg-preview upgrades, and
checking the non-cancelable one-pick continuation. Its completed Read/Sleep
page is a forced Leave. Brutality and Combust already have red native metadata
and import normally. Searing Blow retains upgrade eligibility after repeated
upgrades; Egg preview/acquisition never upgrades an already upgraded card twice.
Direct V4 rejects unqualified pity, and differential tracing rejects Library's
initial page with `DIFFERENTIAL_HIDDEN_REWARD_PITY_UNREPRESENTABLE`.
Mushrooms and Mysterious Sphere use the same counters for combat rewards. Their native leave effects match installed vanilla: Mushrooms heals
and adds Parasite; Sphere leaves without granting gold. Mushrooms' Stomp opens the "Ambushed!" page (`screenNum`
2) whose sole [Fight] starts the fight; the mod marks it a vanilla `event_continue` and the importer passes it through
(`STS_IMPORTER_MUSHROOMS_FIGHT_FIX`, live problem 57). The Joust opens on `HALT` (sole [Continue], no `INTRO` page in
`TheJoust$CUR_SCREEN`), also a vanilla `event_continue` (`STS_IMPORTER_JOUST_HALT_FIX`, live problem 69). Event repairs also
preserve Designer's fee and continuation, Scrap Ooze's increasing damage,
Mausoleum's random relic, and Golden Idol's minimum max-HP loss.
With exact counters, MCTS keeps them at every root particle and the v_win
leaf evaluates them directly. Without them, the v_win leaf marginalizes the
counter features with the exact discrete mixture `E[sigmoid(margin)]` over a bounded
native lattice (`potionChance` -40 through 60), never applying the link to an
expected margin, and hypothetical reward-pity counters are sampled once per
root particle. In both cases MCTS uses an equal public prior where Arm C does
not cover a node, rather than V4 logits.
Without qualified question history, room chances use the public current-act
`?` visit count and jointly advance
all three counters for each sampled latent room outcome, so every sampled
triple is reachable under the native update rule. Qualified question histories
are preserved instead of resampled; this does not expose reward-pity counters.
The shared simulator
sampler retains its previous copied-counter behavior. This is a support-safe
prior, not an exact posterior conditioned on every prior `?` outcome. An
already-open boss chest with only native `proceed` is a
pass-through state, not a fresh treasure decision; the advisor preserves that
single live action.
No RNG state, future encounter queue, or unrevealed outcome is captured.
Checkpoint continuation preserves the simulator's reward-collection order and
uses the V4 Q/margin contract for card rewards. The fixed free-reward prefix
is shared with the full-run driver. The default native floor/win fallback
calculations for card rewards, shop, rest, upgrade and shop removal now live in
`ooc_native_fallback` and are called by both the simulator policy and the
standalone advisor. The runtime packages both tracked compact-tree models;
absence of either is explicit unsupported, not a heuristic substitution.
Other qualified screens use `ScumSearchAgent2` as in the simulator. A
complete-history synthetic MAP fixture now returns 512-simulation scored
paths. Qualified question-room history permits downstream MAP expansion;
otherwise MAP remains a hard planner leaf. Root hidden-counter sampling
preserves reconstructed public room chances, and successors update them through
normal native transitions. The lattice-valid reward-pity prior remains broad rather than an exact
public-history posterior, so this test is not a general belief-equivalence
claim.

`live_ooc_state` creates both a value-only public projection and a separately
conditioned transition root. It imports no hidden queue ordering or RNG.
`ooc_v4_encoding` is the shared pure implementation of the existing 42-global
V4 token and candidate encodings; the ordinary driver's `buildTokState` wrapper
retains its diagnostic hook. `LiveOocPolicy` is the policy-provider interface.
The explicit diagnostic provider is `v4_q`: prepare the token state once,
score every existing legal V4 primitive with the tracked native model, and
select maximum Q with ascending canonical semantic identity as the tie-break.

The stable evaluator is `live_ooc_decision_v1`, with default `policy: "mcts_ctm"`
and opt-in diagnostic `policy: "v4_q"`.
An OK result contains semantic identities/payloads, finite per-action Q scores,
model content identity, latency, and one structured `selectedLiveAction`.
Smith and removal source choices carry a `:current-screen` semantic identity;
the revealed selector is a separate observation and decision. Map identity is
`ooc-live:v1:map:x=X:y=Y`. Native semantic bindings supply the other identities.
Exact duplicate/missing primitive mappings, incomplete semantic enumeration,
nonfinite Q, and invalid schema produce errors. Only explicit unsupported
support/model states permit the driver's deterministic fallback.

#### OOC values and sampled distributions

`advisor_stdio.cpp` copies `LiveOocCandidateScore.q` into
`candidateSummaries[].q` without rescaling. The evaluator's `valueSemantics`
field distinguishes three cases:

- `mcts_ctm`: `mean_backed_up_value_0_1`. `OocMctsPlanner.cpp` computes each
  root action's Q as `ChanceNode.totalValue / visits` (zero when unvisited).
  Every backed-up leaf passes a finite `[0,1]` check. Live search uses the
  public win-value model at checkpoints and exact 0/1 for terminal loss/win;
  this is a **mean search value**, not an established calibrated run-win
  probability. PUCT uses this mean plus a separate exploration term; the
  displayed value is not that selection score. Final choice uses visits,
  then mean, then action identity. A sole legal action bypasses search and
  displays **No samples**, not a fabricated zero-valued evaluation.
- `v4_q`: `raw_v4_action_score`. `scoreLiveOocV4` calls
  `OocStrategicTokNet::predictActionValue`, whose output is
  `q2b + sum(q2w[i] * GELU(q0b[i] + q0w[i] dot state_action_encoding))`.
  It has no sigmoid or probability bounds. `train_strategic_tok.py` defaults
  to `STRAT_Q_TARGET=absolute`, targeting `10 * labelWon + labelHp`;
  `fallback_centered` instead subtracts the behavior action's target.
  The runtime header does not establish that training provenance, so the UI
  says **V4 score**. Finite values above 1 or 100 are allowed by this raw
  utility head and are covered by native/display fixtures; they are neither
  percentages nor accumulated MCTS values. No clamping is applied.
- Native pass-through choices: `forced_no_search`. Their placeholder Q is
  not an evaluation; the UI says **Forced**.
- A validated MCTS root with one legal action reports
  `forced_no_search` and `model.selection=sole_legal_action`: zero actual
  simulations, visits and sample share, with its configured budget recorded
  separately. It carries no value
  or HP sample distributions. The driver accepts this explicit singleton
  contract; searched roots still require a complete visit distribution.

The live MCTS provider enables observational `captureValueDistribution`.
`ooc_value_distribution_v1` retains fixed-size aggregates at the root and
per root action, not whole leaf states: 22 counts, total count, mean, terminal
loss count and terminal win count. Bin 0 is an exact terminal-value 0;
models returning nonterminal 0 go in bin 1. Bins 1–20 cover `[0,.05)`,
`[.05,.10)`, …, `[.95,1]`; bin 21 is exact terminal-value 1. Terminal
classification comes from `terminalValue` or the explicit terminal outcome
of a detached `evaluateLeafWithOutcome` continuation, never an inferred low
model score. Unsupported searches discard partial distributions. The sum of
candidate bins equals the baseline; each candidate count equals its visits.

The aggregates also carry `sumSquares` for a search-noise standard error.

The same observational capture records `ooc_endpoint_hp_distribution_v1`:
per root and per candidate, the player HP of the state each simulation was
actually evaluated at (the node, or where its detached continuation stopped),
with explicit terminal deaths at index 0, on one shared `0..axisMaxHp` axis.
`floorOffsets` counts endpoints by floor relative to the root. Providers
without endpoints report `unresolved` samples. Qualified public question-room
histories allow downstream MAP expansion using native transitions and the
inherited room-chance counters. Histories without that qualification retain
`stopAtMapCheckpoint`; zero leaf combats still bounds detached continuation.
Endpoint floor/HP distributions therefore depend on the actual expanded tree,
not a universal next-map assumption. The capture itself changes no draws,
visits, values or selection.


The persistent upper-left MCTS panel shows two boxes, like combat. **Win
estimate** shows the root mean search value (a model estimate, not a
calibrated probability) and sample count; hovering a choice shows its gap to
the recommended choice with the standard error of the difference, marked
`≈ tie` below two errors. That error covers search noise only, not model
error. The right box, titled by the measured horizon (e.g. **HP at floor
+1**), draws the endpoint HP histogram in cyan with a red death bar, a
current-HP marker and expected HP; hover adds the candidate as an amber
outline on the same scale. When every sample keeps the current HP, it says so
instead of drawing a spike. The 22-bucket value distribution remains in the
response and graph export but is no longer drawn. Reused particles and
adaptive search visits are correlated samples, not an unbiased policy-risk
estimate. The parser checks the schema,
counts, means and root/candidate conservation before displaying an OK result.
A zero-simulation shortcut has empty bins and null mean. The aggregates can
later gain explicit sampled-consequence fields without retaining leaf states.
Capture does not alter selection, RNG draws or the planner's objective.

`STS_LIVE_OOC_MODEL` (inspector property `oocModel`) loads the native V4 model
once in the advisor process. The stable runtime manifest records its SHA-256;
the evaluator also reports a content fingerprint. Missing/incompatible OOC
models report `MODEL_UNAVAILABLE` without disabling Silver. The launcher
validates/displays the OOC path; `--allow-missing-ooc` permits Silver-only work.

Supported native fixtures cover map choices, reward take/skip and repeated
card groups, mixed combat rewards, rest/smith, upgrade selectors with physical
duplicate cards, initial supported events/Neow including the Woman in Blue's
gold-correct potion purchases and Ascension-dependent leave outcome, all shop
purchase types, shop-removal entry, chest open/leave and boss relic take/skip (the live
driver maps the producer's boss-relic `cancel` to MCP's `skip` tool, live problem 71). The existing V4
support gate still excludes non-card reward collection, removal/other
selectors and the final map-to-boss transition. The live producer additionally
qualifies event phases, path history, special maps, shop slot provenance,
relic-counter representation, and key-disabled campfires. A screen-specific
unsupported phase takes precedence over path and relic warnings, so a terminal
event outro cannot be misread as its initial decision. Unopened card reward
groups expose only their occurrence/type and require the driver to open the
group after parent reward collection; their concealed card identities are not
serialized or scored. Multiple unopened card groups (Prayer Wheel, Orrery,
and Sensory Stone) are revealed one eligible physical occurrence at a time;
the decline ledger prevents reopening skipped groups. An opened group records
only the count of unrevealed siblings. MCTS resolves its visible card and known
gold, relic, potion and key rewards, then stops at a player-state value checkpoint; it omits future
unrevealed sibling-choice value and reports that scope in `continuationScope`.
Sapphire Key retains its exact publicly linked relic occurrence, so taking
either excludes only its counterpart. No hidden sibling card identity is
captured or fabricated. Sensory Stone's
post-reward `LEAVE` page is a verified mechanical continuation.
Wing Boots is imported with a separate public charge
  counter, with charged direct and downstream MAP decisions supported by default.
  Frozen value inputs omit remaining charges; mechanical support does not
  establish value calibration. Lizard Tail maps its
  unused/used state to native 1/0; Matryoshka and N'loth's Hungry Face preserve
  remaining charges with Java used-up sentinels mapped to zero. Maw Bank has an explicit
source-derived active/spent conversion, and a spent Neow's Lament or
Omamori reporting Java's used-up -2 is native 0 remaining charges in both the
OOC capture and the combat-entry payload, because the CTM rejects negative
charge data; other
unqualified positive counters
are unsupported. Upgraded Searing Blow is supported: native deck bookkeeping
preserves its repeated-upgrade eligibility, so the public deck reconstructs the
cached count without acquisition history. A GRID result screen
is a forced confirmation only when `isJustForConfirming` is true, MCP exposes
Continue with no choices or Cancel, and `confirmScreenUp` is false. Upgrade
preview screens retain both Confirm and Cancel. For a verified single-card
upgrade/remove/transform/Bonfire preview, the policy scores the original complete
target set: it confirms when the chosen target is hovered, otherwise returns
to the grid. Ordinary selection and preview use the same native-state search
seed, preventing re-scoring noise from causing repeated cancellation. The MCP
command is `proceed` even when the visible button says Confirm. Missing alternatives or multi-pick previews remain unsupported.
Acts 1–3 MAP roots
at row 14 with exactly one boss choice use the same forced-action path;
Act 4 does not. These paths bypass models and history-dependent search,
including active Wing Boots at the forced boss step. Differential tracing
rejects them with `DIFFERENTIAL_FORCED_OOC_UNREPRESENTABLE`.
OOC selector capture identifies bottle relics, Dolly's Mirror and Astrolabe
from their pending-selection fields, and Duplicator/Bonfire from their event
phase. Astrolabe maps to transform-and-upgrade, and Bonfire retains its
sacrifice/reward continuation. Native import restores completed physical picks
for Empty Cage/Astrolabe and only offers remaining cards, preserving each
card's MCP choice index. Note For Yourself captures its public stored card and
subsequent removal grid; its direct acquisition preserves Omamori charges and
applies the actual relic hooks. An off-color stored card can be legitimate
without Prismatic Shard, but subsequent combat still requires broader
Silver/CTM card support and qualification; OOC capture does not establish it.
Removal, bottle, duplicate and Bonfire selectors may still
fall outside direct V4 scoring; their native semantic/MCTS support is separate.
With the research stack's tree rules (ADR-0031), live MCTS offers one bottle,
duplicate or Bonfire candidate per distinct card; the advisor's live mapping
check accepts the other copies' clicks as the same choice (`validateLiveOocActionSet`,
`treeRuleChoices`) instead of failing with `OOC_ACTION_MAPPING`.
When a full belt blocks a visible potion reward or affordable shop potion,
MCTS enumerates each held-slot discard using public potion identity and duplicate
occurrence. Sozu prevents these replacement actions. MCPTheSpire 1.0.4-dev never lists
`discard_potion` in `get_available_commands`, but its executor accepts
`potion discard N` whenever a potion is held, with no room-phase check
(bytecode of `MCPToolHandler`/`CommandExecutor`). The driver therefore offers
`discard_potion` on combat-reward and shop screens when MCP reports a
non-`COMBAT` `room_phase`, and in `COMBAT` wherever MCP advertises
`use_potion` (no screen up), always only for slots with `can_discard`; other
screens keep their exact advertised surface; discarding never takes a monster target. The next observation scores the actual refill separately.
The combat case serves Silver's only discard edge, a discard that frees a
slot for a held Entropic Brew (`SilverSearcher.cpp`
`potionDiscardEnablesEntropicBrew`); `STS_LIVE_COMBAT_POTION_DISCARD=0`
restores the advertised-only combat surface, where such a choice stops the
driver with a mapping failure. The deterministic fallback policy never
discards in combat.
Shop mapping validation includes the semantic discard actions before model
loading. Both native and captured shop purchases require a free potion slot
and no Sozu; MCP can advertise a purchase that would not obtain a potion.
Skipping that blocked click preserves subsequent physical choice indices.
These new actions use a uniform prior where the frozen V4 action set has no
matching source; direct V4 reports `POTION_REPLACEMENT_REQUIRES_MCTS`.
Match and Keep captures physical board slots and a run/event-local memory of
revealed cards. Unseen cards have no identity in the payload. The existing
native memory policy chooses a slot, valuing known cards as hypothetical lone
rewards through the active policy. Initial exploration requires no model;
unqualified history/model dependencies stop card-value decisions. Hidden board
transitions remain outside differential replay.
Unopened Small/Medium/Large chests capture only visible size. MCTS samples
hidden gold and relic tier together using the existing native correlated
prior; capture never reads either hidden setup field. Both Open and Leave
must be available in MCP. A verified unopened BossChest uses an explicit
public-reveal action: Open reveals the offers while retaining the later Skip
decision. This is an informational policy step, not a claim that Proceed is
unavailable. Unknown chest classes remain unsupported.
After the boss relic offer was skipped, vanilla keeps `BossChest.isOpen`
false and the chest clickable. The capture remembers the room whose offer it
published and treats the skip as final. It publishes the completed room's
Proceed (`opened: true`, `bossRewardSkipped: true`), which the advisor passes
through like an opened chest. Before this fix the reveal was published again
and looped open -> skip -> open until the cycle guard abandoned the step
(problem 87, seed 111200537).
Direct V4 returns `PUBLIC_TREASURE_CONTENTS_UNQUALIFIED`, and differential
tracing returns `DIFFERENTIAL_HIDDEN_TREASURE_UNREPRESENTABLE` rather than
claiming an exact hidden chest state.
These limits must not be presented as whole-game equivalence.
Representable relic counters do not expand the frozen CTM/model support gates.
The advisor now uses the existing qualified DeepSets/Lizard sampler with the
standard Entropic Brew fallback. Active Tail follows that wrapper's qualified
support contract; Fairy/Tail+Brew and other excluded combinations still fail
closed. This integration reuses qualified artifacts; it is not new gameplay
quality evidence.

### Full-run driver and failure packets

```bash
tools/live_game_start.sh --probe
uv run --extra live-driver python tools/live_game_driver.py --run-until-error
# Only when there is no saved/live run:
uv run --extra live-driver python tools/live_game_driver.py \
  --new-run --character IRONCLAD --ascension 0 --run-until-error
```

The driver owns the loop and performs one MCP command per iteration. It waits
for command readiness, checks observation/session/sequence/hash and exact MCP
correlation, lowers the selected action to exactly one legal candidate,
rechecks the state immediately before mutation, and waits for an advanced
command-ready state. It consumes Silver in combat and the generic OOC
provider elsewhere; no LLM chooses ordinary gameplay actions. `--ooc-policy
v4`, `--strict-ooc`, `--strict-silver`, and `--max-steps` control coverage and
stopping. The default resumes an advertised save; `--new-run` refuses to
replace a save or live run. Without a save, an explicit new-run/character
request is required. Ascension and seed are passed through to MCP.

At the last campfire's completed map (`y=14`), the single boss entrance
qualifies as a mechanical action even when MCP advertises `Return`. This
requires `room_type=RestRoom`, `room_phase=COMPLETE` and the exact `return`
button; an unfinished campfire remains unqualified. Return only dismisses
that completed room's map overlay and is not a strategic alternative.

The MCP `SHOP_ROOM` merchant entrance is a mechanical inventory reveal. The
driver requires exactly one visible `shop` entry, one matching MCP action, and
an exact act/floor identity. It enters once, lets the OOC provider evaluate the
opened `SHOP_SCREEN`, then proceeds after that provider cancels the shop.
These clicks are traced as `shop_navigation` and work with `--strict-ooc`;
they do not increment fallback or unsupported counters. Failed or dry-run
clicks cannot mark a shop entered. Differential capture retains its explicit
unsupported boundary because the native replay schema does not represent this
inventory reveal. Arm C shop tokens preserve the native physical slot after
any purchase; removing sold slots before indexing changes card identities.

Visible monster state remains nullable when a field cannot be qualified; it
is omitted for the importer to refuse instead of being unboxed and crashing
the game. Runic Dome skips that private-state reader entirely. Vanilla's
`GremlinWarrior` and `GremlinTsundere` IDs have explicit zero native misc
state, verified against the installed JAR constants.

Combat-class history retains the initial encounter identity while the same
monster group remains active. Summons and splits can leave a composition
that no longer identifies its queue draw; they do not invalidate that captured
history. A replacement or reconstructed group must still match the recorded
encounter, and missing initial history remains unsupported.
Vanilla's persisted `path_taken` uses `BOSS` as well as the visible map's `B`;
both identify a public boss room. In particular, the opening map of the next
act can retain row 15 while having no parent in that new map. Its explicit
boss marker must remain a boss, rather than being replaced by an inferred
preceding room or an empty transition placeholder. Unknown markers retain
their existing qualification checks.
On the opening MAP of Act 2 or 3, vanilla may also retain `(-1, 15)` as the
current node. The importer represents it as the native unchosen-map position
`(-1, -1)` only at that act's exact starting floor, with MCP proving a completed
boss chest, an unchosen first node, no boss/cancel/proceed action, and a complete
set of row-zero choices with matching physical click indices. The original
capture remains intact; ordinary row-15 transitions remain unsupported.
That same public proof retains `BOSS_TREASURE` as the planning root's current
room, for either `(-1, 15)` or the ordinary `(-1, -1)` unchosen coordinate.
The first imagined combat therefore receives the same boss-chest predecessor
as the real first room, instead of inheriting the hypothetical constructor's
`INVALID` placeholder.
The first room of a new act has only one current-act path coordinate, so it
cannot recover CTM's previous room from a second node. Capture recovers
`BOSS_TREASURE` only when the exact Act 2/3 first-room floor, the matching
row-zero path coordinate, the persisted boss/chest room records, and a
completed boss combat metric agree. Combat-entry capture retries that public
path recovery after save loading if the initial transition latch was empty.
Missing or contradictory records remain unqualified.
After the Act 3 boss dies, MCP can expose an empty `COMPLETE` surface rather
than a reward screen. The strict driver advances its single Proceed button
only for a living player at Act 3 floor 50 (or floor 51 with verified A20) or after the Heart (Act 4 floor 56 at
verified A20, live problem 52; floor 55 below A20 is **Inference** from Act 3's single boss, not observed live), with a completed MonsterRoomBoss,
no active overlay, no choices/cancel action, and agreeing run coordinates.
It records `boss_completion` and waits for the following boss or actual terminal screen (after the Heart that is
`TrueVictoryRoom`, whose `NO_INTERACT` ending cutscene is never command-ready; the driver treats that room as a terminal
victory, live problem 60); it does
not declare victory from the boss-room phase alone. Differential capture
retains the native unsupported boundary for this UI-only transition.
The following `Spire Heart` story in `VictoryRoom` is also mechanical: the
installed JAR's button handler advances its single index-zero option through
the narrative screens, then opens the end screen or the final-act door.
The driver requires that exact room/event identity, enabled physical choice,
and Act 3 victory-room floor (51, or 52 at A20). It records
`victory_dialogue`; other one-choice events still require their provider.

Combat targets are lowered from the captured explicit native `slot`/`idx` to
MCP's compact living-monster list in its displayed order. The slots can have
holes after Slime Boss splits or a summon replaces an occupant; array position
is not a native slot. Once a dead Slime Boss has been observed replaced by
its large children, the producer remembers that physical parent's retirement
through subsequent splits and deaths; it cannot reappear with slot -1 after
the large children leave the list. Other split/summon corpses are omitted only
when the public birth tracker proves that a known slot belongs to another
physical occupant. Current corpses, half-dead and unbound living objects are
not discarded by this rule. Missing/dead targets, duplicate slots and contradictory
slot/idx fields are rejected for both card and potion actions.

In-combat `CARD_REWARD`, `GRID` and `HAND_SELECT` modals use Silver.
Non-skippable Discovery/Colorless Potion offers support exactly three distinct,
unmodified cards and one or two zero-cost copies. The chosen option lowers to
its captured MCP choice index. Discovery's sole pending `UseCardAction` is
restored through native interrupted-card replay, preserving exhaust/discard
cleanup and physical card identity; unrelated queued actions are rejected.
A standalone potion offer clears historical current-card bookkeeping so an
already-completed card cannot replay. Typed Attack/Skill/Power Potion offers
include their exact Skip action. Toolbox preserves normal card costs and the
qualified ordered opening actions, including Bag of Preparation's draw,
Gambling Chip and Warped Tongs. Nilry's Codex resumes verified queued self-block actions
and Stone Calendar's literal damage before ending the turn after choosing or
skipping; lethal damage terminates combat without another turn. Extra
unrepresented queued relic/power actions remain unsupported; these popups never become deck rewards.
Combat capture uses the room's `COMBAT` phase, including event rooms, rather
than requiring a monster-room subclass. Selection boundary detection is
independent of native serializer support: an unknown selection task remains
combat and returns Silver `UNSUPPORTED` with `silver_unmapped_selection_task`,
allowing the normal deterministic combat fallback. Hand selections project the
screen's actual `canPickZero` value. The driver still stops on any genuine
boundary mismatch instead of reinterpreting OOC output as a Silver result.
Player selection continuations use the player's actual end-turn flags and
require empty enemy and pre-turn queues. Vanilla's `monsterAttacksQueued` is
not a pending-work flag: it remains true after the enemy turn and resets only
at the next player end-turn action. Rejecting that flag alone incorrectly
rejects later-turn Warcry and other otherwise qualified selections. Codex
retains its explicit end-turn continuation contract and queue validation.
Warcry, base Forethought, Armaments, Dual Wield, Exhume, Headbutt, one-card ExhaustAction,
Secret Technique and Secret Weapon derive their
selection task from the active vanilla action class, with exact screen/count
checks, before the legacy prompt-text fallback. These single-pick tasks
capture the physical card UUIDs in MCP's actual displayed order. Import checks
that the set matches eligible native cards, and lowering resolves that UUID
to its captured choice index, including duplicate card names. Completed single
HAND picks emit a verified model-free Proceed, retaining the native predecessor
session for the next stable combat root. Armaments, Dual Wield and Exhume capture cards
temporarily held by their owning action so the native source pile remains
complete. Upgraded Forethought, Gambling Chip/Gambler's Brew, and Purity/Elixir
emit the whole ordered UUID subset, including the empty subset. The driver
checks the action owner and selection limit, then clicks in the native
hand order, resolving each UUID against the remaining displayed hand before
every click. Vanilla appends to `selectedCards.group`, so this also preserves
the native exhaust/discard effect order. The driver validates remaining and
selected UUIDs after every click, then confirms. This avoids the installed MCP bulk command's ascending-index
mutation bug. Exhaust/discard triggers follow the original hand order after
the selected cards are removed. A partial transaction, unknown owner, missing/duplicate UUID, or
changed hand stops before any further click. Differential replay excludes UI
confirmations without an equivalent native state.

A source-card selection (`continuation: source_card_actions`) may also carry
the monster on-hit reactions vanilla queues with `addToBot` behind the
interrupted card, e.g. a Headbutt hit: `MONSTER_GAIN_BLOCK` (monster
self-`GainBlockAction` such as Malleable, with the emitted `slot`),
`REACTIVE_ROLL_MOVE` (Writhing Mass `RollMoveAction`, slot 0), `MONSTER_THORNS`
(defensive Guardian's Sharp Hide `DamageAction(player, THORNS)`, queued by
`onUseCard` ahead of `UseCardAction`, slot 0) and
`MONSTER_REDUCE_PLATED_ARMOR` / `MONSTER_REDUCE_FLIGHT` (`ReducePowerAction`
"Plated Armor" or Byrd "Flight" by 1), `MONSTER_CURL_UP` (a louse's
`ChangeStateAction` "CLOSED", which is animation only, plus `GainBlockAction` and
`RemoveSpecificPowerAction` "Curl Up"; imported as `MonsterGainBlock` with Curl Up
cleared, as native does at the hit) and `GUARDIAN_DEFENSIVE_SHIFT` (`VFXAction` plus
`ChangeStateAction` "Defensive Mode", last in the queue, after a hit crosses the
Mode Shift threshold; the importer emits nothing, and the wire settles Mode Shift <= 0
itself by shifting and queueing the 20 block behind the tail). The
first three become native `MonsterGainBlock`/`ReactiveRollMove`/`DamagePlayer` queue items
(Reactive's scalar counts the queued rolls); the Plated Armor and Flight losses are folded
into the imported monster because native applies them at the hit. A reduction
that would remove the power with a side effect (Shelled Parasite stun) stays unsupported; a living Byrd's
grounding at Flight 1 folds in as native applies it at the hit (Flight removed, a deferred Runic Dome roll cancelled,
Stunned next; `STS_SILVER_BYRD_GROUNDING_QUEUE`);
removing Plated Armor 1 from another monster (Donu, Deca) folds in (`STS_SILVER_PLATED_ARMOR_REMOVAL_QUEUE`). A lethal hit
still queues the reduction; it folds into the dead monster (`STS_SILVER_LETHAL_REACTION_QUEUE`). Also unsupported is
any other queued monster action. A Headbutt that kills a Darkling to half-dead leaves `SetMoveAction(Darkling, 4, UNKNOWN)` queued; the producer emits `MONSTER_SET_MOVE {move:4, slot}`, imported as native `SetMonsterMove(Regrow)` (`STS_SILVER_HALF_DEAD_SET_MOVE_QUEUE`); the producer checks only `isDying`/`isEscaping`/`escaped` for that Darkling, since `isDeadOrEscaped()` is true for every half-dead monster and refused the item (`half_dead_set_move`, problem 89, 2026-10-22). A Headbutt that kills a Bronze Orb holding a Stasis card leaves `MakeTempCardInHandAction(card, false, true)` queued (`StasisPower.onDeath`, hand under 10 cards); the producer emits `STASIS_RETURN {slot}` (orb slot 0 or 2 as Stasis slot 0 or 1; refused unless the card's uuid is that dead orb's Stasis card), and the importer moves the card to hand as native does at the death (`STS_SILVER_STASIS_RETURN_QUEUE`). A Headbutt that takes a large slime or the Slime Boss to half HP leaves `TextAboveCreatureAction` + `SetMoveAction(3)` queued (the split is already the current move); the producer emits `MONSTER_SPLIT_SET_MOVE {slot}`, and the importer writes the split as the previous move too (`STS_SILVER_SLIME_SPLIT_QUEUE`). A Headbutt that kills the Gremlin Leader leaves a `ShoutAction` then an `EscapeAction` per surviving minion queued; the producer emits `MINION_LEADER_ESCAPE {slots}` (refused unless the shouts and escapes name the same creatures in order and those are exactly the surviving gremlins), and the advisor answers the grid with `choose 1` as a forced pass-through, since native already ended the combat at the kill (`STS_SILVER_LEADER_ESCAPE_PASS_THROUGH`). A Headbutt that wakes a sleeping Lagavulin leaves `ChangeStateAction("OPEN")` queued (OPEN is already set); the producer emits `MONSTER_LAGAVULIN_OPEN {amount, slot:0}` with the unreduced Metallicize, and the importer folds the wake's Metallicize reduction by native's rule (`STS_SILVER_LAGAVULIN_OPEN_QUEUE`). In the wire, a pending action's JSON now carries `monster` (native
index, `0` when absent). Native
conversions capture the same two queue items as an exact tail
(`STS_SILVER_MONSTER_REACTION_QUEUE`, default on; `=0` restores the legacy
unobserved tail and its card-replay fallback).
Under Runic Dome the folded Reactive count is accepted for Writhing Mass when the
queue carries its `REACTIVE_ROLL_MOVE` (live seed 111200416): the mod's history has
not counted the queued reroll, and native defers it under hidden intents with the
inputs of the moment it runs, as Java's `RollMoveAction` rolls then
(`STS_IMPORTER_RUNIC_DOME_REACTIVE_FIX`, default on; `=0` restores the refusal
`silver_runic_dome_monster_power_domain`).

Runic Dome also covers Act 4 (THE_HEART and SHIELD_AND_SPEAR). The Java moves
there follow a public `moveCount` cycle: the Heart opens with Debilitate (a roll
that does not advance `moveCount`), then flips Blood Shots/Echo, plays the other
one (Echo unless it just echoed) and Buffs; the Shield flips Fortify/Bash, plays
Bash unless it just bashed, then Smash; the Spear plays Burn Strike unless it
just did, then Skewer, then flips Piercer/Burn Strike. The tracker accepts these
monsters only in act 4, patches their `takeTurn`, and exports every roll the
executed history determines as a known next move of kind `act4_public_cycle`;
only the coin flips stay pending hidden rolls. The importer recomputes the cycle
from `completedTurns` and the last executed move and refuses a missing, extra or
wrong proof (`STS_IMPORTER_RUNIC_DOME_ACT4`, default on; `=0` restores the
refusal `silver_runic_dome_encounter_domain`). No live Dome run has reached Act 4
yet; the Java cycles come from the canary's `javap` of CorruptHeart, SpireShield
and SpireSpear.

A split- or summon-born occupant's birth roll may carry `aliveCount` 0 (live seed
111200458 s546, problem 63): Java rolls the child's first move in `init()` before
`SpawnMonsterAction` adds it to the group, so the first Slime Boss child sees only the
dead boss. The importer accepts 0 only when `rollGlobalTurn == birthGlobalTurn` on a
non-initial row (`STS_IMPORTER_RUNIC_DOME_NEWBORN_ALIVE_FIX`, default on; `=0` restores
the refusal `silver_runic_dome_history_schema`).

Liquid Memories qualifies its exact owning action and one- or two-card count.
The two-card native decision preserves selection order, including the case
where only one card fits in hand. The driver clicks the ordered physical UUID
pair using stable GRID indices, checks the offered and selected UUIDs before
the second click, and lets vanilla close the grid automatically. This differs
from HAND selections, which remove chosen cards and require confirmation.
An unsupported partial selection observation emits no executable advice and
invalidates its cached root/budget, but retains the previously validated Silver
graph only for the same protocol session and combat entry. The next valid
snapshot is fully reimported and searched. A different session/combat cannot
inherit that predecessor; native search/lowering failures still clear it.

At an otherwise stable player decision, an unretrieved, nonempty hand
selection with no current action is an abandoned transaction, not normal play.
The producer marks `orphanedHandSelection`; native import refuses it with
`silver_orphaned_hand_selection` before searching incomplete piles. It never
deduplicates card UUIDs or mutates the game to repair an abandoned selection.

MCP can advertise readiness before a Soul animation initializes a newly created
card's cached damage/block/magic display in draw or discard. If the pre-click
check changes only by the presence of a positive cached stat in those piles,
the driver discards the unexecuted Silver decision and reads/correlates/maps a
fresh snapshot. It allows at most three consecutive refreshes per action and
traces each as `combat_display_refresh`; discarded decisions do not count as
accepted Silver actions. The state identity itself stays strict. Changes to
HP, energy, hand, costs, UUIDs, order, base fields or two different present
stat values still stop before mutation. Zero/absent ambiguity remains strict,
and differential replay does not use this refresh path.
A pile card that settles a frame after it moved also refreshes
(`STS_LIVE_PILE_SETTLING_REFRESH`, default on; `=0` restores the strict stop;
problem 82). This covers a card with the same UUID and id at the same
draw/discard/exhaust position whose `cost`, `is_playable`, `damage`, `block`,
`magic_number` or `base_*` values changed. A card exhausted by its own use is
first snapshotted with its in-use cost 0, playability and hand stats (all 36
transient dumps of seeds 450-519). Upgrades, UUIDs, order, the hand
and every other field stay strict. The match only discards the decision and
re-reads, within the same three-refresh limit.
OOC correlation takes act, floor, HP, max HP and gold from MCP `game_state`
when get_screen's copy differs (`STS_LIVE_OOC_GAME_STATE_STATS`, default on;
`=0` restores the screen-first merge; problem 86, seed 111200523). After
Ceramic Fish's +9 gold at the Transmogrifier, get_screen kept 229 for the
whole wait, while game_state, the inspector's `publicState` and its captured
`mcpState` all said 238.
Inspector correlation also accepts the Awakened One rebirth window
(`STS_LIVE_REBIRTH_CORRELATION`, default on; `=0` restores the refusal;
problem 85, seed 111200512). MCP lists no monsters while all of them are dead
or halfDead, so neither the hand nor the monster comparison could run. When
both hands are empty, the MCP monster list is empty and every inspector
monster is dead or halfDead, the snapshot counts as correlated. A stale
snapshot that still shows a live monster keeps failing.
MCP also reports exhaust-pile cards with stale displayed values (overnight
2026-10-19: `damage` 10 vs 4 with `base_damage` 4), so the exhaust pile is treated like draw
and discard: a positive explicit base replaces a different displayed stat in
the state identity, and a stat appearing or disappearing there takes the refresh path. A JSON
`null` base counts as absent, and a negative base (Java's -1 for a card
without that stat) drops both the base and its derived display value. Hand
values and pile-card costs/playability stay strict.

Card-reward skips are retained by session and an opaque, read-only identity of
that physical reward. Returning to the combat-reward list collects other
rewards or proceeds instead of reopening the skipped group. These identities
do not expose unopened card contents. A repeated OOC state/action pair stops
before another mutation and emits a failure packet; distinct physical rewards
remain distinguishable even when their visible offers match.

A real integration error exits nonzero and atomically writes
`<trace>.failure.json`: current MCP state/identity, inspector snapshot and
identity, evaluators, selected hint and mapping diagnostics, exact error,
recent trace rows, Git identity, and reproduction command. A
`LIVE_DRIVER_ERROR` line identifies the packet. Terminal outcomes and step
bounds exit zero. The final JSONL summary records reached act/floor/HP,
Silver/OOC/fallback counts, exact unsupported reasons and latency count/mean/
p50/p95/max. The trace is integration evidence only, never a win-rate benchmark.

Focused checks are `live_ooc_parity`, `live_ooc_policy`, `live_ooc_protocol`,
`live_game_driver` and the existing Silver/protocol regressions. Native fixtures
project ordinary states into the live JSON schema and compare all 42 globals,
deck/relic/potion tokens, candidate order/encodings, semantic keys/payloads,
per-action Q and argmax. Driver fixtures prove stale/malformed actions cause
zero mutations, a failure packet and nonzero exit. Live screen coverage and
run progress are recorded in the task's PR evidence packet, not promoted into
benchmark evidence.

Run the endpoint after building:

```text
build/linux-gcc-debug/one_combat_advisor
```

Use `tools/mod/doctor.sh` to locate the standard Steam installation and
workshop dependencies. Build the local JAR with
`mods/sts-model-inspector/build.sh MODTHESPIRE.jar BASEMOD.jar desktop-1.0.jar`.
The bundled Steam runtime is sufficient to launch the game but does not ship a
Java compiler, so a Java 8 JDK is needed for the build; the helper does not
install one or alter system defaults.

For a handshake:

```json
{"protocol":"sts_model_inspector_v1","kind":"hello"}
```

An observation must include `session`, `sequence`, `observationHash`, and an
object containing a string `boundary`. The response echoes the identity fields
so a future game UI can discard responses after a reload or newer capture.

## Remaining bounded boundary

The Java process owns bounded background I/O and treats the endpoint as
advisory only. Common Grid and Hand card-selection screens are mapped to the
native selection tasks for Exhaust, Armaments, Dual Wield, Headbutt, Exhume,
Warcry, Gambler's Brew, Liquid Memories, and Hologram. The mapping remains
deliberately bounded: an unrecognized selection prompt, an unavailable runtime
tracker, or an option list larger than the native representation is rejected.
The ordinary player limbo pile is serialized. Native `Monster::rollMove` and
`CombatKnowledgeState` represent hidden rolls using public executed-move
history, `pendingMoveRolls`, `pendingDirectMoveChoice`, and roll-time
`pendingRollInputs`. The Java Dome observer now starts at `MonsterGroup.init`
before initial rolls, captures public HP at roll entry, and records an audited
move only when its concrete `takeTurn` executes. It survives the later battle
callback and includes epoch/generation in the observation. Raw queued intent,
private move history and live RNG are omitted.

The supported roster and public knowledge contract are listed in the combat
import section above, including stable audited groups, Spot Weakness predicates
and small Acid Slime's deterministic known-next proof. Unknown lifecycle,
replacements, unaudited rerolls or overrides, missing initial history and
unqualified generators remain fail-closed. Save resume during an unobserved
combat does not manufacture earlier provenance.
Native fixtures check deferred-roll public-input/history parity, including
roll-time HP that differs from current HP. These fixed fixtures do not qualify
all encounters or establish live whole-fight/gameplay quality.

General action-queue metadata remains outside the supported boundary. CTM and
Silver results remain separate evaluators, and neither path controls gameplay
or establishes policy-quality evidence. Further public-state support requires
its native parity fixture and explicit public-information contract.

Knowledge impact: this page records the protocol/lifecycle boundary, the
player-visible combat gate, protocol-v4 producer/importer contract, explicit
fail-closed state handling, selection coverage, and the producer coverage
boundary.
