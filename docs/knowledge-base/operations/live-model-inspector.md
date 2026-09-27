# Live model inspector

Last verified: 2026-09-27 for the combat final-HP panel and OOC endpoint HP; 2026-09-26 for two-offer Neow capture/import; 2026-09-25 for the native Silver evaluator; 2026-09-23 otherwise. This page describes the private integration
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
(`battleContextFromWire`), and runs a 1,000-simulation Silver decision by
default with the native `SilverSearcher` (the same search `one_combat` uses,
ADR-0021; responses carry `"engine": "native_silver"`). The combat
panel's `Silver +9k` button raises the active root budget to 10,000; each later
click adds another 10,000 (20,000, 30,000, ...). The retained Silver root is
continued incrementally, and any gameplay state change resets the next decision
to 1,000. The panel reports the requested budget, accumulated root visits, and
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
strategic model for policy priors, and `v_win_trees.txt` for compact-tree leaf
values. The default search budget is exactly 512 simulations with the native
OOC MCTS planner's default PUCT and progressive-widening configuration. The
search seed is derived from the request observation hash, so repeated
observations are reproducible without importing live RNG state. V4 remains
available only as the explicit `STS_LIVE_OOC_POLICY=v4` diagnostic path; it is
not the default and is not used as a post-hoc selector.
Newly expanded reward, shop, event, and selector states are continued through
the shared bounded dependency to a resolved map checkpoint before `v_win` is
evaluated. Semantic roots outside V4's screen support use uniform source
priors; REMOVE, TRANSFORM, and non-card reward roots are not rejected merely
because V4 cannot supply their prior.

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
boundary for runtime IDs. Monster move-history bytes are emitted in Java's
oldest-to-newest order and translated by the native importer through the
per-monster mapping; they are never copied as native enum values. Ordinary
draw order is sorted before emission; the actual runtime order is retained
when Frozen Eye is present. Under Runic Dome, the observer omits `nextMove`,
`moveHistory`, `intent`, and `intentDamage`; the root remains rejected because
the public producer does not expose enough pre-roll state for a fair import.
Sensitive player and monster powers carry the runtime `justApplied` bit when
the bounded reflection helper can read it and are rejected when it cannot.
The producer maps vanilla `RitualPower.skipFirst` to this field because that
power uses a different turn-local member name; `SlaverBlue` has stable native
`miscInfo` zero and is emitted explicitly as zero. The player-side
`Weakened` ID is an alias of native `Weak` and follows the same
`justApplied` requirement.
Special bookkeeping for Combust, Echo Form, Panache, Deva Form, Orange
Pellets, used-up relics, and Necronomicon is serialized when its runtime field
is accessible; otherwise the importer rejects that state. Monster `miscInfo`
is similarly serialized from known runtime trackers or omitted so the importer
fails closed. Bronze Orb Stasis uses the runtime `StasisPower.card` object to
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
`silver_card_queue_item`. The producer does not emit it yet. Without it, copies
queued by a spent Double Tap, Duplication or Necronomicon are missing from the
search root (issue #328). Boolean monster powers are
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
`null`. OOC inventory potion actions remain outside the current MCTS semantic
support boundary and show no badge. Freshness and unsupported/error suppression apply to potion scores
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
this is a timeout, not a delay. Gameplay transition timeouts stay separate.
It uses the seed guard and forwards arguments as an array; `--run` cannot be
combined with `--check` or `--foreground`. For a fresh run with no existing save:

```bash
tools/live_game_start.sh --super-fast --run -- \
  --new-run --character IRONCLAD --ascension 0 --run-until-error
```

`--super-fast` enables an already installed `mods/SuperFastMode.jar` (mod ID
`superfastmode`). Use `--restart-game` once if the running game lacks that mod.
Its local configuration is under `~/.config/ModTheSpire/SuperFastMode/`; the
debug setup uses `deltaMultiplier=4.0`, `isDeltaMultiplied=true`, and
`isInstantLerp=true`. The external JAR is not a repository artifact. Speed
changes remain subject to the same readiness and observation checks.

`--refresh-runtime` builds only `one_combat_advisor`, copies it and
the tracked CTM/OOC model artifacts into a new release, validates their hashes,
and atomically changes `current`. A running game is never silently restarted;
when it is using another release, the helper prints both identities and
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
ctmModel=<XDG data>/sts-ai/live-runtime/current/models/combat_transition_near_full_except_smoke_v2.native
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
driver. Only an explicit Silver `UNSUPPORTED` result may use the deterministic
fallback policy, and `--strict-silver` turns that boundary into a stop.
Non-combat screens use deterministic priorities over the generated legal
candidates, so no policy can invent an MCP tool name or arguments. The driver
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
  binding, relic data, visible boss, the complete visible 15-by-7 map and edges,
  current/burning-elite coordinates, exact whole-run and current-act path
  counts, completed combat floors and observed combat classes, acquired/lost relic identities, prior event
  identities, and the publicly recorded number of paid shop removals. A
  `seenRelics` list is accepted only when its producer marks the history
  complete. The Java observer accumulates visible shop, reward and boss offers
  from a fresh Neow boundary; a resumed or mid-run observer leaves the marker
  incomplete. A separate current-act combat-class observer records whether each
  fight consumed the normal or elite encounter queue, was a fixed event fight,
  or was a boss. The observer persists this public ledger in
  `~/.cache/sts-model-inspector/combat-history/<seed>-act<act>.tsv` and restores
  it on process restart, suppresses duplicate observations of the same current
  fight, and clears the sidecar at a positively identified fresh Neow run. Each
  normal/elite queue entry also stores the canonical encounter identity, so
  reconstruction restores the consumed native queue prefix rather than only
  its length. Legacy two-column sidecars and unknown identities fail closed. It
  then validates it against `damage_taken`. It qualifies
  only when every combat in the act is represented; a missing or contradictory
  sidecar still fails closed with `PUBLIC_COMBAT_CLASS_HISTORY_UNQUALIFIED`.
  An optional
  `rewardPityHistoryComplete` marker is reserved for synthetic captures with
  an exact reconstruction; the live Java producer leaves it false.
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
- `liveChoices`: occurrence-bound native action identities and single-command
  structured MCP hints. Duplicate labels are never action identity.
- `mcpState`: the exact current MCP screen conversion used by the driver to
  reject observation/screen/offer mismatches before mutation.
- `unsupportedReason`: an explicit producer qualification boundary, when the
  live state cannot be represented exactly. Missing or malformed schema fields
  are errors, not permission to guess an action.
- `captureError`: an unexpected capture or identity failure. This always stops
  the driver, including when an unsupported reason is also present.

Combat rewards with a full potion inventory are fail-closed at this boundary:
the native OOC candidate set and the inspector omit the potion-take candidate,
leaving other rewards and `proceed` available. The current MCP reward surface
does not expose the vanilla discard-potion command, so this is not discard
support or a claim of whole-game reward equivalence.

The live driver opens an unrevealed card reward only after all claimable
non-card rewards in that combat reward have been collected. This preserves the
simulator continuation order (gold, relic, potion, then card choice; keys stay
normal OOC choices) and
ensures the card scorer sees the post-collection root state.

Path counts derive from persisted `metricData.path_taken`, whose original map
symbols survive event-to-room conversion and save/resume. Completed combat
floors additionally come from `metricData.damage_taken`. The observed live room
class distinguishes a `?` floor that became a hallway fight from a fixed event
fight on the same map symbol: only the former advances the normal encounter
queue. The combat-class ledger is checked against completed public combat
floors without indexing `path_taken` by absolute floor. Wing Boots' public
charge counter is copied into the native root only to identify the explicit
active-MAP unsupported boundary; the frozen simulator/value-model integration
does not enable Wing Boots map expansion here. Missing or
contradictory history is unsupported. A historical unknown boss-transition marker is qualified only
after fifteen public map-room entries for that act and a matching public boss
combat floor; other unknown path symbols remain unsupported. Public metric
history conditions current-act normal/elite
encounter consumption, relic-pool membership, one-time/event membership, and
shop-removal cost. Currently visible shop, combat-reward, and boss-relic offers
are also removed from every reconstructed relic pool because native generation
consumes a relic when it is offered, not when it is acquired. Historical
seen-but-skipped offers are absent from vanilla metrics. An uninterrupted
fresh-run observer accumulates them from each public screen; random-relic
branches and direct MAP search fail closed with
`PUBLIC_SEEN_RELIC_HISTORY_UNQUALIFIED` when that ledger is incomplete. The
resolved `?`-room outcome ledger is not yet persisted in the live producer;
therefore any current-act history containing event-room visits fails closed
with `PUBLIC_QUESTION_ROOM_HISTORY_UNQUALIFIED`, and no uniform historical
room sampler is used. Events whose native `StateInfo` fields are not captured
(`ShiningLight`, `Ghosts`, `WindingHalls`, and `WorldOfGoop`) are unsupported.
Unopened treasure is likewise unsupported until `setupTreasureRoom()` state
(`chestSize`, `haveGold`, and `tier`) is imported; a Java chest class alone is
not sufficient. The
private Java `potionChance` and `cardRarityFactor` counters are
not captured. Roots such as Library, Mushrooms and Mysterious Sphere whose pre-MAP
continuation can generate potion or card rewards fail closed with
`PUBLIC_REWARD_PITY_HISTORY_UNQUALIFIED`. The v_win leaf marginalizes those
features with the exact discrete mixture `E[sigmoid(margin)]` over a bounded
native lattice (`potionChance` -40 through 60), never applying the link to an
expected margin. Real live captures do not claim an exact pity history: direct V4 requests fail closed and
MCTS uses an equal public prior rather than a fabricated midpoint. Synthetic
parity fixtures may mark an exact pity reconstruction explicitly. Live
hypothetical room-chance and pity counters are sampled once per root particle.
Room chances use the public current-act `?` visit count and jointly advance
all three counters for each sampled latent room outcome, so every sampled
triple is reachable under the native update rule. The shared simulator
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
paths. Every downstream MAP state is a hard planner leaf before expansion.
The lattice-valid hidden-counter prior is still broad rather than an exact
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
without endpoints report `unresolved` samples. In the live configuration
(`stopAtMapCheckpoint`, zero leaf combats) every simulation ends at the next
map: measured on the CI fixtures, a map root's endpoints are all floor +1 and
card-reward, event and rest roots stay on floor +0, so a card reward's HP is
constant. The capture changes no draws, visits, values or selection
(`ooc_mcts` and `live_ooc_protocol` check this).

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
purchase types, shop-removal entry, chest open/leave and boss relic take/skip. The existing V4
support gate still excludes non-card reward collection, removal/other
selectors and the final map-to-boss transition. The live producer additionally
qualifies event phases, path history, special maps, shop slot provenance,
relic-counter representation, and key-disabled campfires. A screen-specific
unsupported phase takes precedence over path and relic warnings, so a terminal
event outro cannot be misread as its initial decision. Unopened card reward
groups expose only their occurrence/type and require the driver to open the
group after parent reward collection; their concealed card identities are not
serialized or scored. Wing Boots is imported with a separate public charge
  counter, while direct MAP roots with active charges fail closed because the
  frozen value models do not encode remaining charges; Matryoshka, Lizard Tail and N’loth’s Hungry Face are unsupported
where live/native counter initialization differs. Maw Bank has an explicit
source-derived active/spent conversion, and a spent Neow's Lament or
Omamori reporting Java's used-up -2 is native 0 remaining charges in both the
OOC capture and the combat-entry payload, because the CTM rejects negative
charge data; other
unqualified positive counters
are unsupported. A deck containing upgraded Searing Blow returns
`SEARING_BLOW_UPGRADE_HISTORY_UNQUALIFIED`, because public card fields cannot
reconstruct the native history-dependent upgradeable count. Confirmation-only
screens and unsupported dialogue phases are explicitly accounted fallbacks.
These limits must not be presented as whole-game equivalence.

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

In-combat potion/discovery `CARD_REWARD` modals follow the inspector's OOC
boundary, with explicit unsupported fallback when skipping is unavailable.
Combat `GRID`/`HAND_SELECT` boundaries continue to use Silver.
Combat capture uses the room's `COMBAT` phase, including event rooms, rather
than requiring a monster-room subclass. Selection boundary detection is
independent of native serializer support: an unknown selection task remains
combat and returns Silver `UNSUPPORTED` with `silver_unmapped_selection_task`,
allowing the normal deterministic combat fallback. Hand selections project the
screen's actual `canPickZero` value. The driver still stops on any genuine
boundary mismatch instead of reinterpreting OOC output as a Silver result.

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
The ordinary player limbo pile is serialized. The remaining common combat
exclusion is live Runic Dome because exact public pre-roll reconstruction has
not been proven. Other unsupported queue metadata remains outside the
supported boundary. CTM and Silver results remain separate evaluators, and
neither path controls gameplay or establishes policy-quality evidence. Any
future public-state expansion must add a native parity fixture and an explicit
public-information contract before promotion.

Knowledge impact: this page records the protocol/lifecycle boundary, the
player-visible combat gate, protocol-v4 producer/importer contract, explicit
fail-closed state handling, selection coverage, and the producer coverage
boundary.
