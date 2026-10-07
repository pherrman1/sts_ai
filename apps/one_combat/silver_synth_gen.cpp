// Research-only corpus for a learned Silver root prior and leaf value
// (silversynthgen). Full runs play flat exact-budget native Silver; each
// recorded fight writes one JSONL row per searched root (its search state,
// root edge visits and Q), sampled rollout-start leaves with their rollout
// value and, on deterministically sampled roots, an independent second search
// and independent Silver continuation labels for every root action.
//
// Variant `natural` records the run's own fights. Variant `perturbed` records
// a detached copy of each fight's pre-combat state with a small random change
// (HP, a few cards, upgrades, a potion); the run itself continues through the
// unperturbed fight, so its trajectory equals the natural run of that seed.

#include "one_combat/driver_shared.h"

#include "constants/CardPools.h"
#include "constants/Potions.h"
#include "sim/search/SearchRng.h"
#include "sim/search/SilverSearcher.h"
#include "sim/search/SilverWireJson.h"
#include "sim/search/SilverWireState.h"

namespace {

constexpr int kContinuationSims = 2000;      // per continuation decision
constexpr int kContinuationReplicates = 2;   // per root action
constexpr std::uint64_t kSecondTeacherEvery = 4;
constexpr std::uint64_t kContinuationEvery = 8;
constexpr std::uint64_t kLeafStride = 2503;  // rollout starts between leaf samples
constexpr std::size_t kLeavesPerRoot = 4;

std::uint64_t mix(std::uint64_t x) {
    x += 0x9e3779b97f4a7c15ULL;
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
    x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
    return x ^ (x >> 31);
}

std::uint64_t key(std::uint64_t a, std::uint64_t b, std::uint64_t c = 0, std::uint64_t d = 0,
                  std::uint64_t e = 0) {
    return mix(mix(mix(mix(mix(a) ^ b) ^ c) ^ d) ^ e);
}

// Deterministic draws for the perturbation; never touches game RNG.
struct Draws {
    std::uint64_t state;
    std::uint64_t next() { return state = mix(state); }
    double unit() { return static_cast<double>(next() >> 11) * 0x1.0p-53; }
    int below(int n) { return static_cast<int>(next() % static_cast<std::uint64_t>(n)); }
};

nlohmann::json applyPerturbation(GameContext &gc, std::uint64_t seed) {
    Draws draws{seed};
    nlohmann::json applied = nlohmann::json::object();
    if (draws.unit() < 0.5) {
        const int hp = std::max(1, static_cast<int>(std::lround(gc.maxHp * (0.15 + 0.85 * draws.unit()))));
        applied["hp"] = {gc.curHp, hp};
        gc.curHp = std::min(hp, gc.maxHp);
    }
    const double addRoll = draws.unit();
    const int adds = addRoll < 0.4 ? 0 : addRoll < 0.8 ? 1 : 2;
    for (int i = 0; i < adds; ++i) {
        const double r = draws.unit();
        const auto rarity = r < 0.6 ? CardRarity::COMMON : r < 0.9 ? CardRarity::UNCOMMON : CardRarity::RARE;
        const int offset = RarityCardPool::getPoolOffset(CardColor::RED, rarity);
        const int size = RarityCardPool::getPoolSize(CardColor::RED, rarity);
        const Card card(RarityCardPool::cardBlob[offset + draws.below(size)], draws.unit() < 0.25 ? 1 : 0);
        gc.deck.obtain(gc, card);
        applied["added"].push_back(std::string(card.getName()) + (card.isUpgraded() ? "+" : ""));
    }
    if (draws.unit() < 0.3) {
        std::vector<int> removable;
        for (int i = 0; i < static_cast<int>(gc.deck.cards.size()); ++i)
            if (!gc.deck.isCardBottled(i) && gc.deck.cards[i].getType() != CardType::CURSE) removable.push_back(i);
        if (gc.deck.size() > 5 && !removable.empty()) {
            const int idx = removable[draws.below(static_cast<int>(removable.size()))];
            applied["removed"] = gc.deck.cards[idx].getName();
            gc.deck.remove(gc, idx);
        }
    }
    const int upgrades = draws.below(3);
    for (int i = 0; i < upgrades; ++i) {
        const auto idxs = gc.deck.getUpgradeableCardIdxs();
        if (idxs.empty()) break;
        const int idx = idxs[draws.below(static_cast<int>(idxs.size()))];
        applied["upgraded"].push_back(gc.deck.cards[idx].getName());
        gc.deck.upgrade(idx);
    }
    if (draws.unit() < 0.5 && gc.potionCount < gc.potionCapacity) {
        const Potion p = PotionPool::getPotionForClass(CharacterClass::IRONCLAD, draws.below(PotionPool::poolSize));
        gc.obtainPotion(p);
        applied["potion"] = getPotionName(p);
    }
    return applied;
}

nlohmann::json wireJson(const BattleContext &state, const search::SilverSearchContext &context) {
    return nlohmann::json(search::wireFromSearchState(state, context));
}

std::string fingerprint(const BattleContext &state, const search::Action &action) {
    try {
        return search::semanticFingerprint(search::semanticFromSearchAction(state, action));
    } catch (const std::exception &) {
        return {};
    }
}

nlohmann::json rootEdges(const search::SilverSearcher &searcher) {
    nlohmann::json edges = nlohmann::json::array();
    const auto &state = searcher.rootSearchState();
    for (const auto &edge : searcher.rootNode().edges) {
        const bool hasQ = edge.node && edge.node->simulationCount > 0;
        edges.push_back({{"bits", edge.action.bits}, {"semantic", fingerprint(state, edge.action)},
                         {"visits", edge.visitCount},
                         {"childSims", edge.node ? edge.node->simulationCount : 0},
                         {"q", hasQ ? nlohmann::json(edge.node->evaluationSum / edge.node->simulationCount)
                                    : nlohmann::json(nullptr)}});
    }
    return edges;
}

// A search root equal to `state` whose search randomness comes from `planner`.
BattleContext plannerRoot(const BattleContext &state, std::uint64_t planner) {
    BattleContext root = state;
    root.seed = planner;   // SilverSearcher seeds its rollouts from root.seed
    search::seedSearchRng(root, search::nativeSilverBattleSeed(root));
    return root;
}

// Silver plays `world` to the end of combat at kContinuationSims per decision.
// Each decision searches a fresh root whose randomness is independent of the
// world's, so the search never sees the world's sampled future. The value is
// `scorer`'s terminal evaluation (the recorded root's reference).
nlohmann::json continuation(BattleContext world, const search::SilverSearcher &scorer, std::uint64_t planner) {
    search::SilverSearcher searcher(plannerRoot(world, planner), scorer.searchContext());
    searcher.evalWeights = scorer.evalWeights;
    int decisions = 0;
    std::string error;
    while (world.outcome == Outcome::UNDECIDED) {
        if (decisions >= 400) { error = "decision_cap"; break; }
        if (world.inputState != InputState::PLAYER_NORMAL && world.inputState != InputState::CARD_SELECT) {
            error = "unsupported_input_state"; break;
        }
        if (decisions > 0) searcher.setRoot(plannerRoot(world, key(planner, decisions)));
        const auto actions = searcher.prepareRootActions();
        if (actions == 0) { error = "no_actions"; break; }
        if (actions > 1) searcher.search(kContinuationSims);
        const auto action = search::SilverSearcher::translateAction(
            searcher.bestAction(), searcher.rootSearchState(), world);
        if (!action.isValidAction(world)) { error = "invalid_action"; break; }
        action.execute(world);
        ++decisions;
    }
    const bool valid = error.empty() && world.outcome != Outcome::UNDECIDED;
    return {{"valid", valid}, {"error", error}, {"decisions", decisions},
            {"won", world.outcome == Outcome::PLAYER_VICTORY}, {"hp", world.player.curHp},
            {"value", valid ? nlohmann::json(scorer.scoreEndState(world)) : nlohmann::json(nullptr)}};
}

struct FightRecorder {
    std::uint64_t seed = 0;
    std::string variant;
    int fightIdx = 0;
    int sims = 0;
    std::ostringstream *out = nullptr;
    search::SilverLeafSamples leaves;
    long long roots = 0, leafRows = 0, secondTeachers = 0, continuationRoots = 0;

    void observe(const search::NativeSilverRootView &view) {
        const auto &searcher = view.searcher;
        const auto &state = searcher.rootSearchState();
        const auto &context = searcher.searchContext();
        const std::uint64_t rootKey = key(seed, fightIdx, view.decision);
        const bool multi = searcher.rootNode().edges.size() > 1;
        nlohmann::json row = {
            {"kind", "root"}, {"seed", seed}, {"variant", variant}, {"fight", fightIdx},
            {"decision", view.decision}, {"act", view.gc.act}, {"floor", view.gc.floorNum},
            {"room", roomStrings[static_cast<int>(view.gc.curRoom)]},
            {"encounter", monsterEncounterEnumNames[static_cast<int>(view.live.encounter)]},
            {"turn", view.live.turn}, {"hp", view.live.player.curHp}, {"maxHp", view.live.player.maxHp},
            {"inheritedVisits", view.inheritedVisits}, {"simulations", view.simulations},
            {"skipped", view.skipped}, {"chosen", fingerprint(view.live, view.chosen)},
            {"edges", rootEdges(searcher)}};
        try {
            row["wire"] = wireJson(state, context);
        } catch (const std::exception &e) {
            row["wire"] = nullptr;
            row["wireError"] = e.what();
        }
        if (multi && mix(rootKey) % kSecondTeacherEvery == 0) {
            // Independent second teacher: a fresh search with other randomness.
            search::SilverSearcher second(plannerRoot(state, key(rootKey, 2)), context);
            second.evalWeights = searcher.evalWeights;
            second.search(sims);
            row["second"] = rootEdges(second);
            ++secondTeachers;
        }
        if (multi && mix(rootKey ^ 0x5157) % kContinuationEvery == 0) {
            nlohmann::json labels = nlohmann::json::array();
            const auto &edges = searcher.rootNode().edges;
            for (int e = 0; e < static_cast<int>(edges.size()); ++e) {
                nlohmann::json reps = nlohmann::json::array();
                for (int rep = 0; rep < kContinuationReplicates; ++rep) {
                    BattleContext world = state;
                    search::seedSearchRng(world, key(rootKey, 3, e, rep));
                    edges[e].action.execute(world);
                    reps.push_back(continuation(world, searcher, key(rootKey, 4, e, rep)));
                }
                labels.push_back({{"bits", edges[e].action.bits}, {"reps", reps}});
            }
            row["continuations"] = labels;
            row["continuationSims"] = kContinuationSims;
            ++continuationRoots;
        }
        *out << row.dump() << '\n';
        ++roots;
        for (std::size_t i = 0; i < leaves.samples.size(); ++i) {
            const auto &leaf = leaves.samples[i];
            nlohmann::json leafRow = {
                {"kind", "leaf"}, {"seed", seed}, {"variant", variant}, {"fight", fightIdx},
                {"decision", view.decision}, {"sample", i}, {"pathNodes", leaf.pathNodes},
                {"rolloutValue", leaf.value}, {"inputState", static_cast<int>(leaf.start.inputState)}};
            try {
                leafRow["wire"] = wireJson(leaf.start, context);
            } catch (const std::exception &e) {
                leafRow["wire"] = nullptr;
                leafRow["wireError"] = e.what();
            }
            *out << leafRow.dump() << '\n';
            ++leafRows;
        }
        leaves.samples.clear();
    }
};

struct SeedResult {
    std::string rows;
    bool complete = false;
    long long roots = 0, leaves = 0, secondTeachers = 0, continuationRoots = 0, fights = 0, invalidFights = 0;
    std::string error;
};

SeedResult runSynthSeed(std::uint64_t seed, int sims, int asc, const WholeCombatTeacher &teacher,
                        bool perturbed) {
    SeedResult result;
    std::ostringstream out;
    FightRecorder recorder;
    recorder.seed = seed;
    recorder.variant = perturbed ? "perturbed" : "natural";
    recorder.sims = sims;
    recorder.out = &out;
    recorder.leaves.stride = kLeafStride;
    recorder.leaves.max = kLeavesPerRoot;
    struct HookScope {
        ~HookScope() {
            search::g_nativeSilverRootObserver = nullptr;
            search::g_nativeSilverLeafSamples = nullptr;
        }
    } hooks;
    auto record = [&](GameContext &gc, BattleContext &bc, search::ScumSearchAgent2 &agent,
                      const nlohmann::json &perturbation) {
        const int preHp = gc.curHp, preMaxHp = gc.maxHp;
        const long long rootsBefore = recorder.roots;
        recorder.leaves.samples.clear();
        search::g_nativeSilverLeafSamples = &recorder.leaves;
        search::g_nativeSilverRootObserver = [&](const search::NativeSilverRootView &view) { recorder.observe(view); };
        agent.playoutBattle(gc, bc);
        search::g_nativeSilverRootObserver = nullptr;
        search::g_nativeSilverLeafSamples = nullptr;
        const bool decided = bc.outcome != Outcome::UNDECIDED;
        const bool valid = trainingRunValid(decided);
        out << nlohmann::json{
            {"kind", "fight"}, {"seed", seed}, {"variant", recorder.variant}, {"fight", recorder.fightIdx},
            {"teacherId", teacher.id}, {"act", gc.act}, {"floor", gc.floorNum},
            {"room", roomStrings[static_cast<int>(gc.curRoom)]},
            {"encounter", monsterEncounterEnumNames[static_cast<int>(bc.encounter)]},
            {"preHp", preHp}, {"preMaxHp", preMaxHp}, {"perturbation", perturbation},
            {"valid", valid}, {"won", bc.outcome == Outcome::PLAYER_VICTORY},
            {"endHp", bc.player.curHp}, {"turns", bc.turn}, {"roots", recorder.roots - rootsBefore}}.dump() << '\n';
        ++result.fights;
        if (!valid) ++result.invalidFights;
        return valid;
    };
    try {
        trainingRunStart();
        GameContext gc(CharacterClass::IRONCLAD, seed, asc);
        search::ScumSearchAgent2 agent;
        agent.simulationCountBase = sims;
        agent.rng = std::default_random_engine(seed);
        PathHistory path;
        t_curPath = &path;
        using RT = search::GameAction::RewardsActionType;
        while (gc.outcome == GameOutcome::UNDECIDED) {
            path.update(gc);
            if (gc.screenState == ScreenState::BATTLE) {
                if (perturbed) {
                    GameContext shadow = detachedCounterfactualCopy(gc);
                    const auto applied = applyPerturbation(shadow, key(seed, recorder.fightIdx, 0x9e57));
                    search::ScumSearchAgent2 shadowAgent;
                    shadowAgent.simulationCountBase = sims;
                    shadowAgent.rng = std::default_random_engine(key(seed, recorder.fightIdx, 1));
                    BattleContext shadowBc;
                    record(shadow, shadowBc, shadowAgent, applied);
                    BattleContext bc;
                    agent.playoutBattle(gc, bc);
                    if (!trainingRunValid(bc.outcome != Outcome::UNDECIDED)) {
                        result.error = "natural_fight_invalid";
                        break;
                    }
                    bc.exitBattle(gc);
                } else {
                    BattleContext bc;
                    if (!record(gc, bc, agent, nullptr)) {
                        result.error = "fight_invalid";
                        break;
                    }
                    bc.exitBattle(gc);
                }
                ++recorder.fightIdx;
            } else if (gc.screenState == ScreenState::MAP_SCREEN && gc.curMapNodeY < 14) {
                search::GameAction(one_combat::chooseMapAction(gc)).execute(gc);
            } else if (gc.screenState == ScreenState::REWARDS) {
                auto &r = gc.info.rewardsContainer;
                if (r.goldRewardCount > 0) search::GameAction(RT::GOLD, 0).execute(gc);
                else if (r.relicCount > 0) search::GameAction(RT::RELIC, 0).execute(gc);
                else if (r.potionCount > 0 && gc.potionCount < gc.potionCapacity) search::GameAction(RT::POTION, 0).execute(gc);
                else if (g_collectKeys && r.emeraldKey) search::GameAction(RT::KEY, 0).execute(gc);
                else if (g_collectKeys && r.sapphireKey) search::GameAction(RT::KEY, 0).execute(gc);
                else if (r.cardRewardCount == 0) search::GameAction(RT::SKIP).execute(gc);
                else evalCardRewardPolicy(gc);
            } else {
                agent.stepOutOfCombatPolicy(gc);
            }
        }
        result.complete = result.error.empty();
    } catch (const std::exception &e) {
        result.error = e.what();
    }
    t_curPath = nullptr;
    result.rows = out.str();
    result.roots = recorder.roots;
    result.leaves = recorder.leafRows;
    result.secondTeachers = recorder.secondTeachers;
    result.continuationRoots = recorder.continuationRoots;
    return result;
}

}  // namespace

void silverSynthGen(int nSeeds, int sims, int asc, const std::string &outPrefix, long long seedOffset,
                    const std::string &teacherPath, const std::string &variant) {
    if (variant != "natural" && variant != "perturbed")
        throw std::runtime_error("silversynthgen: variant must be natural or perturbed");
    if (nSeeds < 1 || seedOffset < 0)
        throw std::runtime_error("silversynthgen: requires a positive seed count and offset");
    trainingCampaignStart();
    const auto teacher = loadWholeCombatTeacher(teacherPath, sims, false, false, false);
    if (!search::nativeSilverExactRootBudgets())
        throw std::runtime_error("silversynthgen: requires the flat exact-budget teacher");
    const std::string rowsPath = outPrefix + ".jsonl";
    const std::string manifestPath = outPrefix + ".manifest.json";
    for (const auto &path : {rowsPath, manifestPath})
        if (std::filesystem::exists(path))
            throw std::runtime_error("silversynthgen: refusing to overwrite " + path);
    std::ofstream rows(rowsPath);
    if (!rows) throw std::runtime_error("silversynthgen: cannot open " + rowsPath);
    long long roots = 0, leaves = 0, secondTeachers = 0, continuationRoots = 0, fights = 0, invalidFights = 0;
    int completed = 0;
    nlohmann::json seeds = nlohmann::json::array();
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        const auto seed = static_cast<std::uint64_t>(seedOffset + s);
        const auto result = runSynthSeed(seed, sims, asc, teacher, variant == "perturbed");
        #pragma omp critical(silver_synth_write)
        {
            rows << result.rows;
            rows.flush();
            roots += result.roots;
            leaves += result.leaves;
            secondTeachers += result.secondTeachers;
            continuationRoots += result.continuationRoots;
            fights += result.fights;
            invalidFights += result.invalidFights;
            if (result.complete) ++completed;
            seeds.push_back({{"seed", seed}, {"complete", result.complete}, {"error", result.error},
                             {"fights", result.fights}, {"roots", result.roots}});
        }
    }
    rows.close();
    const nlohmann::json manifest = {
        {"schemaVersion", "silver_synth_v1"}, {"variant", variant},
        {"producerGitSha", trainingExecutableGitSha()},
        {"producerExecutableSha256", fileSha256(g_mainBinaryPath)},
        {"teacherId", teacher.id}, {"teacherManifestSha256", fileSha256(teacherPath)},
        {"combatTeacher", teacher.specification},
        {"seedSpec", {{"start", seedOffset}, {"count", nSeeds}, {"ascension", asc}}},
        {"simulationsPerDecision", sims},
        {"sampling", {{"secondTeacherEvery", kSecondTeacherEvery}, {"continuationEvery", kContinuationEvery},
                      {"continuationSims", kContinuationSims}, {"continuationReplicates", kContinuationReplicates},
                      {"leafStride", kLeafStride}, {"leavesPerRoot", kLeavesPerRoot}}},
        {"integrity", {{"requestedSeeds", nSeeds}, {"completedSeeds", completed}, {"fights", fights},
                       {"invalidFights", invalidFights}, {"roots", roots}, {"leaves", leaves},
                       {"secondTeachers", secondTeachers}, {"continuationRoots", continuationRoots}}},
        {"seeds", seeds},
        {"rows", {{"path", std::filesystem::absolute(rowsPath).string()}, {"sha256", fileSha256(rowsPath)}}}};
    std::ofstream mf(manifestPath);
    if (!mf) throw std::runtime_error("silversynthgen: cannot write manifest");
    mf << manifest.dump(2) << '\n';
    std::cout << "silversynthgen variant=" << variant << " teacher=" << teacher.id << " completed=" << completed
              << '/' << nSeeds << " fights=" << fights << " roots=" << roots << " leaves=" << leaves
              << " secondTeachers=" << secondTeachers << " continuationRoots=" << continuationRoots
              << " -> " << rowsPath << '\n';
    writeTrainingProvenance(rowsPath, "silversynthgen", nSeeds, completed, nSeeds - completed,
                            g_trainingHealthFailures.load(), roots + leaves, seedOffset, sims, asc);
}
