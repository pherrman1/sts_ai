// Bounded research diagnostic: one frozen public Champ decision, two actions.
// This executable is not a gameplay backend and never reads a private snapshot.
#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <ctime>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <memory>
#include <sstream>
#include <stdexcept>
#include <string>

#include <openssl/evp.h>
#include <nlohmann/json.hpp>
#include "sim/search/SearchRng.h"
#include "sim/search/SilverSemanticAction.h"
#include "sim/search/SilverWireJson.h"
#include "sim/search/SilverWireState.h"

namespace {
using J = nlohmann::json;
using sts::BattleContext;
using sts::Outcome;
namespace search = sts::search;
constexpr int simulations = 10000;
constexpr int maximumDecisions = 1000;
constexpr const char *futureDomain = "champ-d13-public-pair-v1-environment";

void require(bool ok, const std::string &why) {
    if (!ok) throw std::runtime_error(why);
}

std::string read(const std::string &path) {
    std::ifstream in(path, std::ios::binary);
    require(bool(in), "cannot read " + path);
    return {std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>()};
}

std::string sha256(const std::string &text) {
    unsigned char digest[EVP_MAX_MD_SIZE]{};
    unsigned int size = 0;
    require(EVP_Digest(text.data(), text.size(), digest, &size, EVP_sha256(), nullptr) == 1
                && size == 32, "SHA256 failure");
    std::ostringstream out;
    out << std::hex << std::setfill('0');
    for (unsigned int i = 0; i < size; ++i) out << std::setw(2) << unsigned(digest[i]);
    return out.str();
}

int parseK(const std::string &text) {
    require(!text.empty() && text.size() <= 2
        && std::all_of(text.begin(), text.end(), [](char c) { return c >= '0' && c <= '9'; }),
        "future index must be decimal 0..63");
    return std::stoi(text);
}

void emit(const J &row) {
    std::cout << row.dump() << '\n' << std::flush;
    require(bool(std::cout), "output write failure");
}

void checkPublicWire(const silver_bridge::BattleStateWire &wire) {
    require(wire.valid && wire.version == silver_bridge::BattleStateWire::kVersion,
            "invalid public wire");
    require(wire.act == 2 && wire.ascension == 0 && wire.floorNum == 33
        && wire.encounter == int(sts::MonsterEncounter::CHAMP), "wrong combat context");
    require(!wire.intentsHidden && !wire.fullDrawOrderObserved
        && wire.drawPile.valid && !wire.drawPile.fullOrderObserved,
        "only abstract draw / visible intent states are supported");
    if (wire.inputState == int(sts::InputState::CARD_SELECT)) {
        require(wire.pendingActionQueueObserved && wire.pendingCardQueueObserved,
                "selection lacks exact supported public queue tail");
    }
}

silver_bridge::BattleStateWire exportPublic(const BattleContext &world,
                                           const search::SilverSearchContext &context) {
    require(!world.cards.drawPile.isConcrete() && !world.intentsHidden,
            "public lifecycle lost abstract draw / visible intent contract");
    require(world.inputState == sts::InputState::PLAYER_NORMAL
        || world.inputState == sts::InputState::CARD_SELECT,
        "continuation did not settle at a supported decision");
    if (world.inputState == sts::InputState::PLAYER_NORMAL) {
        require(world.actionQueue.size == 0 && world.cardQueue.size == 0,
                "normal root has an unobserved pending queue");
    }
    auto wire = search::wireFromSearchState(world, context);
    wire.isolatedSearchSeed = 0;  // Never export environment identity/RNG to search.
    checkPublicWire(wire);
    return wire;
}

BattleContext plannerRoot(const BattleContext &world,
                          const search::SilverSearchContext &context) {
    const auto wire = exportPublic(world, context);
    auto root = search::battleContextFromWire(wire);
    require(root.seed == 0 && !root.cards.drawPile.isConcrete(), "planner seed/draw contract");
    // Complete supported wire equality includes known top/bottom and queue tails.
    // No reordering, field deletion, or fallback reconstruction is accepted here.
    const J before = silver_bridge::battleStateWireEnvelope(wire);
    const J after = silver_bridge::battleStateWireEnvelope(exportPublic(root, context));
    require(before == after, "public export/hydration roundtrip changed state");
    return root;
}

J endpoint(const BattleContext &world, const search::SilverSearchContext &context) {
    auto wire = search::wireFromSearchState(world, context);
    wire.isolatedSearchSeed = 0;
    return silver_bridge::battleStateWireEnvelope(wire);
}

void execute(BattleContext &world, const silver_bridge::SemanticAction &semantic) {
    const auto resolved = search::resolveSilverSemanticAction(world, semantic);
    require(resolved.ok, "semantic action rejected: " + resolved.error);
    resolved.action.execute(world);
}

struct Frozen {
    J specification, row;
    std::string specSha, rowSha;
    silver_bridge::BattleStateWire wire;
    search::SilverSearchContext context;
    silver_bridge::SemanticAction actions[2];
    std::string fingerprints[2];
};

Frozen loadFrozen(const std::string &path) {
    Frozen f;
    const auto text = read(path);
    f.specSha = sha256(text); f.specification = J::parse(text);
    const auto &s = f.specification;
    require(s.at("schema") == "champ_d13_public_pair_v1", "wrong specification");
    require(s.at("continuation_simulations") == simulations
        && s.at("maximum_decisions") == maximumDecisions && s.at("planner_seed") == 0
        && s.at("future_domain") == futureDomain, "unsupported continuation contract");
    const auto raw = read(s.at("public_row_path").get<std::string>());
    f.rowSha = sha256(raw); require(f.rowSha == s.at("public_row_sha256"), "public row changed");
    f.row = J::parse(raw);
    require(f.row.at("schema") == "silver_public_decision_v1" && f.row.at("capture_valid") == true
        && f.row.at("seed") == "610081002" && f.row.at("floor") == 33
        && f.row.at("decision") == 13 && f.row.at("turn") == 1, "wrong frozen decision");
    f.wire = silver_bridge::battleStateWireFromEnvelope(f.row.at("public_wire"));
    checkPublicWire(f.wire);
    require(f.wire.isolatedSearchSeed == 0 && f.wire.player.curHp == 75
        && f.wire.player.block == 3 && f.wire.player.energy == 1,
        "unexpected D13 public root");
    f.context = search::searchContextFromWire(f.wire);
    require(f.context.act == 2 && f.context.actBossRoom && !f.context.finalBossBinary,
            "Act2 boss evaluation context missing");
    f.fingerprints[0] = s.at("baseline_fingerprint").get<std::string>();
    f.fingerprints[1] = s.at("alternative_fingerprint").get<std::string>();
    require(f.fingerprints[0] == f.row.at("chosen_fingerprint")
        && f.fingerprints[0] != f.fingerprints[1], "baseline/alternative identity");
    for (int arm = 0; arm < 2; ++arm) {
        int matches = 0;
        for (const auto &a : f.row.at("legal_actions")) {
            if (a.at("fingerprint") != f.fingerprints[arm]) continue;
            f.actions[arm] = a.at("action").get<silver_bridge::SemanticAction>();
            ++matches;
        }
        require(matches == 1 && search::semanticFingerprint(f.actions[arm]) == f.fingerprints[arm],
                "frozen semantic alternative absent/ambiguous");
    }
    require(f.actions[0].type == silver_bridge::SemanticActionType::END_TURN
        && f.actions[1].type == silver_bridge::SemanticActionType::CARD
        && f.actions[1].card.id == int(sts::CardId::SHRUG_IT_OFF)
        && f.actions[1].card.uniqueId == 14 && !f.actions[1].card.upgraded,
        "only END versus unupgraded Shrug#14 is authorized");
    return f;
}

BattleContext initialWorld(const Frozen &f, int k) {
    auto wire = f.wire;
    const auto digest = sha256(std::string(futureDomain) + ":" + f.rowSha + ":" + std::to_string(k));
    wire.isolatedSearchSeed = std::stoull(digest.substr(0, 16), nullptr, 16);
    auto world = search::battleContextFromWire(wire);
    require(!world.cards.drawPile.isConcrete(), "world must sample only public unknown region");
    auto expected = f.wire;
    expected.isolatedSearchSeed = 0;
    // Observer generation is trace metadata, not an engine-state field.
    expected.observedGeneration = 0;
    require(endpoint(world, f.context) == silver_bridge::battleStateWireEnvelope(expected),
            "initial captured public state did not hydrate exactly");
    (void)plannerRoot(world, f.context);
    return world;
}

void contractCheck(const Frozen &f) {
    const auto initial = initialWorld(f, 0);
    const J publicInitial = endpoint(initial, f.context);
    const auto initialRng = search::captureSearchRng(initial);
    // Different private future streams must produce the identical planner view.
    const auto other = initialWorld(f, 1);
    require(endpoint(plannerRoot(initial, f.context), f.context)
        == endpoint(plannerRoot(other, f.context), f.context), "environment leaked into planner");
    for (int arm = 0; arm < 2; ++arm) {
        auto a = initial, b = initial;
        execute(a, f.actions[arm]); execute(b, f.actions[arm]);
        require(endpoint(a, f.context) == endpoint(b, f.context)
            && search::captureSearchRng(a) == search::captureSearchRng(b), "same action not deterministic");
        require(endpoint(initial, f.context) == publicInitial
            && search::captureSearchRng(initial) == initialRng, "paired source copy mutated");
        require(a.outcome == Outcome::UNDECIDED, "unexpected one-step terminal");
        (void)plannerRoot(a, f.context);
        if (arm == 0) require(a.player.curHp == 69 && a.turn == 2, "baseline immediate loss changed");
        else require(a.player.curHp == 75 && a.player.block == 11 && a.player.energy == 0
            && a.turn == 1, "Shrug immediate block/draw changed");
    }
}

J branch(const Frozen &f, const BattleContext &initial, int arm, int k) {
    const auto clockStart = std::chrono::steady_clock::now();
    const auto cpuStart = std::clock();
    auto world = initial;
    int decisions = 0;
    std::uint64_t totalSimulations = 0;
    std::array<std::int64_t, search::SilverTreeProfile::COUNT> searchEndpoints{};
    J trace = J::array();
    J result = {{"kind", "branch"}, {"k", k}, {"arm", arm == 0 ? "END" : "SHRUG"},
        {"environment_seed", std::to_string(initial.seed)}, {"forced_fingerprint", f.fingerprints[arm]},
        {"valid", false}, {"combat_won", nullptr}};
    try {
        execute(world, f.actions[arm]); ++decisions;
        trace.push_back(f.fingerprints[arm]);
        while (world.outcome == Outcome::UNDECIDED) {
            require(decisions < maximumDecisions, "nonterminal decision cap; invalid, not a loss");
            const auto beforeRng = search::captureSearchRng(world);
            const auto beforePublic = endpoint(world, f.context);
            auto root = plannerRoot(world, f.context);
            search::SilverSearcher planner(root, f.context);
            search::SilverTreeProfile profile;
            planner.profile = &profile;
            planner.search(simulations);
            planner.profile = nullptr;
            totalSimulations += profile.completed;
            for (int kind = 0; kind < search::SilverTreeProfile::COUNT; ++kind) {
                for (const auto &[depth, count] : profile.endpoints[kind].tree) {
                    (void)depth;
                    searchEndpoints[kind] += count;
                }
            }
            require(profile.completed == simulations && planner.rootNode().simulationCount == simulations,
                    "fresh exact continuation budget mismatch");
            require(searchEndpoints[search::SilverTreeProfile::TURN_LIMIT] == 0
                && searchEndpoints[search::SilverTreeProfile::ENGINE_STOP] == 0
                && searchEndpoints[search::SilverTreeProfile::NONTERMINAL] == 0,
                "search has unresolved/engine-stop endpoints; invalid, not losses");
            const auto semantic = search::semanticFromSearchAction(planner.rootSearchState(), planner.bestAction());
            require(search::captureSearchRng(world) == beforeRng && endpoint(world, f.context) == beforePublic,
                    "planning mutated environment state or RNG");
            trace.push_back(search::semanticFingerprint(semantic));
            execute(world, semantic); ++decisions;
        }
        require(world.turn <= 500 && world.loopCount <= 1000000 && world.monsters.monstersAlive >= 0,
                "actual world exceeded engine health guard");
        require(world.outcome == Outcome::PLAYER_VICTORY
            || (world.outcome == Outcome::PLAYER_LOSS && world.player.curHp <= 0),
            "non-death/engine-stop outcome unsupported; invalid, not a loss");
        result["valid"] = true;
        result["combat_won"] = world.outcome == Outcome::PLAYER_VICTORY;
    } catch (const std::exception &e) {
        result["error"] = e.what();
    }
    result["decisions"] = decisions;
    result["continuation_simulations"] = totalSimulations;
    result["search_endpoints"] = J::object();
    for (int kind = 0; kind < search::SilverTreeProfile::COUNT; ++kind)
        result["search_endpoints"][search::SilverTreeProfile::names[kind]] = searchEndpoints[kind];
    result["terminal_hp"] = world.player.curHp;
    result["terminal_potion_count"] = world.potionCount;
    result["terminal_turn"] = world.turn;
    result["terminal_outcome"] = int(world.outcome);
    result["endpoint_sha256"] = sha256(endpoint(world, f.context).dump());
    result["action_fingerprints"] = std::move(trace);
    result["cpu_seconds"] = double(std::clock() - cpuStart) / CLOCKS_PER_SEC;
    result["wall_seconds"] = std::chrono::duration<double>(std::chrono::steady_clock::now() - clockStart).count();
    return result;
}
} // namespace

int main(int argc, char **argv) {
    try {
        require(argc == 3 || argc == 4, "usage: silver_public_pair_probe SPEC.json check|canary|evaluation [K]");
        const std::string mode = argv[2];
        require((mode == "check" && argc == 3) || ((mode == "canary" || mode == "evaluation") && argc == 4),
                "invalid mode/arguments");
        const auto f = loadFrozen(argv[1]);
        const char *source = std::getenv("STS_EXECUTABLE_GIT_SHA");
        require(source && std::string(source).size() == 40
            && std::all_of(source, source + 40, [](char c) { return (c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'); }),
            "explicit producer source SHA is required");
        emit({{"kind", "header"}, {"schema", "champ_d13_public_pair_result_v1"}, {"mode", mode},
            {"specification_sha256", f.specSha}, {"public_row_sha256", f.rowSha}, {"source_sha", source},
            {"binary_sha256", sha256(read("/proc/self/exe"))}, {"act", 2}, {"boss_context", true},
            {"continuation_policy", "fresh_exact_10000_public_seed_0"}, {"models", J::array()},
            {"maximum_decisions", maximumDecisions},
            {"forced_fingerprints", J::array({f.fingerprints[0], f.fingerprints[1]})}});
        if (mode == "check") {
            contractCheck(f);
            emit({{"kind", "check"}, {"status", "PASS"}, {"search_simulations", 0},
                {"checks", {"paired source immutability", "one-step repeat determinism", "environment/planner separation",
                    "public wire roundtrip", "END immediate HP loss", "Shrug immediate block/draw"}}});
            return 0;
        }
        const int k = parseK(argv[3]);
        require((mode == "canary" && k <= 1) || (mode == "evaluation" && k >= 2 && k <= 63),
                "unallocated future index for stage");
        const auto initial = initialWorld(f, k);
        const auto original = endpoint(initial, f.context);
        const auto rng = search::captureSearchRng(initial);
        bool valid = true;
        for (int arm = 0; arm < 2; ++arm) {
            auto result = branch(f, initial, arm, k);
            require(endpoint(initial, f.context) == original && search::captureSearchRng(initial) == rng,
                    "branch changed immutable paired root");
            valid = result.at("valid").get<bool>() && valid;
            emit(result);
        }
        emit({{"kind", "pair"}, {"k", k}, {"valid", valid}, {"branches", 2}});
        return valid ? 0 : 1;
    } catch (const std::exception &e) {
        emit({{"kind", "error"}, {"valid", false}, {"error", e.what()}});
        return 1;
    }
}
