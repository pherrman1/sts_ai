#include "screen_leaf_s0.h"
#include "screen_leaf_snapshot.h"
#include "screen_leaf_continuations.h"
#include "screen_leaf_import.h"
#include "ooc_mcts_adapter.h"
#include "combat_transition_runtime.h"
#include <cstdio>
#include <fstream>
#include <set>
#include <time.h>

namespace one_combat {
namespace {
double cpuSeconds() {
    timespec t{};
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &t)) throw std::runtime_error("CPU clock failed");
    return double(t.tv_sec) + double(t.tv_nsec) * 1e-9;
}
std::uint64_t evaluationSeed(const std::string &identity, unsigned replicate) {
    // Frozen FNV-1a-64 domain; these IDs are randomization keys, never features.
    std::uint64_t value = 14695981039346656037ULL;
    for (unsigned char c : "screen-leaf-379-s0-v1:" + identity + ":" + std::to_string(replicate)) {
        value ^= c; value *= 1099511628211ULL;
    }
    return value;
}
}

int screenLeafS0(const std::string &input, const std::string &output,
                 unsigned limit, unsigned replicates) {
    using Json = nlohmann::json;
    if (!limit || !replicates || replicates > 32) throw std::runtime_error("invalid S0 pilot budget");
    std::ifstream in(input);
    if (!in) throw std::runtime_error("cannot read S0 snapshots");
    const auto deps = defaultOocMctsDependencies();
    if (!deps.leafValue || !deps.policyAvailable || !deps.policyAvailable()
        || deps.sampleHiddenCounters) throw std::runtime_error("S0 dependencies not native simulator contract");
    // Same default qualified hybrid stack as configureLiveOocMcts. Explicit
    // legacy overrides are deliberately not accepted by this offline harness.
    auto sampler = std::make_shared<EntropicBrewFallbackCombatTransitionSampler>(
        "selfplay/models/combat_transition_deepsets_lizard_t2.native",
        "selfplay/models/combat_transition_near_full_except_smoke_v2.native", true);
    OocAdapterOptions options;
    options.checkpointLeaves = true;
    options.sampleNoncombat = true;
    auto *file = std::fopen(output.c_str(), "wx");
    if (!file) throw std::runtime_error("S0 output exists or cannot be created");
    struct Close { std::FILE *f; ~Close() { std::fclose(f); } } close{file};
    const auto initialPolicy = captureOocPolicyThreadState();
    const auto *initialPath = t_curPath;
    struct Restore {
        OocPolicyThreadState policy; const PathHistory *path;
        ~Restore() { restoreOocPolicyThreadState(policy); t_curPath = path; }
    } restore{initialPolicy, initialPath};
    std::set<std::string> seen;
    std::string line;
    unsigned count = 0;
    while (count < limit && std::getline(in, line)) {
        Json row = Json::parse(line);
        const std::string identity = std::to_string(row.at("sourceSeed").get<std::uint64_t>())
            + ":" + row.at("branchId").get<std::string>() + ":" + std::to_string(row.at("rowIdx").get<int>());
        if (!seen.insert(identity).second) throw std::runtime_error("duplicate snapshot identity");
        auto state = screen_leaf::importEnvelope(row);
        if (state.gc.screenState == sts::ScreenState::MAP_SCREEN
            || state.gc.screenState == sts::ScreenState::BATTLE)
            throw std::runtime_error("S0 input is not a DECISION screen");
        if (richRow(state.gc, state.path) != row.at("features").get<std::string>())
            throw std::runtime_error("snapshot rich-feature parity failed: " + identity);
        const auto contract = screenLeafPublicContract(state.gc);
        const auto originalKeys = row.at("candidateKeys").get<std::set<std::string>>();
        const auto currentKeys = contract.at("candidateKeys").get<std::set<std::string>>();
        std::set<std::string> additions, removals;
        std::set_difference(currentKeys.begin(), currentKeys.end(), originalKeys.begin(), originalKeys.end(),
                            std::inserter(additions, additions.end()));
        std::set_difference(originalKeys.begin(), originalKeys.end(), currentKeys.begin(), currentKeys.end(),
                            std::inserter(removals, removals.end()));
        bool visibleReplacement = false;
        if (state.gc.potionCount == state.gc.potionCapacity && state.gc.potionCapacity > 0
            && !state.gc.hasRelic(sts::RelicId::SOZU)) {
            if (state.gc.screenState == sts::ScreenState::REWARDS)
                visibleReplacement = state.gc.info.rewardsContainer.potionCount > 0;
            if (state.gc.screenState == sts::ScreenState::SHOP_ROOM)
                for (int slot = 0; slot < 3; ++slot) {
                    const int price = state.gc.info.shop.potionPrice(slot);
                    visibleReplacement = visibleReplacement || (price >= 0 && price <= state.gc.gold);
                }
        }
        std::set<std::string> expectedDiscards;
        if (visibleReplacement) {
            if (state.gc.potionCapacity > int(state.gc.potions.size()))
                throw std::runtime_error("invalid restored potion capacity");
            for (int slot = 0; slot < state.gc.potionCapacity; ++slot) {
                const auto potion = state.gc.potions[slot];
                if (potion == sts::Potion::EMPTY_POTION_SLOT || potion == sts::Potion::INVALID) continue;
                sts::search::OocRewardTarget target;
                target.entity = potion;
                for (int prior = 0; prior < slot; ++prior)
                    if (state.gc.potions[prior] == potion) ++target.occurrence;
                sts::search::OocSemanticAction action;
                action.effect = sts::search::OocSemanticEffect::DISCARD_POTION;
                action.source = state.gc.screenState == sts::ScreenState::SHOP_ROOM
                    ? sts::search::OocSemanticSource::SHOP : sts::search::OocSemanticSource::REWARDS;
                action.target = target;
                expectedDiscards.insert(sts::search::canonicalOocSemanticActionKey(action));
            }
        }
        const bool allowedDiscardAddition = visibleReplacement && removals.empty()
            && additions == expectedDiscards
            && additions == contract.at("replacementDiscardKeys").get<std::set<std::string>>();
        if (contract.at("screenContents") != row.at("screenContents")
            || (!additions.empty() && !allowedDiscardAddition) || !removals.empty())
            throw std::runtime_error("snapshot public-screen/candidate parity failed: " + identity
                + "\n" + Json({{"actual", contract}, {"expected", {
                    {"screenContents", row.at("screenContents")},
                    {"candidateKeys", row.at("candidateKeys")}}}}).dump());
        Json values = Json::array(), seeds = Json::array();
        double elapsed = 0;
        std::uint64_t steps = 0;
        std::string unsupported;
        for (unsigned replicate = 0; replicate < replicates && unsupported.empty(); ++replicate) {
            restoreOocPolicyThreadState(state.policy);
            t_curPath = &state.path;
            OocGameContextModel model(state.gc, state.path, sampler, options, deps);
            const auto seed = evaluationSeed(identity, replicate);
            std::mt19937_64 rng(seed);
            // Root 0 equals a newly expanded non-MAP leaf here: the only
            // root-specific callback is absent (asserted above), and the MAP
            // special-case cannot apply. Calls the actual current implementation.
            const double start = cpuSeconds();
            double value = 0;
            try {
                value = model.evaluateLeaf(0, rng);
            } catch (const sts::search::OocSearchUnsupported &error) {
                // Live OOC MCTS aborts the whole search on this exception and
                // the decision falls back; S0 has no leaf value. Record the row
                // as fail-closed so comparisons exclude it pairwise.
                unsupported = error.what();
                if (unsupported.empty()) unsupported = "unspecified";
            }
            elapsed += cpuSeconds() - start;
            seeds.push_back(seed);
            steps += model.continuationMetrics().projectionSteps;
            if (!unsupported.empty()) break;
            if (!std::isfinite(value) || value < 0 || value > 1)
                throw std::runtime_error("invalid S0 prediction");
            values.push_back(value);
        }
        if (!unsupported.empty()) values = Json::array();
        Json result = {{"sourceSeed", row.at("sourceSeed")}, {"branchId", row.at("branchId")},
            {"rowIdx", row.at("rowIdx")}, {"decisionIdx", row.at("decisionIdx")},
            {"screen", row.at("screenContents").at("screen")}, {"act", state.gc.act},
            {"values", values}, {"rngSeeds", seeds}, {"leafCpuSeconds", elapsed},
            {"projectionSteps", steps},
            {"candidateCompatibility", additions.empty() ? "exact" : "public_potion_discard_additions"},
            {"historicalCandidateKeys", originalKeys}, {"currentCandidateKeys", currentKeys},
            {"addedPublicDiscardKeys", additions},
            {"snapshotSemantics", row.at("snapshotSemantics")},
            {"snapshotImportHistory", row.value("snapshotImportHistory", Json::array())}};
        if (!unsupported.empty()) {
            result["s0Status"] = "S0_UNSUPPORTED";
            result["unsupportedReason"] = unsupported;
        }
        const auto encoded = result.dump() + "\n";
        if (std::fwrite(encoded.data(), 1, encoded.size(), file) != encoded.size()
            || std::fflush(file)) throw std::runtime_error("S0 output write failure");
        ++count;
    }
    if (!count) throw std::runtime_error("empty S0 snapshot input");
    return 0;
}
}
