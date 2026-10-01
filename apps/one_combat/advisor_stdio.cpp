#include "sim/search/MatchAndKeepPolicy.h"
#include "advisor_protocol.h"
#include "live_ooc_importer.h"
#include "live_ooc_state.h"
#include "live_ooc_policy.h"
#include "differential_state.h"
#include "ooc_v4_encoding.h"
#include "../ooc_strategic_tok_net.h"
#include <fstream>
#include <iomanip>
#include <sstream>
#include "combat_transition_runtime.h"
#include "live_silver_importer.h"
#include "native_silver_advisor.h"
#include "sim/search/SilverBridge.h"
#include "sim/search/SilverWireJson.h"
#include "sim/search/SilverWireState.h"

#include <iostream>
#include <algorithm>
#include <cerrno>
#include <cmath>
#include <cstdlib>
#include <filesystem>
#include <string>
#include <chrono>
#include <memory>
#include <vector>

using nlohmann::json;

namespace {
// Content fingerprint is diagnostic identity, not an artifact trust decision.
std::string modelIdentity(const std::string &path) {
    std::ifstream stream(path, std::ios::binary);
    std::uint64_t hash = 14695981039346656037ULL;
    char byte;
    while (stream.get(byte)) { hash ^= static_cast<unsigned char>(byte); hash *= 1099511628211ULL; }
    if (!stream.eof()) return "unavailable";
    std::ostringstream out; out << "fnv1a64:" << std::hex << std::setw(16) << std::setfill('0') << hash;
    return out.str();
}
std::uint64_t stableHash(const std::string &value) {
    std::uint64_t hash = 14695981039346656037ULL;
    for (const unsigned char byte : value) { hash ^= byte; hash *= 1099511628211ULL; }
    return hash;
}

struct PendingCompoundPlan {
    bool active = false;
    std::string session;
    std::int64_t sequence = 0;
    int selectorType = 0;
    std::string selectorName;
    json card;
};

int keyInteger(const std::string &key, const char *field) {
    const std::string prefix = std::string(field) + "=";
    const auto start = key.find(prefix);
    if (start == std::string::npos) return -1;
    const auto valueStart = start + prefix.size();
    const auto end = key.find(':', valueStart);
    try { return std::stoi(key.substr(valueStart, end - valueStart)); }
    catch (...) { return -1; }
}

PendingCompoundPlan pendingCompoundPlan(const one_combat::advisor::Request &request,
                                        const json &selected) {
    PendingCompoundPlan plan;
    const auto targetType = selected.value("type", std::string());
    if (targetType != "transaction" && targetType != "deck_card"
            && !selected.contains("compoundTarget")) return plan;
    const auto source = keyInteger(selected.value("semanticKey", std::string()), "source");
    const auto effect = keyInteger(selected.value("semanticKey", std::string()), "effect");
    // These are the only public source primitives whose semantic enumeration
    // expands to a deterministic single-card selector. The numeric selector
    // IDs are the append-only native CardSelectScreenType wire values.
    if (source == 0) { plan.selectorType = 3; plan.selectorName = "upgrade"; }
    else if (source == 2 || source == 4) { plan.selectorType = 4; plan.selectorName = "remove"; }
    else if (source == 5 && effect == 0) { plan.selectorType = 3; plan.selectorName = "upgrade"; }
    else if (source == 5 && effect == 1) { plan.selectorType = 4; plan.selectorName = "remove"; }
    else if (source == 5 && effect == 2) { plan.selectorType = 1; plan.selectorName = "transform"; }
    else if (source == 5 && effect == 3) { plan.selectorType = 2; plan.selectorName = "transform_upgrade"; }
    else return plan;
    const auto &target = selected.contains("compoundTarget")
        ? selected.at("compoundTarget") : selected.at("card");
    if (!target.is_object()) return PendingCompoundPlan{};
    plan.active = true;
    plan.session = request.session;
    plan.sequence = request.sequence;
    plan.card = target;
    return plan;
}

bool sameCardTarget(const json &candidate, int selectorType, const json &target) {
    if (candidate.value("type", std::string()) != "selector") return false;
    if (candidate.value("selectorType", -1) != selectorType) return false;
    const auto &candidateTarget = candidate.value("target", json::object());
    if (candidateTarget.value("type", std::string()) != "deck_card") return false;
    const auto &card = candidateTarget.value("card", json::object());
    for (const char *field : {"id", "misc", "upgraded", "bottle", "occurrence"})
        if (!card.contains(field) || !target.contains(field) || card.at(field) != target.at(field)) return false;
    return true;
}

one_combat::LiveOocDecision retainedCompoundDecision(
        const one_combat::advisor::LiveOocStateV1 &state,
        const PendingCompoundPlan &pending) {
    one_combat::LiveOocDecision result;
    result.policy = "mcts_ctm";
    const auto bindings = sts::search::enumerateOocSemanticPrimitiveBindings(state.projected);
    if (!bindings.supported || !bindings.complete) {
        result.reason = "SEMANTIC_ENUMERATION_UNSUPPORTED:" + bindings.error;
        return result;
    }
    const double prior = bindings.bindings.empty()
        ? 0.0 : 1.0 / static_cast<double>(bindings.bindings.size());
    int matches = 0;
    for (const auto &binding : bindings.bindings) {
        const auto payload = json::parse(sts::search::oocSemanticActionPayloadJson(binding.semantic));
        result.candidates.push_back({
            sts::search::canonicalOocSemanticActionKey(binding.semantic), payload.dump(),
            binding.primitiveBits, 0.0, 0, 0.0, prior});
        if (sameCardTarget(payload, pending.selectorType, pending.card)) {
            ++matches;
            result.selectedIndex = static_cast<int>(result.candidates.size()) - 1;
        }
    }
    if (matches != 1) {
        result.candidates.clear();
        result.selectedIndex = -1;
        result.reason = "COMPOUND_TARGET_UNAVAILABLE:" + pending.selectorName;
        return result;
    }
    // This is the retained source transaction's target, not a new selector
    // search. Give the client a coherent one-candidate visit distribution so
    // the selected target and the reported MCTS statistics cannot disagree.
    auto &selected = result.candidates.at(result.selectedIndex);
    selected.visits = 1;
    selected.visitShare = 1.0;
    result.supported = true;
    return result;
}

void validateCapturedLiveOocMapping(const one_combat::advisor::LiveOocStateV1 &state) {
    std::vector<std::uint32_t> expected;
    // Rewards can contain simulator-only synthetic card-skip primitives for
    // groups that Java does not expose as live choices. For those screens the
    // observed primitive set is the source boundary; other screens have an
    // exact native candidate set that can detect missing mappings as well as
    // duplicate ones before policy/model fallback.
    if (state.projected.screenState == sts::ScreenState::REWARDS) {
        expected = one_combat::advisor::liveOocPrimitiveBits(state);
    } else {
        for (const auto &action : one_combat::v4CandidateActions(state.projected))
            if (action.isValidAction(state.projected)) expected.push_back(action.bits);
    }
    if (expected.empty()) return;
    one_combat::advisor::validateLiveOocActionSet(state, expected);
}

std::size_t oocTreeNodeCap() {
    const char *value = std::getenv("STS_OOC_DEBUG_TREE_NODE_CAP");
    if (!value || !*value) return 4096;
    for (const char *p = value; *p; ++p) if (*p < '0' || *p > '9') return 4096;
    char *end = nullptr;
    errno = 0;
    const auto parsed = std::strtoull(value, &end, 10);
    if (errno == ERANGE || end == value || *end || !parsed) return 4096;
    return static_cast<std::size_t>(std::min<unsigned long long>(parsed, 100000));
}

json oocResponse(const one_combat::advisor::Request &request,
                 one_combat::LiveOocPolicy &policy, const std::string &identity,
                 PendingCompoundPlan &pending) {
    using namespace one_combat;
    const auto started = std::chrono::steady_clock::now();
    json evaluator = {{"id", "live_ooc_decision_v1"}, {"scope", "ooc_decision"},
                      {"policy", policy.name()}, {"status", "UNSUPPORTED"}};
    advisor::LiveOocStateV1 state;
    const auto imported = advisor::importLiveOocStateV1(request.observation, state);
    if (!imported.ok && imported.code != "UNSUPPORTED")
        return advisor::errorResponse(request, imported.code, imported.message);
    evaluator["questionChanceBelief"] = {{"qualified",state.mctsRoot.questionHistoryComplete},
            {"kind",!state.mctsRoot.questionHistoryComplete?"unqualified":
                state.mctsRoot.questionChancePosterior.size()>1?"finite_posterior":"point"},
            {"prior","fair_uniform_24_bit_room_roll"},
            {"monsterChanceStates",state.mctsRoot.questionChancePosterior}};

    if (!imported.ok) evaluator["reason"] = imported.message;
    else if (std::string(policy.name()) != "mcts_ctm"
             && std::any_of(state.ooc.at("liveChoices").begin(),state.ooc.at("liveChoices").end(),
                 [](const json &choice) { return choice.at("nativeAction").value("kind",std::string())=="discard_potion"; }))
        evaluator["reason"] = "POTION_REPLACEMENT_REQUIRES_MCTS";
    else if (state.hiddenTreasureContents && std::string(policy.name()) != "mcts_ctm")
        evaluator["reason"] = "PUBLIC_TREASURE_CONTENTS_UNQUALIFIED";
    else if (state.hiddenEventState && std::string(policy.name()) != "mcts_ctm")
        evaluator["reason"] = "PUBLIC_EVENT_STATE_UNQUALIFIED";
    else if (state.mctsRoot.questionChancePosterior.size()>1 && std::string(policy.name())!="mcts_ctm")
        evaluator["reason"] = "PUBLIC_QUESTION_CHANCE_POSTERIOR_REQUIRES_MCTS";
    else if (const char *flag = std::getenv("STS_DIFFERENTIAL_TRACE");
             state.mctsRoot.questionChancePosterior.size()>1 && flag && std::string(flag)=="1")
        evaluator["reason"] = "DIFFERENTIAL_QUESTION_CHANCE_POSTERIOR_UNREPRESENTABLE";
    else if (const char *flag = std::getenv("STS_DIFFERENTIAL_TRACE");
             state.hiddenEventState && flag && std::string(flag) == "1")
        evaluator["reason"] = "DIFFERENTIAL_HIDDEN_EVENT_UNREPRESENTABLE";
    else if (const char *flag = std::getenv("STS_DIFFERENTIAL_TRACE");
             state.hiddenTreasureContents && flag && std::string(flag) == "1")
        evaluator["reason"] = "DIFFERENTIAL_HIDDEN_TREASURE_UNREPRESENTABLE";
    else if (const char *flag = std::getenv("STS_DIFFERENTIAL_TRACE");
             state.hiddenEventRewardPity && flag && std::string(flag) == "1")
        evaluator["reason"] = "DIFFERENTIAL_HIDDEN_REWARD_PITY_UNREPRESENTABLE";
    else {
        if (state.selectorPreview) {
            pending=PendingCompoundPlan{};
            try {
                if(const char *flag=std::getenv("STS_DIFFERENTIAL_TRACE");flag && std::string(flag)=="1")
                    throw std::runtime_error("DIFFERENTIAL_SELECTOR_PREVIEW_UNREPRESENTABLE");
                if(std::string(policy.name())=="mcts_ctm" && !state.mctsRoot.supported)
                    throw std::runtime_error(state.mctsRoot.reason);
                std::vector<std::uint32_t> targets;
                for(const auto &action:v4CandidateActions(state.mctsRoot.state)) targets.push_back(action.bits);
                policy.setRootPrimitiveBits(targets);
                policy.setRewardPityHistoryComplete(state.rewardPityHistoryComplete);
                policy.setQuestionHistoryComplete(state.mctsRoot.questionHistoryComplete);
                policy.setQuestionChancePosterior(state.mctsRoot.questionChancePosterior);
                policy.setMapHistoryComplete(state.mctsRoot.mapHistoryComplete);
                policy.setSearchSeed(stableHash(differential::canonicalOocState(
                    state.mctsRoot.state,state.mctsRoot.path).dump()+":selector"));
                policy.setTreeCapture(false,0);
                const auto decision=policy.score(state.mctsRoot.state,state.mctsRoot.path,state.mctsRoot.currentActEventVisits);
                if(!decision.supported || decision.selectedIndex<0
                        || decision.selectedIndex>=static_cast<int>(decision.candidates.size()))
                    throw std::runtime_error(decision.reason.empty()?"SELECTOR_PREVIEW_VALUE_UNAVAILABLE":decision.reason);
                const auto &candidate=decision.candidates[decision.selectedIndex];
                const auto index=sts::search::GameAction(candidate.primitiveBits).getIdx1();
                if(index<0 || index>=static_cast<int>(state.mctsRoot.state.info.toSelectCards.size()))
                    throw std::runtime_error("SELECTOR_PREVIEW_TARGET_UNREPRESENTABLE");
                const bool confirm=state.mctsRoot.state.info.toSelectCards[index].deckIdx==state.selectorPreviewDeckIndex;
                const auto action=state.ooc.at("liveChoices").at(confirm?0:1).at("liveAction");
                const std::string key=confirm?"ooc-live:v1:preview:confirm":"ooc-live:v1:preview:cancel";
                evaluator["status"]="OK";
                evaluator["mode"]="selector_preview_policy";
                evaluator["valueSemantics"]="native_selector_value";
                evaluator["selectedSemanticKey"]=key;
                evaluator["selectedLabel"]=confirm?"Confirm selected card":"Return to card selection";
                evaluator["selectedLiveAction"]=action;
                evaluator["candidateSummaries"]=json::array({json{
                    {"semanticKey",key},{"semanticPayload",{{"type","selector_preview"},{"confirm",confirm}}},
                    {"label",evaluator["selectedLabel"]},{"q",candidate.q},{"visits",candidate.visits},
                    {"visitShare",1.0},{"prior",1.0},{"liveAction",action}}});
            } catch(const std::exception &error) {evaluator["reason"]=error.what();}
            policy.setRootPrimitiveBits(advisor::liveOocPrimitiveBits(state));
            evaluator["latencyMicros"]=std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now()-started).count();
            return {{"protocol",advisor::kProtocol},{"protocolVersion",advisor::kProtocolVersion},
                {"kind","analysis"},{"status",evaluator.at("status")},{"session",request.session},
                {"sequence",request.sequence},{"observationHash",request.observationHash},
                {"evaluators",json::array({evaluator})}};
        }
        if (state.matchAndKeep) {
            pending=PendingCompoundPlan{};
            try {
                if(const char *flag=std::getenv("STS_DIFFERENTIAL_TRACE");flag && std::string(flag)=="1")
                    throw std::runtime_error("DIFFERENTIAL_PUBLIC_MATCH_KEEP_UNREPRESENTABLE");
                std::map<std::tuple<int,int,bool>,bool> wants;
                policy.setRewardPityHistoryComplete(state.rewardPityHistoryComplete);
                policy.setQuestionHistoryComplete(state.mctsRoot.questionHistoryComplete);
                policy.setQuestionChancePosterior(state.mctsRoot.questionChancePosterior);
                policy.setMapHistoryComplete(state.mctsRoot.mapHistoryComplete);
                policy.setTreeCapture(false,0);
                const auto want=[&](const sts::Card &card) {
                    const auto key=std::make_tuple(static_cast<int>(card.id),static_cast<int>(card.misc),card.isUpgraded());
                    if(wants.count(key)) return wants.at(key);
                    if(!state.mctsRoot.supported) throw std::runtime_error(state.mctsRoot.reason);
                    auto offer=state.mctsRoot.state;
                    offer.screenState=sts::ScreenState::REWARDS;
                    offer.info.rewardsContainer=sts::Rewards();
                    sts::CardReward cards; cards.push_back(card);
                    offer.info.rewardsContainer.addCardReward(cards);
                    offer.regainControlAction=[](sts::GameContext &g) {
                        g.screenState=sts::ScreenState::MAP_SCREEN;g.regainControlAction=nullptr;
                    };
                    std::vector<std::uint32_t> bits;
                    for(const auto &action:v4CandidateActions(offer)) bits.push_back(action.bits);
                    policy.setRootPrimitiveBits(bits);
                    policy.setSearchSeed(stableHash(request.observationHash+":match-keep:"+std::to_string(static_cast<int>(card.id))));
                    const auto decision=policy.score(offer,state.mctsRoot.path,state.mctsRoot.currentActEventVisits);
                    if(!decision.supported || decision.selectedIndex<0
                            || decision.selectedIndex>=static_cast<int>(decision.candidates.size()))
                        throw std::runtime_error(decision.reason.empty()?"MATCH_KEEP_CARD_VALUE_UNAVAILABLE":decision.reason);
                    const auto before=offer.deck.size();
                    sts::search::GameAction(decision.candidates[decision.selectedIndex].primitiveBits).execute(offer);
                    const bool take=offer.deck.size()>before;
                    wants.emplace(key,take);
                    return take;
                };
                const int slot=sts::search::chooseMatchAndKeepSlot(state.projected,want);
                const auto action=advisor::lowerLiveOocAction(state,sts::search::GameAction(slot).bits);
                const std::string key="ooc-live:v1:match-keep:slot:"+std::to_string(slot);
                evaluator["status"]="OK";
                evaluator["mode"]="public_memory_policy";
                evaluator["valueSemantics"]="public_card_preferences";
                evaluator["selectedSemanticKey"]=key;
                evaluator["selectedLabel"]="Reveal remembered board slot "+std::to_string(slot+1);
                evaluator["selectedLiveAction"]=action;
                evaluator["candidateSummaries"]=json::array({json{
                    {"semanticKey",key},{"semanticPayload",{{"type","match_keep_slot"},{"slot",slot}}},
                    {"label",evaluator["selectedLabel"]},{"q",0.0},{"visits",1},{"visitShare",1.0},{"prior",1.0},
                    {"liveAction",action}}});
            } catch(const std::exception &error) { evaluator["reason"]=error.what(); }
            policy.setRootPrimitiveBits(advisor::liveOocPrimitiveBits(state));
            evaluator["latencyMicros"]=std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now()-started).count();
            return {{"protocol",advisor::kProtocol},{"protocolVersion",advisor::kProtocolVersion},
                {"kind","analysis"},{"status",evaluator.at("status")},{"session",request.session},
                {"sequence",request.sequence},{"observationHash",request.observationHash},
                {"evaluators",json::array({evaluator})}};
        }
        if (state.mechanicalEventTransition || state.forcedOocTransition) {
            // The importer checked the exact public boundary: either a sole
            // continuation or the boss chest's informational Open action.
            // No model or native search is needed for this click.
            const auto &liveAction = state.ooc.at("liveChoices").at(0).at("liveAction");
            const auto transition = state.ooc.at("details").at("mechanicalTransition").get<std::string>();
            const bool reveal = transition == "boss_chest_reveal";
            const std::string key = (reveal ? "ooc-live:v1:reveal:" : "ooc-live:v1:mechanical:") + transition;
            pending = PendingCompoundPlan{};
            evaluator["status"] = "OK";
            evaluator["mode"] = "native_pass_through";
            evaluator["valueSemantics"] = reveal ? "public_reveal_no_search" : "forced_no_search";
            evaluator["selectedSemanticKey"] = key;
            evaluator["selectedLabel"] = reveal ? "Open boss chest" : "continue";
            evaluator["selectedLiveAction"] = liveAction;
            evaluator["candidateSummaries"] = json::array({json{
                {"semanticKey", key}, {"semanticPayload", json{{"type", "pass_through"},
                    {"transition", transition}}}, {"label", evaluator["selectedLabel"]},
                {"q", 0.0}, {"visits", 1}, {"visitShare", 1.0}, {"prior", 1.0},
                {"liveAction", liveAction}}});
            if (const char *flag = std::getenv("STS_DIFFERENTIAL_TRACE"); flag && std::string(flag) == "1") {
                // The simulator omits these dialogue boundaries; there is
                // no equivalent canonical state or intro RNG transition.
                evaluator["status"] = "UNSUPPORTED";
                evaluator["reason"] = state.mechanicalEventTransition
                    ? "DIFFERENTIAL_MECHANICAL_EVENT_UNREPRESENTABLE"
                    : "DIFFERENTIAL_FORCED_OOC_UNREPRESENTABLE";
                evaluator.erase("selectedSemanticKey");
                evaluator.erase("selectedLiveAction");
                evaluator.erase("candidateSummaries");
            }
            evaluator["latencyMicros"] = std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now() - started).count();
            return {{"protocol", advisor::kProtocol}, {"protocolVersion", advisor::kProtocolVersion},
                    {"kind", "analysis"}, {"status", evaluator.at("status")}, {"session", request.session},
                    {"sequence", request.sequence}, {"observationHash", request.observationHash},
                    {"evaluators", json::array({evaluator})}};
        }
        if (const char *flag = std::getenv("STS_DIFFERENTIAL_TRACE"); flag && std::string(flag) == "1")
            evaluator["differentialState"] = differential::canonicalOocState(
            state.projected, state.path);
        // After choosing a boss relic, vanilla can expose the already-open
        // boss chest as a completed room with only the native Proceed button.
        // The simulator's TREASURE_ROOM action set describes the pre-open
        // state, so it is not a valid mapping for this observed pass-through.
        // Preserve the one legal live action without scoring hypothetical
        // open/skip actions.
        const auto &ooc = state.ooc;
        const bool openedPassThrough = state.projected.screenState == sts::ScreenState::TREASURE_ROOM
            && ooc.contains("details") && ooc.at("details").is_object()
            && ooc.at("details").value("opened", false)
            && ooc.contains("liveChoices") && ooc.at("liveChoices").is_array()
            && ooc.at("liveChoices").size() == 1
            && ooc.at("liveChoices").at(0).contains("liveAction")
            && ooc.at("liveChoices").at(0).at("liveAction").value("kind", std::string()) == "proceed";
        if (openedPassThrough) {
            const auto liveAction = ooc.at("liveChoices").at(0).at("liveAction");
            evaluator["status"] = "OK";
            evaluator["mode"] = "native_pass_through";
            evaluator["valueSemantics"] = "forced_no_search";
            evaluator["selectedSemanticKey"] = "ooc-live:v1:pass-through";
            evaluator["selectedLabel"] = "proceed";
            evaluator["selectedLiveAction"] = liveAction;
            evaluator["candidateSummaries"] = json::array({json{
                {"semanticKey", "ooc-live:v1:pass-through"},
                {"semanticPayload", json{{"type", "pass_through"}}},
                {"label", "proceed"}, {"q", 0.0}, {"visits", 1},
                {"visitShare", 1.0}, {"prior", 1.0},
                {"liveAction", liveAction}}});
            evaluator["latencyMicros"] = std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now() - started).count();
            return {{"protocol", advisor::kProtocol}, {"protocolVersion", advisor::kProtocolVersion},
                    {"kind", "analysis"}, {"status", evaluator.at("status")},
                    {"session", request.session}, {"sequence", request.sequence},
                    {"observationHash", request.observationHash},
                    {"evaluators", json::array({evaluator})}};
        }
        if (const auto forcedGoldAction = advisor::forcedRewardGoldLiveAction(state)) {
            const auto &liveAction = *forcedGoldAction;
            evaluator["status"] = "OK";
            evaluator["mode"] = "native_pass_through";
            evaluator["valueSemantics"] = "forced_no_search";
            evaluator["selectedSemanticKey"] = "ooc-live:v1:take-gold";
            evaluator["selectedLabel"] = "collect gold";
            evaluator["selectedLiveAction"] = liveAction;
            evaluator["candidateSummaries"] = json::array({json{
                {"semanticKey", "ooc-live:v1:take-gold"},
                {"semanticPayload", json{{"type", "take_gold"}}},
                {"label", "collect gold"}, {"q", 0.0}, {"visits", 1},
                {"visitShare", 1.0}, {"prior", 1.0},
                {"liveAction", liveAction}}});
            evaluator["latencyMicros"] = std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now() - started).count();
            return {{"protocol", advisor::kProtocol}, {"protocolVersion", advisor::kProtocolVersion},
                    {"kind", "analysis"}, {"status", evaluator.at("status")},
                    {"session", request.session}, {"sequence", request.sequence},
                    {"observationHash", request.observationHash},
                    {"evaluators", json::array({evaluator})}};
        }
        try {
            validateCapturedLiveOocMapping(state);
            policy.setRootPrimitiveBits(advisor::liveOocPrimitiveBits(state));
            policy.setRewardPityHistoryComplete(state.rewardPityHistoryComplete);
            policy.setQuestionHistoryComplete(state.mctsRoot.questionHistoryComplete);
            policy.setQuestionChancePosterior(state.mctsRoot.questionChancePosterior);
            policy.setMapHistoryComplete(state.mctsRoot.mapHistoryComplete);
            const char *treeEnv = std::getenv("STS_OOC_DEBUG_TREE");
            policy.setTreeCapture(request.observation.value("oocDebugTree", false)
                || (treeEnv && std::string(treeEnv) == "1"), oocTreeNodeCap());
        } catch (const std::exception &error) {
            return advisor::errorResponse(request, "OOC_ACTION_MAPPING", error.what());
        }
        if (std::string(policy.name()) == "mcts_ctm" && !state.mctsRoot.supported) {
            evaluator["reason"] = state.mctsRoot.reason;
            evaluator["latencyMicros"] = std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now() - started).count();
            return {{"protocol", advisor::kProtocol}, {"protocolVersion", advisor::kProtocolVersion},
                    {"kind", "analysis"}, {"status", evaluator.at("status")},
                    {"session", request.session}, {"sequence", request.sequence},
                    {"observationHash", request.observationHash},
                    {"evaluators", json::array({evaluator})}};
        }
        LiveOocDecision decision;
        bool appliedPending = false;
        json appliedTarget;
        if (pending.active && pending.session != request.session) pending = PendingCompoundPlan{};
        if (pending.active && request.sequence <= pending.sequence) pending = PendingCompoundPlan{};
        if (pending.active && state.projected.screenState == sts::ScreenState::CARD_SELECT) {
            const auto scoreStarted = std::chrono::steady_clock::now();
            decision = retainedCompoundDecision(state, pending);
            evaluator["scorerLatencyMicros"] = std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now() - scoreStarted).count();
            appliedPending = decision.supported;
            appliedTarget = pending.card;
        } else {
            if (pending.active) pending = PendingCompoundPlan{};
            policy.setSearchSeed(stableHash(state.projected.screenState==sts::ScreenState::CARD_SELECT
                ? differential::canonicalOocState(state.mctsRoot.state,state.mctsRoot.path).dump()+":selector"
                : request.observationHash + ":live-ooc-mcts"));
            const auto scoreStarted = std::chrono::steady_clock::now();
            decision = policy.score(state.mctsRoot.state, state.mctsRoot.path,
                                    state.mctsRoot.currentActEventVisits);
            evaluator["scorerLatencyMicros"] = std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now() - scoreStarted).count();
        }
        // Qualified candidate identities remain checkable without model weights.
        // A missing model must not turn corrupt live mappings into fallback.
        if (!decision.candidates.empty()) {
            try {
                std::vector<std::uint32_t> bits;
                for (const auto &c : decision.candidates) bits.push_back(c.primitiveBits);
                advisor::validateLiveOocActionSet(state, bits,
                    std::string(policy.name()) == "mcts_ctm");
            } catch (const std::exception &error) {
                return advisor::errorResponse(request, "OOC_ACTION_MAPPING", error.what());
            }
        }
        if (!decision.supported) {
            // Missing support/model may fall back; malformed/ambiguous native
            // candidates and nonfinite scores are integration errors.
            if (decision.reason != "MODEL_UNAVAILABLE" && decision.reason != "V4_SCREEN_UNSUPPORTED"
                    && decision.reason != "CTM_MODEL_UNAVAILABLE"
                    && decision.reason != "OOC_WIN_MODEL_UNAVAILABLE"
                    && decision.reason != "OOC_FLOOR_MODEL_UNAVAILABLE"
                    && decision.reason != "PUBLIC_REWARD_PITY_HISTORY_UNQUALIFIED"
                    && decision.reason != "RELIC_NATIVE_STATE_UNREPRESENTABLE:WingedGreaves:active"
                    && decision.reason.rfind("COMPOUND_TARGET_UNAVAILABLE:", 0) != 0
                    && decision.reason.rfind("SEMANTIC_ENUMERATION_UNSUPPORTED:", 0) != 0
                    && decision.reason.rfind("OOC_MCTS_", 0) != 0)
                return advisor::errorResponse(request, "OOC_POLICY_FAILURE", decision.reason);
            evaluator["reason"] = decision.reason;
        } else {
            try {
                const auto distributionJson = [](const sts::search::OocValueDistribution &d) {
                    return json{{"schema", "ooc_value_distribution_v1"}, {"bins", d.bins},
                        {"count", d.count}, {"mean", d.count ? json(d.sum / d.count) : json(nullptr)},
                        {"sumSquares", d.sumSquares},
                        {"terminalDeaths", d.bins[0]}, {"terminalVictories", d.bins[21]},
                        {"normalization", "share_of_own_samples"}};
                };
                evaluator["valueSemantics"] = decision.policy == "mcts_ctm"
                    ? "mean_backed_up_value_0_1" : "raw_v4_action_score";
                if (decision.valueDistribution)
                    evaluator["valueDistribution"] = distributionJson(*decision.valueDistribution);
                // One 0..axisMaxHp axis for the root and every candidate (index 0 = deaths).
                std::size_t hpBins = static_cast<std::size_t>(std::max(decision.rootMaxHp, 0)) + 1;
                if (decision.hpDistribution)
                    hpBins = std::max({hpBins, decision.hpDistribution->hpCounts.size(),
                        static_cast<std::size_t>(decision.hpDistribution->maxHp) + 1});
                const auto hpJson = [&](const sts::search::OocHpDistribution &d) {
                    auto counts = d.hpCounts;
                    counts.resize(hpBins, 0);
                    json floors = json::object();
                    for (const auto &[floor, n] : d.floors)
                        floors[std::to_string(floor - decision.rootFloor)] = n;
                    return json{{"count", d.count}, {"deaths", d.deaths}, {"unresolved", d.unresolved},
                        {"hpCounts", counts}, {"floorOffsets", floors}};
                };
                if (decision.hpDistribution)
                    evaluator["endpointHpDistribution"] = {
                        {"schema", "ooc_endpoint_hp_distribution_v1"},
                        {"hpSemantics", "player_hp_where_each_simulation_was_evaluated"},
                        {"currentHp", decision.rootHp}, {"maxHp", decision.rootMaxHp},
                        {"rootFloor", decision.rootFloor}, {"axisMaxHp", hpBins - 1},
                        {"root", hpJson(*decision.hpDistribution)}};
                evaluator["candidateSummaries"] = json::array();
                for (const auto &c : decision.candidates) {
                    json summary = {{"semanticKey", c.semanticKey},
                        {"semanticPayload", json::parse(c.payload)}, {"label", c.semanticKey}, {"q", c.q},
                        {"visits", c.visits}, {"visitShare", c.visitShare}, {"prior", c.prior},
                        {"liveAction", advisor::lowerLiveOocAction(state, c.primitiveBits)}};
                    if (c.valueDistribution) summary["valueDistribution"] = distributionJson(*c.valueDistribution);
                    if (c.hpDistribution && decision.hpDistribution) summary["endpointHp"] = hpJson(*c.hpDistribution);
                    if (!c.followUpPreview.empty()) summary["followUpPreview"] = json::parse(c.followUpPreview);
                    evaluator["candidateSummaries"].push_back(std::move(summary));
                }
                const auto &selected = decision.candidates.at(decision.selectedIndex);
                evaluator["status"] = "OK";
                evaluator["selectedSemanticKey"] = selected.semanticKey;
                evaluator["selectedLabel"] = selected.semanticKey;
                evaluator["selectedLiveAction"] = advisor::lowerLiveOocAction(state, selected.primitiveBits);
                if (appliedPending) {
                    evaluator["compoundPlan"] = json{{"status", "APPLIED"},
                        {"selectorType", pending.selectorName}, {"target", appliedTarget},
                        {"selectionMode", "retained_compound_target"}};
                    pending = PendingCompoundPlan{};
                } else {
                    auto selectedPayload = json::parse(selected.payload);
                    selectedPayload["semanticKey"] = selected.semanticKey;
                    const auto plan = pendingCompoundPlan(request, selectedPayload);
                    if (plan.active) {
                        pending = plan;
                        evaluator["compoundPlan"] = json{{"status", "PENDING"},
                            {"selectorType", plan.selectorName}, {"target", plan.card}};
                    }
                }
                if (policy.name() == std::string("mcts_ctm")) {
                    evaluator["model"] = {{"kind", "ooc_mcts_ctm"},
                                           {"prior", "ooc_strategic_tok_v4"},
                                           {"leaf", "v_win_compact_tree"}, {"simulations", 512},
                                           {"selection", "visits_then_q"}, {"identity", identity}};
                } else {
                    evaluator["model"] = {{"kind", "ooc_v4_q"}, {"identity", identity}};
                }
            } catch (const std::exception &error) {
                return advisor::errorResponse(request, "OOC_ACTION_MAPPING", error.what());
            }
        }
        if (decision.tree) {
            const auto &tree = *decision.tree;
            json captured = {{"accepted", true}, {"rootId", 0},
                {"truncated", tree.truncated}, {"nodes", json::array()},
                {"edges", json::array()}};
            for (const auto &node : tree.nodes)
                captured["nodes"].push_back({{"id", node.id}, {"kind", node.chance ? "chance" : "state"},
                    {"stateId", std::to_string(node.state)}, {"actionId", node.action},
                    {"label", node.label}, {"key", node.key}, {"outcome", node.outcome},
                    {"screen", node.screen}, {"room", node.room}, {"floor", node.floor},
                    {"mapX", node.mapX}, {"mapY", node.mapY}, {"hp", node.hp},
                    {"maxHp", node.maxHp}, {"gold", node.gold}, {"selected", node.selected},
                    {"depth", node.depth}, {"visits", node.visits},
                    {"prior", node.chance ? json(node.prior) : json(nullptr)},
                    {"q", node.chance && node.visits ? json(node.q) : json(nullptr)}});
            for (const auto &edge : tree.edges)
                captured["edges"].push_back({{"parentId", edge.parentId},
                    {"childId", edge.childId ? json(*edge.childId) : json(nullptr)},
                    {"visits", edge.visits}, {"kind", edge.particle ? "particle" : "action"},
                    {"combatModelUsed", edge.combatModelUsed},
                    {"combatEncounter", edge.combatEncounter}, {"combatOutcome", edge.combatOutcome}});
            evaluator["tree"] = std::move(captured);
        }
    }
    evaluator["latencyMicros"] = std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now() - started).count();
    return {{"protocol", advisor::kProtocol}, {"protocolVersion", advisor::kProtocolVersion},
            {"kind", "analysis"}, {"status", evaluator.at("status")},
            {"session", request.session}, {"sequence", request.sequence},
            {"observationHash", request.observationHash}, {"evaluators", json::array({evaluator})}};
}

bool truthyEnvironment(const char *name) {
    const char *value = std::getenv(name);
    if (value == nullptr) return false;
    return std::string(value) == "1" || std::string(value) == "true"
        || std::string(value) == "TRUE" || std::string(value) == "yes";
}

std::size_t silverTreeNodeCap() {
    const char *value = std::getenv("STS_SILVER_DEBUG_TREE_NODE_CAP");
    if (value == nullptr || *value == '\0') return 8192;
    for (const char *cursor = value; *cursor != '\0'; ++cursor) {
        if (*cursor < '0' || *cursor > '9') return 8192;
    }
    char *end = nullptr;
    errno = 0;
    const auto parsed = std::strtoull(value, &end, 10);
    if (errno == ERANGE || end == value || *end != '\0' || parsed == 0) return 8192;
    return static_cast<std::size_t>(std::min<unsigned long long>(parsed, 100000));
}

json silverTreeSnapshotJson(const silver_bridge::SilverTreeSnapshot &snapshot) {
    json output = {
        {"accepted", snapshot.accepted},
        {"failureReason", snapshot.failureReason},
        {"truncated", snapshot.truncated},
        {"rootId", snapshot.rootId},
        {"retainedNodeCount", snapshot.retainedNodeCount},
        {"retainedEdgeCount", snapshot.retainedEdgeCount},
        {"nodes", json::array()},
        {"edges", json::array()},
    };
    for (const auto &node : snapshot.nodes) {
        json item = {
            {"id", node.id}, {"parentId", node.parentId}, {"depth", node.depth},
            {"isChanceNode", node.isChanceNode}, {"hasState", node.hasState},
            {"stateHash", node.stateHash}, {"simulationCount", node.simulationCount},
            {"victoryCount", node.victoryCount}, {"evaluationSum", node.evaluationSum},
        };
        if (node.hasState) item["state"] = node.state;
        output["nodes"].push_back(std::move(item));
    }
    for (const auto &edge : snapshot.edges) {
        json item = {
            {"parentId", edge.parentId}, {"childId", edge.childId},
            {"childCaptured", edge.childCaptured}, {"chanceOutcome", edge.chanceOutcome},
            {"rngAdvanceSteps", edge.rngAdvanceSteps}, {"visitCount", edge.visitCount},
            {"hasAction", edge.hasAction}, {"actionFingerprint", edge.actionFingerprint},
            {"actionLabel", edge.actionLabel}, {"hasContinuation", edge.hasContinuation},
            {"continuationFingerprint", edge.continuationFingerprint},
            {"continuationLabel", edge.continuationLabel},
        };
        if (edge.hasAction) item["action"] = edge.action;
        if (edge.hasContinuation) item["continuation"] = edge.continuation;
        output["edges"].push_back(std::move(item));
    }
    return output;
}

json finalHpLayerJson(const sts::search::SilverOutcomeCapture::Layer &layer,
                      std::size_t bins) {
    auto counts = layer.hpCounts;
    counts.resize(bins, 0);
    return {{"count", layer.count}, {"deaths", layer.deaths},
            {"unresolved", layer.unresolved}, {"hpCounts", counts}};
}

json silverEvaluator(const one_combat::advisor::Request &request,
                     std::unique_ptr<one_combat::advisor::NativeSilverAdvisorSession> &session,
                     std::string &sessionIdentity, std::string &combatEntryIdentity,
                     one_combat::advisor::SilverImportContext &importContext,
                     std::string &silverRootIdentity,
                     std::int64_t &silverSimulations) {
    const auto entryIdentity = request.observation.value(
        "combatEntryHash", request.observation.value("silverRoot", json::object())
            .value("combatInstance", std::string()));
    // Reset before importing so a new protocol session cannot inherit the
    // previous session's UUID registry when the combat hash happens to repeat.
    importContext.reset(request.session, entryIdentity);
    json evaluator = {{"id", "silver_player_decision_v2"},
                      {"scope", "combat_player_decision"}, {"engine", "native_silver"},
                      {"simulations", 1000}, {"adaptiveEnabled", false},
                      {"exactVisitLockEnabled", false}, {"rhoRacingEnabled", false}};
    const auto clearSession = [&] {
        session.reset();
        sessionIdentity.clear();
        combatEntryIdentity.clear();
        silverRootIdentity.clear();
        silverSimulations = 0;
    };
    const auto unsupported = [&](const std::string &reason) {
        clearSession();
        evaluator["status"] = "UNSUPPORTED";
        evaluator["reason"] = reason;
        return evaluator;
    };
    const auto combat = request.observation.contains("combat")
        ? request.observation.at("combat")
        : request.observation.value("silverRoot", json::object()).value("combat", json::object());
    const auto selection = combat.value("cardSelect", json::object());
    if (selection.contains("mechanicalTransition")) {
        evaluator["mode"] = "native_pass_through";
        const auto task = selection.value("task", std::string());
        const auto owner = selection.value("actionClass", std::string());
        const bool knownOwner = (task == "WARCRY" && owner == "com.megacrit.cardcrawl.actions.common.PutOnDeckAction")
            || (task == "FORETHOUGHT" && owner == "com.megacrit.cardcrawl.actions.unique.ForethoughtAction");
        const auto integerIs = [&](const char *key, int expected) {
            return selection.contains(key) && selection.at(key).is_number_integer()
                && selection.at(key).get<int>() == expected;
        };
        if (selection.value("mechanicalTransition", std::string()) != "single_select_confirm"
            || selection.value("origin", std::string()) != "HAND_SELECT" || !knownOwner
            || !integerIs("pickCount", 1) || !integerIs("selectedCount", 1)
            || !integerIs("liveChoiceCount", 0)
            || !selection.contains("canProceed") || selection.at("canProceed") != true
            || !selection.contains("canCancel") || selection.at("canCancel") != false
            || !selection.contains("selectedUuid") || !selection.at("selectedUuid").is_string()
            || selection.at("selectedUuid").get<std::string>().empty())
            return unsupported("silver_unqualified_selection_confirmation");
        if (const char *flag = std::getenv("STS_DIFFERENTIAL_TRACE"); flag && std::string(flag) == "1")
            return unsupported("DIFFERENTIAL_COMBAT_CONFIRMATION_UNREPRESENTABLE");
        // Java has moved the selected card into a temporary UI group. Only
        // Proceed remains. Keep the prior native session for the next stable
        // combat root; this UI click neither searches nor fabricates a state.
        evaluator["status"] = "OK";
        evaluator["mode"] = "native_pass_through";
        evaluator["valueSemantics"] = "forced_no_search";
        evaluator["simulations"] = 0;
        evaluator["selectedLabel"] = "confirm selected card";
        evaluator["selectedLiveAction"] = {{"kind", "proceed"}};
        return evaluator;
    }
    const auto imported = one_combat::advisor::importSilverRoot(request.observation, importContext);
    if (!imported.ok) return unsupported(imported.reason);
    const auto entry = request.observation.value("combatEntryHash", std::string());
    const bool matchingSession = session != nullptr && sessionIdentity == request.session
        && combatEntryIdentity == entry;
    if (!matchingSession && imported.playerTurn == 1 && imported.decisionInTurn == 0) {
        session = std::make_unique<one_combat::advisor::NativeSilverAdvisorSession>();
        sessionIdentity = request.session;
        combatEntryIdentity = entry;
        silverRootIdentity.clear();
        silverSimulations = 0;
    } else if (!matchingSession) {
        return unsupported("silver_missing_predecessor");
    }
    if (const char *flag = std::getenv("STS_DIFFERENTIAL_TRACE"); flag && std::string(flag) == "1")
        evaluator["differentialState"] = one_combat::differential::canonicalCombatState(imported.wire);
    const auto requestedSimulations = std::max<std::int64_t>(1000,
        request.observation.value("silverSearchBudget", static_cast<std::int64_t>(1000)));
    const auto rootIdentity = request.observation.value("silverRoot", json::object()).dump();
    if (silverRootIdentity != rootIdentity) {
        silverRootIdentity = rootIdentity;
        silverSimulations = 0;
    }
    if (silverSimulations > requestedSimulations) return unsupported("silver_budget_regression");
    const auto additionalSimulations = requestedSimulations - silverSimulations;
    const auto started = std::chrono::steady_clock::now();
    const auto decision = silverSimulations == 0
        ? session->decide(imported.wire, additionalSimulations)
        : session->extend(additionalSimulations);
    evaluator["latencyMicros"] = std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now() - started).count();
    if (!decision.accepted) return unsupported(decision.failureReason);
    silverSimulations += decision.simulations;
    evaluator["status"] = "OK";
    evaluator["simulations"] = silverSimulations;
    evaluator["requestedSimulations"] = requestedSimulations;
    evaluator["additionalSimulations"] = decision.simulations;
    evaluator["totalSimulations"] = silverSimulations;
    evaluator["rootVisits"] = decision.rootVisits;
    evaluator["selectedAction"] = sts::search::semanticFingerprint(decision.action);
    evaluator["selectedLabel"] = one_combat::advisor::silverActionLabel(decision.action, imported.wire);
    evaluator["selectedLiveAction"] = one_combat::advisor::selectedLiveAction(
        decision.action, importContext, request.observation);
    if (evaluator["selectedLiveAction"].is_null()) {
        evaluator.erase("selectedAction");
        evaluator.erase("selectedLabel");
        evaluator.erase("selectedLiveAction");
        return unsupported("silver_live_action_lowering");
    }
    evaluator["legalActions"] = json::array();
    for (const auto &action : decision.legalActions)
        evaluator["legalActions"].push_back(sts::search::semanticFingerprint(action));
    evaluator["rootActionSummaries"] = json::array();
    std::vector<const one_combat::advisor::NativeSilverRootSummary *> ranked;
    for (const auto &summary : decision.rootActionSummaries) ranked.push_back(&summary);
    std::stable_sort(ranked.begin(), ranked.end(),
                     [](const auto *a, const auto *b) { return a->edgeVisits > b->edgeVisits; });
    std::int64_t totalVisits = 0;
    for (const auto *summary : ranked) totalVisits += summary->edgeVisits;
    // Every layer shares one 0..axisMaxHp axis; victories can exceed the root
    // max HP (e.g. Feed).
    const std::size_t finalHpBins = std::max<std::size_t>(
        static_cast<std::size_t>(std::max(decision.rootMaxHp, 0)) + 1,
        decision.outcomes.root.hpCounts.size());
    evaluator["finalHpDistribution"] = {
        {"schema", "silver_final_hp_distribution_v1"},
        {"scope", "simulations_since_root"},
        {"hpSemantics", "player_hp_at_combat_end_before_post_combat_heals"},
        {"currentHp", decision.rootHp}, {"maxHp", decision.rootMaxHp},
        {"axisMaxHp", finalHpBins - 1},
        {"root", finalHpLayerJson(decision.outcomes.root, finalHpBins)}};
    std::string rankingText;
    for (const auto *summary : ranked) {
        json item = {
            {"fingerprint", sts::search::semanticFingerprint(summary->action)},
            {"label", one_combat::advisor::silverActionLabel(summary->action, imported.wire)},
            {"liveAction", one_combat::advisor::selectedLiveAction(
                summary->action, importContext, request.observation)},
            {"edgeVisits", summary->edgeVisits}, {"selectionQValid", summary->selectionQValid},
            {"visitShare", totalVisits == 0 ? 0.0 : static_cast<double>(summary->edgeVisits) / totalVisits}};
        if (summary->selectionQValid) item["selectionQ"] = summary->selectionQ;
        const auto edge = static_cast<std::size_t>(summary - decision.rootActionSummaries.data());
        item["finalHp"] = finalHpLayerJson(decision.outcomes.edges.at(edge), finalHpBins);
        evaluator["rootActionSummaries"].push_back(std::move(item));
    }
    for (std::size_t i = 0; i < ranked.size() && i < 5; ++i) {
        if (!rankingText.empty()) rankingText += "\n";
        rankingText += one_combat::advisor::silverActionLabel(ranked[i]->action, imported.wire);
        rankingText += "|" + std::to_string(ranked[i]->edgeVisits);
        rankingText += "|" + (ranked[i]->selectionQValid ? std::to_string(ranked[i]->selectionQ) : "");
    }
    evaluator["rankingText"] = rankingText;
    evaluator["playerTurn"] = imported.playerTurn;
    evaluator["decisionInTurn"] = imported.decisionInTurn;
    evaluator["reroot"] = {
        {"exact", decision.exactReroot},
        {"equivalentCopy", decision.equivalentCopyReroot},
        {"fallback", decision.fallback},
        {"fallbackReason", decision.fallbackReason},
        {"inheritedVisits", decision.inheritedVisits},
    };
    const bool debugTree = request.observation.value("silverDebugTree", false)
        || truthyEnvironment("STS_SILVER_DEBUG_TREE");
    if (debugTree) {
        const auto nodeCap = silverTreeNodeCap();
        auto tree = silverTreeSnapshotJson(session->snapshot(nodeCap));
        tree["nodeCap"] = nodeCap;
        evaluator["tree"] = std::move(tree);
    }
    return evaluator;
}
}

int main() {
    one_combat::advisor::LatestObservation latest;
    auto oocModel = std::make_unique<OocStrategicTokNet>();
    std::string oocIdentity = "unavailable";
    if (const char *path = std::getenv("STS_LIVE_OOC_MODEL"); path && *path) {
        if (oocModel->load(path, true)) oocIdentity = modelIdentity(path);
    }
    one_combat::CompactTreeNet oocWinModel;
    std::string oocWinIdentity = "unavailable";
    if (const char *path = std::getenv("STS_LIVE_OOC_WIN_MODEL"); path && *path) {
        // CompactTreeNet is also used by the simulator and reports successful
        // loads on stdout. The advisor stdout is a strict JSONL protocol, so
        // keep that diagnostic out of the wire stream.
        std::ostringstream discardedLoadBanner;
        auto *const stdoutBuffer = std::cout.rdbuf(discardedLoadBanner.rdbuf());
        bool loaded = false;
        try {
            loaded = oocWinModel.load(path, one_combat::richIdxMap(), "LiveOocWinModel");
        } catch (...) {
            std::cout.rdbuf(stdoutBuffer);
            throw;
        }
        std::cout.rdbuf(stdoutBuffer);
        if (loaded)
            oocWinIdentity = modelIdentity(path);
    }
    one_combat::CompactTreeNet oocFloorModel;
    std::string oocFloorIdentity = "unavailable";
    if (const char *path = std::getenv("STS_LIVE_OOC_FLOOR_MODEL"); path && *path) {
        std::ostringstream discardedLoadBanner;
        auto *const stdoutBuffer = std::cout.rdbuf(discardedLoadBanner.rdbuf());
        bool loaded = false;
        try {
            loaded = oocFloorModel.load(path, one_combat::richIdxMap(), "LiveOocFloorModel");
        } catch (...) {
            std::cout.rdbuf(stdoutBuffer);
            throw;
        }
        std::cout.rdbuf(stdoutBuffer);
        if (loaded) oocFloorIdentity = modelIdentity(path);
    }
    std::shared_ptr<one_combat::CombatTransitionSampler> ctm;
    json ctmStack = nullptr;
    std::string ctmStatus = "MODEL_UNAVAILABLE", ctmReason;
    std::string ctmIdentity = "unavailable";
    std::string cachedEntryHash;
    PendingCompoundPlan pendingCompound;
    json cachedEvaluator;
    if (const char *path = std::getenv("STS_SILVER_ROOT_PRIOR_MODEL"); path && *path)
        throw std::invalid_argument("STS_SILVER_ROOT_PRIOR_MODEL is no longer supported: "
                                    "the advisor runs native Silver search without a root prior");
    std::unique_ptr<one_combat::advisor::NativeSilverAdvisorSession> silverSession;
    std::string silverSessionIdentity;
    std::string silverCombatEntryIdentity;
    one_combat::advisor::SilverImportContext silverImportContext;
    std::string silverRootIdentity;
    std::int64_t silverSimulations = 0;
    if (const char *path = std::getenv("STS_CTM_MODEL"); path) {
        try {
            if (!*path) throw std::invalid_argument("STS_CTM_MODEL cannot be empty");
            auto primary = std::make_shared<one_combat::NativeCombatTransitionSampler>(path);
            const char *fallbackOverride = std::getenv("STS_CTM_BREW_FALLBACK_MODEL");
            const char *lizardOverride = std::getenv("STS_CTM_ACTIVE_LIZARD");
            if (fallbackOverride && !*fallbackOverride)
                throw std::invalid_argument("STS_CTM_BREW_FALLBACK_MODEL cannot be empty");
            const auto &metadata = primary->runtime().metadata();
            const bool productionLizard = primary->runtime().hasActiveLizardCorrection()
                && metadata.value("defaultForOocMcts", false)
                && metadata.at("activeLizardCorrection").value("qualified", false)
                && metadata.at("activeLizardCorrection").value("status", std::string())
                    == "production_default_when_ooc_enabled";
            // The loader also accepts frozen integration candidates. Their
            // correction requires an explicit opt-in, never implicit promotion.
            bool activeLizard = productionLizard;
            if (lizardOverride) {
                if (std::string(lizardOverride) == "0") activeLizard = false;
                else if (std::string(lizardOverride) == "1") activeLizard = true;
                else throw std::invalid_argument("STS_CTM_ACTIVE_LIZARD must be 0 or 1");
            }
            const bool hybrid = primary->runtime().requiresEntropicBrewFallback();
            if (!hybrid && (fallbackOverride || activeLizard))
                throw std::invalid_argument("CTM fallback/Lizard correction requires a qualified fast artifact");
            ctmStack = {{"kind", hybrid ? "deepsets_brew" : "single"},
                        {"primary", modelIdentity(path)}, {"activeLizard", activeLizard},
                        {"lizardProductionQualified", productionLizard}};
            if (hybrid) {
                const std::string fallback = fallbackOverride ? fallbackOverride :
                    (std::filesystem::path(path).parent_path() /
                        "combat_transition_near_full_except_smoke_v2.native").string();
                ctm = std::make_shared<one_combat::EntropicBrewFallbackCombatTransitionSampler>(
                    path, fallback, activeLizard);
                ctmStack["brewFallback"] = modelIdentity(fallback);
            } else ctm = std::move(primary);
            ctmIdentity = ctmStack.dump();
            ctmStatus = "OK";
        } catch (const std::exception &e) {
            ctm.reset(); ctmStack = nullptr;
            ctmStatus = "SCHEMA_MISMATCH"; ctmReason = e.what();
        }
    }
    std::unique_ptr<one_combat::LiveOocPolicy> oocPolicy;
    if (const char *selected = std::getenv("STS_LIVE_OOC_POLICY"); selected && std::string(selected) == "v4")
        oocPolicy = std::make_unique<one_combat::LiveOocV4QPolicy>(*oocModel);
    else
        oocPolicy = std::make_unique<one_combat::LiveOocMctsPolicy>(*oocModel, ctm,
                                                                      &oocWinModel, &oocFloorModel);
    std::string line;
    while (std::getline(std::cin, line)) {
        json response;
        try {
            const json wire = json::parse(line);
            if (wire.value("kind", std::string()) == "hello" &&
                wire.value("protocol", std::string()) == one_combat::advisor::kProtocol) {
                response = one_combat::advisor::helloResponse();
                response["ctmStatus"] = ctmStatus;
                response["ctmStack"] = ctmStack;
                if (!ctmReason.empty()) response["ctmReason"] = ctmReason;
            } else {
                one_combat::advisor::Request request;
                const auto validation = one_combat::advisor::parseRequest(wire, request);
                if (!validation.ok) {
                    response = request.identityTrusted
                        ? one_combat::advisor::errorResponse(
                              request, validation.code, validation.message)
                        : one_combat::advisor::errorResponse(validation.code, validation.message);
                } else if (!latest.accept(request)) {
                    response = one_combat::advisor::staleResponse(request, "older sequence in session");
                } else {
                    if (request.observation.value("boundary", std::string()) == "combat") {
                        const auto silver = silverEvaluator(request, silverSession,
                                                            silverSessionIdentity,
                                                            silverCombatEntryIdentity,
                                                            silverImportContext,
                                                            silverRootIdentity,
                                                            silverSimulations);
                        if (silver.value("mode", std::string()) == "native_pass_through") {
                            response = {{"protocol", one_combat::advisor::kProtocol},
                                {"protocolVersion", one_combat::advisor::kProtocolVersion},
                                {"kind", "analysis"}, {"status", silver.at("status")}, {"session", request.session},
                                {"sequence", request.sequence}, {"observationHash", request.observationHash},
                                {"evaluators", json::array({silver})}};
                        } else if (!ctm) {
                            if (!request.observation.contains("combatEntry")) {
                                response = one_combat::advisor::unsupportedResponse(
                                    request, "model unavailable");
                            } else response = { {"protocol", one_combat::advisor::kProtocol},
                                {"protocolVersion", one_combat::advisor::kProtocolVersion},
                                {"kind", "analysis"}, {"status", ctmStatus},
                                {"reason", ctmReason.empty() ? ctmStatus : ctmReason},
                                {"session", request.session}, {"sequence", request.sequence},
                                {"observationHash", request.observationHash},
                                {"evaluators", json::array({silver})} };
                        } else {
                            one_combat::CombatPredictorInputV1 input;
                            const auto imported = one_combat::advisor::importCombatPredictorInput(
                                request.observation, input);
                            if (!imported.ok) response = one_combat::advisor::errorResponse(
                                request, imported.code, imported.message);
                            else {
                                const std::string entryHash = request.observation.value(
                                    "combatEntryHash", request.observationHash);
                                json evaluator;
                                if (entryHash == cachedEntryHash && !cachedEvaluator.is_null()) {
                                    evaluator = cachedEvaluator;
                                    evaluator["latencyMicros"] = 0;
                                } else {
                                    const auto started = std::chrono::steady_clock::now();
                                    const auto support = ctm->forecastSupport(input);
                                    evaluator = {{"id", "ctm_combat_entry_v2"},
                                        {"scope", "combat_entry"}, {"combatEntryHash", entryHash},
                                        {"potionKeepValue", input.globals.potionKeepValue},
                                        {"modelIdentity", ctmIdentity}, {"ctmStack", ctmStack}};
                                    if (!support.supported) {
                                        evaluator["status"] = "UNSUPPORTED";
                                        evaluator["reason"] = support.reason;
                                    } else {
                                        const auto result = ctm->forecastExpectation(input);
                                        evaluator["status"] = "OK";
                                        evaluator["deathProbability"] = result.death;
                                        evaluator["winningHpHistogramMin"] = result.winningHpMin;
                                        evaluator["winningHpHistogram"] = result.winningHpHistogram;
                                    }
                                    evaluator["latencyMicros"] = std::chrono::duration_cast<std::chrono::microseconds>(
                                        std::chrono::steady_clock::now() - started).count();
                                    cachedEntryHash = entryHash;
                                    cachedEvaluator = evaluator;
                                }
                                response = {{"protocol", one_combat::advisor::kProtocol},
                                    {"protocolVersion", one_combat::advisor::kProtocolVersion},
                                    {"kind", "analysis"}, {"status", "OK"},
                                    {"session", request.session}, {"sequence", request.sequence},
                                    {"observationHash", request.observationHash},
                                    {"evaluators", json::array({evaluator, silver})},
                                    {"model", ctmIdentity}, {"ctmStack", ctmStack},
                                    {"modelStatus", ctmStatus}};
                            }
                        }
                    } else if (request.observation.value("boundary", std::string()) == "ooc") {
                        response = oocResponse(request, *oocPolicy, oocIdentity + ":ctm=" + ctmIdentity
                                                + ":win=" + oocWinIdentity + ":floor=" + oocFloorIdentity
                                                + (one_combat::advisor::liveOocWingBootsEnabled()
                                                    ? ":wingBoots=experimental_exact" : ":wingBoots=guarded"),
                                                pendingCompound);
                    } else {
                        one_combat::advisor::PublicOocState imported;
                        const auto importedResult =
                            one_combat::advisor::importPublicOoc(request.observation, imported);
                        if (!importedResult.ok) {
                            response = one_combat::advisor::errorResponse(
                                request, importedResult.code, importedResult.message);
                        } else {
                            // The public OOC state is now imported and ID-checked.
                            // Keep evaluation fail-closed until map/path, relic,
                            // potion, and feature-parity contracts are imported.
                            response = one_combat::advisor::unsupportedResponse(
                                request, "native OOC evaluator is not yet feature-qualified");
                        }
                    }
                }
            }
        } catch (const json::exception &error) {
            response = one_combat::advisor::errorResponse("MALFORMED_JSON", error.what());
        } catch (const std::exception &error) {
            response = one_combat::advisor::errorResponse("ADVISOR_FAILURE", error.what());
        }
        if (response.contains("evaluators") && response["evaluators"].is_array()) {
            for (const auto &evaluator : response["evaluators"]) {
                if (evaluator.value("id", std::string()) == "silver_player_decision_v2") {
                    response["silverStatus"] = evaluator.value("status", std::string());
                    response["silverReason"] = evaluator.value("reason", std::string());
                    response["silverRanking"] = evaluator.value("rankingText", std::string());
                    break;
                }
            }
        }
        std::cout << response.dump() << '\n' << std::flush;
    }
    return 0;
}
