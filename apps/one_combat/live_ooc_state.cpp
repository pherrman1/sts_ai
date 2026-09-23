#include "live_ooc_state.h"

#include <algorithm>
#include <cstdint>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <stdexcept>
#include "constants/SaveFileMappings.h"
#include "sim/search/GameAction.h"
#include "sim/search/OocSemanticAction.h"

namespace one_combat::advisor {
namespace {
using J = nlohmann::json;
using namespace sts;
using A = search::GameAction;
using RT = A::RewardsActionType;

void require(bool yes, const std::string &why) {
    if (!yes) throw std::invalid_argument(why);
}
int integerValue(const J &v, int lo, int hi, const std::string &key) {
    require(v.is_number_integer(), key + " must be an integer");
    if (v.is_number_unsigned()) {
        const auto n=v.get<std::uint64_t>();
        require(hi>=0 && n<=static_cast<std::uint64_t>(hi) && (lo<=0 || n>=static_cast<std::uint64_t>(lo)),key+" out of range");
        return static_cast<int>(n);
    }
    const auto n=v.get<std::int64_t>();
    require(n>=lo && n<=hi,key+" out of range");
    return static_cast<int>(n);
}
int integer(const J &o, const char *key, int lo, int hi) {
    return integerValue(o.at(key),lo,hi,key);
}
bool boolean(const J &o, const char *key) {
    require(o.at(key).is_boolean(), std::string(key) + " must be a boolean");
    return o.at(key).get<bool>();
}
std::string string(const J &o, const char *key) {
    require(o.at(key).is_string(), std::string(key) + " must be a string");
    return o.at(key).get<std::string>();
}
const J &array(const J &o, const char *key, std::size_t max) {
    const auto &v = o.at(key);
    require(v.is_array() && v.size() <= max, std::string(key) + " invalid array");
    return v;
}
template<class T> T id(const J &v, T invalid) {
    require(v.is_string(), "entity ID must be a save-file string");
    const auto result = v.get<T>();
    require(result != invalid, "unknown entity ID: " + v.dump());
    return result;
}
Card card(const J &v) {
    const auto cid = id<CardId>(v.at("id"), CardId::INVALID);
    Card c(cid, boolean(v, "upgraded") ? 1 : 0);
    c.misc = integer(v, "misc", std::numeric_limits<std::int16_t>::min(), std::numeric_limits<std::int16_t>::max());
    return c;
}
Room room(const J &v) {
    require(v.is_string(), "room must be a canonical name");
    for (int i=0; i<10; ++i) if (v == roomStrings[i]) return static_cast<Room>(i);
    throw std::invalid_argument("unknown room");
}
ScreenState screen(const std::string &name) {
    if (name == "card_reward" || name == "combat_reward" || name == "rewards") return ScreenState::REWARDS;
    if (name == "rest") return ScreenState::REST_ROOM;
    if (name == "shop") return ScreenState::SHOP_ROOM;
    if (name == "map") return ScreenState::MAP_SCREEN;
    if (name == "treasure") return ScreenState::TREASURE_ROOM;
    if (name == "boss_relic") return ScreenState::BOSS_RELIC_REWARDS;
    if (name == "event" || name == "neow") return ScreenState::EVENT_SCREEN;
    if (name == "selector" || name == "upgrade" || name == "remove") return ScreenState::CARD_SELECT;
    throw std::invalid_argument("unknown OOC screen");
}
std::uint32_t primitive(const J &choice, ScreenState s) {
    const auto &n = choice.at("nativeAction");
    const auto kind = string(n, "kind");
    const int index = integer(n, "index", 0, 255);
    if (s == ScreenState::REWARDS || s == ScreenState::SHOP_ROOM) {
        if (kind == "card") return A(RT::CARD, s == ScreenState::REWARDS ? integer(n,"group",0,4) : index,
                                    s == ScreenState::REWARDS ? index : 0).bits;
        if (kind == "gold") return A(RT::GOLD,index).bits;
        if (kind == "relic") return A(RT::RELIC,index).bits;
        if (kind == "potion") return A(RT::POTION,index).bits;
        if (kind == "key") return A(RT::KEY,index).bits;
        if (kind == "remove") return A(RT::CARD_REMOVE,index).bits;
        if (kind == "skip") return A(RT::SKIP,index).bits;
    } else if (kind == "option") return A(index).bits;
    throw std::invalid_argument("invalid nativeAction for screen");
}
void validateHint(const J &hint) {
    const auto k = string(hint, "kind");
    if (k == "choose") {
        integer(hint,"choiceIndex",1,1000);
        require(hint.size() == 2, "unexpected choose hint fields");
    } else {
        require(k == "skip" || k == "proceed" || k == "cancel" || k == "confirm", "unknown liveAction kind");
        require(hint.size() == 1, "unexpected liveAction fields");
    }
}
LiveOocStateV1::LiveOocMctsRootV1 makeMctsRoot(const LiveOocStateV1 &source) {
    // The constructor supplies canonical act/pool/history support from a
    // fixed hypothetical seed. It is deliberately overwritten with the
    // public observation below and re-randomized by sampleNoncombatFuture.
    constexpr std::uint64_t hypotheticalSeed = 0x4f4f435f4c495645ULL;
    sts::GameContext root(sts::CharacterClass::IRONCLAD, hypotheticalSeed,
                          source.projected.ascension);
    if (source.projected.act != 1)
        root.transitionToAct(source.projected.act);

    root.seed = 0;
    root.outcome = source.projected.outcome;
    root.screenState = source.projected.screenState;
    root.lastRoom = source.projected.lastRoom;
    root.curEvent = source.projected.curEvent;
    root.boss = source.projected.boss;
    // Keep the constructor's public prior for hidden reward/event counters.
    // Live Java's private blizzard counters are deliberately not imported.
    root.shopRemoveCount = source.projected.shopRemoveCount;
    root.wingBootsCharges = source.projected.wingBootsCharges;
    root.opaqueCardRewardGroups = source.projected.opaqueCardRewardGroups;
    root.curMapNodeX = source.projected.curMapNodeX;
    root.curMapNodeY = source.projected.curMapNodeY;
    root.floorNum = source.projected.floorNum;
    root.act = source.projected.act;
    root.ascension = source.projected.ascension;
    root.cc = source.projected.cc;
    root.curHp = source.projected.curHp;
    root.maxHp = source.projected.maxHp;
    root.gold = source.projected.gold;
    root.potionCount = source.projected.potionCount;
    root.potionCapacity = source.projected.potionCapacity;
    root.potions = source.projected.potions;
    root.relics = source.projected.relics;
    root.deck = source.projected.deck;
    root.blueKey = source.projected.blueKey;
    root.greenKey = source.projected.greenKey;
    root.keysEnabled = source.projected.keysEnabled;
    root.restRoomResolved = source.projected.restRoomResolved;
    root.redKey = source.projected.redKey;
    root.info = source.projected.info;
    root.map = source.projected.map ? std::make_shared<sts::Map>(*source.projected.map) : root.map;

    if (root.curMapNodeY >= 0 && root.curMapNodeY < 15
            && root.curMapNodeX >= 0 && root.curMapNodeX < 7 && root.map)
        root.curRoom = root.map->getNode(root.curMapNodeX, root.curMapNodeY).room;
    root.lastRoom = source.projected.lastRoom == sts::Room::INVALID
        ? root.curRoom : source.projected.lastRoom;

    const auto &publicState = source.ooc.at("publicState");
    const auto &actVisits = array(publicState, "currentActPathVisits", 10);
    require(actVisits.size() == 10, "ten current-act path counters required");
    // path_taken retains '?' after conversion and the damage metric has no
    // encounter class. Only the observed, complete combat-class ledger may
    // determine which native encounter queue was consumed.
    const auto &combatFloors = array(publicState, "combatFloors", 1000);
    const auto &combatHistory = array(publicState, "combatHistory", 1000);
    const bool combatHistoryComplete = boolean(publicState, "combatHistoryComplete");
    array(publicState, "pathHistory", 1000);
    const int actStartFloor = source.projected.act <= 1 ? 0
        : source.projected.act == 2 ? 17
        : source.projected.act == 3 ? 34 : 51;
    std::vector<int> completedCombatFloors;
    for (const auto &floorValue : combatFloors) {
        const int floor = integerValue(floorValue, 1, 1000, "combat floor");
        if (floor <= actStartFloor || floor > source.projected.floorNum) continue;
        completedCombatFloors.push_back(floor);
    }
    const int eliteVisits = integerValue(actVisits.at(static_cast<int>(Room::ELITE)),
        0, 1000, "current-act elite visits");
    const int eventVisits = integerValue(actVisits.at(static_cast<int>(Room::EVENT)),
        0, 1000, "current-act event visits");
    const bool questionHistoryComplete = publicState.contains("questionHistoryComplete")
        ? boolean(publicState, "questionHistoryComplete") : false;
    const auto &questionOutcomes = array(publicState, "questionOutcomes", 100);
    if (questionHistoryComplete) {
        require(questionOutcomes.size() == static_cast<std::size_t>(eventVisits),
                "complete question history length differs from event visits");
        int previousFloor = actStartFloor;
        root.monsterChance = 0.1f;
        root.shopChance = 0.03f;
        root.treasureChance = 0.02f;
        for (const auto &entry : questionOutcomes) {
            const int floor = integer(entry, "floor", actStartFloor + 1, source.projected.floorNum);
            require(floor > previousFloor, "question outcomes must follow floor order");
            previousFloor = floor;
            const auto outcome = string(entry, "outcome");
            Room room = Room::INVALID;
            if (outcome == "MONSTER") room = Room::MONSTER;
            else if (outcome == "SHOP") room = Room::SHOP;
            else if (outcome == "TREASURE") room = Room::TREASURE;
            else if (outcome == "EVENT") room = Room::EVENT;
            require(room != Room::INVALID, "unknown public question outcome");
            root.monsterChance = room == Room::MONSTER ? 0.1f : root.monsterChance + 0.1f;
            root.shopChance = room == Room::SHOP ? 0.03f : root.shopChance + 0.03f;
            root.treasureChance = room == Room::TREASURE ? 0.02f : root.treasureChance + 0.02f;
            if (floor == source.projected.floorNum) root.curRoom = room;
            if (floor + 1 == source.projected.floorNum) root.lastRoom = room;
        }
    }
    int normalCombats = 0, eliteCombats = 0;
    require(!combatHistoryComplete || combatHistory.size() == completedCombatFloors.size(),
        "complete combat history length differs from public combat metric");
    for (std::size_t i = 0; i < combatHistory.size(); ++i) {
        const auto &entry = combatHistory.at(i);
        const int floor = integer(entry, "floor", 1, 1000);
        const auto kind = string(entry, "kind");
        require(kind == "NORMAL_QUEUE" || kind == "ELITE_QUEUE" || kind == "FIXED_EVENT"
                || kind == "BOSS", "unknown public combat class");
        if (combatHistoryComplete)
            require(floor == completedCombatFloors.at(i), "combat history floor mismatch");
        if (kind == "NORMAL_QUEUE" || kind == "ELITE_QUEUE") {
            if (!entry.contains("encounter") || !entry.at("encounter").is_string()
                    || entry.at("encounter").get<std::string>().empty()) {
                // A resumed or otherwise incomplete ledger is already a
                // fail-closed boundary below. Do not promote its missing
                // queue identity into a schema error before that boundary can
                // be reported to the live driver.
                if (!combatHistoryComplete) continue;
                require(false, "queue combat identity is incomplete");
            }
            const auto encounterName = entry.at("encounter").get<std::string>();
            MonsterEncounter encounter = MonsterEncounter::INVALID;
            for (int candidate = 1; candidate < static_cast<int>(sizeof(monsterEncounterEnumNames)
                    / sizeof(*monsterEncounterEnumNames)); ++candidate)
                if (encounterName == monsterEncounterEnumNames[candidate]) {
                    encounter = static_cast<MonsterEncounter>(candidate);
                    break;
                }
            require(encounter != MonsterEncounter::INVALID, "unknown public encounter identity");
            if (kind == "NORMAL_QUEUE") {
                require(normalCombats < static_cast<int>(root.monsterList.size()),
                        "normal encounter history exceeds native queue");
                root.monsterList[normalCombats++] = encounter;
            } else {
                require(eliteCombats < static_cast<int>(root.eliteMonsterList.size()),
                        "elite encounter history exceeds native queue");
                root.eliteMonsterList[eliteCombats++] = encounter;
            }
        }
    }
    if (combatHistoryComplete)
        require(eliteCombats == eliteVisits,
            "elite combat history differs from elite map visits");
    root.monsterListOffset = normalCombats;
    root.eliteMonsterListOffset = eliteCombats;
    const auto eraseRelic = [&](RelicId relic) {
        for (auto pool : {&root.commonRelicPool, &root.uncommonRelicPool, &root.rareRelicPool,
                          &root.shopRelicPool, &root.bossRelicPool})
            pool->erase(std::remove(pool->begin(), pool->end(), relic), pool->end());
    };
    for (const auto &relic : array(publicState, "acquiredRelics", 181))
        eraseRelic(id<RelicId>(relic, RelicId::INVALID));
    const bool seenRelicsComplete = boolean(publicState, "seenRelicsComplete");
    require(array(publicState, "seenRelics", 181).size() <= 181,
        "seen relic history too large");
    if (seenRelicsComplete) {
        for (const auto &relic : array(publicState, "seenRelics", 181))
            eraseRelic(id<RelicId>(relic, RelicId::INVALID));
    }
    // Native pools consume relics when they are offered, not when acquired.
    // Condition every currently visible offer before Courier or another
    // within-checkpoint transition can draw from the reconstructed pools.
    if (source.projected.screenState == ScreenState::SHOP_ROOM) {
        for (int i=0; i<3; ++i)
            if (source.projected.info.shop.relicPrice(i) >= 0)
                eraseRelic(source.projected.info.shop.relics[i]);
    } else if (source.projected.screenState == ScreenState::REWARDS) {
        const auto &rewards = source.projected.info.rewardsContainer;
        for (int i=0; i<rewards.relicCount; ++i) eraseRelic(rewards.relics[i]);
    } else if (source.projected.screenState == ScreenState::BOSS_RELIC_REWARDS) {
        for (RelicId relic : source.projected.info.bossRelics) eraseRelic(relic);
    }
    const auto eraseEvent = [&](Event event) {
        for (auto pool : {&root.eventList, &root.shrineList, &root.specialOneTimeEventList})
            pool->erase(std::remove(pool->begin(), pool->end(), event), pool->end());
    };
    for (const auto &event : array(publicState, "priorEvents", 100))
        eraseEvent(id<Event>(event, Event::INVALID));
    if (root.curEvent != Event::INVALID && root.curEvent != Event::NEOW) eraseEvent(root.curEvent);

    const bool canDrawUnseenRelic = [&] {
        if (seenRelicsComplete) return false;
        // A direct MAP root searches its next room before the hard downstream
        // MAP checkpoint. Any branch may generate a relic offer there.
        if (source.projected.screenState == ScreenState::MAP_SCREEN) return true;
        if (source.projected.screenState == ScreenState::TREASURE_ROOM) return true;
        if (source.projected.screenState == ScreenState::REST_ROOM
                && root.relics.has(RelicId::SHOVEL)) return true;
        if (source.projected.screenState == ScreenState::SHOP_ROOM
                && root.relics.has(RelicId::THE_COURIER)) {
            for (int i = 0; i < 3; ++i)
                if (source.projected.info.shop.relicPrice(i) >= 0) return true;
        }
        if (source.projected.screenState != ScreenState::EVENT_SCREEN) return false;
        switch (root.curEvent) {
            case Event::BIG_FISH:
            case Event::PLEADING_VAGRANT:
            case Event::DEAD_ADVENTURER:
                return true;
            default:
                return false;
        }
    }();

    // These callbacks are only the public-screen continuation boundary. Any
    // callback that depends on an unrevealed prior room remains unsupported by
    // the importer rather than borrowing live Java state.
    root.regainControlAction = [](sts::GameContext &gc) {
        gc.screenState = sts::ScreenState::MAP_SCREEN;
        gc.regainControlAction = nullptr;
    };
    if (root.screenState == sts::ScreenState::BOSS_RELIC_REWARDS)
        root.regainControlAction = [](sts::GameContext &gc) { gc.transitionToAct(gc.act + 1); };

    LiveOocStateV1::LiveOocMctsRootV1 result;
    result.state = std::move(root);
    result.path = source.path;
    result.currentActEventVisits = eventVisits;
    // MAP roots are searchable with sampled room-outcome belief particles;
    // stopAtMapCheckpoint applies only after a searched transition. Random
    // relic branches still require complete public offer history.
    if (!combatHistoryComplete) {
        result.supported = false;
        result.reason = "PUBLIC_COMBAT_CLASS_HISTORY_UNQUALIFIED";
    } else if (!questionHistoryComplete && eventVisits > 0) {
        result.supported = false;
        result.reason = "PUBLIC_QUESTION_ROOM_HISTORY_UNQUALIFIED";
    } else if (canDrawUnseenRelic) {
        result.supported = false;
        result.reason = "PUBLIC_SEEN_RELIC_HISTORY_UNQUALIFIED";
    }
    return result;
}
} // namespace

ImportResult importLiveOocStateV1(const J &observation, LiveOocStateV1 &out) {
    try {
        require(string(observation,"boundary") == "ooc", "OOC boundary required");
        const auto &o = observation.at("ooc");
        integer(o,"schemaVersion",1,1);
        const auto screenName = string(o,"screen");
        require(!screenName.empty(),"OOC screen is empty");
        if (o.contains("captureError"))
            throw std::runtime_error("live capture integrity failure: " + string(o,"captureError"));
        std::string deferredUnsupportedReason;
        if (o.contains("unsupportedReason")) {
            const auto reason = string(o,"unsupportedReason");
            // A normal combat reward can expose gold alongside an unopened
            // card group. Defer this one support boundary until the complete
            // capture and its live mappings have been validated below.
            const bool hiddenCardReward = reason == "CARD_GROUP_NOT_REVEALED"
                && (screenName == "combat_reward" || screenName == "rewards");
            if (!reason.empty() && !hiddenCardReward)
                return {false,"UNSUPPORTED",reason};
            if (hiddenCardReward) deferredUnsupportedReason = reason;
        }
        LiveOocStateV1 next;
        next.ooc = o;
        auto &g = next.projected;
        const auto &p = o.at("publicState");
        next.rewardPityHistoryComplete = p.contains("rewardPityHistoryComplete")
            ? boolean(p, "rewardPityHistoryComplete") : false;
        require(string(p,"character") == "IRONCLAD", "only Ironclad is representable");
        g.cc = CharacterClass::IRONCLAD;
        g.seed = 0; // Never used. No live RNG or hidden queue is imported.
        g.ascension=integer(p,"ascension",0,20); g.act=integer(p,"act",1,4);
        g.floorNum=integer(p,"floor",0,1000); g.curHp=integer(p,"hp",0,32767);
        g.maxHp=integer(p,"maxHp",1,32767); require(g.curHp<=g.maxHp,"hp exceeds maxHp");
        g.gold=integer(p,"gold",0,1000000);
        // Hidden native blizzard counters are intentionally absent. These
        // compatibility fields are populated only for exact synthetic
        // fixtures; real captures mark rewardPityHistoryComplete=false, so
        // direct V4 fails closed and MCTS does not consume these values.
        g.potionChance=30;
        g.cardRarityFactor=-18;
        g.shopRemoveCount=integer(p,"shopRemoveCount",0,100);
        g.blueKey=boolean(p,"blueKey"); g.greenKey=boolean(p,"greenKey");
        g.keysEnabled=boolean(p,"keysEnabled"); g.redKey=boolean(p,"redKey");
        g.potionCapacity=integer(p,"potionCapacity",0,5);
        const auto &potions=array(p,"potions",5); require(potions.size()==5,"five potion slots required");
        for (int i=0;i<5;++i) {
            g.potions[i]=id<Potion>(potions[i],Potion::INVALID);
            require(i<g.potionCapacity || g.potions[i]==Potion::EMPTY_POTION_SLOT,"potion outside capacity");
            g.potionCount += g.potions[i]!=Potion::EMPTY_POTION_SLOT;
        }
        bool unqualifiedUpgradeHistory = false;
        for (const auto &v:array(p,"deck",Deck::MAX_SIZE)) {
            const Card c = card(v);
            const auto type = c.getType();
            // Native Deck::upgrade decrements its cached count even though
            // Searing Blow remains upgradeable. Public card fields cannot
            // recover whether upgrades happened before or after acquisition.
            unqualifiedUpgradeHistory |= c.getId() == CardId::SEARING_BLOW
                    && (c.isUpgraded() || c.misc != 0);
            require(type == CardType::ATTACK || type == CardType::SKILL
                    || type == CardType::POWER || type == CardType::CURSE,
                    "non-permanent card in deck");
            // Reconstruct bookkeeping without acquisition effects or obtainRaw's
            // historical double-counting. Match ordinary Deck::obtain state.
            g.deck.cards.push_back(c);
            if (type != CardType::CURSE || c.canTransform()) {
                ++g.deck.cardTypeCounts[static_cast<int>(type)];
                ++g.deck.transformableCount;
            }
            if (c.canUpgrade()) ++g.deck.upgradeableCount;
            const int binding=integer(v,"bottleBinding",-1,2);
            if(binding>=0) {
                require(g.deck.bottleIdxs[binding]==-1,"duplicate bottle binding");
                const CardType types[]={CardType::ATTACK,CardType::SKILL,CardType::POWER};
                require(g.deck.cards[g.deck.size()-1].getType()==types[binding],"bottle type mismatch");
                g.deck.bottleCard(g.deck.size()-1,types[binding]);
            }
        }
        std::set<RelicId> relicIds;
        for(const auto &v:array(p,"relics",181)) {
            const auto r=id<RelicId>(v.at("id"),RelicId::INVALID);
            require(relicIds.insert(r).second,"duplicate relic identity");
            const int modelData = integer(v,"data",-1000000,1000000);
            if (r == RelicId::WING_BOOTS) {
                require(v.contains("liveCounter"), "Wing Boots liveCounter missing");
                g.relics.add({r, 0});
                g.wingBootsCharges = std::max(0, integer(v,"liveCounter",0,3));
            } else {
                g.relics.add({r, modelData});
            }
        }
        g.boss=id<MonsterEncounter>(p.at("boss"),MonsterEncounter::INVALID);
        const auto &m=p.at("map");
        g.curMapNodeX=integer(m,"x",-1,6); g.curMapNodeY=integer(m,"y",-1,16);
        // The native inspector uses (-1, 15) while the act-boss room is
        // active: row 15 is the transition above the 15-row visible map and
        // has no selectable map node. Preserve that sentinel instead of
        // fabricating an x-coordinate; all ordinary map rows still require
        // a real x when y is non-negative.
        require(g.curMapNodeY < 0 || g.curMapNodeX >= 0
                    || (g.curMapNodeY == 15 && g.curMapNodeX == -1),
                "invalid current map coordinate");
        g.map=std::make_shared<Map>();
        g.map->burningEliteX=integer(m,"burningEliteX",-1,6);
        g.map->burningEliteY=integer(m,"burningEliteY",-1,14);
        require((g.map->burningEliteX<0)==(g.map->burningEliteY<0),"partial burning elite coordinate");
        for(int y=0;y<15;++y)for(int x=0;x<7;++x){g.map->nodes[y][x].x=x;g.map->nodes[y][x].y=y;}
        std::set<std::pair<int,int>> seen;
        const auto &nodes=array(m,"nodes",105);
        require(nodes.size()==105,"complete 15 by 7 visible map required");
        for(const auto &n:nodes) {
            const int x=integer(n,"x",0,6),y=integer(n,"y",0,14);
            require(seen.insert({x,y}).second,"duplicate map node");
            auto &node=g.map->nodes[y][x]; node.room=room(n.at("room"));
            std::set<int> children;
            for(const auto &e:array(n,"edges",3)) {
                const auto cx=integerValue(e,0,6,"edge child x");
                require(children.insert(cx).second,"duplicate map edge");
                node.addEdge(cx);
            }
        }
        // Reconstruct parent lists from the complete visible edge set.
        for(int y=0;y<14;++y)for(int x=0;x<7;++x) {
            auto &n=g.map->nodes[y][x];
            for(int e=0;e<n.edgeCount;++e) {
                require(seen.count({n.edges[e],y+1}),"map edge target missing");
                auto &child=g.map->nodes[y+1][n.edges[e]];
                require(child.parentCount < static_cast<int>(child.parents.size()), "map parent capacity exceeded");
                child.addParent(x);
            }
        }
        require(boolean(p,"pathComplete"),"path history not reconstructed");
        const auto &visits=array(p,"pathVisits",10); require(visits.size()==10,"ten path counters required");
        for(int i=0;i<10;++i) {
            require(visits[i].is_number_integer(),"path count must be integer");
            const auto n=visits[i].get<std::int64_t>();require(n>=0 && n<=1000,"path count out of range");
            next.path.roomVisits[i]=static_cast<int>(n);
        }
        // Java's path counters already include the currently visible room.
        // Preserve the current node identity so the shared OOC provider does
        // not count that room a second time at its root.
        if (g.curMapNodeY >= 0 && g.curMapNodeY < 15
                && g.curMapNodeX >= 0 && g.curMapNodeX < 7)
            next.path.lastNodeKey = static_cast<long>(g.act) * 100000L
                + static_cast<long>(g.curMapNodeY) * 100L + g.curMapNodeX;
        g.screenState=screen(screenName);
        if (g.screenState == ScreenState::MAP_SCREEN
                && g.curMapNodeX == -1 && g.curMapNodeY == 15
                && g.act >= 2 && g.act <= 3
                && g.floorNum == 17 * (g.act - 1)
                && boolean(p, "pathComplete")
                && o.contains("mcpState") && o.at("mcpState").is_object()) {
            const auto &mcp = o.at("mcpState");
            if (mcp.value("screen_type", "") == "MAP"
                    && mcp.contains("screen_state") && mcp.at("screen_state").is_object()) {
                const auto &state = mcp.at("screen_state");
                const auto &current = state.at("current_node");
                const auto &nextNodes = array(state, "next_nodes", 7);
                require(!boolean(state, "first_node_chosen")
                            && integer(current, "x", -1, 6) == -1
                            && integer(current, "y", -1, 15) == 15
                            && !nextNodes.empty(), "invalid next-act map sentinel");
                for (const auto &node : nextNodes)
                    require(integer(node, "y", 0, 14) == 0,
                            "next-act map choices must start in row zero");
                // Vanilla retains the previous boss node while displaying the
                // new act's first row. Native transitionToAct uses (-1,-1).
                g.curMapNodeY = -1;
            }
        }
        if (g.screenState == ScreenState::REST_ROOM && o.contains("details")
                && o.at("details").is_object() && o.at("details").contains("options")) {
            const auto &options = o.at("details").at("options");
            require(options.is_array(), "rest details.options must be an array");
            g.restRoomResolved = options.size() == 1 && options.at(0).is_number_integer()
                    && options.at(0).get<int>() == 6;
        }
        if (g.screenState==ScreenState::MAP_SCREEN && g.curMapNodeY>=14)
            return {false,"UNSUPPORTED","V4_BOSS_MAP_TRANSITION"};
        const auto &d=o.at("details"); require(d.is_object(),"details must be an object");
        if(g.screenState==ScreenState::TREASURE_ROOM && !d.value("opened",false)) {
            const auto size=string(d,"chestSize");
            if(size=="SMALL")g.info.chestSize=ChestSize::SMALL;
            else if(size=="MEDIUM")g.info.chestSize=ChestSize::MEDIUM;
            else if(size=="LARGE")g.info.chestSize=ChestSize::LARGE;
            else return {false,"UNSUPPORTED","TREASURE_STATE_UNREPRESENTABLE:chest_size"};
        }
        if(g.screenState==ScreenState::REWARDS) {
            auto &r=g.info.rewardsContainer;
            g.opaqueCardRewardGroups = d.value("opaqueCardRewardGroups", 0);
            require(g.opaqueCardRewardGroups >= 0 && g.opaqueCardRewardGroups <= 5,
                    "opaqueCardRewardGroups out of range");
            for(const auto &v:array(d,"gold",2)) r.addGold(integerValue(v,0,1000000,"gold reward"));
            for(const auto &group:array(d,"cardRewards",5)) {
                require(group.is_array() && !group.empty() && group.size()<=4,"invalid card reward group");
                CardReward reward;for(const auto &v:group)reward.push_back(card(v));r.addCardReward(reward);
            }
            for(const auto &v:array(d,"relics",3))r.addRelic(id<RelicId>(v,RelicId::INVALID));
            for(const auto &v:array(d,"potions",5))r.addPotion(id<Potion>(v,Potion::INVALID));
            r.emeraldKey=boolean(d,"emeraldKey");r.sapphireKey=boolean(d,"sapphireKey");
            require(!(r.emeraldKey&&r.sapphireKey),"native reward keys are mutually exclusive");
        } else if(g.screenState==ScreenState::SHOP_ROOM) {
            auto &s=g.info.shop;
            auto offers=[&](const char *key,int count,auto load) {
                const auto &vs=array(d,key,count);require(vs.size()==static_cast<std::size_t>(count),"shop slot count mismatch");
                for(int i=0;i<count;++i)load(vs[i],i);
            };
            offers("cards",7,[&](const J &v,int i){ s.cardPrice(i)=integer(v,"price",-1,1000000);if(s.cardPrice(i)>=0)s.cards[i]=card(v.at("card")); });
            offers("relics",3,[&](const J &v,int i){ s.relicPrice(i)=integer(v,"price",-1,1000000);if(s.relicPrice(i)>=0)s.relics[i]=id<RelicId>(v.at("id"),RelicId::INVALID); });
            offers("potions",3,[&](const J &v,int i){ s.potionPrice(i)=integer(v,"price",-1,1000000);if(s.potionPrice(i)>=0)s.potions[i]=id<Potion>(v.at("id"),Potion::INVALID); });
            s.removeCost=integer(d,"removeCost",-1,1000000);
        } else if(g.screenState==ScreenState::BOSS_RELIC_REWARDS) {
            const auto &rs=array(d,"relics",3);require(rs.size()==3,"three boss relics required");
            for(int i=0;i<3;++i)g.info.bossRelics[i]=id<RelicId>(rs[i],RelicId::INVALID);
        } else if(g.screenState==ScreenState::CARD_SELECT) {
            const auto kind=string(d,"type");
            if(kind=="upgrade")g.info.selectScreenType=CardSelectScreenType::UPGRADE;
            else if(kind=="remove")g.info.selectScreenType=CardSelectScreenType::REMOVE;
            else if(kind=="transform")g.info.selectScreenType=CardSelectScreenType::TRANSFORM;
            else if(kind=="bottle")g.info.selectScreenType=CardSelectScreenType::BOTTLE;
            else return {false,"UNSUPPORTED","selector_type:"+kind};
            g.info.toSelectCount=integer(d,"requiredPicks",1,3);
            for(const auto &v:array(d,"cards",96)) {
                const auto idx=integer(v,"deckIndex",0,g.deck.size()-1);
                const auto c=card(v.at("card"));require(c==g.deck.cards[idx],"selector card does not match deck");
                for(const auto &prev:g.info.toSelectCards)require(prev.deckIdx!=idx,"duplicate physical selector target");
                g.info.toSelectCards.push_back(SelectScreenCard(c,idx));
            }
            require(integer(d,"completedPicks",0,3)==0,"partially selected grid unsupported");
        } else if(g.screenState==ScreenState::EVENT_SCREEN) {
            const auto event=string(d,"event");
            g.curEvent=event=="Neow" ? Event::NEOW : id<Event>(d.at("event"),Event::INVALID);
            g.info.eventData=integer(d,"eventData",0,100);
            g.info.phase=integer(d,"phase",0,100);
            if (g.curEvent == Event::DEAD_ADVENTURER) {
                require(g.info.phase == 0, "Dead Adventurer later phase unsupported");
                const int encounter = integer(d,"deadAdventurerEncounter",0,2);
                constexpr MonsterEncounter encounters[] {MonsterEncounter::THREE_SENTRIES,
                    MonsterEncounter::GREMLIN_NOB, MonsterEncounter::LAGAVULIN_EVENT};
                g.info.encounter = encounters[encounter];
                g.info.rewards = {0,1,2}; // Hidden order is shuffled per root sample.
            }
            if(g.curEvent==Event::SHINING_LIGHT)
                g.info.hpAmount0=integer(d,"hpAmount0",1,g.maxHp);
            if(g.curEvent==Event::FORGOTTEN_ALTAR)
                g.info.hpAmount0=integer(d,"hpAmount0",0,g.maxHp);
            if(g.curEvent==Event::THE_LIBRARY)
                g.info.hpAmount0=integer(d,"hpAmount0",1,g.maxHp);
            if(g.curEvent==Event::WORLD_OF_GOOP)
                g.info.goldLoss=integer(d,"goldLoss",0,g.gold);
            if(g.curEvent==Event::GOLDEN_IDOL) {
                g.info.hpAmount0=integer(d,"hpAmount0",1,g.maxHp);
                g.info.hpAmount1=integer(d,"hpAmount1",1,g.maxHp);
            }
            // Fields used by native candidate/semantic enumeration are explicit even when inactive.
            g.info.upgradeOne=boolean(d,"upgradeOne");g.info.cleanUpIsRemoveCard=boolean(d,"cleanUpIsRemoveCard");
            g.info.skillCardDeckIdx=integer(d,"skillCardDeckIdx",-1,g.deck.size()-1);
            g.info.powerCardDeckIdx=integer(d,"powerCardDeckIdx",-1,g.deck.size()-1);
            g.info.attackCardDeckIdx=integer(d,"attackCardDeckIdx",-1,g.deck.size()-1);
            g.info.potionIdx=integer(d,"potionIdx",-1,4);g.info.gold=integer(d,"gold",-1,1000000);
            g.info.cardIdx=integer(d,"cardIdx",-1,g.deck.size()-1);
            if(g.curEvent==Event::NEOW) {
                const auto &ns=array(d,"neow",4);require(ns.size()==4,"four Neow offers required");
                for(int i=0;i<4;++i) {
                    g.info.neowRewards[i].r=id<Neow::Bonus>(ns[i].at("bonus"),Neow::Bonus::INVALID);
                    g.info.neowRewards[i].d=id<Neow::Drawback>(ns[i].at("drawback"),Neow::Drawback::INVALID);
                }
            }
            if (g.curEvent == Event::HYPNOTIZING_COLORED_MUSHROOMS
                    || g.curEvent == Event::MYSTERIOUS_SPHERE)
                return {false,"UNSUPPORTED","PUBLIC_REWARD_PITY_HISTORY_UNQUALIFIED"};
        }
        for(const auto &choice:array(o,"liveChoices",1024)) {
            primitive(choice,g.screenState);validateHint(choice.at("liveAction"));
        }
        if (!deferredUnsupportedReason.empty()) {
            // Validate that every visible gold reward has exactly one
            // distinct, well-formed captured click before allowing the
            // narrowly scoped pass-through. The regular unsupported boundary
            // remains in force after the last gold disappears.
            std::set<std::string> goldActions;
            int goldChoiceCount = 0;
            const auto &gold = array(d,"gold",2);
            for (const auto &choice : array(o,"liveChoices",1024)) {
                if (string(choice.at("nativeAction"),"kind") != "gold") continue;
                const int nativeIndex = integer(choice.at("nativeAction"),"index",0,255);
                require(nativeIndex < static_cast<int>(gold.size()),
                        "gold native index outside visible rewards");
                const auto &action = choice.at("liveAction");
                require(string(action,"kind") == "choose","gold choice must lower to choose");
                require(goldActions.insert(action.dump()).second,"duplicate gold live mapping");
                ++goldChoiceCount;
            }
            require(goldChoiceCount == static_cast<int>(gold.size()),
                    "gold reward/live mapping count mismatch: rewards="
                    + std::to_string(gold.size()) + " choices=" + std::to_string(goldChoiceCount));
            if (goldChoiceCount == 0) return {false,"UNSUPPORTED",deferredUnsupportedReason};
        }
        if (unqualifiedUpgradeHistory)
            return {false,"UNSUPPORTED","SEARING_BLOW_UPGRADE_HISTORY_UNQUALIFIED"};
        next.mctsRoot = makeMctsRoot(next);
        out=std::move(next);
        return {true,{},{}};
    } catch(const std::exception &e) {
        return {false,"SCHEMA_MISMATCH",e.what()};
    }
}

J lowerLiveOocAction(const LiveOocStateV1 &state,std::uint32_t bits) {
    J found;int count=0;
    for(const auto &c:state.ooc.at("liveChoices"))if(primitive(c,state.projected.screenState)==bits){found=c.at("liveAction");++count;}
    require(count==1,"OOC primitive mapping expected one occurrence; matches="+std::to_string(count));
    return found;
}
void validateLiveOocActionSet(const LiveOocStateV1 &state,const std::vector<std::uint32_t> &bits,
                              bool allowEquivalentDeckCards) {
    std::set<std::uint32_t> expected(bits.begin(),bits.end()), observed;
    std::set<std::string> retainedChoices;
    std::map<std::uint32_t,std::string> choiceByPrimitive;
    if (allowEquivalentDeckCards && state.projected.screenState == ScreenState::CARD_SELECT) {
        const auto bindings=search::enumerateOocSemanticPrimitiveBindings(state.projected);
        require(bindings.supported && bindings.complete,"native/live semantic enumeration incomplete");
        for(const auto &binding:bindings.bindings) {
            const auto key=search::canonicalOocMctsChoiceKey(binding.semantic);
            require(choiceByPrimitive.emplace(binding.primitiveBits,key).second,
                    "duplicate native selector primitive mapping");
            if(expected.count(binding.primitiveBits)) retainedChoices.insert(key);
        }
    }
    // Multiple semantic MCTS candidates may intentionally share one source
    // click; validate the source mapping as a set, not as a semantic list.
    for(const auto &c:state.ooc.at("liveChoices")) {
        const auto bit = primitive(c,state.projected.screenState);
        if (!expected.count(bit)) {
            const auto action = search::GameAction(bit);
            const bool displayedPrismaticShard = state.projected.screenState == ScreenState::SHOP_ROOM
                && action.getRewardsActionType() == search::GameAction::RewardsActionType::RELIC
                && action.getIdx1() >= 0 && action.getIdx1() < 3
             && state.projected.info.shop.relics[action.getIdx1()] == RelicId::PRISMATIC_SHARD;
            const auto choice=choiceByPrimitive.find(bit);
            const bool equivalent=choice!=choiceByPrimitive.end()
                && retainedChoices.count(choice->second);
            require(displayedPrismaticShard || equivalent,
                    "native/live candidate enumeration disagreement");
            continue;
        }
        require(observed.insert(bit).second,"duplicate observed primitive mapping");
    }
    require(expected==observed,"native/live candidate enumeration disagreement");
    for(const auto b:bits)lowerLiveOocAction(state,b);
}
std::vector<std::uint32_t> liveOocPrimitiveBits(const LiveOocStateV1 &state) {
    std::vector<std::uint32_t> bits;
    for (const auto &choice : state.ooc.at("liveChoices"))
        bits.push_back(primitive(choice, state.projected.screenState));
    return bits;
}
std::optional<J> forcedRewardGoldLiveAction(const LiveOocStateV1 &state) {
    if (state.projected.screenState != sts::ScreenState::REWARDS) return std::nullopt;
    int goldChoices = 0;
    std::set<std::string> actions;
    const J *first = nullptr;
    for (const auto &choice : state.ooc.at("liveChoices")) {
        if (choice.at("nativeAction").value("kind", std::string()) != "gold") continue;
        // Keep this tied to the captured choice entry because multiple Java
        // gold rows may lower to the same native primitive bits. Execute one
        // captured choice per observation and let the caller re-observe.
        primitive(choice, state.projected.screenState); // validate native identity
        require(integer(choice.at("nativeAction"),"index",0,255)
                    < static_cast<int>(state.ooc.at("details").at("gold").size()),
                "gold native index outside visible rewards");
        const auto &action = choice.at("liveAction");
        require(string(action,"kind") == "choose","gold choice must lower to choose");
        require(actions.insert(action.dump()).second,"duplicate gold live mapping");
        if (!first) first = &choice;
        ++goldChoices;
    }
    if (goldChoices == 0) return std::nullopt;
    require(state.ooc.at("details").at("gold").size() == static_cast<std::size_t>(goldChoices),
            "gold reward/live mapping count mismatch: rewards="
            + std::to_string(state.ooc.at("details").at("gold").size())
            + " choices=" + std::to_string(goldChoices));
    return first->at("liveAction");
}
} // namespace one_combat::advisor
