#include "screen_leaf_probes.h"
#include "screen_leaf_s0.h"
#include "screen_leaf_snapshot.h"
#include "screen_leaf_continuations.h"
#include "screen_leaf_import.h"
#include <openssl/sha.h>
#include <algorithm>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <limits>
#include <map>
#include <set>
#include <vector>

namespace one_combat {
namespace {
using Json = nlohmann::json;
using screen_leaf::Snapshot;

void require(bool ok, const std::string &message) {
    if (!ok) throw std::runtime_error("screen leaf probes: " + message);
}

bool validationSource(std::uint64_t seed) {
    if (seed < 13001000 || seed > 13002023) return false;
    const auto domain = "vwin-refresh-334-v1:" + std::to_string(seed);
    unsigned char bytes[SHA256_DIGEST_LENGTH];
    SHA256(reinterpret_cast<const unsigned char *>(domain.data()), domain.size(), bytes);
    const std::uint32_t prefix = (std::uint32_t(bytes[0]) << 24) | (std::uint32_t(bytes[1]) << 16)
        | (std::uint32_t(bytes[2]) << 8) | std::uint32_t(bytes[3]);
    const double fraction = double(prefix) / 4294967296.;
    return fraction >= .70 && fraction < .85;
}

struct PolicyRestore {
    OocPolicyThreadState policy = captureOocPolicyThreadState();
    const PathHistory *path = t_curPath;
    ~PolicyRestore() { restoreOocPolicyThreadState(policy); t_curPath = path; }
};

struct OutputFiles {
    std::map<std::string, std::FILE *> handles;
    ~OutputFiles() { for (auto &[name, f] : handles) std::fclose(f); }
    void write(const std::string &name, const Json &row) {
        auto found = handles.find(name);
        if (found == handles.end()) {
            auto *file = std::fopen(name.c_str(), "wx");
            require(file != nullptr, "output exists or cannot be created: " + name);
            found = handles.emplace(name, file).first;
        }
        const auto encoded = row.dump() + "\n";
        require(std::fwrite(encoded.data(), 1, encoded.size(), found->second) == encoded.size()
            && !std::fflush(found->second), "output write failed: " + name);
    }
};

Snapshot restore(Json &row) {
    const auto seed = row.at("sourceSeed").get<std::uint64_t>();
    require(validationSource(seed), "only frozen source-hash VALIDATION permitted");
    auto state = screen_leaf::importEnvelope(row);
    require(state.gc.seed == seed, "source and snapshot seed differ");
    require(richRow(state.gc, state.path) == row.at("features").get<std::string>(), "input rich-feature parity");
    return state;
}

Json publicProjection(Json row, const Snapshot &state) {
    restoreOocPolicyThreadState(state.policy);
    t_curPath = &state.path;
    row["features"] = richRow(state.gc, state.path);
    row["snapshot"] = encodeScreenLeafSnapshot(state.gc, state.path);
    screen_leaf::markCurrentEnvelope(row);
    row["act"] = state.gc.act;
    row["floor"] = state.gc.floorNum;
    row["screenState"] = static_cast<int>(state.gc.screenState);
    row.erase("screenContents"); row.erase("candidateKeys");
    if (state.gc.outcome != sts::GameOutcome::UNDECIDED) {
        row["projectionStatus"] = "TERMINAL";
        row["terminalValue"] = state.gc.outcome == sts::GameOutcome::PLAYER_VICTORY ? 1 : 0;
    } else if (state.gc.screenState == sts::ScreenState::MAP_SCREEN) {
        row["projectionStatus"] = "MAP";
    } else if (state.gc.screenState == sts::ScreenState::BATTLE) {
        row["projectionStatus"] = "EXCLUDED_BATTLE";
    } else {
        try {
            const auto contract = screenLeafPublicContract(state.gc);
            row["screenContents"] = contract.at("screenContents");
            row["candidateKeys"] = contract.at("candidateKeys");
            row["projectionStatus"] = "SUPPORTED_DECISION";
        } catch (const std::runtime_error &error) {
            require(std::string(error.what()).find("incomplete restored DECISION:") == 0, error.what());
            row["projectionStatus"] = "EXCLUDED_UNSUPPORTED";
            row["projectionError"] = error.what();
        }
    }
    // Projection is observation only: no hidden state, path or policy mutation.
    require(row.at("snapshot") == screen_leaf::snapshotJson(state.gc, state.path, state.policy),
            "public projection changed policy state");
    return row;
}

Json fixedOffers(Json contents) {
    // Legal actions can change with resources, while public offers stay fixed.
    contents.erase("availableOptions");
    if (contents.at("screen") == "shop") {
        contents.erase("ownedPotions");
        contents.erase("policyBuyableRelics");
    }
    return contents;
}

struct Variant {
    std::string name;
    Snapshot state;
    Json metadata;
};

std::vector<Variant> variants(const Snapshot &original) {
    const auto &gc = original.gc;
    require(gc.curHp >= 1 && gc.maxHp >= gc.curHp && gc.maxHp < std::numeric_limits<int>::max(), "invalid living HP");
    require(gc.gold >= 0 && gc.gold <= std::numeric_limits<int>::max() - 25, "invalid gold");
    require(gc.potionCapacity >= 0 && gc.potionCapacity <= int(gc.potions.size()), "invalid potion capacity");
    int held = 0;
    std::map<int, int> distinct;
    for (int slot = 0; slot < gc.potionCapacity; ++slot) {
        const auto potion = gc.potions[slot];
        if (potion == sts::Potion::EMPTY_POTION_SLOT) continue;
        require(potion != sts::Potion::INVALID, "invalid active potion slot");
        ++held; distinct.emplace(int(potion), slot);
    }
    require(held == gc.potionCount, "held potion count mismatch");
    std::vector<Variant> result;
    auto add = [&](const std::string &name, Json metadata) -> Snapshot & {
        result.push_back({name, original, std::move(metadata)});
        return result.back().state;
    };
    add("identity", {{"family", "identity"}, {"actualDelta", 0}});
    const int hpLow = std::max(1, gc.curHp - 5), hpHigh = int(std::min<long long>(gc.maxHp, gc.curHp + 5LL));
    for (const auto &[name, hp] : std::vector<std::pair<std::string, int>>{{"hp_minus", hpLow}, {"hp_plus", hpHigh}}) {
        auto &state = add(name, {{"family", "curHP"}, {"nominalStep", 5}, {"actualDelta", hp - gc.curHp},
            {"pairDenominator", 10}, {"actualPairDistance", hpHigh - hpLow}, {"clipped", std::abs(hp-gc.curHp) != 5}});
        state.gc.curHp = hp;
    }
    const int goldLow = std::max(0, gc.gold - 25), goldHigh = gc.gold + 25;
    for (const auto &[name, gold] : std::vector<std::pair<std::string, int>>{{"gold_minus", goldLow}, {"gold_plus", goldHigh}}) {
        auto &state = add(name, {{"family", "gold"}, {"nominalStep", 25}, {"actualDelta", gold - gc.gold},
            {"pairDenominator", goldHigh - goldLow}, {"actualPairDistance", goldHigh - goldLow},
            {"clipped", std::abs(gold-gc.gold) != 25}});
        state.gc.gold = gold;
    }
    auto &feed = add("feed_like", {{"family", "Feed_like"}, {"curHpDelta", 1}, {"maxHpDelta", 1}, {"pairDenominator", 1}});
    ++feed.gc.curHp; ++feed.gc.maxHp;
    ++add("max_only", {{"family", "maxHP"}, {"curHpDelta", 0}, {"maxHpDelta", 1}, {"pairDenominator", 1}}).gc.maxHp;
    for (const auto &[potion, slot] : distinct) {
        auto &state = add("remove_potion_" + std::to_string(potion), {{"family", "held_potion"},
            {"potionId", potion}, {"removedSlot", slot}, {"actualDelta", -1}, {"pairDenominator", 1}});
        state.gc.potions[slot] = sts::Potion::EMPTY_POTION_SLOT;
        --state.gc.potionCount;
    }
    return result;
}

void verifyMutation(const Snapshot &original, const Variant &variant) {
    auto expected = screen_leaf::snapshotJson(original.gc, original.path, original.policy);
    auto actual = screen_leaf::snapshotJson(variant.state.gc, variant.state.path, variant.state.policy);
    for (const auto *field : {"curHp", "maxHp", "gold", "potions", "potionCount"})
        expected["game"][field] = actual.at("game").at(field);
    require(expected == actual, "non-resource state changed");
}
}

int screenLeafProbes(const std::string &input, const std::string &outputDirectory, unsigned limit) {
    require(limit > 0, "positive input limit required");
    std::ifstream in(input); require(bool(in), "cannot open input");
    require(!std::filesystem::exists(outputDirectory), "output directory already exists");
    require(std::filesystem::create_directory(outputDirectory), "cannot create fresh output directory");
    PolicyRestore restorePolicy;
    OutputFiles files;
    std::set<std::string> seen;
    Json counts = Json::object();
    unsigned rows = 0;
    std::string line;
    while (rows < limit && std::getline(in, line)) {
        auto row = Json::parse(line);
        const auto identity = Json::array({row.at("sourceSeed"), row.at("branchId"), row.at("rowIdx")}).dump();
        require(row.at("rowIdx").get<int>() >= 0 && seen.insert(identity).second, "duplicate/invalid DECISION identity");
        const auto original = restore(row);
        const auto baseline = publicProjection(row, original);
        require(baseline.at("projectionStatus") == "SUPPORTED_DECISION", "probe input is not supported DECISION");
        const std::set<std::string> allowed{"boss_relic", "rest", "shop", "treasure"};
        require(allowed.count(baseline.at("screenContents").at("screen").get<std::string>()), "screen outside provisional probe mask");
        for (const auto &variant : variants(original)) {
            verifyMutation(original, variant);
            auto variantRow = row;
            // A factual next-MAP link is not a counterfactual transition label.
            variantRow.erase("calibrationLink");
            auto projected = publicProjection(std::move(variantRow), variant.state);
            require(projected.at("projectionStatus") == "SUPPORTED_DECISION", "resource probe became unsupported");
            require(fixedOffers(projected.at("screenContents")) == fixedOffers(baseline.at("screenContents")), "resource probe changed visible offers/prices");
            projected["probe"] = variant.metadata;
            projected["probe"]["name"] = variant.name;
            projected["probe"]["schema"] = "screen-leaf-resource-probe-v1";
            projected["probe"]["identityPreservedForS0Rng"] = true;
            files.write((std::filesystem::path(outputDirectory) / (variant.name + ".jsonl")).string(), projected);
            counts[variant.name] = counts.value(variant.name, 0) + 1;
        }
        ++rows;
    }
    require(rows > 0, "empty probe input");
    files.write((std::filesystem::path(outputDirectory) / "manifest.jsonl").string(),
        {{"schema", "screen-leaf-resource-probe-export-v1"}, {"inputRows", rows}, {"variantRows", counts},
         {"split", "VALIDATION"}, {"predictionsComputed", false}, {"identityRngCoupling", "unchanged sourceSeed/branchId/rowIdx"}});
    return 0;
}

int screenLeafProject(const std::string &input, const std::string &output, unsigned limit) {
    require(limit > 0, "positive input limit required");
    std::ifstream in(input); require(bool(in), "cannot open input");
    PolicyRestore restorePolicy;
    OutputFiles files;
    unsigned count = 0; std::string line;
    while (count < limit && std::getline(in, line)) {
        auto row = Json::parse(line);
        if (row.contains("forcedPostAction")) {
            require(validationSource(row.at("sourceSeed").get<std::uint64_t>()), "only VALIDATION post-action inputs permitted");
            if (row.at("forcedPostAction").is_null()) {
                files.write(output, {{"sourceSeed", row.at("sourceSeed")}, {"branchId", row.at("branchId")},
                    {"projectionStatus", "EXCLUDED_NO_FORCED_POST_ACTION"}});
                ++count; continue;
            }
            auto post = row.at("forcedPostAction");
            require(post.at("branchId") == row.at("branchId"), "post-action branch mismatch");
            post["sourceSeed"] = row.at("sourceSeed"); row = std::move(post);
        }
        const auto state = restore(row);
        files.write(output, publicProjection(row, state));
        ++count;
    }
    require(count > 0, "empty projection input");
    return 0;
}

int screenLeafProbesSelfTest() {
    PolicyRestore restorePolicy;
    Snapshot base;
    base.gc.info.neowRewards = {};
    base.gc.seed = 13001025; base.gc.cc = sts::CharacterClass::IRONCLAD;
    base.gc.curHp = 2; base.gc.maxHp = 4; base.gc.gold = 9;
    base.gc.potionCapacity = 3; base.gc.potionCount = 3;
    base.gc.potions = {sts::Potion::FIRE_POTION, sts::Potion::FIRE_POTION, sts::Potion::BLOCK_POTION,
                      sts::Potion::EMPTY_POTION_SLOT, sts::Potion::EMPTY_POTION_SLOT};
    base.gc.screenState = sts::ScreenState::REST_ROOM;
    base.gc.map = std::make_shared<sts::Map>();
    const auto result = variants(base);
    require(result.size() == 9, "distinct potion variant count");
    for (const auto &variant : result) verifyMutation(base, variant);
    require(result[1].state.gc.curHp == 1 && result[2].state.gc.curHp == 4, "HP clipping");
    require(result[1].metadata.at("pairDenominator") == 10 && result[1].metadata.at("actualPairDistance") == 3, "HP denominator");
    require(result[3].state.gc.gold == 0 && result[4].state.gc.gold == 34
        && result[3].metadata.at("pairDenominator") == 34, "gold actual-distance denominator");
    require(result[5].state.gc.curHp == 3 && result[5].state.gc.maxHp == 5
        && result[6].state.gc.curHp == 2 && result[6].state.gc.maxHp == 5, "max HP probes");
    for (std::size_t i = 7; i < result.size(); ++i) require(result[i].state.gc.potionCount == 2, "potion removal count");
    require(base.gc.potionCount == 3 && base.gc.potions[0] == sts::Potion::FIRE_POTION, "original state mutated");
    require(validationSource(13001025) && !validationSource(13001000), "source split guard");
    // Exercise actual public enumeration: only resources and derived legal
    // actions change when a previously unaffordable potion becomes affordable.
    base.gc.screenState = sts::ScreenState::SHOP_ROOM;
    base.gc.curRoom = sts::Room::SHOP;
    for (auto &price : base.gc.info.shop.prices) price = -1;
    base.gc.info.shop.removeCost = -1;
    base.gc.info.shop.potions[0] = sts::Potion::FIRE_POTION;
    base.gc.info.shop.potionPrice(0) = 10;
    Json row = {{"sourceSeed", base.gc.seed}, {"branchId", "synthetic-fixture"}, {"rowIdx", 7},
        {"decisionIdx", 3}, {"features", richRow(base.gc, base.path)},
        {"snapshot", screen_leaf::snapshotJson(base.gc, base.path, base.policy)},
        {"snapshotSemantics", screen_leaf::currentImportContext()}};
    const auto checked = restore(row);
    const auto baseline = publicProjection(row, checked);
    require(baseline.at("projectionStatus") == "SUPPORTED_DECISION", "synthetic shop projection");
    for (const auto &variant : variants(checked)) {
        const auto output = publicProjection(row, variant.state);
        require(output.at("sourceSeed") == row.at("sourceSeed") && output.at("branchId") == row.at("branchId")
            && output.at("rowIdx") == row.at("rowIdx"), "projection changed RNG identity");
        require(fixedOffers(output.at("screenContents")) == fixedOffers(baseline.at("screenContents")), "shop offers changed");
        if (variant.name == "gold_plus")
            require(output.at("candidateKeys") != baseline.at("candidateKeys"), "shop legal actions not recomputed");
    }
    auto projectedState = checked;
    projectedState.gc.screenState = sts::ScreenState::MAP_SCREEN;
    require(publicProjection(row, projectedState).at("projectionStatus") == "MAP", "MAP projection");
    projectedState.gc.screenState = sts::ScreenState::BATTLE;
    require(publicProjection(row, projectedState).at("projectionStatus") == "EXCLUDED_BATTLE", "battle projection");
    projectedState.gc.outcome = sts::GameOutcome::PLAYER_LOSS;
    const auto terminal = publicProjection(row, projectedState);
    require(terminal.at("projectionStatus") == "TERMINAL" && terminal.at("terminalValue") == 0, "terminal projection");
    // Constructed version-bound imports only: no GameContext seed constructor,
    // generation, hidden sampling, policy action or model evaluation occurs.
    const std::vector<std::string> producers{
        "1e93bd66cb5ef489028f1a06c22d5f12bd2ca935",
        "0665747164ca3914c229546ad13f4f26a3a4a23c"};
    auto historicalRow = [&](const std::string &producer, bool held, bool withOptions) {
        auto fixture = base;
        fixture.gc.screenState = sts::ScreenState::EVENT_SCREEN;
        fixture.gc.curEvent = sts::Event::GOLDEN_IDOL;
        fixture.gc.info.phase = 0;
        if (held) fixture.gc.relics.add({sts::RelicId::GOLDEN_IDOL, 0});
        Json envelope = {{"sourceSeed", fixture.gc.seed}, {"branchId", "constructed-golden-idol"},
            {"rowIdx", 0}, {"decisionIdx", 0}, {"features", richRow(fixture.gc, fixture.path)},
            {"snapshot", screen_leaf::snapshotJson(fixture.gc, fixture.path, fixture.policy)},
            {"snapshotSemantics", {{"schema", "screen-leaf-import-context-v1"},
                {"domain", "frozen-334"}, {"producerGitSha", producer},
                {"snapshotSchema", "screen-leaf-full-state-v1"}, {"sourceSeed", fixture.gc.seed},
                {"sourceManifestSha256", std::string(64, 'a')},
                {"inputArtifactSha256", std::string(64, 'b')}}}};
        if (withOptions) {
            // Manufacture the known original public contract with current
            // equivalent phase, retaining historical phase0 in the snapshot.
            fixture.gc.info.phase = held ? 1 : 0;
            const auto contract = screenLeafPublicContract(fixture.gc);
            envelope["screenContents"] = contract.at("screenContents");
            envelope["candidateKeys"] = contract.at("candidateKeys");
        }
        return envelope;
    };
    for (const auto &producer : producers) {
        for (bool held : {false, true}) {
            auto envelope = historicalRow(producer, held, true);
            const auto originalSnapshot = envelope.at("snapshot");
            const auto imported = screen_leaf::importEnvelope(envelope);
            auto expected = originalSnapshot;
            expected["game"]["info"]["phase"] = held ? 1 : 0;
            require(screen_leaf::snapshotJson(imported.gc, imported.path, imported.policy) == expected,
                    "historical adapter must change phase only");
            require(envelope.at("snapshot") == originalSnapshot, "historical input snapshot preserved");
            require(richRow(imported.gc, imported.path) == envelope.at("features"), "historical rich parity");
            const auto contract = screenLeafPublicContract(imported.gc);
            require(contract.at("screenContents") == envelope.at("screenContents") &&
                    contract.at("candidateKeys") == envelope.at("candidateKeys"), "historical exact public/candidate parity");
            const auto &history = envelope.at("snapshotImportHistory");
            require(history.size() == 1 && history[0].at("originalPhase") == 0 &&
                    history[0].at("adaptedPhase") == (held ? 1 : 0) &&
                    history[0].at("changed") == held &&
                    history[0].at("context") == envelope.at("snapshotSemantics"), "historical audit record");
            auto projected = publicProjection(envelope, imported);
            require(projected.at("snapshotSemantics") == screen_leaf::currentImportContext() &&
                    projected.at("snapshotOrigin") == envelope.at("snapshotSemantics"), "current export custody");
            const auto currentSnapshot = projected.at("snapshot");
            const auto repeated = screen_leaf::importEnvelope(projected);
            require(screen_leaf::snapshotJson(repeated.gc, repeated.path, repeated.policy) == currentSnapshot &&
                    projected.at("snapshotImportHistory") == history, "current re-import idempotent");
        }
        // A forced post-action snapshot has no stored public options. The
        // known-producer historical relic contract still determines the phase.
        auto forced = historicalRow(producer, true, false);
        const auto imported = screen_leaf::importEnvelope(forced);
        require(imported.gc.info.phase == 1 &&
                forced.at("snapshotImportHistory")[0].at("originalPublicOptionsPresent") == false,
                "historical forced post-action contract");
    }
    auto nativeHeldOffer = historicalRow(producers[0], true, false);
    nativeHeldOffer["snapshotSemantics"] = screen_leaf::currentImportContext();
    const auto nativeOriginal = nativeHeldOffer.at("snapshot");
    const auto nativeImported = screen_leaf::importEnvelope(nativeHeldOffer);
    require(nativeImported.gc.info.phase == 0 &&
            screen_leaf::snapshotJson(nativeImported.gc, nativeImported.path, nativeImported.policy) == nativeOriginal &&
            !nativeHeldOffer.contains("snapshotImportHistory"), "current held-idol offer must not become historical trap");
    auto rejectImport = [&](Json invalid, const std::string &why) {
        bool rejected = false;
        try { (void)screen_leaf::importEnvelope(invalid); }
        catch (const std::exception &) { rejected = true; }
        require(rejected, "invalid import accepted: " + why);
    };
    auto invalid = historicalRow(producers[0], true, true);
    invalid.erase("snapshotSemantics"); rejectImport(invalid, "untagged");
    invalid = historicalRow(producers[0], true, true);
    invalid["snapshotSemantics"]["producerGitSha"] = std::string(40, '0'); rejectImport(invalid, "unknown producer");
    invalid = historicalRow(producers[0], true, true);
    invalid["snapshotSemantics"]["sourceSeed"] = 13001026; rejectImport(invalid, "wrong source context");
    invalid = historicalRow(producers[0], true, true);
    invalid["sourceSeed"] = 13001026; invalid["snapshotSemantics"]["sourceSeed"] = 13001026;
    rejectImport(invalid, "wrong snapshot seed");
    invalid = historicalRow(producers[0], true, true);
    invalid["snapshotSemantics"]["inputArtifactSha256"] = "bad"; rejectImport(invalid, "bad artifact hash");
    invalid = historicalRow(producers[0], true, true);
    invalid["snapshotSemantics"]["sourceManifestSha256"] = std::string(64, 'G'); rejectImport(invalid, "bad manifest hash");
    invalid = historicalRow(producers[0], true, true);
    invalid["snapshotSemantics"]["snapshotSchema"] = "unknown"; rejectImport(invalid, "unknown snapshot schema");
    invalid = historicalRow(producers[0], true, true);
    invalid["screenContents"]["optionIds"] = Json::array({0, 1}); rejectImport(invalid, "contradictory public options");
    std::puts("screen leaf probes PASS: resource mutations, clipping, identity, public shop contract, projection statuses, split guard, version-bound Golden Idol imports");
    return 0;
}
}
