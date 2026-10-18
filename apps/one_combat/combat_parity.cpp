#include "combat_parity.h"

#include <map>
#include <optional>
#include <stdexcept>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include "combat/BattleContext.h"
#include "live_silver_importer.h"
#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/SilverSearcher.h"
#include "sim/search/SilverSemanticAction.h"
#include "sim/search/SilverWireJson.h"
#include "sim/search/SilverWireState.h"

namespace one_combat::parity {
namespace {
using J = nlohmann::json;
using namespace sts;

// A step that cannot be compared. The category names why, so coverage gaps
// stay visible in the report instead of disappearing.
struct Skip : std::runtime_error {
    std::string category;
    J detail;
    Skip(std::string c, const std::string &reason, J d = nullptr)
        : std::runtime_error(reason), category(std::move(c)), detail(std::move(d)) {}
};

const J &combatOf(const J &observation) {
    const auto root = observation.find("silverRoot");
    if (root == observation.end() || !root->is_object()) throw Skip("IMPORT_FAILED", "silverRoot missing");
    const auto combat = root->find("combat");
    if (combat == root->end() || !combat->is_object()) throw Skip("IMPORT_FAILED", "combat missing");
    return *combat;
}

std::vector<std::string> pileUuids(const J &pile) {
    std::vector<std::string> out;
    const auto add = [&](const J &array) {
        if (!array.is_array()) return;
        for (const auto &card : array) out.push_back(card.value("uuid", std::string()));
    };
    if (pile.is_array()) add(pile);
    else if (pile.is_object()) {
        for (const char *part : {"knownBottom", "unknown", "knownTop"})
            if (pile.contains(part)) add(pile.at(part));
    }
    return out;
}

std::vector<silver_bridge::CardWire> allCards(const silver_bridge::PileWire &pile) {
    std::vector<silver_bridge::CardWire> out = pile.knownBottom;
    out.insert(out.end(), pile.unknown.begin(), pile.unknown.end());
    out.insert(out.end(), pile.knownTop.begin(), pile.knownTop.end());
    return out;
}

// Reorders a pile the importer stored as a public multiset into the true
// order given by Java UUIDs, bottom to top.
silver_bridge::PileWire orderedPile(const silver_bridge::PileWire &imported,
                                    const std::vector<std::string> &uuids,
                                    const advisor::SilverImportContext &context,
                                    const char *name) {
    std::map<std::int16_t, silver_bridge::CardWire> byId;
    for (const auto &card : allCards(imported)) byId[card.uniqueId] = card;
    if (byId.size() != uuids.size())
        throw Skip("EXACT_ORDER_UNAVAILABLE", std::string(name) + " size differs from its UUID order");
    silver_bridge::PileWire out;
    for (const auto &uuid : uuids) {
        const auto id = context.cardIds.find(uuid);
        if (id == context.cardIds.end() || !byId.count(id->second))
            throw Skip("EXACT_ORDER_UNAVAILABLE", std::string(name) + " UUID not imported");
        out.knownTop.push_back(byId.at(id->second));
    }
    return out;
}

silver_bridge::BattleStateWire exactWire(const J &observation, const J &rng,
                                         advisor::SilverImportContext &context) {
    const auto imported = advisor::importSilverRoot(observation, context);
    if (!imported.ok) throw Skip("IMPORT_FAILED", imported.reason);
    if (imported.wire.intentsHidden)
        throw Skip("EXACT_STATE_UNAVAILABLE", "Runic Dome hides intents");
    if (!rng.is_object() || !rng.value("available", false) || !rng.contains("drawPileUuids"))
        throw Skip("EXACT_STATE_UNAVAILABLE", "no hidden RNG or draw order");
    auto wire = imported.wire;
    const auto &combat = combatOf(observation);
    auto draw = orderedPile(wire.drawPile, rng.at("drawPileUuids").get<std::vector<std::string>>(),
                            context, "draw");
    draw.fullOrderObserved = true;
    wire.drawPile = std::move(draw);
    wire.fullDrawOrderObserved = true;
    // Discard and exhaust order is public in Java; the importer sorts it.
    wire.discardPile.unknown = orderedPile(wire.discardPile, pileUuids(combat.value("discard", J::array())),
                                           context, "discard").knownTop;
    wire.exhaustPile.unknown = orderedPile(wire.exhaustPile, pileUuids(combat.value("exhaust", J::array())),
                                           context, "exhaust").knownTop;
    return wire;
}

void setStream(Random &stream, const J &streams, const char *name) {
    const auto it = streams.find(name);
    if (it == streams.end() || !it->is_object() || !it->value("available", true))
        throw Skip("EXACT_STATE_UNAVAILABLE", std::string("RNG stream missing: ") + name);
    stream.counter = it->at("counter").get<std::int32_t>();
    stream.seed0 = std::stoull(it->at("seed0").get<std::string>());
    stream.seed1 = std::stoull(it->at("seed1").get<std::string>());
}

void setCombatRng(BattleContext &bc, const J &rng) {
    const auto &streams = rng.at("streams");
    setStream(bc.aiRng, streams, "aiRng");
    setStream(bc.cardRandomRng, streams, "cardRandomRng");
    setStream(bc.miscRng, streams, "miscRng");
    setStream(bc.monsterHpRng, streams, "monsterHpRng");
    setStream(bc.potionRng, streams, "potionRng");
    setStream(bc.shuffleRng, streams, "shuffleRng");
}

J streamJson(const Random &r) {
    return {{"counter", r.counter}, {"seed0", std::to_string(r.seed0)}, {"seed1", std::to_string(r.seed1)}};
}

J combatRng(const BattleContext &bc) {
    return {{"aiRng", streamJson(bc.aiRng)}, {"cardRandomRng", streamJson(bc.cardRandomRng)},
            {"miscRng", streamJson(bc.miscRng)}, {"monsterHpRng", streamJson(bc.monsterHpRng)},
            {"potionRng", streamJson(bc.potionRng)}, {"shuffleRng", streamJson(bc.shuffleRng)}};
}

J gameCombatRng(const J &rng) {
    J out = J::object();
    for (const char *name : {"aiRng", "cardRandomRng", "miscRng", "monsterHpRng", "potionRng", "shuffleRng"}) {
        const auto &s = rng.at("streams").at(name);
        out[name] = {{"counter", s.at("counter")}, {"seed0", s.at("seed0")}, {"seed1", s.at("seed1")}};
    }
    return out;
}

// One projection for both sides, so importer conventions cancel out.
J project(const BattleContext &bc, const search::SilverSearchContext &context) {
    return search::wireFromSearchState(bc, context);
}

std::string entryOf(const J &observation) {
    return observation.value("combatEntryHash", observation.value("silverRoot", J::object())
        .value("combatInstance", std::string()));
}

J probeStep(const J &row, advisor::SilverImportContext &context) {
    const auto &pre = row.at("pre");
    const auto session = row.value("session", std::string("parity"));
    context.reset(session, entryOf(pre));
    const auto preWire = exactWire(pre, row.value("preRng", J()), context);
    const auto searchContext = search::searchContextFromWire(preWire);
    BattleContext bc = search::battleContextFromWire(preWire);
    setCombatRng(bc, row.at("preRng"));

    const auto fingerprint = row.value("action", std::string());
    std::optional<silver_bridge::SemanticAction> selected;
    J legal = J::array();
    {
        BattleContext root = bc;
        search::SilverSearcher searcher(root, searchContext);
        searcher.prepareRootActions();
        for (const auto &edge : searcher.rootNode().edges) {
            const auto semantic = search::semanticFromSearchAction(root, edge.action);
            legal.push_back(search::semanticFingerprint(semantic));
            if (search::semanticFingerprint(semantic) != fingerprint) continue;
            if (selected) throw Skip("RECORDED_ACTION_AMBIGUOUS", fingerprint);
            selected = semantic;
        }
    }
    if (!selected) throw Skip("RECORDED_ACTION_NOT_FOUND", fingerprint, legal);
    const auto resolved = search::resolveSilverSemanticAction(bc, *selected);
    if (!resolved.ok) throw Skip("RECORDED_ACTION_NOT_FOUND", resolved.error);
    search::ScumSearchAgent2 agent;
    agent.takeAction(bc, resolved.action);

    J out = {{"step", row.value("step", -1)}, {"status", "COMPARED"},
             {"actionLabel", advisor::silverActionLabel(*selected, preWire)},
             {"encounter", preWire.encounter}, {"turn", preWire.turn},
             {"nativeOutcome", static_cast<int>(bc.outcome)},
             {"native", project(bc, searchContext)}, {"nativeRng", combatRng(bc)}};
    const auto boundary = row.value("postBoundary", std::string());
    if (boundary != "combat") {
        // Combat ended (or the run did). Python compares outcome and HP with
        // the following out-of-combat observation.
        out["status"] = "COMBAT_END";
        return out;
    }
    if (bc.outcome != Outcome::UNDECIDED) {
        out["game"] = nullptr;
        out["mismatch"] = "native combat ended but the game is still in combat";
        return out;
    }
    const auto &post = row.at("post");
    if (entryOf(post) != entryOf(pre)) throw Skip("TRACE_ERROR", "post observation is another combat");
    const auto postWire = exactWire(post, row.value("postRng", J()), context);
    BattleContext game = search::battleContextFromWire(postWire);
    setCombatRng(game, row.at("postRng"));
    out["game"] = project(game, search::searchContextFromWire(postWire));
    out["gameRng"] = gameCombatRng(row.at("postRng"));
    return out;
}
}

int runCombatParityProbe(std::istream &input, std::ostream &output) {
    advisor::SilverImportContext context;
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        J row;
        try { row = J::parse(line); }
        catch (const std::exception &error) {
            output << J{{"status", "SKIPPED"}, {"category", "TRACE_ERROR"}, {"reason", error.what()}}.dump() << '\n';
            continue;
        }
        try {
            output << probeStep(row, context).dump() << '\n';
        } catch (const Skip &skip) {
            J out = {{"step", row.value("step", -1)}, {"status", "SKIPPED"},
                     {"category", skip.category}, {"reason", skip.what()}};
            if (!skip.detail.is_null()) out["legalActions"] = skip.detail;
            output << out.dump() << '\n';
        } catch (const std::exception &error) {
            output << J{{"step", row.value("step", -1)}, {"status", "SKIPPED"},
                        {"category", "NATIVE_ERROR"}, {"reason", error.what()}}.dump() << '\n';
        }
    }
    return 0;
}

}
