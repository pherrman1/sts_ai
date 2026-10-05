#pragma once
// Issue379 offline input compatibility only. Never used by live inference or
// the frozen producer. Python must bind historical tags to verified receipts.
#include "screen_leaf_snapshot.h"
#include "screen_leaf_continuations.h"
#include "sim/search/GameAction.h"
#include <algorithm>
#include <string>
#include <vector>

namespace one_combat::screen_leaf {
inline Json currentImportContext() {
    return {{"schema", "screen-leaf-import-context-v1"}, {"domain", "current-379"}};
}
inline bool importHash(const Json &value) {
    if (!value.is_string()) return false;
    const auto text = value.get<std::string>();
    return text.size() == 64 && std::all_of(text.begin(), text.end(), [](char c) {
        return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f');
    });
}
inline Snapshot importEnvelope(Json &row) {
    const auto &context = row.at("snapshotSemantics");
    if (!context.is_object() || context.at("schema") != "screen-leaf-import-context-v1")
        throw std::runtime_error("missing/invalid issue379 snapshot semantics");
    const bool historical = context.at("domain") == "frozen-334";
    if (historical) {
        const auto producer = context.at("producerGitSha").get<std::string>();
        if (context.size() != 7 ||
            (producer != "1e93bd66cb5ef489028f1a06c22d5f12bd2ca935" &&
             producer != "0665747164ca3914c229546ad13f4f26a3a4a23c") ||
            context.at("snapshotSchema") != "screen-leaf-full-state-v1" ||
            context.at("snapshotSchema") != row.at("snapshot").at("schema") ||
            context.at("sourceSeed") != row.at("sourceSeed") ||
            !importHash(context.at("sourceManifestSha256")) ||
            !importHash(context.at("inputArtifactSha256")))
            throw std::runtime_error("unbound historical issue379 import domain");
    } else if (context != currentImportContext()) {
        throw std::runtime_error("unknown issue379 snapshot import domain");
    }
    // This is intentionally still the lossless transport decoder. Original
    // bytes/state remain intact in the input; adaptation happens afterwards.
    auto state = snapshotFromJson(row.at("snapshot"), importContinuation);
    if (state.gc.seed != row.at("sourceSeed").get<std::uint64_t>())
        throw std::runtime_error("snapshot source seed differs");
    if (historical && state.gc.screenState == sts::ScreenState::EVENT_SCREEN &&
        state.gc.curEvent == sts::Event::GOLDEN_IDOL) {
        const bool idol = state.gc.hasRelic(sts::RelicId::GOLDEN_IDOL);
        const std::vector<int> expected = idol ? std::vector<int>{2, 3, 4} : std::vector<int>{0, 1};
        if (row.contains("screenContents")) {
            const auto &contents = row.at("screenContents");
            if (contents.at("screen") != "event" ||
                contents.at("eventId") != static_cast<int>(sts::Event::GOLDEN_IDOL) ||
                contents.at("optionIds").get<std::vector<int>>() != expected)
                throw std::runtime_error("historical Golden Idol public options disagree with frozen relic contract");
        }
        const int originalPhase = state.gc.info.phase;
        state.gc.info.phase = idol ? 1 : 0;
        std::vector<int> actual;
        for (const auto &action : sts::search::GameAction::getAllActionsInState(state.gc))
            actual.push_back(action.getIdx1());
        if (actual != expected)
            throw std::runtime_error("Golden Idol version adaptation failed exact option parity");
        auto expectedSnapshot = row.at("snapshot");
        expectedSnapshot["game"]["info"]["phase"] = state.gc.info.phase;
        if (snapshotJson(state.gc, state.path, state.policy) != expectedSnapshot)
            throw std::runtime_error("Golden Idol adapter changed fields beyond phase");
        if (!row.contains("snapshotImportHistory")) row["snapshotImportHistory"] = Json::array();
        row.at("snapshotImportHistory").push_back({
            {"rule", "frozen334_golden_idol_relic_to_current_phase_v1"},
            {"context", context}, {"originalPhase", originalPhase},
            {"adaptedPhase", state.gc.info.phase}, {"changed", originalPhase != state.gc.info.phase},
            {"historicalOptionIds", expected},
            {"originalPublicOptionsPresent", row.contains("screenContents")}});
    }
    return state;
}
inline void markCurrentEnvelope(Json &row) {
    // Retain historical custody while preventing a second normalization after a
    // current action, resource edit or observation has produced this snapshot.
    if (row.contains("snapshotSemantics") && row.at("snapshotSemantics").at("domain") == "frozen-334")
        row["snapshotOrigin"] = row.at("snapshotSemantics");
    row["snapshotSemantics"] = currentImportContext();
}
} // namespace one_combat::screen_leaf
