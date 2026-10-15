#include "ooc_selective_silver_sampler.h"

#include "sim/search/CombatValueNet.h"
#include "sim/search/NativeSilverBackend.h"
#include "sim/search/OocMctsPlanner.h"
#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/SimHealth.h"

#include <iostream>
#include <optional>
#include <stdexcept>
#include <tuple>
#include <utility>

namespace one_combat {
namespace {
namespace S = sts::search;
using Outcome = CombatRuntimeSample::Outcome;

[[noreturn]] void unsupported(const std::string &reason) {
    throw S::OocSearchUnsupported("audit_native_silver:" + reason);
}

struct NativeSeeds { std::uint64_t planner, agent; };
NativeSeeds redrawNativeFuture(sts::GameContext &gc, std::mt19937_64 &rng) {
    // Ordinary BattleContext::init resets four streams from seed+floor; the
    // Colosseum continuation instead retains the six carried streams.
    gc.seed = rng();
    for (auto stream : {&gc.aiRng, &gc.cardRandomRng, &gc.miscRng,
            &gc.monsterHpRng, &gc.potionRng, &gc.shuffleRng}) {
        const auto counter = stream->counter;
        *stream = sts::Random(rng());
        stream->counter = counter;
    }
    return {rng(), rng()};
}

struct NativeScope {
    decltype(S::g_nativeSilverRootPriorOverride) root = S::g_nativeSilverRootPriorOverride;
    decltype(S::g_nativeSilverTreePriorOverride) tree = S::g_nativeSilverTreePriorOverride;
    decltype(S::g_nativeSilverPlannerSeedOverride) planner = S::g_nativeSilverPlannerSeedOverride;
    decltype(S::g_nativeSilverBudgetOverride) budget = S::g_nativeSilverBudgetOverride;
    decltype(S::g_nativeSilverSearchParamOverride) params = S::g_nativeSilverSearchParamOverride;
    const S::CombatValueNet *net = S::g_nativeSilverPriorNetOverride;
    bool bonusOff = S::g_nativeSilverRootPriorBonusOff;
    bool disallow = S::g_disallowImaginedCombat;
    S::NativeSilverCombatStats stats = S::g_nativeSilverCombatStats;
    decltype(sts::g_onBattleExitRaw) raw = std::move(sts::g_onBattleExitRaw);
    decltype(sts::g_onBattleExitPersistent) persistent = std::move(sts::g_onBattleExitPersistent);
    decltype(S::g_onCombatDecision) decision = std::move(S::g_onCombatDecision);
    decltype(S::g_onGameActionExecute) action = std::move(S::g_onGameActionExecute);
    decltype(S::g_nativeSilverRootObserver) rootObserver = std::move(S::g_nativeSilverRootObserver);
    decltype(S::g_nativeSilverLeafSamples) leafSamples = S::g_nativeSilverLeafSamples;

    NativeScope(bool usePrior, const S::CombatValueNet *policy, std::uint64_t seed) {
        S::g_nativeSilverRootPriorOverride = usePrior;
        S::g_nativeSilverTreePriorOverride = usePrior ? std::optional<int>(8) : std::nullopt;
        S::g_nativeSilverPlannerSeedOverride = seed;
        S::g_nativeSilverBudgetOverride = S::NativeSilverBudgetOverride{
            S::NativeSilverBudgetOverride::Policy::Flat, false};
        S::g_nativeSilverSearchParamOverride.reset();
        S::g_nativeSilverPriorNetOverride = usePrior ? policy : nullptr;
        S::g_nativeSilverRootPriorBonusOff = false;
        S::g_disallowImaginedCombat = false;
        sts::g_onBattleExitRaw = {};
        sts::g_onBattleExitPersistent = {};
        S::g_onCombatDecision = {};
        S::g_onGameActionExecute = {};
        S::g_nativeSilverRootObserver = {};
        S::g_nativeSilverLeafSamples = nullptr;
    }
    ~NativeScope() {
        S::g_nativeSilverRootPriorOverride = root;
        S::g_nativeSilverTreePriorOverride = tree;
        S::g_nativeSilverPlannerSeedOverride = planner;
        S::g_nativeSilverBudgetOverride = budget;
        S::g_nativeSilverSearchParamOverride = params;
        S::g_nativeSilverPriorNetOverride = net;
        S::g_nativeSilverRootPriorBonusOff = bonusOff;
        S::g_disallowImaginedCombat = disallow;
        S::g_nativeSilverCombatStats = stats;
        sts::g_onBattleExitRaw = std::move(raw);
        sts::g_onBattleExitPersistent = std::move(persistent);
        S::g_onCombatDecision = std::move(decision);
        S::g_onGameActionExecute = std::move(action);
        S::g_nativeSilverRootObserver = std::move(rootObserver);
        S::g_nativeSilverLeafSamples = leafSamples;
    }
};

Outcome terminalOutcome(const sts::BattleContext &bc, int decisions, int before, int after) {
    // undefinedBehaviorEvoked only marks a played Discovery (known card
    // limitation, not a health failure); source and live combats accept it.
    if (before != after) unsupported("simulator_health_failure");
    if (bc.outcome == sts::Outcome::UNDECIDED) unsupported("undecided_combat");
    // A valid start-of-combat effect may finish before the first decision.
    if (decisions == 0 && bc.turn != 0) unsupported("missing_combat_decision_hook");
    if (bc.outcome == sts::Outcome::PLAYER_LOSS) {
        if (bc.player.curHp > 0 || bc.smokeBombUsed) unsupported("non_death_loss");
        return Outcome::DEATH;
    }
    if (bc.outcome != sts::Outcome::PLAYER_VICTORY || bc.player.curHp <= 0
            || bc.player.maxHp <= 0 || bc.player.curHp > bc.player.maxHp)
        unsupported("invalid_surviving_terminal");
    return bc.smokeBombUsed ? Outcome::ESCAPE : Outcome::VICTORY;
}

CombatRuntimeSample checkedRaw(Outcome outcome, const sts::BattleContext &bc,
        const std::optional<CombatTransitionPersistentState> &raw, int captures) {
    if (captures != 1 || !raw) unsupported("raw_capture_count");
    // exitBattle applies victory healing before RAW capture; RAW HP need not
    // equal terminal BattleContext HP (e.g. Burning Blood).
    if (raw->maxHp <= 0 || raw->smokeBombUsed != bc.smokeBombUsed
            || (outcome == Outcome::DEATH ? raw->curHp > 0
                : raw->curHp <= 0 || raw->curHp > raw->maxHp))
        unsupported("raw_terminal_mismatch");
    return {outcome, *raw};
}

CombatRuntimeSample finishNativeBattle(sts::GameContext &gc, const sts::BattleContext &bc,
        Outcome outcome, int healthBefore, const std::optional<CombatTransitionPersistentState> &raw,
        const int &captures) {
    // Only RAW belongs to the combat sampler. Do not run a copied callback
    // (which may capture external state) or generate disposable rewards here;
    // applySampledCombatExit invokes the real branch continuation exactly once.
    gc.regainControlAction = [](sts::GameContext &) {};
    bc.exitBattle(gc);
    if (healthBefore != S::g_simHealthFailureCount) unsupported("exit_health_failure");
    return checkedRaw(outcome, bc, raw, captures);
}

class NativeSampler final : public CombatTransitionSampler {
    int simulations_;
    const S::CombatValueNet *net_;
    bool prior_;
public:
    NativeSampler(int simulations, const S::CombatValueNet *net, bool prior)
        : simulations_(simulations), net_(net), prior_(prior) {}
    CombatRuntimeSupport support(const sts::GameContext &gc, const CombatPredictorInputV1 &) const override {
        if (gc.ascension != 20 || gc.screenState != sts::ScreenState::BATTLE
                || gc.outcome != sts::GameOutcome::UNDECIDED
                || gc.info.encounter == sts::MonsterEncounter::INVALID
                || gc.curHp <= 0 || gc.curHp > gc.maxHp)
            return {false, "audit_native_silver:invalid_battle_input"};
        return {true, {}};
    }
    bool modelsSmokeBombEscape() const override { return true; }
    CombatRuntimeSample sample(const sts::GameContext &source, const CombatPredictorInputV1 &input,
            std::mt19937_64 &rng) const override {
        const auto allowed = support(source, input);
        if (!allowed.supported) throw S::OocSearchUnsupported(allowed.reason);
        auto gc = source;
        if (source.map) gc.map = std::make_shared<sts::Map>(*source.map);
        const auto seeds = redrawNativeFuture(gc, rng);
        NativeScope scope(prior_, net_, seeds.planner);
        std::optional<CombatTransitionPersistentState> raw;
        int captures = 0, decisions = 0;
        sts::g_onBattleExitRaw = [&](const sts::BattleContext &, sts::GameContext &state) {
            ++captures;
            if (!raw) raw = captureCombatTransitionState(state);
        };
        S::g_onCombatDecision = [&](const sts::BattleContext &) { ++decisions; };
        S::ScumSearchAgent2 agent;
        agent.simulationCountBase = simulations_;
        agent.bossSimulationMultiplier = 1;
        agent.rng.seed(static_cast<std::default_random_engine::result_type>(seeds.agent));
        const int healthBefore = S::g_simHealthFailureCount;
        sts::BattleContext bc;
        try {
            agent.playoutBattle(gc, bc);
            const auto outcome = terminalOutcome(bc, decisions, healthBefore, S::g_simHealthFailureCount);
            return finishNativeBattle(gc, bc, outcome, healthBefore, raw, captures);
        } catch (const S::OocSearchUnsupported &) {
            throw;
        } catch (const std::exception &error) {
            unsupported(error.what());
        }
    }
};

class NonceSampler final : public CombatTransitionSampler {
    std::shared_ptr<const CombatTransitionSampler> inner_;
public:
    explicit NonceSampler(std::shared_ptr<const CombatTransitionSampler> inner) : inner_(std::move(inner)) {}
    CombatRuntimeSupport support(const sts::GameContext &gc, const CombatPredictorInputV1 &input) const override {
        return inner_->support(gc, input);
    }
    CombatRuntimeSupport forecastSupport(const CombatPredictorInputV1 &input) const override {
        return inner_->forecastSupport(input);
    }
    CombatTransitionExpectation forecastExpectation(const CombatPredictorInputV1 &input) const override {
        return inner_->forecastExpectation(input);
    }
    CombatTransitionExpectation expectation(const sts::GameContext &gc, const CombatPredictorInputV1 &input) const override {
        return inner_->expectation(gc, input);
    }
    bool modelsSmokeBombEscape() const override { return inner_->modelsSmokeBombEscape(); }
    CombatRuntimeSample sample(const sts::GameContext &gc, const CombatPredictorInputV1 &input,
            std::mt19937_64 &rng) const override {
        std::mt19937_64 privateRng(rng());
        return inner_->sample(gc, input, privateRng);
    }
};
}

std::shared_ptr<const CombatTransitionSampler> auditNativeSilverSampler(
        int simulations, const S::CombatValueNet *net, bool prior) {
    if (!((simulations == 2500 && prior) || (simulations == 10000 && !prior)))
        throw std::invalid_argument("audit_native_silver:requires_prior2500_or_plain10k");
    if (!S::nativeSilverBackendInstalled() || !S::nativeSilverExactRootBudgets())
        throw std::runtime_error("audit_native_silver:requires_native_exact_backend");
    if (prior && (!net || !net->loaded() || !net->isPolicy || S::nativeSilverRootPriorPath().empty()
            || S::nativeSilverRootPriorWeight() != 400))
        throw std::runtime_error("audit_native_silver:requires_loaded_policy_and_weight400");
    return std::make_shared<NativeSampler>(simulations, prior ? net : nullptr, prior);
}

std::shared_ptr<const CombatTransitionSampler> auditNonceSampler(
        std::shared_ptr<const CombatTransitionSampler> sampler) {
    if (!sampler) throw std::invalid_argument("audit_nonce:missing_sampler");
    return std::make_shared<NonceSampler>(std::move(sampler));
}

int auditNativeSilverSamplerSelfTest() {
    const auto require = [](bool ok, const char *message) {
        if (!ok) throw std::runtime_error(std::string("audit sampler selftest: ") + message);
    };
    try {
        sts::GameContext source(sts::CharacterClass::IRONCLAD, 17, 20);
        source.screenState = sts::ScreenState::BATTLE;
        source.curRoom = sts::Room::MONSTER;
        source.floorNum = 1;
        source.info.encounter = sts::MonsterEncounter::CULTIST;
        auto first = source, second = source;
        std::mt19937_64 left(23), right(23);
        const auto a = redrawNativeFuture(first, left), b = redrawNativeFuture(second, right);
        require(source.seed == 17 && first.seed != source.seed && first.seed == second.seed
            && a.planner == b.planner && a.agent == b.agent && a.planner != a.agent,
            "native battle/planner/agent seeds are detached and paired");
        const auto originalPersistent = captureCombatTransitionState(source);
        const auto redrawnPersistent = captureCombatTransitionState(first);
        for (std::size_t i = 0; i < originalPersistent.combatRng.size(); ++i)
            require(originalPersistent.combatRng[i].counter == redrawnPersistent.combatRng[i].counter,
                "carried combat counters preserved before native initialization");
        auto publicState = [](const sts::GameContext &gc) {
            auto value = combatTransitionStateJson(captureCombatTransitionState(gc));
            value.erase("combatRng"); return value;
        };
        require(publicState(source) == publicState(first), "redraw preserves persistent combat inputs");
        sts::BattleContext control, pairedA, pairedB;
        control.init(source, source.info.encounter);
        pairedA.init(first, first.info.encounter);
        pairedB.init(second, second.info.encounter);
        const auto streams = [](const sts::BattleContext &bc) {
            return std::array<const sts::Random *, 6>{&bc.aiRng, &bc.cardRandomRng, &bc.miscRng,
                &bc.monsterHpRng, &bc.potionRng, &bc.shuffleRng};
        };
        const auto original = streams(control), one = streams(pairedA), two = streams(pairedB);
        for (std::size_t i = 0; i < one.size(); ++i) {
            const auto bits = [](const sts::Random *r) { return std::make_tuple(r->seed0, r->seed1, r->counter); };
            require(bits(one[i]) == bits(two[i]) && bits(one[i]) != bits(original[i]),
                "initialized native streams change from original and match paired arms");
        }
        // Synthetic terminal classification covers genuine deaths/escapes and
        // rejects simulator failures rather than converting them to zero.
        control.outcome = sts::Outcome::PLAYER_LOSS; control.player.curHp = 0;
        require(terminalOutcome(control, 1, 0, 0) == Outcome::DEATH, "healthy death accepted");
        control.outcome = sts::Outcome::PLAYER_VICTORY; control.player.curHp = 20; control.smokeBombUsed = true;
        require(terminalOutcome(control, 1, 0, 0) == Outcome::ESCAPE, "healthy escape accepted");
        const auto rejects = [&](auto call, const char *message) {
            bool rejected = false;
            try { call(); } catch (const S::OocSearchUnsupported &) { rejected = true; }
            require(rejected, message);
        };
        rejects([&] { terminalOutcome(control, 1, 0, 1); }, "health failures rejected");
        control.undefinedBehaviorEvoked = true;
        require(terminalOutcome(control, 1, 0, 0) == Outcome::ESCAPE, "played Discovery accepted");
        control.undefinedBehaviorEvoked = false;
        rejects([&] { checkedRaw(Outcome::ESCAPE, control, {}, 0); }, "missing RAW rejected");

        NativeScope restore(false, nullptr, 0);
        {
            std::optional<CombatTransitionPersistentState> raw;
            int captures = 0, continuationCalls = 0;
            auto detached = source;
            detached.regainControlAction = [&](sts::GameContext &) { ++continuationCalls; };
            sts::g_onBattleExitRaw = [&](const sts::BattleContext &, sts::GameContext &gc) {
                ++captures; raw = captureCombatTransitionState(gc);
            };
            const auto sample = finishNativeBattle(detached, control, Outcome::ESCAPE,
                S::g_simHealthFailureCount, raw, captures);
            require(sample.outcome == Outcome::ESCAPE && captures == 1 && continuationCalls == 0
                && sample.rawPost.smokeBombUsed && sample.rawPost.curHp >= control.player.curHp,
                "RAW escape captured once before callback, including exit healing");
            rejects([&] { checkedRaw(Outcome::ESCAPE, control, raw, 2); }, "repeated RAW rejected");
            sts::g_onBattleExitRaw = {};
        }
        S::CombatValueNet sentinel, policy;
        S::g_nativeSilverRootPriorOverride = false; S::g_nativeSilverTreePriorOverride = 19;
        S::g_nativeSilverPlannerSeedOverride = 123;
        S::g_nativeSilverBudgetOverride = S::NativeSilverBudgetOverride{
            S::NativeSilverBudgetOverride::Policy::Adaptive, true};
        S::g_nativeSilverSearchParamOverride = S::NativeSilverSearchParams{};
        S::g_nativeSilverPriorNetOverride = &sentinel;
        S::g_nativeSilverRootPriorBonusOff = true; S::g_disallowImaginedCombat = true;
        S::g_nativeSilverCombatStats.decisions = 77;
        int callbackCalls = 0;
        sts::g_onBattleExitRaw = [&](const auto &, auto &) { ++callbackCalls; };
        sts::g_onBattleExitPersistent = [&](const auto &, auto &) { ++callbackCalls; };
        S::g_onCombatDecision = [&](const auto &) { ++callbackCalls; };
        try {
            NativeScope scoped(true, &policy, 456);
            require(S::g_nativeSilverRootPriorOverride == true && S::g_nativeSilverTreePriorOverride == 8
                && S::g_nativeSilverPlannerSeedOverride == 456 && S::g_nativeSilverPriorNetOverride == &policy
                && S::g_nativeSilverBudgetOverride->policy == S::NativeSilverBudgetOverride::Policy::Flat
                && !S::g_nativeSilverBudgetOverride->skipSingletonRoots && !S::g_nativeSilverSearchParamOverride
                && !S::g_nativeSilverRootPriorBonusOff && !S::g_disallowImaginedCombat
                && !sts::g_onBattleExitRaw && !sts::g_onBattleExitPersistent && !S::g_onCombatDecision,
                "complete native configuration and callback suppression");
            S::g_nativeSilverCombatStats.decisions = 1;
            throw std::logic_error("synthetic scope unwind");
        } catch (const std::logic_error &) {}
        require(S::g_nativeSilverRootPriorOverride == false && S::g_nativeSilverTreePriorOverride == 19
            && S::g_nativeSilverPlannerSeedOverride == 123 && S::g_nativeSilverPriorNetOverride == &sentinel
            && S::g_nativeSilverBudgetOverride->policy == S::NativeSilverBudgetOverride::Policy::Adaptive
            && S::g_nativeSilverBudgetOverride->skipSingletonRoots && S::g_nativeSilverSearchParamOverride
            && S::g_nativeSilverRootPriorBonusOff && S::g_disallowImaginedCombat
            && S::g_nativeSilverCombatStats.decisions == 77, "native overrides restored on exception");
        sts::g_onBattleExitRaw(control, source); sts::g_onBattleExitPersistent(control, source);
        S::g_onCombatDecision(control);
        require(callbackCalls == 3, "callbacks restored on exception");

        struct DrawSampler final : CombatTransitionSampler {
            int draws;
            bool fail;
            explicit DrawSampler(int n, bool reject = false) : draws(n), fail(reject) {}
            CombatRuntimeSupport support(const sts::GameContext &, const CombatPredictorInputV1 &) const override {
                return {true, "synthetic"};
            }
            CombatRuntimeSupport forecastSupport(const CombatPredictorInputV1 &) const override {
                return {true, "synthetic_forecast"};
            }
            CombatTransitionExpectation forecastExpectation(const CombatPredictorInputV1 &) const override {
                return {true, .25f, .5f, 10, {.5f, .5f}};
            }
            CombatTransitionExpectation expectation(const sts::GameContext &, const CombatPredictorInputV1 &input) const override {
                return forecastExpectation(input);
            }
            bool modelsSmokeBombEscape() const override { return true; }
            CombatRuntimeSample sample(const sts::GameContext &, const CombatPredictorInputV1 &,
                    std::mt19937_64 &rng) const override {
                for (int i = 0; i < draws; ++i) (void)rng();
                if (fail) unsupported("synthetic_resolver_failure");
                return {Outcome::DEATH, {}};
            }
        };
        const auto shortDraw = auditNonceSampler(std::make_shared<DrawSampler>(1));
        const auto longDraw = auditNonceSampler(std::make_shared<DrawSampler>(97));
        std::mt19937_64 shortOuter(31), longOuter(31), expected(31);
        CombatPredictorInputV1 input;
        (void)expected();
        require(shortDraw->sample(source, input, shortOuter).outcome == Outcome::DEATH
            && longDraw->prepare(source, input)->sample(longOuter).outcome == Outcome::DEATH
            && shortOuter == expected && longOuter == expected,
            "one outer nonce despite different resolver draw counts and prepared sampling");
        require(shortDraw->support(source, input).reason == "synthetic" && shortDraw->modelsSmokeBombEscape()
            && shortDraw->forecastSupport(input).reason == "synthetic_forecast"
            && shortDraw->forecastExpectation(input).death == .25f
            && shortDraw->expectation(source, input).winningHpHistogram == std::vector<float>({.5f, .5f}),
            "nonce wrapper preserves support, expectation and escape capability");
        const auto failed = auditNonceSampler(std::make_shared<DrawSampler>(97, true));
        std::mt19937_64 failedOuter(31);
        rejects([&] { failed->sample(source, input, failedOuter); }, "resolver failure retained");
        require(failedOuter == expected, "failed resolver still consumes exactly one outer nonce");
        std::cout << "audit native Silver sampler selftest: PASS\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n'; return 1;
    }
}
}
