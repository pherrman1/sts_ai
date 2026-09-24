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
        "BeatOfDeath", "