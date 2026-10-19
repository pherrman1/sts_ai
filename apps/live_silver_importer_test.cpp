#include "one_combat/live_silver_importer.h"
#include "one_combat/live_silver_mapping.h"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <optional>
#include <fstream>
#include <stdexcept>
#include <string>
#include <set>
#include <vector>
#include <tuple>

#include "combat/Actions.h"
#include "combat/BattleContext.h"
#include "combat/BattleContextBinary.h"
#include "constants/Cards.h"
#include "constants/MonsterMoves.h"
#include "game/GameContext.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/SilverBridge.h"
#include "sim/search/SilverConversion.h"
#include "sim/search/SilverWireJson.h"
#include "sim/search/SilverWireState.h"
#include "sim/search/SilverSemanticAction.h"
#include "sim/search/Action.h"
#include "sim/search/SilverRolloutAgent.h"
#include "one_combat/native_silver_advisor.h"

using nlohmann::json;
using namespace sts;
using namespace sts::search;
using silver_bridge::BattleStateWire;
using silver_bridge::CardWire;
using silver_bridge::CardQueueItemWire;
using silver_bridge::MonsterWire;

namespace {
// The native Silver search the advisor runs, under the names this test used
// for the retired vendored session (ADR-0022).
struct SilverSearchConfig {
    std::int64_t simulationsPerDecision = 1000;
    bool collectRootActionSummaries = false;
    bool collectDecisionDiagnostics = false;
    bool adaptiveEnabled = false;
    bool exactVisitLockEnabled = false;
    bool rhoRacingEnabled = false;
};
using SilverRootActionSummary = one_combat::advisor::NativeSilverRootSummary;
using SilverSearchSession = one_combat::advisor::NativeSilverAdvisorSession;
struct SilverDecisionResult {
    bool accepted = false;
    silver_bridge::SemanticAction action;
    std::vector<SilverRootActionSummary> rootActionSummaries;
    one_combat::advisor::NativeSilverDecision diagnostic;
};
std::shared_ptr<SilverSearchSession> makeSilverSearchSession() {
    return std::make_shared<SilverSearchSession>();
}
SilverDecisionResult runSilverDecision(SilverSearchSession &session, const BattleStateWire &wire,
                                       const SilverSearchConfig &config) {
    auto decision = session.decide(wire, config.simulationsPerDecision);
    SilverDecisionResult out;
    out.accepted = decision.accepted;
    out.action = decision.action;
    out.rootActionSummaries = decision.rootActionSummaries;
    out.diagnostic = std::move(decision);
    return out;
}
SilverDecisionResult runSilverDecision(const BattleStateWire &wire, const SilverSearchConfig &config) {
    SilverSearchSession session;
    return runSilverDecision(session, wire, config);
}
std::vector<silver_bridge::SemanticAction> enumerateSilverLegalActions(const BattleStateWire &wire) {
    SilverSearchSession session;
    return session.decide(wire, 1).legalActions;
}
bool convertedStatesEqualForSearch(const BattleStateWire &a, const BattleStateWire &b) {
    try {
        return battleContextFromWire(a).equalForSearch(battleContextFromWire(b));
    } catch (const std::exception &) {
        return false;
    }
}
std::string semanticActionFingerprint(const silver_bridge::SemanticAction &action) {
    return semanticFingerprint(action);
}
struct Fixture { const char *name; int move; const char *room; BattleStateWire wire; json observation; };
json observation(const BattleStateWire &, const char *, int, const char *,
                 int = 0, json = json::array());
json cardJson(const CardWire &);
json genericObservation(const Fixture &, const char *);
void setProducerV4CardObservation(json &, const BattleStateWire &);

const char *cardId(CardId id) {
    switch (id) {
    case CardId::BASH: return "Bash";
    case CardId::HEADBUTT: return "Headbutt";
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
const char *nativeJavaMonsterName(MonsterId id) {
    switch (id) {
    case MonsterId::ACID_SLIME_L: return "AcidSlime_L";
    case MonsterId::ACID_SLIME_M: return "AcidSlime_M";
    case MonsterId::ACID_SLIME_S: return "AcidSlime_S";
    case MonsterId::AWAKENED_ONE: return "AwakenedOne";
    case MonsterId::BEAR: return "BanditBear";
    case MonsterId::BLUE_SLAVER: return "SlaverBlue";
    case MonsterId::BOOK_OF_STABBING: return "BookOfStabbing";
    case MonsterId::BRONZE_AUTOMATON: return "BronzeAutomaton";
    case MonsterId::BRONZE_ORB: return "BronzeOrb";
    case MonsterId::BYRD: return "Byrd";
    case MonsterId::CENTURION: return "Centurion";
    case MonsterId::CHOSEN: return "Chosen";
    case MonsterId::CORRUPT_HEART: return "CorruptHeart";
    case MonsterId::CULTIST: return "Cultist";
    case MonsterId::DAGGER: return "SnakeDagger";
    case MonsterId::DARKLING: return "Darkling";
    case MonsterId::DECA: return "Deca";
    case MonsterId::DONU: return "Donu";
    case MonsterId::EXPLODER: return "Exploder";
    case MonsterId::FAT_GREMLIN: return "GremlinFat";
    case MonsterId::FUNGI_BEAST: return "FungiBeast";
    case MonsterId::GIANT_HEAD: return "GiantHead";
    case MonsterId::GREEN_LOUSE: return "FuzzyLouseDefensive";
    case MonsterId::GREMLIN_LEADER: return "GremlinLeader";
    case MonsterId::GREMLIN_NOB: return "GremlinNob";
    case MonsterId::GREMLIN_WIZARD: return "GremlinWizard";
    case MonsterId::HEXAGHOST: return "Hexaghost";
    case MonsterId::JAW_WORM: return "JawWorm";
    case MonsterId::LAGAVULIN: return "Lagavulin";
    case MonsterId::LOOTER: return "Looter";
    case MonsterId::MAD_GREMLIN: return "GremlinWarrior";
    case MonsterId::MUGGER: return "Mugger";
    case MonsterId::MYSTIC: return "Healer";
    case MonsterId::NEMESIS: return "Nemesis";
    case MonsterId::ORB_WALKER: return "Orb Walker";
    case MonsterId::POINTY: return "BanditPointy";
    case MonsterId::RED_LOUSE: return "FuzzyLouseNormal";
    case MonsterId::RED_SLAVER: return "SlaverRed";
    case MonsterId::REPTOMANCER: return "Reptomancer";
    case MonsterId::REPULSOR: return "Repulsor";
    case MonsterId::ROMEO: return "BanditLeader";
    case MonsterId::SENTRY: return "Sentry";
    case MonsterId::SHELLED_PARASITE: return "Shelled Parasite";
    case MonsterId::SHIELD_GREMLIN: return "GremlinTsundere";
    case MonsterId::SLIME_BOSS: return "SlimeBoss";
    case MonsterId::SNAKE_PLANT: return "SnakePlant";
    case MonsterId::SNEAKY_GREMLIN: return "GremlinThief";
    case MonsterId::SNECKO: return "Snecko";
    case MonsterId::SPHERIC_GUARDIAN: return "SphericGuardian";
    case MonsterId::SPIKER: return "Spiker";
    case MonsterId::SPIKE_SLIME_L: return "SpikeSlime_L";
    case MonsterId::SPIKE_SLIME_M: return "SpikeSlime_M";
    case MonsterId::SPIKE_SLIME_S: return "SpikeSlime_S";
    case MonsterId::SPIRE_GROWTH: return "Serpent";
    case MonsterId::SPIRE_SHIELD: return "SpireShield";
    case MonsterId::SPIRE_SPEAR: return "SpireSpear";
    case MonsterId::TASKMASTER: return "SlaverBoss";
    case MonsterId::THE_CHAMP: return "Champ";
    case MonsterId::THE_COLLECTOR: return "TheCollector";
    case MonsterId::THE_GUARDIAN: return "TheGuardian";
    case MonsterId::THE_MAW: return "Maw";
    case MonsterId::TIME_EATER: return "TimeEater";
    case MonsterId::TORCH_HEAD: return "TorchHead";
    case MonsterId::TRANSIENT: return "Transient";
    case MonsterId::WRITHING_MASS: return "WrithingMass";
    default: return "";
    }
}
int javaMoveByte(const char *name, MonsterMoveId nativeMove) {
    if (nativeMove == MonsterMoveId::INVALID) return -1;
    // The independent literal table above proves the Java byte -> native
    // direction.  This inverse is only a test renderer for native fixtures;
    // it is not production mapping logic.
    for (int byte = 0; byte <= 8; ++byte) {
        const auto mapped = one_combat::advisor::live_silver::monsterMove(name, byte);
        if (mapped && *mapped == nativeMove) return byte;
    }
    return -1;
}
const char *nativeMonsterPowerName(int status) {
    static constexpr const char *names[] = {
        "Artifact", "BlockReturnPower", "ChokedPower", "CorpseExplosionPower",
        "LockOnPower", "MarkPower", "Metallicize", "Plated Armor", "Poison",
        "Regeneration", "ShackledPower", "Strength", "Vulnerable", "Weak", "Angry",
        "BeatOfDeath", "Curiosity", "Curl Up", "Enrage", "Fading", "Flight",
        "GenericStrengthUp", "Intangible", "Malleable", "Mode Shift", "Ritual", "Slow",
        "Spore Cloud", "Thievery", "Thorns", "Time Warp", "Invincible", "Reactive",
        "Sharp Hide", "Asleep", "Barricade", "Minion", "MinionLeader", "PainfulStabs",
        "Regrow", "Shifting", "Stasis",
    };
    return status >= 0 && status < static_cast<int>(sizeof(names) / sizeof(names[0]))
        ? names[status] : "";
}
int nativeMonsterPowerAmount(const MonsterWire &monster, int status) {
    if (status == static_cast<int>(MonsterStatus::STRENGTH)) return monster.strength;
    if (status == static_cast<int>(MonsterStatus::VULNERABLE)) return monster.vulnerable;
    if (status == static_cast<int>(MonsterStatus::WEAK)) return monster.weak;
    if (status >= static_cast<int>(MonsterStatus::INVINCIBLE)
        && status <= static_cast<int>(MonsterStatus::SHARP_HIDE)) return monster.uniquePower1;
    if (status >= static_cast<int>(MonsterStatus::ANGRY)
        && status <= static_cast<int>(MonsterStatus::TIME_WARP)) return monster.uniquePower0;
    if (status < static_cast<int>(MonsterStatus::ARTIFACT)
        || status > static_cast<int>(MonsterStatus::SHACKLED)) return 1;
    return monster.smallPowers[static_cast<std::size_t>(status)];
}
json nativeMonsterPowers(const MonsterWire &monster) {
    json powers = json::array();
    for (int status = 0; status <= static_cast<int>(MonsterStatus::STASIS); ++status) {
        const bool active = status == static_cast<int>(MonsterStatus::STRENGTH)
            ? monster.strength != 0
            : (monster.statusBits & (1ULL << status)) != 0;
        if (!active) continue;
        const auto name = nativeMonsterPowerName(status);
        if (*name == '\0') throw std::runtime_error("native power renderer missing status name");
        json power = {{"id", name}, {"amount", nativeMonsterPowerAmount(monster, status)}};
        if (status == static_cast<int>(MonsterStatus::VULNERABLE)
            || status == static_cast<int>(MonsterStatus::WEAK)
            || status == static_cast<int>(MonsterStatus::RITUAL)) {
            const int bit = status == static_cast<int>(MonsterStatus::VULNERABLE) ? 63
                : status == static_cast<int>(MonsterStatus::WEAK) ? 62 : 61;
            power["justApplied"] = (monster.statusBits & (1ULL << bit)) != 0;
        }
        powers.push_back(std::move(power));
    }
    return powers;
}
json nativeObservation(const BattleStateWire &wire, const char *room, const char *instance) {
    const char *firstName = "Cultist";
    int firstMove = 3;
    for (int i = 0; i < wire.monsterCount; ++i) {
        if (wire.monsters[i].idx < 0) continue;
        firstName = nativeJavaMonsterName(static_cast<MonsterId>(wire.monsters[i].id));
        firstMove = javaMoveByte(firstName,
            static_cast<MonsterMoveId>(wire.monsters[i].moveHistory[0]));
        if (firstMove < 0) throw std::runtime_error("native sweep current move has no Java byte");
        break;
    }
    auto out = observation(wire, firstName, firstMove, room, 0, json::array());
    out["sequence"] = wire.observedGeneration;
    auto &root = out["silverRoot"];
    root["schemaVersion"] = 4;
    root.erase("decisionOrdinal");
    root.erase("firstDecision");
    root["decisionInTurn"] = 0;
    root["playerTurn"] = wire.turn + 1;
    root["combatInstance"] = instance;
    root["encounter"] = monsterEncounterEnumNames[wire.encounter];
    root["act"] = wire.act;
    root["floor"] = wire.floorNum;
    root["ascension"] = wire.ascension;
    root["hp"] = wire.player.curHp;
    root["maxHp"] = wire.player.maxHp;
    root["gold"] = wire.player.gold;
    root["potionCapacity"] = wire.potionCapacity;
    root["burningElite"] = false;
    auto &combat = root["combat"];
    combat["turn"] = wire.turn + 1;
    combat["energy"] = wire.player.energy;
    combat["block"] = wire.player.block;
    combat["cardsPlayedThisTurn"] = wire.player.cardsPlayedThisTurn;
    combat["attacksPlayedThisTurn"] = wire.player.attacksPlayedThisTurn;
    combat["skillsPlayedThisTurn"] = wire.player.skillsPlayedThisTurn;
    combat["cardsDiscardedThisTurn"] = wire.player.cardsDiscardedThisTurn;
    combat["lastAttackUnblockedDamage"] = wire.player.lastAttackUnblockedDamage;
    combat["timesDamagedThisCombat"] = wire.player.timesDamagedThisCombat;
    combat["lastTargetedMonster"] = wire.player.lastTargetedMonster;
    combat["energyPerTurn"] = wire.player.energyPerTurn;
    combat["cardDrawPerTurn"] = wire.player.cardDrawPerTurn;
    combat["artifact"] = wire.player.artifact;
    combat["dexterity"] = wire.player.dexterity;
    combat["focus"] = wire.player.focus;
    combat["strength"] = wire.player.strength;
    combat["stance"] = wire.player.stance;
    combat["orbSlots"] = wire.player.orbSlots;
    combat["statusBits0"] = wire.player.statusBits0;
    combat["statusBits1"] = wire.player.statusBits1;
    combat["justAppliedBits"] = wire.player.justAppliedBits;
    combat["statusMap"] = json::array();
    for (const auto &[status, amount] : wire.player.statusMap)
        combat["statusMap"].push_back(json::array({status, amount}));
    combat["playedThisTurn"] = json::array();
    combat["playerPowers"] = json::array();
    combat["loopCount"] = wire.loopCount;
    combat["cardsDrawn"] = wire.cardsDrawn;
    combat["energyWasted"] = wire.energyWasted;
    combat["monsterTurnIdx"] = wire.monsterTurnIdx;
    combat["outcome"] = wire.outcome;
    combat["endTurnQueued"] = wire.endTurnQueued;
    combat["turnHasEnded"] = wire.turnHasEnded;
    combat["skipMonsterTurn"] = wire.skipMonsterTurn;
    combat["miscBits"] = wire.miscBits;
    combat["extraRollMoveOnTurn"] = wire.extraRollMoveOnTurn;
    combat["skipMonsterTurnBits"] = wire.skipMonsterTurnBits;
    combat["monsterCount"] = wire.monsterCount;
    combat["monstersAlive"] = wire.monstersAlive;
    combat["stasis"] = json::array();
    for (std::size_t slot = 0; slot < wire.stasisCards.size(); ++slot) {
        const auto &card = wire.stasisCards[slot];
        if (card.id == static_cast<std::int16_t>(CardId::INVALID)) continue;
        auto serialized = cardJson(card);
        serialized["slot"] = slot;
        combat["stasis"].push_back(std::move(serialized));
    }
    combat["monsters"] = json::array();
    for (int i = 0; i < wire.monsterCount; ++i) {
        const auto &monster = wire.monsters[i];
        if (monster.idx < 0) continue;
        const auto id = static_cast<MonsterId>(monster.id);
        const auto name = nativeJavaMonsterName(id);
        if (*name == '\0') throw std::runtime_error("native sweep monster has no Java id");
        const auto current = javaMoveByte(name,
            static_cast<MonsterMoveId>(monster.moveHistory[0]));
        if (current < 0) throw std::runtime_error("native sweep current move is not mapped");
        json history = json::array();
        const auto previous = javaMoveByte(name,
            static_cast<MonsterMoveId>(monster.moveHistory[1]));
        if (previous >= 0) history.push_back(previous);
        history.push_back(current);
        combat["monsters"].push_back({
            {"id", name}, {"slot", monster.idx}, {"idx", monster.idx}, {"occupantGeneration",monster.occupantGeneration},
            {"hp", monster.curHp}, {"maxHp", monster.maxHp}, {"block", monster.block},
            {"dead", monster.curHp <= 0 || monster.isEscapingB},
            {"escaping", monster.isEscapingB}, {"halfDead", monster.halfDead},
            {"escapeNext", monster.escapeNext}, {"nextMove", current},
            {"moveHistory", std::move(history)}, {"statusBits", monster.statusBits},
            {"strength", monster.strength}, {"vulnerable", monster.vulnerable},
            {"weak", monster.weak}, {"uniquePower0", monster.uniquePower0},
            {"uniquePower1", monster.uniquePower1}, {"miscInfo", monster.miscInfo},
            {"powers", nativeMonsterPowers(monster)}});
    }
    return out;
}
json javaLikeDynamicObservation(const BattleStateWire &wire, const char *room,
                                const char *instance) {
    auto out = nativeObservation(wire, room, instance);
    auto &monsters = out["silverRoot"]["combat"]["monsters"];
    for (auto &monster : monsters) {
        const auto id = monster.value("id", std::string());
        // These are native convenience fields, not fields emitted by the
        // Java observer.  Dynamic parity must cross the same public boundary
        // as production observations and reconstruct status bits from powers.
        monster.erase("statusBits");
        monster.erase("strength");
        monster.erase("vulnerable");
        monster.erase("weak");
        monster.erase("uniquePower1");
        if (id != "Hexaghost") monster.erase("uniquePower0");
        if (id == "AwakenedOne") {
            const auto &powers = monster["powers"];
            const bool phase2 = std::any_of(powers.begin(), powers.end(), [](const json &power) {
                return power.value("id", std::string()) == "MinionLeader";
            });
            monster["miscInfo"] = phase2 ? 1 : 0;
        }
        // Ordinary BronzeOrb capture reads Java usedStasis, set when Stasis
        // is selected. Presence of the later Stasis power is not that flag.
    }
    return out;
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
    for (auto &card : wire.stasisCards) {
        card.uniqueId = -1;
        card.cost = 1;
        card.costForTurn = 1;
    }
}
void normalizeDynamicObservationIdentity(BattleStateWire &wire) {
    int nextId = 0;
    const auto assign = [&nextId](auto &cards) {
        for (auto &card : cards) card.uniqueId = static_cast<std::int16_t>(nextId++);
    };
    assign(wire.drawPile.unknown);
    assign(wire.discardPile.unknown);
    assign(wire.exhaustPile.unknown);
    assign(wire.hand);
    wire.limbo.assign(10, CardWire{});
    for (auto &card : wire.limbo) card.uniqueId = -1;
    const auto stasisCards = wire.stasisCards;
    wire.stasisCards.fill(CardWire{});
    for (std::size_t i = 0; i < wire.stasisCards.size(); ++i) {
        auto &card = wire.stasisCards[i];
        card.uniqueId = -1;
        card.cost = 1;
        card.costForTurn = 1;
        if (stasisCards[i].id != static_cast<std::int16_t>(CardId::INVALID))
            card = stasisCards[i];
        if (card.id != static_cast<std::int16_t>(CardId::INVALID))
            card.uniqueId = static_cast<std::int16_t>(nextId++);
    }
    wire.nextUniqueCardId = nextId;
    wire.observedGeneration = 1;
}
void assertAbsentLimboAndStasisLayout(const BattleStateWire &wire, const char *source) {
    if (wire.limbo.size() != 10)
        throw std::runtime_error(std::string(source) + " limbo does not have ten native slots");
    for (std::size_t i = 0; i < wire.limbo.size(); ++i) {
        const auto &card = wire.limbo[i];
        if (card.id == static_cast<std::int16_t>(CardId::INVALID)
            && (card.uniqueId != -1 || card.cost != 0 || card.costForTurn != 0))
            throw std::runtime_error(std::string(source) + " absent limbo slot is not default-constructed");
    }
    for (std::size_t i = 0; i < wire.stasisCards.size(); ++i) {
        const auto &card = wire.stasisCards[i];
        if (card.id == static_cast<std::int16_t>(CardId::INVALID)
            && (card.uniqueId != -1 || card.cost != 1 || card.costForTurn != 1))
            throw std::runtime_error(std::string(source) + " absent stasis slot has the wrong sentinel");
    }
}
void resolveMonsterTransition(BattleContext &live, int monsterIdx) {
    if (monsterIdx < 0 || monsterIdx >= live.monsters.monsterCount)
        throw std::runtime_error("dynamic transition monster index is out of range");
    live.setState(InputState::EXECUTING_ACTIONS);
    live.monsterTurnIdx = monsterIdx;
    live.monsters.arr[monsterIdx].takeTurn(live);
    // The transition under test is the selected monster's action.  Skip the
    // remaining monster turns and drain its queued actions to reach the next
    // ordinary player decision boundary.
    live.monsterTurnIdx = live.monsters.monsterCount;
    live.setState(InputState::EXECUTING_ACTIONS);
    live.executeActions();
    if (live.inputState != InputState::PLAYER_NORMAL)
        throw std::runtime_error("dynamic transition did not reach PLAYER_NORMAL");
}
void assertDynamicParity(const char *name, BattleContext &live, CombatKnowledgeState &knowledge,
                         const GameContext &game) {
    auto wire = makeSilverBattleStateWire(live, knowledge, makeSilverRunContext(game), live.seed);
    if (!wire.valid) throw std::runtime_error(std::string(name) + " native conversion failed");
    normalizeDynamicObservationIdentity(wire);
    const auto rendered = javaLikeDynamicObservation(wire, "MONSTER", name);
    one_combat::advisor::SilverImportContext context;
    context.session = "dynamic-transition";
    const auto imported = one_combat::advisor::importSilverRoot(rendered, context);
    if (!imported.ok)
        throw std::runtime_error(std::string(name) + " Java-like observation rejected: "
            + imported.reason);
    assertAbsentLimboAndStasisLayout(imported.wire, name);
    auto canonical = wire;
    canonical.isolatedSearchSeed = imported.wire.isolatedSearchSeed;
    if (!convertedStatesEqualForSearch(canonical, imported.wire))
        throw std::runtime_error(std::string(name) + " dynamic search-state parity failed: native="
            + battleStateWireEnvelope(canonical).dump() + " imported="
            + battleStateWireEnvelope(imported.wire).dump());
    SilverSearchConfig config;
    config.simulationsPerDecision = 1;
    config.adaptiveEnabled = false;
    config.exactVisitLockEnabled = false;
    config.rhoRacingEnabled = false;
    const auto decision = runSilverDecision(imported.wire, config);
    if (!decision.accepted)
        throw std::runtime_error(std::string(name) + " dynamic Silver decision was rejected");
}
void verifyDynamicTransitionCorpus() {
    {
        GameContext game(CharacterClass::IRONCLAD, 0xD506u, 0);
        game.act = 3; game.floorNum = 1;
        BattleContext live;
        live.init(game, MonsterEncounter::GIANT_HEAD);
        CombatKnowledgeState knowledge;
        knowledge.initializeFromLiveBattle(live);
        if (!live.monsters.arr[0].hasStatus<MonsterStatus::SLOW>()
            || live.monsters.arr[0].getStatus<MonsterStatus::SLOW>() != 0)
            throw std::runtime_error("Giant Head did not expose active Slow(0)");
        assertDynamicParity("GIANT_HEAD_SLOW_ZERO", live, knowledge, game);
    }
    {
        GameContext game(CharacterClass::IRONCLAD, 0xD507u, 0);
        game.act = 3; game.floorNum = 1;
        BattleContext live;
        live.init(game, MonsterEncounter::TIME_EATER);
        CombatKnowledgeState knowledge;
        knowledge.initializeFromLiveBattle(live);
        if (!live.monsters.arr[0].hasStatus<MonsterStatus::TIME_WARP>()
            || live.monsters.arr[0].getStatus<MonsterStatus::TIME_WARP>() != 0)
            throw std::runtime_error("Time Eater did not expose active Time Warp(0)");
        assertDynamicParity("TIME_EATER_TIME_WARP_ZERO", live, knowledge, game);
    }
    {
        GameContext game(CharacterClass::IRONCLAD, 0xD508u, 0);
        game.act = 3; game.floorNum = 1;
        BattleContext live;
        live.init(game, MonsterEncounter::WRITHING_MASS);
        CombatKnowledgeState knowledge;
        knowledge.initializeFromLiveBattle(live);
        if (!live.monsters.arr[0].hasStatus<MonsterStatus::REACTIVE>()
            || live.monsters.arr[0].getStatus<MonsterStatus::REACTIVE>() != 0)
            throw std::runtime_error("Writhing Mass did not expose active Reactive(0)");
        assertDynamicParity("WRITHING_MASS_REACTIVE_ZERO", live, knowledge, game);
    }
    {
        GameContext game(CharacterClass::IRONCLAD, 0xD509u, 0);
        game.act = 1; game.floorNum = 1;
        BattleContext live;
        live.init(game, MonsterEncounter::CULTIST);
        CombatKnowledgeState knowledge;
        knowledge.initializeFromLiveBattle(live);
        // This is the native effect queued by CardId::DISARM.  Apply the
        // effect directly so the producer-shaped root remains a starter-deck
        // observation rather than introducing a non-starter card into the
        // exhaust pile solely for this transition fixture.
        live.setState(InputState::EXECUTING_ACTIONS);
        live.addToBot(Actions::DebuffEnemy<MonsterStatus::STRENGTH>(0, -2, false));
        live.executeActions();
        if (live.inputState != InputState::PLAYER_NORMAL
            || live.monsters.arr[0].strength != -2)
            throw std::runtime_error("Disarm did not produce native Strength -2 state");
        assertDynamicParity("DISARM_NEGATIVE_STRENGTH", live, knowledge, game);
    }
    {
        GameContext game(CharacterClass::IRONCLAD, 0xD501u, 0);
        game.act = 1; game.floorNum = 1;
        BattleContext live;
        live.init(game, MonsterEncounter::LARGE_SLIME);
        CombatKnowledgeState knowledge;
        knowledge.initializeFromLiveBattle(live);
        const auto split = live.monsters.arr[0].id == MonsterId::ACID_SLIME_L
            ? MonsterMoveId::ACID_SLIME_L_SPLIT : MonsterMoveId::SPIKE_SLIME_L_SPLIT;
        live.monsters.arr[0].moveHistory[0] = split;
        resolveMonsterTransition(live, 0);
        if (live.monsters.monsterCount != 2 || live.monsters.arr[0].idx != 0
            || live.monsters.arr[1].idx != 1
            || live.monsters.arr[0].id != live.monsters.arr[1].id)
            throw std::runtime_error("Large Slime split did not occupy native slots 0/1");
        assertDynamicParity("LARGE_SLIME_SPLIT", live, knowledge, game);
    }
    {
        GameContext game(CharacterClass::IRONCLAD, 0xD502u, 0);
        game.act = 2; game.floorNum = 1;
        BattleContext live;
        live.init(game, MonsterEncounter::REPTOMANCER);
        CombatKnowledgeState knowledge;
        knowledge.initializeFromLiveBattle(live);
        live.monsters.arr[2].moveHistory[0] = MonsterMoveId::REPTOMANCER_SUMMON;
        resolveMonsterTransition(live, 2);
        if (live.monsters.monsterCount != 5 || live.monsters.arr[3].id != MonsterId::DAGGER)
            throw std::runtime_error("Reptomancer summon did not preserve native slot 3");
        assertDynamicParity("REPTOMANCER_SUMMON", live, knowledge, game);
    }
    {
        GameContext game(CharacterClass::IRONCLAD, 0xD503u, 0);
        game.act = 3; game.floorNum = 1;
        BattleContext live;
        live.init(game, MonsterEncounter::THREE_DARKLINGS);
        CombatKnowledgeState knowledge;
        knowledge.initializeFromLiveBattle(live);
        if (!live.monsters.arr[0].hasStatus<MonsterStatus::REGROW>())
            throw std::runtime_error("Darkling root did not expose Java Regrow power");
        live.setState(InputState::EXECUTING_ACTIONS);
        live.addToBot(Actions::DamageEnemy(0, 9999));
        live.executeActions();
        if (live.inputState != InputState::PLAYER_NORMAL
            || !live.monsters.arr[0].isHalfDead()
            || live.monsters.arr[0].moveHistory[0] != MonsterMoveId::DARKLING_REGROW)
            throw std::runtime_error("Darkling Regrow transition did not produce public state");
        assertDynamicParity("DARKLING_REGROW", live, knowledge, game);
    }
    {
        GameContext game(CharacterClass::IRONCLAD, 0xD504u, 0);
        game.act = 2; game.floorNum = 1;
        BattleContext live;
        live.init(game, MonsterEncounter::AUTOMATON);
        CombatKnowledgeState knowledge;
        knowledge.initializeFromLiveBattle(live);
        live.monsters.arr[1].moveHistory[0] = MonsterMoveId::BRONZE_AUTOMATON_SPAWN_ORBS;
        resolveMonsterTransition(live, 1);
        live.monsters.arr[0].moveHistory[0] = MonsterMoveId::BRONZE_ORB_STASIS;
        resolveMonsterTransition(live, 0);
        if (live.cards.stasisCards[0].id == CardId::INVALID
            || !live.monsters.arr[0].hasStatus<MonsterStatus::STASIS>())
            throw std::runtime_error("Bronze Orb Stasis transition did not produce public state");
        assertDynamicParity("BRONZE_ORB_STASIS", live, knowledge, game);
    }
    {
        GameContext game(CharacterClass::IRONCLAD, 0xD505u, 0);
        game.act = 3; game.floorNum = 1;
        BattleContext live;
        live.init(game, MonsterEncounter::AWAKENED_ONE);
        CombatKnowledgeState knowledge;
        knowledge.initializeFromLiveBattle(live);
        live.setState(InputState::EXECUTING_ACTIONS);
        live.addToBot(Actions::DamageEnemy(2, 9999));
        live.addToBot(Actions::DamageEnemy(0, 9999));
        live.addToBot(Actions::DamageEnemy(1, 9999));
        live.executeActions();
        live.monsters.arr[2].takeTurn(live);
        live.monsterTurnIdx = live.monsters.monsterCount;
        live.setState(InputState::EXECUTING_ACTIONS);
        live.executeActions();
        if (live.inputState != InputState::PLAYER_NORMAL
            || live.monsters.arr[2].isHalfDead()
            || !live.monsters.arr[2].hasStatus<MonsterStatus::MINION_LEADER>())
            throw std::runtime_error("Awakened One stage-2 transition did not produce public state");
        assertDynamicParity("AWAKENED_ONE_STAGE2", live, knowledge, game);
    }
    std::cout << "live Silver dynamic transition corpus passed: split/summon/regrow/stasis/phase/zero-powers/negative-strength\n";
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
                 int ordinal, json played) {
    json monsters = json::array();
    const auto &m = w.monsters[0];
    monsters.push_back({{"id", name}, {"hp", m.curHp}, {"maxHp", m.maxHp},
                        {"block", m.block}, {"nextMove", move},
                        {"moveHistory", json::array({move})}, {"miscInfo", m.miscInfo},
                        {"powers", json::array()}});
    if (m.occupantGeneration > 0)
        monsters[0]["occupantGeneration"] = m.occupantGeneration;
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
    int selectedNativeUniqueId = semantic.card.uniqueId;
    const auto &combat = root.observation["silverRoot"]["combat"];
    const int handBase = static_cast<int>(combat.value("draw", json::array()).size()
        + combat.value("discard", json::array()).size()
        + combat.value("exhaust", json::array()).size());
    const int protocolHandIndex = semantic.card.uniqueId - handBase;
    if (protocolHandIndex >= 0 && protocolHandIndex < static_cast<int>(root.wire.hand.size()))
        selectedNativeUniqueId = root.wire.hand[protocolHandIndex].uniqueId;
    for (int i = 0; i < live.cards.cardsInHand; ++i) {
        const auto &candidate = live.cards.hand[i];
        if (candidate.id != wanted) continue;
        const bool selectedIdentity = candidate.uniqueId == selectedNativeUniqueId;
        if ((!differentEquivalentCopy && selectedIdentity)
            || (differentEquivalentCopy && !selectedIdentity)) {
            handIndex = i;
            break;
        }
    }
    if (handIndex < 0) throw std::runtime_error("requested semantic card copy is absent");
    const auto rawAction = semantic.target >= 0
        ? sts::search::Action(sts::search::ActionType::CARD, handIndex, semantic.target)
        : sts::search::Action(sts::search::ActionType::CARD, handIndex);
    rawAction.execute(live);
    auto wire = makeSilverBattleStateWire(live, knowledge, makeSilverRunContext(game),
                                           root.wire.isolatedSearchSeed);
    if (!wire.valid) throw std::runtime_error("semantic successor conversion failed");
    Fixture successor{root.name, root.move, root.room, wire,
        observation(wire, root.name, root.move, root.room, 1,
                    json::array({{{"id", cardId(wanted)},
                                  {"uuid", uuid(wire.curCardQueueItem.card)},
                                  {"upgraded", false}}}))};
    // The retained-branch tests intentionally use the producer-shaped v4
    // boundary.  The older schema-v2 path has a synthetic queue item and
    // cannot prove that Java's public CardQueueItem was preserved.
    const auto entry = root.observation.value("combatEntryHash", "entry-v4");
    successor.observation = genericObservation(successor, entry.c_str());
    return successor;
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
            {"idx", monster.idx}, {"occupantGeneration",monster.occupantGeneration}, {"hp", monster.curHp}, {"maxHp", monster.maxHp},
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
    expect("AwakenedOne", 1, MonsterMoveId::AWAKENED_ONE_SLASH);
    expect("AwakenedOne", 2, MonsterMoveId::AWAKENED_ONE_SOUL_STRIKE);
    expect("AwakenedOne", 3, MonsterMoveId::AWAKENED_ONE_REBIRTH);
    expect("AwakenedOne", 5, MonsterMoveId::AWAKENED_ONE_DARK_ECHO);
    expect("AwakenedOne", 6, MonsterMoveId::AWAKENED_ONE_SLUDGE);
    expect("AwakenedOne", 8, MonsterMoveId::AWAKENED_ONE_TACKLE);
    expect("Darkling", 1, MonsterMoveId::DARKLING_CHOMP);
    expect("Darkling", 2, MonsterMoveId::DARKLING_HARDEN);
    expect("Darkling", 3, MonsterMoveId::DARKLING_NIP);
    expect("Darkling", 4, MonsterMoveId::DARKLING_REGROW);
    expect("Darkling", 5, MonsterMoveId::DARKLING_REINCARNATE);
    expect("Deca", 0, MonsterMoveId::DECA_BEAM);
    expect("Deca", 2, MonsterMoveId::DECA_SQUARE_OF_PROTECTION);
    expect("Donu", 0, MonsterMoveId::DONU_BEAM);
    expect("Donu", 2, MonsterMoveId::DONU_CIRCLE_OF_POWER);
    expect("Exploder", 1, MonsterMoveId::EXPLODER_SLAM);
    expect("Exploder", 2, MonsterMoveId::EXPLODER_EXPLODE);
    expect("GiantHead", 1, MonsterMoveId::GIANT_HEAD_GLARE);
    expect("GiantHead", 2, MonsterMoveId::GIANT_HEAD_IT_IS_TIME);
    expect("GiantHead", 3, MonsterMoveId::GIANT_HEAD_COUNT);
    expect("GremlinLeader", 2, MonsterMoveId::GREMLIN_LEADER_RALLY);
    expect("GremlinLeader", 3, MonsterMoveId::GREMLIN_LEADER_ENCOURAGE);
    expect("GremlinLeader", 4, MonsterMoveId::GREMLIN_LEADER_STAB);
    expect("Mugger", 1, MonsterMoveId::MUGGER_MUG);
    expect("Mugger", 2, MonsterMoveId::MUGGER_SMOKE_BOMB);
    expect("Mugger", 3, MonsterMoveId::MUGGER_ESCAPE);
    expect("Mugger", 4, MonsterMoveId::MUGGER_LUNGE);
    expect("Nemesis", 2, MonsterMoveId::NEMESIS_ATTACK);
    expect("Nemesis", 3, MonsterMoveId::NEMESIS_SCYTHE);
    expect("Nemesis", 4, MonsterMoveId::NEMESIS_DEBUFF);
    expect("Orb Walker", 1, MonsterMoveId::ORB_WALKER_LASER);
    expect("Orb Walker", 2, MonsterMoveId::ORB_WALKER_CLAW);
    expect("Reptomancer", 1, MonsterMoveId::REPTOMANCER_SNAKE_STRIKE);
    expect("Reptomancer", 2, MonsterMoveId::REPTOMANCER_SUMMON);
    expect("Reptomancer", 3, MonsterMoveId::REPTOMANCER_BIG_BITE);
    expect("Repulsor", 1, MonsterMoveId::REPULSOR_REPULSE);
    expect("Repulsor", 2, MonsterMoveId::REPULSOR_BASH);
    expect("Spiker", 1, MonsterMoveId::SPIKER_CUT);
    expect("Spiker", 2, MonsterMoveId::SPIKER_SPIKE);
    expect("Serpent", 1, MonsterMoveId::SPIRE_GROWTH_QUICK_TACKLE);
    expect("Serpent", 2, MonsterMoveId::SPIRE_GROWTH_CONSTRICT);
    expect("Serpent", 3, MonsterMoveId::SPIRE_GROWTH_SMASH);
    expect("TimeEater", 2, MonsterMoveId::TIME_EATER_REVERBERATE);
    expect("TimeEater", 3, MonsterMoveId::TIME_EATER_RIPPLE);
    expect("TimeEater", 4, MonsterMoveId::TIME_EATER_HEAD_SLAM);
    expect("TimeEater", 5, MonsterMoveId::TIME_EATER_HASTE);
    expect("Transient", 1, MonsterMoveId::TRANSIENT_ATTACK);
    expect("WrithingMass", 0, MonsterMoveId::WRITHING_MASS_STRONG_STRIKE);
    expect("WrithingMass", 1, MonsterMoveId::WRITHING_MASS_MULTI_STRIKE);
    expect("WrithingMass", 2, MonsterMoveId::WRITHING_MASS_FLAIL);
    expect("WrithingMass", 3, MonsterMoveId::WRITHING_MASS_WITHER);
    expect("WrithingMass", 4, MonsterMoveId::WRITHING_MASS_IMPLANT);
    expect("BookOfStabbing", 1, MonsterMoveId::BOOK_OF_STABBING_MULTI_STAB);
    expect("BookOfStabbing", 2, MonsterMoveId::BOOK_OF_STABBING_SINGLE_STAB);
    expect("BronzeAutomaton", 1, MonsterMoveId::BRONZE_AUTOMATON_FLAIL);
    expect("BronzeAutomaton", 2, MonsterMoveId::BRONZE_AUTOMATON_HYPER_BEAM);
    expect("BronzeAutomaton", 3, MonsterMoveId::BRONZE_AUTOMATON_STUNNED);
    expect("BronzeAutomaton", 4, MonsterMoveId::BRONZE_AUTOMATON_SPAWN_ORBS);
    expect("BronzeAutomaton", 5, MonsterMoveId::BRONZE_AUTOMATON_BOOST);
    expect("BronzeOrb", 1, MonsterMoveId::BRONZE_ORB_BEAM);
    expect("BronzeOrb", 2, MonsterMoveId::BRONZE_ORB_SUPPORT_BEAM);
    expect("BronzeOrb", 3, MonsterMoveId::BRONZE_ORB_STASIS);
    expect("Byrd", 1, MonsterMoveId::BYRD_PECK);
    expect("Byrd", 2, MonsterMoveId::BYRD_FLY);
    expect("Byrd", 3, MonsterMoveId::BYRD_SWOOP);
    expect("Byrd", 4, MonsterMoveId::BYRD_STUNNED);
    expect("Byrd", 5, MonsterMoveId::BYRD_HEADBUTT);
    expect("Byrd", 6, MonsterMoveId::BYRD_CAW);
    expect("Centurion", 1, MonsterMoveId::CENTURION_SLASH);
    expect("Centurion", 2, MonsterMoveId::CENTURION_DEFEND);
    expect("Centurion", 3, MonsterMoveId::CENTURION_FURY);
    expect("Chosen", 1, MonsterMoveId::CHOSEN_ZAP);
    expect("Chosen", 2, MonsterMoveId::CHOSEN_DRAIN);
    expect("Chosen", 3, MonsterMoveId::CHOSEN_DEBILITATE);
    expect("Chosen", 4, MonsterMoveId::CHOSEN_HEX);
    expect("Chosen", 5, MonsterMoveId::CHOSEN_POKE);
    expect("CorruptHeart", 1, MonsterMoveId::CORRUPT_HEART_BLOOD_SHOTS);
    expect("CorruptHeart", 2, MonsterMoveId::CORRUPT_HEART_ECHO);
    expect("CorruptHeart", 3, MonsterMoveId::CORRUPT_HEART_DEBILITATE);
    expect("CorruptHeart", 4, MonsterMoveId::CORRUPT_HEART_BUFF);
    expect("Dagger", 1, MonsterMoveId::DAGGER_STAB);
    expect("Dagger", 2, MonsterMoveId::DAGGER_EXPLODE);
    expect("Healer", 1, MonsterMoveId::MYSTIC_ATTACK_DEBUFF);
    expect("Healer", 2, MonsterMoveId::MYSTIC_HEAL);
    expect("Healer", 3, MonsterMoveId::MYSTIC_BUFF);
    expect("Mystic", 1, MonsterMoveId::MYSTIC_ATTACK_DEBUFF);
    expect("Mystic", 2, MonsterMoveId::MYSTIC_HEAL);
    expect("Mystic", 3, MonsterMoveId::MYSTIC_BUFF);
    expect("SlaverBoss", 2, MonsterMoveId::TASKMASTER_SCOURING_WHIP);
    expect("Shelled Parasite", 1, MonsterMoveId::SHELLED_PARASITE_FELL);
    expect("Shelled Parasite", 2, MonsterMoveId::SHELLED_PARASITE_DOUBLE_STRIKE);
    expect("Shelled Parasite", 3, MonsterMoveId::SHELLED_PARASITE_SUCK);
    expect("Shelled Parasite", 4, MonsterMoveId::SHELLED_PARASITE_STUNNED);
    expect("SnakePlant", 1, MonsterMoveId::SNAKE_PLANT_CHOMP);
    expect("SnakePlant", 2, MonsterMoveId::SNAKE_PLANT_ENFEEBLING_SPORES);
    expect("Snecko", 1, MonsterMoveId::SNECKO_PERPLEXING_GLARE);
    expect("Snecko", 2, MonsterMoveId::SNECKO_BITE);
    expect("Snecko", 3, MonsterMoveId::SNECKO_TAIL_WHIP);
    expect("SphericGuardian", 1, MonsterMoveId::SPHERIC_GUARDIAN_SLAM);
    expect("SphericGuardian", 2, MonsterMoveId::SPHERIC_GUARDIAN_ACTIVATE);
    expect("SphericGuardian", 3, MonsterMoveId::SPHERIC_GUARDIAN_HARDEN);
    expect("SphericGuardian", 4, MonsterMoveId::SPHERIC_GUARDIAN_ATTACK_DEBUFF);
    expect("SpireShield", 1, MonsterMoveId::SPIRE_SHIELD_BASH);
    expect("SpireShield", 2, MonsterMoveId::SPIRE_SHIELD_FORTIFY);
    expect("SpireShield", 3, MonsterMoveId::SPIRE_SHIELD_SMASH);
    expect("SpireSpear", 1, MonsterMoveId::SPIRE_SPEAR_BURN_STRIKE);
    expect("SpireSpear", 2, MonsterMoveId::SPIRE_SPEAR_PIERCER);
    expect("SpireSpear", 3, MonsterMoveId::SPIRE_SPEAR_SKEWER);
    expect("Champ", 1, MonsterMoveId::THE_CHAMP_HEAVY_SLASH);
    expect("Champ", 2, MonsterMoveId::THE_CHAMP_DEFENSIVE_STANCE);
    expect("Champ", 3, MonsterMoveId::THE_CHAMP_EXECUTE);
    expect("Champ", 4, MonsterMoveId::THE_CHAMP_FACE_SLAP);
    expect("Champ", 5, MonsterMoveId::THE_CHAMP_GLOAT);
    expect("Champ", 6, MonsterMoveId::THE_CHAMP_TAUNT);
    expect("Champ", 7, MonsterMoveId::THE_CHAMP_ANGER);
    expect("TheCollector", 1, MonsterMoveId::THE_COLLECTOR_SPAWN);
    expect("TheCollector", 2, MonsterMoveId::THE_COLLECTOR_FIREBALL);
    expect("TheCollector", 3, MonsterMoveId::THE_COLLECTOR_BUFF);
    expect("TheCollector", 4, MonsterMoveId::THE_COLLECTOR_MEGA_DEBUFF);
    expect("TheCollector", 5, MonsterMoveId::THE_COLLECTOR_SPAWN);
    expect("Maw", 2, MonsterMoveId::THE_MAW_ROAR);
    expect("Maw", 3, MonsterMoveId::THE_MAW_SLAM);
    expect("Maw", 4, MonsterMoveId::THE_MAW_DROOL);
    expect("Maw", 5, MonsterMoveId::THE_MAW_NOM);
    expect("TorchHead", 1, MonsterMoveId::TORCH_HEAD_TACKLE);
    expect("BanditLeader", 1, MonsterMoveId::ROMEO_CROSS_SLASH);
    expect("BanditLeader", 2, MonsterMoveId::ROMEO_MOCK);
    expect("BanditLeader", 3, MonsterMoveId::ROMEO_AGONIZING_SLASH);
    expect("BanditBear", 1, MonsterMoveId::BEAR_MAUL);
    expect("BanditBear", 2, MonsterMoveId::BEAR_BEAR_HUG);
    expect("BanditBear", 3, MonsterMoveId::BEAR_LUNGE);
    expect("Pointy", 1, MonsterMoveId::POINTY_ATTACK);
    if (monsterMove("JawWorm", 4) || monsterMove("Hexaghost", 7)
        || monsterMove("BookOfStabbing", 3) || monsterMove("Donu", 1))
        throw std::runtime_error("invalid or unqualified monster move was accepted");
}

void verifyEncounterManifestAndNativeSweep() {
    const auto &manifest = one_combat::advisor::live_silver::encounterSupportManifest();
    const auto &exclusions = one_combat::advisor::live_silver::encounterExclusionManifest();
    if (exclusions.size() != 1 || std::string(exclusions[0].encounterName) != "FOUR_BYRDS"
        || std::string(exclusions[0].reason).empty())
        throw std::runtime_error("non-native encounter exclusion manifest is incomplete");
    const auto expectedCount = sizeof(monsterEncounterEnumNames)
        / sizeof(monsterEncounterEnumNames[0]);
    if (manifest.size() != expectedCount)
        throw std::runtime_error("encounter manifest does not cover every native enum value");
    std::set<int> seen;
    int supported = 0, excluded = 0;
    SilverSearchConfig sweepConfig;
    sweepConfig.simulationsPerDecision = 1;
    sweepConfig.adaptiveEnabled = false;
    sweepConfig.exactVisitLockEnabled = false;
    sweepConfig.rhoRacingEnabled = false;
    for (const auto &entry : manifest) {
        const int value = static_cast<int>(entry.encounter);
        if (!seen.insert(value).second || value < 0 || value >= static_cast<int>(expectedCount))
            throw std::runtime_error("encounter manifest has duplicate or invalid value");
        if (std::string(entry.enumName) != monsterEncounterEnumNames[value]
            || !entry.reason || std::string(entry.reason).empty())
            throw std::runtime_error("encounter manifest entry is not self-describing");
        if (!entry.supported) {
            ++excluded;
            continue;
        }
        ++supported;
        if (entry.encounter == MonsterEncounter::INVALID)
            throw std::runtime_error("INVALID cannot be marked live-supported");

        // This is a native state-construction sweep, not a policy benchmark:
        // every declared live encounter must at least construct its physical
        // monster slots and cross the ordinary Silver conversion boundary.
        GameContext game(CharacterClass::IRONCLAD, 0x51L + value, 0);
        game.act = value <= static_cast<int>(MonsterEncounter::HEXAGHOST) ? 1
            : value <= static_cast<int>(MonsterEncounter::CHAMP) ? 2
            : value <= static_cast<int>(MonsterEncounter::DONU_AND_DECA) ? 3
            : 4;
        game.floorNum = 1;
        BattleContext battle;
        battle.init(game, entry.encounter);
        if (battle.monsters.monsterCount <= 0 || battle.monsters.monsterCount > 5)
            throw std::runtime_error("native encounter did not construct bounded monster slots: "
                + std::string(entry.enumName));
        for (int i = 0; i < battle.monsters.monsterCount; ++i) {
            const auto &monster = battle.monsters.arr[i];
            if (monster.idx != -1 && monster.idx != i)
                throw std::runtime_error("native encounter changed initial slot identity: "
                    + std::string(entry.enumName));
        }
        CombatKnowledgeState knowledge;
        knowledge.initializeFromLiveBattle(battle);
        const auto wire = makeSilverBattleStateWire(
            battle, knowledge, makeSilverRunContext(game), 0x510000ULL + value);
        if (!wire.valid || wire.encounter != value
            || wire.outcome != static_cast<int>(Outcome::UNDECIDED)
            || wire.inputState != static_cast<int>(InputState::PLAYER_NORMAL))
            throw std::runtime_error("native encounter failed Silver wire conversion: "
                + std::string(entry.enumName));
        auto normalized = wire;
        normalizeFirstObservationIdentity(normalized);
        // The simulator's JAW_WORM_HORDE fixture can retain a stale previous
        // move byte in the fresh reserved array.  A Java first observation has
        // no previous move at this boundary, so model the public state as an
        // absent history entry rather than inventing an impossible Jaw Worm
        // byte.
        if (entry.encounter == MonsterEncounter::JAW_WORM_HORDE) {
            for (int i = 0; i < normalized.monsterCount; ++i)
                if (normalized.monsters[i].idx >= 0)
                    normalized.monsters[i].moveHistory[1] = static_cast<std::int16_t>(MonsterMoveId::INVALID);
        }
        const auto rendered = nativeObservation(normalized, "MONSTER", entry.enumName);
        one_combat::advisor::SilverImportContext context;
        context.session = "native-sweep";
        const auto imported = one_combat::advisor::importSilverRoot(rendered, context);
        if (!imported.ok) {
            throw std::runtime_error("native encounter observation was not importable: "
                + std::string(entry.enumName) + " reason=" + imported.reason
                + " nativeCount=" + std::to_string(normalized.monsterCount)
                + " renderedCount=" + std::to_string(rendered["silverRoot"]["combat"]["monsters"].size())
                + " slots=" + rendered["silverRoot"]["combat"]["monsters"].dump());
        }
        assertAbsentLimboAndStasisLayout(imported.wire, entry.enumName);
        auto canonical = normalized;
        canonical.isolatedSearchSeed = imported.wire.isolatedSearchSeed;
        if (!convertedStatesEqualForSearch(canonical, imported.wire)) {
            throw std::runtime_error("native encounter observation lost search state: "
                + std::string(entry.enumName) + " canonical="
                + battleStateWireEnvelope(canonical).dump()
                + " imported=" + battleStateWireEnvelope(imported.wire).dump());
        }
        const auto decision = runSilverDecision(imported.wire, sweepConfig);
        if (!decision.accepted)
            throw std::runtime_error("native encounter could not reach a Silver decision: "
                + std::string(entry.enumName));
    }
    if (static_cast<int>(seen.size()) != static_cast<int>(expectedCount)
        || supported + excluded != static_cast<int>(expectedCount)
        || excluded != 1)
        throw std::runtime_error("encounter manifest counts are inconsistent");
    std::cout << "live Silver encounter manifest/native sweep passed: supported="
              << supported << " excluded=" << excluded << '\n';
}
// Java has no miscBits: a thief's stolen gold (Looter/Mugger stolenGold, native
// miscInfo) must set the native stolen-gold check bit on import
// (STS_IMPORTER_THIEF_GOLD_FIX, default on; =0 restores the legacy importer).
void verifyThiefStolenGoldFlag() {
    GameContext game(CharacterClass::IRONCLAD, 0x51L + static_cast<int>(MonsterEncounter::TWO_THIEVES), 0);
    game.act = 2;
    game.floorNum = 1;
    BattleContext battle;
    battle.init(game, MonsterEncounter::TWO_THIEVES);
    CombatKnowledgeState knowledge;
    knowledge.initializeFromLiveBattle(battle);
    auto wire = makeSilverBattleStateWire(battle, knowledge, makeSilverRunContext(game), 0x51A000ULL);
    if (!wire.valid) throw std::runtime_error("thief fixture conversion failed");
    normalizeFirstObservationIdentity(wire);
    int mugger = -1;
    for (int i = 0; i < wire.monsterCount; ++i)
        if (static_cast<MonsterId>(wire.monsters[i].id) == MonsterId::MUGGER) mugger = i;
    if (mugger < 0 || wire.miscBits != 0) throw std::runtime_error("thief fixture has no fresh Mugger");
    for (const int stolen : {0, 15}) {
        auto stateWire = wire;
        stateWire.monsters[mugger].miscInfo = stolen;
        auto rendered = nativeObservation(stateWire, "MONSTER", "thief-stolen-gold");
        rendered["silverRoot"]["combat"].erase("miscBits");
        for (const char *flag : {"1", "0"}) {
            setenv("STS_IMPORTER_THIEF_GOLD_FIX", flag, 1);
            one_combat::advisor::SilverImportContext context;
            context.session = "thief-stolen-gold";
            const auto imported = one_combat::advisor::importSilverRoot(rendered, context);
            if (!imported.ok) throw std::runtime_error("thief import failed: " + imported.reason);
            auto expected = stateWire;
            expected.isolatedSearchSeed = imported.wire.isolatedSearchSeed;
            if (stolen > 0 && std::string(flag) == "1") expected.miscBits |= 1U;
            if (!convertedStatesEqualForSearch(expected, imported.wire))
                throw std::runtime_error("thief stolen-gold flag parity failed, stolen="
                    + std::to_string(stolen) + " flag=" + flag + " miscBits="
                    + std::to_string(imported.wire.miscBits));
        }
    }
    unsetenv("STS_IMPORTER_THIEF_GOLD_FIX");
    std::cout << "live Silver thief stolen-gold flag passed\n";
}
json genericObservation(const Fixture &fixture, const char *instance) {
    auto out = fixture.observation;
    out["sequence"] = 1;
    auto &root = out["silverRoot"];
    root["schemaVersion"] = 4;
    root.erase("decisionOrdinal");
    root.erase("firstDecision");
    root["decisionInTurn"] = fixture.wire.player.cardsPlayedThisTurn;
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
    setProducerV4CardObservation(out, fixture.wire);
    return out;
}
json producerQueueJson(const CardQueueItemWire &queue) {
    json out = { {"card", nullptr},
        {"target", queue.target}, {"energyOnUse", queue.energyOnUse},
        {"isEndTurn", queue.isEndTurn}, {"triggerOnUse", queue.triggerOnUse},
        {"ignoreEnergyTotal", queue.ignoreEnergyTotal},
        {"freeToPlay", queue.freeToPlay}, {"randomTarget", queue.randomTarget},
        {"autoplay", queue.autoplay}, {"regretCardCount", queue.regretCardCount},
        {"purgeOnUse", queue.purgeOnUse}, {"exhaustOnUse", queue.exhaustOnUse} };
    if (queue.card.id != static_cast<std::int16_t>(CardId::INVALID))
        out["card"] = cardJson(queue.card);
    return out;
}
json producerCleanupJson(const json &queue) {
    return json{{"kind","USE_CARD"},{"uuid",queue.at("card").at("uuid")},
        {"actionClass","com.megacrit.cardcrawl.actions.utility.UseCardAction"},
        {"unstarted",true},{"returnToHand",false},{"reboundCard",false},{"triggerOnUse",true},
        {"exhaustOnUse",queue.at("exhaustOnUse")},{"purgeOnUse",queue.at("purgeOnUse")},{"autoplay",queue.at("autoplay")}};
}
void setProducerV4CardObservation(json &observationJson, const BattleStateWire &wire) {
    auto &root = observationJson["silverRoot"];
    auto &combat = root["combat"];
    root["decisionInTurn"] = wire.player.cardsPlayedThisTurn;
    combat["cardsPlayedThisTurn"] = wire.player.cardsPlayedThisTurn;
    combat["attacksPlayedThisTurn"] = wire.player.attacksPlayedThisTurn;
    combat["skillsPlayedThisTurn"] = wire.player.skillsPlayedThisTurn;
    combat["lastTargetedMonster"] = wire.player.lastTargetedMonster;
    combat["curCardQueueItem"] = producerQueueJson(wire.curCardQueueItem);
    if (wire.curCardQueueItem.card.id == static_cast<std::int16_t>(CardId::INVALID)) {
        combat["lastCard"] = nullptr;
        return;
    }
    json played = cardJson(wire.curCardQueueItem.card);
    combat["playedThisTurn"] = json::array({played});
    combat["lastCard"] = played;
    combat["lastCard"]["target"] = wire.curCardQueueItem.target;
    combat["lastCard"]["energyOnUse"] = wire.curCardQueueItem.energyOnUse;
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
void verifyGuardianProducerThresholds() {
    // Values are shaped by the verified Java fields, not copied from wire miscInfo.
    for (int ascension : {0, 9, 19, 20}) for (int phase = 0; phase < 3; ++phase) {
        // Keep the existing starter-card fixture and vary only Guardian's
        // ascension rules; native curse costs are not Java card projections.
        GameContext game(CharacterClass::IRONCLAD, 0, 0);
        game.ascension = ascension;
        game.floorNum = 16;
        BattleContext battle;
        battle.init(game, MonsterEncounter::THE_GUARDIAN);
        auto &guardian = battle.monsters.arr[0];
        const bool javaOpen = phase != 1;
        const int initialThreshold = ascension >= 19 ? 40 : ascension >= 9 ? 35 : 30;
        const int javaThreshold = initialThreshold + (phase == 0 ? 0 : 10);
        guardian.miscInfo = initialThreshold + (phase == 2 ? 10 : 0);
        if (phase == 0) guardian.setStatus<MonsterStatus::MODE_SHIFT>(12);
        else if (phase == 1) {
            guardian.removeStatus<MonsterStatus::MODE_SHIFT>();
            guardian.buff<MonsterStatus::SHARP_HIDE>(ascension >= 19 ? 4 : 3);
            guardian.setMove(MonsterMoveId::THE_GUARDIAN_ROLL_ATTACK);
        } else {
            guardian.setStatus<MonsterStatus::MODE_SHIFT>(initialThreshold + 10);
            guardian.setMove(MonsterMoveId::THE_GUARDIAN_WHIRLWIND);
        }
        CombatKnowledgeState knowledge;
        knowledge.initializeFromLiveBattle(battle);
        auto expected = makeSilverBattleStateWire(battle, knowledge, makeSilverRunContext(game), 1);
        normalizeFirstObservationIdentity(expected);
        auto observation = nativeObservation(expected, "MONSTER", "THE_GUARDIAN");
        observation["silverRoot"]["combat"]["monsters"][0]["miscInfo"] =
            javaThreshold - (javaOpen ? 0 : 10);
        one_combat::advisor::SilverImportContext context;
        context.session = "guardian-producer";
        const auto imported = one_combat::advisor::importSilverRoot(observation, context);
        if (!imported.ok) throw std::runtime_error("Guardian producer import: A"
            + std::to_string(ascension) + " phase=" + std::to_string(phase) + ": " + imported.reason);
        expected.isolatedSearchSeed = imported.wire.isolatedSearchSeed;
        if (!convertedStatesEqualForSearch(expected, imported.wire))
            throw std::runtime_error("Guardian producer threshold lost phase parity");
    }
}

int main(int argc, char **argv) {
    verifyGuardianProducerThresholds();
    try {
        {
            // Overlay labels name the card a selection picks.
            using namespace silver_bridge;
            BattleStateWire state;
            SemanticAction select;
            select.type = SemanticActionType::SINGLE_CARD_SELECT;
            select.source = CardSource::HAND;
            select.card.id = static_cast<std::int16_t>(sts::CardId::STRIKE_RED);
            select.card.upgraded = true;
            SemanticAction multi;
            multi.type = SemanticActionType::MULTI_CARD_SELECT;
            multi.selectedCards = {select.card, select.card};
            multi.selectedCards[1].id = static_cast<std::int16_t>(sts::CardId::BASH);
            multi.selectedCards[1].upgraded = false;
            const auto single = one_combat::advisor::silverActionLabel(select, state);
            const auto many = one_combat::advisor::silverActionLabel(multi, state);
            if (single != "Select Strike+" || many != "Select Strike+, Bash")
                throw std::runtime_error("card-select labels: " + single + " / " + many);
        }
        {
            const std::string path = argc > 2 ? argv[2] : "tests/fixtures/live_guardian_a20_phases.json";
            std::ifstream input(path);
            if (!input) throw std::runtime_error("cannot read captured Guardian phases: " + path);
            json fixture; input >> fixture;
            if (fixture.at("schema") != "live_guardian_a20_phases_v1" || fixture.at("phases").size() != 3)
                throw std::runtime_error("captured Guardian phase fixture schema");
            int previousSequence = -1;
            for (const auto &phase : fixture.at("phases")) {
                auto observation = phase.at("observation");
                const auto &source = phase.at("source");
                for (const auto *key : {"session", "sequence", "observationHash"})
                    observation[key] = source.at(key);
                if (source.at("sequence").get<int>() <= previousSequence)
                    throw std::runtime_error("captured Guardian phase order");
                previousSequence = source.at("sequence").get<int>();
                one_combat::advisor::SilverImportContext context;
                const auto imported = one_combat::advisor::importSilverRoot(observation, context);
                if (!imported.ok) throw std::runtime_error("captured Guardian import: " + imported.reason);
                const auto &expected = phase.at("expected");
                const auto battle = battleContextFromWire(imported.wire);
                const auto &guardian = battle.monsters.arr[0];
                if (imported.wire.ascension != 20 || battle.turn + 1 != expected.at("turn")
                    || guardian.id != MonsterId::THE_GUARDIAN || guardian.curHp != expected.at("guardianHp")
                    || guardian.curHp != phase.at("mcpGuardian").at("current_hp")
                    || guardian.miscInfo != expected.at("miscInfo")
                    || guardian.getStatus<MonsterStatus::MODE_SHIFT>() != expected.at("modeShift")
                    || guardian.getStatus<MonsterStatus::SHARP_HIDE>() != expected.at("sharpHide"))
                    throw std::runtime_error("captured Guardian threshold/power parity");
                SilverSearchSession session;
                const auto decision = session.decide(imported.wire, 1);
                if (!decision.accepted || one_combat::advisor::selectedLiveAction(
                        decision.action, context, observation).is_null())
                    throw std::runtime_error("captured Guardian search/lowering refused");
            }
            std::cout << "captured A20 Guardian offense/defense/return search parity passed\n";
        }
        {
            const std::string path=argc>1?argv[1]:"tests/fixtures/live_slime_boss_split.json";
            std::ifstream input(path);
            if(!input)throw std::runtime_error("cannot read captured Slime Boss fixture: "+path);
            json observation; input >> observation;
            one_combat::advisor::SilverImportContext context;
            const auto imported=one_combat::advisor::importSilverRoot(observation,context);
            if(!imported.ok)throw std::runtime_error("captured Slime Boss split import: "+imported.reason);
            SilverSearchSession session;
            const auto decision=session.decide(imported.wire,1000);
            if(!decision.accepted)throw std::runtime_error("captured Slime Boss split search: "+decision.failureReason);
            for(const auto &action:decision.legalActions) {
                const auto live=one_combat::advisor::selectedLiveAction(action,context,observation);
                if(live.is_null() || (action.target>=0 && live.value("targetIndex",-1)!=(action.target==0?1:2)))
                    throw std::runtime_error("captured Slime Boss sparse target lowering failed");
            }
            auto targeted=decision.action;
            targeted.type=silver_bridge::SemanticActionType::CARD;
            targeted.card.uniqueId=imported.wire.hand.back().uniqueId;
            targeted.target=2;
            for(bool potion:{false,true}) {
                targeted.type=potion?silver_bridge::SemanticActionType::POTION:silver_bridge::SemanticActionType::CARD;
                targeted.potionSlot=0;targeted.discardPotion=false;
                auto reordered=observation;
                auto &monsters=reordered["silverRoot"]["combat"]["monsters"];
                std::swap(monsters[0],monsters[1]);
                if(one_combat::advisor::selectedLiveAction(targeted,context,reordered).value("targetIndex",-1)!=1)
                    throw std::runtime_error("sparse reordered target did not follow MCP list order");
                monsters[0]["dead"]=true;
                if(!one_combat::advisor::selectedLiveAction(targeted,context,reordered).is_null())
                    throw std::runtime_error("dead sparse target was lowered");
                for(int target:{1,4}) {
                    targeted.target=target;
                    if(!one_combat::advisor::selectedLiveAction(targeted,context,observation).is_null())
                        throw std::runtime_error("missing sparse target was lowered");
                }
                targeted.target=2;
                monsters[0]["dead"]=false;monsters[1]["slot"]=2;monsters[1]["idx"]=2;
                if(!one_combat::advisor::selectedLiveAction(targeted,context,reordered).is_null())
                    throw std::runtime_error("duplicate sparse slot was lowered");
            }
            std::cout << "captured Slime Boss split search and target lowering passed\n";
        }
        {
            GameContext game(CharacterClass::IRONCLAD, 0x71517u, 0);
            game.act = 1;
            game.floorNum = 1;
            BattleContext live;
            live.init(game, MonsterEncounter::CULTIST);
            CombatKnowledgeState knowledge;
            knowledge.initializeFromLiveBattle(live);
            live.potions[0] = Potion::GAMBLERS_BREW;
            live.potionCount = 1;
            sts::search::Action(sts::search::ActionType::POTION, 0, 0).execute(live);
            if (live.inputState != InputState::CARD_SELECT
                || live.cardSelectInfo.cardSelectTask != CardSelectTask::GAMBLE
                || live.actionQueue.size != 0 || live.cardQueue.size != 0)
                throw std::runtime_error("live Gambler's Brew did not settle at quiescent selection");
            auto wire = makeSilverBattleStateWire(live, knowledge,
                makeSilverRunContext(game), 0x71517u);
            if (!wire.valid || !wire.historicalQueueItemAtSource
                || battleContextFromWire(wire).actionQueue.size != 0)
                throw std::runtime_error("quiescent live GAMBLE lost queue-item provenance");
            // A selection interrupting a card play: the playing card is in no
            // pile and its OnAfterCardUsed is queued. The search root restores it.
            live.cardSelectInfo.cardSelectTask = CardSelectTask::HEADBUTT;
            live.curCardQueueItem.card = CardInstance(CardId::HEADBUTT);
            live.curCardQueueItem.card.uniqueId = 999;
            live.actionQueue.pushBack(Actions::OnAfterCardUsed());
            wire = makeSilverBattleStateWire(live, knowledge,
                makeSilverRunContext(game), 0x71517u);
            if (!wire.valid || wire.historicalQueueItemAtSource
                || battleContextFromWire(wire).actionQueue.size != 1)
                throw std::runtime_error("pending live Headbutt lost its OnAfterCardUsed in the search root");
            live.actionQueue.clear();
            wire = makeSilverBattleStateWire(live, knowledge,
                makeSilverRunContext(game), 0x71517u);
            if (!wire.valid || !wire.historicalQueueItemAtSource)
                throw std::runtime_error("settled live selection did not preserve provenance");
            const auto serialized = json(wire).get<BattleStateWire>();
            if (serialized.historicalQueueItemAtSource)
                throw std::runtime_error("legacy JSON manufactured queue-item provenance");
        }
        verifyRuntimeMoveBoundary();
        verifyEncounterManifestAndNativeSweep();
        verifyThiefStolenGoldFlag();
        verifyDynamicTransitionCorpus();
        const std::vector<Fixture> fixtures = {
            fixture(MonsterEncounter::CULTIST, "Cultist", 3, "MONSTER", 0xC011u),
            fixture(MonsterEncounter::JAW_WORM, "JawWorm", 1, "MONSTER", 0xA01u),
            fixture(MonsterEncounter::GREMLIN_NOB, "Gremlin Nob", 3, "ELITE", 0xB003u)};
        for (const auto &[id, upgraded, misc, damage] : std::vector<std::tuple<CardId, bool, int, int>>{
                {CardId::SEARING_BLOW, false, 0, 12}, {CardId::SEARING_BLOW, true, 1, 16},
                {CardId::SEARING_BLOW, true, 2, 21}, {CardId::SEARING_BLOW, true, 4, 34},
                {CardId::RAMPAGE, false, 0, 8}, {CardId::RAMPAGE, false, 5, 13},
                {CardId::RAMPAGE, true, 16, 24}, {CardId::RITUAL_DAGGER, true, 27, 27}}) {
            auto observation = genericObservation(fixtures[0], "combat-card-growth");
            auto &combat = observation["silverRoot"]["combat"];
            auto &card = combat["hand"][0];
            card["id"] = cardStringIds[static_cast<int>(id)];
            card["upgraded"] = upgraded; card["misc"] = misc;
            card["cost"] = card["costForTurn"] = id == CardId::SEARING_BLOW ? 2 : 1;
            combat.erase("strikeCount");
            one_combat::advisor::SilverImportContext context;
            const auto imported = one_combat::advisor::importSilverRoot(observation, context);
            if (!imported.ok) throw std::runtime_error("combat card growth import: " + imported.reason);
            auto battle = battleContextFromWire(imported.wire);
            const auto physicalId = battle.cards.hand[0].uniqueId;
            const auto hp = battle.monsters.arr[0].curHp;
            sts::search::Action(sts::search::ActionType::CARD, 0, 0).execute(battle);
            if (hp - battle.monsters.arr[0].curHp != damage)
                throw std::runtime_error("combat card growth damage was not preserved");
            if (id == CardId::RAMPAGE) {
                const auto played = std::find_if(battle.cards.discardPile.begin(), battle.cards.discardPile.end(),
                    [physicalId](const auto &c) { return c.uniqueId == physicalId; });
                if (played == battle.cards.discardPile.end() || played->specialData != misc + (upgraded ? 8 : 5))
                    throw std::runtime_error("imported Rampage lost its next growth increment");
            }
        }
        {
            const auto domeObservation=[&](int which,int completed) {
                auto obs=genericObservation(fixtures[which],which==0?"dome-cultist":"dome-jaw");
                auto &root=obs["silverRoot"]; auto &combat=root["combat"];
                root["playerTurn"]=completed+1; combat["turn"]=completed+1; combat["runicDome"]=true;
                combat["relics"].push_back({{"id","Runic Dome"},{"counter",0},{"usedUp",false}});
                auto &monster=combat["monsters"][0];
                monster.erase("nextMove");monster.erase("moveHistory");
                monster["hp"]=monster["maxHp"].get<int>()-3; // damage after the roll
                json moves=json::array();
                if(completed>0) moves.push_back(which==0?3:1);
                if(completed>1) moves.push_back(which==0?1:2);
                combat["runicDomeKnowledge"]={{"schemaVersion",1},{"epoch",1},{"generation",2*completed+1},
                    {"complete",true},{"monsterId",which==0?"Cultist":"JawWorm"},{"slot",0},
                    {"completedTurns",completed},{"executedMoves",moves},{"pendingMoveRolls",1},
                    {"rollHp",monster["maxHp"]},{"rollMaxHp",monster["maxHp"]}};
                return obs;
            };
            for(int which=0;which<2;++which) for(int completed=0;completed<3;++completed) {
                auto obs=domeObservation(which,completed);
                const auto imported=one_combat::advisor::importSilverRoot(obs);
                if(!imported.ok) throw std::runtime_error("bounded Dome import: "+imported.reason);
                auto root=battleContextFromWire(imported.wire);
                if(!root.intentsHidden || root.monsters.arr[0].pendingMoveRolls!=1
                        || root.monsters.arr[0].pendingRollInputs.curHp!=root.monsters.arr[0].maxHp
                        || root.monsters.arr[0].curHp==root.monsters.arr[0].pendingRollInputs.curHp)
                    throw std::runtime_error("Dome lost deferred roll-time public state");
                auto reference=root;
                reference.monsters.arr[0].pendingMoveRolls=0;
                reference.monsters.arr[0].rollMoveFromInputs(reference,root.monsters.arr[0].pendingRollInputs);
                root.monsters.arr[0].materializePendingMove(root);
                if(!std::equal(std::begin(root.monsters.arr[0].moveHistory),std::end(root.monsters.arr[0].moveHistory),
                               std::begin(reference.monsters.arr[0].moveHistory))
                        || root.aiRng!=reference.aiRng)
                    throw std::runtime_error("Dome deferred materialization differs from native public-input transition");
                if(completed==0 && root.monsters.arr[0].moveHistory[0]
                        !=(which==0?MonsterMoveId::CULTIST_INCANTATION:MonsterMoveId::JAW_WORM_CHOMP))
                    throw std::runtime_error("Dome initial public rule differs from vanilla");
                const auto legal=enumerateSilverLegalActions(imported.wire);
                if(legal.empty()) throw std::runtime_error("Dome imported root has no legal actions");
            }
            // Producer schema v2: original physical slots survive a teammate
            // death, while each living monster keeps its own roll-time state.
            const auto groupDome=[&](const std::vector<std::string> &ids,const std::vector<std::vector<int>> &history) {
                const int completed=history[0].size();
                auto obs=domeObservation(1,0);auto &c=obs["silverRoot"]["combat"];
                obs["silverRoot"]["playerTurn"]=completed+1;c["turn"]=completed+1;
                obs["silverRoot"]["encounter"]="EXORDIUM_WILDLIFE";
                json monsters=json::array(), rows=json::array();
                for(std::size_t i=0;i<ids.size();++i) {
                    auto m=c["monsters"][0];m["id"]=ids[i];m["slot"]=i;m["idx"]=i;m["hp"]=28;m["maxHp"]=40;
                    monsters.push_back(m);
                    rows.push_back({{"schemaVersion",1},{"epoch",1},{"generation",2*completed+1},
                        {"complete",true},{"monsterId",ids[i]},{"slot",i},{"completedTurns",completed},
                        {"executedMoves",history[i]},{"pendingMoveRolls",1},{"rollHp",30},{"rollMaxHp",40},
                        {"publicMisc",ids[i]=="SlaverRed" && completed==2?1:0},{"firstHp",35},
                        {"firstMaxHp",40},{"firstAlive",true},{"aliveCount",ids.size()},{"pendingAttackPredicates",json::array()}});
                }
                c["monsters"]=monsters;
                c["runicDomeKnowledge"]={{"schemaVersion",2},{"epoch",1},{"complete",true},{"monsters",rows}};
                return obs;
            };
            // Bound public occupants: every remaining family enters before its first hidden roll.
            const auto boundDome=[&](const std::string &id) {
                auto obs=groupDome({id},{{}});auto &knowledge=obs["silverRoot"]["combat"]["runicDomeKnowledge"];
                knowledge["schemaVersion"]=3;auto &row=knowledge["monsters"][0];
                row.update({{"schemaVersion",4},{"historySchemaVersion",3},{"occupantGeneration",1},
                    {"birthGlobalTurn",0},{"birthKind","initial"},{"birthParentSlot",-1},{"birthParentGeneration",0},
                    {"lastExecutionGlobalTurn",-1},{"rollGlobalTurn",0},{"totalRolls",1},{"knownTransitions",0},
                    {"knownNextMove",nullptr},{"knownRollPredecessor",nullptr}});
                const auto nativeId=one_combat::advisor::live_silver::monsterId(id);
                const auto prior=Monster::latentDamagePrior(*nativeId,0);
                if(id=="TorchHead")row.update({{"generation",2},{"knownTransitions",1},{"knownRollPredecessor","torch_constructor_tackle"}});
                if(prior){row["latentDamageExecutions"]=0;row["latentDamageMask"]=prior;row["latentDamageObservations"]=json::array();}
                return obs;
            };
            for(const std::string id:{"AcidSlime_L","SpikeSlime_L","SlimeBoss","BronzeAutomaton","BronzeOrb","GremlinLeader",
                    "Reptomancer","Dagger","TheCollector","TorchHead","FuzzyLouseNormal","FuzzyLouseDefensive","Darkling"}) {
                auto obs=boundDome(id);const auto imported=one_combat::advisor::importSilverRoot(obs);
                if(!imported.ok)throw std::runtime_error("remaining Dome initial "+id+": "+imported.reason);
                auto state=battleContextFromWire(imported.wire);auto expectedRng=state.aiRng;expectedRng.random(99);state.monsters.arr[0].materializePendingMove(state);
                if(id=="TorchHead" && (state.monsters.arr[0].moveHistory[0]!=MonsterMoveId::TORCH_HEAD_TACKLE || state.monsters.arr[0].moveHistory[1]!=MonsterMoveId::TORCH_HEAD_TACKLE || state.aiRng!=expectedRng))throw std::runtime_error("Torch constructor then initial roll parity");
                if(id=="TorchHead") {
                    const auto turnRng=state.aiRng;state.monsters.arr[0].takeTurn(state);
                    while(!state.actionQueue.isEmpty()){auto action=state.actionQueue.popFront();action(state);}
                    if(state.aiRng!=turnRng || state.monsters.arr[0].moveHistory[0]!=MonsterMoveId::TORCH_HEAD_TACKLE || state.monsters.arr[0].moveHistory[1]!=MonsterMoveId::TORCH_HEAD_TACKLE)
                        throw std::runtime_error("Torch queued turn setter or zero-roll parity");
                    auto invalidTorch=obs;invalidTorch["silverRoot"]["combat"]["runicDomeKnowledge"]["monsters"][0]["knownRollPredecessor"]=nullptr;
                    if(one_combat::advisor::importSilverRoot(invalidTorch).ok)throw std::runtime_error("Torch missing constructor proof accepted");
                }
                if(state.monsters.arr[0].occupantGeneration!=1 || state.monsters.arr[0].pendingMoveRolls)
                    throw std::runtime_error("remaining Dome occupant materialization "+id);
                auto invalid=obs;invalid["silverRoot"]["combat"]["runicDomeKnowledge"]["monsters"][0].erase("occupantGeneration");
                if(one_combat::advisor::importSilverRoot(invalid).ok)throw std::runtime_error("missing occupant generation accepted");
            }
            for(int level:{0,9,19}) {
                auto state=battleContextFromWire(one_combat::advisor::importSilverRoot(boundDome("TorchHead")).wire);
                auto actual=state.monsterHpRng,expected=actual;
                expected.random(38,40);const int hp=expected.random(level>=9?40:38,level>=9?45:40);
                Monster torch;torch.id=MonsterId::TORCH_HEAD;torch.initHp(actual,level);
                if(actual!=expected || torch.curHp!=hp || torch.maxHp!=hp)throw std::runtime_error("Torch fixed first HP draw/final ascension range parity");
            }
            for(int level:{0,19})for(int completed=1;completed<=20;++completed) {
                auto obs=boundDome("BronzeAutomaton");auto &c=obs["silverRoot"]["combat"];auto &row=c["runicDomeKnowledge"]["monsters"][0];
                obs["silverRoot"]["ascension"]=level;obs["silverRoot"]["playerTurn"]=completed+1;c["turn"]=completed+1;
                const auto move=[&](int i){const int cycle[]={1,5,1,5,2,level>=19?5:3};return i==0?4:cycle[(i-1)%6];};
                json history=json::array();for(int i=std::max(0,completed-2);i<completed;++i)history.push_back(move(i));
                row.update({{"completedTurns",completed},{"executedMoves",history},{"generation",2*completed+1},
                    {"totalRolls",completed+1},{"lastExecutionGlobalTurn",completed},{"rollGlobalTurn",completed},
                    {"publicMisc",(completed-1)%6==5?0:(completed-1)%6}});
                auto imported=one_combat::advisor::importSilverRoot(obs);
                if(!imported.ok)throw std::runtime_error("Automaton bound cycle: "+imported.reason);
                auto state=battleContextFromWire(imported.wire);auto before=state.aiRng;state.monsters.arr[0].materializePendingMove(state);
                if(state.monsters.arr[0].moveHistory[0]!=*one_combat::advisor::live_silver::monsterMove("BronzeAutomaton",move(completed)) || state.aiRng==before)
                    throw std::runtime_error("Automaton A0/A19 deferred cycle parity");
            }
            {
                auto obs=groupDome({"Darkling","Darkling","Darkling"},{{3},{1},{2}});auto &c=obs["silverRoot"]["combat"];auto &knowledge=c["runicDomeKnowledge"];
                knowledge["schemaVersion"]=3;
                for(int slot=0;slot<3;++slot)knowledge["monsters"][slot].update({{"schemaVersion",4},{"historySchemaVersion",3},
                    {"occupantGeneration",1},{"birthGlobalTurn",0},{"birthKind","initial"},{"birthParentSlot",-1},{"birthParentGeneration",0},
                    {"lastExecutionGlobalTurn",1},{"rollGlobalTurn",1},{"totalRolls",2},{"knownTransitions",0},
                    {"knownNextMove",nullptr},{"knownRollPredecessor",nullptr},{"latentDamageMask",Monster::latentDamagePrior(MonsterId::DARKLING,0)},
                    {"latentDamageExecutions",0},{"latentDamageObservations",json::array()}});
                auto &row=knowledge["monsters"][0];c["monsters"][0]["hp"]=0;c["monsters"][0]["halfDead"]=true;
                row.update({{"generation",5},{"knownTransitions",2},{"pendingMoveRolls",0},
                    {"knownNextMove",{{"kind","darkling_public_regrow"},{"move",4}}},
                    {"knownRollPredecessor","darkling_reincarnate_before_regrow"},{"latentDamageExecutions",1}});
                row["latentDamageObservations"]=json::array({{{"beforeHp",80},{"afterHp",80},{"beforeBlock",100},{"afterBlock",99},
                    {"beforeBuffer",0},{"afterBuffer",0},{"maxHp",80},{"strength",0},{"reviveHp",0},
                    {"weak",false},{"vulnerable",false},{"intangible",true},{"oddMushroom",false},{"paperKrane",false},
                    {"torii",false},{"tungstenRod",false},{"wrath",false}}});
                auto imported=one_combat::advisor::importSilverRoot(obs);
                if(!imported.ok)throw std::runtime_error("Darkling interleaved bridge: "+imported.reason);
                auto state=battleContextFromWire(imported.wire);
                if(state.monsters.arr[0].moveHistory[0]!=MonsterMoveId::DARKLING_REGROW || state.monsters.arr[0].moveHistory[1]!=MonsterMoveId::DARKLING_REINCARNATE)
                    throw std::runtime_error("Darkling public overwritten roll predecessor lost");
                row["latentDamageObservations"]=json::array();
                if(one_combat::advisor::importSilverRoot(obs).ok)throw std::runtime_error("missing public Bite/Nip observation accepted");
            }
            {
                auto obs=boundDome("WrithingMass");auto &row=obs["silverRoot"]["combat"]["runicDomeKnowledge"]["monsters"][0];
                row.erase("knownNextMove");row.erase("knownRollPredecessor");row.erase("knownTransitions");
                row.update({{"historySchemaVersion",2},{"generation",2},{"totalRolls",2},{"pendingMoveRolls",2},{"rollGlobalTurn",1}});
                json inputs={{"rollHp",30},{"rollMaxHp",40},{"firstHp",35},{"firstMaxHp",40},{"firstAlive",true},
                    {"aliveCount",1},{"playerConstricted",false},{"rollGlobalTurn",0}};
                row["pendingRollInputs"]=json::array({inputs,inputs});row["pendingRollInputs"][1]["rollGlobalTurn"]=1;
                auto imported=one_combat::advisor::importSilverRoot(obs);
                if(!imported.ok || imported.wire.monsters[0].pendingRollInputHistory.size()!=2)throw std::runtime_error("bound reactive current-player roll: "+imported.reason);
                row["pendingRollInputs"][1]["rollGlobalTurn"]=2;
                if(one_combat::advisor::importSilverRoot(obs).ok)throw std::runtime_error("future reactive roll accepted");
            }
            {
                auto obs=boundDome("FuzzyLouseNormal");auto &row=obs["silverRoot"]["combat"]["runicDomeKnowledge"]["monsters"][0];
                row["latentDamageMask"]=1<<5;
                if(one_combat::advisor::importSilverRoot(obs).ok)throw std::runtime_error("unobserved latent collapse accepted");
            }
            {
                auto obs=boundDome("Dagger");auto &c=obs["silverRoot"]["combat"];auto &row=c["runicDomeKnowledge"]["monsters"][0];
                obs["silverRoot"]["playerTurn"]=8;c["turn"]=8;
                row.update({{"occupantGeneration",3},{"birthGlobalTurn",7},{"birthKind","summon"},{"birthParentSlot",2},
                    {"birthParentGeneration",1},{"rollGlobalTurn",7}});
                auto imported=one_combat::advisor::importSilverRoot(obs);
                if(!imported.ok || imported.wire.monsters[0].pendingRollInputs.monsterTurnNumber!=7)
                    throw std::runtime_error("newborn global clock: "+imported.reason);
                row["birthGlobalTurn"]=8;
                if(one_combat::advisor::importSilverRoot(obs).ok)throw std::runtime_error("future birth accepted");
            }
            for(const auto &ids:std::vector<std::vector<std::string>>{{"FungiBeast","FungiBeast"},
                    {"SlaverRed","SlaverBlue"},{"AcidSlime_M","SpikeSlime_M"}}) {
                auto obs=groupDome(ids,{{1},{1}});
                auto imported=one_combat::advisor::importSilverRoot(obs);
                if(!imported.ok) throw std::runtime_error("Dome group producer: "+imported.reason);
                auto root=battleContextFromWire(imported.wire),reference=root;
                for(int slot=0;slot<2;++slot) {
                    auto &m=root.monsters.arr[slot];auto &r=reference.monsters.arr[slot];
                    if(m.pendingRollInputs.knightCurHp!=35 || m.pendingRollInputs.aliveCount!=2)
                        throw std::runtime_error("Dome group lost public roll inputs");
                    r.pendingMoveRolls=0;r.rollMoveFromInputs(reference,m.pendingRollInputs);m.materializePendingMove(root);
                    if(!std::equal(std::begin(m.moveHistory),std::end(m.moveHistory),std::begin(r.moveHistory)) || root.aiRng!=reference.aiRng)
                        throw std::runtime_error("Dome group public-input parity");
                }
                obs["silverRoot"]["combat"]["monsters"][0]["hp"]=0;
                obs["silverRoot"]["combat"]["runicDomeKnowledge"]["monsters"][0]["pendingMoveRolls"]=0;
                imported=one_combat::advisor::importSilverRoot(obs);
                if(!imported.ok || imported.wire.monsters[0].pendingMoveRolls || imported.wire.monstersAlive!=1)
                    throw std::runtime_error("Dome original dead slot: "+imported.reason);
            }
            {
                auto obs=groupDome({"SlaverRed"},{{1,2}});
                const auto imported=one_combat::advisor::importSilverRoot(obs);
                if(!imported.ok || imported.wire.monsters[0].miscInfo!=1 || imported.wire.monsters[0].pendingRollInputs.miscInfo!=1)
                    throw std::runtime_error("Dome public Entangle history: "+imported.reason);
            }
            {
                auto obs=groupDome({"GremlinNob"},{{3}});obs["silverRoot"]["encounter"]="GREMLIN_NOB";
                obs["silverRoot"]["roomClass"]="ELITE";
                obs["silverRoot"]["combat"]["monsters"][0]["powers"].push_back({{"id","Anger"},{"amount",2}});
                auto imported=one_combat::advisor::importSilverRoot(obs);
                if(!imported.ok || imported.wire.monsters[0].uniquePower0!=2) throw std::runtime_error("Dome ordinary Nob: "+imported.reason);
                obs["silverRoot"]["encounter"]="COLOSSEUM_EVENT_NOBS";
                if(one_combat::advisor::importSilverRoot(obs).ok) throw std::runtime_error("unaudited Nob constructor variant accepted");
                obs=groupDome({"FungiBeast","FungiBeast"},{{1},{2}});
                obs["silverRoot"]["encounter"]="TWO_FUNGI_BEASTS";
                for(auto &m:obs["silverRoot"]["combat"]["monsters"]) m["powers"].push_back({{"id","Spore Cloud"},{"amount",2}});
                obs["silverRoot"]["combat"]["playerPowers"].push_back({{"id","Vulnerable"},{"amount",2},{"justApplied",false}});
                imported=one_combat::advisor::importSilverRoot(obs);
                if(!imported.ok || imported.wire.monsters[1].uniquePower0!=2) throw std::runtime_error("Dome public Fungi powers: "+imported.reason);
            }
            for(int completed=0;completed<3;++completed) {
                std::vector<std::vector<int>> history(3);
                for(int slot=0;slot<3;++slot) for(int turn=0;turn<completed;++turn) history[slot].push_back((slot+turn)%2==0?3:4);
                auto obs=groupDome({"Sentry","Sentry","Sentry"},history);obs["silverRoot"]["encounter"]="THREE_SENTRIES";
                for(auto &m:obs["silverRoot"]["combat"]["monsters"]) m["powers"].push_back({{"id","Artifact"},{"amount",1}});
                auto imported=one_combat::advisor::importSilverRoot(obs);
                if(!imported.ok) throw std::runtime_error("Dome Sentry public phase: "+imported.reason);
                auto bc=battleContextFromWire(imported.wire);
                for(int slot=0;slot<3;++slot) {
                    bc.monsters.arr[slot].materializePendingMove(bc);
                    const auto expected=(slot+completed)%2==0?MMID::SENTRY_BOLT:MMID::SENTRY_BEAM;
                    if(bc.monsters.arr[slot].moveHistory[0]!=expected) throw std::runtime_error("Sentry public alternation parity");
                }
                if(completed==1) {
                    obs["silverRoot"]["combat"]["runicDomeKnowledge"]["monsters"][1]["executedMoves"]=json::array({3});
                    if(one_combat::advisor::importSilverRoot(obs).ok) throw std::runtime_error("wrong Sentry physical phase accepted");
                }
            }
            {
                auto obs=groupDome({"SpikeSlime_S","AcidSlime_M"},{{1},{1}});obs["silverRoot"]["encounter"]="SMALL_SLIMES";
                const auto imported=one_combat::advisor::importSilverRoot(obs);
                if(!imported.ok) throw std::runtime_error("Dome small Spike slime: "+imported.reason);
                auto bc=battleContextFromWire(imported.wire);bc.monsters.arr[0].materializePendingMove(bc);
                if(bc.monsters.arr[0].moveHistory[0]!=MMID::SPIKE_SLIME_S_TACKLE) throw std::runtime_error("small Spike deferred rule");
                bc.monsters.arr[0].moveHistory[1]=MMID::INVALID;
                bc.monsters.arr[0].takeTurn(bc);
                if(bc.monsters.arr[0].moveHistory[1]!=MMID::SPIKE_SLIME_S_TACKLE) throw std::runtime_error("small Spike repeated public history");
                obs=groupDome({"SlaverRed"},{{1}});
                auto old=obs["silverRoot"]["combat"]["runicDomeKnowledge"]["monsters"][0];old.erase("pendingAttackPredicates");
                old["completedTurns"]=3;old["generation"]=7;old["executedMoves"]=json::array({3,1});
                obs["silverRoot"]["combat"]["runicDomeKnowledge"]=old;obs["silverRoot"]["playerTurn"]=4;obs["silverRoot"]["combat"]["turn"]=4;
                if(one_combat::advisor::importSilverRoot(obs).ok) throw std::runtime_error("legacy Red lost public Entangle accepted");
            }
            // Small Acid Slime: initial hidden roll, then the public direct
            // alternating override (no later RNG draw or queued-intent read).
            for(int asc:{0,17}) for(int opening:{1,2}) {
                if(asc>=17 && opening!=2) continue;
                for(int completed=0;completed<=4;++completed) {
                    std::vector<int> history;
                    for(int t=std::max(0,completed-2);t<completed;++t) history.push_back(t%2==0?opening:3-opening);
                    auto obs=groupDome({"AcidSlime_S"},{history});
                    obs["silverRoot"]["encounter"]="SMALL_SLIMES";
                    obs["silverRoot"]["ascension"]=asc;
                    obs["silverRoot"]["playerTurn"]=completed+1;
                    auto &c=obs["silverRoot"]["combat"];c["turn"]=completed+1;
                    auto &k=c["runicDomeKnowledge"]["monsters"][0];
                    k["completedTurns"]=completed;k["generation"]=2*completed+1;
                    k["pendingMoveRolls"]=completed?0:1;
                    k["knownNextMove"]=completed?json{{"kind","acid_slime_s_alternation"},{"move",completed%2==0?opening:3-opening}}:json(nullptr);
                    const auto imported=one_combat::advisor::importSilverRoot(obs);
                    if(!imported.ok) throw std::runtime_error("Dome small Acid phase: "+imported.reason);
                    auto bc=battleContextFromWire(imported.wire);auto before=bc;
                    auto &m=bc.monsters.arr[0];
                    m.materializePendingMove(bc);
                    if(completed==0) {
                        auto &r=before.monsters.arr[0];auto inputs=r.pendingRollInputs;
                        r.cancelPendingMove();r.rollMoveFromInputs(before,inputs);
                        if(m.moveHistory[0]!=r.moveHistory[0] || bc.aiRng!=before.aiRng)
                            throw std::runtime_error("small Acid initial secondary RNG parity");
                    } else {
                        const auto expected=(completed%2==0?opening:3-opening)==1?MMID::ACID_SLIME_S_TACKLE:MMID::ACID_SLIME_S_LICK;
                        const auto previous=history.back()==1?MMID::ACID_SLIME_S_TACKLE:MMID::ACID_SLIME_S_LICK;
                        if(m.pendingMoveRolls || m.moveHistory[0]!=expected || m.moveHistory[1]!=previous || bc.aiRng!=before.aiRng)
                            throw std::runtime_error("small Acid known move/history RNG parity");
                        m.takeTurn(bc);
                        if(m.moveHistory[0]!=previous || m.moveHistory[1]!=expected || bc.aiRng!=before.aiRng)
                            throw std::runtime_error("small Acid direct alternating turn parity");
                    }
                    const auto rejectAcid=[&](json bad) {
                        if(one_combat::advisor::importSilverRoot(bad).ok) throw std::runtime_error("unproven Acid known intent accepted");
                    };
                    auto bad=obs;bad["silverRoot"]["combat"]["runicDomeKnowledge"]["monsters"][0].erase("knownNextMove");rejectAcid(bad);
                    if(completed) {
                        bad=obs;bad["silverRoot"]["combat"]["runicDomeKnowledge"]["monsters"][0]["knownNextMove"]["move"]=history.back();rejectAcid(bad);
                        bad=obs;bad["silverRoot"]["combat"]["runicDomeKnowledge"]["monsters"][0]["pendingMoveRolls"]=1;rejectAcid(bad);
                        bad=obs;bad["silverRoot"]["combat"]["runicDomeKnowledge"]["monsters"][0]["pendingAttackPredicates"]=json::array({json::array({1,true})});rejectAcid(bad);
                        bad=obs;bad["silverRoot"]["combat"]["runicDomeKnowledge"]["monsters"][0]["knownNextMove"]["kind"]="inferred_private_move";rejectAcid(bad);
                        if(history.size()==2) {
                            bad=obs;bad["silverRoot"]["combat"]["runicDomeKnowledge"]["monsters"][0]["executedMoves"][0]=history.back();rejectAcid(bad);
                        }
                    }
                    // Dead slots carry neither a latent nor a known future move.
                    c["monsters"][0]["hp"]=0;k["pendingMoveRolls"]=0;k["knownNextMove"]=nullptr;
                    const auto dead=one_combat::advisor::importSilverRoot(obs);
                    if(!dead.ok || dead.wire.monsters[0].pendingMoveRolls) throw std::runtime_error("small Acid dead slot: "+dead.reason);
                }
            }
            // Public stun overrides cancel the former hidden roll. Byrd's
            // headbutt directly selects Fly; Shelled's stun instead inserts
            // Fell into history BEFORE another hidden roll.
            for(const std::string id:{"Byrd","Shelled Parasite"}) for(int phase=0;phase<3;++phase) {
                if(id=="Shelled Parasite" && phase==2) continue;
                std::vector<int> history=phase==0?std::vector<int>{}:phase==1?std::vector<int>{4}:std::vector<int>{4,5};
                auto obs=groupDome({id},{history});obs["silverRoot"]["act"]=2;
                auto &k=obs["silverRoot"]["combat"]["runicDomeKnowledge"]["monsters"][0];
                k["schemaVersion"]=3;k["totalRolls"]=phase?2:1;
                k["knownTransitions"]=(phase==2 || (id=="Shelled Parasite" && phase==1))?2:1;
                k["generation"]=phase+k["totalRolls"].get<int>()+k["knownTransitions"].get<int>();
                k["pendingMoveRolls"]=phase==1?1:0;
                k["knownNextMove"]=phase==1?json(nullptr):json{{"kind",phase==0?"public_stun_override":"byrd_headbutt_fly"},{"move",phase==0?4:2}};
                k["knownRollPredecessor"]=id=="Shelled Parasite" && phase==1?json("shelled_stun_fell"):json(nullptr);
                auto imported=one_combat::advisor::importSilverRoot(obs);
                if(!imported.ok) throw std::runtime_error("Dome public stun lifecycle "+id+": "+imported.reason);
                auto bc=battleContextFromWire(imported.wire);const auto rng=bc.aiRng;
                auto &m=bc.monsters.arr[0];m.materializePendingMove(bc);
                if(phase!=1 && (bc.aiRng!=rng || m.moveHistory[0]!=(phase==0?(id=="Byrd"?MMID::BYRD_STUNNED:MMID::SHELLED_PARASITE_STUNNED):MMID::BYRD_FLY)))
                    throw std::runtime_error("Dome public override consumed RNG or lost move");
                if(phase==1 && id=="Byrd" && m.moveHistory[0]!=MMID::BYRD_HEADBUTT)
                    throw std::runtime_error("Byrd post-stun must roll Headbutt");
                if(phase==1 && id=="Shelled Parasite" && m.moveHistory[1]!=MMID::SHELLED_PARASITE_FELL)
                    throw std::runtime_error("Shelled post-stun predecessor lost");
                auto bad=obs;bad["silverRoot"]["combat"]["runicDomeKnowledge"]["monsters"][0].erase("knownRollPredecessor");
                if(one_combat::advisor::importSilverRoot(bad).ok) throw std::runtime_error("missing public predecessor proof accepted");
            }
            {
                auto obs=groupDome({"Exploder","Repulsor"},{{1,2},{1,1}});
                obs["silverRoot"]["act"]=3;obs["silverRoot"]["playerTurn"]=4;obs["silverRoot"]["combat"]["turn"]=4;
                auto &c=obs["silverRoot"]["combat"];
                for(auto &k:c["runicDomeKnowledge"]["monsters"]) {k["completedTurns"]=3;k["generation"]=7;}
                c["monsters"][0]["hp"]=0;c["monsters"][0]["powers"].push_back({{"id","Explosive"},{"amount",1}});
                c["runicDomeKnowledge"]["monsters"][0]["pendingMoveRolls"]=0;
                auto imported=one_combat::advisor::importSilverRoot(obs);
                if(!imported.ok || imported.wire.monsters[0].pendingMoveRolls) throw std::runtime_error("dead Exploder retained public countdown: "+imported.reason);
            }
            for(int phase=0;phase<9;++phase) {
                const int publicMoves[]={6,2,7,5,1,3,4,5};
                std::vector<int> history;for(int i=std::max(0,phase-2);i<phase;++i) history.push_back(publicMoves[i]);
                auto obs=groupDome({"TheGuardian"},{history});obs["silverRoot"]["encounter"]="THE_GUARDIAN";
                auto &c=obs["silverRoot"]["combat"];c["turn"]=phase+1;obs["silverRoot"]["playerTurn"]=phase+1;
                auto &k=c["runicDomeKnowledge"]["monsters"][0];k["schemaVersion"]=3;k["completedTurns"]=phase;
                k["totalRolls"]=1;k["knownTransitions"]=phase+(phase>=4?1:0);k["generation"]=phase+1+k["knownTransitions"].get<int>();
                k["publicMisc"]=phase>=7?40:30;k["pendingMoveRolls"]=phase?0:1;k["knownRollPredecessor"]=nullptr;
                const int next[]={0,3,7,4,5,6,2,5};
                const int target=phase==4?1:phase?next[publicMoves[phase-1]]:6;
                k["knownNextMove"]=phase?json{{"kind",phase==4?"guardian_defensive_override":"guardian_public_cycle"},{"move",target}}:json(nullptr);
                if(phase<4 || phase>=7) c["monsters"][0]["powers"].push_back({{"id","Mode Shift"},{"amount",phase>=7?40:30}});
                if(phase==5 || phase==6) c["monsters"][0]["powers"].push_back({{"id","Sharp Hide"},{"amount",3}});
                auto imported=one_combat::advisor::importSilverRoot(obs);
                if(!imported.ok) throw std::runtime_error("Dome Guardian public phase: "+imported.reason);
                auto bc=battleContextFromWire(imported.wire);const auto rng=bc.aiRng;
                bc.monsters.arr[0].materializePendingMove(bc);
                if(javaMoveByte("TheGuardian",bc.monsters.arr[0].moveHistory[0])!=target || (phase && bc.aiRng!=rng))
                    throw std::runtime_error("Guardian phase consumed RNG or changed move");
                if(phase==4) {
                    c["monsters"][0]["powers"].push_back({{"id","Mode Shift"},{"amount",1}});
                    if(one_combat::advisor::importSilverRoot(obs).ok) throw std::runtime_error("Guardian contradictory forced defense accepted");
                }
            }
            for(int completed=0;completed<=17;++completed) {
                const int cycle[]={4,2,4,3,2,4,6};
                const auto executed=[&](int i){return i==0?5:i==1?1:cycle[(i-2)%7];};
                std::vector<int> history;for(int i=std::max(0,completed-2);i<completed;++i) history.push_back(executed(i));
                auto obs=groupDome({"Hexaghost"},{history});obs["silverRoot"]["encounter"]="HEXAGHOST";
                auto &c=obs["silverRoot"]["combat"];c["turn"]=completed+1;obs["silverRoot"]["playerTurn"]=completed+1;
                auto &k=c["runicDomeKnowledge"]["monsters"][0];k["schemaVersion"]=3;k["completedTurns"]=completed;
                k["totalRolls"]=std::max(1,completed);k["knownTransitions"]=completed?1+(completed-1)/7:0;
                k["generation"]=completed+k["totalRolls"].get<int>()+k["knownTransitions"].get<int>();
                k["publicMisc"]=completed?4:0;k["pendingMoveRolls"]=completed==1?0:1;
                k["knownNextMove"]=completed==1?json{{"kind","hexaghost_activate"},{"move",1}}:json(nullptr);
                const bool inferno=completed>=2 && (completed-2)%7==6;
                k["knownRollPredecessor"]=inferno?json("hexaghost_inferno_predecessor"):json(nullptr);
                auto imported=one_combat::advisor::importSilverRoot(obs);
                if(!imported.ok) throw std::runtime_error("Dome Hex public phase: "+imported.reason);
                auto bc=battleContextFromWire(imported.wire);const auto rng=bc.aiRng;
                bc.monsters.arr[0].materializePendingMove(bc);
                if(javaMoveByte("Hexaghost",bc.monsters.arr[0].moveHistory[0])!=executed(completed)
                        || (completed==1 && bc.aiRng!=rng)
                        || bc.monsters.arr[0].uniquePower0!=(completed==1?6:completed>=2?(completed-2)%7:0))
                    throw std::runtime_error("Hex public cycle/RNG/orb count parity");
                if(completed==0) {
                    const auto before=bc.aiRng;bc.player.curHp=47;bc.monsters.arr[0].takeTurn(bc);
                    if(bc.aiRng!=before || bc.monsters.arr[0].miscInfo!=4 || bc.monsters.arr[0].uniquePower0!=6)
                        throw std::runtime_error("Hex Activate public HP or phantom RNG draw");
                }
                if(inferno) {
                    auto bad=obs;bad["silverRoot"]["combat"]["runicDomeKnowledge"]["monsters"][0]["knownRollPredecessor"]=nullptr;
                    if(one_combat::advisor::importSilverRoot(bad).ok) throw std::runtime_error("Hex missing extra setter accepted");
                }
                if(completed==8) {
                    bc.cards.drawPile.assignConcrete({CardInstance(CardId::BURN),CardInstance(CardId::STRIKE_RED)});
                    bc.cards.discardPile.clear();bc.cards.discardPile.push_back(CardInstance(CardId::BURN));
                    bc.cards.exhaustPile.clear();bc.cards.exhaustPile.push_back(CardInstance(CardId::BURN));
                    bc.cards.cardsInHand=1;bc.cards.hand[0]=CardInstance(CardId::BURN);
                    const auto before=bc.aiRng;Actions::BurnIncreaseAction()(bc);
                    if(!bc.cards.drawPile[0].isUpgraded() || bc.cards.drawPile[1].isUpgraded()
                            || bc.cards.discardPile.size()!=4 || bc.cards.hand[0].isUpgraded()
                            || bc.cards.exhaustPile[0].isUpgraded() || bc.aiRng!=before)
                        throw std::runtime_error("Hex Inferno BurnIncrease pile semantics");
                    for(const auto &card:bc.cards.discardPile) if(card.getId()!=CardId::BURN || !card.isUpgraded())
                        throw std::runtime_error("Hex Inferno did not add exactly three upgraded Burns");
                }
            }
            // Lagavulin public natural wake and awake/event override.
            for(int mode=0;mode<3;++mode) for(int phase=0;phase<6;++phase) {
                const std::vector<int> sequence=mode==0?std::vector<int>{5,5,5,3,3,1}:mode==1?std::vector<int>{4,3,3,1,3,3}:std::vector<int>{1,3,3,1,3,3};
                std::vector<int> history(sequence.begin()+std::max(0,phase-2),sequence.begin()+phase);
                auto obs=groupDome({"Lagavulin"},{history});obs["silverRoot"]["encounter"]=mode==2?"LAGAVULIN_EVENT":"LAGAVULIN";
                auto &c=obs["silverRoot"]["combat"];c["turn"]=phase+1;obs["silverRoot"]["playerTurn"]=phase+1;
                auto &k=c["runicDomeKnowledge"]["monsters"][0];k["schemaVersion"]=3;k["completedTurns"]=phase;
                const bool known=mode==0?phase==3:phase==0;
                k["totalRolls"]=mode==0?phase+1-(phase>=3?1:0):phase+1;k["knownTransitions"]=mode==0?std::min(phase,3):1;
                k["generation"]=phase+k["totalRolls"].get<int>()+k["knownTransitions"].get<int>();
                k["pendingMoveRolls"]=known?0:1;k["publicAsleep"]=mode==0 && phase<3;k["publicSleepTurns"]=mode==0?std::min(phase,3):0;
                k["knownNextMove"]=known?json{{"kind",mode==0?"lagavulin_natural_wake":mode==1?"public_stun_override":"lagavulin_awake_event"},{"move",mode==0?3:mode==1?4:1}}:json(nullptr);
                k["knownRollPredecessor"]=mode==0 && phase>0 && phase<3?json("lagavulin_sleep_predecessor"):json(nullptr);
                if(mode==0 && phase<3) c["monsters"][0]["powers"].push_back({{"id","Metallicize"},{"amount",8}});
                auto imported=one_combat::advisor::importSilverRoot(obs);if(!imported.ok) throw std::runtime_error("Dome Lagavulin public phase: "+imported.reason);
                auto bc=battleContextFromWire(imported.wire);const auto rng=bc.aiRng;auto &m=bc.monsters.arr[0];m.materializePendingMove(bc);
                const auto target=sequence[phase]==1?MMID::LAGAVULIN_SIPHON_SOUL:sequence[phase]==3?MMID::LAGAVULIN_ATTACK:MMID::LAGAVULIN_SLEEP;
                if(m.moveHistory[0]!=target || (known && bc.aiRng!=rng)) throw std::runtime_error("Laga deferred phase/RNG mismatch");
                if(mode==0 && phase==2) {const auto before=bc.aiRng;m.takeTurn(bc);
                    if(bc.aiRng!=before || m.hasStatus<MS::ASLEEP>() || m.hasStatus<MS::METALLICIZE>() || m.moveHistory[0]!=MMID::LAGAVULIN_ATTACK)
                        throw std::runtime_error("Laga natural third wake must not roll");}
            }
            for(const std::string id:{"Looter","Mugger"}) for(bool lunge:{false,true}) {
                const std::vector<int> sequence=lunge?std::vector<int>{1,1,4,2,3}:std::vector<int>{1,1,2,3};
                for(int completed=0;completed<=static_cast<int>(sequence.size());++completed) {
                    std::vector<int> history(sequence.begin()+std::max(0,completed-2),sequence.begin()+completed);
                    auto obs=groupDome({id,"JawWorm"},{history,history});obs["silverRoot"]["act"]=1;
                    auto &c=obs["silverRoot"]["combat"];c["turn"]=completed+1;obs["silverRoot"]["playerTurn"]=completed+1;
                    // Companion keeps the combat alive after the public escape.
                    auto &companion=c["runicDomeKnowledge"]["monsters"][1];companion["completedTurns"]=completed;companion["generation"]=2*completed+1;
                    companion["executedMoves"]=completed==0?json::array():completed==1?json::array({1}):json::array({1,1});
                    auto &k=c["runicDomeKnowledge"]["monsters"][0];k["schemaVersion"]=3;k["completedTurns"]=completed;k["totalRolls"]=1;
                    k["directChoices"]=completed>=2?1:0;k["knownTransitions"]=completed-(completed>=2?1:0);k["generation"]=2*completed+1;
                    const bool escaped=completed==static_cast<int>(sequence.size()),direct=completed==2;
                    k["pendingDirectMoveChoice"]=direct?1:0;k["pendingMoveRolls"]=completed?0:1;k["knownRollPredecessor"]=nullptr;
                    k["knownNextMove"]=completed && !direct && !escaped?json{{"kind","thief_public_cycle"},{"move",sequence[completed]}}:json(nullptr);
                    k["publicMisc"]=completed==0?0:completed==1?15:22;
                    c["monsters"][0]["powers"].push_back({{"id","Thievery"},{"amount",15}});c["monsters"][0]["escaping"]=escaped;
                    if(direct) k["pendingAttackPredicates"]=json::array({json::array({1,lunge})});
                    auto imported=one_combat::advisor::importSilverRoot(obs);if(!imported.ok) throw std::runtime_error("Dome thief public phase: "+imported.reason);
                    if(completed && !(imported.wire.miscBits & 1U)) throw std::runtime_error("thief public stolen-gold flag lost");
                    auto bc=battleContextFromWire(imported.wire);auto &m=bc.monsters.arr[0];const auto rng=bc.aiRng;
                    if(direct) {
                        auto policyState=bc;policyState.monsters.monsterCount=1;policyState.monsters.monstersAlive=1;
                        SilverRolloutAgent policy(false,0,1);
                        if(policy.getIncomingDamage(policyState)!=5) throw std::runtime_error("direct-only hidden intent used stale MUG damage");
                        policy.materializeHiddenIntents(policyState);
                        if(policyState.monsters.arr[0].pendingDirectMoveChoice || policyState.monsters.arr[0].isAttacking()!=lunge
                                || (!lunge && policy.getIncomingDamage(policyState)!=0)) throw std::runtime_error("rollout boundary ignored direct Spot evidence");
                    }
                    m.materializePendingMove(bc);
                    if(!escaped && javaMoveByte(id.c_str(),m.moveHistory[0])!=sequence[completed]) throw std::runtime_error("thief isolated choice/known successor mismatch");
                    if(completed && !direct && bc.aiRng!=rng) throw std::runtime_error("known thief successor consumed RNG");
                    if(escaped && (bc.monsters.monstersAlive!=1 || m.pendingDirectMoveChoice || m.pendingMoveRolls)) throw std::runtime_error("escaped thief retained latent intent");
                }
            }
            for(int deathTurn:{0,2}) for(int phase=0;phase<4;++phase) {
                const int completed=deathTurn+phase;
                std::vector<int> bossHistory;for(int i=0;i<deathTurn;++i) bossHistory.push_back(i==0?1:2);
                for(int i=0;i<phase;++i) bossHistory.push_back(i==0?3:i==1?5:6);
                if(bossHistory.size()>2) bossHistory.erase(bossHistory.begin(),bossHistory.end()-2);
                std::vector<int> cultistHistory;for(int i=std::max(0,completed-2);i<completed;++i) cultistHistory.push_back(i==0?3:1);
                auto obs=groupDome({"Cultist","Cultist","AwakenedOne"},{cultistHistory,cultistHistory,bossHistory});
                obs["silverRoot"]["act"]=3;obs["silverRoot"]["encounter"]="AWAKENED_ONE";obs["silverRoot"]["playerTurn"]=completed+1;
                auto &c=obs["silverRoot"]["combat"];c["turn"]=completed+1;
                for(auto &row:c["runicDomeKnowledge"]["monsters"]) {row["completedTurns"]=completed;row["generation"]=2*completed+1;}
                auto &m=c["monsters"][2];m["hp"]=phase?300:0;m["maxHp"]=300;m["halfDead"]=phase==0;
                auto &k=c["runicDomeKnowledge"]["monsters"][2];k["schemaVersion"]=3;k["totalRolls"]=completed+1;k["knownTransitions"]=2;
                k["generation"]=2*completed+3;k["publicMisc"]=phase?1:0;k["rollHp"]=300;k["rollMaxHp"]=300;
                k["pendingMoveRolls"]=phase?1:0;k["knownRollPredecessor"]=nullptr;
                k["knownNextMove"]=phase?json(nullptr):json{{"kind","awakened_public_rebirth"},{"move",3}};
                auto imported=one_combat::advisor::importSilverRoot(obs);if(!imported.ok) throw std::runtime_error("Dome Awakened public phase: "+imported.reason);
                auto bc=battleContextFromWire(imported.wire);auto &boss=bc.monsters.arr[2];boss.materializePendingMove(bc);
                if(phase==0) {
                    if(!boss.halfDead || boss.moveHistory[0]!=MMID::AWAKENED_ONE_REBIRTH || boss.moveHistory[1]!=MMID::AWAKENED_ONE_REBIRTH)
                        throw std::runtime_error("Awakened duplicate known Rebirth lost");
                    auto expected=bc.aiRng;expected.random(99);boss.takeTurn(bc);
                    while(!bc.actionQueue.isEmpty()) {auto action=bc.actionQueue.popFront();action(bc);}
                    boss.materializePendingMove(bc);
                    if(boss.halfDead || boss.curHp!=300 || boss.miscInfo!=1 || boss.moveHistory[0]!=MMID::AWAKENED_ONE_DARK_ECHO || bc.aiRng!=expected)
                        throw std::runtime_error("Awakened rebirth/Echo deferred draw parity");
                    auto bad=obs;bad["silverRoot"]["combat"]["runicDomeKnowledge"]["monsters"][2]["knownTransitions"]=1;
                    bad["silverRoot"]["combat"]["runicDomeKnowledge"]["monsters"][2]["generation"]=2*completed+2;
                    if(one_combat::advisor::importSilverRoot(bad).ok) throw std::runtime_error("missing duplicate Rebirth proof accepted");
                } else if(!boss.hasStatus<MS::MINION_LEADER>() || (phase==1 && boss.moveHistory[0]!=MMID::AWAKENED_ONE_DARK_ECHO)
                        || (phase>1 && boss.moveHistory[0]!=MMID::AWAKENED_ONE_SLUDGE && boss.moveHistory[0]!=MMID::AWAKENED_ONE_TACKLE))
                    throw std::runtime_error("Awakened public second-form semantics lost");
            }
            // Ordinary Act 2/3 lifecycles: no queued byte is supplied. Import
            // exactly public execution history, then compare deferred sampling
            // to the native transition from those same public roll-time inputs.
            for(const auto &[name,history]:std::vector<std::pair<std::string,std::vector<int>>>{
                    {"Chosen",{5,4}},{"SnakePlant",{1,2}},{"Snecko",{1,2}},
                    {"SphericGuardian",{2,4}},{"Exploder",{1,1}},{"Repulsor",{2,1}},
                    {"Maw",{2,5}},{"Nemesis",{2,4}},{"Orb Walker",{1,2}},
                    {"GiantHead",{1,3}},{"Spiker",{2,1}},{"Serpent",{2,1}},
                    {"SlaverBoss",{2,2}},{"GremlinFat",{2,2}},{"BookOfStabbing",{1,2}},{"TimeEater",{2,3}}}) {
                for(int completed=0;completed<=2;++completed) {
                    std::vector<int> executed(history.begin(),history.begin()+completed);
                    auto obs=groupDome({name},{executed});obs["silverRoot"]["act"]=3;
                    auto &k=obs["silverRoot"]["combat"]["runicDomeKnowledge"]["monsters"][0];
                    k["playerConstricted"]=true;
                    k["publicMisc"]=name=="Spiker"?std::count(executed.begin(),executed.end(),2)
                        :name=="BookOfStabbing"?1+std::count(executed.begin(),executed.end(),1):0;
                    if(name=="Exploder") obs["silverRoot"]["combat"]["monsters"][0]["powers"].push_back({{"id","Explosive"},{"amount",3-completed}});
                    const auto imported=one_combat::advisor::importSilverRoot(obs);
                    if(!imported.ok) throw std::runtime_error("expanded Dome import "+name+": "+imported.reason);
                    auto actual=battleContextFromWire(imported.wire), reference=actual;
                    auto &m=actual.monsters.arr[0];auto &r=reference.monsters.arr[0];
                    r.pendingMoveRolls=0;r.rollMoveFromInputs(reference,m.pendingRollInputs);m.materializePendingMove(actual);
                    if(!std::equal(std::begin(m.moveHistory),std::end(m.moveHistory),std::begin(r.moveHistory))
                            || m.miscInfo!=r.miscInfo || actual.aiRng!=reference.aiRng)
                        throw std::runtime_error("expanded Dome future transition "+name);
                }
            }
            for(const auto &ids:std::vector<std::vector<std::string>>{{"Centurion","Healer"},{"Deca","Donu"}}) {
                const bool bosses=ids[0]=="Deca";
                auto obs=groupDome(ids,bosses?std::vector<std::vector<int>>{{0},{2}}:std::vector<std::vector<int>>{{1},{3}});
                obs["silverRoot"]["act"]=bosses?3:2;
                const auto imported=one_combat::advisor::importSilverRoot(obs);
                if(!imported.ok) throw std::runtime_error("expanded Dome pair "+ids[0]+": "+imported.reason);
                auto actual=battleContextFromWire(imported.wire);
                for(int slot=0;slot<2;++slot) actual.monsters.arr[slot].materializePendingMove(actual);
                if(bosses && (actual.monsters.arr[0].moveHistory[0]!=MMID::DECA_SQUARE_OF_PROTECTION
                        || actual.monsters.arr[1].moveHistory[0]!=MMID::DONU_BEAM))
                    throw std::runtime_error("Donu/Deca deferred alternation");
            }
            for(const auto &[name,history,next,misc]:std::vector<std::tuple<std::string,std::vector<int>,int,int>>{
                    {"GremlinThief",{1,1},1,0},{"GremlinWarrior",{1,1},1,0},{"GremlinWizard",{2,2},2,2},
                    {"GremlinTsundere",{1,1},2,0},{"BanditBear",{2,3},1,0},{"BanditLeader",{2,3},1,0},
                    {"BanditChild",{1,1},1,0},{"Transient",{1,1},1,0}}) {
                auto obs=groupDome({name},{history});obs["silverRoot"]["act"]=2;
                auto &k=obs["silverRoot"]["combat"]["runicDomeKnowledge"]["monsters"][0];
                k["publicMisc"]=misc;k["pendingMoveRolls"]=0;
                k["knownNextMove"]={{"kind","public_deterministic_transition_v1"},{"move",next}};
                const auto imported=one_combat::advisor::importSilverRoot(obs);
                if(!imported.ok) throw std::runtime_error("Dome known public transition "+name+": "+imported.reason);
                auto bc=battleContextFromWire(imported.wire);const auto rng=bc.aiRng;
                bc.monsters.arr[0].materializePendingMove(bc);
                if(bc.aiRng!=rng || bc.monsters.arr[0].moveHistory[0]!=*one_combat::advisor::live_silver::monsterMove(name,next))
                    throw std::runtime_error("known deterministic move sampled hidden RNG "+name);
                k["knownNextMove"]["move"]=next==1?2:1;
                if(one_combat::advisor::importSilverRoot(obs).ok) throw std::runtime_error("false deterministic proof accepted "+name);
            }
            {
                auto obs=groupDome({"WrithingMass"},{{1}});
                auto &k=obs["silverRoot"]["combat"]["runicDomeKnowledge"]["monsters"][0];
                k["schemaVersion"]=2;k["totalRolls"]=4;k["generation"]=5;k["pendingMoveRolls"]=3;
                k["pendingRollInputs"]=json::array();
                for(int hp:{35,32,30}) k["pendingRollInputs"].push_back({{"rollHp",hp},{"rollMaxHp",40},
                    {"firstHp",hp},{"firstMaxHp",40},{"firstAlive",true},{"aliveCount",1},{"playerConstricted",false}});
                k["pendingAttackPredicates"]=json::array({json::array({1,true}),json::array({2,false}),json::array({3,true})});
                auto imported=one_combat::advisor::importSilverRoot(obs);
                if(!imported.ok || imported.wire.monsters[0].pendingRollInputHistory.size()!=3)
                    throw std::runtime_error("reactive Dome chain import: "+imported.reason);
                auto bc=battleContextFromWire(imported.wire);bc.monsters.arr[0].materializePendingMove(bc);
                if(!bc.monsters.arr[0].isAttacking() || bc.monsters.arr[0].pendingMoveRolls)
                    throw std::runtime_error("reactive Dome public predicates not conditioned");
                k["pendingRollInputs"].erase(k["pendingRollInputs"].begin());
                if(one_combat::advisor::importSilverRoot(obs).ok) throw std::runtime_error("compressed reactive roll history accepted");
            }
            {
                auto obs=groupDome({"Champ"},{{2,7}});obs["silverRoot"]["act"]=2;
                obs["silverRoot"]["combat"]["runicDomeKnowledge"]["monsters"][0]["publicMisc"]=5;
                auto imported=one_combat::advisor::importSilverRoot(obs);
                if(!imported.ok || imported.wire.monsters[0].miscInfo!=5) throw std::runtime_error("Champ public phase: "+imported.reason);
                auto bc=battleContextFromWire(imported.wire);bc.monsters.arr[0].materializePendingMove(bc);
                if(bc.monsters.arr[0].moveHistory[0]!=MMID::THE_CHAMP_EXECUTE) throw std::runtime_error("Champ executed Anger phase lost");
                obs=groupDome({"SlaverBoss","GremlinNob"},{{2},{3}});obs["silverRoot"]["act"]=2;
                obs["silverRoot"]["encounter"]="COLOSSEUM_EVENT_NOBS";
                if(!one_combat::advisor::importSilverRoot(obs).ok) throw std::runtime_error("source-qualified Colosseum Nob rejected");
                obs=groupDome({"JawWorm","JawWorm","JawWorm"},{{},{},{}});
                obs["silverRoot"]["act"]=3;obs["silverRoot"]["encounter"]="JAW_WORM_HORDE";
                imported=one_combat::advisor::importSilverRoot(obs);
                if(!imported.ok) throw std::runtime_error("public hard Jaw horde: "+imported.reason);
                bc=battleContextFromWire(imported.wire);
                for(int slot=0;slot<3;++slot) {
                    auto &jaw=bc.monsters.arr[slot];int misc=0;
                    if(jaw.getMoveForRoll(bc,jaw.pendingRollInputs,misc,99)!=MMID::JAW_WORM_BELLOW)
                        throw std::runtime_error("hard Jaw incorrectly forced ordinary opening");
                }
                auto mad=battleContextFromWire(fixtures[1].wire);mad.monsters.arr[0].id=MonsterId::MAD_GREMLIN;
                mad.monsters.arr[0].moveHistory[0]=MMID::MAD_GREMLIN_SCRATCH;
                const auto rng=mad.aiRng;mad.monsters.arr[0].takeTurn(mad);
                while(!mad.actionQueue.isEmpty()) {auto action=mad.actionQueue.popFront();action(mad);}
                if(mad.aiRng!=rng) throw std::runtime_error("Mad Gremlin consumed phantom roll");
            }
            // Independent vanilla-table expectations, including paths ordinary
            // native simulation previously bypassed with direct setMove.
            {
                auto bc=battleContextFromWire(fixtures[1].wire);auto &m=bc.monsters.arr[0];
                const auto expect=[&](MonsterId id,MonsterMoveId last,MonsterMoveId before,int roll,MonsterMoveId wanted,int turn=1,int asc=0) {
                    m.id=id;m.moveHistory[0]=last;m.moveHistory[1]=before;bc.ascension=asc;
                    auto in=m.captureRollInputs(bc);in.monsterTurnNumber=turn;in.curHp=30;in.maxHp=40;
                    in.knightCurHp=30;in.knightMaxHp=40;in.knightAlive=true;int data=0;
                    if(m.getMoveForRoll(bc,in,data,roll)!=wanted) throw std::runtime_error("expanded vanilla-table boundary "+std::to_string(static_cast<int>(id)));
                };
                expect(MonsterId::MYSTIC,MMID::MYSTIC_BUFF,MMID::INVALID,0,MMID::MYSTIC_HEAL);
                expect(MonsterId::MYSTIC,MMID::MYSTIC_HEAL,MMID::MYSTIC_HEAL,0,MMID::MYSTIC_BUFF);
                expect(MonsterId::SNAKE_PLANT,MMID::SNAKE_PLANT_CHOMP,MMID::SNAKE_PLANT_ENFEEBLING_SPORES,65,MMID::SNAKE_PLANT_CHOMP,1,17);
                expect(MonsterId::SPHERIC_GUARDIAN,MMID::SPHERIC_GUARDIAN_ACTIVATE,MMID::INVALID,99,MMID::SPHERIC_GUARDIAN_ATTACK_DEBUFF);
                expect(MonsterId::SPHERIC_GUARDIAN,MMID::SPHERIC_GUARDIAN_ATTACK_DEBUFF,MMID::SPHERIC_GUARDIAN_ACTIVATE,0,MMID::SPHERIC_GUARDIAN_SLAM);
                expect(MonsterId::SPHERIC_GUARDIAN,MMID::SPHERIC_GUARDIAN_SLAM,MMID::SPHERIC_GUARDIAN_ATTACK_DEBUFF,0,MMID::SPHERIC_GUARDIAN_HARDEN);
                expect(MonsterId::EXPLODER,MMID::EXPLODER_SLAM,MMID::INVALID,0,MMID::EXPLODER_SLAM);
                expect(MonsterId::EXPLODER,MMID::EXPLODER_SLAM,MMID::EXPLODER_SLAM,99,MMID::EXPLODER_EXPLODE);
                expect(MonsterId::THE_MAW,MMID::THE_MAW_NOM,MMID::THE_MAW_ROAR,0,MMID::THE_MAW_DROOL);
                expect(MonsterId::GIANT_HEAD,MMID::GIANT_HEAD_COUNT,MMID::GIANT_HEAD_GLARE,0,MMID::GIANT_HEAD_GLARE,3);
                expect(MonsterId::GIANT_HEAD,MMID::GIANT_HEAD_COUNT,MMID::GIANT_HEAD_GLARE,0,MMID::GIANT_HEAD_IT_IS_TIME,4);
                expect(MonsterId::GIANT_HEAD,MMID::GIANT_HEAD_COUNT,MMID::GIANT_HEAD_GLARE,0,MMID::GIANT_HEAD_IT_IS_TIME,3,18);
                for(auto id:{MonsterId::DONU,MonsterId::DECA}) {
                    m.id=id;m.moveHistory[0]=id==MonsterId::DONU?MMID::DONU_CIRCLE_OF_POWER:MMID::DECA_SQUARE_OF_PROTECTION;
                    bc.actionQueue.clear();const auto before=bc.aiRng;auto expected=before;expected.random(99);
                    m.takeTurn(bc);while(!bc.actionQueue.isEmpty()) { auto action=bc.actionQueue.popFront();action(bc); }
                    if(bc.aiRng!=expected) throw std::runtime_error("Donu/Deca missing vanilla trailing roll");
                }
            }
            // Vanilla bytecode boundaries: SlaverRed uses 55 (not 50),
            // asc17 forbids consecutive debuffs, Nob asc18 checks either of
            // the previous two moves for Bash (not two consecutive Bashes).
            {
                auto bc=battleContextFromWire(fixtures[1].wire); auto &m=bc.monsters.arr[0];
                const auto expect=[&](MonsterId id,int asc,int roll,MonsterMoveId last,MonsterMoveId before,int misc,MonsterMoveId wanted) {
                    bc.ascension=asc;m.id=id;m.miscInfo=misc;m.moveHistory[0]=last;m.moveHistory[1]=before;
                    auto inputs=m.captureRollInputs(bc);inputs.miscInfo=misc;int data=misc;
                    const auto actual=m.getMoveForRoll(bc,inputs,data,roll);
                    if(actual!=wanted) throw std::runtime_error("vanilla Dome move-rule boundary id="+std::to_string(static_cast<int>(id))+" asc="+std::to_string(asc)+" roll="+std::to_string(roll)+" expected="+std::to_string(static_cast<int>(wanted))+" actual="+std::to_string(static_cast<int>(actual)));
                };
                for(int roll:{50,54}) expect(MonsterId::RED_SLAVER,0,roll,MMID::RED_SLAVER_STAB,MMID::RED_SLAVER_SCRAPE,1,MMID::RED_SLAVER_SCRAPE);
                expect(MonsterId::RED_SLAVER,0,55,MMID::RED_SLAVER_STAB,MMID::RED_SLAVER_SCRAPE,1,MMID::RED_SLAVER_STAB);
                expect(MonsterId::RED_SLAVER,0,74,MMID::RED_SLAVER_STAB,MMID::INVALID,0,MMID::RED_SLAVER_SCRAPE);
                expect(MonsterId::RED_SLAVER,0,75,MMID::RED_SLAVER_STAB,MMID::INVALID,0,MMID::RED_SLAVER_ENTANGLE);
                expect(MonsterId::RED_SLAVER,17,0,MMID::RED_SLAVER_SCRAPE,MMID::RED_SLAVER_STAB,1,MMID::RED_SLAVER_STAB);
                expect(MonsterId::BLUE_SLAVER,17,0,MMID::BLUE_SLAVER_RAKE,MMID::BLUE_SLAVER_STAB,0,MMID::BLUE_SLAVER_STAB);
                expect(MonsterId::BLUE_SLAVER,0,0,MMID::BLUE_SLAVER_RAKE,MMID::BLUE_SLAVER_STAB,0,MMID::BLUE_SLAVER_RAKE);
                expect(MonsterId::GREMLIN_NOB,18,99,MMID::GREMLIN_NOB_BELLOW,MMID::INVALID,0,MMID::GREMLIN_NOB_SKULL_BASH);
                expect(MonsterId::GREMLIN_NOB,18,0,MMID::GREMLIN_NOB_RUSH,MMID::GREMLIN_NOB_SKULL_BASH,0,MMID::GREMLIN_NOB_RUSH);
                expect(MonsterId::GREMLIN_NOB,18,0,MMID::GREMLIN_NOB_RUSH,MMID::GREMLIN_NOB_RUSH,0,MMID::GREMLIN_NOB_SKULL_BASH);
                expect(MonsterId::GREMLIN_NOB,0,32,MMID::GREMLIN_NOB_BELLOW,MMID::INVALID,0,MMID::GREMLIN_NOB_SKULL_BASH);
                expect(MonsterId::GREMLIN_NOB,0,33,MMID::GREMLIN_NOB_BELLOW,MMID::INVALID,0,MMID::GREMLIN_NOB_RUSH);
            }
            for(bool attacking:{false,true}) {
                auto obs=groupDome({"JawWorm"},{{1}});
                obs["silverRoot"]["combat"]["runicDomeKnowledge"]["monsters"][0]["pendingAttackPredicates"]=json::array({json::array({1,attacking})});
                const auto imported=one_combat::advisor::importSilverRoot(obs);
                if(!imported.ok || imported.wire.monsters[0].pendingMoveRolls!=1
                        || imported.wire.monsters[0].pendingAttackPredicates!=std::vector<std::pair<int,bool>>{{1,attacking}})
                    throw std::runtime_error("Dome Spot boolean projection: "+imported.reason);
                auto bc=battleContextFromWire(imported.wire);
                bc.monsters.arr[0].materializePendingMove(bc);
                if(bc.monsters.arr[0].isAttacking()!=attacking) throw std::runtime_error("Dome Spot conditioned materialization");
            }
            for(const auto &badPredicate:{json::array({json::array({1,1})}),json::array({json::array({2,true})}),json::array({json::array({1,true}),json::array({1,false})})}) {
                auto obs=groupDome({"JawWorm"},{{1}});obs["silverRoot"]["combat"]["runicDomeKnowledge"]["monsters"][0]["pendingAttackPredicates"]=badPredicate;
                if(one_combat::advisor::importSilverRoot(obs).ok) throw std::runtime_error("malformed Spot predicate accepted");
            }
            const auto expectDomeReject=[&](json obs,const char *reason) {
                const auto result=one_combat::advisor::importSilverRoot(obs);
                if(result.ok || result.reason!=reason)
                    throw std::runtime_error(std::string("Dome rejection mismatch expected ")+reason+" got "+result.reason+" knowledge="+obs["silverRoot"]["combat"].value("runicDomeKnowledge",json()).dump());
            };
            {
                auto invalid=groupDome({"FungiBeast","FungiBeast"},{{1},{1}});
                invalid["silverRoot"]["combat"]["runicDomeKnowledge"]["monsters"][0].erase("pendingAttackPredicates");
                if(one_combat::advisor::importSilverRoot(invalid).ok) throw std::runtime_error("unobserved Spot history accepted");
            }
            for(const auto &mutation:{json{{"slot",1}},json{{"publicMisc",1}},json{{"monsterId","Looter"}},
                    json{{"completedTurns",0}},json{{"pendingMoveRolls",0}},json{{"firstAlive","true"}}}) {
                auto invalid=groupDome({"FungiBeast","FungiBeast"},{{1},{1}});
                invalid["silverRoot"]["combat"]["runicDomeKnowledge"]["monsters"][0].update(mutation);
                if(one_combat::advisor::importSilverRoot(invalid).ok) throw std::runtime_error("malformed Dome group accepted");
            }
            auto bad=domeObservation(1,1); bad["silverRoot"]["combat"].erase("runicDomeKnowledge");
            expectDomeReject(bad,"silver_runic_dome_missing_history");
            for(const auto &field:{"nextMove","moveHistory","intentDamage","uniquePower0"}) {
                bad=domeObservation(1,1);bad["silverRoot"]["combat"]["monsters"][0][field]=1;
                expectDomeReject(bad,"silver_runic_dome_hidden_field");
            }
            for(auto mutation:{json{{"schemaVersion",2}},json{{"epoch",0}},json{{"generation","3"}},
                               json{{"pendingMoveRolls",2}}}) {
                bad=domeObservation(1,1);bad["silverRoot"]["combat"]["runicDomeKnowledge"].update(mutation);
                expectDomeReject(bad,"silver_runic_dome_history_schema");
            }
            for(auto mutation:{json{{"completedTurns",0}},json{{"generation",1}},json{{"executedMoves",json::array({2})}},json{{"rollHp",0}}}) {
                bad=domeObservation(1,1);bad["silverRoot"]["combat"]["runicDomeKnowledge"].update(mutation);
                expectDomeReject(bad,"silver_runic_dome_history_gap");
            }
            bad=domeObservation(1,1);bad["silverRoot"]["combat"]["runicDomeKnowledge"]["complete"]=false;
            expectDomeReject(bad,"silver_runic_dome_incomplete_history");
            bad=domeObservation(1,1);bad["silverRoot"]["act"]=2;
            expectDomeReject(bad,"silver_runic_dome_encounter_domain");
            // Normal Ironclad/colorless generators and their public powers
            // use the generic support contract, including generated Spot.
            auto generated=groupDome({"JawWorm"},{{1}});
            auto &gc=generated["silverRoot"]["combat"];
            gc["hand"][0]["id"]="Spot Weakness";
            gc["relics"].push_back({{"id","Dead Branch"},{"counter",0},{"usedUp",false}});
            gc["playerPowers"].push_back({{"id","Magnetism"},{"amount",1}});
            gc["playerPowers"].push_back({{"id","Mayhem"},{"amount",1}});
            gc["potions"][0]["id"]="SkillPotion";
            gc["runicDomeKnowledge"]["monsters"][0]["pendingAttackPredicates"]=json::array({json::array({1,true})});
            const auto generatedImport=one_combat::advisor::importSilverRoot(generated);
            if(!generatedImport.ok) throw std::runtime_error("Dome generated Spot generic support: "+generatedImport.reason);
            auto generatedBc=battleContextFromWire(generatedImport.wire);generatedBc.monsters.arr[0].materializePendingMove(generatedBc);
            if(!generatedBc.monsters.arr[0].isAttacking()) throw std::runtime_error("generated Spot public predicate lost");
            bad=generated;bad["silverRoot"]["combat"]["hand"][0]["id"]="Go for the Eyes";
            expectDomeReject(bad,"silver_off_color_card");
            bad=domeObservation(1,1);
            bad["silverRoot"]["combat"]["monsters"][0]["powers"].push_back({{"id","Ritual"},{"amount",3},{"justApplied",false}});
            expectDomeReject(bad,"silver_runic_dome_monster_power_domain");

        }
        {
            auto capped = battleContextFromWire(fixtures[0].wire);
            capped.player.block = 998;
            capped.player.buff<PlayerStatus::JUGGERNAUT>(5);
            capped.monsters.arr[0].curHp = capped.monsters.arr[0].maxHp = 200;
            capped.player.gainBlock(capped, 3);
            capped.player.gainBlock(capped, 4);
            if (capped.player.block != 999 || capped.actionQueue.size != 2)
                throw std::runtime_error("block cap changed positive-gain Juggernaut triggers");
            capped.player.gainBlock(capped, 0);
            capped.player.gainBlock(capped, -1);
            if (capped.actionQueue.size != 2 || capped.player.block != 999)
                throw std::runtime_error("nonpositive block gain triggered Juggernaut");
            capped.inputState = InputState::EXECUTING_ACTIONS;
            capped.executeActions();
            if (capped.monsters.arr[0].curHp != 190 || capped.player.block != 999)
                throw std::runtime_error("capped block gains lost per-action Juggernaut damage");
        }
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
        {
            // Final-HP capture: each simulation at the current root is one
            // sample, root edges partition the root layer, extends accumulate,
            // a new root restarts, and capturing never changes the search.
            using Capture = sts::search::SilverOutcomeCapture;
            const auto &wire = fixtures[1].wire;
            const auto samples = [](const Capture::Layer &layer) {
                std::int64_t sum = 0;
                for (const auto n : layer.hpCounts) sum += n;
                const auto deathBin = layer.hpCounts.empty() ? 0 : layer.hpCounts[0];
                if (sum != layer.count || deathBin != layer.deaths || layer.unresolved < 0)
                    throw std::runtime_error("final-HP layer counts are inconsistent");
                return layer.count + layer.unresolved;
            };
            const auto partitions = [&](const one_combat::advisor::NativeSilverDecision &d,
                                        std::int64_t expected) {
                const auto &root = d.outcomes.root;
                if (!d.accepted || samples(root) != expected
                    || d.outcomes.edges.size() != d.rootActionSummaries.size()
                    || d.rootHp != wire.player.curHp || d.rootMaxHp != wire.player.maxHp)
                    throw std::runtime_error("final-HP root layer does not match the search");
                std::int64_t edgeSamples = 0, deaths = 0, unresolved = 0;
                std::vector<std::int64_t> hp(root.hpCounts.size(), 0);
                for (const auto &edge : d.outcomes.edges) {
                    edgeSamples += samples(edge);
                    deaths += edge.deaths;
                    unresolved += edge.unresolved;
                    if (edge.hpCounts.size() > hp.size())
                        throw std::runtime_error("final-HP edge exceeds the root axis");
                    for (std::size_t i = 0; i < edge.hpCounts.size(); ++i) hp[i] += edge.hpCounts[i];
                }
                if (edgeSamples != expected || deaths != root.deaths
                    || unresolved != root.unresolved || hp != root.hpCounts)
                    throw std::runtime_error("final-HP root edges do not partition the root layer");
            };
            SilverSearchSession session;
            const auto first = session.decide(wire, 96);
            partitions(first, 96);
            for (std::size_t i = 0; i < first.rootActionSummaries.size(); ++i)
                if (samples(first.outcomes.edges[i]) != first.rootActionSummaries[i].edgeVisits)
                    throw std::runtime_error("fresh-root edge samples differ from edge visits");
            if (first.outcomes.root.count == 0)
                throw std::runtime_error("final-HP capture recorded no resolved combat");
            partitions(session.extend(32), 128);
            const auto other = session.decide(fixtures[0].wire, 40);
            if (!other.accepted || samples(other.outcomes.root) != 40)
                throw std::runtime_error("a new root did not restart the final-HP capture");

            SilverSearcher plain(battleContextFromWire(wire), searchContextFromWire(wire));
            SilverSearcher captured(battleContextFromWire(wire), searchContextFromWire(wire));
            Capture capture;
            captured.outcomes = &capture;
            plain.search(200);
            captured.search(200);
            const auto &a = plain.rootNode(), &b = captured.rootNode();
            bool same = a.edges.size() == b.edges.size() && a.simulationCount == b.simulationCount
                && a.evaluationSum == b.evaluationSum
                && plain.bestAction().bits == captured.bestAction().bits;
            for (std::size_t i = 0; same && i < a.edges.size(); ++i)
                same = a.edges[i].visitCount == b.edges[i].visitCount;
            if (!same || samples(capture.root) != 200)
                throw std::runtime_error("final-HP capture changed the Silver search");
        }
        {
            // The Java v4 producer does not emit monsterTurnIdx at a stable
            // player decision. A missing field must retain the native player-
            // turn sentinel, not schedule monsters after the next card play.
            auto producerShaped = multi.observation;
            producerShaped["silverRoot"]["combat"].erase("monsterTurnIdx");
            const auto imported = one_combat::advisor::importSilverRoot(producerShaped);
            if (!imported.ok || imported.wire.monsterTurnIdx != multi.wire.monsterTurnIdx)
                throw std::runtime_error("missing producer monsterTurnIdx changed player-turn phase");
            auto session = makeSilverSearchSession();
            SilverSearchConfig config;
            config.simulationsPerDecision = 64;
            config.adaptiveEnabled = false;
            const auto decision = runSilverDecision(*session, imported.wire, config);
            const auto tree = session->snapshot(256);
            if (!decision.accepted || !tree.accepted)
                throw std::runtime_error("producer-shaped root search failed");
            bool sawCard = false;
            for (const auto &edge : tree.edges) {
                if (edge.parentId != tree.rootId || !edge.hasAction
                    || edge.action.type != silver_bridge::SemanticActionType::CARD) continue;
                sawCard = true;
                const auto child = std::find_if(tree.nodes.begin(), tree.nodes.end(),
                    [&](const auto &node) { return node.id == edge.childId; });
                if (child == tree.nodes.end() || child->isChanceNode || !child->hasState
                    || child->state.player.curHp != imported.wire.player.curHp
                    || child->state.monsterTurnIdx != imported.wire.monsterTurnIdx)
                    throw std::runtime_error("card play scheduled a monster turn at player boundary");
            }
            if (!sawCard) throw std::runtime_error("producer-shaped search explored no root card");
        }
        {
            // Render an actual targeted card successor through the public v4
            // fields.  Do not copy native status bits or infer the target from
            // actionManager.lastCard: the Java queue item owns the resolved
            // AbstractMonster identity.
            GameContext game(CharacterClass::IRONCLAD, multi.wire.isolatedSearchSeed, 0);
            game.act = 1;
            game.floorNum = 1;
            BattleContext live;
            live.init(game, MonsterEncounter::THREE_CULTIST);
            for (int i = 0; i < multi.wire.monsterCount; ++i)
                live.monsters.arr[i].moveHistory[0] = static_cast<MMID>(
                    multi.wire.monsters[i].moveHistory[0]);
            CombatKnowledgeState knowledge;
            knowledge.initializeFromLiveBattle(live);
            int handIndex = -1;
            for (int i = 0; i < live.cards.cardsInHand; ++i) {
                if (live.cards.hand[i].id == CardId::STRIKE_RED) {
                    handIndex = i;
                    break;
                }
            }
            if (handIndex < 0) throw std::runtime_error("multi-target Strike is absent");
            sts::search::Action(sts::search::ActionType::CARD, handIndex, 2).execute(live);
            auto successorWire = makeSilverBattleStateWire(
                live, knowledge, makeSilverRunContext(game), multi.wire.isolatedSearchSeed);
            if (!successorWire.valid || successorWire.curCardQueueItem.target != 2
                || successorWire.player.lastTargetedMonster != 2)
                throw std::runtime_error("native multi-target queue state did not resolve slot 2");
            auto rendered = javaLikeDynamicObservation(
                successorWire, "MONSTER", "three-cultist-card-successor");
            setProducerV4CardObservation(rendered, successorWire);
            const auto imported = one_combat::advisor::importSilverRoot(rendered);
            if (!imported.ok)
                throw std::runtime_error("v4 multi-target successor import failed: "
                    + imported.reason);
            if (imported.wire.curCardQueueItem.target != 2
                || imported.wire.player.lastTargetedMonster != 2)
                throw std::runtime_error("v4 multi-target queue target was not preserved");
        }
        auto sparseSlots = multi.observation;
        sparseSlots["silverRoot"]["combat"]["monsters"].erase(
            sparseSlots["silverRoot"]["combat"]["monsters"].begin() + 1);
        const auto sparseImported = one_combat::advisor::importSilverRoot(sparseSlots);
        if (!sparseImported.ok || sparseImported.wire.monsterCount != 3
            || sparseImported.wire.monsters[1].id != static_cast<std::int16_t>(MonsterId::INVALID)
            || sparseImported.wire.monsters[2].idx != 2)
            throw std::runtime_error("stable monster-slot identity was compacted after a death");
        auto halfDead = multi.observation;
        halfDead["silverRoot"]["combat"]["monsters"][0]["halfDead"] = true;
        halfDead["silverRoot"]["combat"]["monsters"][0]["dead"] = false;
        const auto halfDeadImported = one_combat::advisor::importSilverRoot(halfDead);
        if (!halfDeadImported.ok || !halfDeadImported.wire.monsters[0].halfDead
            || halfDeadImported.wire.monstersAlive != 2)
            throw std::runtime_error("half-dead monster state was not preserved");
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
            throw std::runtime_error("multi-hit damage parity failed: "
                + json::diff(battleStateWireEnvelope(multiHitCanonical),
                             battleStateWireEnvelope(multiHitImported.wire)).dump());
        SilverSearchConfig config;
        config.simulationsPerDecision = 1000;
        config.collectRootActionSummaries = true;
        config.collectDecisionDiagnostics = true;
        config.adaptiveEnabled = false;
        config.exactVisitLockEnabled = false;
        config.rhoRacingEnabled = false;
        bool duplicateStrikeSummariesCovered = false;
        bool duplicateDefendSummariesCovered = false;
        for (const auto &source : {fixtures[0].observation,
                                  genericObservation(fixtures[0], "generation-binding")}) {
            auto absent = source;
            absent["silverRoot"]["combat"]["monsters"][0].erase("occupantGeneration");
            const auto old = one_combat::advisor::importSilverRoot(absent);
            if (!old.ok || old.wire.monsters[0].occupantGeneration != 0)
                throw std::runtime_error("absent occupant generation legacy default changed");
            auto supplied = source;
            supplied["silverRoot"]["combat"]["monsters"][0]["occupantGeneration"] = 7;
            const auto bound = one_combat::advisor::importSilverRoot(supplied);
            if (!bound.ok || bound.wire.monsters[0].occupantGeneration != 7)
                throw std::runtime_error("supplied occupant generation was not preserved");
            for (const auto &invalid : {json(0), json(-1), json(1000001), json(1.5), json(true), json("1")}) {
                supplied["silverRoot"]["combat"]["monsters"][0]["occupantGeneration"] = invalid;
                const auto rejected = one_combat::advisor::importSilverRoot(supplied);
                if (rejected.ok || rejected.reason != "silver_monster_occupant_binding")
                    throw std::runtime_error("invalid occupant generation accepted or misclassified");
            }
        }
        for (const auto &f : fixtures) {
            auto imported = one_combat::advisor::importSilverRoot(f.observation);
            if (!imported.ok) throw std::runtime_error("import failed: " + imported.reason);
            auto canonical = f.wire;
            canonical.isolatedSearchSeed = imported.wire.isolatedSearchSeed;
            if (!convertedStatesEqualForSearch(canonical, imported.wire))
                throw std::runtime_error(std::string("search parity failed: ") + f.name + " "
                    + json::diff(battleStateWireEnvelope(canonical),
                                 battleStateWireEnvelope(imported.wire)).dump());
            if (imported.wire.cardsDrawn != 5 || imported.wire.strikeCount != 5
                || imported.wire.hand != canonical.hand
                || imported.wire.handNormalityCount != canonical.handNormalityCount
                || imported.wire.handPainCount != canonical.handPainCount
                || imported.wire.handBloodCardCount != canonical.handBloodCardCount
                || imported.wire.drawPileBloodCardCount != canonical.drawPileBloodCardCount
                || imported.wire.discardPileBloodCardCount != canonical.discardPileBloodCardCount)
                throw std::runtime_error(std::string("first-root fields failed: ") + f.name);
            // The public observation cannot prove that its omitted queues
            // were empty. Compare search under the same conservative policy.
            if (!canonical.historicalQueueItemAtSource
                || imported.wire.historicalQueueItemAtSource)
                throw std::runtime_error("live queue provenance boundary changed");
            canonical.historicalQueueItemAtSource = imported.wire.historicalQueueItemAtSource;
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
            for (const auto &summary : b.rootActionSummaries) {
                if (summary.action.type == silver_bridge::SemanticActionType::CARD
                    && summary.action.card.id == static_cast<std::int16_t>(CardId::DEFEND_RED)
                    && summary.action.target != -1)
                    throw std::runtime_error(std::string("Defend retained packed target: ") + f.name);
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
        // Java PanachePower.amount is the countdown; damage is separate.
        verifyPlayerPowerParity("panache-parity", json{{"id", "Panache"}, {"amount", 3}, {"panacheDamage", 14}},
            [](auto &player) {
                static_assert(static_cast<int>(PlayerStatus::PANACHE) >= 64);
                player.statusBits1 |= 1U << (static_cast<int>(PlayerStatus::PANACHE) - 64);
                player.statusMap.emplace_back(static_cast<std::int16_t>(PlayerStatus::PANACHE), 14);
                player.panacheCounter = 3;
            });
        for (const auto &bad : {json{{"id", "Panache"}, {"amount", 5}},
                                json{{"id", "Panache"}, {"amount", 0}, {"panacheDamage", 10}},
                                json{{"id", "Panache"}, {"amount", 5}, {"panacheDamage", 0}}}) {
            auto observation = genericObservation(fixtures[0], "panache-refused");
            observation["silverRoot"]["combat"]["playerPowers"] = json::array({bad});
            if (one_combat::advisor::importSilverRoot(observation).ok)
                throw std::runtime_error("Panache without a valid damage/countdown must be refused");
        }
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

        // Relics with enum index >= 128 (Thread and Needle, Maw Bank) have no
        // combat bit; the legacy importer aliased them onto index - 64.
        auto highRelic = genericObservation(fixtures[0], "high-relic-parity");
        highRelic["silverRoot"]["combat"]["relics"].push_back(
            json{{"id", "Thread and Needle"}, {"counter", -1}, {"usedUp", false}});
        highRelic["silverRoot"]["combat"]["relics"].push_back(
            json{{"id", "MawBank"}, {"counter", -1}, {"usedUp", false}});
        auto highRelicExpected = fixtures[0].wire;
        normalizeFirstObservationIdentity(highRelicExpected);
        for (const char *flag : {"1", "0"}) {
            setenv("STS_IMPORTER_HIGH_RELIC_FIX", flag, 1);
            auto imported = one_combat::advisor::importSilverRoot(highRelic);
            if (!imported.ok) throw std::runtime_error("high relic import failed: " + imported.reason);
            auto expected = highRelicExpected;
            if (std::string(flag) == "0") {
                expected.player.relicBits1 |= 1ULL << (static_cast<int>(RelicId::STRIKE_DUMMY) - 64);
                expected.player.relicBits1 |= 1ULL << (static_cast<int>(RelicId::WRIST_BLADE) - 64);
            }
            expected.isolatedSearchSeed = imported.wire.isolatedSearchSeed;
            if (!convertedStatesEqualForSearch(expected, imported.wire))
                throw std::runtime_error(std::string("high relic parity failed, flag=") + flag);
        }
        unsetenv("STS_IMPORTER_HIGH_RELIC_FIX");

        // Centennial Puzzle: vanilla keeps the relic (usedUp false) after the
        // once-per-combat draw; native marks it used by clearing the bit.
        const auto centennialBit = 1ULL << static_cast<int>(RelicId::CENTENNIAL_PUZZLE);
        const auto centennialObservation = [&](const char *label, std::optional<bool> used) {
            auto obs = genericObservation(fixtures[0], label);
            json relic{{"id", "Centennial Puzzle"}, {"counter", -1}, {"usedUp", false}};
            if (used) relic["usedThisCombat"] = *used;
            obs["silverRoot"]["combat"]["relics"].push_back(relic);
            return obs;
        };
        for (const char *flag : {"1", "0"}) {
            setenv("STS_IMPORTER_CENTENNIAL_USED_FIX", flag, 1);
            const bool fix = std::string(flag) == "1";
            for (const bool used : {false, true}) {
                auto imported = one_combat::advisor::importSilverRoot(
                    centennialObservation("centennial-parity", used));
                if (!imported.ok) throw std::runtime_error("Centennial import failed: " + imported.reason);
                const bool armed = (imported.wire.player.relicBits0 & centennialBit) != 0;
                if (armed != (!fix || !used))
                    throw std::runtime_error(std::string("Centennial relic bit wrong, flag=") + flag
                        + " used=" + (used ? "1" : "0"));
            }
            auto missing = one_combat::advisor::importSilverRoot(
                centennialObservation("centennial-missing", std::nullopt));
            if (missing.ok == fix || (fix && missing.reason != "silver_unmapped_relic_state"))
                throw std::runtime_error(std::string("Centennial without usedThisCombat, flag=") + flag
                    + ": " + missing.reason);
        }
        unsetenv("STS_IMPORTER_CENTENNIAL_USED_FIX");

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

        auto negativeStrength = genericObservation(fixtures[0], "negative-strength-entry");
        negativeStrength["silverRoot"]["combat"]["monsters"][0]["powers"] = json::array({
            json{{"id", "Strength"}, {"amount", -2}}});
        auto negativeStrengthImported = one_combat::advisor::importSilverRoot(negativeStrength);
        if (!negativeStrengthImported.ok)
            throw std::runtime_error("negative Strength import failed: " + negativeStrengthImported.reason);
        auto negativeStrengthExpected = fixtures[0].wire;
        normalizeFirstObservationIdentity(negativeStrengthExpected);
        negativeStrengthExpected.monsters[0].strength = -2;
        negativeStrengthExpected.isolatedSearchSeed = negativeStrengthImported.wire.isolatedSearchSeed;
        if (!convertedStatesEqualForSearch(negativeStrengthExpected, negativeStrengthImported.wire))
            throw std::runtime_error("negative Strength parity failed");

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
        nativeSelection["silverRoot"]["combat"]["cardSelect"]["canPickZero"] = true;
        nativeSelectionImported = one_combat::advisor::importSilverRoot(nativeSelection);
        nativeSelectionExpected.cardSelect.canPickZero = true;
        if (!nativeSelectionImported.ok
            || !convertedStatesEqualForSearch(nativeSelectionExpected, nativeSelectionImported.wire))
            throw std::runtime_error("optional native selection parity failed");
        for (const auto &task : {"WARCRY", "FORETHOUGHT", "EXHAUST_ONE", "HEADBUTT", "ARMAMENTS", "DUAL_WIELD", "EXHUME", "SECRET_TECHNIQUE", "SECRET_WEAPON"}) {
            auto selection = genericObservation(fixtures[0], "single-live-selection");
            auto &combat = selection["silverRoot"]["combat"];
            const bool handSource = std::string(task) == "WARCRY" || std::string(task) == "FORETHOUGHT" || std::string(task) == "EXHAUST_ONE" || std::string(task) == "ARMAMENTS" || std::string(task) == "DUAL_WIELD";
            auto prototype = combat["hand"][0];
            json candidates = json::array();
            for (int i = 0; i < 3; ++i) {
                auto card = prototype;
                card["id"] = std::string(task) == "SECRET_TECHNIQUE" ? "Defend_R" : "Strike_R";
                card["uuid"] = "single-choice-" + std::to_string(i);
                candidates.push_back(card);
            }
            if (handSource) combat["hand"] = candidates;
            else if (std::string(task) == "EXHUME") combat["exhaust"] = json{{"unknown", candidates}};
            else if (std::string(task) == "HEADBUTT") combat["discard"] = json{{"unknown", candidates}};
            else combat["draw"] = json{{"unknown", candidates}};
            json choices = json::array();
            // Duplicate names remain distinct physical occurrences. Display
            // order deliberately differs from the native canonical pile order.
            for (int i : {2, 0, 1}) choices.push_back(json{{"uuid", candidates[i]["uuid"]},
                {"choiceIndex", static_cast<int>(choices.size()) + 1}});
            combat["cardSelect"] = json{{"task", task}, {"origin", handSource ? "HAND_SELECT" : "GRID"},
                {"cards", json::array()}, {"pickCount", 1}, {"canPickZero", false},
                {"canPickAnyNumber", false}, {"selectedBits", 0}, {"liveChoices", choices}};
            if(std::string(task)=="ARMAMENTS" || std::string(task)=="EXHUME" || std::string(task)=="DUAL_WIELD") {
                const bool armaments=std::string(task)=="ARMAMENTS",dualWield=std::string(task)=="DUAL_WIELD";
                auto held=prototype;held["uuid"]="held-card";held["id"]=armaments || dualWield?"Defend_R":"Exhume";
                held["upgraded"]=armaments;
                combat["cardSelect"]["heldCards"]=json::array({held});
                combat["cardSelect"]["upgradeVariant"]=false;
                combat["cardSelect"]["actionClass"]=armaments?"com.megacrit.cardcrawl.actions.unique.ArmamentsAction":dualWield?"com.megacrit.cardcrawl.actions.unique.DualWieldAction":"com.megacrit.cardcrawl.actions.unique.ExhumeAction";
                if(dualWield) combat["cardSelect"]["data0"]=2;
            }
            const std::map<std::string,std::string> sourceIds={{"WARCRY","Warcry"},{"FORETHOUGHT","Forethought"},
                {"EXHAUST_ONE","Burning Pact"},{"HEADBUTT","Headbutt"},{"ARMAMENTS","Armaments"},{"DUAL_WIELD","Dual Wield"},
                {"EXHUME","Exhume"},{"SECRET_TECHNIQUE","Secret Technique"},{"SECRET_WEAPON","Secret Weapon"}};
            auto source=prototype;source["id"]=sourceIds.at(task);source["uuid"]="interrupted-source";
            source["cost"]=source["costForTurn"]=1;
            CardQueueItemWire cleanup;cleanup.triggerOnUse=true;
            cleanup.exhaustOnUse=std::string(task)=="EXHUME" || std::string(task)=="WARCRY";
            combat["curCardQueueItem"]=producerQueueJson(cleanup);combat["curCardQueueItem"]["card"]=source;
            combat["pendingCardQueue"]=json::array();
            combat["pendingActionQueue"]=json::array({producerCleanupJson(combat["curCardQueueItem"])});
            combat["cardSelect"]["continuation"]="source_card_actions";
            one_combat::advisor::SilverImportContext context;
            const auto imported = one_combat::advisor::importSilverRoot(selection, context);
            if (!imported.ok) throw std::runtime_error("single selector import: " + imported.reason);
            auto selected = battleContextFromWire(imported.wire);
            const auto actions = sts::search::Action::enumerateCardSelectActions(selected);
            if (actions.empty()) throw std::runtime_error("single selector has no legal action");
            const auto semantic = sts::search::semanticFromSearchAction(selected, actions[0]);
            const auto lowered = one_combat::advisor::selectedLiveAction(semantic, context, selection);
            const auto expected = std::find_if(choices.begin(), choices.end(), [&](const auto &choice) {
                return context.cardIds.at(choice.at("uuid").template get<std::string>()) == semantic.card.uniqueId;
            });
            if (expected == choices.end() || lowered.value("choiceIndex", 0) != expected->at("choiceIndex").get<int>())
                throw std::runtime_error("single selector guessed pile order instead of UUID occurrence");
            actions[0].execute(selected);
            if (selected.inputState != InputState::PLAYER_NORMAL)
                throw std::runtime_error("single selector failed to resume combat");
            const auto &cleanupPile=cleanup.exhaustOnUse?selected.cards.exhaustPile:selected.cards.discardPile;
            if(std::count_if(cleanupPile.begin(),cleanupPile.end(),[&](const auto &card) {
                    return card.uniqueId==context.cardIds.at("interrupted-source");})!=1)
                throw std::runtime_error("typed single selector did not clean up its exact physical source once");
            if(std::string(task)=="ARMAMENTS" && (selected.cards.cardsInHand!=4
                    || selected.cards.hand[3].uniqueId!=context.cardIds.at("held-card")
                    || !selected.cards.hand[2].isUpgraded()))
                throw std::runtime_error("Armaments omitted held cards or changed Java return order");
            if(std::string(task)=="DUAL_WIELD" && (selected.cards.cardsInHand!=6
                    || selected.cards.hand[2].uniqueId!=context.cardIds.at("held-card")
                    || selected.cards.hand[3].uniqueId==semantic.card.uniqueId
                    || selected.cards.hand[4].uniqueId==selected.cards.hand[3].uniqueId))
                throw std::runtime_error("Dual Wield failed vanilla held-card/copy identity semantics");
            if(std::string(task)=="EXHUME" && std::none_of(selected.cards.exhaustPile.begin(),selected.cards.exhaustPile.end(),
                    [&](const auto &card){return card.uniqueId==context.cardIds.at("held-card");}))
                throw std::runtime_error("Exhume lost temporarily excluded Exhume card");
            for (int corruption = 0; corruption < 5; ++corruption) {
                auto invalid = selection;
                auto &bad = invalid["silverRoot"]["combat"]["cardSelect"];
                if (corruption == 0) bad["liveChoices"].erase(0);
                if (corruption == 1) bad["liveChoices"][1]["uuid"] = bad["liveChoices"][0]["uuid"];
                if (corruption == 2) bad["liveChoices"][0]["uuid"] = "not-in-source";
                if (corruption == 3) bad["pickCount"] = 2;
                if (corruption == 4) bad["liveChoices"][0]["choiceIndex"] = 3;
                const auto rejected = one_combat::advisor::importSilverRoot(invalid);
                if (rejected.ok || rejected.reason != "silver_selection_live_choices")
                    throw std::runtime_error("invalid live selector identity set accepted");
            }
            auto absent = semantic;
            absent.card.uniqueId = -1;
            if (!one_combat::advisor::selectedLiveAction(absent, context, selection).is_null())
                throw std::runtime_error("missing physical selection identity was lowered");
        }
        for(bool corruption:{false,true}) for(int relicTail:{0,1,2}) {
            // Vanilla Burning Pact queues ExhaustAction, DrawCardAction(2),
            // then the unstarted UseCardAction. Cleanup must follow that draw.
            auto observation=genericObservation(fixtures[0],"burning-pact-public-action-tail");
            auto &combat=observation["silverRoot"]["combat"];
            auto source=combat["hand"][0];source["id"]="Burning Pact";source["uuid"]="played-pact";
            source["cost"]=source["costForTurn"]=1;
            CardQueueItemWire queue;queue.triggerOnUse=true;queue.exhaustOnUse=corruption;
            if(corruption)combat["playerPowers"]=json::array({json{{"id","Corruption"},{"amount",1}}});
            combat["curCardQueueItem"]=producerQueueJson(queue);combat["curCardQueueItem"]["card"]=source;
            combat["pendingCardQueue"]=json::array();
            json choices=json::array();
            for(const auto &card:combat["hand"]) choices.push_back(json{{"uuid",card.at("uuid")},{"choiceIndex",choices.size()+1}});
            combat["cardSelect"]={{"task","EXHAUST_ONE"},{"origin","HAND_SELECT"},{"pickCount",1},
                {"canPickZero",false},{"canPickAnyNumber",false},{"selectedBits",0},{"liveChoices",choices},
                {"continuation","source_card_actions"}};
            combat["pendingActionQueue"]=json::array({json{{"kind","DRAW"},{"amount",2}}});
            if(relicTail==1)combat["pendingActionQueue"].push_back(json{{"kind","BUFF_PLAYER"},{"power","Pen Nib"},{"amount",1},{"sourceMonster",false}});
            if(relicTail==2) {
                combat["playerPowers"].push_back(json{{"id","Pen Nib"},{"amount",1}});
                combat["playerPowers"].push_back(json{{"id","Weakened"},{"amount",2},{"justApplied",false}});
                combat["playerPowers"].push_back(json{{"id","Frail"},{"amount",2},{"justApplied",false}});
                combat["playerPowers"].push_back(json{{"id","Strength"},{"amount",-2}});
                combat["playerPowers"].push_back(json{{"id","Dexterity"},{"amount",2}});
                combat["pendingActionQueue"].push_back(json{{"kind","REMOVE_PEN_NIB"}});
                combat["pendingActionQueue"].push_back(json{{"kind","REMOVE_PLAYER_DEBUFFS"}});
            }
            combat["pendingActionQueue"].push_back(producerCleanupJson(combat["curCardQueueItem"]));
            one_combat::advisor::SilverImportContext context;
            const auto imported=one_combat::advisor::importSilverRoot(observation,context);
            if(!imported.ok)throw std::runtime_error("Burning Pact typed tail import: "+imported.reason);
            auto selected=battleContextFromWire(json(imported.wire).get<silver_bridge::BattleStateWire>());
            if(json(wireFromSearchState(selected,searchContextFromWire(imported.wire)).pendingActionQueue)!=json(imported.wire.pendingActionQueue))
                throw std::runtime_error("source relic tail lost typed queue through JSON/native roundtrip");
            const int handBefore=selected.cards.cardsInHand,drawBefore=selected.cards.drawPile.size();
            const int cardBefore=selected.player.cardsPlayedThisTurn;
            const int exhausted=selected.cards.hand[0].uniqueId;
            sts::search::Action(sts::search::ActionType::SINGLE_CARD_SELECT,0).execute(selected);
            if(selected.inputState!=InputState::PLAYER_NORMAL || selected.cards.cardsInHand!=handBefore+1
                    || selected.cards.drawPile.size()!=drawBefore-2 || selected.player.cardsPlayedThisTurn!=cardBefore
                    || std::count_if(selected.cards.exhaustPile.begin(),selected.cards.exhaustPile.end(),[&](const auto &c){return c.uniqueId==exhausted;})!=1
                    || std::count_if((corruption?selected.cards.exhaustPile:selected.cards.discardPile).begin(),
                        (corruption?selected.cards.exhaustPile:selected.cards.discardPile).end(),
                        [&](const auto &c){return c.uniqueId==context.cardIds.at("played-pact");})!=1)
                throw std::runtime_error("Burning Pact tail repeated card use, lost draw, or lost cleanup");
            if(relicTail==1 && !selected.player.hasStatus<PlayerStatus::PEN_NIB>())
                throw std::runtime_error("pending Pen Nib application missing");
            if(relicTail==2 && (selected.player.hasStatus<PlayerStatus::PEN_NIB>() || selected.player.hasStatus<PlayerStatus::WEAK>()
                    || selected.player.hasStatus<PlayerStatus::FRAIL>() || selected.player.strength!=0 || selected.player.dexterity!=2))
                throw std::runtime_error("pending Pen Nib removal / Pellets cleanse lost typed effects or removed buff");
            for(int defect=0;defect<8;++defect) {
                auto bad=observation;auto &c=bad["silverRoot"]["combat"];
                if(defect==0)c["pendingActionQueue"].back()["uuid"]="wrong-physical-card";
                if(defect==1)c["pendingActionQueue"].back()["unstarted"]=false;
                if(defect==2)c["pendingActionQueue"].back()["purgeOnUse"]=true;
                if(defect==3)c["pendingActionQueue"].push_back(c["pendingActionQueue"].back());
                if(defect==4)c.erase("pendingCardQueue");
                if(defect==5)c["curCardQueueItem"]["card"]["id"]="Anger";
                if(defect==6)c["cardSelect"]["origin"]="UNKNOWN";
                if(defect==7)c["pendingActionQueue"].erase(c["pendingActionQueue"].end()-1);
                if(one_combat::advisor::importSilverRoot(bad).ok)throw std::runtime_error("unqualified source cleanup accepted");
            }
        }
        for (int count : {1,2}) for (int handCount : {8,9,10}) {
            auto observation=genericObservation(fixtures[0],"liquid-memories-ordered-choice");
            auto &combat=observation["silverRoot"]["combat"];
            const auto prototype=combat["hand"][0];
            combat["hand"]=json::array();
            for(int i=0;i<handCount;++i) {auto c=prototype;c["uuid"]="liquid-hand-"+std::to_string(i);combat["hand"].push_back(c);}
            json discard=json::array(), choices=json::array();
            for(int i=0;i<3;++i) {auto c=prototype;c["uuid"]="liquid-discard-"+std::to_string(i);discard.push_back(c);}
            for(int i:{2,0,1}) choices.push_back(json{{"uuid",discard[i]["uuid"]},{"choiceIndex",choices.size()+1}});
            combat["discard"]=json{{"unknown",discard}};
            combat["cardSelect"]=json{{"task","LIQUID_MEMORIES_POTION"},{"origin","GRID"},
                {"actionClass","com.megacrit.cardcrawl.actions.common.BetterDiscardPileToHandAction"},
                {"pickCount",count},{"selectedCount",0},{"selectedBits",0},{"canPickZero",false},
                {"canPickAnyNumber",false},{"optional",false},{"newCost",0},{"setCostToZero",true},
                {"continuation","none"},{"liveChoices",choices},{"cards",json::array()}};
            one_combat::advisor::SilverImportContext context;
            const auto imported=one_combat::advisor::importSilverRoot(observation,context);
            if(!imported.ok)throw std::runtime_error("Liquid Memories import: "+imported.reason);
            auto root=battleContextFromWire(imported.wire);
            const auto actions=sts::search::Action::enumerateCardSelectActions(root);
            if(actions.size()!=static_cast<std::size_t>(count==1?3:6)) throw std::runtime_error("Liquid pair enumeration lost order");
            for(const auto &action:actions) {
                if(!action.isValidAction(root)) throw std::runtime_error("invalid Liquid pair enumerated");
                const auto semantic=sts::search::semanticFromSearchAction(root,action);
                const auto lowered=one_combat::advisor::selectedLiveAction(semantic,context,observation);
                if(count==2 && (lowered.value("kind","")!="grid_card_select" || lowered.at("cardUuids").size()!=2))
                    throw std::runtime_error("Liquid pair not lowered atomically");
                if(count==1 && lowered.value("kind","")!="choose") throw std::runtime_error("Liquid single not lowered");
                const auto resolved=resolveSilverSemanticAction(root,semantic);
                if(!resolved.ok || resolved.action!=action) throw std::runtime_error("Liquid pair semantic roundtrip failed");
                auto selected=root;
                resolved.action.execute(selected);
                const int moved=std::min(count,10-handCount);
                if(selected.cards.cardsInHand!=handCount+moved || selected.cards.discardPile.size()!=3-moved)
                    throw std::runtime_error("Liquid capacity changed discard cards");
                if(moved>0 && (selected.cards.hand[handCount].uniqueId!=root.cards.discardPile[action.getSelectIdx()].uniqueId
                        || selected.cards.hand[handCount].costForTurn!=0)) throw std::runtime_error("Liquid first card/order/cost mismatch");
                if(moved>1 && (selected.cards.hand[handCount+1].uniqueId!=root.cards.discardPile[action.getTargetIdx()-1].uniqueId
                        || selected.cards.hand[handCount+1].costForTurn!=0)) throw std::runtime_error("Liquid second card/order/cost mismatch");
                if(handCount==10) for(const auto &card:selected.cards.discardPile)
                    if(card.costForTurn!=prototype["costForTurn"].get<int>()) throw std::runtime_error("Liquid modified overflow card cost");
            }
            auto automatic=root;automatic.cards.discardPile.resize(count);automatic.cards.cardsInHand=8;
            Actions::BetterDiscardPileToHandAction(count,CardSelectTask::LIQUID_MEMORIES_POTION)(automatic);
            if(automatic.cards.cardsInHand!=8+count || !automatic.cards.discardPile.empty())
                throw std::runtime_error("Liquid all-discard branch omitted Sacred Bark second card");
            for(int bad=0;bad<5;++bad) {auto invalid=observation;auto &selection=invalid["silverRoot"]["combat"]["cardSelect"];
                if(bad==0)selection["newCost"]=1;if(bad==1)selection["optional"]=true;
                if(bad==2)selection["selectedCount"]=1;if(bad==3)selection["pickCount"]=3;
                if(bad==4) {selection["liveChoices"]=json::array({choices[0]});
                    invalid["silverRoot"]["combat"]["discard"]=json{{"unknown",json::array({discard[2]})}};}
                if(one_combat::advisor::importSilverRoot(invalid).ok)throw std::runtime_error("Liquid unsupported variant accepted");}
        }
        for (const auto &task : {"GAMBLE", "EXHAUST_MANY"}) for (int mask : {0, 1, 5, 7}) {
            auto observation = genericObservation(fixtures[0], "multi-hand-transaction");
            auto &combat = observation["silverRoot"]["combat"];
            const auto prototype = combat["hand"][0];
            combat["hand"] = json::array();
            json choices = json::array();
            for (int i=0;i<3;++i) {
                auto card=prototype;card["id"]="Strike_R";card["uuid"]="multi-"+std::to_string(i);
                combat["hand"].push_back(card);
                choices.push_back(json{{"uuid",card["uuid"]},{"choiceIndex",i+1}});
            }
            const bool gamble=std::string(task)=="GAMBLE";
            combat["cardSelect"]=json{{"task",task},{"origin","HAND_SELECT"},{"pickCount",gamble?99:3},
                {"canPickZero",true},{"canPickAnyNumber",true},{"selectedBits",0},{"selectedCount",0},
                {"liveChoices",choices},{"continuation","none"},{"cards",json::array()},
                {"actionClass",gamble?"com.megacrit.cardcrawl.actions.unique.GamblingChipAction":"com.megacrit.cardcrawl.actions.common.ExhaustAction"}};
            one_combat::advisor::SilverImportContext context;
            const auto imported=one_combat::advisor::importSilverRoot(observation,context);
            if(!imported.ok) throw std::runtime_error("multi hand import: "+imported.reason);
            auto selected=battleContextFromWire(imported.wire);
            const sts::search::Action action(sts::search::ActionType::MULTI_CARD_SELECT,mask);
            if(!action.isValidAction(selected)) throw std::runtime_error("multi hand subset rejected");
            const auto semantic=sts::search::semanticFromSearchAction(selected,action);
            const auto lowered=one_combat::advisor::selectedLiveAction(semantic,context,observation);
            json expected=json::array();
            for(int i=0;i<3;++i) if(mask&(1<<i)) expected.push_back("multi-"+std::to_string(i));
            if(lowered.value("kind","")!="card_select" || lowered.at("cardUuids")!=expected)
                throw std::runtime_error("multi hand physical transaction mismatch");
            const auto oldDiscardCount=selected.player.cardsDiscardedThisTurn;
            const auto oldPile=gamble?selected.cards.discardPile.size():selected.cards.exhaustPile.size();
            action.execute(selected);
            const auto &pile=gamble?selected.cards.discardPile:selected.cards.exhaustPile;
            if(pile.size()!=oldPile+expected.size() || selected.inputState!=InputState::PLAYER_NORMAL)
                throw std::runtime_error("multi hand did not resolve selected cards");
            for(std::size_t i=0;i<expected.size();++i)
                if(pile[oldPile+i].uniqueId!=context.cardIds.at(expected[i].get<std::string>()))
                    throw std::runtime_error("multi hand changed selected trigger order");
            if(gamble && selected.player.cardsDiscardedThisTurn != oldDiscardCount + expected.size())
                throw std::runtime_error("Gamble did not count each manual discard");
            if(selected.cards.cardsInHand!=(gamble?3:3-static_cast<int>(expected.size())))
                throw std::runtime_error("multi hand draw/exhaust count mismatch");
            auto bad=observation;bad["silverRoot"]["combat"]["cardSelect"]["continuation"]="unknown";
            if(one_combat::advisor::importSilverRoot(bad).ok) throw std::runtime_error("multi hand ignored pending continuation");
        }
        // Problem 28: Toy Ornithopter queues its potion heal behind Gambler's
        // Brew's GamblingChipAction, so the live hand selection carries it.
        for (const char *flag : {"1", "0"}) {
            setenv("STS_SELECTION_TOY_HEAL_FIX", flag, 1);
            auto observation = genericObservation(fixtures[0], "gamble-toy-heal-tail");
            auto &combat = observation["silverRoot"]["combat"];
            combat["relics"].push_back(json{{"id","Toy Ornithopter"},{"counter",-1},{"usedUp",false}});
            const auto prototype = combat["hand"][0];
            combat["hand"] = json::array();
            json choices = json::array();
            for (int i=0;i<3;++i) {
                auto card=prototype;card["id"]="Strike_R";card["uuid"]="toy-"+std::to_string(i);
                combat["hand"].push_back(card);
                choices.push_back(json{{"uuid",card["uuid"]},{"choiceIndex",i+1}});
            }
            combat["cardSelect"]=json{{"task","GAMBLE"},{"origin","HAND_SELECT"},{"pickCount",99},
                {"canPickZero",true},{"canPickAnyNumber",true},{"selectedBits",0},{"selectedCount",0},
                {"liveChoices",choices},{"continuation","public_actions"},{"cards",json::array()},
                {"actionClass","com.megacrit.cardcrawl.actions.unique.GamblingChipAction"}};
            combat["pendingActionQueue"]=json::array({json{{"kind","HEAL_PLAYER"},{"amount",5}}});
            const auto imported=one_combat::advisor::importSilverRoot(observation);
            if(std::string(flag)=="0") {
                if(imported.ok || imported.reason!="silver_selection_pending_actions")
                    throw std::runtime_error("STS_SELECTION_TOY_HEAL_FIX=0 accepted the Toy heal tail");
                continue;
            }
            if(!imported.ok) throw std::runtime_error("Toy heal tail import: "+imported.reason);
            if(!imported.wire.pendingActionQueueObserved || imported.wire.pendingActionQueue.size()!=1
                    || imported.wire.pendingActionQueue[0].kind!=silver_bridge::PendingActionKind::HEAL_PLAYER)
                throw std::runtime_error("Toy heal tail not carried on the wire");
            auto selected=battleContextFromWire(imported.wire);
            selected.player.curHp=selected.player.maxHp-10;
            const auto before=selected.player.curHp;
            sts::search::Action(sts::search::ActionType::MULTI_CARD_SELECT,1).execute(selected);
            if(selected.inputState!=InputState::PLAYER_NORMAL || selected.player.curHp!=before+5
                    || selected.cards.cardsInHand!=3)
                throw std::runtime_error("Toy heal tail did not heal after the Gamble");
            for(int amount:{4,0}) {auto bad=observation;
                bad["silverRoot"]["combat"]["pendingActionQueue"][0]["amount"]=amount;
                if(one_combat::advisor::importSilverRoot(bad).ok)throw std::runtime_error("unqualified heal tail accepted");}
        }
        unsetenv("STS_SELECTION_TOY_HEAL_FIX");
        for (int mask : {0, 1, 5, 7}) {
            auto observation = genericObservation(fixtures[0], "upgraded-forethought-transaction");
            auto &combat = observation["silverRoot"]["combat"];
            auto prototype = combat["hand"][0];
            combat["hand"] = json::array();
            json choices = json::array();
            for (int i = 0; i < 3; ++i) {
                auto card = prototype; card["uuid"] = "forethought-card-" + std::to_string(i);
                card["id"] = i == 0 ? "Strike_R" : i == 1 ? "Defend_R" : "Anger";
                card["cost"] = card["costForTurn"] = i == 2 ? 0 : 1;
                combat["hand"].push_back(card);
                choices.push_back(json{{"uuid", card["uuid"]}, {"choiceIndex", i + 1}});
            }
            auto played = prototype; played["id"] = "Forethought"; played["uuid"] = "interrupted-forethought";
            played["upgraded"] = true; played["cost"] = played["costForTurn"] = 0;
            CardQueueItemWire queue;
            combat["curCardQueueItem"] = producerQueueJson(queue);
            combat["curCardQueueItem"]["card"] = played;
            combat["cardSelect"] = json{{"task", "FORETHOUGHT"}, {"origin", "HAND_SELECT"},
                {"canPickAnyNumber", true}, {"canPickZero", true}, {"pickCount", 99}, {"selectedBits", 0},
                {"selectedCount", 0}, {"actionClass", "com.megacrit.cardcrawl.actions.unique.ForethoughtAction"},
                {"cards", json::array()}, {"liveChoices", choices}};
            one_combat::advisor::SilverImportContext context;
            const auto imported = one_combat::advisor::importSilverRoot(observation, context);
            if (!imported.ok) throw std::runtime_error("upgraded Forethought import: " + imported.reason);
            auto selected = battleContextFromWire(imported.wire);
            const auto beforeDraw = selected.cards.drawPile.size();
            const auto actions = sts::search::Action::enumerateCardSelectActions(selected);
            if (std::any_of(actions.begin(), actions.end(), [](const auto &a) {
                    return a.getActionType() != sts::search::ActionType::MULTI_CARD_SELECT;
                })) throw std::runtime_error("upgraded Forethought exposed scalar choices");
            const sts::search::Action action(sts::search::ActionType::MULTI_CARD_SELECT, mask);
            if (!action.isValidAction(selected)) throw std::runtime_error("upgraded Forethought subset rejected");
            const auto semantic = sts::search::semanticFromSearchAction(selected, action);
            const auto lowered = one_combat::advisor::selectedLiveAction(semantic, context, observation);
            json expected = json::array();
            for (int i = 0; i < 3; ++i) if (mask & (1 << i)) expected.push_back("forethought-card-" + std::to_string(i));
            if (lowered.value("kind", "") != "card_select" || lowered.at("cardUuids") != expected)
                throw std::runtime_error("Forethought atomic physical-card plan mismatch");
            const auto resolved = resolveSilverSemanticAction(selected, semantic);
            if (!resolved.ok) throw std::runtime_error("Forethought semantic subset did not resolve");
            if (mask == 5) {
                auto manual = selected;
                fixed_list<int,10> reverse; reverse.push_back(2); reverse.push_back(0);
                manual.chooseForethoughtCards(reverse);
                if (manual.cards.cardsInHand != 1
                        || manual.cards.hand[0].uniqueId != selected.cards.hand[1].uniqueId
                        || manual.cards.drawPile[0].uniqueId != selected.cards.hand[2].uniqueId
                        || manual.cards.drawPile[1].uniqueId != selected.cards.hand[0].uniqueId)
                    throw std::runtime_error("unordered manual Forethought selection changed identity/order");
                for (int invalid : {-1, 0, 3}) {
                    auto rejected = selected;
                    fixed_list<int,10> indices; indices.push_back(0); indices.push_back(invalid);
                    bool threw = false;
                    try { rejected.chooseForethoughtCards(indices); }
                    catch (const std::invalid_argument &) { threw = true; }
                    if (!threw || rejected.cards.cardsInHand != selected.cards.cardsInHand
                            || rejected.cards.drawPile.size() != selected.cards.drawPile.size())
                        throw std::runtime_error("malformed manual Forethought mutated cards");
                }
            }
            resolved.action.execute(selected);
            if (selected.cards.cardsInHand != 3 - static_cast<int>(expected.size())
                || selected.cards.drawPile.size() != beforeDraw + expected.size()
                || selected.inputState != InputState::PLAYER_NORMAL)
                throw std::runtime_error("Forethought subset/card conservation failure");
            int bottom = 0;
            for (int i = 2; i >= 0; --i) if (mask & (1 << i)) {
                const auto &card = selected.cards.drawPile[bottom++];
                if (card.uniqueId != context.cardIds.at("forethought-card-" + std::to_string(i))
                    || card.freeToPlayOnce != (i != 2))
                    throw std::runtime_error("Forethought lost bottom order or cost-dependent free flag");
            }
            if (std::none_of(selected.cards.discardPile.begin(), selected.cards.discardPile.end(), [](const auto &card) {
                    return card.id == CardId::FORETHOUGHT;
                })) throw std::runtime_error("Forethought interrupted-card cleanup missing");
            auto native = battleContextFromWire(fixtures[0].wire);
            native.cards.cardsInHand = 1;
            Actions::ForethoughtAction(true)(native);
            if (native.inputState != InputState::CARD_SELECT || !native.cardSelectInfo.canPickAnyNumber
                || !native.cardSelectInfo.canPickZero || native.cards.cardsInHand != 1)
                throw std::runtime_error("upgraded Forethought auto-selected the sole hand card");
        }
        const auto offerSelection = [](int copies, const char *continuation) {
            return json{{"task", "DISCOVERY"}, {"origin", "CARD_REWARD"},
                {"continuation", continuation}, {"cards", json::array({"Anger", "Shrug It Off", "Flash of Steel"})},
                {"data0", copies}, {"pickCount", 1}, {"canPickZero", false},
                {"canPickAnyNumber", false}, {"setCostToZero", true}, {"selectedBits", 0}};
        };
        for (int copies : {1, 2}) {
            auto offer = genericObservation(fixtures[0], "typed-potion-skip");
            auto &selection = offer["silverRoot"]["combat"]["cardSelect"];
            selection = offerSelection(copies, "none");
            selection["canPickZero"] = true;
            one_combat::advisor::SilverImportContext context;
            auto imported = one_combat::advisor::importSilverRoot(offer, context);
            if (!imported.ok) throw std::runtime_error("typed potion skip import: " + imported.reason);
            auto selected = battleContextFromWire(imported.wire);
            const int nextId = selected.cards.nextUniqueCardId;
            const int handCount = selected.cards.cardsInHand;
            const auto actions = sts::search::Action::enumerateCardSelectActions(selected);
            if (actions.size() != 4) throw std::runtime_error("typed potion Skip action missing");
            const auto semantic = sts::search::semanticFromSearchAction(selected, actions[3]);
            if (!semantic.skipCardSelect || one_combat::advisor::selectedLiveAction(semantic, context, offer)
                    .value("kind", "") != "skip") throw std::runtime_error("typed potion skip lowering failed");
            const auto resolved = resolveSilverSemanticAction(selected, semantic);
            if (!resolved.ok) throw std::runtime_error("typed potion Skip semantic roundtrip failed");
            resolved.action.execute(selected);
            if (selected.cards.cardsInHand != handCount || selected.cards.nextUniqueCardId != nextId
                || selected.inputState != InputState::PLAYER_NORMAL)
                throw std::runtime_error("typed potion Skip generated a card or failed to resume");
            selection["canPickZero"] = false;
            if (!one_combat::advisor::selectedLiveAction(semantic, context, offer).is_null())
                throw std::runtime_error("non-skippable reward accepted Skip");
        }
        {
            auto offer = genericObservation(fixtures[0], "normal-cost-toolbox-offer");
            auto &selection = offer["silverRoot"]["combat"]["cardSelect"];
            selection = offerSelection(1, "none");
            selection["setCostToZero"] = false;
            auto imported = one_combat::advisor::importSilverRoot(offer);
            if (!imported.ok) throw std::runtime_error("normal-cost offer import: " + imported.reason);
            auto selected = battleContextFromWire(imported.wire);
            if (wireFromSearchState(selected, searchContextFromWire(imported.wire)).cardSelect.setCostToZero)
                throw std::runtime_error("normal-cost offer flag lost in native roundtrip");
            const int originalCount = selected.cards.cardsInHand;
            sts::search::Action(sts::search::ActionType::SINGLE_CARD_SELECT, 1).execute(selected);
            if (selected.cards.hand[originalCount].id != CardId::SHRUG_IT_OFF
                    || selected.cards.hand[originalCount].costForTurn != 1)
                throw std::runtime_error("Toolbox card incorrectly made free");
        }
        {
            auto native=battleContextFromWire(fixtures[0].wire);
            native.player.buff<PlayerStatus::INTANGIBLE>(1);
            if(native.player.wasJustApplied<PlayerStatus::INTANGIBLE>())throw std::runtime_error("vanilla Intangible gained nonexistent justApplied metadata");
            native.player.applyAtEndOfRoundPowers();
            if(native.player.hasStatus<PlayerStatus::INTANGIBLE>())throw std::runtime_error("Intangible failed vanilla end-round expiration");
        }
        {
            auto offer=genericObservation(fixtures[0],"toolbox-status-and-mark-of-pain-tail");auto &combat=offer["silverRoot"]["combat"];
            combat["cardSelect"]=offerSelection(1,"toolbox_actions");combat["cardSelect"]["setCostToZero"]=false;
            combat["pendingActionQueue"]=json::array({json{{"kind","SHUFFLE_WOUNDS"},{"amount",2}},
                json{{"kind","DEBUFF_ALL_ENEMY"},{"power","Weakened"},{"amount",1},{"sourceMonster",false}},
                json{{"kind","DEBUFF_ALL_ENEMY"},{"power","Vulnerable"},{"amount",1},{"sourceMonster",false}},
                json{{"kind","DRAW"},{"amount",1}},json{{"kind","DEBUFF_PLAYER"},{"power","Weakened"},{"amount",1},{"sourceMonster",false}}});
            combat["monsters"][0]["powers"].push_back(json{{"id","Artifact"},{"amount",1}});
            const auto imported=one_combat::advisor::importSilverRoot(offer);
            if(!imported.ok)throw std::runtime_error("typed startup powers import: "+imported.reason);
            auto selected=battleContextFromWire(imported.wire);
            sts::search::Action(sts::search::ActionType::SINGLE_CARD_SELECT,1).execute(selected);
            const auto &monster=selected.monsters.arr[0];
            if(monster.getStatus<MonsterStatus::ARTIFACT>()!=0 || monster.hasStatus<MonsterStatus::WEAK>()
                    || monster.getStatus<MonsterStatus::VULNERABLE>()!=1 || selected.player.getStatus<PlayerStatus::WEAK>()!=1
                    || selected.player.wasJustApplied<PlayerStatus::WEAK>())throw std::runtime_error("typed starter debuff order/artifact mismatch");
            int wounds=0;for(int n=0;n<selected.cards.cardsInHand;++n)wounds+=selected.cards.hand[n].id==CardId::WOUND;
            for(const auto &card:selected.cards.drawPile)wounds+=card.id==CardId::WOUND;
            if(wounds!=2)throw std::runtime_error("Mark of Pain did not create two fair shuffled Wounds");
            auto invalid=offer;invalid["silverRoot"]["combat"]["pendingActionQueue"][0]["amount"]=3;
            if(one_combat::advisor::importSilverRoot(invalid).ok)throw std::runtime_error("unqualified Wound count accepted");
        }
        for(int subset:{0,1}) {
            auto offer=genericObservation(fixtures[0],"toolbox-typed-relic-tail");auto &combat=offer["silverRoot"]["combat"];
            const auto prototype=combat["hand"][0];combat["hand"]=json::array();json draw=json::array();
            for(int i=0;i<7;++i){auto c=prototype;c["uuid"]="typed-draw-"+std::to_string(i);draw.push_back(c);}
            combat["draw"]=json{{"unknown",draw}};
            combat["cardSelect"]=offerSelection(1,"toolbox_actions");combat["cardSelect"]["setCostToZero"]=false;
            combat["pendingActionQueue"]=json::array({json{{"kind","DRAW"},{"amount",5}},json{{"kind","GAMBLE"}},
                json{{"kind","DRAW"},{"amount",2}},json{{"kind","UPGRADE_RANDOM"}},json{{"kind","GAIN_BLOCK"},{"amount",10}},
                json{{"kind","GAIN_ENERGY"},{"amount",1}},json{{"kind","BUFF_PLAYER"},{"power","Strength"},{"amount",2},{"sourceMonster",false}},
                json{{"kind","BUFF_PLAYER"},{"power","Artifact"},{"amount",1},{"sourceMonster",false}},
                json{{"kind","DEBUFF_PLAYER"},{"power","Flex"},{"amount",2},{"sourceMonster",false}},
                json{{"kind","DAMAGE_ALL"},{"amount",3}},json{{"kind","DAMAGE_RANDOM"},{"amount",3}}});
            const auto imported=one_combat::advisor::importSilverRoot(offer);
            if(!imported.ok)throw std::runtime_error("typed Toolbox tail import: "+imported.reason);
            auto native=battleContextFromWire(imported.wire);const auto beforeEnergy=native.player.energy,beforeHp=native.monsters.arr[0].curHp;
            const auto beforeStrength=native.player.strength,beforeBlock=native.player.block;
            sts::search::Action(sts::search::ActionType::SINGLE_CARD_SELECT,1).execute(native);
            if(native.inputState!=InputState::CARD_SELECT || native.cardSelectInfo.cardSelectTask!=CardSelectTask::GAMBLE
                    || native.cards.cardsInHand!=6 || native.player.strength!=beforeStrength)
                throw std::runtime_error("typed tail failed to pause at Gambling Chip in queue order");
            const auto wire=wireFromSearchState(native,searchContextFromWire(imported.wire));
            if(!wire.pendingActionQueueObserved || wire.pendingActionQueue.size()!=9)
                throw std::runtime_error("typed queue lost after first selection");
            auto restored=battleContextFromWire(json(wire).get<silver_bridge::BattleStateWire>());
            sts::search::Action(sts::search::ActionType::MULTI_CARD_SELECT,subset).execute(restored);
            if(restored.inputState!=InputState::PLAYER_NORMAL || restored.cards.cardsInHand!=8
                    || restored.player.energy!=beforeEnergy+1 || restored.player.strength!=beforeStrength+2
                    || restored.player.block!=beforeBlock+10 || restored.player.artifact!=0
                    || restored.player.hasStatus<PlayerStatus::LOSE_STRENGTH>() || restored.monsters.arr[0].curHp!=beforeHp-6)
                throw std::runtime_error("typed relic tail lost ordered effects after Gambling Chip");
            int upgraded=0;for(int n=0;n<restored.cards.cardsInHand;++n)upgraded+=restored.cards.hand[n].isUpgraded();
            if(upgraded!=1)throw std::runtime_error("Warped Tongs pending random upgrade not applied once");
            for(int defect=0;defect<4;++defect){auto bad=offer;auto &c=bad["silverRoot"]["combat"];
                if(defect==0)c["pendingActionQueue"][0]["kind"]="ROLL_PRIVATE_MOVE";
                if(defect==1)c["pendingActionQueue"][0]["amount"]=1.5;
                if(defect==2)c["pendingActionQueue"][6]["power"]="Echo Form";
                if(defect==3)c["cardSelect"]["drawsAfter"]=json::array({5});
                if(one_combat::advisor::importSilverRoot(bad).ok)throw std::runtime_error("unsupported or duplicated typed continuation accepted");}
        }
        {
            auto offer = genericObservation(fixtures[0], "toolbox-before-opening-draw");
            auto &combat = offer["silverRoot"]["combat"];
            auto prototype = combat["hand"][0];
            combat["hand"] = json::array();
            json draw = json::array();
            for (int i = 0; i < 7; ++i) {
                auto card = prototype; card["uuid"] = "opening-draw-" + std::to_string(i);
                draw.push_back(card);
            }
            combat["draw"] = json{{"unknown", draw}};
            combat["cardSelect"] = offerSelection(1, "toolbox_draw");
            combat["cardSelect"]["setCostToZero"] = false;
            combat["cardSelect"]["drawAfter"] = 5;
            auto bagOffer = offer;
            bagOffer["silverRoot"]["combat"]["cardSelect"].erase("drawAfter");
            bagOffer["silverRoot"]["combat"]["cardSelect"]["drawsAfter"] = json::array({5, 2});
            const auto bagImported = one_combat::advisor::importSilverRoot(bagOffer);
            if (!bagImported.ok) throw std::runtime_error("Toolbox Bag import: " + bagImported.reason);
            for (int defect = 0; defect < 3; ++defect) {
                auto bad = bagOffer;
                auto &selection = bad["silverRoot"]["combat"]["cardSelect"];
                if (defect == 0) selection["drawsAfter"] = json::array({5, 2.5});
                if (defect == 1) selection["drawAfter"] = 5;
                if (defect == 2) selection["origin"] = "HAND_SELECT";
                if (one_combat::advisor::importSilverRoot(bad).ok)
                    throw std::runtime_error("malformed ordered Toolbox continuation accepted");
            }
            auto bag = battleContextFromWire(bagImported.wire);
            const auto bagWire = wireFromSearchState(bag, searchContextFromWire(bagImported.wire));
            if (bagWire.cardSelect.drawsAfter != std::vector<int>({5, 2}))
                throw std::runtime_error("Toolbox separate draw actions lost in wire");
            bag.cards.drawPile.assignConcrete(std::vector<CardInstance>(bag.cards.drawPile.begin(), bag.cards.drawPile.end()));
            const auto bagBytes = serializeBattleContext(bag);
            const auto bagRestored = deserializeBattleContext(bagBytes.data(), bagBytes.size());
            if (bagRestored.cardSelectInfo.drawsAfter != std::vector<int>({5, 2}))
                throw std::runtime_error("Toolbox separate draws lost in binary snapshot");
            sts::search::Action(sts::search::ActionType::SINGLE_CARD_SELECT, 1).execute(bag);
            if (bag.cards.cardsInHand != 8 || !bag.cards.drawPile.empty()
                    || bag.cards.hand[0].id != CardId::SHRUG_IT_OFF || bag.cards.hand[0].costForTurn != 1
                    || !bag.cardSelectInfo.drawsAfter.empty())
                throw std::runtime_error("Toolbox Bag did not execute both ordered draws");
            const auto imported = one_combat::advisor::importSilverRoot(offer);
            if (!imported.ok) throw std::runtime_error("Toolbox opening draw import: " + imported.reason);
            auto selected = battleContextFromWire(imported.wire);
            const auto roundtrip = wireFromSearchState(selected, searchContextFromWire(imported.wire));
            if (roundtrip.cardSelect.drawAfter != 5) throw std::runtime_error("Toolbox pending draw lost");
            json selectionWire = roundtrip.cardSelect;
            if (selectionWire.get<silver_bridge::CardSelectWire>().drawAfter != 5)
                throw std::runtime_error("Toolbox pending draw JSON roundtrip failed");
            selectionWire.erase("drawAfter");
            if (selectionWire.get<silver_bridge::CardSelectWire>().drawAfter != 0)
                throw std::runtime_error("legacy card-select wire did not default absent continuation");
            // Binary snapshots intentionally require a concrete sampled order.
            // This fixture's seven cards are identical except physical UUID;
            // fixing that order preserves the draw behavior being tested.
            selected.cards.drawPile.assignConcrete(std::vector<CardInstance>(selected.cards.drawPile.begin(), selected.cards.drawPile.end()));
            const auto binary = serializeBattleContext(selected);
            auto restored = deserializeBattleContext(binary.data(), binary.size());
            if (binary.at(8) != 4 || restored.cardSelectInfo.setCostToZero
                    || restored.cardSelectInfo.drawAfter != 5)
                throw std::runtime_error("Toolbox binary continuation roundtrip failed");
            // Build the exact visible v1 layout by dropping the appended v2
            // group-6 fields and v4 group 8, then adjusting all lengths.
            auto legacy = binary;
            const auto read32 = [&](std::size_t offset) {
                std::uint32_t value = 0;
                for (int i = 0; i < 4; ++i) value |= std::uint32_t(legacy.at(offset+i)) << (8*i);
                return value;
            };
            const auto write32 = [&](std::size_t offset, std::uint32_t value) {
                for (int i = 0; i < 4; ++i) legacy.at(offset+i) = (value >> (8*i)) & 255;
            };
            std::size_t group = 16;
            while (legacy.at(group) != 6) group += 5 + read32(group+1);
            const auto oldSize = read32(group+1);
            legacy.erase(legacy.begin()+group+5+oldSize-17, legacy.begin()+group+5+oldSize);
            write32(group+1, oldSize-17);
            group = 16;
            while (group < legacy.size() && legacy.at(group) != 8) {
                if (legacy.at(group) == 7)
                    throw std::runtime_error("visible legacy binary fixture unexpectedly contains hidden intents");
                group += 5 + read32(group+1);
            }
            if (group == legacy.size())
                throw std::runtime_error("current binary fixture omitted persistent monster group");
            const auto persistentSize = read32(group+1);
            legacy.erase(legacy.begin()+group, legacy.begin()+group+5+persistentSize);
            write32(8, 1); write32(12, legacy.size());
            const auto legacyRestored = deserializeBattleContext(legacy.data(), legacy.size());
            if (legacyRestored.inputState != selected.inputState
                    || legacyRestored.cardSelectInfo.cards != selected.cardSelectInfo.cards
                    || !legacyRestored.cardSelectInfo.setCostToZero || legacyRestored.cardSelectInfo.drawAfter != 0)
                throw std::runtime_error("legacy binary offer defaults failed");
            sts::search::Action(sts::search::ActionType::SINGLE_CARD_SELECT, 1).execute(restored);
            sts::search::Action(sts::search::ActionType::SINGLE_CARD_SELECT, 1).execute(selected);
            if (restored.cards.cardsInHand != selected.cards.cardsInHand
                    || restored.cards.drawPile.size() != selected.cards.drawPile.size()
                    || restored.cards.hand[0].id != selected.cards.hand[0].id
                    || restored.cards.hand[0].costForTurn != selected.cards.hand[0].costForTurn
                    || restored.inputState != selected.inputState || restored.cardSelectInfo.drawAfter != 0)
                throw std::runtime_error("Toolbox binary restore changed selection behavior");
            if (selected.cards.cardsInHand != 6 || selected.cards.drawPile.size() != 2
                || selected.cards.hand[0].id != CardId::SHRUG_IT_OFF || selected.cards.hand[0].costForTurn != 1
                || selected.cardSelectInfo.drawAfter != 0 || selected.inputState != InputState::PLAYER_NORMAL)
                throw std::runtime_error("Toolbox did not create normal-cost card before opening draw");
        }
        for (int choice : {1, 3}) {
            auto offer = genericObservation(fixtures[1], "codex-end-turn-offer");
            auto &combat = offer["silverRoot"]["combat"];
            combat["relics"].push_back(json{{"id", "Nilry's Codex"}, {"counter", -1}, {"usedUp", false}});
            combat["cardSelect"] = offerSelection(1, "codex_end_turn");
            combat["cardSelect"]["task"] = "CODEX";
            combat["cardSelect"]["canPickZero"] = true;
            combat["cardSelect"]["setCostToZero"] = false;
            combat["cardSelect"]["data0"] = 0;
            one_combat::advisor::SilverImportContext context;
            const auto imported = one_combat::advisor::importSilverRoot(offer, context);
            if (!imported.ok || !imported.wire.endTurnQueued)
                throw std::runtime_error("Codex continuation import: " + imported.reason);
            auto selected = battleContextFromWire(imported.wire);
            const int nextId = selected.cards.nextUniqueCardId;
            auto poweredOffer = offer;
            auto &poweredCombat = poweredOffer["silverRoot"]["combat"];
            poweredCombat["relics"].push_back(json{{"id", "StoneCalendar"}, {"counter", 7}, {"usedUp", false}});
            poweredCombat["cardSelect"]["blocksAfter"] = json::array({3, 4});
            poweredCombat["cardSelect"]["damageAllBeforeBlocks"] = 52;
            const auto poweredImport = one_combat::advisor::importSilverRoot(poweredOffer);
            if (!poweredImport.ok) throw std::runtime_error("Codex block/Calendar continuation import: " + poweredImport.reason);
            auto powered = battleContextFromWire(poweredImport.wire);
            powered.monsters.arr[0].curHp = powered.monsters.arr[0].maxHp = 200;
            powered.player.block = 0;
            auto withoutBlocks = powered; withoutBlocks.cardSelectInfo.blocksAfter.clear();
            auto lethal = powered; lethal.monsters.arr[0].curHp = 30;
            const int lethalTurn = lethal.turn;
            auto oracle = powered;
            oracle.cardSelectInfo.blocksAfter.clear(); oracle.cardSelectInfo.damageAllBeforeBlocks = 0;
            oracle.addToBot(Actions::DamageAllEnemy(52));
            oracle.addToBot(Actions::GainBlock(3)); oracle.addToBot(Actions::GainBlock(4));
            const sts::search::Action action(sts::search::ActionType::SINGLE_CARD_SELECT, choice);
            action.execute(powered); action.execute(oracle); action.execute(withoutBlocks); action.execute(lethal);
            if (lethal.outcome != Outcome::PLAYER_VICTORY || lethal.turn != lethalTurn)
                throw std::runtime_error("lethal Codex Calendar continuation advanced another turn");
            if (powered.player.curHp != withoutBlocks.player.curHp + 7)
                throw std::runtime_error("Codex self blocks did not prevent the pending monster attack damage");
            if (powered.monsters.arr[0].curHp != 148 || powered.monsters.arr[0].curHp != oracle.monsters.arr[0].curHp
                    || powered.player.curHp != oracle.player.curHp || powered.player.block != oracle.player.block
                    || powered.turn != oracle.turn || !powered.cardSelectInfo.blocksAfter.empty()
                    || powered.cardSelectInfo.damageAllBeforeBlocks != 0)
                throw std::runtime_error("Codex pending damage/block sequence duplicated or omitted");
            const auto semantic = sts::search::semanticFromSearchAction(selected, action);
            const auto lowered = one_combat::advisor::selectedLiveAction(semantic, context, offer);
            if (lowered.value("kind", "") != (choice == 3 ? "skip" : "choose"))
                throw std::runtime_error("Codex choice/Skip lowering failed");
            action.execute(selected);
            if (selected.turn != imported.wire.turn + 1 || selected.inputState != InputState::PLAYER_NORMAL
                || selected.cards.nextUniqueCardId != nextId + (choice == 3 ? 0 : 1)
                || selected.endTurnQueued || selected.turnHasEnded)
                throw std::runtime_error("Codex did not resume exactly one end-turn/monster cycle");
            auto invalid = offer;
            invalid["silverRoot"]["combat"]["cardSelect"]["canPickZero"] = false;
            if (one_combat::advisor::importSilverRoot(invalid).ok)
                throw std::runtime_error("unqualified Codex continuation accepted");
        }
        // Nilry's Codex pauses before these exact hand-owned end-turn cards.
        // Preserve pending blocks -> Burn/Decay damage -> discard -> one turn.
        for (int choice : {0,3}) for (bool upgraded : {false,true}) {
            auto offer = genericObservation(fixtures[0], "codex-status-queue");
            auto &combat=offer["silverRoot"]["combat"];
            combat["relics"].push_back({{"id","Nilry's Codex"},{"counter",-1},{"usedUp",false}});
            combat["cardSelect"]=offerSelection(1,"codex_end_turn");
            combat["cardSelect"]["task"]="CODEX";
            combat["cardSelect"]["canPickZero"]=true;
            combat["cardSelect"]["setCostToZero"]=false;
            combat["cardSelect"]["data0"]=0;
            combat["cardSelect"]["blocksAfter"]=json::array({3});
            combat["hand"]=json::array(); combat["pendingCardQueue"]=json::array();
            for(const std::string id:{"Burn","Decay"}) {
                auto card=genericObservation(fixtures[0],"card")["silverRoot"]["combat"]["hand"][0];
                card["id"]=id;card["uuid"]="end-turn-"+id;card["cost"]=card["costForTurn"]=-2;
                card["upgraded"]=id=="Burn" && upgraded;card["freeToPlayOnce"]=false;card["retain"]=false;
                combat["hand"].push_back(card);
                combat["pendingCardQueue"].push_back({{"card",card},{"target",0},{"energyOnUse",2},
                    {"isEndTurn",false},{"triggerOnUse",false},{"ignoreEnergyTotal",false},{"freeToPlay",false},
                    {"randomTarget",false},{"autoplay",false},{"regretCardCount",0},{"purgeOnUse",false},
                    {"exhaustOnUse",false},{"endTurnAutoPlay",true},{"noTriggerOwner","codex_end_turn"}});
            }
            const auto imported=one_combat::advisor::importSilverRoot(offer);
            if(!imported.ok || imported.wire.pendingCardQueue.size()!=2)
                throw std::runtime_error("Codex Burn/Decay import: "+imported.reason);
            auto root=battleContextFromWire(imported.wire);
            root.player.block=0;root.player.curHp=root.player.maxHp=80;
            // Public deterministic nonattack isolates end-turn status damage.
            root.monsters.arr[0].id=MonsterId::CULTIST;
            root.monsters.arr[0].moveHistory[0]=MMID::CULTIST_INCANTATION;
            auto oracle=root;
            oracle.cardQueue.clear();oracle.cards.cardsInHand=0;
            oracle.cardSelectInfo.blocksAfter.clear();
            oracle.addToBot(Actions::GainBlock(3));
            oracle.addToBot(Actions::DamagePlayer(upgraded?4:2,true));
            oracle.addToBot(Actions::DamagePlayer(2,true));
            auto lethal=root;lethal.player.curHp=1;lethal.cardSelectInfo.blocksAfter.clear();
            const int oldTurn=root.turn;
            const sts::search::Action action(sts::search::ActionType::SINGLE_CARD_SELECT,choice);
            action.execute(root);action.execute(oracle);action.execute(lethal);
            if(root.player.curHp!=80-(upgraded?3:1) || root.player.curHp!=oracle.player.curHp
                    || root.turn!=oldTurn+1 || root.turn!=oracle.turn || !root.cardQueue.isEmpty()
                    || root.endTurnQueued || root.turnHasEnded)
                throw std::runtime_error("Codex queued status order/damage/end-turn mismatch");
            if(lethal.outcome!=Outcome::PLAYER_LOSS || lethal.turn!=oldTurn)
                throw std::runtime_error("lethal Codex Burn advanced another turn");
            const auto reject=[&](json bad) {
                if(one_combat::advisor::importSilverRoot(bad).ok)
                    throw std::runtime_error("unqualified Codex no-trigger queue accepted");
            };
            auto bad=offer;bad["silverRoot"]["combat"]["pendingCardQueue"][0].erase("noTriggerOwner");reject(bad);
            bad=offer;bad["silverRoot"]["combat"]["pendingCardQueue"][0]["endTurnAutoPlay"]=false;reject(bad);
            bad=offer;bad["silverRoot"]["combat"]["pendingCardQueue"][0]["card"]["id"]="Regret";reject(bad);
            bad=offer;bad["silverRoot"]["combat"]["hand"].erase(0);reject(bad);
            bad=offer;bad["silverRoot"]["combat"]["pendingCardQueue"].push_back(combat["pendingCardQueue"][0]);reject(bad);
            bad=offer;bad["silverRoot"]["combat"]["relics"].push_back({{"id","Unceasing Top"},{"counter",0},{"usedUp",false}});
            if (!one_combat::advisor::importSilverRoot(bad).ok)
                throw std::runtime_error("Codex end-turn barrier failed to qualify Unceasing Top");
        }
        for (bool top : {false, true}) for (bool artifact : {false, true}) for (int choice : {1, 3}) {
            auto offer=genericObservation(fixtures[0],"codex-queued-curses");
            auto &combat=offer["silverRoot"]["combat"];
            combat["relics"].push_back({{"id","Nilry's Codex"},{"counter",-1},{"usedUp",false}});
            if(top)combat["relics"].push_back({{"id","Unceasing Top"},{"counter",0},{"usedUp",false}});
            combat["cardSelect"]=offerSelection(1,"codex_end_turn");
            combat["cardSelect"]["task"]="CODEX";combat["cardSelect"]["canPickZero"]=true;
            combat["cardSelect"]["setCostToZero"]=false;combat["cardSelect"]["data0"]=0;
            auto prototype=combat["hand"][0];combat["hand"]=json::array();combat["pendingCardQueue"]=json::array();
            for(const std::string id:{"Doubt","Shame","Regret"}) {
                auto card=prototype;card["id"]=id;card["uuid"]="end-"+id;
                card["cost"]=-2;card["costForTurn"]=-2;card["upgraded"]=false;
                card["freeToPlayOnce"]=false;card["retain"]=false;combat["hand"].push_back(card);
                combat["pendingCardQueue"].push_back({{"card",card},{"target",0},{"energyOnUse",0},
                    {"isEndTurn",false},{"triggerOnUse",false},{"ignoreEnergyTotal",false},{"freeToPlay",false},
                    {"randomTarget",false},{"autoplay",false},{"regretCardCount",id=="Regret"?7:0},
                    {"purgeOnUse",false},{"exhaustOnUse",false},{"endTurnAutoPlay",true},{"noTriggerOwner","codex_end_turn"}});
            }
            const auto imported=one_combat::advisor::importSilverRoot(offer);
            if(!imported.ok)throw std::runtime_error("Codex curse/Top import: "+imported.reason);
            auto state=battleContextFromWire(imported.wire);
            state.player.curHp=state.player.maxHp=80;state.player.block=20;
            if(artifact)state.player.buff<PlayerStatus::ARTIFACT>(2);
            const int turn=state.turn;
            sts::search::Action(sts::search::ActionType::SINGLE_CARD_SELECT,choice).execute(state);
            if(state.player.curHp!=73 || state.turn!=turn+1 || state.cards.cardsInHand!=5
                || state.player.getStatus<PlayerStatus::WEAK>()!=(artifact?0:1)
                || state.player.getStatus<PlayerStatus::FRAIL>()!=(artifact?0:1)
                || state.player.getStatus<PlayerStatus::ARTIFACT>()!=0 || !state.cardQueue.isEmpty())
                throw std::runtime_error("Codex curse debuff/Artifact/stored-Regret/Top continuation mismatch");
            auto bad=offer;bad["silverRoot"]["combat"]["pendingCardQueue"][2]["regretCardCount"]=11;
            if(one_combat::advisor::importSilverRoot(bad).ok)throw std::runtime_error("invalid captured Regret amount accepted");
        }
        for (const auto &cardName : {"Brutality", "Combust"}) {
            auto observation = genericObservation(fixtures[0], "ironclad-persistent-power-card");
            observation["silverRoot"]["combat"]["hand"][0]["id"] = cardName;
            const auto imported = one_combat::advisor::importSilverRoot(observation);
            if (!imported.ok) throw std::runtime_error("Ironclad power card rejected: " + imported.reason);
        }
        for (int copies : {1, 2}) {
            for (int handSize : {7, 9, 10}) {
                auto offer = genericObservation(fixtures[0], "colorless-potion-offer");
                auto &combat = offer["silverRoot"]["combat"];
                auto prototype = combat["hand"][0];
                combat["hand"] = json::array();
                for (int i = 0; i < handSize; ++i) {
                    auto card = prototype;
                    card["uuid"] = "offer-hand-" + std::to_string(i);
                    combat["hand"].push_back(card);
                }
                combat["cardSelect"] = offerSelection(copies, "none");
                one_combat::advisor::SilverImportContext context;
                const auto imported = one_combat::advisor::importSilverRoot(offer, context);
                if (!imported.ok) throw std::runtime_error("Colorless Potion offer import: " + imported.reason);
                auto selected = battleContextFromWire(imported.wire);
                const auto beforeDiscard = selected.cards.discardPile.size();
                const auto actions = sts::search::Action::enumerateCardSelectActions(selected);
                if (actions.size() != 3) throw std::runtime_error("Discovery option count changed");
                auto semantic = sts::search::semanticFromSearchAction(selected, actions[1]);
                const auto lowered = one_combat::advisor::selectedLiveAction(semantic, context, offer);
                if (lowered.value("kind", "") != "choose" || lowered.value("choiceIndex", 0) != 2)
                    throw std::runtime_error("Discovery option occurrence lowering failed");
                actions[1].execute(selected);
                if (selected.inputState != InputState::PLAYER_NORMAL
                    || selected.cards.cardsInHand != std::min(10, handSize + copies)
                    || selected.cards.discardPile.size() != beforeDiscard + std::max(0, handSize + copies - 10))
                    throw std::runtime_error("Discovery copy count/full-hand destination mismatch");
                int created = 0;
                const auto checkCreated = [&](const auto &card) {
                    if (card.id == CardId::SHRUG_IT_OFF) {
                        if (card.costForTurn != 0 || card.isUpgraded())
                            throw std::runtime_error("Discovery lost zero-cost/unupgraded card semantics");
                        ++created;
                    }
                };
                for (int i = 0; i < selected.cards.cardsInHand; ++i) checkCreated(selected.cards.hand[i]);
                for (const auto &card : selected.cards.discardPile) checkCreated(card);
                if (created != copies) throw std::runtime_error("Discovery generated wrong number of copies");
                auto ambiguous = offer;
                ambiguous["silverRoot"]["combat"]["cardSelect"]["cards"][0] = "Shrug It Off";
                if (one_combat::advisor::importSilverRoot(ambiguous).reason != "silver_card_reward_option_state"
                    || !one_combat::advisor::selectedLiveAction(semantic, context, ambiguous).is_null())
                    throw std::runtime_error("ambiguous Discovery offer accepted/lowered");
                semantic.optionCardId = static_cast<std::int16_t>(CardId::BASH);
                if (!one_combat::advisor::selectedLiveAction(semantic, context, offer).is_null())
                    throw std::runtime_error("absent Discovery option lowered");
            }
        }
        {
            auto afterPower = genericObservation(fixtures[0], "offer-after-completed-power");
            auto &combat = afterPower["silverRoot"]["combat"];
            auto historical = combat["hand"][0];
            historical["id"] = "Inflame"; historical["uuid"] = "completed-inflame";
            historical["cost"] = historical["costForTurn"] = 1;
            afterPower["silverRoot"]["decisionInTurn"] = 1;
            combat["cardsPlayedThisTurn"] = 1;
            combat["playerPowers"] = json::array({json{{"id", "Strength"}, {"amount", 2}}});
            CardQueueItemWire queue;
            combat["curCardQueueItem"] = producerQueueJson(queue);
            combat["curCardQueueItem"]["card"] = historical;
            combat["cardSelect"] = offerSelection(1, "none");
            const auto imported = one_combat::advisor::importSilverRoot(afterPower);
            if (!imported.ok || imported.wire.curCardQueueItem.card.id != static_cast<int>(CardId::INVALID))
                throw std::runtime_error("standalone offer retained completed power as interrupted card");
            auto selected = battleContextFromWire(imported.wire);
            sts::search::Action(sts::search::ActionType::SINGLE_CARD_SELECT, 1).execute(selected);
            if (selected.player.strength != 2 || selected.inputState != InputState::PLAYER_NORMAL)
                throw std::runtime_error("standalone offer replayed a completed historical power");
        }
        for (bool upgraded : {false, true}) for(bool exactTail:{false,true}) {
            auto discovery = genericObservation(fixtures[0], "discovery-card-continuation");
            auto &root = discovery["silverRoot"];
            auto &combat = root["combat"];
            auto card = combat["hand"][0];
            combat["hand"].erase(combat["hand"].begin());
            card["id"] = "Discovery"; card["uuid"] = "played-discovery";
            card["cost"] = card["costForTurn"] = 1;
            card["upgraded"] = upgraded;
            root["decisionInTurn"] = 1;
            combat["cardsPlayedThisTurn"] = 1; combat["skillsPlayedThisTurn"] = 1;
            combat["energy"] = 2;
            combat["playedThisTurn"] = json::array({card});
            combat["lastCard"] = card;
            CardQueueItemWire queue;
            queue.triggerOnUse = true; queue.energyOnUse = 1; queue.exhaustOnUse = !upgraded;
            combat["curCardQueueItem"] = producerQueueJson(queue);
            combat["curCardQueueItem"]["card"] = card;
            combat["cardSelect"] = offerSelection(1, "discovery_card");
            if(exactTail) {
                combat["cardSelect"]["continuation"]="source_card_actions";
                combat["pendingCardQueue"]=json::array();
                combat["pendingActionQueue"]=json::array({producerCleanupJson(combat["curCardQueueItem"])});
            }
            one_combat::advisor::SilverImportContext context;
            const auto imported = one_combat::advisor::importSilverRoot(discovery, context);
            if (!imported.ok) throw std::runtime_error("Discovery cleanup import: " + imported.reason);
            auto selected = battleContextFromWire(imported.wire);
            const auto discoveryId = imported.wire.curCardQueueItem.card.uniqueId;
            if (imported.wire.nextUniqueCardId <= discoveryId)
                throw std::runtime_error("resumed Discovery would reuse interrupted physical card ID");
            const int handSize = selected.cards.cardsInHand;
            sts::search::Action(sts::search::ActionType::SINGLE_CARD_SELECT, 1).execute(selected);
            const auto &destination = upgraded ? selected.cards.discardPile : selected.cards.exhaustPile;
            if (selected.inputState != InputState::PLAYER_NORMAL || selected.cards.cardsInHand != handSize + 1
                || std::none_of(destination.begin(), destination.end(), [discoveryId](const auto &c) {
                    return c.id == CardId::DISCOVERY && c.uniqueId == discoveryId;
                }))
                throw std::runtime_error("Discovery cleanup did not preserve exhaust/discard semantics");
        }
        for (const char *reason : {"silver_card_reward_end_turn_continuation", "silver_card_reward_toolbox_cost",
                                  "silver_card_reward_skip_unrepresentable", "silver_card_reward_pending_actions"}) {
            auto blocked = genericObservation(fixtures[0], "blocked-offer");
            blocked["silverRoot"]["combat"]["cardSelect"] = json{{"task", ""}, {"origin", "CARD_REWARD"},
                {"unsupportedReason", reason}};
            if (one_combat::advisor::importSilverRoot(blocked).reason != reason)
                throw std::runtime_error("combat offer rejection lost its precise reason");
        }
        for (const auto &invalidCards : {json::array({"Anger", "Shrug It Off"}),
                json::array({"Anger", "Shrug It Off", "Flash of Steel", "Bash"}),
                json::array({"Anger", "Shrug It Off", json{{"id", "Flash of Steel"}, {"upgraded", true}}})}) {
            auto invalid = genericObservation(fixtures[0], "invalid-offer");
            invalid["silverRoot"]["combat"]["cardSelect"] = offerSelection(1, "none");
            invalid["silverRoot"]["combat"]["cardSelect"]["cards"] = invalidCards;
            if (one_combat::advisor::importSilverRoot(invalid).ok)
                throw std::runtime_error("Discovery offer was silently truncated or flattened");
        }
        auto unknownSelection = nativeSelection;
        // A timed-out hand-selection action can disappear after confirmation
        // without retrieving its selected physical card. The remaining piles
        // can otherwise look importable despite the missing card.
        auto orphanedSelection = genericObservation(fixtures[0], "orphaned-hand-selection");
        orphanedSelection["silverRoot"]["combat"]["orphanedHandSelection"] = true;
        if (one_combat::advisor::importSilverRoot(orphanedSelection).reason
                != "silver_orphaned_hand_selection")
            throw std::runtime_error("abandoned hand selection was accepted as ordinary play");
        unknownSelection["silverRoot"]["combat"]["cardSelect"]["task"] = "";
        // Unknown selectors must not become normal play or be obscured by an
        // unrelated unsupported projection field at a resumed combat boundary.
        unknownSelection["silverRoot"]["combat"]["damageTrackingExact"] = false;
        const auto unknownSelectionImported = one_combat::advisor::importSilverRoot(unknownSelection);
        if (unknownSelectionImported.ok
            || unknownSelectionImported.reason != "silver_unmapped_selection_task")
            throw std::runtime_error("unknown combat selection was not explicitly unsupported");

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
        {
            // Real native Double Tap interruption, translated through the
            // same queue/card JSON shape emitted by the Java observer.
            GameContext game(CharacterClass::IRONCLAD, 11, 0);
            game.act=1; game.floorNum=1;
            BattleContext live; live.init(game, MonsterEncounter::JAW_WORM);
            for (int played=0;played<2;++played) {
                int idx=0;
                while (idx<live.cards.cardsInHand && live.cards.hand[idx].id!=CardId::DEFEND_RED
                        && live.cards.hand[idx].id!=CardId::STRIKE_RED) ++idx;
                if (idx==live.cards.cardsInHand) throw std::runtime_error("pending-copy fixture lacks starter card");
                sts::search::Action(sts::search::ActionType::CARD,idx,0).execute(live);
            }
            CardInstance headbutt(CardId::HEADBUTT); headbutt.uniqueId=900;
            live.cards.moveToHand(headbutt); live.player.buff<PlayerStatus::DOUBLE_TAP>(1);
            sts::search::Action(sts::search::ActionType::CARD,live.cards.cardsInHand-1,0).execute(live);
            if(live.inputState!=InputState::CARD_SELECT || live.cardQueue.size!=1)
                throw std::runtime_error("pending-copy fixture did not interrupt Headbutt");
            CombatKnowledgeState knowledge; knowledge.initializeFromLiveBattle(live);
            auto expected=makeSilverBattleStateWire(live,knowledge,makeSilverRunContext(game),0x71517u);
            auto observation=nativeObservation(expected,"MonsterRoom","observed-headbutt-copy");
            setProducerV4CardObservation(observation,expected);
            auto &combat=observation["silverRoot"]["combat"];
            combat["cardSelect"]={{"task","HEADBUTT"},{"cards",pileJson(expected.discardPile.unknown)},
                {"pickCount",1},{"canPickZero",false},{"canPickAnyNumber",false}};
            combat["pendingCardQueue"]=json::array();
            for(const auto &item:expected.pendingCardQueue) combat["pendingCardQueue"].push_back(producerQueueJson(item));
            combat["cardSelect"]["origin"]="GRID";combat["cardSelect"]["selectedBits"]=0;
            combat["cardSelect"]["continuation"]="source_card_actions";
            combat["cardSelect"]["liveChoices"]=json::array();
            for(const auto &card:combat["discard"])
                combat["cardSelect"]["liveChoices"].push_back(json{{"uuid",card.at("uuid")},
                    {"choiceIndex",combat["cardSelect"]["liveChoices"].size()+1}});
            combat["pendingActionQueue"]=json::array({producerCleanupJson(combat["curCardQueueItem"])});
            const auto imported=one_combat::advisor::importSilverRoot(observation);
            if(!imported.ok) throw std::runtime_error("producer Headbutt copy import: "+imported.reason);
            normalizeDynamicObservationIdentity(expected);
            expected.curCardQueueItem.card.uniqueId=imported.wire.curCardQueueItem.card.uniqueId;
            expected.pendingCardQueue[0].card.uniqueId=expected.curCardQueueItem.card.uniqueId;
            expected.nextUniqueCardId=imported.wire.nextUniqueCardId;
            expected.isolatedSearchSeed=imported.wire.isolatedSearchSeed;
            // HEADBUTT indexes the discard pile, not this Discovery-only
            // cache. Java's offered-card IDs populate it in the wire, while
            // the native fixture leaves it stale; align that inert metadata.
            expected.cardSelect.cards=imported.wire.cardSelect.cards;
            auto actual=battleContextFromWire(imported.wire);
            auto reference=battleContextFromWire(expected);
            if(actual.cardQueue!=reference.cardQueue || actual.actionQueue.size!=reference.actionQueue.size)
                throw std::runtime_error("producer Headbutt pending queue reconstruction mismatch");
            // First selection resumes the pending copy, opening Headbutt's
            // second selection; both physical continuations must agree.
            const sts::search::Action pick(sts::search::ActionType::SINGLE_CARD_SELECT,0);
            pick.execute(actual); pick.execute(reference);
            if(!actual.equalForSearch(reference)) {
                const auto context=searchContextFromWire(imported.wire);
                std::cerr << json::diff(json(wireFromSearchState(reference,context)),
                                        json(wireFromSearchState(actual,context))).dump(2) << '\n';
                throw std::runtime_error("producer Headbutt copied-play continuation parity failed");
            }
            // Reimport the copied selector itself: Java's purge copy shares
            // the original UUID, which has already reached the discard pile.
            const auto copiedWire=wireFromSearchState(actual,searchContextFromWire(imported.wire));
            auto second=nativeObservation(copiedWire,"MonsterRoom","copied-headbutt-selector");
            setProducerV4CardObservation(second,copiedWire);
            auto &secondCombat=second["silverRoot"]["combat"];
            secondCombat["cardSelect"]={{"task","HEADBUTT"},{"origin","GRID"},{"pickCount",1},
                {"canPickZero",false},{"canPickAnyNumber",false},{"selectedBits",0},{"continuation","source_card_actions"},
                {"liveChoices",json::array()}};
            for(const auto &card:secondCombat["discard"])
                secondCombat["cardSelect"]["liveChoices"].push_back(json{{"uuid",card.at("uuid")},
                    {"choiceIndex",secondCombat["cardSelect"]["liveChoices"].size()+1}});
            secondCombat["pendingCardQueue"]=json::array();
            secondCombat["pendingActionQueue"]=json::array({producerCleanupJson(secondCombat["curCardQueueItem"])});
            const auto secondImported=one_combat::advisor::importSilverRoot(second);
            if(!secondImported.ok)throw std::runtime_error("copied source selector reimport: "+secondImported.reason);
            auto resumed=battleContextFromWire(secondImported.wire);
            if(!resumed.curCardQueueItem.purgeOnUse || !resumed.curCardQueueItem.autoplay)
                throw std::runtime_error("copied cleanup lost purge/autoplay owner flags");
            pick.execute(resumed);
            if(resumed.inputState!=InputState::PLAYER_NORMAL)
                throw std::runtime_error("copied source selection did not finish");
            int originals=0;
            for(const auto &card:resumed.cards.discardPile)originals+=card.id==CardId::HEADBUTT;
            for(const auto &card:resumed.cards.drawPile)originals+=card.id==CardId::HEADBUTT;
            if(originals!=1)throw std::runtime_error("copied source cleanup duplicated or removed original Headbutt");
        }
        const auto v4Successor = successorFixture(fixtures[0], CardId::STRIKE_RED);
        const auto v4Continuation = genericObservation(v4Successor, "v4-normal-card");
        const auto v4ContinuationImported = one_combat::advisor::importSilverRoot(v4Continuation);
        if (!v4ContinuationImported.ok)
            throw std::runtime_error("v4 continuation import failed: "
                + v4ContinuationImported.reason);
        auto v4ContinuationCanonical = v4Successor.wire;
        normalizeDynamicObservationIdentity(v4ContinuationCanonical);
        if (!v4ContinuationCanonical.discardPile.unknown.empty())
            v4ContinuationCanonical.curCardQueueItem.card.uniqueId =
                v4ContinuationCanonical.discardPile.unknown.front().uniqueId;
        v4ContinuationCanonical.isolatedSearchSeed = v4ContinuationImported.wire.isolatedSearchSeed;
        if (!convertedStatesEqualForSearch(v4ContinuationCanonical,
                                           v4ContinuationImported.wire))
            throw std::runtime_error("v4 continuation search-state parity failed");
        // An observed pending card queue (a Double Tap copy of the played
        // card) is imported item by item with the played card's identity.
        {
            auto withQueue = v4Continuation;
            auto copy = producerQueueJson(v4Successor.wire.curCardQueueItem);
            copy["purgeOnUse"] = true;
            copy["autoplay"] = true;
            withQueue["silverRoot"]["combat"]["pendingCardQueue"] = json::array({copy});
            const auto queued = one_combat::advisor::importSilverRoot(withQueue);
            if (!queued.ok || !queued.wire.pendingCardQueueObserved || queued.wire.pendingCardQueue.size() != 1
                || !queued.wire.pendingCardQueue[0].purgeOnUse || !queued.wire.pendingCardQueue[0].autoplay
                || queued.wire.pendingCardQueue[0].card.uniqueId != queued.wire.curCardQueueItem.card.uniqueId)
                throw std::runtime_error("pending card queue was not imported");
            if (v4ContinuationImported.wire.pendingCardQueueObserved)
                throw std::runtime_error("absent pending card queue was treated as observed");
            auto generated = copy;
            generated["card"]["uuid"] = "generated-copy-not-in-any-pile";
            generated["energyOnUse"] = 2;
            generated["freeToPlay"] = true;
            generated["ignoreEnergyTotal"] = true;
            generated["exhaustOnUse"] = true;
            withQueue["silverRoot"]["combat"]["pendingCardQueue"] = json::array({generated, copy});
            const auto ordered = one_combat::advisor::importSilverRoot(withQueue);
            if (!ordered.ok || ordered.wire.pendingCardQueue.size()!=2
                    || ordered.wire.pendingCardQueue[0].card.uniqueId == ordered.wire.curCardQueueItem.card.uniqueId
                    || ordered.wire.pendingCardQueue[1].card.uniqueId != ordered.wire.curCardQueueItem.card.uniqueId)
                throw std::runtime_error("generated/same-instance pending queue identity or order lost");
            auto restored = battleContextFromWire(ordered.wire);
            if (restored.cardQueue.size!=2 || !restored.cardQueue.front().exhaustOnUse
                    || !restored.cardQueue.front().ignoreEnergyTotal || !restored.cardQueue.front().freeToPlay
                    || restored.cardQueue.front().energyOnUse!=2
                    || restored.cardQueue.front().card.uniqueId != ordered.wire.pendingCardQueue[0].card.uniqueId)
                throw std::runtime_error("producer pending queue flags lost in native reconstruction");
            withQueue["silverRoot"]["combat"]["pendingCardQueue"] = json::array();
            const auto empty = one_combat::advisor::importSilverRoot(withQueue);
            if (!empty.ok || !empty.wire.pendingCardQueueObserved || !empty.wire.pendingCardQueue.empty())
                throw std::runtime_error("observed empty queue lost completeness");
            for (const char *field : {"isEndTurn", "triggerOnUse", "ignoreEnergyTotal", "freeToPlay", "randomTarget",
                                     "autoplay", "purgeOnUse", "exhaustOnUse", "target", "energyOnUse", "regretCardCount", "card"}) {
                auto malformed = copy; malformed.erase(field);
                withQueue["silverRoot"]["combat"]["pendingCardQueue"] = json::array({malformed});
                if (one_combat::advisor::importSilverRoot(withQueue).reason != "silver_card_queue_item")
                    throw std::runtime_error(std::string("missing pending queue field accepted: ")+field);
            }
            for (auto malformed : {json{{"target",5}}, json{{"target",4}}, json{{"target",-1}}, json{{"energyOnUse",-1}},
                                   json{{"autoplay","true"}}, json{{"energyOnUse",1.5}}, json{{"isEndTurn",true}}}) {
                auto bad = copy; bad.update(malformed);
                withQueue["silverRoot"]["combat"]["pendingCardQueue"] = json::array({bad});
                if (one_combat::advisor::importSilverRoot(withQueue).reason != "silver_card_queue_item")
                    throw std::runtime_error("invalid pending queue flag/range accepted");
            }
            withQueue["silverRoot"]["combat"]["pendingCardQueue"] = json::array();
            for (int i=0;i<=sts::CardQueue::capacity;++i)
                withQueue["silverRoot"]["combat"]["pendingCardQueue"].push_back(copy);
            if (one_combat::advisor::importSilverRoot(withQueue).reason != "silver_card_queue_item")
                throw std::runtime_error("pending queue overflow accepted");
            auto failedCapture = v4Continuation;
            failedCapture["silverRoot"]["combat"]["pendingCardQueueError"] = "queue_not_settled";
            if (one_combat::advisor::importSilverRoot(failedCapture).reason != "silver_pending_card_queue_unrepresentable")
                throw std::runtime_error("failed pending queue capture fell back to replay");
            withQueue["silverRoot"]["combat"]["pendingCardQueue"] = 5;
            if (one_combat::advisor::importSilverRoot(withQueue).reason != "silver_card_queue_item")
                throw std::runtime_error("malformed pending card queue was accepted");
        }
        auto missingV4Queue = v4Continuation;
        missingV4Queue["silverRoot"]["combat"].erase("curCardQueueItem");
        if (one_combat::advisor::importSilverRoot(missingV4Queue).reason
            != "silver_card_queue_item")
            throw std::runtime_error("v4 continuation without CardQueueItem was accepted");
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
        auto dedupActions = enumerateSilverLegalActions(dedupWire);
        if (cardActionCount(dedupActions, CardId::STRIKE_RED) != 1
            || cardActionCount(dedupActions, CardId::DEFEND_RED) != 1
            || cardActionCount(dedupActions, CardId::BASH) != 1)
            throw std::runtime_error("live root did not collapse equivalent starter card actions");
        dedupWire.hand[1].retain = true;
        auto distinctActions = enumerateSilverLegalActions(dedupWire);
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
        SilverDecisionResult rerootFirst;
        std::shared_ptr<SilverSearchSession> rerootSession;
        for (const auto &candidate : fixtures) {
            const auto entry = candidate.observation.value("combatEntryHash", "entry-v4");
            auto imported = one_combat::advisor::importSilverRoot(
                genericObservation(candidate, entry.c_str()));
            auto session = makeSilverSearchSession();
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

        auto disagreementSession = makeSilverSearchSession();
        const auto disagreementFirst = runSilverDecision(*disagreementSession, rerootImported.wire, config);
        auto otherAction = disagreementFirst.action;
        const auto otherCard = disagreementFirst.action.card.id
                == static_cast<std::int16_t>(CardId::STRIKE_RED)
            ? CardId::DEFEND_RED : CardId::STRIKE_RED;
        bool foundOther = false;
        for (const auto &action : enumerateSilverLegalActions(rerootImported.wire)) {
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
            || disagreementDecision.diagnostic.fallback
            || disagreementDecision.diagnostic.fallbackReason != "none"
            || disagreementDecision.diagnostic.inheritedVisits <= 0
            || disagreementDecision.rootActionSummaries.empty())
            throw std::runtime_error("different listed action did not reuse its retained branch");

        auto otherEquivalentSession = makeSilverSearchSession();
        const auto otherEquivalentFirst = runSilverDecision(
            *otherEquivalentSession, rerootImported.wire, config);
        const auto otherEquivalentSuccessor = successorForSemantic(*rerootRoot, otherAction, true);
        const auto otherEquivalentImported = one_combat::advisor::importSilverRoot(
            otherEquivalentSuccessor.observation);
        const auto otherEquivalentDecision = runSilverDecision(
            *otherEquivalentSession, otherEquivalentImported.wire, config);
        // A different physical copy of an equivalent card reuses the retained
        // branch through findNodeUpToEquivalentCopy.
        if (!otherEquivalentFirst.accepted || !otherEquivalentDecision.accepted
            || otherEquivalentDecision.diagnostic.exactReroot
            || !otherEquivalentDecision.diagnostic.equivalentCopyReroot
            || otherEquivalentDecision.diagnostic.fallback
            || otherEquivalentDecision.diagnostic.fallbackReason != "none"
            || otherEquivalentDecision.diagnostic.inheritedVisits <= 0)
            throw std::runtime_error(
                "different listed action's equivalent copy did not reuse its retained branch");

        auto equivalentSession = makeSilverSearchSession();
        const auto equivalentFirst = runSilverDecision(*equivalentSession, rerootImported.wire, config);
        const auto equivalentSuccessor = successorForSemantic(*rerootRoot, equivalentFirst.action, true);
        const auto equivalentImported = one_combat::advisor::importSilverRoot(equivalentSuccessor.observation);
        if (convertedStatesEqualForSearch(exactImported.wire, equivalentImported.wire))
            throw std::runtime_error("equivalent-copy reroot test accidentally relaxed global equality");
        const auto equivalentDecision = runSilverDecision(*equivalentSession, equivalentImported.wire, config);
        if (!equivalentDecision.accepted || equivalentDecision.diagnostic.exactReroot
            || !equivalentDecision.diagnostic.equivalentCopyReroot
            || equivalentDecision.diagnostic.fallback
            || equivalentDecision.diagnostic.fallbackReason != "none"
            || equivalentDecision.diagnostic.inheritedVisits <= 0
            || equivalentDecision.rootActionSummaries.empty())
            throw std::runtime_error("equivalent physical copy did not reuse the retained root: exact="
                + std::to_string(equivalentDecision.diagnostic.exactReroot)
                + " fallback=" + std::to_string(equivalentDecision.diagnostic.fallback)
                + " reason=" + equivalentDecision.diagnostic.fallbackReason
                + " inherited=" + std::to_string(equivalentDecision.diagnostic.inheritedVisits));
        // The retained root names the other copy; actions must name live hand cards.
        for (const auto &summary : equivalentDecision.rootActionSummaries) {
            if (summary.action.type != silver_bridge::SemanticActionType::CARD) continue;
            const bool inHand = std::any_of(equivalentImported.wire.hand.begin(), equivalentImported.wire.hand.end(),
                [&](const CardWire &card) { return card.uniqueId == summary.action.card.uniqueId; });
            if (!inHand) throw std::runtime_error("equivalent-copy reroot lowered a card that is not in the live hand");
        }

        auto changedStateSession = makeSilverSearchSession();
        const auto changedStateFirst = runSilverDecision(*changedStateSession, rerootImported.wire, config);
        auto changedStateWire = equivalentImported.wire;
        if (changedStateWire.hand.empty()) throw std::runtime_error("changed-state fixture has no hand");
        changedStateWire.hand.front().retain = !changedStateWire.hand.front().retain;
        const auto changedStateDecision = runSilverDecision(*changedStateSession, changedStateWire, config);
        if (!changedStateFirst.accepted || !changedStateDecision.accepted
            || changedStateDecision.diagnostic.exactReroot
            || changedStateDecision.diagnostic.equivalentCopyReroot
            || !changedStateDecision.diagnostic.fallback
            || changedStateDecision.diagnostic.fallbackReason != "candidate_missing"
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
        if (generalImported.wire.extraRollMoveOnTurn != 0
            || generalImported.wire.skipMonsterTurnBits != 0)
            throw std::runtime_error("explicit stable-boundary group state was not preserved");
        // Literal vanilla POWER_IDs, independently verified with javap.
        // The older native-name corpus alone cannot catch spelling gaps.
        const std::pair<const char *, PlayerStatus> rawPlayerPowers[] = {
            {"Flame Barrier", PlayerStatus::FLAME_BARRIER},
            {"Double Tap", PlayerStatus::DOUBLE_TAP}, {"Brutality", PlayerStatus::BRUTALITY},
            {"Constricted", PlayerStatus::CONSTRICTED},
            {"Next Turn Block", PlayerStatus::NEXT_TURN_BLOCK},
            {"DexLoss", PlayerStatus::LOSE_DEXTERITY}, {"Regeneration", PlayerStatus::REGEN},
            {"Ritual", PlayerStatus::RITUAL}, {"Magnetism", PlayerStatus::MAGNETISM},
            {"Mayhem", PlayerStatus::MAYHEM}, {"Sadistic", PlayerStatus::SADISTIC},
            {"IntangiblePlayer", PlayerStatus::INTANGIBLE},
            {"Double Damage", PlayerStatus::DOUBLE_DAMAGE}};
        for (const auto &[name, status] : rawPlayerPowers) {
            auto raw = general;
            raw["silverRoot"]["combat"]["playerPowers"] = json::array({
                json{{"id", name}, {"amount", 2}, {"justApplied", true}}});
            const auto imported = one_combat::advisor::importSilverRoot(raw);
            const auto expected = std::make_pair(static_cast<std::int16_t>(status), std::int16_t{2});
            if (!imported.ok || std::find(imported.wire.player.statusMap.begin(),
                    imported.wire.player.statusMap.end(), expected) == imported.wire.player.statusMap.end())
                throw std::runtime_error(std::string("raw player power failed: ") + name + ": " + imported.reason);
            if (status == PlayerStatus::INTANGIBLE || status == PlayerStatus::DOUBLE_DAMAGE) {
                if (!(imported.wire.player.justAppliedBits & (1U << static_cast<int>(status))))
                    throw std::runtime_error("raw timed player power lost justApplied");
                raw["silverRoot"]["combat"]["playerPowers"][0].erase("justApplied");
                if (one_combat::advisor::importSilverRoot(raw).reason != "silver_unmapped_player_power")
                    throw std::runtime_error("raw timed player power bypassed lifetime qualification");
            }
        }
        auto confusion = general;
        confusion["silverRoot"]["combat"]["playerPowers"] = json::array({
            json{{"id", "Confusion"}, {"amount", -1}}});
        const auto confused = one_combat::advisor::importSilverRoot(confusion);
        if (!confused.ok || !(confused.wire.player.statusBits0
                & (1ULL << static_cast<int>(PlayerStatus::CONFUSED))))
            throw std::runtime_error("raw Confusion presence was not imported");
        for (const int baseEnergy : {3, 4}) {
            auto berserk = general;
            auto &combat = berserk["silverRoot"]["combat"];
            combat["energyPerTurn"] = baseEnergy;
            combat["playerPowers"] = json::array({json{{"id", "Berserk"}, {"amount", 2}}});
            const auto imported = one_combat::advisor::importSilverRoot(berserk);
            if (!imported.ok || imported.wire.player.energyPerTurn != baseEnergy + 2
                || imported.wire.player.energy != generalImported.wire.player.energy)
                throw std::runtime_error("Berserk did not add only to future turn energy");
            for (const int invalid : {-1, 0, 128}) {
                combat["playerPowers"][0]["amount"] = invalid;
                if (one_combat::advisor::importSilverRoot(berserk).reason != "silver_unmapped_player_power")
                    throw std::runtime_error("invalid Berserk amount accepted");
            }
            combat["playerPowers"][0]["amount"] = 1;
            combat.erase("energyPerTurn");
            if (one_combat::advisor::importSilverRoot(berserk).reason != "silver_unmapped_player_power")
                throw std::runtime_error("Berserk accepted without captured base turn energy");
        }
        for (const json invalidEnergy : {json(-1), json(128), json(4294967300LL), json("4")}) {
            auto invalid = general;
            invalid["silverRoot"]["combat"]["energyPerTurn"] = invalidEnergy;
            if (one_combat::advisor::importSilverRoot(invalid).reason != "silver_unmapped_player_power")
                throw std::runtime_error("invalid turn energy was narrowed or accepted");
        }
        const std::pair<const char *, MonsterStatus> rawMonsterPowers[] = {
            {"Shackled", MonsterStatus::SHACKLED},
            {"Generic Strength Up Power", MonsterStatus::GENERIC_STRENGTH_UP},
            {"Regenerate", MonsterStatus::REGEN},
            {"Painful Stabs", MonsterStatus::PAINFUL_STABS}, {"Life Link", MonsterStatus::REGROW}};
        for (const auto &[name, status] : rawMonsterPowers) {
            auto raw = general;
            const int amount = sts::isBooleanPower(status) ? -1 : 2;
            raw["silverRoot"]["combat"]["monsters"][0]["powers"] = json::array({
                json{{"id", name}, {"amount", amount}}});
            const auto imported = one_combat::advisor::importSilverRoot(raw);
            if (!imported.ok || !(imported.wire.monsters[0].statusBits & (1ULL << static_cast<int>(status))))
                throw std::runtime_error(std::string("raw monster power failed: ") + name + ": " + imported.reason);
            if (status == MonsterStatus::SHACKLED && imported.wire.monsters[0].smallPowers[10] != amount)
                throw std::runtime_error("Shackled lost temporary strength restoration");
            if (status == MonsterStatus::REGEN && imported.wire.monsters[0].smallPowers[9] != amount)
                throw std::runtime_error("Regenerate lost healing amount");
        }
        auto awakened = general;
        awakened["silverRoot"]["encounter"] = "AWAKENED_ONE";
        auto &awakenedMonster = awakened["silverRoot"]["combat"]["monsters"][0];
        awakenedMonster["id"] = "AwakenedOne";
        awakenedMonster["miscInfo"] = 0;
        awakenedMonster["moveHistory"] = json::array({1});
        awakenedMonster["powers"] = json::array({json{{"id", "Unawakened"}, {"amount", -1}}});
        const auto unawakened = one_combat::advisor::importSilverRoot(awakened);
        if (!unawakened.ok || unawakened.wire.monsters[0].miscInfo != 0
                || unawakened.wire.monsters[0].statusBits != 0)
            throw std::runtime_error("Unawakened did not preserve native phase without adding a status");
        awakenedMonster["miscInfo"] = 1;
        if (one_combat::advisor::importSilverRoot(awakened).reason != "silver_unmapped_monster_power")
            throw std::runtime_error("Unawakened accepted in phase two");
        awakenedMonster["powers"] = json::array();
        awakenedMonster["moveHistory"] = json::array({5});
        const auto phaseTwo = one_combat::advisor::importSilverRoot(awakened);
        if (!phaseTwo.ok || !(phaseTwo.wire.monsters[0].statusBits
                & (1ULL << static_cast<int>(MonsterStatus::MINION_LEADER))))
            throw std::runtime_error("Awakened phase two lost native leader victory rule");
        auto withCultist = phaseTwo.wire;
        withCultist.monsters[1] = generalImported.wire.monsters[0];
        withCultist.monsters[1].idx = 1;
        withCultist.monsterCount = withCultist.monstersAlive = 2;
        auto phaseTwoBattle = battleContextFromWire(withCultist);
        phaseTwoBattle.monsters.arr[0].die(phaseTwoBattle);
        if (phaseTwoBattle.outcome != Outcome::PLAYER_VICTORY)
            throw std::runtime_error("Awakened phase two death did not end combat with a Cultist alive");
        awakenedMonster["halfDead"] = true;
        if (one_combat::advisor::importSilverRoot(awakened).reason != "silver_unmapped_monster_state")
            throw std::runtime_error("Awakened phase two accepted contradictory half-dead state");
        awakenedMonster["halfDead"] = false;
        awakenedMonster["moveHistory"] = json::array({1});
        awakenedMonster["powers"] = json::array({json{{"id", "Unawakened"}, {"amount", -1}}});
        awakenedMonster["miscInfo"] = 0;
        awakenedMonster["id"] = "Cultist";
        if (one_combat::advisor::importSilverRoot(awakened).reason != "silver_unmapped_monster_power")
            throw std::runtime_error("Unawakened accepted on the wrong monster");
        for (const int turnsLeft : {3, 2, 1}) {
            auto explosive = general;
            explosive["silverRoot"]["encounter"] = "THREE_SHAPES";
            auto &monster = explosive["silverRoot"]["combat"]["monsters"][0];
            monster["id"] = "Exploder";
            monster["miscInfo"] = 0;
            monster["moveHistory"] = turnsLeft == 3 ? json::array({1})
                : turnsLeft == 2 ? json::array({1, 1}) : json::array({1, 2});
            monster["powers"] = json::array({json{{"id", "Explosive"}, {"amount", turnsLeft}}});
            const auto imported = one_combat::advisor::importSilverRoot(explosive);
            if (!imported.ok || imported.wire.monsters[0].statusBits != 0)
                throw std::runtime_error("Explosive countdown failed to match native moves: " + imported.reason);
            monster["powers"][0]["amount"] = turnsLeft + 1;
            if (one_combat::advisor::importSilverRoot(explosive).reason != "silver_unmapped_monster_power")
                throw std::runtime_error("contradictory Explosive countdown accepted");
        }
        auto compulsive = general;
        compulsive["silverRoot"]["encounter"] = "WRITHING_MASS";
        auto &writhing = compulsive["silverRoot"]["combat"]["monsters"][0];
        writhing["id"] = "WrithingMass";
        writhing["miscInfo"] = 0;
        writhing["moveHistory"] = json::array({javaMoveByte("WrithingMass", MonsterMoveId::WRITHING_MASS_FLAIL)});
        writhing["powers"] = json::array({json{{"id", "Compulsive"}, {"amount", -1}}});
        const auto reactive = one_combat::advisor::importSilverRoot(compulsive);
        if (!reactive.ok || reactive.wire.monsters[0].uniquePower1 != 0
                || !(reactive.wire.monsters[0].statusBits & (1ULL << static_cast<int>(MonsterStatus::REACTIVE))))
            throw std::runtime_error("Compulsive marker did not map to resolved native reactive state: " + reactive.reason);
        writhing["uniquePower1"] = 1;
        if (one_combat::advisor::importSilverRoot(compulsive).reason != "silver_unmapped_monster_power")
            throw std::runtime_error("Compulsive accepted with an unresolved native roll");
        auto ritualPower = general;
        ritualPower["silverRoot"]["combat"]["monsters"][0]["powers"] = json::array({
            json{{"id", "Ritual"}, {"amount", 3}, {"justApplied", false}}});
        auto ritualImported = one_combat::advisor::importSilverRoot(ritualPower);
        if (!ritualImported.ok
            || ritualImported.wire.monsters[0].uniquePower0 != 3
            || !(ritualImported.wire.monsters[0].statusBits
                & (1ULL << static_cast<int>(MonsterStatus::RITUAL)))
            || (ritualImported.wire.monsters[0].statusBits & (1ULL << 61)))
            throw std::runtime_error("monster Ritual false justApplied parity failed");
        ritualPower["silverRoot"]["combat"]["monsters"][0]["powers"][0]["justApplied"] = true;
        ritualImported = one_combat::advisor::importSilverRoot(ritualPower);
        if (!ritualImported.ok
            || !(ritualImported.wire.monsters[0].statusBits & (1ULL << 61)))
            throw std::runtime_error("monster Ritual true justApplied parity failed");
        auto weakenedPower = general;
        weakenedPower["silverRoot"]["combat"]["playerPowers"] = json::array({
            json{{"id", "Weakened"}, {"amount", 1}, {"justApplied", true}}});
        auto weakenedImported = one_combat::advisor::importSilverRoot(weakenedPower);
        bool weakenedMapped = false;
        for (const auto &[status, amount] : weakenedImported.wire.player.statusMap)
            weakenedMapped |= status == static_cast<std::int16_t>(PlayerStatus::WEAK) && amount == 1;
        if (!weakenedImported.ok || !weakenedMapped
            || !(weakenedImported.wire.player.justAppliedBits
                & (1U << static_cast<int>(PlayerStatus::WEAK))))
            throw std::runtime_error("player Weakened alias/justApplied parity failed");
        auto flexPower = general;
        flexPower["silverRoot"]["combat"]["playerPowers"] = json::array({
            json{{"id", "Flex"}, {"amount", 5}}});
        const auto flexImported = one_combat::advisor::importSilverRoot(flexPower);
        bool flexMapped = false;
        for (const auto &[status, amount] : flexImported.wire.player.statusMap)
            flexMapped |= status == static_cast<std::int16_t>(PlayerStatus::LOSE_STRENGTH) && amount == 5;
        if (!flexImported.ok || !flexMapped)
            throw std::runtime_error("player Flex temporary-strength-loss parity failed");
        auto blueSlaver = general;
        blueSlaver["silverRoot"]["encounter"] = "BLUE_SLAVER";
        auto &blueSlaverMonster = blueSlaver["silverRoot"]["combat"]["monsters"][0];
        blueSlaverMonster["id"] = "SlaverBlue";
        blueSlaverMonster["nextMove"] = javaMoveByte("SlaverBlue", MonsterMoveId::BLUE_SLAVER_STAB);
        blueSlaverMonster["moveHistory"] = json::array({blueSlaverMonster["nextMove"]});
        blueSlaverMonster["powers"] = json::array();
        blueSlaverMonster["miscInfo"] = 0;
        const auto blueSlaverImported = one_combat::advisor::importSilverRoot(blueSlaver);
        if (!blueSlaverImported.ok || blueSlaverImported.wire.monsters[0].miscInfo != 0)
            throw std::runtime_error("Blue Slaver zero miscInfo parity failed: reason="
                + blueSlaverImported.reason + " move="
                + std::to_string(blueSlaverMonster["nextMove"].get<int>()));
        const char *offColorLocations[] = {"hand", "draw", "discard", "exhaust"};
        const char *offColorCards[] = {"Neutralize", "Zap", "Eruption", "Neutralize"};
        const auto placeOffColorCard = [&](json &combat, const char *location, const char *cardName) {
            auto &pile = combat[location];
            json card = combat["hand"].at(0);
            card["id"] = cardName;
            card["uuid"] = std::string("off-color-") + location;
            if (pile.is_array()) {
                if (pile.empty()) pile.push_back(std::move(card));
                else pile[0] = std::move(card);
            } else {
                auto &unknown = pile["unknown"];
                if (!unknown.is_array()) unknown = json::array();
                if (unknown.empty()) unknown.push_back(std::move(card));
                else unknown[0] = std::move(card);
            }
        };
        for (int i = 0; i < 4; ++i) {
            auto offColor = general;
            placeOffColorCard(offColor["silverRoot"]["combat"], offColorLocations[i], offColorCards[i]);
            const auto imported = one_combat::advisor::importSilverRoot(offColor);
            if (imported.ok || imported.reason != "silver_off_color_card")
                throw std::runtime_error(std::string("off-color ") + offColorLocations[i]
                    + " was not rejected before Silver search: " + imported.reason);
        }
        auto redAndColorless = general;
        redAndColorless["silverRoot"]["combat"]["hand"][0]["id"] = "Strike_R";
        redAndColorless["silverRoot"]["combat"]["draw"][0]["id"] = "Dramatic Entrance";
        const auto redAndColorlessImported = one_combat::advisor::importSilverRoot(redAndColorless);
        if (!redAndColorlessImported.ok)
            throw std::runtime_error("RED/COLORLESS cards were rejected: " + redAndColorlessImported.reason);
        auto burningGeneric = general;
        burningGeneric["silverRoot"]["burningElite"] = true;
        const auto burningImported = one_combat::advisor::importSilverRoot(burningGeneric);
        if (!burningImported.ok)
            throw std::runtime_error("fully represented generic burning-elite state was rejected: "
                + burningImported.reason);
        auto fourByrds = general;
        fourByrds["silverRoot"]["encounter"] = "FOUR_BYRDS";
        if (one_combat::advisor::importSilverRoot(fourByrds).reason
            != "silver_unsupported_four_byrds")
            throw std::runtime_error("FOUR_BYRDS exclusion was not reported explicitly");
        auto powerBits = general;
        powerBits["silverRoot"]["combat"]["monsters"][0]["powers"] = json::array({
            json{{"id", "Vulnerable"}, {"amount", 2}, {"justApplied", false}}});
        const auto powerImported = one_combat::advisor::importSilverRoot(powerBits);
        if (!powerImported.ok || powerImported.wire.monsters[0].vulnerable != 2
            || !(powerImported.wire.monsters[0].statusBits
                & (1ULL << static_cast<int>(MonsterStatus::VULNERABLE))))
            throw std::runtime_error("monster Vulnerable amount/activation parity failed");
        auto weakenedAlias = general;
        weakenedAlias["silverRoot"]["combat"]["monsters"][0]["powers"] = json::array({
            json{{"id", "Weakened"}, {"amount", 1}, {"justApplied", true}}});
        const auto weakenedMonsterImported = one_combat::advisor::importSilverRoot(weakenedAlias);
        if (!weakenedMonsterImported.ok || weakenedMonsterImported.wire.monsters[0].weak != 1
            || !(weakenedMonsterImported.wire.monsters[0].statusBits
                & (1ULL << static_cast<int>(MonsterStatus::WEAK))))
            throw std::runtime_error("monster Weakened alias/activation parity failed");
        const char *booleanPowerNames[] = {"Minion", "Asleep", "Regrow", "Stasis", "PainfulStabs"};
        const MonsterStatus booleanPowerStatuses[] = {
            MonsterStatus::MINION, MonsterStatus::ASLEEP, MonsterStatus::REGROW,
            MonsterStatus::STASIS, MonsterStatus::PAINFUL_STABS};
        for (int i = 0; i < 5; ++i) {
            auto booleanPower = general;
            booleanPower["silverRoot"]["combat"]["monsters"][0]["powers"] = json::array({
                json{{"id", booleanPowerNames[i]}, {"amount", -1}}});
            const auto imported = one_combat::advisor::importSilverRoot(booleanPower);
            if (!imported.ok || !(imported.wire.monsters[0].statusBits
                    & (1ULL << static_cast<int>(booleanPowerStatuses[i]))))
                throw std::runtime_error(std::string("negative boolean power was discarded: ")
                    + booleanPowerNames[i] + " reason=" + imported.reason);
        }
        auto invalidNegativePower = general;
        invalidNegativePower["silverRoot"]["combat"]["monsters"][0]["powers"] = json::array({
            json{{"id", "Slow"}, {"amount", -1}}});
        if (one_combat::advisor::importSilverRoot(invalidNegativePower).reason
            != "silver_unmapped_monster_power")
            throw std::runtime_error("negative numeric monster power was silently accepted");
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
        assertAbsentLimboAndStasisLayout(eyeImported.wire, "Frozen Eye");
        auto stasis = general;
        stasis["silverRoot"]["encounter"] = "AUTOMATON";
        stasis["silverRoot"]["combat"]["monsters"][0]["id"] = "BronzeOrb";
        stasis["silverRoot"]["combat"]["monsters"][0]["nextMove"] = 3;
        stasis["silverRoot"]["combat"]["monsters"][0]["moveHistory"] = json::array({3});
        stasis["silverRoot"]["combat"]["monsters"][0]["miscInfo"] = 1;
        stasis["silverRoot"]["combat"]["monsters"][0]["powers"] = json::array({
            json{{"id", "Stasis"}, {"amount", 1}}});
        stasis["silverRoot"]["combat"]["stasis"] = json::array({
            json{{"id", "Strike_R"}, {"uuid", "stasis-card"}, {"slot", 0}, {"upgraded", false},
                 {"misc", 0}, {"cost", 1}, {"costForTurn", 1},
                 {"freeToPlayOnce", false}, {"retain", false}}});
        const auto stasisImported = one_combat::advisor::importSilverRoot(stasis);
        if (!stasisImported.ok || stasisImported.wire.stasisCards[0].id
                != static_cast<std::int16_t>(CardId::STRIKE_RED)
            || !(stasisImported.wire.monsters[0].statusBits
                & (1ULL << static_cast<int>(MonsterStatus::STASIS))))
            throw std::runtime_error("Bronze Orb Stasis card/state was not imported exactly");
        // Java StasisPower.onDeath returns the card with its UUID while the
        // dead orb still lists the same card in its Stasis power.
        auto returnedStasis = stasis;
        returnedStasis["silverRoot"]["combat"]["monsters"][0]["hp"] = 0;
        returnedStasis["silverRoot"]["combat"]["monsters"][0]["dead"] = true;
        returnedStasis["silverRoot"]["combat"]["hand"].push_back(
            returnedStasis["silverRoot"]["combat"]["stasis"][0]);
        returnedStasis["silverRoot"]["combat"]["hand"].back().erase("slot");
        const auto returnedImported = one_combat::advisor::importSilverRoot(returnedStasis);
        if (!returnedImported.ok || returnedImported.wire.stasisCards[0].id
                != static_cast<std::int16_t>(CardId::INVALID)
            || returnedImported.wire.stasisCards[0].uniqueId != -1
            || std::count_if(returnedImported.wire.hand.begin(), returnedImported.wire.hand.end(),
                   [](const auto &card) { return card.id == static_cast<std::int16_t>(CardId::STRIKE_RED); })
                != std::count_if(stasisImported.wire.hand.begin(), stasisImported.wire.hand.end(),
                   [](const auto &card) { return card.id == static_cast<std::int16_t>(CardId::STRIKE_RED); }) + 1)
            throw std::runtime_error("dead Bronze Orb's returned Stasis card was not imported once: ok="
                + std::to_string(returnedImported.ok) + " reason=" + returnedImported.reason);
        auto aliveDuplicate = returnedStasis;
        aliveDuplicate["silverRoot"]["combat"]["monsters"][0]["hp"] = 20;
        aliveDuplicate["silverRoot"]["combat"]["monsters"][0]["dead"] = false;
        if (one_combat::advisor::importSilverRoot(aliveDuplicate).reason != "silver_card_identity")
            throw std::runtime_error("live Bronze Orb Stasis card duplicated in hand was accepted");
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
        const auto targetObservation = json{{"combat", json{{"monsters", json::array({
            json{{"name", "Cultist"}, {"dead", true}},
            json{{"name", "Louse"}, {"dead", false}},
            json{{"name", "Slaver"}, {"dead", false}}})}}}};
        const auto lowered = one_combat::advisor::selectedLiveAction(
            loweringAction, loweringContext, targetObservation);
        if (lowered.value("kind", std::string()) != "card"
            || lowered.value("cardUuid", std::string()) != "copy-b"
            || lowered.value("targetIndex", 0) != 1)
            throw std::runtime_error("selectedLiveAction did not preserve physical card UUID and target");
        loweringAction.target = 2;
        const auto secondTarget = one_combat::advisor::selectedLiveAction(
            loweringAction, loweringContext, targetObservation);
        if (secondTarget.value("targetIndex", 0) != 2)
            throw std::runtime_error("selectedLiveAction did not compact the second live target");
        loweringAction.target = 0;
        if (!one_combat::advisor::selectedLiveAction(
                loweringAction, loweringContext, targetObservation).is_null())
            throw std::runtime_error("dead Silver target was not rejected");
        loweringAction.type = silver_bridge::SemanticActionType::SINGLE_CARD_SELECT;
        if (!one_combat::advisor::selectedLiveAction(
                loweringAction, loweringContext, targetObservation).is_null())
            throw std::runtime_error("unsupported single-card selection was lowered as executable");
        loweringAction.type = silver_bridge::SemanticActionType::POTION;
        loweringAction.potionSlot = 0;
        loweringAction.target = 1;
        loweringAction.discardPotion = false;
        const auto potionTarget = one_combat::advisor::selectedLiveAction(
            loweringAction, loweringContext, targetObservation);
        if (potionTarget.value("targetIndex", 0) != 1)
            throw std::runtime_error("targeted potion did not compact the Silver target");
        loweringAction.target = 2;
        const auto secondPotionTarget = one_combat::advisor::selectedLiveAction(
            loweringAction, loweringContext, targetObservation);
        if (secondPotionTarget.value("targetIndex", 0) != 2)
            throw std::runtime_error("targeted potion did not compact the second live target");
        std::cout << "live Silver native first-turn parity checks passed\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "live Silver parity FAIL: " << e.what() << '\n';
        return 1;
    }
}
