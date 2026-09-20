#include "one_combat/live_silver_importer.h"
#include "one_combat/live_silver_mapping.h"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

#include "combat/BattleContext.h"
#include "constants/Cards.h"
#include "constants/MonsterMoves.h"
#include "game/GameContext.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/SilverBridge.h"
#include "sim/search/SilverConversion.h"
#include "sim/search/Action.h"

using nlohmann::json;
using namespace sts;
using namespace sts::search;
using silver_bridge::BattleStateWire;
using silver_bridge::CardWire;
using silver_bridge::SilverRootActionSummary;
using silver_bridge::SilverSearchConfig;
using silver_bridge::SilverRerootFallbackReason;
using silver_bridge::convertedStatesEqualForSearch;
using silver_bridge::runSilverDecision;
using silver_bridge::semanticActionFingerprint;

namespace {
struct Fixture { const char *name; int move; const char *room; BattleStateWire wire; json observation; };

const char *cardId(CardId id) {
    switch (id) {
    case CardId::BASH: return "Bash";
    case CardId::DEFEND_RED: return "Defend_R";
    case CardId::STRIKE_RED: return "Strike_R";
    default: return "";
    }
}
int javaMove(MonsterMoveId move) {
    switch (move) {
    case MonsterMoveId::CULTIST_INCANTATION: return 3;
    case MonsterMoveId::CULTIST_DARK_STRIKE: return 1;
    case MonsterMoveId::JAW_WORM_CHOMP: return 1;
    case MonsterMoveId::JAW_WORM_BELLOW: return 2;
    case MonsterMoveId::JAW_WORM_THRASH: return 3;
    case MonsterMoveId::GREMLIN_NOB_BELLOW: return 3;
    case MonsterMoveId::GREMLIN_NOB_RUSH: return 1;
    case MonsterMoveId::GREMLIN_NOB_SKULL_BASH: return 2;
    default: return 0;
    }
}
const char *monsterName(MonsterId id) {
    switch (id) {
    case MonsterId::GREEN_LOUSE: return "FuzzyLouseDefensive";
    case MonsterId::RED_LOUSE: return "FuzzyLouseNormal";
    case MonsterId::CULTIST: return "Cultist";
    case MonsterId::JAW_WORM: return "JawWorm";
    case MonsterId::GREMLIN_NOB: return "GremlinNob";
    default: return "";
    }
}
void normalizeFirstObservationIdentity(BattleStateWire &wire) {
    for (std::size_t i = 0; i < wire.drawPile.unknown.size(); ++i)
        wire.drawPile.unknown[i].uniqueId = static_cast<std::int16_t>(i);
    for (std::size_t i = 0; i < wire.hand.size(); ++i)
        wire.hand[i].uniqueId = static_cast<std::int16_t>(wire.drawPile.unknown.size() + i);
    wire.nextUniqueCardId = static_cast<int>(wire.drawPile.unknown.size() + wire.hand.size());
    wire.observedGeneration = 1;
    wire.limbo.assign(10, CardWire{});
    for (auto &card : wire.limbo) card.uniqueId = -1;
    wire.stasisCards.fill(CardWire{});
}
std::string uuid(const CardWire &c) { return "card-" + std::to_string(c.uniqueId); }
json cardJson(const CardWire &c) {
    return {{"id", cardId(static_cast<CardId>(c.id))}, {"uuid", uuid(c)},
            {"misc", c.specialData}, {"cost", c.cost}, {"costForTurn", c.costForTurn},
            {"upgraded", c.upgraded}, {"freeToPlayOnce", c.freeToPlayOnce}, {"retain", c.retain}};
}
json pileJson(const std::vector<CardWire> &cards) {
    json out = json::array();
    for (const auto &c : cards) out.push_back(cardJson(c));
    return out;
}
json observation(const BattleStateWire &w, const char *name, int move, const char *room,
                 int ordinal = 0, json played = json::array()) {
    json monsters = json::array();
    const auto &m = w.monsters[0];
    monsters.push_back({{"id", name}, {"hp", m.curHp}, {"maxHp", m.maxHp},
                        {"block", m.block}, {"nextMove", move},
                        {"moveHistory", json::array({move})}, {"miscInfo", m.miscInfo},
                        {"powers", json::array()}});
    json potions = json::array();
    for (int i = 0; i < w.potionCapacity; ++i)
        potions.push_back({{"slot", i}, {"id", "Potion Slot"}});
    json combat = {
        {"turn", 1}, {"energy", w.player.energy}, {"block", w.player.block},
        {"cardsPlayedThisTurn", w.player.cardsPlayedThisTurn}, {"cardSelect", false},
        {"resolving", false}, {"runicDome", false}, {"frozenEye", false},
        {"damageTrackingExact", true},
        {"lastAttackUnblockedDamage", w.player.lastAttackUnblockedDamage},
        {"timesDamagedThisCombat", w.player.timesDamagedThisCombat},
        {"playedThisTurn", std::move(played)}, {"playerPowers", json::array()},
        {"hand", pileJson(w.hand)}, {"limbo", json::array()}, {"stasis", json::array()},
        {"draw", pileJson(w.drawPile.unknown)},
        {"discard", pileJson(w.discardPile.unknown)}, {"exhaust", pileJson(w.exhaustPile.unknown)},
        {"relics", json::array({json{{"id", "Burning Blood"}, {"counter", 0}, {"usedUp", false}}})},
        {"potions", std::move(potions)}, {"monsters", std::move(monsters)}};
    return {{"boundary", "combat"}, {"character", "IRONCLAD"},
        {"observationHash", std::string("parity-") + name},
        {"combatEntryHash", std::string("entry-") + name},
        {"silverRoot", {{"schemaVersion", 2}, {"decisionOrdinal", ordinal},
            {"firstDecision", ordinal == 0},
            {"character", "IRONCLAD"}, {"ascension", w.ascension}, {"act", w.act},
            {"floor", w.floorNum}, {"hp", w.player.curHp}, {"maxHp", w.player.maxHp},
            {"gold", w.player.gold}, {"potionCapacity", w.potionCapacity},
            {"burningElite", false}, {"roomClass", room}, {"combat", std::move(combat)}}}};
}

Fixture successorFixture(const Fixture &root, CardId wanted, int occurrence = 0) {
    GameContext game(CharacterClass::IRONCLAD, root.wire.isolatedSearchSeed, 0);
    game.act = 1;
    game.floorNum = 1;
    BattleContext live;
    live.init(game, static_cast<MonsterEncounter>(root.wire.encounter));
    live.monsters.arr[0].moveHistory[0] = static_cast<MMID>(root.wire.monsters[0].moveHistory[0]);
    CombatKnowledgeState knowledge;
    knowledge.initializeFromLiveBattle(live);
    int handIndex = -1;
    for (int i = 0, seen = 0; i < live.cards.cardsInHand; ++i) {
        if (live.cards.hand[i].id != wanted) continue;
        if (seen++ == occurrence) { handIndex = i; break; }
    }
    if (handIndex < 0) throw std::runtime_error("successor card not in native hand");
    const int target = wanted == CardId::STRIKE_RED ? 0 : 0;
    sts::search::Action(sts::search::ActionType::CARD, handIndex, target).execute(live);
    auto wire = makeSilverBattleStateWire(live, knowledge, makeSilverRunContext(game),
                                           root.wire.isolatedSearchSeed);
    if (!wire.valid) throw std::runtime_error("native successor conversion failed");
    const auto id = cardId(wanted);
    const auto playedUuid = uuid(wire.curCardQueueItem.card);
    return {root.name, root.move, root.room, wire,
            observation(wire, root.name, root.move, root.room, 1,
                        json::array({{{"id", id}, {"uuid", playedUuid}, {"upgraded", false}}}))};
}

Fixture successorForSemantic(const Fixture &root,
                             const silver_bridge::SemanticAction &semantic,
                             bool differentEquivalentCopy = false) {
    if (semantic.type != silver_bridge::SemanticActionType::CARD)
        throw std::runtime_error("semantic successor requires a card action");
    const auto wanted = static_cast<CardId>(semantic.card.id);
    GameContext game(CharacterClass::IRONCLAD, root.wire.isolatedSearchSeed, 0);
    game.act = 1;
    game.floorNum = 1;
    BattleContext live;
    live.init(game, static_cast<MonsterEncounter>(root.wire.encounter));
    live.monsters.arr[0].moveHistory[0] = static_cast<MMID>(root.wire.monsters[0].moveHistory[0]);
    CombatKnowledgeState knowledge;
    knowledge.initializeFromLiveBattle(live);
    int handIndex = -1;
    for (int i = 0; i < live.cards.cardsInHand; ++i) {
        const auto &candidate = live.cards.hand[i];
        if (candidate.id != wanted) continue;
        const bool selectedIdentity = candidate.uniqueId == semantic.card.uniqueId;
        if ((!differentEquivalentCopy && selectedIdentity)
            || (differentEquivalentCopy && !selectedIdentity)) {
            handIndex = i;
            break;
        }
    }
    if (handIndex < 0) throw std::runtime_error("requested semantic card copy is absent");
    sts::search::Action(sts::search::ActionType::CARD, handIndex, semantic.target).execute(live);
    auto wire = makeSilverBattleStateWire(live, knowledge, makeSilverRunContext(game),
                                           root.wire.isolatedSearchSeed);
    if (!wire.valid) throw std::runtime_error("semantic successor conversion failed");
    return {root.name, root.move, root.room, wire,
            observation(wire, root.name, root.move, root.room, 1,
                        json::array({{{"id", cardId(wanted)},
                                      {"uuid", uuid(wire.curCardQueueItem.card)},
                                      {"upgraded", false}}}))};
}
Fixture fixture(MonsterEncounter encounter, const char *name, int move,
                const char *room, std::uint64_t seed) {
    GameContext game(CharacterClass::IRONCLAD, seed, 0);
    game.act = 1;
    game.floorNum = 1;
    BattleContext live;
    live.init(game, encounter);
    live.monsters.arr[0].moveHistory[0] = static_cast<MMID>(
        encounter == MonsterEncounter::CULTIST ? MonsterMoveId::CULTIST_INCANTATION :
        encounter == MonsterEncounter::JAW_WORM ? MonsterMoveId::JAW_WORM_CHOMP :
        MonsterMoveId::GREMLIN_NOB_BELLOW);
    CombatKnowledgeState knowledge;
    knowledge.initializeFromLiveBattle(live);
    auto wire = makeSilverBattleStateWire(live, knowledge, makeSilverRunContext(game), seed);
    if (!wire.valid) throw std::runtime_error("native fixture conversion failed");
    return {name, move, room, wire, observation(wire, name, move, room)};
}
Fixture multiFixture() {
    GameContext game(CharacterClass::IRONCLAD, 0x1A11u, 0);
    game.act = 1;
    game.floorNum = 1;
    BattleContext live;
    live.init(game, MonsterEncounter::THREE_CULTIST);
    CombatKnowledgeState knowledge;
    knowledge.initializeFromLiveBattle(live);
    auto wire = makeSilverBattleStateWire(live, knowledge, makeSilverRunContext(game), 0x1A11u);
    if (!wire.valid || wire.monsterCount != 3) throw std::runtime_error("three-cultist native fixture failed");
    // A first live observation allocates persistent UUIDs in the producer's
    // visible-pile order.  Give this native fixture the same assignment.
    normalizeFirstObservationIdentity(wire);
    auto out = observation(wire, monsterName(static_cast<MonsterId>(wire.monsters[0].id)),
                           javaMove(static_cast<MonsterMoveId>(wire.monsters[0].moveHistory[0])),
                           "MONSTER");
    auto &root = out["silverRoot"];
    root["schemaVersion"] = 4;
    root.erase("decisionOrdinal");
    root.erase("firstDecision");
    root["decisionInTurn"] = 0;
    root["playerTurn"] = wire.turn + 1;
    root["combatInstance"] = "three-cultist-entry";
    root["encounter"] = "THREE_CULTIST";
    auto &combat = root["combat"];
    combat["turn"] = wire.turn + 1;
    combat["loopCount"] = wire.loopCount;
    combat["cardsDrawn"] = wire.cardsDrawn;
    combat["energyWasted"] = wire.energyWasted;
    combat["monsterTurnIdx"] = wire.monsterTurnIdx;
    combat["lastTargetedMonster"] = wire.player.lastTargetedMonster;
    combat["monsters"] = json::array();
    for (int i = 0; i < wire.monsterCount; ++i) {
        const auto &monster = wire.monsters[i];
        const auto current = javaMove(static_cast<MonsterMoveId>(monster.moveHistory[0]));
        if (current == 0) throw std::runtime_error("three-cultist current move mapping missing");
        json history = json::array();
        const auto previous = javaMove(static_cast<MonsterMoveId>(monster.moveHistory[1]));
        if (previous != 0) history.push_back(previous);
        history.push_back(current);
        json powers = json::array();
        if (monster.uniquePower0 != 0)
            powers.push_back({{"id", "Curl Up"}, {"amount", monster.uniquePower0},
                              {"justApplied", false}});
        json monsterJson = {
            {"id", monsterName(static_cast<MonsterId>(monster.id))},
            {"idx", monster.idx}, {"hp", monster.curHp}, {"maxHp", monster.maxHp},
            {"block", monster.block}, {"dead", monster.curHp <= 0 || monster.isEscapingB},
            {"nextMove", current}, {"moveHistory", history},
            {"miscInfo", monster.miscInfo}, {"powers", std::move(powers)}};
        combat["monsters"].push_back(std::move(monsterJson));
    }
    return {"ThreeCultist", 3, "MONSTER", wire, std::move(out)};
}
Fixture multiHitFixture() {
    GameContext game(CharacterClass::IRONCLAD, 0xD1A3u, 0);
    game.act = 1;
    game.floorNum = 1;
    BattleContext live;
    live.init(game, MonsterEncounter::CULTIST);
    CombatKnowledgeState knowledge;
    knowledge.initializeFromLiveBattle(live);
    for (const int damage : {2, 3, 4, 5, 6, 4})
        live.player.attacked(live, 0, damage);
    auto wire = makeSilverBattleStateWire(live, knowledge, makeSilverRunContext(game), 0xD1A3u);
    if (!wire.valid || wire.player.timesDamagedThisCombat != 6
        || wire.player.lastAttackUnblockedDamage != 4)
        throw std::runtime_error("native multi-hit damage fixture failed");
    normalizeFirstObservationIdentity(wire);
    return {"CultistMultiHit", 3, "MONSTER", wire,
            observation(wire, "Cultist", 3, "MONSTER")};
}
void verifyRuntimeMoveBoundary() {
    using one_combat::advisor::live_silver::monsterMove;
    const auto expect = [](const char *id, int javaByte, MonsterMoveId native) {
        const auto actual = monsterMove(id, javaByte);
        if (!actual || *actual != native)
            throw std::runtime_error(std::string("runtime move mapping failed: ")
                + id + ":" + std::to_string(javaByte));
    };
    // These bytes are the actual constants used by the installed vanilla
    // classes and by the PR 248 producer, not values generated by this table.
    expect("Cultist", 3, MonsterMoveId::CULTIST_INCANTATION);
    expect("Cultist", 1, MonsterMoveId::CULTIST_DARK_STRIKE);
    expect("JawWorm", 1, MonsterMoveId::JAW_WORM_CHOMP);
    expect("JawWorm", 2, MonsterMoveId::JAW_WORM_BELLOW);
    expect("JawWorm", 3, MonsterMoveId::JAW_WORM_THRASH);
    expect("GremlinNob", 1, MonsterMoveId::GREMLIN_NOB_RUSH);
    expect("GremlinNob", 2, MonsterMoveId::GREMLIN_NOB_SKULL_BASH);
    expect("GremlinNob", 3, MonsterMoveId::GREMLIN_NOB_BELLOW);

    // Literal byte constants from desktop-1.0.jar (verified with javap -p
    // -constants).  This table is intentionally independent of the
    // production mapping implementation; reverse-generating bytes from
    // MonsterMoveId would only test that the two sides agree with themselves.
    expect("AcidSlime_L", 1, MonsterMoveId::ACID_SLIME_L_CORROSIVE_SPIT);
    expect("AcidSlime_L", 2, MonsterMoveId::ACID_SLIME_L_TACKLE);
    expect("AcidSlime_L", 3, MonsterMoveId::ACID_SLIME_L_SPLIT);
    expect("AcidSlime_L", 4, MonsterMoveId::ACID_SLIME_L_LICK);
    expect("AcidSlime_M", 1, MonsterMoveId::ACID_SLIME_M_CORROSIVE_SPIT);
    expect("AcidSlime_M", 2, MonsterMoveId::ACID_SLIME_M_TACKLE);
    expect("AcidSlime_M", 4, MonsterMoveId::ACID_SLIME_M_LICK);
    expect("AcidSlime_S", 1, MonsterMoveId::ACID_SLIME_S_TACKLE);
    expect("AcidSlime_S", 2, MonsterMoveId::ACID_SLIME_S_LICK);
    expect("FungiBeast", 1, MonsterMoveId::FUNGI_BEAST_BITE);
    expect("FungiBeast", 2, MonsterMoveId::FUNGI_BEAST_GROW);
    expect("GremlinFat", 2, MonsterMoveId::FAT_GREMLIN_SMASH);
    expect("GremlinThief", 1, MonsterMoveId::SNEAKY_GREMLIN_PUNCTURE);
    expect("GremlinTsundere", 1, MonsterMoveId::SHIELD_GREMLIN_PROTECT);
    expect("GremlinTsundere", 2, MonsterMoveId::SHIELD_GREMLIN_SHIELD_BASH);
    expect("GremlinWarrior", 1, MonsterMoveId::MAD_GREMLIN_SCRATCH);
    expect("GremlinWizard", 1, MonsterMoveId::GREMLIN_WIZARD_ULTIMATE_BLAST);
    expect("GremlinWizard", 2, MonsterMoveId::GREMLIN_WIZARD_CHARGING);
    expect("Hexaghost", 1, MonsterMoveId::HEXAGHOST_DIVIDER);
    expect("Hexaghost", 2, MonsterMoveId::HEXAGHOST_TACKLE);
    expect("Hexaghost", 3, MonsterMoveId::HEXAGHOST_INFLAME);
    expect("Hexaghost", 4, MonsterMoveId::HEXAGHOST_SEAR);
    expect("Hexaghost", 5, MonsterMoveId::HEXAGHOST_ACTIVATE);
    expect("Hexaghost", 6, MonsterMoveId::HEXAGHOST_INFERNO);
    expect("Lagavulin", 1, MonsterMoveId::LAGAVULIN_SIPHON_SOUL);
    expect("Lagavulin", 3, MonsterMoveId::LAGAVULIN_ATTACK);
    expect("Lagavulin", 4, MonsterMoveId::LAGAVULIN_SLEEP);
    expect("Lagavulin", 5, MonsterMoveId::LAGAVULIN_SLEEP);
    expect("Lagavulin", 6, MonsterMoveId::LAGAVULIN_SLEEP);
    expect("Looter", 1, MonsterMoveId::LOOTER_MUG);
    expect("Looter", 2, MonsterMoveId::LOOTER_SMOKE_BOMB);
    expect("Looter", 3, MonsterMoveId::LOOTER_ESCAPE);
    expect("Looter", 4, MonsterMoveId::LOOTER_LUNGE);
    expect("FuzzyLouseDefensive", 3, MonsterMoveId::GREEN_LOUSE_BITE);
    expect("FuzzyLouseDefensive", 4, MonsterMoveId::GREEN_LOUSE_SPIT_WEB);
    expect("FuzzyLouseNormal", 3, MonsterMoveId::RED_LOUSE_BITE);
    expect("FuzzyLouseNormal", 4, MonsterMoveId::RED_LOUSE_GROW);
    expect("Sentry", 3, MonsterMoveId::SENTRY_BOLT);
    expect("Sentry", 4, MonsterMoveId::SENTRY_BEAM);
    expect("SlaverBlue", 1, MonsterMoveId::BLUE_SLAVER_STAB);
    expect("SlaverBlue", 4, MonsterMoveId::BLUE_SLAVER_RAKE);
    expect("SlaverRed", 1, MonsterMoveId::RED_SLAVER_STAB);
    expect("SlaverRed", 2, MonsterMoveId::RED_SLAVER_ENTANGLE);
    expect("SlaverRed", 3, MonsterMoveId::RED_SLAVER_SCRAPE);
    expect("SlimeBoss", 1, MonsterMoveId::SLIME_BOSS_SLAM);
    expect("SlimeBoss", 2, MonsterMoveId::SLIME_BOSS_PREPARING);
    expect("SlimeBoss", 3, MonsterMoveId::SLIME_BOSS_SPLIT);
    expect("SlimeBoss", 4, MonsterMoveId::SLIME_BOSS_GOOP_SPRAY);
    expect("SpikeSlime_L", 1, MonsterMoveId::SPIKE_SLIME_L_FLAME_TACKLE);
    expect("SpikeSlime_L", 3, MonsterMoveId::SPIKE_SLIME_L_SPLIT);
    expect("SpikeSlime_L", 4, MonsterMoveId::SPIKE_SLIME_L_LICK);
    expect("SpikeSlime_M", 1, MonsterMoveId::SPIKE_SLIME_M_FLAME_TACKLE);
    expect("SpikeSlime_M", 4, MonsterMoveId::SPIKE_SLIME_M_LICK);
    expect("SpikeSlime_S", 1, MonsterMoveId::SPIKE_SLIME_S_TACKLE);
    expect("TheGuardian", 1, MonsterMoveId::THE_GUARDIAN_DEFENSIVE_MODE);
    expect("TheGuardian", 2, MonsterMoveId::THE_GUARDIAN_FIERCE_BASH);
    expect("TheGuardian", 3, MonsterMoveId::THE_GUARDIAN_ROLL_ATTACK);
    expect("TheGuardian", 4, MonsterMoveId::THE_GUARDIAN_TWIN_SLAM);
    expect("TheGuardian", 5, MonsterMoveId::THE_GUARDIAN_WHIRLWIND);
    expect("TheGuardian", 6, MonsterMoveId::THE_GUARDIAN_CHARGING_UP);
    expect("TheGuardian", 7, MonsterMoveId::THE_GUARDIAN_VENT_STEAM);
    if (monsterMove("JawWorm", 4) || monsterMove("Hexaghost", 7)
        || monsterMove("BookOfStabbing", 1))
        throw std::runtime_error("invalid or unqualified monster move was accepted");
}
json genericObservation(const Fixture &fixture, const char *instance) {
    auto out = fixture.observation;
    out["sequence"] = 1;
    auto &root = out["silverRoot"];
    root["schemaVersion"] = 4;
    root.erase("decisionOrdinal");
    root.erase("firstDecision");
    root["decisionInTurn"] = 0;
    root["playerTurn"] = fixture.wire.turn + 1;
    root["combatInstance"] = instance;
    root["encounter"] = std::string(fixture.name).rfind("Cultist", 0) == 0 ? "CULTIST"
        : (std::string(fixture.name) == "JawWorm" ? "JAW_WORM" : "GREMLIN_NOB");
    root["combat"]["turn"] = fixture.wire.turn + 1;
    root["combat"]["loopCount"] = fixture.wire.loopCount;
    root["combat"]["cardsDrawn"] = fixture.wire.cardsDrawn;
    root["combat"]["energyWasted"] = fixture.wire.energyWasted;
    root["combat"]["monsterTurnIdx"] = fixture.wire.monsterTurnIdx;
    root["combat"]["lastTargetedMonster"] = fixture.wire.player.lastTargetedMonster;
    return out;
}
bool sameSummaries(const std::vector<SilverRootActionSummary> &a,
                   const std::vector<SilverRootActionSummary> &b) {
    if (a.size() != b.size()) return false;
    for (std::size_t i = 0; i < a.size(); ++i) {
        if (semanticActionFingerprint(a[i].action) != semanticActionFingerprint(b[i].action)
            || a[i].edgeVisits != b[i].edgeVisits
            || a[i].selectionQValid != b[i].selectionQValid
            || (a[i].selectionQValid && std::abs(a[i].selectionQ - b[i].selectionQ) > 1e-12))
            return false;
    }
    return true;
}
int cardActionCount(const std::vector<silver_bridge::SemanticAction> &actions, CardId id) {
    return static_cast<int>(std::count_if(actions.begin(), actions.end(), [id](const auto &action) {
        return action.type == silver_bridge::SemanticActionType::CARD
            && action.card.id == static_cast<std::int16_t>(id);
    }));
}
}
int main() {
    try {
        verifyRuntimeMoveBoundary();
        const std::vector<Fixture> fixtures = {
            fixture(MonsterEncounter::CULTIST, "Cultist", 3, "MONSTER", 0xC011u),
            fixture(MonsterEncounter::JAW_WORM, "JawWorm", 1, "MONSTER", 0xA01u),
            fixture(MonsterEncounter::GREMLIN_NOB, "Gremlin Nob", 3, "ELITE", 0xB003u)};
        const auto multi = multiFixture();
        auto multiImported = one_combat::advisor::importSilverRoot(multi.observation);
        if (!multiImported.ok) throw std::runtime_error("multi-enemy import failed: " + multiImported.reason);
        auto multiCanonical = multi.wire;
        multiCanonical.isolatedSearchSeed = multiImported.wire.isolatedSearchSeed;
        if (!convertedStatesEqualForSearch(multiCanonical, multiImported.wire))
            throw std::runtime_error("multi-enemy native parity failed: count="
                + std::to_string(multiCanonical.monsterCount) + "/"
                + std::to_string(multiImported.wire.monsterCount)
                + " alive=" + std::to_string(multiCanonical.monstersAlive) + "/"
                + std::to_string(multiImported.wire.monstersAlive)
                + " encounter=" + std::to_string(multiCanonical.encounter) + "/"
                + std::to_string(multiImported.wire.encounter)
                + " m0move=" + std::to_string(multiCanonical.monsters[0].moveHistory[0]) + "/"
                + std::to_string(multiImported.wire.monsters[0].moveHistory[0])
                + " m1move=" + std::to_string(multiCanonical.monsters[1].moveHistory[0]) + "/"
                + std::to_string(multiImported.wire.monsters[1].moveHistory[0]));
        const auto multiHit = multiHitFixture();
        auto multiHitImported = one_combat::advisor::importSilverRoot(
            genericObservation(multiHit, "multi-hit-damage-entry"));
        if (!multiHitImported.ok)
            throw std::runtime_error("multi-hit damage import failed: " + multiHitImported.reason);
        auto multiHitCanonical = multiHit.wire;
        multiHitCanonical.isolatedSearchSeed = multiHitImported.wire.isolatedSearchSeed;
        if (multiHitImported.wire.player.timesDamagedThisCombat != 6
            || multiHitImported.wire.player.lastAttackUnblockedDamage != 4
            || !convertedStatesEqualForSearch(multiHitCanonical, multiHitImported.wire))
            throw std::runtime_error("multi-hit damage parity failed");
        SilverSearchConfig config;
        config.simulationsPerDecision = 1000;
        config.collectRootActionSummaries = true;
        config.collectDecisionDiagnostics = true;
        config.adaptiveEnabled = false;
        config.exactVisitLockEnabled = false;
        config.rhoRacingEnabled = false;
        bool duplicateStrikeSummariesCovered = false;
        bool duplicateDefendSummariesCovered = false;
        for (const auto &f : fixtures) {
            auto imported = one_combat::advisor::importSilverRoot(f.observation);
            if (!imported.ok) throw std::runtime_error("import failed: " + imported.reason);
            auto canonical = f.wire;
            canonical.isolatedSearchSeed = imported.wire.isolatedSearchSeed;
            if (!convertedStatesEqualForSearch(canonical, imported.wire))
                throw std::runtime_error(std::string("search parity failed: ") + f.name);
            if (imported.wire.cardsDrawn != 5 || imported.wire.strikeCount != 5
                || imported.wire.hand != canonical.hand
                || imported.wire.handNormalityCount != canonical.handNormalityCount
                || imported.wire.handPainCount != canonical.handPainCount
                || imported.wire.handBloodCardCount != canonical.handBloodCardCount
                || imported.wire.drawPileBloodCardCount != canonical.drawPileBloodCardCount
                || imported.wire.discardPileBloodCardCount != canonical.discardPileBloodCardCount)
                throw std::runtime_error(std::string("first-root fields failed: ") + f.name);
            auto a = runSilverDecision(canonical, config);
            auto b = runSilverDecision(imported.wire, config);
            if (!a.accepted || !b.accepted
                || semanticActionFingerprint(a.action) != semanticActionFingerprint(b.action)
                || !sameSummaries(a.rootActionSummaries, b.rootActionSummaries))
                throw std::runtime_error(std::string("search result parity failed: ") + f.name);
            for (const auto id : {CardId::STRIKE_RED, CardId::DEFEND_RED}) {
                const int physical = static_cast<int>(std::count_if(
                    imported.wire.hand.begin(), imported.wire.hand.end(), [id](const auto &card) {
                        return card.id == static_cast<std::int16_t>(id);
                    }));
                const int summaries = static_cast<int>(std::count_if(
                    b.rootActionSummaries.begin(), b.rootActionSummaries.end(), [id](const auto &summary) {
                        return summary.action.type == silver_bridge::SemanticActionType::CARD
                            && summary.action.card.id == static_cast<std::int16_t>(id);
                    }));
                if (physical > 1) {
                    if (summaries != 1)
                        throw std::runtime_error(std::string("duplicate root summaries: ") + cardId(id));
                    if (id == CardId::STRIKE_RED) duplicateStrikeSummariesCovered = true;
                    else duplicateDefendSummariesCovered = true;
                }
            }
        }
        if (!duplicateStrikeSummariesCovered || !duplicateDefendSummariesCovered)
            throw std::runtime_error("starter fixtures did not cover duplicate Strike and Defend summaries");

        // The v4 corpus must compare imported mechanics against a matching
        // native wire, not only check that JSON fields were accepted.
        auto mechanics = genericObservation(fixtures[0], "native-mechanics-entry");
        mechanics["silverRoot"]["combat"]["playerPowers"] = json::array({
            json{{"id", "Metallicize"}, {"amount", 2}}});
        mechanics["silverRoot"]["combat"]["potions"][0] =
            json{{"slot", 0}, {"id", "Strength Potion"}};
        mechanics["silverRoot"]["combat"]["relics"].push_back(
            json{{"id", "Happy Flower"}, {"counter", 2}, {"usedUp", false}});
        auto mechanicsImported = one_combat::advisor::importSilverRoot(mechanics);
        if (!mechanicsImported.ok)
            throw std::runtime_error("native power/relic/potion import failed: " + mechanicsImported.reason);
        auto mechanicsNative = fixtures[0].wire;
        normalizeFirstObservationIdentity(mechanicsNative);
        mechanicsNative.player.statusBits1 |=
            1U << (static_cast<int>(PlayerStatus::METALLICIZE) - 64);
        mechanicsNative.player.statusMap.emplace_back(
            static_cast<std::int16_t>(PlayerStatus::METALLICIZE), 2);
        mechanicsNative.potions[0] = static_cast<std::int16_t>(Potion::STRENGTH_POTION);
        mechanicsNative.potionCount = 1;
        mechanicsNative.player.relicBits0 |=
            1ULL << static_cast<int>(RelicId::HAPPY_FLOWER);
        mechanicsNative.player.relicCounters[0] = 2;
        mechanicsNative.isolatedSearchSeed = mechanicsImported.wire.isolatedSearchSeed;
        if (!convertedStatesEqualForSearch(mechanicsNative, mechanicsImported.wire))
            throw std::runtime_error("native power/relic/potion parity failed");

        const auto verifyPlayerPowerParity = [&](const char *name, json power,
                                                 const auto &materialize) {
            auto observation = genericObservation(fixtures[0], name);
            observation["silverRoot"]["combat"]["playerPowers"] = json::array({std::move(power)});
            auto imported = one_combat::advisor::importSilverRoot(observation);
            if (!imported.ok)
                throw std::runtime_error(std::string("player power import failed: ")
                    + name + ":" + imported.reason);
            auto expected = fixtures[0].wire;
            normalizeFirstObservationIdentity(expected);
            materialize(expected.player);
            expected.isolatedSearchSeed = imported.wire.isolatedSearchSeed;
            if (!convertedStatesEqualForSearch(expected, imported.wire))
                throw std::runtime_error(std::string("player power parity failed: ") + name);
        };
        verifyPlayerPowerParity("barricade-parity", json{{"id", "Barricade"}, {"amount", -1}},
            [](auto &player) { player.statusBits0 |= 1ULL << static_cast<int>(PlayerStatus::BARRICADE); });
        verifyPlayerPowerParity("corruption-parity", json{{"id", "Corruption"}, {"amount", -1}},
            [](auto &player) { player.statusBits0 |= 1ULL << static_cast<int>(PlayerStatus::CORRUPTION); });
        verifyPlayerPowerParity("confused-parity", json{{"id", "Confused"}, {"amount", -1}},
            [](auto &player) { player.statusBits0 |= 1ULL << static_cast<int>(PlayerStatus::CONFUSED); });
        verifyPlayerPowerParity("hex-parity", json{{"id", "Hex"}, {"amount", 1}},
            [](auto &player) { player.statusBits0 |= 1ULL << static_cast<int>(PlayerStatus::HEX); });
        verifyPlayerPowerParity("pen-nib-parity", json{{"id", "Pen Nib"}, {"amount", 1}},
            [](auto &player) { player.statusBits0 |= 1ULL << static_cast<int>(PlayerStatus::PEN_NIB); });
        auto drawReduction = genericObservation(fixtures[0], "draw-reduction-parity");
        drawReduction["silverRoot"]["combat"]["cardDrawPerTurn"] = 4;
        drawReduction["silverRoot"]["combat"]["playerPowers"] = json::array({
            json{{"id", "DrawReductionPower"}, {"amount", 1}, {"justApplied", true}}});
        auto drawReductionImported = one_combat::advisor::importSilverRoot(drawReduction);
        if (!drawReductionImported.ok)
            throw std::runtime_error("draw reduction import failed: " + drawReductionImported.reason);
        auto drawReductionExpected = fixtures[0].wire;
        normalizeFirstObservationIdentity(drawReductionExpected);
        drawReductionExpected.player.cardDrawPerTurn = 4;
        drawReductionExpected.player.statusBits0 |= 1ULL << static_cast<int>(PlayerStatus::DRAW_REDUCTION);
        drawReductionExpected.player.justAppliedBits |= 1U << static_cast<int>(PlayerStatus::DRAW_REDUCTION);
        drawReductionExpected.isolatedSearchSeed = drawReductionImported.wire.isolatedSearchSeed;
        if (!convertedStatesEqualForSearch(drawReductionExpected, drawReductionImported.wire))
            throw std::runtime_error("draw reduction parity failed");
        verifyPlayerPowerParity("bomb-parity", json{{"id", "TheBomb0"}, {"amount", 3}, {"bombDamage", 40}},
            [](auto &player) { player.bombs[2] = 40; });
        auto penNibRelic = genericObservation(fixtures[0], "pen-nib-relic-parity");
        penNibRelic["silverRoot"]["combat"]["relics"].push_back(
            json{{"id", "Pen Nib"}, {"counter", 9}, {"usedUp", false}});
        auto penNibRelicImported = one_combat::advisor::importSilverRoot(penNibRelic);
        if (!penNibRelicImported.ok)
            throw std::runtime_error("Pen Nib relic import failed: " + penNibRelicImported.reason);
        auto penNibRelicExpected = fixtures[0].wire;
        normalizeFirstObservationIdentity(penNibRelicExpected);
        penNibRelicExpected.player.relicBits0 |= 1ULL << static_cast<int>(RelicId::PEN_NIB);
        penNibRelicExpected.player.relicCounters[5] = -1;
        penNibRelicExpected.player.statusBits0 |= 1ULL << static_cast<int>(PlayerStatus::PEN_NIB);
        penNibRelicExpected.isolatedSearchSeed = penNibRelicImported.wire.isolatedSearchSeed;
        if (!convertedStatesEqualForSearch(penNibRelicExpected, penNibRelicImported.wire))
            throw std::runtime_error("Pen Nib relic parity failed");

        auto nativePower = genericObservation(fixtures[0], "native-power-entry");
        nativePower["silverRoot"]["combat"]["monsters"][0]["powers"] = json::array({
            json{{"id", "Vulnerable"}, {"amount", 2}, {"justApplied", false}}});
        auto nativePowerImported = one_combat::advisor::importSilverRoot(nativePower);
        if (!nativePowerImported.ok)
            throw std::runtime_error("native monster power import failed: " + nativePowerImported.reason);
        auto nativePowerExpected = fixtures[0].wire;
        normalizeFirstObservationIdentity(nativePowerExpected);
        nativePowerExpected.monsters[0].vulnerable = 2;
        nativePowerExpected.monsters[0].statusBits |=
            1ULL << static_cast<int>(MonsterStatus::VULNERABLE);
        nativePowerExpected.isolatedSearchSeed = nativePowerImported.wire.isolatedSearchSeed;
        if (!convertedStatesEqualForSearch(nativePowerExpected, nativePowerImported.wire))
            throw std::runtime_error("native monster power parity failed");

        auto nativeSelection = genericObservation(fixtures[0], "native-selection-entry");
        nativeSelection["silverRoot"]["combat"]["cardSelect"] = json{
            {"task", "EXHAUST_ONE"}, {"cards", json::array({"Strike_R"})},
            {"pickCount", 1}, {"canPickZero", false}, {"canPickAnyNumber", false},
            {"data0", 0}, {"setCostToZero", true}, {"selectedBits", 0}};
        auto nativeSelectionImported = one_combat::advisor::importSilverRoot(nativeSelection);
        if (!nativeSelectionImported.ok)
            throw std::runtime_error("native selection import failed: " + nativeSelectionImported.reason);
        auto nativeSelectionExpected = fixtures[0].wire;
        normalizeFirstObservationIdentity(nativeSelectionExpected);
        nativeSelectionExpected.inputState = static_cast<int>(InputState::CARD_SELECT);
        nativeSelectionExpected.cardSelect.task = static_cast<std::int16_t>(CardSelectTask::EXHAUST_ONE);
        nativeSelectionExpected.cardSelect.cards[0] = static_cast<std::int16_t>(CardId::STRIKE_RED);
        nativeSelectionExpected.cardSelect.pickCount = 1;
        nativeSelectionExpected.isolatedSearchSeed = nativeSelectionImported.wire.isolatedSearchSeed;
        if (!convertedStatesEqualForSearch(nativeSelectionExpected, nativeSelectionImported.wire))
            throw std::runtime_error("native selection parity failed");

        for (const auto &root : fixtures) {
            for (const auto card : {CardId::STRIKE_RED, CardId::DEFEND_RED}) {
                const auto successor = successorFixture(root, card);
                auto imported = one_combat::advisor::importSilverRoot(successor.observation);
                if (!imported.ok)
                    throw std::runtime_error(std::string("successor import failed: ")
                                             + root.name + ":" + cardId(card) + ":" + imported.reason);
                auto canonical = successor.wire;
                canonical.isolatedSearchSeed = imported.wire.isolatedSearchSeed;
                if (!convertedStatesEqualForSearch(canonical, imported.wire)) {
                    throw std::runtime_error(std::string("successor parity failed: ") + root.name
                        + ":" + cardId(card)
                        + " energy=" + std::to_string(canonical.player.energy) + "/" + std::to_string(imported.wire.player.energy)
                        + " block=" + std::to_string(canonical.player.block) + "/" + std::to_string(imported.wire.player.block)
                        + " hp=" + std::to_string(canonical.monsters[0].curHp) + "/" + std::to_string(imported.wire.monsters[0].curHp)
                        + " loop=" + std::to_string(canonical.loopCount) + "/" + std::to_string(imported.wire.loopCount)
                        + " queue=" + std::to_string(canonical.curCardQueueItem.card.id) + "/" + std::to_string(imported.wire.curCardQueueItem.card.id)
                        + " cards=" + std::to_string(canonical.player.cardsPlayedThisTurn) + "/" + std::to_string(imported.wire.player.cardsPlayedThisTurn)
                        + " attacks=" + std::to_string(canonical.player.attacksPlayedThisTurn) + "/" + std::to_string(imported.wire.player.attacksPlayedThisTurn)
                        + " skills=" + std::to_string(canonical.player.skillsPlayedThisTurn) + "/" + std::to_string(imported.wire.player.skillsPlayedThisTurn)
                        + " target=" + std::to_string(canonical.player.lastTargetedMonster) + "/" + std::to_string(imported.wire.player.lastTargetedMonster)
                        + " damage=" + std::to_string(canonical.player.lastAttackUnblockedDamage) + "/" + std::to_string(imported.wire.player.lastAttackUnblockedDamage)
                        + " misc=" + std::to_string(canonical.miscBits) + "/" + std::to_string(imported.wire.miscBits)
                        + " qtarget=" + std::to_string(canonical.curCardQueueItem.target) + "/" + std::to_string(imported.wire.curCardQueueItem.target));
                }
                if (imported.wire.curCardQueueItem.card.uniqueId
                    != successor.wire.curCardQueueItem.card.uniqueId)
                    throw std::runtime_error(std::string("card identity changed: ") + cardId(card));
            }
        }
        auto dedupWire = one_combat::advisor::importSilverRoot(fixtures[0].observation).wire;
        std::vector<CardWire> allCards = dedupWire.hand;
        allCards.insert(allCards.end(), dedupWire.drawPile.unknown.begin(), dedupWire.drawPile.unknown.end());
        dedupWire.hand.clear();
        const auto appendCards = [&](CardId id, int count) {
            for (const auto &card : allCards) {
                if (card.id != static_cast<std::int16_t>(id) || count == 0) continue;
                dedupWire.hand.push_back(card);
                --count;
            }
            if (count != 0) throw std::runtime_error("dedup fixture card count unavailable");
        };
        appendCards(CardId::STRIKE_RED, 2);
        appendCards(CardId::DEFEND_RED, 2);
        appendCards(CardId::BASH, 1);
        auto dedupActions = silver_bridge::enumerateSilverLegalActions(dedupWire);
        if (cardActionCount(dedupActions, CardId::STRIKE_RED) != 1
            || cardActionCount(dedupActions, CardId::DEFEND_RED) != 1
            || cardActionCount(dedupActions, CardId::BASH) != 1)
            throw std::runtime_error("live root did not collapse equivalent starter card actions");
        dedupWire.hand[1].retain = true;
        auto distinctActions = silver_bridge::enumerateSilverLegalActions(dedupWire);
        if (cardActionCount(distinctActions, CardId::STRIKE_RED) != 2)
            throw std::runtime_error("relevant card-state difference was incorrectly deduplicated");
        auto unsupported = successorFixture(fixtures[0], CardId::DEFEND_RED).observation;
        unsupported["silverRoot"]["combat"]["playedThisTurn"][0]["id"] = "Bash";
        if (one_combat::advisor::importSilverRoot(unsupported).reason
            != "silver_unsupported_continuation")
            throw std::runtime_error("Bash continuation was not rejected");
        unsupported = successorFixture(fixtures[0], CardId::DEFEND_RED).observation;
        unsupported["silverRoot"]["combat"]["playerPowers"] = json::array({json{{"id", "Metallicize"}}});
        if (one_combat::advisor::importSilverRoot(unsupported).reason
            != "silver_unmapped_player_power")
            throw std::runtime_error("player power was not rejected");
        unsupported = successorFixture(fixtures[0], CardId::DEFEND_RED).observation;
        unsupported["silverRoot"]["combat"]["monsters"][0]["powers"] = json::array({json{{"id", "Ritual"}}});
        if (one_combat::advisor::importSilverRoot(unsupported).reason
            != "silver_unmapped_monster_power")
            throw std::runtime_error("monster power was not rejected");
        auto nonstarter = fixtures[0].observation;
        nonstarter["silverRoot"]["combat"]["draw"][0]["upgraded"] = true;
        if (one_combat::advisor::importSilverRoot(nonstarter).reason != "silver_nonstarter_deck")
            throw std::runtime_error("upgraded starter card was not rejected");
        const auto seed0 = one_combat::advisor::importSilverRoot(fixtures[0].observation).wire.isolatedSearchSeed;
        const auto seed1 = one_combat::advisor::importSilverRoot(
            successorFixture(fixtures[0], CardId::DEFEND_RED).observation).wire.isolatedSearchSeed;
        const auto seedOtherCombat = one_combat::advisor::importSilverRoot(fixtures[1].observation).wire.isolatedSearchSeed;
        if (seed0 != seed1 || seed0 == seedOtherCombat)
            throw std::runtime_error("Silver seed is not stable per combat");

        const Fixture *rerootRoot = nullptr;
        one_combat::advisor::SilverRootImportResult rerootImported;
        silver_bridge::SilverDecisionResult rerootFirst;
        std::shared_ptr<silver_bridge::SilverSearchSession> rerootSession;
        for (const auto &candidate : fixtures) {
            auto imported = one_combat::advisor::importSilverRoot(candidate.observation);
            auto session = silver_bridge::makeSilverSearchSession();
            auto decision = runSilverDecision(*session, imported.wire, config);
            if (decision.accepted && decision.action.type == silver_bridge::SemanticActionType::CARD
                && (decision.action.card.id == static_cast<std::int16_t>(CardId::STRIKE_RED)
                    || decision.action.card.id == static_cast<std::int16_t>(CardId::DEFEND_RED))) {
                rerootRoot = &candidate;
                rerootImported = std::move(imported);
                rerootFirst = std::move(decision);
                rerootSession = std::move(session);
                break;
            }
        }
        if (rerootRoot == nullptr) throw std::runtime_error("no deterministic supported 1k root action");

        const auto exactSuccessor = successorForSemantic(*rerootRoot, rerootFirst.action);
        const auto exactImported = one_combat::advisor::importSilverRoot(exactSuccessor.observation);
        const auto exactDecision = runSilverDecision(*rerootSession, exactImported.wire, config);
        if (!exactDecision.accepted || !exactDecision.diagnostic.exactReroot
            || exactDecision.diagnostic.fallback || exactDecision.diagnostic.inheritedVisits <= 0)
            throw std::runtime_error("exact representative did not exact-reroot with inherited visits");

        auto disagreementSession = silver_bridge::makeSilverSearchSession();
        const auto disagreementFirst = runSilverDecision(*disagreementSession, rerootImported.wire, config);
        auto otherAction = disagreementFirst.action;
        const auto otherCard = disagreementFirst.action.card.id
                == static_cast<std::int16_t>(CardId::STRIKE_RED)
            ? CardId::DEFEND_RED : CardId::STRIKE_RED;
        bool foundOther = false;
        for (const auto &action : silver_bridge::enumerateSilverLegalActions(rerootImported.wire)) {
            if (action.type == silver_bridge::SemanticActionType::CARD
                && action.card.id == static_cast<std::int16_t>(otherCard)) {
                otherAction = action;
                foundOther = true;
                break;
            }
        }
        if (!foundOther) throw std::runtime_error("different supported action is absent");
        const auto disagreementSuccessor = successorForSemantic(*rerootRoot, otherAction);
        const auto disagreementImported = one_combat::advisor::importSilverRoot(disagreementSuccessor.observation);
        const auto disagreementDecision = runSilverDecision(
            *disagreementSession, disagreementImported.wire, config);
        if (!disagreementDecision.accepted || !disagreementDecision.diagnostic.exactReroot
            || disagreementDecision.diagnostic.equivalentCopyReroot
            || disagreementDecision.diagnostic.fallback
            || disagreementDecision.diagnostic.fallbackReason != SilverRerootFallbackReason::NONE
            || disagreementDecision.diagnostic.inheritedVisits <= 0
            || disagreementDecision.rootActionSummaries.empty())
            throw std::runtime_error("different listed action did not reuse its retained branch");

        auto otherEquivalentSession = silver_bridge::makeSilverSearchSession();
        const auto otherEquivalentFirst = runSilverDecision(
            *otherEquivalentSession, rerootImported.wire, config);
        const auto otherEquivalentSuccessor = successorForSemantic(*rerootRoot, otherAction, true);
        const auto otherEquivalentImported = one_combat::advisor::importSilverRoot(
            otherEquivalentSuccessor.observation);
        const auto otherEquivalentDecision = runSilverDecision(
            *otherEquivalentSession, otherEquivalentImported.wire, config);
        if (!otherEquivalentFirst.accepted || !otherEquivalentDecision.accepted
            || otherEquivalentDecision.diagnostic.exactReroot
            || !otherEquivalentDecision.diagnostic.equivalentCopyReroot
            || otherEquivalentDecision.diagnostic.fallback
            || otherEquivalentDecision.diagnostic.fallbackReason != SilverRerootFallbackReason::NONE
            || otherEquivalentDecision.diagnostic.inheritedVisits <= 0)
            throw std::runtime_error(
                "different listed action's equivalent copy did not reuse its retained branch");

        auto equivalentSession = silver_bridge::makeSilverSearchSession();
        const auto equivalentFirst = runSilverDecision(*equivalentSession, rerootImported.wire, config);
        const auto equivalentSuccessor = successorForSemantic(*rerootRoot, equivalentFirst.action, true);
        const auto equivalentImported = one_combat::advisor::importSilverRoot(equivalentSuccessor.observation);
        if (convertedStatesEqualForSearch(exactImported.wire, equivalentImported.wire))
            throw std::runtime_error("equivalent-copy reroot test accidentally relaxed global equality");
        const auto equivalentDecision = runSilverDecision(*equivalentSession, equivalentImported.wire, config);
        if (!equivalentDecision.accepted || equivalentDecision.diagnostic.exactReroot
            || !equivalentDecision.diagnostic.equivalentCopyReroot
            || equivalentDecision.diagnostic.fallback
            || equivalentDecision.diagnostic.fallbackReason != SilverRerootFallbackReason::NONE
            || equivalentDecision.diagnostic.inheritedVisits <= 0
            || equivalentDecision.rootActionSummaries.empty())
            throw std::runtime_error("equivalent physical copy did not reuse the retained root: exact="
                + std::to_string(equivalentDecision.diagnostic.exactReroot)
                + " equivalent=" + std::to_string(equivalentDecision.diagnostic.equivalentCopyReroot)
                + " fallback=" + std::to_string(equivalentDecision.diagnostic.fallback)
                + " reason=" + silver_bridge::silverRerootFallbackReasonName(
                    equivalentDecision.diagnostic.fallbackReason)
                + " inherited=" + std::to_string(equivalentDecision.diagnostic.inheritedVisits)
                + " miss=" + equivalentDecision.rerootMissDiagnostic);

        auto changedStateSession = silver_bridge::makeSilverSearchSession();
        const auto changedStateFirst = runSilverDecision(*changedStateSession, rerootImported.wire, config);
        auto changedStateWire = equivalentImported.wire;
        if (changedStateWire.hand.empty()) throw std::runtime_error("changed-state fixture has no hand");
        changedStateWire.hand.front().retain = !changedStateWire.hand.front().retain;
        const auto changedStateDecision = runSilverDecision(*changedStateSession, changedStateWire, config);
        if (!changedStateFirst.accepted || !changedStateDecision.accepted
            || changedStateDecision.diagnostic.exactReroot
            || changedStateDecision.diagnostic.equivalentCopyReroot
            || !changedStateDecision.diagnostic.fallback
            || changedStateDecision.diagnostic.fallbackReason
                != SilverRerootFallbackReason::CANDIDATE_MISSING
            || changedStateDecision.diagnostic.inheritedVisits != 0)
            throw std::runtime_error("non-equivalent card state incorrectly reused the retained root");
        auto hand = fixtures[0].observation;
        std::swap(hand["silverRoot"]["combat"]["hand"][0], hand["silverRoot"]["combat"]["hand"][1]);
        auto original = one_combat::advisor::importSilverRoot(fixtures[0].observation);
        auto handSwap = one_combat::advisor::importSilverRoot(hand);
        if (!original.ok || !handSwap.ok || original.wire.hand == handSwap.wire.hand)
            throw std::runtime_error("visible hand permutation was discarded");
        auto draw = fixtures[0].observation;
        std::swap(draw["silverRoot"]["combat"]["draw"][0], draw["silverRoot"]["combat"]["draw"][1]);
        auto drawSwap = one_combat::advisor::importSilverRoot(draw);
        if (!drawSwap.ok || !convertedStatesEqualForSearch(original.wire, drawSwap.wire))
            throw std::runtime_error("hidden draw permutation changed search state");
        auto reject = fixtures[0].observation;
        reject["silverRoot"]["combat"]["runicDome"] = true;
        if (one_combat::advisor::importSilverRoot(reject).reason != "silver_runic_dome") return 2;
        reject = fixtures[0].observation;
        reject["silverRoot"]["combat"]["frozenEye"] = true;
        if (one_combat::advisor::importSilverRoot(reject).reason != "silver_frozen_eye") return 3;
        reject = fixtures[0].observation;
        reject["silverRoot"]["burningElite"] = true;
        if (one_combat::advisor::importSilverRoot(reject).reason != "silver_burning_elite") return 4;
        reject = fixtures[0].observation;
        reject["silverRoot"]["combat"]["rng"] = 1;
        if (one_combat::advisor::importSilverRoot(reject).reason != "silver_rng_field") return 5;
        reject = fixtures[1].observation;
        reject["silverRoot"]["combat"]["monsters"][0]["nextMove"] = 4;
        if (one_combat::advisor::importSilverRoot(reject).ok) return 6;
        reject = fixtures[2].observation;
        reject["silverRoot"]["combat"]["monsters"][0]["nextMove"] = 4;
        if (one_combat::advisor::importSilverRoot(reject).ok) return 7;
        reject = fixtures[0].observation;
        reject["silverRoot"]["combat"]["turn"] = 2;
        if (one_combat::advisor::importSilverRoot(reject).ok) return 8;

        // Protocol v4 is deliberately exercised with a non-starter card,
        // upgraded state, a public power, a real potion, and the persistent
        // UUID registry.  The draw array is an information-state multiset;
        // swapping it must not change the imported search state.
        auto general = fixtures[0].observation;
        auto &generalRoot = general["silverRoot"];
        generalRoot["schemaVersion"] = 4;
        generalRoot.erase("decisionOrdinal");
        generalRoot.erase("firstDecision");
        generalRoot["decisionInTurn"] = 0;
        generalRoot["combatInstance"] = "generic-entry";
        generalRoot["playerTurn"] = 4;
        generalRoot["encounter"] = "CULTIST";
        generalRoot["combat"]["relics"][0]["usedUp"] = false;
        generalRoot["combat"]["playerPowers"] = json::array({
            json{{"id", "Metallicize"}, {"amount", 2}}});
        generalRoot["combat"]["potions"][0] = json{{"slot", 0}, {"id", "Strength Potion"}};
        generalRoot["combat"]["relics"].push_back(
            json{{"id", "Happy Flower"}, {"counter", 2}, {"usedUp", false}});
        generalRoot["combat"]["draw"].push_back(json{
            {"id", "Shrug It Off"}, {"uuid", "generated-shrug"}, {"upgraded", true},
            {"misc", 0}, {"cost", 1}, {"costForTurn", 1},
            {"freeToPlayOnce", false}, {"retain", false}});
        one_combat::advisor::SilverImportContext generalContext;
        generalContext.session = "generic-session";
        general["session"] = "generic-session";
        auto generalImported = one_combat::advisor::importSilverRoot(general, generalContext);
        if (!generalImported.ok) throw std::runtime_error("schema-v4 import failed: " + generalImported.reason);
        if (generalImported.wire.inputState != static_cast<int>(InputState::PLAYER_NORMAL)
            || generalImported.wire.potionCount != 1
            || generalImported.wire.player.statusMap.empty()
            || generalImported.wire.nextUniqueCardId <= 10)
            throw std::runtime_error("schema-v4 state fields were not materialized: potion="
                + std::to_string(generalImported.wire.potionCount) + " powers="
                + std::to_string(generalImported.wire.player.statusMap.size()) + " next="
                + std::to_string(generalImported.wire.nextUniqueCardId));
        auto powerBits = general;
        powerBits["silverRoot"]["combat"]["monsters"][0]["powers"] = json::array({
            json{{"id", "Vulnerable"}, {"amount", 2}, {"justApplied", false}}});
        const auto powerImported = one_combat::advisor::importSilverRoot(powerBits);
        if (!powerImported.ok || powerImported.wire.monsters[0].vulnerable != 2
            || !(powerImported.wire.monsters[0].statusBits
                & (1ULL << static_cast<int>(MonsterStatus::VULNERABLE))))
            throw std::runtime_error("monster Vulnerable amount/activation parity failed");
        auto missingMisc = general;
        missingMisc["silverRoot"]["combat"]["monsters"][0].erase("miscInfo");
        if (one_combat::advisor::importSilverRoot(missingMisc).reason
            != "silver_unmapped_monster_state")
            throw std::runtime_error("missing monster miscInfo was accepted");
        auto missingRelicState = general;
        missingRelicState["silverRoot"]["combat"]["relics"][0].erase("usedUp");
        if (one_combat::advisor::importSilverRoot(missingRelicState).reason
            != "silver_unmapped_relic_state")
            throw std::runtime_error("missing relic usedUp state was accepted");
        auto missingDamageTracking = general;
        missingDamageTracking["silverRoot"]["combat"].erase("damageTrackingExact");
        if (one_combat::advisor::importSilverRoot(missingDamageTracking).reason
            != "silver_damage_tracking")
            throw std::runtime_error("missing exact damage tracking was accepted");
        const auto generatedId = generalContext.cardIds.at("generated-shrug");
        auto generalAgain = general;
        std::swap(generalAgain["silverRoot"]["combat"]["draw"][0],
                  generalAgain["silverRoot"]["combat"]["draw"][1]);
        auto generalAgainImported = one_combat::advisor::importSilverRoot(generalAgain, generalContext);
        if (!generalAgainImported.ok || generalAgainImported.wire.drawPile.unknown.empty()
            || generalContext.cardIds.at("generated-shrug") != generatedId
            || !convertedStatesEqualForSearch(generalImported.wire, generalAgainImported.wire))
            throw std::runtime_error("schema-v4 UUID or hidden draw contract failed");
        general["silverRoot"]["combat"]["frozenEye"] = true;
        general["silverRoot"]["combat"]["draw"] = json::array({
            json{{"id", "Strike_R"}, {"uuid", "eye-a"}, {"upgraded", false}, {"cost", 1}, {"costForTurn", 1}},
            json{{"id", "Defend_R"}, {"uuid", "eye-b"}, {"upgraded", false}, {"cost", 1}, {"costForTurn", 1}}});
        one_combat::advisor::SilverImportContext eyeContext;
        eyeContext.session = "eye-session";
        auto eyeImported = one_combat::advisor::importSilverRoot(general, eyeContext);
        if (!eyeImported.ok || !eyeImported.wire.fullDrawOrderObserved
            || eyeImported.wire.drawPile.knownTop.size() != 2
            || eyeImported.wire.drawPile.knownTop[0].uniqueId
                == eyeImported.wire.drawPile.knownTop[1].uniqueId)
            throw std::runtime_error("Frozen Eye order/identity contract failed: ok="
                + std::to_string(eyeImported.ok) + " reason=" + eyeImported.reason
                + " full=" + std::to_string(eyeImported.wire.fullDrawOrderObserved)
                + " size=" + std::to_string(eyeImported.wire.drawPile.knownTop.size()));
        general["silverRoot"]["combat"]["cardSelect"] = json{
            {"task", "EXHAUST_ONE"}, {"cards", json::array({"Strike_R"})},
            {"pickCount", 1}, {"canPickZero", false}};
        auto selectionImported = one_combat::advisor::importSilverRoot(general, eyeContext);
        if (!selectionImported.ok || selectionImported.wire.inputState
                != static_cast<int>(InputState::CARD_SELECT)
            || selectionImported.wire.cardSelect.task
                != static_cast<std::int16_t>(CardSelectTask::EXHAUST_ONE))
            throw std::runtime_error("schema-v4 card-select contract failed");
        one_combat::advisor::SilverImportContext loweringContext;
        loweringContext.cardIds = {{"copy-a", 17}, {"copy-b", 23}};
        silver_bridge::SemanticAction loweringAction;
        loweringAction.type = silver_bridge::SemanticActionType::CARD;
        loweringAction.card.uniqueId = 23;
        loweringAction.target = 1;
        const auto lowered = one_combat::advisor::selectedLiveAction(loweringAction, loweringContext);
        if (lowered.value("kind", std::string()) != "card"
            || lowered.value("cardUuid", std::string()) != "copy-b"
            || lowered.value("targetIndex", 0) != 2)
            throw std::runtime_error("selectedLiveAction did not preserve physical card UUID and target");
        loweringAction.type = silver_bridge::SemanticActionType::SINGLE_CARD_SELECT;
        if (!one_combat::advisor::selectedLiveAction(loweringAction, loweringContext).is_null())
            throw std::runtime_error("unsupported single-card selection was lowered as executable");
        std::cout << "live Silver native first-turn parity checks passed\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "live Silver parity FAIL: " << e.what() << '\n';
        return 1;
    }
}
