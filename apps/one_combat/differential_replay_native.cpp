#include "differential_replay_native.h"

#include <map>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>

#include <nlohmann/json.hpp>

#include "combat/BattleContext.h"
#include "differential_state.h"
#include "ooc_v4_encoding.h"
#include "live_ooc_action_identity.h"
#include "sim/search/CombatKnowledge.h"
#include "sim/search/GameAction.h"
#include "sim/search/OocSemanticAction.h"
#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/SilverConversion.h"
#include "sim/search/SilverSemanticAction.h"
#include "sim/search/SilverWireState.h"

namespace one_combat {
namespace {
using J = nlohmann::json;
using namespace sts;

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
        const auto wire = combatWire();
        auto root = search::battleContextFromWire(wire);
        search::SilverSearcher searcher(root, search::searchContextFromWire(wire));
        searcher.prepareRootActions();
        std::vector<silver_bridge::SemanticAction> legal;
        for (const auto &edge : searcher.rootNode().edges)
            legal.push_back(search::semanticFromSearchAction(root, edge.action));
        J out = J::array();
        for (const auto &action : legal)
            out.push_back({{"fingerprint", search::semanticFingerprint(action)}});
        if (values) *values = std::move(legal);
        return out;
    }

    J oocLegal(const std::string &policy, const std::string &selectionMode,
               std::map<std::string, std::uint32_t> *values = nullptr) {
        const bool retainedTarget = selectionMode == "retained_compound_target";
        if (retainedTarget && game.screenState != ScreenState::CARD_SELECT)
            throw std::runtime_error("UNSUPPORTED_BOUNDARY: retained compound target requires card selection");
        J out = J::array();
        std::map<std::string, std::uint32_t> resolved;
        const auto add = [&](const std::string &key, std::uint32_t bits) {
            if (!resolved.emplace(key, bits).second)
                throw std::runtime_error("UNSUPPORTED_BOUNDARY: duplicate OOC semantic identity");
            out.push_back({{"semanticKey", key}});
        };
        if (game.screenState == ScreenState::MAP_SCREEN) {
            if (!v4DecisionSupported(game))
                throw std::runtime_error("UNSUPPORTED_BOUNDARY: unsupported map decision");
            for (const auto &action : v4CandidateActions(game))
                add("ooc-live:v1:map:x=" + std::to_string(action.getIdx1())
                    + ":y=" + std::to_string(game.curMapNodeY + 1), action.bits);
        } else {
            const auto semantic = search::enumerateOocSemanticPrimitiveBindings(game);
            if (!semantic.supported || !semantic.complete)
                throw std::runtime_error("UNSUPPORTED_BOUNDARY: " + semantic.error);
            if (retainedTarget) {
                // retainedCompoundDecision exposes every physical selector
                // binding, including equivalent deck copies, for either policy.
                for (const auto &binding : semantic.bindings)
                    add(search::canonicalOocSemanticActionKey(binding.semantic), binding.primitiveBits);
            } else if (policy == "mcts_ctm") {
                // Match OocGameContextModel: distinct compound targets remain
                // separate candidates even when they share a source primitive;
                // equivalent copies of a deck card share one MCTS choice.
                std::set<std::string> choices;
                for (const auto &binding : semantic.bindings) {
                    if (!search::GameAction(binding.primitiveBits).isValidAction(game)) continue;
                    if (!choices.insert(search::canonicalOocMctsChoiceKey(binding.semantic)).second)
                        continue;
                    add(search::canonicalOocSemanticActionKey(binding.semantic), binding.primitiveBits);
                }
            } else {
                if (!v4DecisionSupported(game))
                    throw std::runtime_error("UNSUPPORTED_BOUNDARY: unsupported V4 decision");
                std::map<std::uint32_t, std::string> identities;
                for (const auto &binding : semantic.bindings) {
                    const auto identity = currentLiveOocIdentity(binding).first;
                    const auto [it, inserted] = identities.emplace(binding.primitiveBits, identity);
                    // V4 scores one source primitive and retains the canonical
                    // first compound target, just as scoreLiveOocV4 does.
                    if (!inserted && (binding.compoundSelector == CardSelectScreenType::INVALID
                            || it->second.find(":current-screen") == std::string::npos))
                        throw std::runtime_error("UNSUPPORTED_BOUNDARY: ambiguous OOC semantic mapping");
                }
                for (const auto &action : v4CandidateActions(game)) {
                    const auto found = identities.find(action.bits);
                    if (!action.isValidAction(game) || found == identities.end())
                        throw std::runtime_error("UNSUPPORTED_BOUNDARY: incomplete OOC semantic mapping");
                    add(found->second, action.bits);
                }
            }
        }
        if (values) *values = std::move(resolved);
        return out;
    }

    J legal(const std::string &boundary, const std::string &oocPolicy,
            const std::string &selectionMode) {
        return boundary == "combat" ? combatLegal() : oocLegal(oocPolicy, selectionMode);
    }

    void execute(const std::string &boundary, const std::string &identity,
                 const std::string &oocPolicy, const std::string &selectionMode) {
        if (boundary == "combat") {
            std::vector<silver_bridge::SemanticAction> actions;
            combatLegal(&actions);
            const auto expected = identity.rfind("silver:", 0) == 0 ? identity.substr(7) : identity;
            const silver_bridge::SemanticAction *selected = nullptr;
            for (const auto &action : actions) {
                if (search::semanticFingerprint(action) != expected) continue;
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
        oocLegal(oocPolicy, selectionMode, &actions);
        const auto found = actions.find(identity);
        if (found == actions.end()) throw std::runtime_error("RECORDED_ACTION_NOT_FOUND");
        // Replay only the source click. The recorded selector is a separate
        // decision, even when the MCTS identity describes a full transaction.
        search::GameAction(found->second).execute(game);
    }
};

std::string oocPolicyFrom(const J &header, const J &decision) {
    const auto readPolicy = [](const J &object) -> std::string {
        if (!object.contains("oocPolicy")) return {};
        const auto &value = object.at("oocPolicy");
        if (!value.is_string() || (value != "mcts_ctm" && value != "v4_q"))
            throw std::runtime_error("TRACE_OR_SCHEMA_ERROR: invalid OOC policy");
        return value.get<std::string>();
    };
    const auto headerPolicy = readPolicy(header.value("provenance", J::object()));
    const auto decisionPolicy = readPolicy(decision);
    if (!headerPolicy.empty() && !decisionPolicy.empty() && headerPolicy != decisionPolicy)
        throw std::runtime_error("TRACE_OR_SCHEMA_ERROR: OOC policy disagrees with header");
    const auto policy = decisionPolicy.empty() ? headerPolicy : decisionPolicy;
    if (policy.empty())
        throw std::runtime_error("TRACE_OR_SCHEMA_ERROR: missing OOC policy");
    return policy;
}

std::string oocSelectionModeFrom(const J &decision) {
    if (!decision.contains("oocSelectionMode")) return "policy";
    const auto &mode = decision.at("oocSelectionMode");
    if (!mode.is_string() || (mode != "policy" && mode != "retained_compound_target"))
        throw std::runtime_error("TRACE_OR_SCHEMA_ERROR: invalid OOC selection mode");
    return mode.get<std::string>();
}

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
            const auto oocPolicy = boundary == "combat" ? std::string() : oocPolicyFrom(header, row);
            const auto selectionMode = oocSelectionModeFrom(row);
            if (boundary == "combat" && selectionMode != "policy")
                throw std::runtime_error("TRACE_OR_SCHEMA_ERROR: retained compound target requires OOC selection");
            native = {{"state", replay->state()}, {"rng", replay->rng()},
                      {"legalActions", replay->legal(boundary, oocPolicy, selectionMode)}};
            replay->execute(boundary, row.at("selectedAction").at("identity").get<std::string>(),
                            oocPolicy, selectionMode);
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
