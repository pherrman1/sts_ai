# Fair discovery REST diagnostic candidate

The selected source is **Fprod, seed 610081015, act 3 floor 44**, at `build/overnight_20261008/wave1/Fprod_3.trace.jsonl:783`. Trace index 142 is not the GEN2 observer decision index. The completed shard receipt binds source `736d1ff7e61725d9c6a50326064b2e3060ce6ae4`, binary SHA256 `3f69f5fd251ac699580bca8eb8da707282c77bc5263732f10e83f8e2670aba2d`, public futures 8 and the Fprod policy. The trace SHA matches that receipt. The source trajectory's outcome and all battle rows were not inspected for this selection.

The root has 85/85 HP and no potions. Its observed transition is REST to MAP with unchanged visible HP, deck and relic identities. It has no Fusion Hammer, Dream Catcher, Girya, Peace Pipe or Shovel. Several useful cards remain unupgraded. Exact chosen semantic key, legal options, relic counters and GEN2 replay identity still require the zero-future target preflight. This is **SUSPICIOUS_UNTESTED**, not a confirmed win-probability error.

The public packet is `fair_rest_610081015_a3f44.public.json`; `fair_rest_610081015_a3f44.preflight_target.json` is the initial target request. Its public packet intentionally omits post-state and outcome; however, the strategy review itself is action-selected because locating the case used its REST-to-MAP transition. It must not be labeled blinded to the chosen action. A separate reviewer can rank the public packet before seeing the action or labels.

## Public alternatives before any continuation labels

| Candidate | Public reason to test | Competing explanation / uncertainty |
|---|---|---|
| SMITH Offering | In this 33-card deck, Offering+ draws five instead of three while retaining its two-energy gain and six-HP cost. Extra access to Shockwave+, Disarm, Exhume and damage can improve setup. | Draw timing, hand capacity, and altered learned combat choices can reverse a seemingly useful upgrade. No label has been seen. |
| SMITH Disarm | Disarm+ reduces enemy strength by three instead of two. Repeated multi-hit encounters can amplify one additional strength reduction. | Public trace omits the visible act boss identity and future path topology; the full target receipt should restore both. Some foes have artifact or cleanse. |
| SMITH Immolate | Immolate+ increases base damage from 21 to 28 on every enemy. Remaining multi-enemy fights may become shorter. | Lower marginal value in single-target final fights; attack timing and existing damage density matter. |
| Actual captured baseline | Required paired control for every tested semantic alternative. At full HP and without Dream Catcher, ordinary REST has no immediate healing/reward value. | The trace alone does not serialize the exact action; never substitute an assumed REST key for captured baseline. |

Mechanics checked in repository source: `src/combat/BattleContext.cpp` cases OFFERING, DISARM and IMMOLATE; `src/game/GameContext.cpp::chooseCampfireOption` handles REST and SMITH. Ancient Tea Set is charged on entering the rest site (`GameContext.cpp`, Room::REST), so it does not provide a special benefit to choosing REST over SMITH. Eternal Feather already produced any camp-entry healing represented in the root's full HP.

## Confounds excluded during local selection

A scan restricted to REST pre/post states in Fprod shards 0–4 (source seeds 610081000–610081019, before later shards completed) saw 160 REST screens, 54 full-HP roots, and 29 full-HP transitions to MAP. Seventeen remained after excluding Fusion Hammer and visible deck/relic changes; one has Girya and cannot be called no-benefit without its counter. These descriptive counts are not a completed-wave rate or independent statistical sample.

No final-floor49 clean full-HP no-op with SMITH apparently available was found in that bounded prefix. Late full-HP transitions often involved Fusion Hammer; full-HP Dream Catcher rests can still produce a card reward. Floor44 was preferred because it is near the actual Act-3 objective, has clear visible alternatives and avoids those confounds. No loss outcome was used to choose it.

The initial protocol should preserve actual baseline plus Offering, Disarm and Immolate canonical keys from preflight, subject to legal enumeration. Selection and evaluation k ranges must be preregistered and disjoint. Any selected alternative requires separate evaluation futures and later population validation; a favorable root diagnosis cannot promote a deployed policy.

Knowledge impact: experiment evidence only. This packet proposes a bounded local test; it does not change maintained gameplay facts or production defaults. No build or seed execution was performed by this specialist.
