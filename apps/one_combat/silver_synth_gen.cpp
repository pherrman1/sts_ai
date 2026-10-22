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
//
// silverazgen (Silver AZ MLP loop self-play, /mnt/project-files/silver-az-mlp/
// PLAN.md §2.2-2.3) writes the same root and fight rows without the extras
// (no second teacher, continuations or leaf samples). Every fight searches
// with the STS_SILVER_ROOT_PRIOR policy model as tree prior at nodes with
// TREE_MIN_VISITS simulations; ROOT_BONUS 0 drops the bonus at the root, whose
// visit shares are the label (untried root edges still go in prior order).
// Every fight row also carries `score`, Silver's own terminal evaluation of the
// fight's end (the value label for a leaf value head).
//
// Out of combat these generators play their own fixed rules (map heuristic,
// reward rules, evalCardRewardPolicy, ScumSearchAgent2's policy), which never
// consult STS_OOC_HEART1. STS_AZGEN_PRODUCTION_OOC=1 plays every non-battle
// screen through runFullRunOOC's chain instead (realOocChainStep: key rule,
// heart1 when STS_OOC_HEART1 is loaded, chest and relic rules, Match and Keep,
// the policy chain), so the recorded fights follow the production run
// distribution. It requires live OOC MCTS off; fights play as before.
//
// silverazfocusgen is silverazgen for one encounter (fight-specific prior data,
// /mnt/project-files/silver-prior-fight-specific/): the run plays every other
// fight unrecorded at OTHER_SIMS with the same prior, and at the first fight of
// ENCOUNTER records REPLICATES detached copies at SIMS (replicate 0 unperturbed,
// the others perturbed as above), then ends. Fight ids are fight + 1000 *
// replicate. A boss ENCOUNTER is forced as its act's boss (gc.boss is
// overwritten when the act starts; no game RNG is drawn).

#include "one_combat/driver_shared.h"
#include "one_combat/silver_synth_keys.h"

#include "constants/CardPools.h"
#include "constants/Potions.h"
#include "sim/search/CombatValueNet.h"
#include "sim/search/NativeSilverBackend.h"
#include "sim/search/SearchRng.h"
#include "sim/search/SilverSearcher.h"
#include "sim/search/SilverWireJson.h"
#include "sim/search/SilverWireState.h"

#include <unistd.h>

namespace {

constexpr int kContinuationSims = 2000;      // per continuation decision
constexpr int kContinuationReplicates = 2;   // per root action
constexpr std::uint64_t kSecondTeacherEvery = 4;
constexpr std::uint64_t kContinuationEvery = 8;
constexpr std::uint64_t kLeafStride = 2503;  // rollout starts between leaf samples
constexpr std::size_t kLeavesPerRoot = 4;

using silver_synth::key;
using silver_synth::mix;
using silver_synth::plannerRoot;

// STS_AZGEN_PRODUCTION_OOC: unset or 0 = the generators' own out-of-combat rules; 1 = runFullRunOOC's chain.
bool productionOoc() {
    const char *v = std::getenv("STS_AZGEN_PRODUCTION_OOC");
    if (!v || !*v || std::string(v) == "0") return false;
    if (std::string(v) != "1") throw std::runtime_error("STS_AZGEN_PRODUCTION_OOC must be 0 or 1");
    if (one_combat::liveOocMctsEnabled())
        throw std::runtime_error("STS_AZGEN_PRODUCTION_OOC=1 requires live OOC MCTS off (STS_OOC_MCTS=0)");
    return true;
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
    bool lean = false;   // silverazgen: no second teacher or continuations
    std::ostringstream *out = nullptr;
    search::SilverLeafSamples leaves;
    long long roots = 0, leafRows = 0, secondTeachers = 0, continuationRoots = 0;
    // Scores the fight's end with Silver's own terminal evaluation, referenced to the fight's first
    // searched root (its gold and max-HP terms): the label a leaf value must share with the tree.
    std::unique_ptr<search::SilverSearcher> scorer;

    void observe(const search::NativeSilverRootView &view) {
        const auto &searcher = view.searcher;
        const auto &state = searcher.rootSearchState();
        const auto &context = searcher.searchContext();
        if (!scorer) {
            scorer = std::make_unique<search::SilverSearcher>(state, context);
            scorer->evalWeights = searcher.evalWeights;
        }
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
        if (!lean && multi && mix(rootKey) % kSecondTeacherEvery == 0) {
            // Independent second teacher: a fresh search with other randomness.
            search::SilverSearcher second(plannerRoot(state, key(rootKey, 2)), context);
            second.evalWeights = searcher.evalWeights;
            second.search(sims);
            row["second"] = rootEdges(second);
            ++secondTeachers;
        }
        if (!lean && multi && mix(rootKey ^ 0x5157) % kContinuationEvery == 0) {
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

// Self-play search settings of silverazgen; unset for silversynthgen.
struct AzPrior {
    int treeMinVisits = 0;
    bool rootBonus = true;
};

// silverazfocusgen: record only `target`, then end the run.
struct AzFocus {
    MonsterEncounter target = MonsterEncounter::INVALID;
    int replicates = 1;
    int otherSims = 0;
    int bossAct = 0;   // act whose boss is forced to `target`; 0 = not a boss
};

int focusBossAct(MonsterEncounter e) {
    using ME = MonsterEncounter;
    switch (e) {
        case ME::THE_GUARDIAN: case ME::HEXAGHOST: case ME::SLIME_BOSS: return 1;
        case ME::AUTOMATON: case ME::COLLECTOR: case ME::CHAMP: return 2;
        case ME::AWAKENED_ONE: case ME::TIME_EATER: case ME::DONU_AND_DECA: return 3;
        default: return 0;
    }
}

SeedResult runSynthSeed(std::uint64_t seed, int sims, int asc, const std::string &teacherId,
                        bool perturbed, const std::optional<AzPrior> &az = std::nullopt,
                        const std::optional<AzFocus> &focus = std::nullopt) {
    SeedResult result;
    std::ostringstream out;
    FightRecorder recorder;
    recorder.seed = seed;
    recorder.variant = perturbed ? "perturbed" : "natural";
    recorder.sims = sims;
    recorder.lean = az.has_value();
    recorder.out = &out;
    recorder.leaves.stride = kLeafStride;
    recorder.leaves.max = kLeavesPerRoot;
    struct HookScope {
        ~HookScope() {
            search::g_nativeSilverRootObserver = nullptr;
            search::g_nativeSilverLeafSamples = nullptr;
            search::g_nativeSilverRootPriorOverride.reset();
            search::g_nativeSilverTreePriorOverride.reset();
            search::g_nativeSilverRootPriorBonusOff = false;
        }
    } hooks;
    if (az) {
        // Every fight of the run (recorded or not) plays the self-play search.
        search::g_nativeSilverRootPriorOverride = true;
        search::g_nativeSilverTreePriorOverride = az->treeMinVisits;
        search::g_nativeSilverRootPriorBonusOff = !az->rootBonus;
    }
    auto record = [&](GameContext &gc, BattleContext &bc, search::ScumSearchAgent2 &agent,
                      const nlohmann::json &perturbation) {
        const int preHp = gc.curHp, preMaxHp = gc.maxHp;
        const long long rootsBefore = recorder.roots;
        recorder.leaves.samples.clear();
        recorder.scorer.reset();
        search::g_nativeSilverLeafSamples = recorder.lean ? nullptr : &recorder.leaves;
        search::g_nativeSilverRootObserver = [&](const search::NativeSilverRootView &view) { recorder.observe(view); };
        agent.playoutBattle(gc, bc);
        search::g_nativeSilverRootObserver = nullptr;
        search::g_nativeSilverLeafSamples = nullptr;
        const bool decided = bc.outcome != Outcome::UNDECIDED;
        const bool valid = trainingRunValid(decided);
        out << nlohmann::json{
            {"kind", "fight"}, {"seed", seed}, {"variant", recorder.variant}, {"fight", recorder.fightIdx},
            {"teacherId", teacherId}, {"act", gc.act}, {"floor", gc.floorNum},
            {"room", roomStrings[static_cast<int>(gc.curRoom)]},
            {"encounter", monsterEncounterEnumNames[static_cast<int>(bc.encounter)]},
            {"preHp", preHp}, {"preMaxHp", preMaxHp}, {"perturbation", perturbation},
            {"valid", valid}, {"won", bc.outcome == Outcome::PLAYER_VICTORY},
            {"endHp", bc.player.curHp}, {"turns", bc.turn}, {"roots", recorder.roots - rootsBefore},
            {"score", decided && recorder.scorer ? nlohmann::json(recorder.scorer->scoreEndState(bc))
                                                 : nlohmann::json(nullptr)}}.dump() << '\n';
        ++result.fights;
        if (!valid) ++result.invalidFights;
        return valid;
    };
    try {
        trainingRunStart();
        GameContext gc(CharacterClass::IRONCLAD, seed, asc);
        search::ScumSearchAgent2 agent;
        agent.simulationCountBase = focus ? focus->otherSims : sims;
        agent.rng = std::default_random_engine(seed);
        PathHistory path;
        t_curPath = &path;
        const bool chain = productionOoc();
        one_combat::LiveOocMctsMetrics chainMetrics;
        std::uint64_t chainIndex = 0;
        if (chain) beginRealOocChainRun(/*shopV=*/true);
        using RT = search::GameAction::RewardsActionType;
        while (gc.outcome == GameOutcome::UNDECIDED) {
            if (focus && focus->bossAct == gc.act) gc.boss = focus->target;
            path.update(gc);
            if (gc.screenState == ScreenState::BATTLE) {
                if (focus && gc.info.encounter == focus->target) {
                    const int base = recorder.fightIdx;
                    for (int r = 0; r < focus->replicates; ++r) {
                        GameContext shadow = detachedCounterfactualCopy(gc);
                        const auto applied = r == 0 ? nlohmann::json(nullptr)
                                                    : applyPerturbation(shadow, key(seed, base, 0x9e57, r));
                        search::ScumSearchAgent2 shadowAgent;
                        shadowAgent.simulationCountBase = sims;
                        shadowAgent.rng = std::default_random_engine(key(seed, base, 1, r));
                        recorder.variant = r == 0 ? "natural" : "perturbed";
                        recorder.fightIdx = base + 1000 * r;
                        BattleContext shadowBc;
                        record(shadow, shadowBc, shadowAgent, applied);
                    }
                    break;
                } else if (focus) {
                    BattleContext bc;
                    agent.playoutBattle(gc, bc);
                    if (!trainingRunValid(bc.outcome != Outcome::UNDECIDED)) {
                        result.error = "natural_fight_invalid";
                        break;
                    }
                    bc.exitBattle(gc);
                } else if (perturbed) {
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
            } else if (chain) {
                realOocChainStep(gc, agent, deployedRestV(), /*shopV=*/true, path, seed, chainIndex++, chainMetrics);
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
    const bool chainOoc = productionOoc();
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
        const auto result = runSynthSeed(seed, sims, asc, teacher.id, variant == "perturbed");
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
        {"silverLeaf", effectiveSilverLeafSpecification()},
        {"teacherId", teacher.id}, {"teacherManifestSha256", fileSha256(teacherPath)},
        {"combatTeacher", teacher.specification},
        {"oocPlay", chainOoc ? "production_chain" : "generator_rules"},
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

namespace {

void silverAzRun(int nSeeds, int sims, int asc, const std::string &outPrefix, long long seedOffset,
                 const std::string &variant, int treeMinVisits, int rootBonus, const std::optional<AzFocus> &focus) {
    if (variant != "natural" && variant != "perturbed" && !focus)
        throw std::runtime_error("silverazgen: variant must be natural or perturbed");
    if (nSeeds < 1 || seedOffset < 0 || sims < 1)
        throw std::runtime_error("silverazgen: requires positive seed count, budget and offset");
    if (treeMinVisits < 1 || (rootBonus != 0 && rootBonus != 1))
        throw std::runtime_error("silverazgen: TREE_MIN_VISITS must be >= 1 and ROOT_BONUS 0 or 1");
    trainingCampaignStart();
    // The frozen flat exact-budget Silver of the §397 corpus, at SIMS, with the prior.
    const std::map<std::string, std::string> required = {
        {"STS_FAIR", "1"}, {"STS_SEARCHER3", "0"}, {"STS_SILVER_SEARCH", "1"},
        {"STS_SILVER_EXACT_ROOT_BUDGETS", "1"}, {"STS_SILVER_REUSE_CAP_MODE", "allocated"},
        {"STS_SILVER_ADAPTIVE", "0"}, {"STS_SILVER_VNET_LEAF_DIRECT", "0"}};
    nlohmann::json environment = nlohmann::json::object();
    for (const auto &[name, value] : required) {
        const char *actual = std::getenv(name.c_str());
        if (!actual || value != actual) throw std::runtime_error("silverazgen: requires " + name + "=" + value);
    }
    for (char **env = environ; env && *env; ++env) {
        const std::string entry(*env);
        const auto eq = entry.find('=');
        if (entry.rfind("STS_", 0) == 0 && eq != std::string::npos) environment[entry.substr(0, eq)] = entry.substr(eq + 1);
    }
    if (!search::nativeSilverBackendInstalled() || !search::nativeSilverExactRootBudgets()
            || search::nativeSilverAdaptiveEnabled() || search::nativeSilverLearnedStopEnabled())
        throw std::runtime_error("silverazgen: requires flat exact-budget native Silver");
    if (search::nativeSilverReuseCap() != 32768)
        throw std::runtime_error("silverazgen: reuse cap differs from the frozen 32k");
    const bool chainOoc = productionOoc();
    const std::string priorPath = search::nativeSilverRootPriorPath();
    search::CombatValueNet prior;
    if (priorPath.empty() || !prior.load(priorPath) || !prior.isPolicyMlp)
        throw std::runtime_error("silverazgen: STS_SILVER_ROOT_PRIOR must be a combat_policy_mlp_v1 model");
    const std::string rowsPath = outPrefix + ".jsonl";
    const std::string manifestPath = outPrefix + ".manifest.json";
    for (const auto &path : {rowsPath, manifestPath})
        if (std::filesystem::exists(path))
            throw std::runtime_error("silverazgen: refusing to overwrite " + path);
    std::ofstream rows(rowsPath);
    if (!rows) throw std::runtime_error("silverazgen: cannot open " + rowsPath);
    const std::string priorSha = fileSha256(priorPath);
    const std::string teacherId = "silver-az-" + std::to_string(sims) + "-k" + std::to_string(treeMinVisits)
        + "-rb" + std::to_string(rootBonus) + "-" + priorSha.substr(0, 8);
    const AzPrior az{treeMinVisits, rootBonus == 1};
    long long roots = 0, fights = 0, invalidFights = 0;
    int completed = 0;
    nlohmann::json seeds = nlohmann::json::array();
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        const auto seed = static_cast<std::uint64_t>(seedOffset + s);
        const auto result = runSynthSeed(seed, sims, asc, teacherId, variant == "perturbed", az, focus);
        #pragma omp critical(silver_az_write)
        {
            rows << result.rows;
            rows.flush();
            roots += result.roots;
            fights += result.fights;
            invalidFights += result.invalidFights;
            if (result.complete) ++completed;
            seeds.push_back({{"seed", seed}, {"complete", result.complete}, {"error", result.error},
                             {"fights", result.fights}, {"roots", result.roots}});
        }
    }
    rows.close();
    const nlohmann::json manifest = {
        {"schemaVersion", "silver_az_v1"}, {"variant", variant}, {"teacherId", teacherId},
        {"producerGitSha", trainingExecutableGitSha()},
        {"producerExecutableSha256", fileSha256(g_mainBinaryPath)},
        {"silverLeaf", effectiveSilverLeafSpecification()},
        {"prior", {{"path", priorPath}, {"sha256", priorSha}, {"model", prior.description()},
                   {"weight", search::nativeSilverRootPriorWeight()}, {"treeMinVisits", treeMinVisits},
                   {"rootBonus", rootBonus == 1}}},
        {"environment", environment}, {"oocPolicy", effectiveOocPolicySpecification()},
        {"oocPlay", chainOoc ? "production_chain" : "generator_rules"},
        {"seedSpec", {{"start", seedOffset}, {"count", nSeeds}, {"ascension", asc}}},
        {"simulationsPerDecision", sims},
        {"focus", focus ? nlohmann::json{{"encounter", monsterEncounterEnumNames[static_cast<int>(focus->target)]},
                                         {"replicates", focus->replicates}, {"otherSims", focus->otherSims},
                                         {"forcedBossAct", focus->bossAct}}
                        : nlohmann::json(nullptr)},
        {"integrity", {{"requestedSeeds", nSeeds}, {"completedSeeds", completed}, {"fights", fights},
                       {"invalidFights", invalidFights}, {"roots", roots}}},
        {"seeds", seeds},
        {"rows", {{"path", std::filesystem::absolute(rowsPath).string()}, {"sha256", fileSha256(rowsPath)}}}};
    std::ofstream mf(manifestPath);
    if (!mf) throw std::runtime_error("silverazgen: cannot write manifest");
    mf << manifest.dump(2) << '\n';
    std::cout << "silverazgen variant=" << variant << " teacher=" << teacherId << " completed=" << completed
              << '/' << nSeeds << " fights=" << fights << " roots=" << roots << " -> " << rowsPath << '\n';
    writeTrainingProvenance(rowsPath, "silverazgen", nSeeds, completed, nSeeds - completed,
                            g_trainingHealthFailures.load(), roots, seedOffset, sims, asc);
}

}  // namespace

void silverAzGen(int nSeeds, int sims, int asc, const std::string &outPrefix, long long seedOffset,
                 const std::string &variant, int treeMinVisits, int rootBonus) {
    silverAzRun(nSeeds, sims, asc, outPrefix, seedOffset, variant, treeMinVisits, rootBonus, std::nullopt);
}

void silverAzFocusGen(int nSeeds, int sims, int asc, const std::string &outPrefix, long long seedOffset,
                      const std::string &encounter, int replicates, int otherSims, int treeMinVisits, int rootBonus) {
    AzFocus focus;
    for (int i = 1; i < static_cast<int>(std::size(monsterEncounterEnumNames)); ++i)
        if (encounter == monsterEncounterEnumNames[i]) focus.target = static_cast<MonsterEncounter>(i);
    if (focus.target == MonsterEncounter::INVALID)
        throw std::runtime_error("silverazfocusgen: unknown encounter " + encounter);
    if (replicates < 1 || otherSims < 1)
        throw std::runtime_error("silverazfocusgen: REPLICATES and OTHER_SIMS must be >= 1");
    focus.replicates = replicates;
    focus.otherSims = otherSims;
    focus.bossAct = focusBossAct(focus.target);
    silverAzRun(nSeeds, sims, asc, outPrefix, seedOffset, "focus", treeMinVisits, rootBonus, focus);
}

// silverfocusevalgen (§469): paired online check of two combat_policy_mlp_v1 tree priors on one
// encounter. Each run reaches the first ENCOUNTER fight as silverazfocusgen does (other fights
// unrecorded at OTHER_SIMS with the STS_SILVER_ROOT_PRIOR model as tree prior, boss forced), then
// plays REPLICATES detached copies of that fight per arm at ARM_SIMS with the arm's model as root
// and tree prior (K = TREE_MIN_VISITS, root bonus on, as the ctmsilvergen mlpprior arms). Copy r of
// both arms shares one combat-future redraw and one search RNG seed, so the arms differ only in the
// prior. One CSV row per (run, replicate, arm); the run ends after the target fight's copies.
namespace {

std::uint64_t threadCpuNanos() {
    timespec ts{};
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts);
    return static_cast<std::uint64_t>(ts.tv_sec) * 1000000000ULL + static_cast<std::uint64_t>(ts.tv_nsec);
}

void redrawCombatFuture(GameContext &gc, std::uint64_t seed) {
    std::mt19937_64 rng(seed);
    for (auto stream : {&gc.aiRng, &gc.cardRandomRng, &gc.miscRng, &gc.monsterHpRng, &gc.potionRng, &gc.shuffleRng}) {
        const auto counter = stream->counter;
        *stream = sts::Random(rng());
        stream->counter = counter;
    }
}

struct FocusEvalArm { std::string name; const search::CombatValueNet *net; };

std::string runFocusEvalSeed(std::uint64_t seed, int asc, const AzFocus &focus, int armSims, int treeMinVisits,
                             const std::vector<FocusEvalArm> &arms, std::string &error, bool &reached) {
    std::ostringstream out;
    reached = false;
    struct HookScope {
        ~HookScope() {
            search::g_nativeSilverRootPriorOverride.reset();
            search::g_nativeSilverTreePriorOverride.reset();
            search::g_nativeSilverPriorNetOverride = nullptr;
            search::g_nativeSilverPlannerSeedOverride.reset();
        }
    } hooks;
    search::g_nativeSilverRootPriorOverride = true;
    search::g_nativeSilverTreePriorOverride = treeMinVisits;
    try {
        trainingRunStart();
        GameContext gc(CharacterClass::IRONCLAD, seed, asc);
        search::ScumSearchAgent2 agent;
        agent.simulationCountBase = focus.otherSims;
        agent.rng = std::default_random_engine(seed);
        PathHistory path;
        t_curPath = &path;
        using RT = search::GameAction::RewardsActionType;
        int fightIdx = 0;
        while (gc.outcome == GameOutcome::UNDECIDED) {
            if (focus.bossAct == gc.act) gc.boss = focus.target;
            path.update(gc);
            if (gc.screenState == ScreenState::BATTLE) {
                if (gc.info.encounter == focus.target) {
                    reached = true;
                    for (int r = 0; r < focus.replicates; ++r) {
                        for (const auto &arm : arms) {
                            // Same detached copy, combat future and search seed for both arms. The
                            // battle reseeds its own streams from gc.seed + floor, so copy r >= 1 gets a
                            // fresh battle seed; the planner seed varies Silver's randomness per copy.
                            GameContext copy = detachedCounterfactualCopy(gc);
                            redrawCombatFuture(copy, key(seed, fightIdx, 0xC0FFEE07, r));
                            if (r > 0) copy.seed = key(seed, fightIdx, 0xBA77, r);
                            search::g_nativeSilverPlannerSeedOverride = key(seed, fightIdx, 0x91A77E2, r);
                            search::ScumSearchAgent2 armAgent;
                            armAgent.simulationCountBase = armSims;
                            armAgent.rng = std::default_random_engine(key(seed, fightIdx, 2, r));
                            search::g_nativeSilverPriorNetOverride = arm.net;
                            BattleContext bc;
                            const int preHp = copy.curHp, preMaxHp = copy.maxHp, prePotions = copy.potionCount;
                            const auto t0 = threadCpuNanos();
                            armAgent.playoutBattle(copy, bc);
                            const double cpu = static_cast<double>(threadCpuNanos() - t0) / 1e9;
                            search::g_nativeSilverPriorNetOverride = nullptr;
                            search::g_nativeSilverPlannerSeedOverride.reset();
                            const bool decided = bc.outcome != Outcome::UNDECIDED;
                            const bool won = bc.outcome == Outcome::PLAYER_VICTORY;
                            const bool valid = trainingRunValid(decided);
                            if (won) bc.exitBattle(copy);
                            out << seed << ',' << fightIdx << ',' << gc.act << ',' << gc.floorNum << ',' << r << ','
                                << arm.name << ',' << preHp << ',' << preMaxHp << ',' << prePotions << ','
                                << (valid ? 1 : 0) << ',' << (won ? 1 : 0) << ',' << (won ? copy.curHp : 0) << ','
                                << copy.maxHp << ',' << copy.potionCount << ',' << copy.gold << ',' << bc.turn << ','
                                << std::setprecision(6) << cpu << '\n';
                        }
                    }
                    break;
                }
                BattleContext bc;
                agent.playoutBattle(gc, bc);
                if (!trainingRunValid(bc.outcome != Outcome::UNDECIDED)) { error = "natural_fight_invalid"; break; }
                bc.exitBattle(gc);
                ++fightIdx;
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
    } catch (const std::exception &e) {
        error = e.what();
    }
    t_curPath = nullptr;
    return out.str();
}

}  // namespace

void silverFocusEvalGen(int nSeeds, int asc, const std::string &outPrefix, long long seedOffset,
                        const std::string &encounter, int replicates, int otherSims, int armSims, int treeMinVisits,
                        const std::string &priorA, const std::string &priorB) {
    AzFocus focus;
    for (int i = 1; i < static_cast<int>(std::size(monsterEncounterEnumNames)); ++i)
        if (encounter == monsterEncounterEnumNames[i]) focus.target = static_cast<MonsterEncounter>(i);
    if (focus.target == MonsterEncounter::INVALID)
        throw std::runtime_error("silverfocusevalgen: unknown encounter " + encounter);
    if (nSeeds < 1 || seedOffset < 0 || replicates < 1 || otherSims < 1 || armSims < 1 || treeMinVisits < 1)
        throw std::runtime_error("silverfocusevalgen: counts, budgets and TREE_MIN_VISITS must be positive");
    focus.replicates = replicates;
    focus.otherSims = otherSims;
    focus.bossAct = focusBossAct(focus.target);
    trainingCampaignStart();
    const std::map<std::string, std::string> required = {
        {"STS_FAIR", "1"}, {"STS_SEARCHER3", "0"}, {"STS_SILVER_SEARCH", "1"},
        {"STS_SILVER_EXACT_ROOT_BUDGETS", "1"}, {"STS_SILVER_REUSE_CAP_MODE", "allocated"},
        {"STS_SILVER_ADAPTIVE", "0"}, {"STS_SILVER_VNET_LEAF_DIRECT", "0"}};
    nlohmann::json environment = nlohmann::json::object();
    for (const auto &[name, value] : required) {
        const char *actual = std::getenv(name.c_str());
        if (!actual || value != actual) throw std::runtime_error("silverfocusevalgen: requires " + name + "=" + value);
    }
    for (char **env = environ; env && *env; ++env) {
        const std::string entry(*env);
        const auto eq = entry.find('=');
        if (entry.rfind("STS_", 0) == 0 && eq != std::string::npos) environment[entry.substr(0, eq)] = entry.substr(eq + 1);
    }
    if (!search::nativeSilverBackendInstalled() || !search::nativeSilverExactRootBudgets()
            || search::nativeSilverAdaptiveEnabled() || search::nativeSilverLearnedStopEnabled())
        throw std::runtime_error("silverfocusevalgen: requires flat exact-budget native Silver");
    const std::string envPrior = search::nativeSilverRootPriorPath();
    search::CombatValueNet envNet, netA, netB;
    if (envPrior.empty() || !envNet.load(envPrior) || !envNet.isPolicyMlp)
        throw std::runtime_error("silverfocusevalgen: STS_SILVER_ROOT_PRIOR must be a combat_policy_mlp_v1 model");
    if (!netA.load(priorA) || !netA.isPolicyMlp || !netB.load(priorB) || !netB.isPolicyMlp)
        throw std::runtime_error("silverfocusevalgen: PRIOR_A and PRIOR_B must be combat_policy_mlp_v1 models");
    const std::vector<FocusEvalArm> arms = {{"A", &netA}, {"B", &netB}};
    const std::string rowsPath = outPrefix + ".csv", manifestPath = outPrefix + ".manifest.json";
    for (const auto &path : {rowsPath, manifestPath})
        if (std::filesystem::exists(path)) throw std::runtime_error("silverfocusevalgen: refusing to overwrite " + path);
    std::ofstream rows(rowsPath);
    if (!rows) throw std::runtime_error("silverfocusevalgen: cannot open " + rowsPath);
    rows << "seed,fightIdx,act,floor,replicate,arm,preHp,preMaxHp,prePotions,valid,won,curHp,maxHp,potionCount,gold,"
            "turns,cpuSeconds\n";
    int completed = 0, reachedCount = 0;
    nlohmann::json seeds = nlohmann::json::array();
    #pragma omp parallel for schedule(dynamic)
    for (int s = 0; s < nSeeds; ++s) {
        const auto seed = static_cast<std::uint64_t>(seedOffset + s);
        std::string error;
        bool reached = false;
        const auto text = runFocusEvalSeed(seed, asc, focus, armSims, treeMinVisits, arms, error, reached);
        #pragma omp critical(silver_focus_eval_write)
        {
            rows << text;
            rows.flush();
            if (error.empty()) ++completed;
            if (reached) ++reachedCount;
            seeds.push_back({{"seed", seed}, {"complete", error.empty()}, {"error", error}, {"reached", reached}});
        }
    }
    rows.close();
    const nlohmann::json manifest = {
        {"schemaVersion", "silver_focus_eval_v1"}, {"producerGitSha", trainingExecutableGitSha()},
        {"producerExecutableSha256", fileSha256(g_mainBinaryPath)},
        {"silverLeaf", effectiveSilverLeafSpecification()},
        {"focus", {{"encounter", encounter}, {"replicates", replicates}, {"otherSims", otherSims},
                   {"forcedBossAct", focus.bossAct}}},
        {"arms", {{"A", {{"path", priorA}, {"sha256", fileSha256(priorA)}}},
                  {"B", {{"path", priorB}, {"sha256", fileSha256(priorB)}}}}},
        {"armSims", armSims}, {"treeMinVisits", treeMinVisits},
        {"reachPrior", {{"path", envPrior}, {"sha256", fileSha256(envPrior)},
                        {"weight", search::nativeSilverRootPriorWeight()}}},
        {"environment", environment}, {"oocPolicy", effectiveOocPolicySpecification()},
        {"seedSpec", {{"start", seedOffset}, {"count", nSeeds}, {"ascension", asc}}},
        {"integrity", {{"requestedSeeds", nSeeds}, {"completedSeeds", completed}, {"reachedSeeds", reachedCount}}},
        {"seeds", seeds},
        {"rows", {{"path", std::filesystem::absolute(rowsPath).string()}, {"sha256", fileSha256(rowsPath)}}}};
    std::ofstream mf(manifestPath);
    if (!mf) throw std::runtime_error("silverfocusevalgen: cannot write manifest");
    mf << manifest.dump(2) << '\n';
    std::cout << "silverfocusevalgen encounter=" << encounter << " completed=" << completed << '/' << nSeeds
              << " reached=" << reachedCount << " -> " << rowsPath << '\n';
}

// act4replay (A20 loss audit F1, 2026-10-17): fight-level replay of recorded Act-4 entry states
// (Shield + Spear, the Heart) under several flat exact Silver budgets. Each JSONL line gives the
// encounter, HP, max HP, deck (trace names, "+" = upgraded once), relics, potions and potion
// capacity of one recorded fight start. The state is rebuilt on a fresh A20 GameContext moved to
// Act 4 (relic counters and card misc reset: an approximation shared by all arms). Copy r of every
// arm shares the battle seed (SEED_OFFSET + state * REPLICATES + r) and the planner seed, so arms
// differ only in the budget. One CSV row per (state, replicate, arm).
namespace {

GameContext act4ReplayContext(const nlohmann::json &s, std::uint64_t seed, MonsterEncounter enc) {
    static const auto cardIds = [] {
        std::map<std::string, CardId> m;
        for (int i = 1; i < static_cast<int>(std::size(cardNames)); ++i) m.emplace(cardNames[i], static_cast<CardId>(i));
        return m;
    }();
    GameContext gc(CharacterClass::IRONCLAD, seed, 20);
    gc.transitionToAct(4);
    gc.deck = Deck{};
    for (const auto &entry : s.at("deck")) {
        std::string name = entry.get<std::string>();
        const bool up = !name.empty() && name.back() == '+';
        if (up) name.pop_back();
        const auto it = cardIds.find(name);
        if (it == cardIds.end()) throw std::runtime_error("act4replay: unknown card " + name);
        Card c(it->second);
        if (up) c.upgrade();
        gc.deck.obtainRaw(c);
    }
    gc.relics.relics.clear();
    for (const auto &entry : s.at("relics")) {
        const auto name = entry.get<std::string>();
        int id = -1;
        for (int i = 0; i < static_cast<int>(std::size(relicEnumNames)) - 1; ++i)
            if (name == relicEnumNames[i]) id = i;
        if (id < 0) throw std::runtime_error("act4replay: unknown relic " + name);
        gc.relics.add({static_cast<RelicId>(id), 0});
    }
    gc.potionCapacity = s.at("potionCapacity").get<int>();
    for (int i = 0; i < static_cast<int>(gc.potions.size()); ++i) gc.potions[i] = Potion::EMPTY_POTION_SLOT;
    gc.potionCount = 0;
    for (const auto &entry : s.at("potions")) {
        const auto name = entry.get<std::string>();
        int id = -1;
        for (int i = 2; i < static_cast<int>(std::size(potionEnumNames)); ++i)
            if (name == potionEnumNames[i]) id = i;
        if (id < 0) throw std::runtime_error("act4replay: unknown potion " + name);
        gc.potions[gc.potionCount++] = static_cast<Potion>(id);
    }
    for (const auto k : {Key::RUBY_KEY, Key::EMERALD_KEY, Key::SAPPHIRE_KEY}) gc.obtainKey(k);
    gc.maxHp = s.at("maxHp").get<int>();
    gc.curHp = s.at("hp").get<int>();
    const bool heart = enc == MonsterEncounter::THE_HEART;
    gc.curMapNodeX = 3;
    gc.curMapNodeY = heart ? 3 : 2;
    gc.floorNum = heart ? 56 : 55;
    gc.curRoom = heart ? Room::BOSS : Room::ELITE;
    gc.enterBattle(enc);
    return gc;
}

}  // namespace

void act4Replay(int nStates, const std::string &statesPath, const std::string &outPrefix, long long seedOffset,
                const std::string &simsList, int replicates) {
    if (nStates < 1 || seedOffset < 0 || replicates < 1) throw std::runtime_error("act4replay: counts must be positive");
    std::vector<int> sims;
    {
        std::stringstream ss(simsList);
        for (std::string tok; std::getline(ss, tok, ',');) sims.push_back(std::stoi(tok));
    }
    if (sims.empty()) throw std::runtime_error("act4replay: empty budget list");
    const std::map<std::string, std::string> required = {
        {"STS_FAIR", "1"}, {"STS_SILVER_SEARCH", "1"}, {"STS_SILVER_EXACT_ROOT_BUDGETS", "1"},
        {"STS_SILVER_REUSE_CAP_MODE", "allocated"}, {"STS_SILVER_ADAPTIVE", "0"}, {"STS_SILVER_VNET_LEAF_DIRECT", "0"},
        {"STS_SILVER_LEARNED_STOP", "0"}};
    for (const auto &[name, value] : required) {
        const char *actual = std::getenv(name.c_str());
        if (!actual || value != actual) throw std::runtime_error("act4replay: requires " + name + "=" + value);
    }
    if (!search::nativeSilverBackendInstalled() || !search::nativeSilverExactRootBudgets()
            || search::nativeSilverAdaptiveEnabled() || search::nativeSilverLearnedStopEnabled())
        throw std::runtime_error("act4replay: requires flat exact-budget native Silver");
    std::vector<nlohmann::json> states;
    {
        std::ifstream in(statesPath);
        for (std::string line; std::getline(in, line) && static_cast<int>(states.size()) < nStates;)
            if (!line.empty()) states.push_back(nlohmann::json::parse(line));
    }
    if (static_cast<int>(states.size()) != nStates) throw std::runtime_error("act4replay: too few states");
    const std::string rowsPath = outPrefix + ".csv";
    if (std::filesystem::exists(rowsPath)) throw std::runtime_error("act4replay: refusing to overwrite " + rowsPath);
    std::ofstream rows(rowsPath);
    rows << "state,id,encounter,replicate,sims,battleSeed,preHp,preMaxHp,prePotions,valid,won,curHp,potionCount,turns,"
            "cpuSeconds\n";
    const int jobs = nStates * replicates;
    #pragma omp parallel for schedule(dynamic)
    for (int j = 0; j < jobs; ++j) {
        const int si = j / replicates, r = j % replicates;
        const auto &s = states[si];
        std::ostringstream out;
        try {
            MonsterEncounter enc = MonsterEncounter::INVALID;
            const auto encName = s.at("enc").get<std::string>();
            for (int i = 1; i < static_cast<int>(std::size(monsterEncounterEnumNames)); ++i)
                if (encName == monsterEncounterEnumNames[i]) enc = static_cast<MonsterEncounter>(i);
            if (enc != MonsterEncounter::THE_HEART && enc != MonsterEncounter::SHIELD_AND_SPEAR)
                throw std::runtime_error("act4replay: unsupported encounter " + encName);
            const auto battleSeed = static_cast<std::uint64_t>(seedOffset) + static_cast<std::uint64_t>(j);
            for (const int budget : sims) {
                trainingRunStart();
                GameContext copy = act4ReplayContext(s, battleSeed, enc);
                search::g_nativeSilverPlannerSeedOverride = key(battleSeed, si, 0xA47, r);
                search::ScumSearchAgent2 agent;
                agent.simulationCountBase = budget;
                agent.rng = std::default_random_engine(key(battleSeed, si, 3, r));
                BattleContext bc;
                const int preHp = copy.curHp, preMaxHp = copy.maxHp, prePotions = copy.potionCount;
                const auto t0 = threadCpuNanos();
                agent.playoutBattle(copy, bc);
                const double cpu = static_cast<double>(threadCpuNanos() - t0) / 1e9;
                search::g_nativeSilverPlannerSeedOverride.reset();
                const bool decided = bc.outcome != Outcome::UNDECIDED;
                const bool won = bc.outcome == Outcome::PLAYER_VICTORY;
                const bool valid = trainingRunValid(decided);
                out << si << ',' << s.value("id", std::string()) << ',' << encName << ',' << r << ',' << budget << ','
                    << battleSeed << ',' << preHp << ',' << preMaxHp << ',' << prePotions << ',' << (valid ? 1 : 0)
                    << ',' << (won ? 1 : 0) << ',' << (won ? bc.player.curHp : 0) << ',' << bc.potionCount << ','
                    << bc.turn << ',' << std::setprecision(6) << cpu << '\n';
            }
        } catch (const std::exception &e) {
            search::g_nativeSilverPlannerSeedOverride.reset();
            out << si << ',' << s.value("id", std::string()) << ",ERROR," << r << ",0,0,0,0,0,0,0,0,0,0,0 # " << e.what() << '\n';
        }
        #pragma omp critical(act4_replay_write)
        {
            rows << out.str();
            rows.flush();
        }
    }
    std::cout << "act4replay states=" << nStates << " replicates=" << replicates << " -> " << rowsPath << '\n';
}
