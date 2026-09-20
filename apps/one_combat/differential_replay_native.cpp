#include "differential_replay_native.h"

#include <map>
#include <memory>
#include <stdexcept>
#include <string>

#include <nlohmann/json.hpp>

#include "combat/BattleContext.h"
#include "differential_state.h"
#include "ooc_v4_encoding.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/GameAction.h"
#include "sim/search/OocSemanticAction.h"
#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/SilverConversion.h"
#include "sim/search/SilverSemanticAction.h"

namespace one_combat {
namespace {
using J = nlohmann::json;
using namespace sts;

std::string currentOocIdentity(const search::OocSemanticPrimitiveBinding &binding) {
    auto semantic = binding.semantic;
    if (binding.compoundSelector == CardSelectScreenType::INVALID)
        return search::canonicalOocSemanticActionKey(semantic);
    if (const auto *transaction = std::get_if<search::OocTransactionTarget>(&semantic.target)) {
        if (semantic.source == search::OocSemanticSource::SHOP_REMOVE)
            semantic.target = search::OocShopTarget{search::OocNoTarget{}, transaction->expectedGoldCost, 0};
        else semantic.target = search::OocEventTarget{transaction->event, transaction->option};
    } else semantic.target = search::OocNoTarget{};
    return search::canonicalOocSemanticActionKey(semantic) + ":current-screen";
}

struct Replay {
    GameContext game;
    PathHistory path;
    search::ScumSearchAgent2 agent;
    std::unique_ptr<BattleContext> battle;
    search::CombatKnowledgeState knowledge;

    Replay(std::uint64_t seed, int ascension)
        : game(CharacterClass::IRONCLAD, seed, ascension) {}

    ~Replay() {
        if (search::g_combatKnowledgeObserver == &knowledge)
            search::g_combatKnowledgeObserver = nullptr;
    }

    void enterBattle() {
        if (battle) return;
        if (game.screenState != ScreenState::BATTLE)
            throw std::runtime_error("native state is not a combat boundary");
        battle = std::make_unique<BattleContext>();
        knowledge.configureHiddenMonsterIntents(game.relics.has(RelicId::RUNIC_DOME));
        knowledge.beginCombatInitialization();
        search::g_combatKnowledgeObserver = &knowledge;
        battle->init(game);
        knowledge.synchronizeAfterCombatInitialization(*battle);
    }

    silver_bridge::BattleStateWire combatWire() {
        knowledge.reconcilePublicDrawPileCardinality(*battle);
        return search::makeSilverBattleStateWire(
            *battle, knowledge, search::makeSilverRunContext(game), 0);
    }

    J state() {
        if (game.screenState == ScreenState::BATTLE || battle) {
            enterBattle();
            return differential::canonicalCombatState(combatWire());
        }
        path.update(game);
        return differential::canonicalOocState(game, path);
    }

    J rng() const { return differential::gameRng(game, battle.get()); }

    J combatLegal(std::vector<silver_bridge::SemanticAction> *values = nullptr) {
        auto legal = silver_bridge::enumerateSilverLegalActions(combatWire());
        J out = J::array();
        for (const auto &action : legal)
            out.push_back({{"fingerprint", silver_bridge::semanticActionFingerprint(action)}});
        if (values) *values = std::move(legal);
        return out;
    }

    J oocLegal(std::map<std::string, std::uint32_t> *values = nullptr) {
        const auto actions = v4CandidateActions(game);
        std::map<std::uint32_t, std::string> identities;
        if (game.screenState == ScreenState::MAP_SCREEN) {
            for (const auto &action : actions)
                identities[action.bits] = "ooc-live:v1:map:x=" + std::to_string(action.getIdx1())
                    + ":y=" + std::to_string(game.curMapNodeY + 1);
        } else {
            const auto semantic = search::enumerateOocSemanticPrimitiveBindings(game);
            if (!semantic.supported || !semantic.complete)
                throw std::runtime_error("UNSUPPORTED_BOUNDARY: " + semantic.error);
            for (const auto &binding : semantic.bindings) {
                const auto identity = currentOocIdentity(binding);
                const auto [it, inserted] = identities.emplace(binding.primitiveBits, identity);
                if (!inserted && it->second != identity)
                    throw std::runtime_error("UNSUPPORTED_BOUNDARY: ambiguous OOC semantic mapping");
            }
        }
        J out = J::array();
        std::map<std::string, std::uint32_t> resolved;
        for (const auto &action : actions) {
            const auto found = identities.find(action.bits);
            if (found == identities.end())
                throw std::runtime_error("UNSUPPORTED_BOUNDARY: incomplete OOC semantic mapping");
            if (!resolved.emplace(found->second, action.bits).second)
                throw std::runtime_error("UNSUPPORTED_BOUNDARY: duplicate OOC semantic identity");
            out.push_back({{"semanticKey", found->second}});
        }
        if (values) *values = std::move(resolved);
        return out;
    }

    J legal(const std::string &boundary) {
        return boundary == "combat" ? combatLegal() : oocLegal();
    }

    void execute(const std::string &boundary, const std::string &identity) {
        if (boundary == "combat") {
            std::vector<silver_bridge::SemanticAction> actions;
            combatLegal(&actions);
            const auto expected = identity.rfind("silver:", 0) == 0 ? identity.substr(7) : identity;
            const silver_bridge::SemanticAction *selected = nullptr;
            for (const auto &action : actions) {
                if (silver_bridge::semanticActionFingerprint(action) != expected) continue;
                if (selected) throw std::runtime_error("RECORDED_ACTION_AMBIGUOUS");
                selected = &action;
            }
            if (!selected) throw std::runtime_error("RECORDED_ACTION_NOT_FOUND");
            const auto resolved = search::resolveSilverSemanticAction(*battle, *selected);
            if (!resolved.ok) throw std::runtime_error("RECORDED_ACTION_NOT_FOUND: " + resolved.error);
            agent.takeAction(*battle, resolved.action);
            if (battle->outcome != Outcome::UNDECIDED) {
                search::g_combatKnowledgeObserver = nullptr;
                battle->exitBattle(game);
                battle.reset();
            }
            return;
        }
        std::map<std::string, std::uint32_t> actions;
        oocLegal(&actions);
        const auto found = actions.find(identity);
        if (found == actions.end()) throw std::runtime_error("RECORDED_ACTION_NOT_FOUND");
        search::GameAction(found->second).execute(game);
    }
};

std::uint64_t seedFrom(const J &header, const J &decision) {
    J value = decision.value("seed", J());
    if (value.is_null() && header.contains("provenance")) value = header["provenance"].value("seed", J());
    if (value.is_number_unsigned()) return value.get<std::uint64_t>();
    if (value.is_number_integer()) return static_cast<std::uint64_t>(value.get<std::int64_t>());
    if (value.is_string()) return std::stoull(value.get<std::string>());
    throw std::runtime_error("trace has no numeric seed");
}
}

int runDifferentialReplayNative(std::istream &input, std::ostream &output) {
    J header;
    std::unique_ptr<Replay> replay;
    std::string line;
    while (std::getline(input, line)) {
        if (line.empty()) continue;
        const J row = J::parse(line);
        if (row.value("record_type", std::string()) == "header") { header = row; continue; }
        if (row.value("record_type", std::string()) != "decision") continue;
        if (row.contains("traceError")) break;
        J native = J::object();
        try {
            if (!replay) {
                const int ascension = header.value("provenance", J::object()).value("ascension", 0);
                replay = std::make_unique<Replay>(seedFrom(header, row), ascension);
            }
            const auto boundary = row.at("boundary").get<std::string>();
            native = {{"state", replay->state()}, {"rng", replay->rng()},
                      {"legalActions", replay->legal(boundary)}};
            replay->execute(boundary, row.at("selectedAction").at("identity").get<std::string>());
            native["after"] = replay->state();
            native["postRng"] = replay->rng();
            output << native.dump() << '\n';
        } catch (const std::exception &error) {
            const std::string reason = error.what();
            std::string category = "UNSUPPORTED_BOUNDARY";
            if (reason.rfind("RECORDED_ACTION_NOT_FOUND", 0) == 0)
                category = "RECORDED_ACTION_NOT_FOUND";
            else if (reason.rfind("RECORDED_ACTION_AMBIGUOUS", 0) == 0)
                category = "RECORDED_ACTION_AMBIGUOUS";
            else if (reason.rfind("TRACE_OR_SCHEMA_ERROR", 0) == 0)
                category = "TRACE_OR_SCHEMA_ERROR";
            native["traceError"] = {{"category", category}, {"reason", reason}};
            output << native.dump() << '\n';
            break;
        }
    }
    return 0;
}
}
