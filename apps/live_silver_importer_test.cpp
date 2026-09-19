#include "one_combat/live_silver_importer.h"

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
                        {"block", m.block}, {"nextMove", move}, {"powers", json::array()}});
    json potions = json::array();
    for (int i = 0; i < w.potionCapacity; ++i)
        potions.push_back({{"slot", i}, {"id", "Potion Slot"}});
    json combat = {
        {"turn", 1}, {"energy", w.player.energy}, {"block", w.player.block},
        {"cardsPlayedThisTurn", w.player.cardsPlayedThisTurn}, {"cardSelect", false},
        {"resolving", false}, {"runicDome", false}, {"frozenEye", false},
        {"playedThisTurn", std::move(played)}, {"playerPowers", json::array()},
        {"hand", pileJson(w.hand)}, {"draw", pileJson(w.drawPile.unknown)},
        {"discard", pileJson(w.discardPile.unknown)}, {"exhaust", pileJson(w.exhaustPile.unknown)},
        {"relics", json::array({json{{"id", "Burning Blood"}, {"counter", 0}}})},
        {"potions", std::move(potions)}, {"monsters", std::move(monsters)}};
    return {{"boundary", "combat"}, {"character", "IRONCLAD"},
        {"observationHash", std::string("parity-") + name},
        {"combatEntryHash", std::string("entry-") + name},
        {"silverRoot", {{"schemaVersion", 2}, {"decisionOrdinal", ordinal}, {"firstDecision", ordinal == 0},
            {"character", "IRONCLAD"}, {"ascension", w.ascension}, {"act", w.act},
            {"floor", w.floorNum}, {"hp", w.player.curHp}, {"maxHp", w.player.maxHp},
            {"gold", w.player.gold}, {"potionCapacity", w.potionCapacity},
            {"burningElite", false}, {"roomClass", room}, {"combat", std::move(combat)}}}};
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

Fixture successorFixture(const Fixture &root, const char *cardId) {
    GameContext game(CharacterClass::IRONCLAD, root.wire.isolatedSearchSeed, 0);
    game.act = 1; game.floorNum = 1;
    BattleContext live;
    live.init(game, root.wire.encounter == static_cast<int>(MonsterEncounter::CULTIST)
        ? MonsterEncounter::CULTIST : root.wire.encounter == static_cast<int>(MonsterEncounter::JAW_WORM)
            ? MonsterEncounter::JAW_WORM : MonsterEncounter::GREMLIN_NOB);
    live.monsters.arr[0].moveHistory[0] = static_cast<MMID>(
        root.wire.monsters[0].moveHistory[0]);
    CombatKnowledgeState knowledge;
    knowledge.initializeFromLiveBattle(live);
    const CardId wanted = std::string(cardId) == "Strike_R" ? CardId::STRIKE_RED : CardId::DEFEND_RED;
    int handIndex = -1;
    for (int i = 0; i < live.cards.cardsInHand; ++i)
        if (live.cards.hand[i].id == wanted) { handIndex = i; break; }
    if (handIndex < 0) throw std::runtime_error("successor card not in native hand");
    sts::search::Action(sts::search::ActionType::CARD, handIndex, 0).execute(live);
    auto wire = makeSilverBattleStateWire(live, knowledge, makeSilverRunContext(game),
                                           root.wire.isolatedSearchSeed);
    if (!wire.valid) throw std::runtime_error("native successor conversion failed");
    const auto playedUuid = std::string("card-") + std::to_string(live.curCardQueueItem.card.uniqueId);
    return {cardId, root.move, root.room, wire,
            observation(wire, root.name, root.move, root.room, 1,
                        json::array({{{"id", cardId}, {"uuid", playedUuid}, {"upgraded", false}}}))};
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
}
int main() {
    try {
        const std::vector<Fixture> fixtures = {
            fixture(MonsterEncounter::CULTIST, "Cultist", 3, "MONSTER", 0xC011u),
            fixture(MonsterEncounter::JAW_WORM, "JawWorm", 1, "MONSTER", 0xA01u),
            fixture(MonsterEncounter::GREMLIN_NOB, "Gremlin Nob", 3, "ELITE", 0xB003u)};
        SilverSearchConfig config;
        config.simulationsPerDecision = 1000;
        config.collectRootActionSummaries = true;
        config.collectDecisionDiagnostics = true;
        config.adaptiveEnabled = false;
        config.exactVisitLockEnabled = false;
        config.rhoRacingEnabled = false;
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
        }
        for (const auto &root : fixtures) {
            for (const auto *card : {"Strike_R", "Defend_R"}) {
                const auto successor = successorFixture(root, card);
                auto imported = one_combat::advisor::importSilverRoot(successor.observation);
                if (!imported.ok) throw std::runtime_error(std::string("successor import failed: ") + card + ":" + imported.reason);
                auto canonical = successor.wire;
                canonical.isolatedSearchSeed = imported.wire.isolatedSearchSeed;
                if (!convertedStatesEqualForSearch(canonical, imported.wire))
                    throw std::runtime_error(std::string("successor parity failed: ") + root.name + ":" + card
                        + " energy=" + std::to_string(canonical.player.energy) + "/" + std::to_string(imported.wire.player.energy)
                        + " block=" + std::to_string(canonical.player.block) + "/" + std::to_string(imported.wire.player.block)
                        + " hp=" + std::to_string(canonical.monsters[0].curHp) + "/" + std::to_string(imported.wire.monsters[0].curHp)
                        + " loop=" + std::to_string(canonical.loopCount) + "/" + std::to_string(imported.wire.loopCount)
                        + " q=" + std::to_string(canonical.curCardQueueItem.card.id) + "/" + std::to_string(imported.wire.curCardQueueItem.card.id)
                        + " cards=" + std::to_string(canonical.player.cardsPlayedThisTurn) + "/" + std::to_string(imported.wire.player.cardsPlayedThisTurn)
                        + " atk=" + std::to_string(canonical.player.attacksPlayedThisTurn) + "/" + std::to_string(imported.wire.player.attacksPlayedThisTurn)
                        + " skill=" + std::to_string(canonical.player.skillsPlayedThisTurn) + "/" + std::to_string(imported.wire.player.skillsPlayedThisTurn)
                        + " last=" + std::to_string(canonical.player.lastTargetedMonster) + "/" + std::to_string(imported.wire.player.lastTargetedMonster)
                        + " dmg=" + std::to_string(canonical.player.lastAttackUnblockedDamage) + "/" + std::to_string(imported.wire.player.lastAttackUnblockedDamage)
                        + " misc=" + std::to_string(canonical.miscBits) + "/" + std::to_string(imported.wire.miscBits)
                        + " qtarget=" + std::to_string(canonical.curCardQueueItem.target) + "/" + std::to_string(imported.wire.curCardQueueItem.target));
                if (imported.wire.curCardQueueItem.card.uniqueId < 0)
                    throw std::runtime_error(std::string("successor card movement failed: ") + card);
                if (imported.wire.curCardQueueItem.card.uniqueId != successor.wire.curCardQueueItem.card.uniqueId)
                    throw std::runtime_error(std::string("card identity changed across hand/discard: ") + card);
            }
        }
        auto unsupported = successorFixture(fixtures[0], "Defend_R").observation;
        unsupported["silverRoot"]["combat"]["playedThisTurn"][0]["id"] = "Bash";
        if (one_combat::advisor::importSilverRoot(unsupported).reason != "silver_unsupported_continuation")
            throw std::runtime_error("Bash continuation was not rejected");
        unsupported = successorFixture(fixtures[0], "Defend_R").observation;
        unsupported["silverRoot"]["combat"]["playerPowers"] = json::array({json{{"id", "Metallicize"}}});
        if (one_combat::advisor::importSilverRoot(unsupported).reason != "silver_unmapped_player_power")
            throw std::runtime_error("player power was not rejected");
        const auto seed0 = one_combat::advisor::importSilverRoot(fixtures[0].observation).wire.isolatedSearchSeed;
        const auto seed1 = one_combat::advisor::importSilverRoot(
            successorFixture(fixtures[0], "Defend_R").observation).wire.isolatedSearchSeed;
        const auto seedOtherCombat = one_combat::advisor::importSilverRoot(fixtures[1].observation).wire.isolatedSearchSeed;
        if (seed0 != seed1 || seed0 == seedOtherCombat)
            throw std::runtime_error("Silver seed is not stable per combat");
        auto session = silver_bridge::makeSilverSearchSession();
        const auto rootForSession = one_combat::advisor::importSilverRoot(fixtures[0].observation);
        const auto nextForSession = one_combat::advisor::importSilverRoot(
            successorFixture(fixtures[0], "Defend_R").observation);
        const auto firstDecision = silver_bridge::runSilverDecision(*session, rootForSession.wire, config);
        const auto secondDecision = silver_bridge::runSilverDecision(*session, nextForSession.wire, config);
        if (!firstDecision.accepted || !secondDecision.accepted)
            throw std::runtime_error("persistent Silver session rejected continuation");
        if (secondDecision.diagnostic.exactReroot) {
            if (secondDecision.diagnostic.inheritedVisits <= 0)
                throw std::runtime_error("exact Silver reroot did not retain visits");
        } else if (secondDecision.diagnostic.fallbackReason
                   != SilverRerootFallbackReason::CANDIDATE_MISSING) {
            throw std::runtime_error("unexpected Silver continuation fallback");
        }
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
        reject["silverRoot"]["combat"]["monsters"][0]["nextMove"] = 2;
        if (one_combat::advisor::importSilverRoot(reject).ok) return 6;
        reject = fixtures[2].observation;
        reject["silverRoot"]["combat"]["monsters"][0]["nextMove"] = 1;
        if (one_combat::advisor::importSilverRoot(reject).ok) return 7;
        reject = fixtures[0].observation;
        reject["silverRoot"]["combat"]["turn"] = 2;
        if (one_combat::advisor::importSilverRoot(reject).ok) return 8;
        std::cout << "live Silver native first-turn parity checks passed\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "live Silver parity FAIL: " << e.what() << '\n';
        return 1;
    }
}
