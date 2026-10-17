// Research tool (issue #605): exact Heart-leaf rows and rollout tails from the
// MAP root snapshots of STS_OOC_MCTS_ROOT_TRACE files. Replays saved states
// only; it starts no game from a seed.
#include "heart_leaf_tail.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <fstream>
#include <random>
#include <iostream>
#include <stdexcept>
#include <nlohmann/json.hpp>
#include "heart_leaf.h"
#include "ooc_mcts_adapter.h"
#include "screen_leaf_continuations.h"
#include "screen_leaf_snapshot.h"

namespace one_combat {
namespace {
nlohmann::json sparse(const std::vector<float> &raw) {
    nlohmann::json idx = nlohmann::json::array(), val = nlohmann::json::array();
    for (std::size_t i = 0; i < raw.size(); ++i) if (raw[i] != 0) { idx.push_back(i); val.push_back(raw[i]); }
    return {{"i", std::move(idx)}, {"v", std::move(val)}};
}
std::uint64_t rootSalt(std::uint64_t salt, std::uint64_t seed, std::uint64_t decision) {
    std::seed_seq seq{salt, seed, decision};
    std::array<std::uint32_t, 2> words{};
    seq.generate(words.begin(), words.end());
    return (std::uint64_t(words[0]) << 32) | words[1];
}
} // namespace

int heartLeafTailGen(std::uint64_t salt, unsigned repeats, const std::string &output,
                     const std::vector<std::string> &inputs) {
    CompactTreeNet anchor;
    if (fileSha256Hex(kHeartLeafAnchorPath) != kHeartLeafAnchorSha256
            || !anchor.load(kHeartLeafAnchorPath, richIdxMap(), "HeartLeaf row anchor"))
        throw std::runtime_error("heartleaftail: cannot load the pinned public X2-B");
    if (repeats && !liveOocMctsEnabled()) throw std::runtime_error("heartleaftail: tails require STS_OOC_MCTS=1");
    std::ofstream out(output, std::ios::app);
    if (!out) throw std::runtime_error("heartleaftail: cannot open " + output);
    std::uint64_t roots = 0, skipped = 0;
    for (const auto &input : inputs) {
        std::ifstream in(input);
        if (!in) throw std::runtime_error("heartleaftail: cannot open " + input);
        std::string line;
        while (std::getline(in, line)) {
            const auto row = nlohmann::json::parse(line);
            if (row.at("screen") != int(sts::ScreenState::MAP_SCREEN) || !row.contains("snapshot")
                    || row.at("snapshot").is_null()) { ++skipped; continue; }
            auto snap = screen_leaf::snapshotFromJson(row.at("snapshot"), screen_leaf::importContinuation);
            const auto seed = row.at("seed").get<std::uint64_t>();
            const auto decision = row.at("decisionIndex").get<std::uint64_t>();
            if (snap.gc.seed != seed) throw std::runtime_error("heartleaftail: snapshot seed differs");
            auto raw = richFeatureVec(snap.gc, snap.path);
            const double margin = anchor.margin(raw);
            appendHeartLeafExtras(raw, snap.gc, margin);
            nlohmann::json result = {{"schema", "heart-leaf-tail-v1"}, {"featureSchema", kHeartLeafFeatureSchema},
                {"seed", seed}, {"decisionIndex", decision}, {"act", snap.gc.act}, {"floor", snap.gc.floorNum},
                {"x2bMargin", margin}, {"root", sparse(raw)}, {"repeats", repeats}};
            if (repeats) {
                const auto streamSalt = rootSalt(salt, seed, decision);
                result["salt"] = streamSalt;
                result["tails"] = liveRootLeafTails(snap.gc, snap.path, snap.policy, streamSalt, repeats);
            }
            out << result.dump() << '\n';
            if (!out) throw std::runtime_error("heartleaftail: write failed");
            ++roots;
        }
    }
    std::cout << nlohmann::json{{"roots", roots}, {"skipped", skipped}, {"repeats", repeats}, {"salt", salt}}.dump() << '\n';
    return 0;
}
int heartLeafParity(const std::string &manifest, const std::string &input) {
    const HeartLeafModel model(manifest);
    std::ifstream in(input);
    if (!in) throw std::runtime_error("heartleafparity: cannot open " + input);
    const std::size_t width = heartLeafIdxMap().size();
    std::string line; std::uint64_t rows = 0; double maxError = 0;
    while (std::getline(in, line)) {
        const auto row = nlohmann::json::parse(line);
        std::vector<float> raw(width, 0.0f);
        const auto idx = row.at("i").get<std::vector<std::size_t>>();
        const auto val = row.at("v").get<std::vector<float>>();
        if (idx.size() != val.size()) throw std::runtime_error("heartleafparity: sparse row shape");
        for (std::size_t k = 0; k < idx.size(); ++k) raw.at(idx[k]) = val[k];
        maxError = std::max(maxError, std::abs(model.valueFromFeatures(raw) - row.at("value").get<double>()));
        ++rows;
    }
    const bool pass = rows > 0 && maxError < 1e-5;
    std::cout << nlohmann::json{{"rows", rows}, {"maxAbsError", maxError}, {"manifestSha256", model.manifestSha256()},
        {"pass", pass}}.dump() << '\n';
    return pass ? 0 : 1;
}
} // namespace one_combat
