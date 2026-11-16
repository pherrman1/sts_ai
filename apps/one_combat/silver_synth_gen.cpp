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
// silverazgen's search overrides hold for every fight of the run, and under
// them Silver also leaves out the ADR-0050/0056 boss prior playouts that
// whole-run fights get from the same prior (the manifest's silverLeaf says so).
// STS_AZGEN_PRODUCTION_COMBAT=1 installs no override: every fight plays the
// whole-run production Silver (the root prior with its bonus, the tree prior
// from STS_SILVER_TREE_PRIOR_MIN_VISITS, boss prior playouts). It requires
// ROOT_BONUS 1 and TREE_MIN_VISITS equal to that whole-run tree prior.
//
// STS_AZGEN_LABEL_SEARCH=1 (silverazgen only, default off; requires STS_AZGEN_PRODUCTION_COMBAT=1 and
// STS_SILVER_LEAF_HEAD) is the on-policy leaf data: the fights play the leaf head's search, and every root is
// searched again by production Silver without the head (g_nativeSilverLabelSearch), at the same budget with its
// own retained graph. The root row's `edges` and `inheritedVisits` are that label search's, so the root value
// label is production's at the states the head's play reaches; `playEdges` and `playInheritedVisits` are the
// played search's. Fight rows (`score`) are the head's play. The label edges are written in the played root's
// edge order and action bits (labelRootEdges), since the row's wire is the played root; the manifest counts the
// roots where the two edge sets could not be matched (labelSearch.edgeFallbacks).
//
// STS_AZGEN_GUMBEL_ROOT=K (silverazgen only, default off; 2..64; requires STS_AZGEN_PRODUCTION_COMBAT=1, no
// label search) is combat plan stage 2's teacher data (§770): every fight of the run plays production Silver with
// the Gumbel root (SilverSearcher::searchGumbelRoot, Gumbel-top-K over the root prior, sequential halving) at the
// flat budget SIMS. Root rows add each edge's root prior (`prior`, null when the root has none) and the Gumbel
// pick's edge index (`gumbelChoice`), so a policy target (visit shares or the completed-Q policy) can be formed
// offline. The manifest records the setting (`gumbelRoot`).
//
// STS_AZGEN_WHOLE_RUN_GUMBEL=1 (silverazgen only, default off; requires STS_AZGEN_PRODUCTION_COMBAT=1,
// STS_SILVER_GUMBEL_ROOT=K > 0, no STS_AZGEN_GUMBEL_ROOT and no label search) is the Gumbel distillation teacher
// data (2026-11-10): no override is installed, so every fight plays the whole-run Gumbel root exactly as bestbench
// does with STS_SILVER_GUMBEL_ROOT (§775: its max backup STS_SILVER_GUMBEL_ROOT_MAX_BACKUP, Act 4 at Act 4 strong's
// budget and reuse cap), and root rows carry `prior` and `gumbelChoice` as above. Whenever the search runs max
// backup (min visits M > 0), every root edge also carries `qBacked` (the max-backed value the search selects with:
// the node's backed value once it has M simulations, else its mean) and the row `rootQBacked`, the root's; `q`
// stays the mean playout value.
//
// STS_AZGEN_BUDGET_LADDER=b1,b2,... (silverazgen only, default off; requires STS_AZGEN_WHOLE_RUN_GUMBEL=1; budgets
// 1..1,000,000 in strictly increasing order) is the learned-budget-per-decision data (2026-11-12): after the played
// search of every searched multi-edge root, the root is searched once more per budget by a fresh searcher configured
// as the played one, with its own Gumbel seed (g_nativeSilverBudgetLadder). The root row adds `ladder`, one entry per
// budget: {budget, edge (the pick as an index into the row's edges, -1 if unmatched), sims, cpu (thread seconds)},
// and `mainCpu`, the played search's thread seconds. Play is bit-identical with the ladder on or off.
//
// STS_AZGEN_EXTRA_LABELS=nodes:N,playouts:M,sims:L[,minvisits:V] (silverazgen only, default off; requires
// STS_AZGEN_WHOLE_RUN_GUMBEL=1; N, M in 0..16 with N + M > 0, L in 1..100,000, V >= 1, default 256) is the next
// prior's broad data (2026-11-16, issue #1053 follow-up): after the played search of every searched multi-edge root,
// up to N interior decision nodes of the played tree (PLAYER_NORMAL, more than one edge, at least V simulations,
// drawn uniformly) and up to M states visited inside the played search's playouts (a uniform reservoir over its
// PLAYER_NORMAL playout steps) are each searched by a fresh searcher configured as the played one, with the Gumbel
// root at L simulations and its own seed (g_nativeSilverExtraLabels). Each writes one row of kind `extra` after its
// root row: `source` (tree / playout), `depth` (tree: decision actions below the root; playout: its leaf's tree
// depth), `playoutStep`, `nodeVisits` (tree), `treeEdges` (tree: the played tree's edges at the node, with visits,
// q, qBacked and the node's tree prior), and, as root rows do, `edges` (the label search's, with prior and qBacked),
// `rootQBacked`, `gumbelChoice`, `labelSims`, `cpu`, `turn`, `hp` and `wire`. Play is bit-identical with the labels
// on or off.
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
#include "sim/search/KnownRngSearcher.h"
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

// STS_AZGEN_PRODUCTION_COMBAT: unset or 0 = the self-play search overrides; 1 = whole-run production Silver.
bool productionCombat() {
    const char *v = std::getenv("STS_AZGEN_PRODUCTION_COMBAT");
    if (!v || !*v || std::string(v) == "0") return false;
    if (std::string(v) != "1") throw std::runtime_error("STS_AZGEN_PRODUCTION_COMBAT must be 0 or 1");
    if (const char *scope = std::getenv("STS_SILVER_ROOT_PRIOR_SCOPE"); scope && std::string(scope) == "override")
        throw std::runtime_error("STS_AZGEN_PRODUCTION_COMBAT=1 requires the root prior in whole-run fights"
                                 " (STS_SILVER_ROOT_PRIOR_SCOPE=all)");
    return true;
}

// STS_AZGEN_LABEL_SEARCH: unset or 0 = rows label the played search; 1 = a production label search per root.
bool labelSearch() {
    const char *v = std::getenv("STS_AZGEN_LABEL_SEARCH");
    if (!v || !*v || std::string(v) == "0") return false;
    if (std::string(v) != "1") throw std::runtime_error("STS_AZGEN_LABEL_SEARCH must be 0 or 1");
    return true;
}

// STS_AZGEN_GUMBEL_ROOT: unset or 0 = production's root search; K in 2..64 = the Gumbel root with K sampled edges.
int gumbelRootK() {
    const char *v = std::getenv("STS_AZGEN_GUMBEL_ROOT");
    if (!v || !*v || std::string(v) == "0") return 0;
    int k = 0;
    try {
        std::size_t used = 0;
        k = std::stoi(v, &used);
        if (used != std::string(v).size()) k = 0;
    } catch (const std::exception &) {
        k = 0;
    }
    if (k < 2 || k > 64) throw std::runtime_error("STS_AZGEN_GUMBEL_ROOT must be 0 or 2..64");
    return k;
}

// A positive integer environment value, 0 when unset or "0"; throws on anything else.
int positiveEnvInt(const char *name) {
    const char *v = std::getenv(name);
    if (!v || !*v || std::string(v) == "0") return 0;
    int k = 0;
    try {
        std::size_t used = 0;
        k = std::stoi(v, &used);
        if (used != std::string(v).size()) k = 0;
    } catch (const std::exception &) {
        k = 0;
    }
    if (k < 1) throw std::runtime_error(std::string(name) + " must be a positive integer or 0");
    return k;
}

// STS_AZGEN_WHOLE_RUN_GUMBEL: unset or 0 = off; 1 = record the whole-run Gumbel root (STS_SILVER_GUMBEL_ROOT) as
// teacher rows. Returns that K (0 when off).
int wholeRunGumbelK() {
    const char *v = std::getenv("STS_AZGEN_WHOLE_RUN_GUMBEL");
    if (!v || !*v || std::string(v) == "0") return 0;
    if (std::string(v) != "1") throw std::runtime_error("STS_AZGEN_WHOLE_RUN_GUMBEL must be 0 or 1");
    const int k = positiveEnvInt("STS_SILVER_GUMBEL_ROOT");
    if (k == 0) throw std::runtime_error("STS_AZGEN_WHOLE_RUN_GUMBEL=1 requires STS_SILVER_GUMBEL_ROOT > 0");
    return k;
}

// STS_AZGEN_BUDGET_LADDER: unset or empty = off; else a comma list of strictly increasing budgets.
std::vector<std::int64_t> budgetLadder() {
    const char *v = std::getenv("STS_AZGEN_BUDGET_LADDER");
    std::vector<std::int64_t> out;
    if (!v || !*v) return out;
    std::stringstream ss(v);
    std::string item;
    while (std::getline(ss, item, ',')) {
        std::size_t used = 0;
        long long b = 0;
        try {
            b = std::stoll(item, &used);
        } catch (const std::exception &) {
            used = 0;
        }
        if (used != item.size() || b < 1 || b > 1000000 || (!out.empty() && b <= out.back()))
            throw std::runtime_error("STS_AZGEN_BUDGET_LADDER must be strictly increasing budgets in 1..1000000");
        out.push_back(b);
    }
    return out;
}

// STS_AZGEN_ROLLOUT_LADDER=policy:budget,... (silverazgen only, default off; requires STS_AZGEN_WHOLE_RUN_GUMBEL=1),
// cheap rollouts 2026-11-13: every searched multi-edge root whose played search uses prior playouts (boss rooms, Act 4)
// is searched once more per arm by a fresh searcher configured as the played one except for its playout policy
// (g_nativeSilverRolloutLadder). Policies: asplayed (prior every step), greedy, tt (prior once per playout turn),
// ftN (prior in the playout's first N turns, then greedy), st (STS_AZGEN_ROLLOUT_STUDENT every step), sttt (the
// student once per playout turn), ste (per-encounter students STS_AZGEN_ROLLOUT_STUDENT_ENC=ENCOUNTER=path,...,
// else the generalist). Rows' ladder entries add {policy, priorCalls, playoutActions}. Play is bit-identical.
std::vector<search::NativeSilverRolloutArm> rolloutLadder() {
    const char *v = std::getenv("STS_AZGEN_ROLLOUT_LADDER");
    std::vector<search::NativeSilverRolloutArm> out;
    if (!v || !*v) return out;
    std::stringstream ss(v);
    std::string item;
    using P = search::NativeSilverRolloutArm;
    while (std::getline(ss, item, ',')) {
        const auto colon = item.find(':');
        if (colon == std::string::npos) throw std::runtime_error("STS_AZGEN_ROLLOUT_LADDER: want policy:budget, got " + item);
        P arm;
        const std::string pol = item.substr(0, colon);
        arm.name = item;
        if (pol == "asplayed") arm.policy = P::AS_PLAYED;
        else if (pol == "greedy") arm.policy = P::GREEDY;
        else if (pol == "tt") arm.policy = P::TURN_TABLE;
        else if (pol.size() == 3 && pol.rfind("ft", 0) == 0 && pol[2] >= '1' && pol[2] <= '9') {
            arm.policy = P::FIRST_TURNS;
            arm.turns = pol[2] - '0';
        } else if (pol == "st") arm.policy = P::STUDENT;
        else if (pol == "sttt") arm.policy = P::STUDENT_TURN_TABLE;
        else if (pol == "ste") arm.policy = P::STUDENT_ENCOUNTER;
        else throw std::runtime_error("STS_AZGEN_ROLLOUT_LADDER: unknown policy " + pol);
        std::size_t used = 0;
        long long b = 0;
        try { b = std::stoll(item.substr(colon + 1), &used); } catch (const std::exception &) { used = 0; }
        if (used != item.size() - colon - 1 || b < 1 || b > 1000000)
            throw std::runtime_error("STS_AZGEN_ROLLOUT_LADDER: budget must be in 1..1000000 in " + item);
        arm.budget = b;
        out.push_back(arm);
    }
    return out;
}

// The rollout ladder's student models (process lifetime); their sha256 go to the manifest.
// STS_AZGEN_EXTRA_LABELS: unset or empty = off.
search::NativeSilverExtraLabels extraLabels() {
    search::NativeSilverExtraLabels x;
    const char *v = std::getenv("STS_AZGEN_EXTRA_LABELS");
    if (!v || !*v) return x;
    const auto bad = [](const std::string &why) {
        return std::runtime_error("STS_AZGEN_EXTRA_LABELS: " + why
                                  + " (want nodes:N,playouts:M,sims:L[,minvisits:V])");
    };
    std::stringstream ss(v);
    std::string item;
    bool haveSims = false;
    while (std::getline(ss, item, ',')) {
        const auto colon = item.find(':');
        if (colon == std::string::npos) throw bad("no ':' in " + item);
        const std::string k = item.substr(0, colon), val = item.substr(colon + 1);
        long long n = 0;
        try {
            std::size_t used = 0;
            n = std::stoll(val, &used);
            if (used != val.size()) throw bad("not an integer: " + item);
        } catch (const std::invalid_argument &) {
            throw bad("not an integer: " + item);
        } catch (const std::out_of_range &) {
            throw bad("out of range: " + item);
        }
        if (k == "nodes" && n >= 0 && n <= 16) x.nodes = static_cast<int>(n);
        else if (k == "playouts" && n >= 0 && n <= 16) x.playouts = static_cast<int>(n);
        else if (k == "sims" && n >= 1 && n <= 100000) { x.sims = n; haveSims = true; }
        else if (k == "minvisits" && n >= 1 && n <= 1000000) x.minVisits = static_cast<int>(n);
        else throw bad("unknown key or value out of range: " + item);
    }
    if (!haveSims || x.nodes + x.playouts == 0) throw bad("needs sims and nodes + playouts > 0");
    return x;
}

nlohmann::json loadRolloutStudents(const std::vector<search::NativeSilverRolloutArm> &arms) {
    static search::CombatValueNet generalist;
    static std::map<int, std::unique_ptr<search::CombatValueNet>> byEncounter;
    nlohmann::json info = nlohmann::json::object();
    bool wantStudent = false;
    for (const auto &a : arms) wantStudent |= a.policy >= search::NativeSilverRolloutArm::STUDENT;
    if (!wantStudent) return info;
    const char *path = std::getenv("STS_AZGEN_ROLLOUT_STUDENT");
    if (!path || !*path || !generalist.load(path) || !generalist.isPolicyMlp)
        throw std::runtime_error("STS_AZGEN_ROLLOUT_LADDER: student arms need STS_AZGEN_ROLLOUT_STUDENT (a policy MLP)");
    search::g_nativeSilverRolloutStudent = &generalist;
    info["generalist"] = {{"path", path}, {"sha256", fileSha256(path)}};
    if (const char *enc = std::getenv("STS_AZGEN_ROLLOUT_STUDENT_ENC"); enc && *enc) {
        std::stringstream ss(enc);
        std::string item;
        while (std::getline(ss, item, ',')) {
            const auto eq = item.find('=');
            if (eq == std::string::npos) throw std::runtime_error("STS_AZGEN_ROLLOUT_STUDENT_ENC: want ENCOUNTER=path");
            const std::string name = item.substr(0, eq), file = item.substr(eq + 1);
            int code = -1;
            for (int i = 0; i < static_cast<int>(std::size(monsterEncounterEnumNames)); ++i)
                if (name == monsterEncounterEnumNames[i]) code = i;
            if (code < 0) throw std::runtime_error("STS_AZGEN_ROLLOUT_STUDENT_ENC: unknown encounter " + name);
            auto net = std::make_unique<search::CombatValueNet>();
            if (!net->load(file) || !net->isPolicyMlp)
                throw std::runtime_error("STS_AZGEN_ROLLOUT_STUDENT_ENC: cannot load " + file);
            search::g_nativeSilverRolloutStudentByEncounter[code] = net.get();
            byEncounter[code] = std::move(net);
            info["encounters"][name] = {{"path", file}, {"sha256", fileSha256(file)}};
        }
    }
    return info;
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

// The value max backup selects a node with (SilverSearcher::selectionValue): its backed value once it has `minVisits`
// simulations and a backed value, else its mean playout value.
double backedValue(const search::SilverSearcher::Node &node, int minVisits) {
    if (minVisits > 0 && node.hasBackedValue && node.simulationCount >= minVisits) return node.backedValue;
    return node.evaluationSum / node.simulationCount;
}

nlohmann::json rootEdges(const search::SilverSearcher &searcher) {
    nlohmann::json edges = nlohmann::json::array();
    const auto &state = searcher.rootSearchState();
    const int mb = searcher.maxBackupMinVisits;
    for (const auto &edge : searcher.rootNode().edges) {
        const bool hasQ = edge.node && edge.node->simulationCount > 0;
        edges.push_back({{"bits", edge.action.bits}, {"semantic", fingerprint(state, edge.action)},
                         {"visits", edge.visitCount},
                         {"childSims", edge.node ? edge.node->simulationCount : 0},
                         {"q", hasQ ? nlohmann::json(edge.node->evaluationSum / edge.node->simulationCount)
                                    : nlohmann::json(nullptr)}});
        if (mb > 0)   // only under max backup, so other rows keep their keys
            edges.back()["qBacked"] = hasQ ? nlohmann::json(backedValue(*edge.node, mb)) : nlohmann::json(nullptr);
    }
    return edges;
}

// The semantic fingerprint of `action` in `state` without the cards' unique ids, equal for plays or selections of
// two search-equivalent copies; empty when the action has no semantic form.
std::string copyFreeFingerprint(const BattleContext &state, const search::Action &action) {
    try {
        auto semantic = search::semanticFromSearchAction(state, action);
        semantic.card.uniqueId = 0;
        for (auto &card : semantic.selectedCards) card.uniqueId = 0;
        return search::semanticFingerprint(semantic);
    } catch (const std::exception &) {
        return {};
    }
}

// STS_AZGEN_LABEL_SEARCH: the label search's root edges in the played search's root order, with that root's
// action bits and semantics, so they read against the row's wire like the played edges do. The two roots are
// equal for search but can order the hand differently (the label graph reached the state by another path), and
// Silver expands one copy of each set of equivalent cards, so the two roots can keep different copies. Each label
// edge is matched to the played edge it translates to, else to the played edge that plays or selects an
// equivalent copy (same semantic action up to the cards' unique ids). Null when the two edge sets do not match one
// to one.
nlohmann::json labelRootEdges(const search::SilverSearcher &label, const search::SilverSearcher &played) {
    const auto &from = label.rootSearchState();
    const auto &to = played.rootSearchState();
    const auto &labelEdges = label.rootNode().edges;
    const auto &playedEdges = played.rootNode().edges;
    const int n = static_cast<int>(playedEdges.size());
    if (static_cast<int>(labelEdges.size()) != n) return nullptr;
    std::vector<search::Action> translated;
    try {
        for (const auto &edge : labelEdges)
            translated.push_back(search::SilverSearcher::translateAction(edge.action, from, to));
    } catch (const std::exception &) {
        return nullptr;
    }
    std::vector<int> labelAt(n, -1);
    std::vector<bool> matched(n, false);
    const auto match = [&](int i, int j) { labelAt[j] = i; matched[i] = true; };
    for (int i = 0; i < n; ++i)
        for (int j = 0; j < n && !matched[i]; ++j)
            if (labelAt[j] < 0 && playedEdges[j].action.bits == translated[i].bits) match(i, j);
    for (int i = 0; i < n; ++i) {
        if (matched[i]) continue;
        const std::string copyFree = copyFreeFingerprint(to, translated[i]);
        for (int j = 0; j < n && !matched[i] && !copyFree.empty(); ++j)
            if (labelAt[j] < 0 && copyFreeFingerprint(to, playedEdges[j].action) == copyFree) match(i, j);
        if (!matched[i]) return nullptr;
    }
    nlohmann::json edges = nlohmann::json::array();
    for (int j = 0; j < n; ++j) {
        const auto &edge = labelEdges[labelAt[j]];
        const bool hasQ = edge.node && edge.node->simulationCount > 0;
        edges.push_back({{"bits", playedEdges[j].action.bits}, {"semantic", fingerprint(to, playedEdges[j].action)},
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
    bool gumbel = false;  // STS_AZGEN_GUMBEL_ROOT / _WHOLE_RUN_GUMBEL: root rows add priors and the Gumbel pick
    std::ostringstream *out = nullptr;
    search::SilverLeafSamples leaves;
    long long roots = 0, leafRows = 0, secondTeachers = 0, continuationRoots = 0, labelRoots = 0;
    long long labelEdgeFallbacks = 0;
    long long extraRows = 0, extraTree = 0, extraPlayout = 0;   // STS_AZGEN_EXTRA_LABELS rows
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
        if (view.label) {
            // STS_AZGEN_LABEL_SEARCH: the label search's edges are the row's; the played search's stay beside them.
            row["edges"] = labelRootEdges(*view.label, searcher);
            if (row["edges"].is_null()) {
                row["edges"] = rootEdges(*view.label);   // its own root's order: the extractor drops the root
                ++labelEdgeFallbacks;
            }
            row["inheritedVisits"] = view.labelInheritedVisits;
            row["playEdges"] = rootEdges(searcher);
            row["playInheritedVisits"] = view.inheritedVisits;
            ++labelRoots;
        }
        if (searcher.maxBackupMinVisits > 0 && searcher.rootNode().simulationCount > 0)
            row["rootQBacked"] = backedValue(searcher.rootNode(), searcher.maxBackupMinVisits);
        if (gumbel) {
            const auto &prior = searcher.rootPrior;
            auto &edges = row["edges"];
            const bool known = prior.size() == edges.size();
            for (std::size_t i = 0; i < edges.size(); ++i)
                edges[i]["prior"] = known ? nlohmann::json(prior[i]) : nlohmann::json(nullptr);
            row["gumbelChoice"] = searcher.lastGumbelEdge();
        }
        if (view.ladder) {
            nlohmann::json lad = nlohmann::json::array();
            for (const auto &p : *view.ladder)
                if (p.arm < 0) {
                    lad.push_back({{"budget", p.budget}, {"edge", p.edge}, {"sims", p.sims}, {"cpu", p.cpu}});
                } else {
                    lad.push_back({{"budget", p.budget}, {"edge", p.edge}, {"sims", p.sims}, {"cpu", p.cpu},
                                   {"policy", search::g_nativeSilverRolloutLadder.at(p.arm).name},
                                   {"priorCalls", p.priorCalls}, {"playoutActions", p.playoutActions}});
                }
            row["ladder"] = lad;
            row["mainCpu"] = view.mainCpu;
        }
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
        if (view.extras) {
            for (const auto &x : *view.extras) {
                const auto &label = *x.label;
                const auto &st = label.rootSearchState();
                nlohmann::json ex = {
                    {"kind", "extra"}, {"seed", seed}, {"variant", variant}, {"fight", fightIdx},
                    {"decision", view.decision}, {"act", view.gc.act}, {"floor", view.gc.floorNum},
                    {"room", roomStrings[static_cast<int>(view.gc.curRoom)]},
                    {"encounter", monsterEncounterEnumNames[static_cast<int>(view.live.encounter)]},
                    {"source", x.source == 0 ? "tree" : "playout"}, {"depth", x.depth},
                    {"playoutStep", x.playoutStep}, {"turn", st.turn}, {"hp", st.player.curHp},
                    {"maxHp", st.player.maxHp}, {"labelSims", x.sims}, {"cpu", x.cpu},
                    {"edges", rootEdges(label)}};
                if (x.source == 0) {
                    ex["nodeVisits"] = x.nodeVisits;
                    nlohmann::json te = nlohmann::json::array();
                    for (const auto &t : x.treeEdges) {
                        nlohmann::json e = {{"bits", t.bits}, {"visits", t.visits}, {"childSims", t.childSims},
                                            {"q", t.hasQ ? nlohmann::json(t.q) : nlohmann::json(nullptr)}};
                        if (t.hasBacked) e["qBacked"] = t.qBacked;
                        e["prior"] = t.hasPrior ? nlohmann::json(t.prior) : nlohmann::json(nullptr);
                        te.push_back(e);
                    }
                    ex["treeEdges"] = te;
                }
                if (label.maxBackupMinVisits > 0 && label.rootNode().simulationCount > 0)
                    ex["rootQBacked"] = backedValue(label.rootNode(), label.maxBackupMinVisits);
                const auto &prior = label.rootPrior;
                auto &edges = ex["edges"];
                const bool known = prior.size() == edges.size();
                for (std::size_t i = 0; i < edges.size(); ++i)
                    edges[i]["prior"] = known ? nlohmann::json(prior[i]) : nlohmann::json(nullptr);
                ex["gumbelChoice"] = label.lastGumbelEdge();
                try {
                    ex["wire"] = wireJson(st, label.searchContext());
                } catch (const std::exception &e) {
                    ex["wire"] = nullptr;
                    ex["wireError"] = e.what();
                }
                *out << ex.dump() << '\n';
                ++extraRows;
                if (x.source == 0) ++extraTree; else ++extraPlayout;
            }
        }
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
    long long labelRoots = 0, labelEdgeFallbacks = 0;
    long long extraTree = 0, extraPlayout = 0;
    std::string error;
};

// Self-play search settings of silverazgen; unset for silversynthgen.
struct AzPrior {
    int treeMinVisits = 0;
    bool rootBonus = true;
    bool production = false;  // STS_AZGEN_PRODUCTION_COMBAT: no search override
    bool labelSearch = false;  // STS_AZGEN_LABEL_SEARCH: a production label search per root
    int gumbelK = 0;           // STS_AZGEN_GUMBEL_ROOT: 0 = off
    int wholeRunGumbelK = 0;   // STS_AZGEN_WHOLE_RUN_GUMBEL: STS_SILVER_GUMBEL_ROOT's K (0 = off), no override
    std::vector<std::int64_t> ladder;   // STS_AZGEN_BUDGET_LADDER: empty = off
    std::vector<search::NativeSilverRolloutArm> rolloutArms;   // STS_AZGEN_ROLLOUT_LADDER: empty = off
    search::NativeSilverExtraLabels extraLabels;   // STS_AZGEN_EXTRA_LABELS: nodes = playouts = 0 = off
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
    recorder.gumbel = az && (az->gumbelK > 0 || az->wholeRunGumbelK > 0);
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
            search::g_nativeSilverLabelSearch = false;
            search::g_nativeSilverGumbelRootOverride.reset();
            search::g_nativeSilverBudgetLadder.clear();
            search::g_nativeSilverRolloutLadder.clear();
            search::g_nativeSilverExtraLabels = {};
        }
    } hooks;
    if (az && !az->production) {
        // Every fight of the run (recorded or not) plays the self-play search.
        search::g_nativeSilverRootPriorOverride = true;
        search::g_nativeSilverTreePriorOverride = az->treeMinVisits;
        search::g_nativeSilverRootPriorBonusOff = !az->rootBonus;
    }
    if (az && az->labelSearch) search::g_nativeSilverLabelSearch = true;
    if (az) search::g_nativeSilverBudgetLadder = az->ladder;
    if (az) search::g_nativeSilverRolloutLadder = az->rolloutArms;
    if (az) search::g_nativeSilverExtraLabels = az->extraLabels;
    if (az && az->gumbelK > 0) {
        // Every fight of the run (recorded or not) plays the Gumbel root.
        search::SilverSearcher::GumbelRoot g;
        g.k = az->gumbelK;
        search::g_nativeSilverGumbelRootOverride = g;
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
    result.labelRoots = recorder.labelRoots;
    result.labelEdgeFallbacks = recorder.labelEdgeFallbacks;
    result.extraTree = recorder.extraTree;
    result.extraPlayout = recorder.extraPlayout;
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
    // STS_AZGEN_WHOLE_RUN_GUMBEL replays bestbench's whole-run Gumbel arm, whose env has the learned stop on: the stop
    // itself is inert under the whole-run Gumbel root, but it gates Act 4 strong (ADR-0060), which that arm plays.
    const int wholeRunK = wholeRunGumbelK();
    if (!search::nativeSilverBackendInstalled() || !search::nativeSilverExactRootBudgets()
            || search::nativeSilverAdaptiveEnabled() || (search::nativeSilverLearnedStopEnabled() && wholeRunK == 0))
        throw std::runtime_error("silverazgen: requires flat exact-budget native Silver (the learned stop only with"
                                 " STS_AZGEN_WHOLE_RUN_GUMBEL=1)");
    if (search::nativeSilverReuseCap() != 32768)
        throw std::runtime_error("silverazgen: reuse cap differs from the frozen 32k");
    const bool chainOoc = productionOoc();
    const bool prodCombat = productionCombat();
    if (prodCombat && (rootBonus != 1 || treeMinVisits != search::nativeSilverTreePriorMinVisits()))
        throw std::runtime_error("silverazgen: STS_AZGEN_PRODUCTION_COMBAT=1 requires ROOT_BONUS 1 and TREE_MIN_VISITS"
                                 " equal to STS_SILVER_TREE_PRIOR_MIN_VISITS");
    const bool label = labelSearch();
    if (label && (!prodCombat || search::nativeSilverLeafSettings().leafHead.empty()))
        throw std::runtime_error("silverazgen: STS_AZGEN_LABEL_SEARCH=1 requires STS_AZGEN_PRODUCTION_COMBAT=1 and"
                                 " STS_SILVER_LEAF_HEAD");
    if (label && focus) throw std::runtime_error("silverazfocusgen: STS_AZGEN_LABEL_SEARCH is silverazgen only");
    const int gumbelK = gumbelRootK();
    if (gumbelK > 0 && (!prodCombat || label || focus))
        throw std::runtime_error("silverazgen: STS_AZGEN_GUMBEL_ROOT requires STS_AZGEN_PRODUCTION_COMBAT=1, no"
                                 " STS_AZGEN_LABEL_SEARCH and is silverazgen only");
    if (wholeRunK > 0 && (!prodCombat || label || focus || gumbelK > 0))
        throw std::runtime_error("silverazgen: STS_AZGEN_WHOLE_RUN_GUMBEL requires STS_AZGEN_PRODUCTION_COMBAT=1, no"
                                 " STS_AZGEN_GUMBEL_ROOT, no STS_AZGEN_LABEL_SEARCH and is silverazgen only");
    const int wholeRunMb = wholeRunK > 0 ? positiveEnvInt("STS_SILVER_GUMBEL_ROOT_MAX_BACKUP") : 0;
    const std::vector<std::int64_t> ladder = budgetLadder();
    if (!ladder.empty() && (wholeRunK == 0 || focus))
        throw std::runtime_error("silverazgen: STS_AZGEN_BUDGET_LADDER requires STS_AZGEN_WHOLE_RUN_GUMBEL=1 and is"
                                 " silverazgen only");
    const auto rolloutArms = rolloutLadder();
    if (!rolloutArms.empty() && (wholeRunK == 0 || focus))
        throw std::runtime_error("silverazgen: STS_AZGEN_ROLLOUT_LADDER requires STS_AZGEN_WHOLE_RUN_GUMBEL=1 and is"
                                 " silverazgen only");
    const nlohmann::json studentInfo = loadRolloutStudents(rolloutArms);
    const auto extras = extraLabels();
    const bool extrasOn = extras.nodes + extras.playouts > 0;
    if (extrasOn && (wholeRunK == 0 || focus))
        throw std::runtime_error("silverazgen: STS_AZGEN_EXTRA_LABELS requires STS_AZGEN_WHOLE_RUN_GUMBEL=1 and is"
                                 " silverazgen only");
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
        + "-rb" + std::to_string(rootBonus) + (prodCombat ? "-prod" : "") + (label ? "-headplay" : "")
        + (gumbelK > 0 ? "-gsh" + std::to_string(gumbelK) : "")
        + (wholeRunK > 0 ? "-wrg" + std::to_string(wholeRunK) + "mb" + std::to_string(wholeRunMb) : "")
        + (ladder.empty() ? "" : "-lad" + std::to_string(ladder.size()))
        + (rolloutArms.empty() ? "" : "-rl" + std::to_string(rolloutArms.size()))
        + (extrasOn ? "-xl" + std::to_string(extras.nodes) + "n" + std::to_string(extras.playouts) + "p"
                      + std::to_string(extras.sims) : "")
        + "-" + priorSha.substr(0, 8);
    const AzPrior az{treeMinVisits, rootBonus == 1, prodCombat, label, gumbelK, wholeRunK, ladder, rolloutArms,
                     extras};
    // Under the self-play overrides Silver plays no prior playouts (NativeSilverBackend skips them).
    nlohmann::json silverLeaf = effectiveSilverLeafSpecification();
    if (!prodCombat && silverLeaf.contains("prior_playout_rooms")) silverLeaf["prior_playout_rooms"] = "none";
    long long roots = 0, fights = 0, invalidFights = 0, labelRoots = 0, labelEdgeFallbacks = 0;
    long long extraTree = 0, extraPlayout = 0;
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
            labelRoots += result.labelRoots;
            labelEdgeFallbacks += result.labelEdgeFallbacks;
            extraTree += result.extraTree;
            extraPlayout += result.extraPlayout;
            if (result.complete) ++completed;
            seeds.push_back({{"seed", seed}, {"complete", result.complete}, {"error", result.error},
                             {"fights", result.fights}, {"roots", result.roots}});
        }
    }
    rows.close();
    nlohmann::json manifest = {
        {"schemaVersion", "silver_az_v1"}, {"variant", variant}, {"teacherId", teacherId},
        {"producerGitSha", trainingExecutableGitSha()},
        {"producerExecutableSha256", fileSha256(g_mainBinaryPath)},
        {"silverLeaf", silverLeaf},
        {"prior", {{"path", priorPath}, {"sha256", priorSha}, {"model", prior.description()},
                   {"weight", search::nativeSilverRootPriorWeight()}, {"treeMinVisits", treeMinVisits},
                   {"rootBonus", rootBonus == 1}}},
        {"environment", environment}, {"oocPolicy", effectiveOocPolicySpecification()},
        {"oocPlay", chainOoc ? "production_chain" : "generator_rules"},
        {"combat", prodCombat ? "production" : "selfplay_overrides"},
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
    // Recorded only when on, so other manifests keep their keys.
    if (label)
        manifest["labelSearch"] = {{"rows", "edges = production Silver without the leaf head; playEdges = played"},
                                   {"play", "leaf_head"}, {"budget", sims}, {"labelRoots", labelRoots},
                                   {"edgeFallbacks", labelEdgeFallbacks}};
    if (gumbelK > 0) {
        const search::SilverSearcher::GumbelRoot g;
        manifest["gumbelRoot"] = {{"k", gumbelK}, {"cVisit", g.cVisit}, {"cScale", g.cScale}, {"budget", sims},
                                  {"rows", "edges[].prior = root prior; gumbelChoice = the Gumbel pick's edge"}};
    }
    if (wholeRunK > 0) {
        const search::SilverSearcher::GumbelRoot g;
        manifest["gumbelRoot"] = {{"k", wholeRunK}, {"cVisit", g.cVisit}, {"cScale", g.cScale}, {"budget", sims},
                                  {"source", "whole-run STS_SILVER_GUMBEL_ROOT (no override)"},
                                  {"maxBackup", wholeRunMb}, {"act4Strong", search::nativeSilverAct4Strong()},
                                  {"rows", "edges[].prior = root prior; gumbelChoice = the Gumbel pick's edge; "
                                           "edges[].qBacked / rootQBacked = max-backed values when maxBackup > 0"}};
    }
    if (!ladder.empty())
        manifest["budgetLadder"] = {{"budgets", ladder},
                                    {"rows", "ladder[] = {budget, edge, sims, cpu}: a fresh Gumbel root search of the"
                                             " root per budget after the played one; mainCpu = the played search's"
                                             " thread seconds"}};
    if (!rolloutArms.empty()) {
        nlohmann::json arms = nlohmann::json::array();
        for (const auto &a : rolloutArms) arms.push_back(a.name);
        manifest["rolloutLadder"] = {{"arms", arms}, {"students", studentInfo},
                                     {"rows", "ladder[] entries with `policy`: a fresh Gumbel root search of a"
                                              " prior-playout root with that playout policy and budget; priorCalls ="
                                              " rolloutPrior evaluations, playoutActions = playout actions"}};
    }
    if (extrasOn)
        manifest["extraLabels"] = {{"nodes", extras.nodes}, {"playouts", extras.playouts}, {"sims", extras.sims},
                                   {"minVisits", extras.minVisits}, {"treeRows", extraTree},
                                   {"playoutRows", extraPlayout},
                                   {"rows", "kind extra: a fresh Gumbel root search (labelSims) of an interior tree"
                                            " node (source tree, treeEdges = the played tree's edges there) or a"
                                            " playout state (source playout) of the root above it"}};
    std::ofstream mf(manifestPath);
    if (!mf) throw std::runtime_error("silverazgen: cannot write manifest");
    mf << manifest.dump(2) << '\n';
    std::cout << "silverazgen variant=" << variant << " teacher=" << teacherId << " completed=" << completed
              << '/' << nSeeds << " fights=" << fights << " roots=" << roots;
    if (label) std::cout << " labelRoots=" << labelRoots << " labelEdgeFallbacks=" << labelEdgeFallbacks;
    std::cout << " -> " << rowsPath << '\n';
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
// Act 4 (card misc reset unless the line gives "deckMisc", one value per card; relic counters reset unless the line
// gives "relicData", one value per relic,
// e.g. an unused Lizard Tail; "bottleIdxs" [attack, skill, power] deck indices bottle those cards; an
// approximation shared by all arms). "Strike"/"Defend" are Ironclad's (STRIKE_RED/DEFEND_RED). Copy r of every
// arm shares the battle seed (SEED_OFFSET + state * REPLICATES + r) and the planner seed, so arms
// differ only in the budget. One CSV row per (state, replicate, arm). STS_ACT4REPLAY_COMBAT=known swaps Silver for the
// research-only known-RNG searcher (ADR-TBD); the last column records the regime.
// STS_ACT4REPLAY_BUDGET=learned (2026-10-30) replaces the flat exact budget with the whole-run learned stop outside
// Act 4 strong: STS_SILVER_LEARNED_STOP=1, STS_SILVER_ACT4_STRONG=0, STS_SILVER_EXACT_ROOT_BUDGETS=0 (one-action
// roots are committed without search), an optional STS_SILVER_LEARNED_STOP_BOSS_MAX extension; SIMS is then only a
// row label. The budget column records the policy.
namespace {

GameContext act4ReplayContext(const nlohmann::json &s, std::uint64_t seed, MonsterEncounter enc) {
    static const auto cardIds = [] {
        std::map<std::string, CardId> m;
        // Later ids win: the duplicated starter names resolve to Ironclad's *_RED variants, the last of each group.
        for (int i = 1; i < static_cast<int>(std::size(cardNames)); ++i) m[cardNames[i]] = static_cast<CardId>(i);
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
    // Optional "deckMisc" (one value per deck card) restores Card::misc, e.g. Searing Blow's upgrade count.
    if (s.contains("deckMisc")) {
        const auto misc = s.at("deckMisc").get<std::vector<int>>();
        if (static_cast<int>(misc.size()) != gc.deck.size())
            throw std::runtime_error("act4replay: deckMisc must give one value per deck card");
        for (int i = 0; i < gc.deck.size(); ++i) gc.deck.cards[i].misc = static_cast<std::int16_t>(misc[i]);
    }
    gc.relics.relics.clear();
    const auto relicData = s.value("relicData", std::vector<int>{});
    if (!relicData.empty() && relicData.size() != s.at("relics").size())
        throw std::runtime_error("act4replay: relicData must give one value per relic");
    std::size_t relicIndex = 0;
    for (const auto &entry : s.at("relics")) {
        const auto name = entry.get<std::string>();
        int id = -1;
        for (int i = 0; i < static_cast<int>(std::size(relicEnumNames)) - 1; ++i)
            if (name == relicEnumNames[i]) id = i;
        if (id < 0) throw std::runtime_error("act4replay: unknown relic " + name);
        gc.relics.add({static_cast<RelicId>(id), relicData.empty() ? 0 : relicData[relicIndex]});
        ++relicIndex;
    }
    if (s.contains("bottleIdxs")) {
        const auto bottles = s.at("bottleIdxs").get<std::vector<int>>();
        if (bottles.size() != 3) throw std::runtime_error("act4replay: bottleIdxs must have 3 entries");
        for (int type = 0; type < 3; ++type) {
            if (bottles[type] < 0) continue;
            if (bottles[type] >= gc.deck.size()) throw std::runtime_error("act4replay: bottle index out of range");
            gc.deck.bottleCard(bottles[type], static_cast<CardType>(type));
        }
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
    // STS_ACT4REPLAY_BUDGET: unset or "flat" keeps the flat exact budget; "learned" runs the learned stop.
    const char *budgetEnv = std::getenv("STS_ACT4REPLAY_BUDGET");
    const std::string budgetPolicy = budgetEnv ? budgetEnv : "flat";
    if (budgetPolicy != "flat" && budgetPolicy != "learned")
        throw std::runtime_error("act4replay: STS_ACT4REPLAY_BUDGET must be flat or learned");
    const bool learned = budgetPolicy == "learned";
    std::map<std::string, std::string> required = {
        {"STS_FAIR", "1"}, {"STS_SILVER_SEARCH", "1"}, {"STS_SILVER_EXACT_ROOT_BUDGETS", learned ? "0" : "1"},
        {"STS_SILVER_REUSE_CAP_MODE", "allocated"}, {"STS_SILVER_ADAPTIVE", "0"}, {"STS_SILVER_VNET_LEAF_DIRECT", "0"},
        {"STS_SILVER_LEARNED_STOP", learned ? "1" : "0"}};
    if (learned) {
        required["STS_SILVER_ACT4_STRONG"] = "0";
        required["STS_SILVER_LEARNED_STOP_BOSS_FALLBACK"] = "0";
    }
    for (const auto &[name, value] : required) {
        const char *actual = std::getenv(name.c_str());
        if (!actual || value != actual) throw std::runtime_error("act4replay: requires " + name + "=" + value);
    }
    if (const char *single = std::getenv("STS_SILVER_SEARCH_SINGLETON_ROOTS"); learned && single && std::atoi(single) != 0)
        throw std::runtime_error("act4replay: learned budget commits one-action roots; unset STS_SILVER_SEARCH_SINGLETON_ROOTS");
    if (!search::nativeSilverBackendInstalled() || search::nativeSilverAdaptiveEnabled()
            || search::nativeSilverExactRootBudgets() == learned || search::nativeSilverLearnedStopEnabled() != learned)
        throw std::runtime_error(learned ? "act4replay: learned budget requires learned-stop native Silver"
                                         : "act4replay: requires flat exact-budget native Silver");

    // STS_ACT4REPLAY_COMBAT=known: research-only known-RNG combat (KnownRngSearcher, P300's stage-value search). Its rows are a
    // separate series (ADR-0002) and carry regime=known_rng; unset or "fair" keeps native Silver.
    const char *combatEnv = std::getenv("STS_ACT4REPLAY_COMBAT");
    const std::string combat = combatEnv ? combatEnv : "fair";
    if (combat != "fair" && combat != "known")
        throw std::runtime_error("act4replay: STS_ACT4REPLAY_COMBAT must be fair or known");
    const bool knownRng = combat == "known";
    const char *regime = knownRng ? "known_rng" : "fair";
    if (learned && knownRng)
        throw std::runtime_error("act4replay: STS_ACT4REPLAY_BUDGET=learned needs STS_ACT4REPLAY_COMBAT=fair");
    // STS_ACT4REPLAY_CHAIN=heart (research, 2026-10-30): a Shield & Spear state that is won goes straight on to the
    // Heart from the end state (HP, potions, relic counters via exitBattle; no S&S rewards), same budget policy.
    const char *chainEnv = std::getenv("STS_ACT4REPLAY_CHAIN");
    const std::string chainName = chainEnv ? chainEnv : "";
    if (!chainName.empty() && chainName != "heart")
        throw std::runtime_error("act4replay: STS_ACT4REPLAY_CHAIN must be unset or heart");
    const bool chain = chainName == "heart";
    if (chain && knownRng) throw std::runtime_error("act4replay: STS_ACT4REPLAY_CHAIN=heart needs STS_ACT4REPLAY_COMBAT=fair");
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
            "cpuSeconds,regime,budget" << (chain ? ",ssIncenseCounter,heartValid,heartWon,heartHp,heartTurns,heartCpuSeconds" : "")
         << '\n';
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
            if (chain && enc != MonsterEncounter::SHIELD_AND_SPEAR)
                throw std::runtime_error("act4replay: STS_ACT4REPLAY_CHAIN=heart needs SHIELD_AND_SPEAR states");
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
                if (knownRng) {
                    bc.init(copy);
                    search::playoutBattleKnownRng(bc, budget, agent.bossSimulationMultiplier);
                } else {
                    agent.playoutBattle(copy, bc);
                }
                const double cpu = static_cast<double>(threadCpuNanos() - t0) / 1e9;
                search::g_nativeSilverPlannerSeedOverride.reset();
                const bool decided = bc.outcome != Outcome::UNDECIDED;
                const bool won = bc.outcome == Outcome::PLAYER_VICTORY;
                const bool valid = trainingRunValid(decided);
                std::ostringstream row;   // written only once the whole row (and any chained Heart) is done
                row << si << ',' << s.value("id", std::string()) << ',' << encName << ',' << r << ',' << budget << ','
                    << battleSeed << ',' << preHp << ',' << preMaxHp << ',' << prePotions << ',' << (valid ? 1 : 0)
                    << ',' << (won ? 1 : 0) << ',' << (won ? bc.player.curHp : 0) << ',' << bc.potionCount << ','
                    << bc.turn << ',' << std::setprecision(6) << cpu << ',' << regime << ',' << budgetPolicy;
                if (chain) {
                    // -1 = no Incense Burner; the Heart columns are 0 unless S&S was won.
                    const int counter = bc.player.hasRelic<RelicId::INCENSE_BURNER>() ? bc.player.incenseBurnerCounter : -1;
                    bool heartValid = false, heartWon = false;
                    int heartHp = 0, heartTurns = 0;
                    double heartCpu = 0;
                    if (valid && won) {
                        copy.regainControlAction = [](GameContext &) {};   // no S&S rewards
                        bc.exitBattle(copy);
                        copy.curMapNodeY = 3;
                        copy.floorNum = 56;
                        copy.curRoom = Room::BOSS;
                        copy.enterBattle(MonsterEncounter::THE_HEART);
                        trainingRunStart();
                        search::g_nativeSilverPlannerSeedOverride = key(battleSeed, si, 0xA48, r);
                        BattleContext heart;
                        const auto h0 = threadCpuNanos();
                        agent.playoutBattle(copy, heart);
                        heartCpu = static_cast<double>(threadCpuNanos() - h0) / 1e9;
                        search::g_nativeSilverPlannerSeedOverride.reset();
                        heartValid = trainingRunValid(heart.outcome != Outcome::UNDECIDED);
                        heartWon = heart.outcome == Outcome::PLAYER_VICTORY;
                        heartHp = heartWon ? heart.player.curHp : 0;
                        heartTurns = heart.turn;
                    }
                    row << ',' << counter << ',' << (heartValid ? 1 : 0) << ',' << (heartWon ? 1 : 0) << ',' << heartHp
                        << ',' << heartTurns << ',' << std::setprecision(6) << heartCpu;
                }
                out << row.str() << '\n';
            }
        } catch (const std::exception &e) {
            search::g_nativeSilverPlannerSeedOverride.reset();
            out << si << ',' << s.value("id", std::string()) << ",ERROR," << r << ",0,0,0,0,0,0,0,0,0,0,0," << regime << ',' << budgetPolicy << " # " << e.what() << '\n';
        }
        #pragma omp critical(act4_replay_write)
        {
            rows << out.str();
            rows.flush();
        }
    }
    std::cout << "act4replay states=" << nStates << " replicates=" << replicates << " -> " << rowsPath << '\n';
}
