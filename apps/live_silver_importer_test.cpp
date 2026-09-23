#include "one_combat/live_silver_importer.h"
#include "one_combat/live_silver_mapping.h"

#include <algorithm>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <string>
#include <set>
#include <vector>

#include "combat/Actions.h"
#include "combat/BattleContext.h"
#include "constants/Cards.h"
#include "constants/CardPools.h"
#include "constants/MonsterMoves.h"
#include "game/GameContext.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/SilverBridge.h"
#include "sim/search/SilverHardCombat.h"
#include "sim/search/SilverConversion.h"
#include "sim/search/SilverWireJson.h"
#include "sim/search/Action.h"

using nlohmann::json;
using namespace sts;
using namespace sts::search;
using silver_bridge::BattleStateWire;
using silver_bridge::CardWire;
using silver_bridge::CardQueueItemWire;
using silver_bridge::MonsterWire;
using silver_bridge::SilverRootActionSummary;
using silver_bridge::SilverSearchConfig;
using silver_bridge::SilverRerootFallbackReason;
using silver_bridge::convertedStatesEqualForSearch;
using silver_bridge::runSilverDecision;
using silver_bridge::semanticActionFingerprint;

namespace {
struct Fixture { const char *name; int move; const char *room; BattleStateWire wire; json observation; };
json observation(const BattleStateWire &, const char *, int, const char *,
                 int = 0, json = json::array());
json cardJson(const CardWire &);
json genericObservation(const Fixture &, const char *);
void setProducerV4CardObservation(json &, const BattleStateWire &);

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
            {"id", name}, {"slot", monster.idx}, {"idx", monster.idx},
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
        } else if (id == "BronzeOrb") {
            const auto &powers = monster["powers"];
            const bool usedStasis = std::any_of(powers.begin(), powers.end(), [](const json &power) {
                return power.value("id", std::string()) == "Stasis";
            });
            monster["miscInfo"] = usedStasis ? 1 : 0;
        }
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
    wire.limbo.clear();
    const auto stasisCards = wire.stasisCards;
    wire.stasisCards.fill(CardWire{});
    for (std::size_t i = 0; i < wire.stasisCards.size(); ++i) {
        auto &card = wire.stasisCards[i];
        if (stasisCards[i].id != static_cast<std::int16_t>(CardId::INVALID))
            card = stasisCards[i];
        if (card.id != static_cast<std::int16_t>(CardId::INVALID))
            card.uniqueId = static_cast<std::int16_t>(nextId++);
    }
    wire.nextUniqueCardId = nextId;
    wire.observedGeneration = 1;
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
    if (one_combat::advisor::live_silver::monsterStatusForMonster("Darkling", "Life Link")
            != MonsterStatus::REGROW
        || one_combat::advisor::live_silver::monsterStatusForMonster("AwakenedOne", "Life Link").has_value())
        throw std::runtime_error("ambiguous Life Link power lost monster-specific lowering");
    expect("Deca", 0, MonsterMoveId::DECA_BEAM);
    expect("Deca", 2, MonsterMoveId::DECA_SQUARE_OF_PROTECTION);
    expect("Donu", 0, MonsterMoveId::DONU_BEAM);
    expect("Donu", 2, MonsterMoveId::DONU_CIRCLE_OF_POWER);
    expect("Exploder", 1, MonsterMoveId::EXPLODER_SLAM);
    expect("Exploder", 2, MonsterMoveId::EXPLODER_EXPLODE);
    for (int turn = 1; turn <= 3; ++turn) {
        if (!one_combat::advisor::live_silver::nativeImplicitMonsterPower(
                "Exploder", "Explosive", 4 - turn, turn, 0)
            || one_combat::advisor::live_silver::nativeImplicitMonsterPower(
                "Exploder", "Explosive", 3, turn + 1, 0))
            throw std::runtime_error("Exploder countdown/native script boundary changed");
    }
    if (one_combat::advisor::live_silver::nativeImplicitMonsterPower(
            "Spiker", "Explosive", 3, 1, 0)
        || one_combat::advisor::live_silver::nativeImplicitMonsterPower(
            "Exploder", "Thorns", 3, 1, 0)
        || !one_combat::advisor::live_silver::nativeImplicitMonsterPower(
            "AwakenedOne", "Unawakened", -1, 1, 0)
        || one_combat::advisor::live_silver::nativeImplicitMonsterPower(
            "AwakenedOne", "Unawakened", -1, 1, 1)
        || one_combat::advisor::live_silver::nativeImplicitMonsterPower(
            "Cultist", "Unawakened", -1, 1, 0))
        throw std::runtime_error("implicit monster power accepted on a mismatched entity or phase");
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
int main() {
    try {
        // Exact POWER_ID constants from the pinned desktop-1.0.jar, rather
        // than Java class names. Keep this audit broad enough to catch the
        // next vanilla player power before a live run reaches it.
        const std::vector<std::pair<std::string, PlayerStatus>> vanillaPlayerPowers = {
            {"Accuracy", PlayerStatus::ACCURACY}, {"After Image", PlayerStatus::AFTER_IMAGE},
            {"Amplify", PlayerStatus::AMPLIFY}, {"Bias", PlayerStatus::BIAS},
            {"Blur", PlayerStatus::BLUR}, {"Brutality", PlayerStatus::BRUTALITY},
            {"Burst", PlayerStatus::BURST}, {"Collect", PlayerStatus::COLLECT},
            {"Constricted", PlayerStatus::CONSTRICTED}, {"Creative AI", PlayerStatus::CREATIVE_AI},
            {"Double Damage", PlayerStatus::DOUBLE_DAMAGE}, {"Draw Card", PlayerStatus::DRAW_CARD_NEXT_TURN},
            {"Draw Reduction", PlayerStatus::DRAW_REDUCTION}, {"Energized", PlayerStatus::ENERGIZED},
            {"Envenom", PlayerStatus::ENVENOM}, {"Equilibrium", PlayerStatus::EQUILIBRIUM},
            {"Infinite Blades", PlayerStatus::INFINITE_BLADES}, {"IntangiblePlayer", PlayerStatus::INTANGIBLE},
            {"Loop", PlayerStatus::LOOP}, {"DexLoss", PlayerStatus::LOSE_DEXTERITY},
            {"Magnetism", PlayerStatus::MAGNETISM}, {"Mayhem", PlayerStatus::MAYHEM},
            {"Next Turn Block", PlayerStatus::NEXT_TURN_BLOCK}, {"Noxious Fumes", PlayerStatus::NOXIOUS_FUMES},
            {"Rebound", PlayerStatus::REBOUND}, {"StaticDischarge", PlayerStatus::STATIC_DISCHARGE},
            {"Surrounded", PlayerStatus::SURROUNDED}, {"Thousand Cuts", PlayerStatus::THOUSAND_CUTS},
            {"Tools Of The Trade", PlayerStatus::TOOLS_OF_THE_TRADE},
            {"Echo Form", PlayerStatus::ECHO_FORM}, {"Electro", PlayerStatus::ELECTRO},
            {"Double Tap", PlayerStatus::DOUBLE_TAP},
            {"Sadistic", PlayerStatus::SADISTIC}, {"Phantasmal", PlayerStatus::PHANTASMAL},
        };
        for (const auto &[powerId, status] : vanillaPlayerPowers)
            if (one_combat::advisor::live_silver::playerStatus(powerId) != status)
                throw std::runtime_error("vanilla player POWER_ID mapping missing: " + powerId);
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
                || !silver_bridge::convertedStateHistoricalQueueItemForTest(wire))
                throw std::runtime_error("quiescent live GAMBLE lost queue-item provenance");
            const auto stateHash = silver_bridge::hardCombatStateHash(wire);
            const auto snapshot = silver_bridge::hardCombatSnapshot(wire, game.seed,
                0, "hallway", std::string(40, 'a'),
                silver_bridge::hardCombatBenchmarkSeed(stateHash),
                {{"simulations", 1000}, {"reuse_cap", 32768},
                 {"reuse_mode", "allocated"}, {"adaptive", false},
                 {"exact_lock", false}, {"rho", false}});
            const auto replayWire = silver_bridge::validateHardCombatSnapshot(
                json::parse(snapshot.dump()));
            if (!replayWire.historicalQueueItemAtSource
                || !silver_bridge::convertedStateHistoricalQueueItemForTest(replayWire))
                throw std::runtime_error("trusted hard-combat capture lost queue provenance");
            live.cardSelectInfo.cardSelectTask = CardSelectTask::HEADBUTT;
            live.curCardQueueItem.card = CardInstance(CardId::HEADBUTT);
            live.actionQueue.pushBack(Actions::OnAfterCardUsed());
            wire = makeSilverBattleStateWire(live, knowledge,
                makeSilverRunContext(game), 0x71517u);
            if (!wire.valid || wire.historicalQueueItemAtSource
                || silver_bridge::convertedStateHistoricalQueueItemForTest(wire))
                throw std::runtime_error("pending live Headbutt became historical after wire conversion");
            live.actionQueue.clear();
            wire = makeSilverBattleStateWire(live, knowledge,
                makeSilverRunContext(game), 0x71517u);
            if (!wire.valid || !wire.historicalQueueItemAtSource
                || !silver_bridge::convertedStateHistoricalQueueItemForTest(wire))
                throw std::runtime_error("settled live selection did not preserve provenance");
            const auto serialized = json(wire).get<BattleStateWire>();
            if (serialized.historicalQueueItemAtSource
                || silver_bridge::convertedStateHistoricalQueueItemForTest(serialized))
                throw std::runtime_error("legacy JSON manufactured queue-item provenance");
        }
        verifyRuntimeMoveBoundary();
        verifyEncounterManifestAndNativeSweep();
        verifyDynamicTransitionCorpus();
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
        {
            // The Java v4 producer does not emit monsterTurnIdx at a stable
            // player decision. A missing field must retain the native player-
            // turn sentinel, not schedule monsters after the next card play.
            auto producerShaped = multi.observation;
            producerShaped["silverRoot"]["combat"].erase("monsterTurnIdx");
            const auto imported = one_combat::advisor::importSilverRoot(producerShaped);
            if (!imported.ok || imported.wire.monsterTurnIdx != multi.wire.monsterTurnIdx)
                throw std::runtime_error("missing producer monsterTurnIdx changed player-turn phase");
            auto session = silver_bridge::makeSilverSearchSession();
            SilverSearchConfig config;
            config.simulationsPerDecision = 64;
            config.adaptiveEnabled = false;
            const auto decision = runSilverDecision(*session, imported.wire, config);
            silver_bridge::SilverTreeSnapshotConfig treeConfig;
            treeConfig.enabled = true;
            treeConfig.maxNodes = 256;
            const auto tree = silver_bridge::snapshotSilverSearchTree(*session, treeConfig);
            if (!decision.accepted || !tree.accepted)
                throw std::runtime_error("producer-shaped root search failed");
            bool sawCard = false;
            for (const auto &edge : tree.edges) {
                if (edge.parentId != tree.rootId
                    || edge.actionLabel.find("use card") == std::string::npos) continue;
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
        verifyPlayerPowerParity("live-confusion-parity", json{{"id", "Confusion"}, {"amount", -1}},
            [](auto &player) { player.statusBits0 |= 1ULL << static_cast<int>(PlayerStatus::CONFUSED); });
        verifyPlayerPowerParity("hex-parity", json{{"id", "Hex"}, {"amount", 1}},
            [](auto &player) { player.statusBits0 |= 1ULL << static_cast<int>(PlayerStatus::HEX); });
        verifyPlayerPowerParity("pen-nib-parity", json{{"id", "Pen Nib"}, {"amount", 1}},
            [](auto &player) { player.statusBits0 |= 1ULL << static_cast<int>(PlayerStatus::PEN_NIB); });
        verifyPlayerPowerParity("live-flame-barrier-parity", json{{"id", "Flame Barrier"}, {"amount", 4}},
            [](auto &player) {
                player.statusBits0 |= 1ULL << static_cast<int>(PlayerStatus::FLAME_BARRIER);
                player.statusMap.emplace_back(static_cast<std::int16_t>(PlayerStatus::FLAME_BARRIER), 4);
            });
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
        auto unknownSelection = nativeSelection;
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
            const auto entry = candidate.observation.value("combatEntryHash", "entry-v4");
            auto imported = one_combat::advisor::importSilverRoot(
                genericObservation(candidate, entry.c_str()));
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
        if (generalImported.wire.extraRollMoveOnTurn != 0
            || generalImported.wire.skipMonsterTurnBits != 0)
            throw std::runtime_error("explicit stable-boundary group state was not preserved");
        auto runicGeneric = general;
        runicGeneric["silverRoot"]["combat"]["runicDome"] = true;
        auto &runicMonster = runicGeneric["silverRoot"]["combat"]["monsters"][0];
        runicMonster.erase("nextMove");
        runicMonster.erase("moveHistory");
        runicMonster.erase("intent");
        runicMonster.erase("intentDamage");
        runicMonster["publicMoveHistory"] = json::array({0, 0});
        runicMonster["publicMoveHistoryCount"] = 0;
        runicMonster["pendingMoveRolls"] = 1;
        runicMonster["pendingDirectMoveChoice"] = 0;
        runicMonster["pendingRollInputs"] = {
            {"curHp", runicMonster["hp"]}, {"maxHp", runicMonster["maxHp"]},
            {"knightCurHp", general["silverRoot"]["hp"]},
            {"knightMaxHp", general["silverRoot"]["maxHp"]},
            {"monsterTurnNumber", 1}, {"miscInfo", runicMonster.value("miscInfo", 0)},
            {"aliveCount", 1}, {"monstersAlive", 1}, {"knightAlive", true},
            {"playerConstricted", false}, {"asleep", false}, {"halfDead", false}};
        const auto runicImported = one_combat::advisor::importSilverRoot(runicGeneric);
        if (!runicImported.ok || !runicImported.wire.intentsHidden
            || runicImported.wire.monsters[0].pendingMoveRolls != 1
            || runicImported.wire.monsters[0].pendingDirectMoveChoice != 0
            || runicImported.wire.monsters[0].moveHistory[0] != 0
            || runicImported.wire.monsters[0].moveHistory[1] != 0)
            throw std::runtime_error("generic Runic Dome deferred-intent import failed: "
                + runicImported.reason);
        for (const auto &[monsterId, expectedMove] : {
                std::pair{"Donu", static_cast<int>(MonsterMoveId::DONU_BEAM)},
                std::pair{"Deca", static_cast<int>(MonsterMoveId::DECA_BEAM)},
                std::pair{"WrithingMass", static_cast<int>(MonsterMoveId::WRITHING_MASS_STRONG_STRIKE)}}) {
            auto publicZeroHistory = runicGeneric;
            auto &zeroMonster = publicZeroHistory["silverRoot"]["combat"]["monsters"][0];
            zeroMonster["id"] = monsterId;
            zeroMonster["publicMoveHistory"] = json::array({0, 0});
            zeroMonster["publicMoveHistoryCount"] = 1;
            const auto zeroImported = one_combat::advisor::importSilverRoot(publicZeroHistory);
            if (!zeroImported.ok || zeroImported.wire.monsters[0].moveHistory[0] != expectedMove)
                throw std::runtime_error(std::string("Runic public move byte zero lost for ")
                    + monsterId + ": " + zeroImported.reason);
        }
        auto chainedRunic = runicGeneric;
        chainedRunic["silverRoot"]["combat"]["monsters"][0]["pendingMoveRolls"] = 2;
        auto &chainedMonster = chainedRunic["silverRoot"]["combat"]["monsters"][0];
        auto firstRoll = chainedMonster["pendingRollInputs"];
        auto secondRoll = firstRoll;
        secondRoll["monsterTurnNumber"] = 2;
        chainedMonster["pendingRollInputHistory"] = json::array({firstRoll, secondRoll});
        chainedRunic["silverRoot"]["combat"]["monsters"][0]["publicMoveHistory"]
            = json::array({0, 0});
        chainedRunic["silverRoot"]["combat"]["monsters"][0]["publicMoveHistoryCount"] = 0;
        const auto chainedImported = one_combat::advisor::importSilverRoot(chainedRunic);
        if (!chainedImported.ok || chainedImported.wire.monsters[0].pendingMoveRolls != 2
            || chainedImported.wire.monsters[0].pendingRollInputHistory.size() != 2
            || chainedImported.wire.monsters[0].pendingRollInputHistory[1].monsterTurnNumber != 2
            || chainedImported.wire.monsters[0].moveHistory[0] != 0
            || chainedImported.wire.monsters[0].moveHistory[1] != 0)
            throw std::runtime_error("chained Runic hidden rolls changed public move history: "
                + chainedImported.reason);
        auto overlongRunic = chainedRunic;
        overlongRunic["silverRoot"]["combat"]["monsters"][0]["pendingMoveRolls"] = 4;
        if (one_combat::advisor::importSilverRoot(overlongRunic).reason
                != "silver_hidden_information_required")
            throw std::runtime_error("incomplete Runic roll input history was accepted");
        auto &overlongMonster = overlongRunic["silverRoot"]["combat"]["monsters"][0];
        auto thirdRoll = secondRoll;
        thirdRoll["monsterTurnNumber"] = 3;
        auto fourthRoll = secondRoll;
        fourthRoll["monsterTurnNumber"] = 4;
        overlongMonster["pendingRollInputHistory"].push_back(thirdRoll);
        overlongMonster["pendingRollInputHistory"].push_back(fourthRoll);
        const auto fourRollImported = one_combat::advisor::importSilverRoot(overlongRunic);
        if (!fourRollImported.ok
            || fourRollImported.wire.monsters[0].pendingRollInputHistory.size() != 4
            || fourRollImported.wire.monsters[0].pendingRollInputHistory[3].monsterTurnNumber != 4)
            throw std::runtime_error("complete four-roll Runic history was rejected: "
                + fourRollImported.reason);
        auto directRunic = runicGeneric;
        directRunic["silverRoot"]["combat"]["monsters"][0]["pendingMoveRolls"] = 0;
        directRunic["silverRoot"]["combat"]["monsters"][0]["pendingDirectMoveChoice"] = 1;
        const auto directImported = one_combat::advisor::importSilverRoot(directRunic);
        if (!directImported.ok || directImported.wire.monsters[0].pendingMoveRolls != 0
            || directImported.wire.monsters[0].pendingDirectMoveChoice != 1)
            throw std::runtime_error("generic Runic Dome direct-choice import failed: "
                + directImported.reason);
        auto malformedRunic = runicGeneric;
        malformedRunic["silverRoot"]["combat"]["monsters"][0]["pendingRollInputs"].erase("miscInfo");
        if (one_combat::advisor::importSilverRoot(malformedRunic).reason
                != "silver_hidden_information_required")
            throw std::runtime_error("malformed generic Runic Dome inputs were accepted");
        auto privateRunic = runicGeneric;
        auto &privateMonster = privateRunic["silverRoot"]["combat"]["monsters"][0];
        privateMonster["privateMiscInfoUnderRunic"] = true;
        privateMonster.erase("miscInfo");
        privateMonster["pendingRollInputs"].erase("miscInfo");
        if (one_combat::advisor::importSilverRoot(privateRunic).reason
                != "silver_hidden_information_required")
            throw std::runtime_error("non-Louse private Runic miscInfo was accepted");
        privateMonster["id"] = "FuzzyLouseNormal";
        privateMonster.erase("privateMiscInfoUnderRunic");
        privateMonster["miscInfo"] = 6;
        if (one_combat::advisor::importSilverRoot(privateRunic).reason
                != "silver_hidden_information_required")
            throw std::runtime_error("Runic Louse private field was accepted without a posterior");
        privateMonster.erase("miscInfo");
        privateMonster["privateMiscInfoUnderRunic"] = true;
        privateMonster["publicMiscCandidateMask"] = 7;
        const auto privateImported = one_combat::advisor::importSilverRoot(privateRunic);
        if (!privateImported.ok || privateImported.wire.monsters[0].miscInfo != -7
            || privateImported.wire.monsters[0].pendingRollInputs.miscInfo != -7)
            throw std::runtime_error("public Runic Louse damage support was not imported: "
                + privateImported.reason);
        std::set<int> sampledPrivateDamage;
        for (int sample = 0; sample < 32; ++sample) {
            auto particle = privateImported.wire;
            particle.isolatedSearchSeed += sample;
            const auto resolved = silver_bridge::materializeDeferredMonsterIntentsForTest(particle);
            if (!resolved.accepted || resolved.monsterMiscInfo[0] < 5
                || resolved.monsterMiscInfo[0] > 7)
                throw std::runtime_error("Runic Louse prior sampled outside native support");
            sampledPrivateDamage.insert(resolved.monsterMiscInfo[0]);
        }
        if (sampledPrivateDamage.size() < 2)
            throw std::runtime_error("Runic Louse private damage prior was not sampled");
        silver_bridge::SilverSearchConfig privateSearch;
        privateSearch.simulationsPerDecision = 16;
        privateSearch.reuseCapMode = silver_bridge::SilverReuseCapMode::NONE;
        const auto privateDecision = silver_bridge::runSilverDecision(
            privateImported.wire, privateSearch);
        if (!privateDecision.accepted)
            throw std::runtime_error("Silver could not search a Runic Louse belief root: "
                + privateDecision.failureReason);
        privateMonster["publicMiscCandidateMask"] = 4;
        const auto singletonImported = one_combat::advisor::importSilverRoot(privateRunic);
        if (!singletonImported.ok || singletonImported.wire.monsters[0].miscInfo != -4)
            throw std::runtime_error("conditioned Runic Louse damage support was lost");
        const auto resolvedPrivate = silver_bridge::materializeDeferredMonsterIntentsForTest(
            singletonImported.wire);
        if (!resolvedPrivate.accepted || resolvedPrivate.monsterMiscInfo[0] != 7)
            throw std::runtime_error("Runic Louse posterior did not persist into deferred move");
        privateMonster["publicMiscCandidateMask"] = 0;
        if (one_combat::advisor::importSilverRoot(privateRunic).reason
                != "silver_hidden_information_required")
            throw std::runtime_error("contradictory public Runic damage evidence was accepted");
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
        auto intangiblePower = general;
        intangiblePower["silverRoot"]["combat"]["playerPowers"] = json::array({
            json{{"id", "IntangiblePlayer"}, {"amount", 1}}});
        const auto intangibleImported = one_combat::advisor::importSilverRoot(intangiblePower);
        bool intangibleMapped = false;
        for (const auto &[status, amount] : intangibleImported.wire.player.statusMap)
            intangibleMapped |= status == static_cast<std::int16_t>(PlayerStatus::INTANGIBLE) && amount == 1;
        if (!intangibleImported.ok || !intangibleMapped
            || !(intangibleImported.wire.player.justAppliedBits
                & (1U << static_cast<int>(PlayerStatus::INTANGIBLE))))
            throw std::runtime_error("vanilla IntangiblePlayer lost native status bookkeeping");
        auto flexPower = general;
        flexPower["silverRoot"]["combat"]["playerPowers"] = json::array({
            json{{"id", "Flex"}, {"amount", 5}}});
        const auto flexImported = one_combat::advisor::importSilverRoot(flexPower);
        bool flexMapped = false;
        for (const auto &[status, amount] : flexImported.wire.player.statusMap)
            flexMapped |= status == static_cast<std::int16_t>(PlayerStatus::LOSE_STRENGTH) && amount == 5;
        if (!flexImported.ok || !flexMapped)
            throw std::runtime_error("player Flex temporary-strength-loss parity failed");
        auto regenPower = general;
        regenPower["silverRoot"]["combat"]["playerPowers"] = json::array({
            json{{"id", "Regeneration"}, {"amount", 5}}});
        const auto regenImported = one_combat::advisor::importSilverRoot(regenPower);
        bool regenMapped = false;
        for (const auto &[status, amount] : regenImported.wire.player.statusMap)
            regenMapped |= status == static_cast<std::int16_t>(PlayerStatus::REGEN) && amount == 5;
        if (!regenImported.ok || !regenMapped)
            throw std::runtime_error("player Regeneration potion power parity failed");
        auto doubleTapPower = general;
        doubleTapPower["silverRoot"]["combat"]["playerPowers"] = json::array({
            json{{"id", "Double Tap"}, {"amount", 1}}});
        const auto doubleTapImported = one_combat::advisor::importSilverRoot(doubleTapPower);
        bool doubleTapMapped = false;
        for (const auto &[status, amount] : doubleTapImported.wire.player.statusMap)
            doubleTapMapped |= status == static_cast<std::int16_t>(PlayerStatus::DOUBLE_TAP) && amount == 1;
        if (!doubleTapImported.ok || !doubleTapMapped)
            throw std::runtime_error("player Double Tap power parity failed");
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
        // The live Act-1 Jaw Worm failure had both Dramatic Entrance and Combust.
        // Combust was incorrectly labeled GREEN by the native card-color table.
        redAndColorless["silverRoot"]["combat"]["draw"][1]["id"] = "Combust";
        if (getCardColor(CardId::COLLECT) != CardColor::PURPLE
            || getCardColor(CardId::COMBUST) != CardColor::RED
            || getCardColor(CardId::COMPILE_DRIVER) != CardColor::BLUE
            || getCardColor(CardId::CONCENTRATE) != CardColor::GREEN)
            throw std::runtime_error("native card colors around Combust are misordered");
        const CardColor classColors[] = {CardColor::RED, CardColor::GREEN,
                                         CardColor::BLUE, CardColor::PURPLE};
        for (int color = 0; color < 4; ++color)
            for (int i = 0; i < TransformCardPool::cardPoolSize[color]; ++i)
                if (getCardColor(TransformCardPool::colorCardPool[color][i]) != classColors[color])
                    throw std::runtime_error("native class card color differs from its canonical pool");
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
        auto panachePower = general;
        panachePower["silverRoot"]["combat"]["panacheCounter"] = 3;
        panachePower["silverRoot"]["combat"]["playerPowers"] = json::array({
            json{{"id", "Panache"}, {"amount", 10}}});
        const auto panacheImported = one_combat::advisor::importSilverRoot(panachePower);
        const bool panacheDamage = panacheImported.ok && std::find(
            panacheImported.wire.player.statusMap.begin(),
            panacheImported.wire.player.statusMap.end(),
            std::pair<std::int16_t, std::int16_t>{
                static_cast<std::int16_t>(PlayerStatus::PANACHE), 10})
            != panacheImported.wire.player.statusMap.end();
        if (!panacheImported.ok || panacheImported.wire.player.panacheCounter != 3
            || !panacheDamage)
            throw std::runtime_error("Panache damage/countdown import lost distinct values: "
                + panacheImported.reason);
        panachePower["silverRoot"]["combat"]["panacheCounter"] = 0;
        if (one_combat::advisor::importSilverRoot(panachePower).reason
                != "silver_unmapped_player_power")
            throw std::runtime_error("invalid Panache countdown was accepted");
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
        auto writhing = general;
        writhing["silverRoot"]["encounter"] = "WRITHING_MASS";
        writhing["silverRoot"]["combat"]["monsters"][0]["id"] = "WrithingMass";
        writhing["silverRoot"]["combat"]["monsters"][0]["nextMove"] = 1;
        writhing["silverRoot"]["combat"]["monsters"][0]["moveHistory"] = json::array({1});
        writhing["silverRoot"]["combat"]["monsters"][0]["powers"] = json::array({
            json{{"id", "Malleable"}, {"amount", 3}},
            json{{"id", "Compulsive"}, {"amount", -1}}});
        const auto writhingImported = one_combat::advisor::importSilverRoot(writhing);
        if (!writhingImported.ok || writhingImported.wire.monsters[0].uniquePower1 != 0
            || !(writhingImported.wire.monsters[0].statusBits
                & (1ULL << static_cast<int>(MonsterStatus::REACTIVE))))
            throw std::runtime_error("Writhing Mass Compulsive sentinel lost its active zero counter");
        writhing["silverRoot"]["combat"]["monsters"][0]["powers"][1]["amount"] = -2;
        if (one_combat::advisor::importSilverRoot(writhing).ok)
            throw std::runtime_error("unknown Compulsive sentinel was accepted");
        general["silverRoot"]["combat"]["cardSelect"] = json{
            {"task", "EXHAUST_ONE"}, {"cards", json::array({"Strike_R"})},
            {"pickCount", 1}, {"canPickZero", false}};
        auto selectionImported = one_combat::advisor::importSilverRoot(general, eyeContext);
        if (!selectionImported.ok || selectionImported.wire.inputState
                != static_cast<int>(InputState::CARD_SELECT)
            || selectionImported.wire.cardSelect.task
                != static_cast<std::int16_t>(CardSelectTask::EXHAUST_ONE))
            throw std::runtime_error("schema-v4 card-select contract failed");
        general["silverRoot"]["combat"]["cardSelect"] = json{
            {"task", "DISCOVERY"}, {"cards", json::array({"Intimidate", "Second Wind", "Entrench"})},
            {"pickCount", 1}, {"canPickZero", true}, {"data0", 1}};
        auto potionDiscovery = one_combat::advisor::importSilverRoot(general, eyeContext);
        if (!potionDiscovery.ok || potionDiscovery.wire.cardSelect.task
                != static_cast<std::int16_t>(CardSelectTask::DISCOVERY)
            || !potionDiscovery.wire.cardSelect.canPickZero
            || potionDiscovery.wire.cardSelect.data0 != 1)
            throw std::runtime_error("observed Skill Potion selector did not preserve optional Discovery");
        general["silverRoot"]["combat"]["cardSelect"] = json{
            {"task", "DISCOVERY"}, {"cards", json::array({"The Bomb", "Blind", "Dark Shackles"})},
            {"pickCount", 1}, {"canPickZero", false}, {"data0", 1},
            {"setCostToZero", false}};
        auto toolbox = one_combat::advisor::importSilverRoot(general, eyeContext);
        if (!toolbox.ok || toolbox.wire.cardSelect.task
                != static_cast<std::int16_t>(CardSelectTask::DISCOVERY)
            || toolbox.wire.cardSelect.setCostToZero
            || toolbox.wire.cardSelect.data0 != 1)
            throw std::runtime_error("Toolbox offer lost its normal-cost copy contract");
        general["silverRoot"]["combat"]["cardSelect"] = json{
            {"task", "LIQUID_MEMORIES_POTION"}, {"cards", json::array()},
            {"pickCount", 1}, {"canPickZero", false}};
        auto liquidMemories = one_combat::advisor::importSilverRoot(general, eyeContext);
        if (!liquidMemories.ok || liquidMemories.wire.cardSelect.task
                != static_cast<std::int16_t>(CardSelectTask::LIQUID_MEMORIES_POTION))
            throw std::runtime_error("observed Liquid Memories grid did not reach its supported native task");
        general["silverRoot"]["combat"]["cardSelect"]["task"] = "HOLOGRAM";
        auto unsupportedPortTask = one_combat::advisor::importSilverRoot(general, eyeContext);
        if (unsupportedPortTask.ok || unsupportedPortTask.reason != "silver_selection_task_not_in_port")
            throw std::runtime_error("unavailable Silver port selector was allowed to abort the advisor");
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
        loweringAction.source = silver_bridge::CardSource::HAND;
        loweringAction.cardSelectTask = static_cast<std::int16_t>(CardSelectTask::ARMAMENTS);
        auto handSelectObservation = targetObservation;
        handSelectObservation["combat"]["cardSelect"] = json{
            {"task", "ARMAMENTS"}, {"liveUuids", json::array({"copy-a", "copy-b"})}};
        if (one_combat::advisor::selectedLiveAction(loweringAction, loweringContext,
                handSelectObservation) != json{{"kind", "choose"}, {"choiceIndex", 2}})
            throw std::runtime_error("single hand selection lost its unique live UUID");
        handSelectObservation["combat"]["cardSelect"]["liveUuids"]
            = json::array({"copy-b", "copy-b"});
        if (!one_combat::advisor::selectedLiveAction(loweringAction, loweringContext,
                handSelectObservation).is_null())
            throw std::runtime_error("ambiguous hand UUID was lowered as executable");
        handSelectObservation["combat"]["cardSelect"]["task"] = "WARCRY";
        if (!one_combat::advisor::selectedLiveAction(loweringAction, loweringContext,
                handSelectObservation).is_null())
            throw std::runtime_error("mismatched hand selection task was lowered");
        loweringAction.source = silver_bridge::CardSource::CARD_SELECT_OPTION;
        loweringAction.cardSelectTask = static_cast<std::int16_t>(CardSelectTask::DISCOVERY);
        loweringAction.optionCardId = static_cast<std::int16_t>(CardId::MAGNETISM);
        auto discoveryObservation = targetObservation;
        discoveryObservation["combat"]["cardSelect"] = json{
            {"task", "DISCOVERY"}, {"cards", json::array({"Forethought", "Magnetism", "Discovery"})}};
        const auto discoveryChoice = one_combat::advisor::selectedLiveAction(
            loweringAction, loweringContext, discoveryObservation);
        if (discoveryChoice != json{{"kind", "choose"}, {"choiceIndex", 2}})
            throw std::runtime_error("Discovery option did not lower to its unique visible choice");
        loweringAction.skipCardSelect = true;
        if (!one_combat::advisor::selectedLiveAction(
                loweringAction, loweringContext, discoveryObservation).is_null())
            throw std::runtime_error("mandatory Discovery gained an unsupported skip");
        discoveryObservation["combat"]["cardSelect"]["canPickZero"] = true;
        if (one_combat::advisor::selectedLiveAction(
                loweringAction, loweringContext, discoveryObservation) != json{{"kind", "skip"}})
            throw std::runtime_error("optional potion Discovery skip did not lower to MCP skip");
        loweringAction.skipCardSelect = false;
        discoveryObservation["combat"]["cardSelect"]["cards"][2] = "Magnetism";
        if (!one_combat::advisor::selectedLiveAction(
                loweringAction, loweringContext, discoveryObservation).is_null())
            throw std::runtime_error("ambiguous Discovery option was lowered as executable");
        loweringAction.source = silver_bridge::CardSource::DISCARD;
        loweringAction.cardSelectTask = static_cast<std::int16_t>(CardSelectTask::LIQUID_MEMORIES_POTION);
        loweringAction.card.uniqueId = 23;
        auto liquidObservation = targetObservation;
        liquidObservation["combat"]["cardSelect"] = json{
            {"task", "LIQUID_MEMORIES_POTION"}, {"liveUuids", json::array({"copy-a", "copy-b"})}};
        if (one_combat::advisor::selectedLiveAction(
                loweringAction, loweringContext, liquidObservation)
                != json{{"kind", "choose"}, {"choiceIndex", 2}})
            throw std::runtime_error("duplicate Liquid Memories cards lost physical GRID choice");
        liquidObservation["combat"]["cardSelect"]["liveUuids"][1] = "copy-a";
        if (!one_combat::advisor::selectedLiveAction(
                loweringAction, loweringContext, liquidObservation).is_null())
            throw std::runtime_error("missing Liquid Memories UUID was silently lowered");
        liquidObservation["combat"]["cardSelect"]["liveUuids"][1] = "copy-b";
        for (auto task : {CardSelectTask::HEADBUTT, CardSelectTask::HOLOGRAM,
                          CardSelectTask::MEDITATE}) {
            loweringAction.cardSelectTask = static_cast<std::int16_t>(task);
            liquidObservation["combat"]["cardSelect"]["task"] = std::string(cardSelectTaskStrings[static_cast<int>(task)]);
            if (one_combat::advisor::selectedLiveAction(loweringAction, loweringContext,
                    liquidObservation) != json{{"kind", "choose"}, {"choiceIndex", 2}})
                throw std::runtime_error("discard selector lost unique physical GRID choice");
        }
        loweringAction.source = silver_bridge::CardSource::EXHAUST;
        loweringAction.cardSelectTask = static_cast<std::int16_t>(CardSelectTask::EXHUME);
        liquidObservation["combat"]["cardSelect"]["task"] = "EXHUME";
        if (one_combat::advisor::selectedLiveAction(loweringAction, loweringContext,
                liquidObservation) != json{{"kind", "choose"}, {"choiceIndex", 2}})
            throw std::runtime_error("Exhume lost unique physical GRID choice");
        loweringAction.source = silver_bridge::CardSource::DISCARD;
        if (!one_combat::advisor::selectedLiveAction(loweringAction, loweringContext,
                liquidObservation).is_null())
            throw std::runtime_error("exhaust selector lowered from discard source");
        loweringAction.source = silver_bridge::CardSource::NONE;
        loweringAction.cardSelectTask = 0;
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
        auto sparseObservation = targetObservation;
        sparseObservation["combat"]["monsters"] = json::array({
            json{{"slot", 1}, {"dead", false}},
            json{{"slot", 2}, {"dead", true}},
            json{{"slot", 3}, {"dead", false}}});
        loweringAction.target = 1;
        if (one_combat::advisor::selectedLiveAction(loweringAction, loweringContext,
                sparseObservation).value("targetIndex", 0) != 1)
            throw std::runtime_error("sparse live monster slot 1 did not lower to target 1");
        loweringAction.target = 3;
        if (one_combat::advisor::selectedLiveAction(loweringAction, loweringContext,
                sparseObservation).value("targetIndex", 0) != 2)
            throw std::runtime_error("sparse live monster slot 3 did not compact to target 2");
        loweringAction.target = 2;
        if (!one_combat::advisor::selectedLiveAction(loweringAction, loweringContext,
                sparseObservation).is_null())
            throw std::runtime_error("dead sparse live monster slot was accepted");
        std::cout << "live Silver native first-turn parity checks passed\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "live Silver parity FAIL: " << e.what() << '\n';
        return 1;
    }
}
