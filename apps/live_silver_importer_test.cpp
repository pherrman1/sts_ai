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
        reject["silverRoot"]["combat"]["monsters"][0]["nextMove"] = 2;
        if (one_combat::advisor::importSilverRoot(reject).ok) return 6;
        reject = fixtures[2].observation;
        reject["silverRoot"]["combat"]["monsters"][0]["nextMove"] = 1;
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
        generalRoot["combat"]["playerPowers"] = json::array({
            json{{"id", "Metallicize"}, {"amount", 2}}});
        generalRoot["combat"]["potions"][0] = json{{"slot", 0}, {"id", "Strength Potion"}};
        generalRoot["combat"]["relics"].push_back(
            json{{"id", "Happy Flower"}, {"counter", 2}});
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
        std::cout << "live Silver native first-turn parity checks passed\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "live Silver parity FAIL: " << e.what() << '\n';
        return 1;
    }
}
