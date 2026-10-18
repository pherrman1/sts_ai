#include "ooc_selective_silver_audit.h"
#include "ooc_selective_silver_sampler.h"
#include "ooc_leaf_capture.h"
#include "combat_transition_runtime.h"
#include "ooc_policy.h"
#include "run_driver.h"
#include "driver_shared.h"
#include "sim/search/CombatValueNet.h"
#include "sim/search/NativeSilverBackend.h"
#include "combat/BattleContext.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <sys/resource.h>
#include <time.h>

namespace one_combat {
namespace {
using J = nlohmann::json;
namespace S = sts::search;
void check(bool ok, const std::string &reason) { if (!ok) throw std::runtime_error("selective_audit: " + reason); }
double usage(int who) {
    rusage u{}; check(getrusage(who, &u) == 0, "CPU accounting unavailable");
    return u.ru_utime.tv_sec + u.ru_stime.tv_sec + (u.ru_utime.tv_usec + u.ru_stime.tv_usec) / 1e6;
}
struct Writer {
    FILE *file;
    explicit Writer(const std::string &path) : file(std::fopen(path.c_str(), "wx")) { check(file, "existing/unwritable output"); }
    ~Writer() { if (file) std::fclose(file); }
    void write(J row) {
        const auto s = row.dump() + "\n";
        check(std::fwrite(s.data(), 1, s.size(), file) == s.size() && std::fflush(file) == 0, "output flush failed");
    }
};
struct SourceScope {
    decltype(S::g_nativeSilverRootPriorOverride) root = S::g_nativeSilverRootPriorOverride;
    decltype(S::g_nativeSilverTreePriorOverride) tree = S::g_nativeSilverTreePriorOverride;
    decltype(S::g_nativeSilverPlannerSeedOverride) planner = S::g_nativeSilverPlannerSeedOverride;
    decltype(S::g_nativeSilverBudgetOverride) budget = S::g_nativeSilverBudgetOverride;
    decltype(S::g_nativeSilverSearchParamOverride) params = S::g_nativeSilverSearchParamOverride;
    const S::CombatValueNet *net = S::g_nativeSilverPriorNetOverride;
    bool bonus = S::g_nativeSilverRootPriorBonusOff;
    bool disallow = S::g_disallowImaginedCombat;
    decltype(t_realRunContextObserver) context = std::move(t_realRunContextObserver);
    decltype(S::g_onGameActionExecute) action = std::move(S::g_onGameActionExecute);
    decltype(sts::g_onBattleExitRaw) raw = std::move(sts::g_onBattleExitRaw);
    decltype(sts::g_onBattleExitPersistent) persistent = std::move(sts::g_onBattleExitPersistent);
    explicit SourceScope(bool imagined = false) {
        S::g_disallowImaginedCombat = imagined;
        S::g_nativeSilverRootPriorOverride = false; S::g_nativeSilverTreePriorOverride.reset();
        S::g_nativeSilverPlannerSeedOverride.reset(); S::g_nativeSilverSearchParamOverride.reset();
        S::g_nativeSilverPriorNetOverride = nullptr; S::g_nativeSilverRootPriorBonusOff = false;
        S::g_nativeSilverBudgetOverride = S::NativeSilverBudgetOverride{S::NativeSilverBudgetOverride::Policy::Flat, false};
        t_realRunContextObserver = {}; S::g_onGameActionExecute = {}; sts::g_onBattleExitRaw = {}; sts::g_onBattleExitPersistent = {};
    }
    ~SourceScope() {
        S::g_disallowImaginedCombat = disallow; S::g_nativeSilverRootPriorOverride = root; S::g_nativeSilverTreePriorOverride = tree;
        S::g_nativeSilverPlannerSeedOverride = planner; S::g_nativeSilverBudgetOverride = budget;
        S::g_nativeSilverSearchParamOverride = params; S::g_nativeSilverPriorNetOverride = net;
        S::g_nativeSilverRootPriorBonusOff = bonus; S::g_onGameActionExecute = std::move(action);
        t_realRunContextObserver = std::move(context); sts::g_onBattleExitRaw = std::move(raw); sts::g_onBattleExitPersistent = std::move(persistent);
    }
};
sts::GameContext copied(const sts::GameContext &source) {
    auto result = source;
    if (source.map) result.map = std::make_shared<sts::Map>(*source.map);
    return result;
}
// Audit-only envelope: ordinary replay callers retain their existing failure behavior.
std::string boundedError(const char *message) {
    std::string result;
    if (!message) return "missing_exception_message";
    for (std::size_t i = 0; message[i] && i < 1024; ++i) {
        const unsigned char c = message[i];
        result.push_back(c >= 32 && c <= 126 ? char(c) : '?');
    }
    return result;
}
J childEnvelope(const std::function<J()> &fn) {
    try { return {{"ok", true}, {"payload", fn()}}; }
    catch (const std::exception &e) {
        return {{"ok", false}, {"category", "std_exception"}, {"message", boundedError(e.what())}};
    } catch (...) { return {{"ok", false}, {"category", "nonstandard_exception"}, {"message", "nonstandard exception"}}; }
}
J unpackChild(const J &envelope) {
    check(envelope.is_object() && envelope.contains("ok") && envelope.at("ok").is_boolean(), "malformed child envelope");
    if (envelope.at("ok").get<bool>()) {
        check(envelope.size() == 2 && envelope.contains("payload") && envelope.at("payload").is_object(), "malformed child success");
        return envelope.at("payload");
    }
    check(envelope.size() == 3 && envelope.contains("category") && envelope.contains("message")
        && envelope.at("category").is_string() && envelope.at("message").is_string(), "malformed child error");
    const auto category = envelope.at("category").get<std::string>();
    const auto message = envelope.at("message").get<std::string>();
    check((category == "std_exception" || category == "nonstandard_exception") && message.size() <= 1024
        && std::all_of(message.begin(), message.end(), [](unsigned char c) { return c >= 32 && c <= 126; }), "malformed child error text");
    throw std::runtime_error("selective_audit:child_exception:" + category + ":" + message);
}
J stats(const S::OocMctsResult &r, const OocGameContextModel &model) {
    check(!r.aborted && r.selectedAction && r.metrics.simulations == 4096, "baseline search invalid/incomplete");
    J actions = J::array();
    for (const auto &a : r.rootActions) {
        const auto &c = model.candidate(0, a.id);
        actions.push_back({{"id", a.id}, {"key", c.key}, {"bits", c.primitive.bits},
                          {"visits", a.visits}, {"q", a.q}, {"prior", a.prior}});
    }
    const auto &m = r.metrics;
    return {{"selectedKey", model.candidate(0, *r.selectedAction).key}, {"actions", actions},
        {"work", {{"simulations", m.simulations}, {"attempts", m.simulationAttempts},
            {"transitions", m.transitionSamples}, {"leaves", m.leafEvaluations},
            {"depthSum", m.depthSum}, {"maxDepth", m.maxDepthReached}, {"combatSamples", model.combatSamples()}}}};
}
}
nlohmann::json selectiveAuditSourcePolicy() { SourceScope scope; return effectiveOocPolicySpecification(); }
int selectiveSilverAccountingSelfTest(const AuditFork &fork) {
    const double before = usage(RUSAGE_CHILDREN);
    const auto digest = fileSha256(g_mainBinaryPath);
    const double provenance = usage(RUSAGE_CHILDREN) - before;
    check(digest.size() == 64 && provenance > 0., "hash utility must contribute measured child CPU");
    std::puts("PASS selective Silver provenance utility accounting (no game seeds)");
    const auto isolated = [&](const std::function<J()> &fn) { return fork([&] { return childEnvelope(fn); }, 10000, 10); };
    check(unpackChild(isolated([] { return J{{"value", .4}}; })) == J{{"value", .4}}, "child success passthrough");
    const auto standard = isolated([]() -> J { throw std::runtime_error("native-sentinel"); });
    check(standard.at("category") == "std_exception" && standard.at("message") == "native-sentinel", "standard child exception retained");
    const auto other = isolated([]() -> J { throw 42; });
    check(other.at("category") == "nonstandard_exception", "nonstandard child exception retained");
    const auto oversized = isolated([]() -> J { throw std::runtime_error(std::string(1, char(255)) + std::string(4096, 'a')); });
    check(oversized.at("message").get<std::string>().size() == 1024 && oversized.at("message").get<std::string>().front() == '?', "error message bounded and printable");
    for (const auto &bad : {standard, other, oversized, J{{"ok", "false"}}, J{{"ok", true}}, J{{"ok", false}, {"message", "x"}}, J{{"ok", true}, {"payload", J::array()}}}) {
        bool rejected = false;
        try { (void)unpackChild(bad); } catch (const std::exception &) { rejected = true; }
        check(rejected, "child error/malformed envelope rejected");
    }
    std::puts("PASS selective Silver child exception transport (real seed-free forks)");
    return 0;
}
int runSelectiveSilverAudit(std::uint64_t seed, const std::string &planPath, const std::string &out,
    std::shared_ptr<const CombatTransitionSampler> ctm, OocAdapterOptions options, S::OocMctsConfig config,
    const AuditFork &fork) {
    Writer writer(out);
    try {
        std::ifstream input(planPath); check(bool(input), "plan unavailable"); J plan; input >> plan;
        check(plan.at("schemaVersion") == "ooc_selective_silver_plan_v1" && plan.at("silverSimulations") == 2500, "wrong plan schema/budget");
        const auto seeds = plan.at("streams").at(std::to_string(seed));
        const auto hybrid = std::dynamic_pointer_cast<const EntropicBrewFallbackCombatTransitionSampler>(ctm);
        check(hybrid && hybrid->fastRuntime().identity() == plan.at("ctmLoadedIdentity"), "wrong loaded CTM identity");
        check(options.leafCombats == 3 && options.checkpointLeaves && options.sampleNoncombat
            && !options.bossRollout && !options.screenLeaf && !options.stopAtMapCheckpoint, "wrong teacher options");
        config.allowUnqualifiedRootStop = false; config.stopAt512VisitGap20 = false; config.gapStopFraction = 0;
        config.observeRootLock = false; config.captureTree = false; config.rootCheckpointSimulations.clear();
        options.leafObserver = {}; options.priorTracePath.clear();
        const char *prior = std::getenv("STS_SILVER_ROOT_PRIOR");
        check(prior && fileSha256(prior) == "ca9bd7f25cd2fb5c3e82609c35077e1c55d40c3f9c3d27da8e87236997b33228", "wrong gen6 E");
        S::CombatValueNet net; check(net.load(prior) && net.isPolicyMlp, "prior load failure");
        auto ctmNonce = auditNonceSampler(ctm);
        auto silver = auditNonceSampler(auditNativeSilverSampler(2500, &net, true));
        auto reference = auditNonceSampler(auditNativeSilverSampler(10000, nullptr, false));
        // Include startup and provenance utility subprocesses in whole-source caps.
        constexpr double startedParent = 0., startedChildren = 0.;
        auto child = [&](const std::function<J()> &fn, int cpu = 60, int wall = 90000) {
            check(usage(RUSAGE_SELF) - startedParent <= 200, "parent CPU cap");
            check(usage(RUSAGE_CHILDREN) - startedChildren + cpu <= 1200, "child reservation exhausted");
            const double p = usage(RUSAGE_SELF), c = usage(RUSAGE_CHILDREN);
            const auto envelope = fork([&] { return childEnvelope(fn); }, wall, cpu);
            const double pc = usage(RUSAGE_SELF) - p, cc = usage(RUSAGE_CHILDREN) - c;
            check(cc <= cpu + .02 && usage(RUSAGE_CHILDREN) - startedChildren <= 1200, "child CPU cap");
            try {
                return J{{"result", unpackChild(envelope)}, {"parentCpuSeconds", pc}, {"childCpuSeconds", cc}};
            } catch (const std::exception &e) {
                writer.write({{"type", "child_failure"}, {"reason", e.what()}, {"parentCpuSeconds", pc}, {"childCpuSeconds", cc}});
                throw;
            }
        };
        SourceScope sourceConfiguration;
        J header{{"type", "header"}, {"seed", seed}, {"silverSimulations", 2500}, {"planSha256", fileSha256(planPath)},
            {"producerGitSha", std::getenv("STS_EXECUTABLE_GIT_SHA")}, {"policy", effectiveOocPolicySpecification()}, {"ctmLoadedIdentity", hybrid->fastRuntime().identity()}};
        // fileSha256 uses reaped utility children; retain their cost before any game or audit fork.
        header["provenanceChildCpuSeconds"] = usage(RUSAGE_CHILDREN);
        writer.write(std::move(header));
        const auto initialPolicy = captureOocPolicyThreadState();
        auto runSource = [&](bool audit) {
            restoreOocPolicyThreadState(initialPolicy); SourceScope sourceScope;
            const int healthBefore = S::g_simHealthFailureCount;
            J actions = J::array(), battles = J::array(), roots = J::array();
            std::array<int, 4> fights{}; std::set<int> seen;
            const sts::GameContext *sourceContext = nullptr;
            t_realRunContextObserver = [&](const sts::GameContext &gc, const PathHistory &) { sourceContext = &gc; };
            sts::g_onBattleExitRaw = [&](const sts::BattleContext &bc, sts::GameContext &gc) {
                if (&gc != sourceContext) return;
                check(bc.outcome != sts::Outcome::UNDECIDED && S::g_simHealthFailureCount == healthBefore, "invalid source battle");
                ++fights.at(gc.act);
                battles.push_back({{"act", gc.act}, {"floor", gc.floorNum}, {"outcome", int(bc.outcome)},
                    {"raw", combatTransitionStateJson(captureCombatTransitionState(gc))}});
            };
            S::g_onGameActionExecute = [&](std::uint32_t bits, const sts::GameContext *gc) {
                if (gc != sourceContext) return;
                check(gc && t_curPath, "missing source context");
                actions.push_back({{"act", gc->act}, {"floor", gc->floorNum}, {"screen", int(gc->screenState)}, {"bits", bits}, {"legalCount", gc->screenState == sts::ScreenState::MAP_SCREEN ? S::GameAction::getAllActionsInState(*gc).size() : 0},
                    {"realCombatsInAct", fights.at(gc->act)}});
                const int act = gc->act;
                if (!audit || gc->screenState != sts::ScreenState::MAP_SCREEN || gc->floorNum < 3
                    || fights.at(act) == 0 || seen.count(act)
                    || S::GameAction::getAllActionsInState(*gc).size() < 2) return;
                seen.insert(act); // selection precedes search support/results
                const auto path = *t_curPath;
                const auto policy = captureOocPolicyThreadState();
                const auto before = combatTransitionFingerprint(*gc);
                const auto publicBefore = oocLeafCandidateInput(*gc, path);
                writer.write({{"type", "root_start"}, {"seed", seed}, {"act", act}, {"decisionOrdinal", actions.size() - 1}, {"input", publicBefore}});
                const auto stream = seeds.at(std::to_string(act));
                auto search = [&]() {
                    restoreOocPolicyThreadState(policy); SourceScope isolated(true);
                    OocGameContextModel model(*gc, path, ctm, options);
                    auto cfg = config; cfg.seed = stream.at("search").at(0).get<std::uint64_t>();
                    return stats(S::OocMctsPlanner(cfg).search(model, 0, 4096), model);
                };
                auto base = child(search), control = child(search);
                check(base.at("result") == control.at("result"), "baseline exact control mismatch");
                OocGameContextModel candidates(*gc, path, ctmNonce, options);
                const auto legal = candidates.legalActions(0);
                const auto baseline = base.at("result").at("selectedKey").get<std::string>();
                auto ranks = base.at("result").at("actions").get<std::vector<J>>();
                std::sort(ranks.begin(), ranks.end(), [](const J &a, const J &b) {
                    return a.at("visits") != b.at("visits") ? a.at("visits") > b.at("visits") : a.at("key") < b.at("key");
                });
                check(ranks.size() >= 2, "selected root has fewer than two candidates");
                const auto runner = std::find_if(ranks.begin(), ranks.end(), [&](const J &a) { return a.at("key") != baseline; });
                check(runner != ranks.end(), "missing runner-up");
                std::array<OocGameContextModel::Candidate, 2> pair;
                for (int i = 0; i < 2; ++i) {
                    const std::string key = i ? runner->at("key").get<std::string>() : baseline;
                    auto found = std::find_if(legal.begin(), legal.end(), [&](const auto &a) { return candidates.candidate(0, a.id).key == key; });
                    check(found != legal.end(), "candidate identity changed"); pair[i] = candidates.candidate(0, found->id);
                }
                auto evaluate = [&](const std::shared_ptr<const CombatTransitionSampler> &sampler, int candidate, std::uint64_t future) {
                    restoreOocPolicyThreadState(policy); SourceScope isolated(true);
                    auto copy = copied(*gc); auto history = path; std::mt19937_64 rng(future);
                    resampleCounterfactualFuture(copy, rng);
                    std::string error; check(executeOocMctsRoot(copy, pair[candidate], error), "primitive failed: " + error);
                    history.update(copy); OocGameContextModel model(copy, history, sampler, options);
                    const int health = S::g_simHealthFailureCount;
                    const double cpu = usage(RUSAGE_SELF);
                    const auto result = model.evaluateLeafWithOutcome(0, rng);
                    check(std::isfinite(result.value) && result.value >= 0 && result.value <= 1
                        && result.endpoint && S::g_simHealthFailureCount == health
                        && (result.terminal || model.combatSamples() >= 3), "invalid continuation");
                    return J{{"value", result.value}, {"terminal", result.terminal},
                        {"hp", result.endpoint->hp}, {"maxHp", result.endpoint->maxHp}, {"floor", result.endpoint->floor},
                        {"combats", model.combatSamples()}, {"steps", model.continuationMetrics().projectionSteps},
                        {"evaluatorCpuSeconds", usage(RUSAGE_SELF) - cpu}};
                };
                auto fixed = [&](const char *name, const char *phase, int count, const auto &sampler) {
                    const double p = usage(RUSAGE_SELF), c = usage(RUSAGE_CHILDREN); J rows = J::array();
                    std::array<double, 2> sums{};
                    for (int k = 0; k < count; ++k) for (int a = 0; a < 2; ++a) {
                        const auto future = stream.at(phase).at(k).template get<std::uint64_t>();
                        writer.write({{"type", "evaluation_start"}, {"act", act}, {"selector", name}, {"k", k}, {"candidate", a}, {"futureSeed", future}, {"candidateKey", pair[a].key}, {"candidateBits", pair[a].primitive.bits}});
                        auto r = child([&] { return evaluate(sampler, a, future); });
                        sums[a] += r.at("result").at("value").template get<double>();
                        r.update({{"k", k}, {"candidate", a}, {"futureSeed", future}}); rows.push_back(r);
                        writer.write({{"type", "evaluation_complete"}, {"act", act}, {"selector", name}, {"row", r}});
                    }
                    return J{{"rows", rows}, {"means", {sums[0] / count, sums[1] / count}},
                        {"selected", sums[1] > sums[0] ? 1 : 0}, {"parentCpuSeconds", usage(RUSAGE_SELF) - p},
                        {"childCpuSeconds", usage(RUSAGE_CHILDREN) - c}};
                };
                const auto ctm8 = fixed("ctm8", "rescore", 8, ctmNonce);
                const auto silver8 = fixed("silver8", "rescore", 8, silver);
                const double target = std::min(50., silver8.at("parentCpuSeconds").get<double>() + silver8.at("childCpuSeconds").get<double>());
                writer.write({{"type", "matched_start"}, {"act", act}, {"targetCpuSeconds", target}});
                auto matched = child([&] {
                    const double start = usage(RUSAGE_SELF); J rows = J::array(); std::array<double, 2> sum{};
                    for (int k = 0; k < 4096; ++k) {
                        const auto future = k < 8 ? stream.at("rescore").at(k).get<std::uint64_t>()
                            : stream.at("matched").at(k - 8).get<std::uint64_t>();
                        J row = J::array();
                        for (int a = 0; a < 2; ++a) { auto v = evaluate(ctmNonce, a, future); sum[a] += v.at("value").get<double>(); row.push_back(v); }
                        const double afterPair = usage(RUSAGE_SELF) - start;
                        rows.push_back({{"k", k}, {"futureSeed", future}, {"results", row}, {"cpuAfterPair", afterPair}});
                        if (k >= 7 && afterPair >= target) break;
                    }
                    return J{{"rows", rows}, {"count", rows.size()}, {"selected", sum[1] > sum[0] ? 1 : 0},
                        {"means", {sum[0] / rows.size(), sum[1] / rows.size()}}, {"evaluatorCpuSeconds", usage(RUSAGE_SELF) - start}};
                });
                for (int k = 0; k < 8; ++k) for (int a = 0; a < 2; ++a) {
                    auto x = matched.at("result").at("rows").at(k).at("results").at(a);
                    auto y = ctm8.at("rows").at(k * 2 + a).at("result");
                    x.erase("evaluatorCpuSeconds"); y.erase("evaluatorCpuSeconds");
                    check(x == y, "matched CTM prefix changed");
                }
                const auto ref = fixed("reference", "reference", 16, reference);
                const double matchedCost = matched.at("parentCpuSeconds").get<double>() + matched.at("childCpuSeconds").get<double>();
                const double silverCost = silver8.at("parentCpuSeconds").get<double>() + silver8.at("childCpuSeconds").get<double>();
                const double ratio = matchedCost / silverCost;
                J root{{"type", "root_complete"}, {"seed", seed}, {"act", act}, {"floor", gc->floorNum},
                    {"decisionOrdinal", actions.size() - 1},
                    {"keys", {pair[0].key, pair[1].key}}, {"bits", {pair[0].primitive.bits, pair[1].primitive.bits}},
                    {"baseline", base}, {"baselineControl", control}, {"ctm8", ctm8}, {"silver8", silver8},
                    {"matched", matched}, {"reference", ref}, {"matchedCostRatio", ratio},
                    {"matchedCostValid", ratio >= .9 && ratio <= 1.1 && matched.at("result").at("count").get<int>() < 4096}};
                check(before == combatTransitionFingerprint(*gc) && publicBefore == oocLeafCandidateInput(*gc, path), "source root changed");
                restoreOocPolicyThreadState(policy); roots.push_back(root); writer.write(root);
            };
            const auto result = runFullRunOOC(seed, 10000, 20, false, true);
            check(S::g_simHealthFailureCount == healthBefore, "source health failure");
            return J{{"actions", actions}, {"battles", battles}, {"roots", roots},
                {"summary", {{"won", result.won}, {"floor", result.floor}, {"act", result.act}, {"hp", result.hpEnd},
                    {"maxHp", result.maxHp}, {"fightsLost", result.fightsLost}, {"deathCombat", result.deathCombat},
                    {"deathEncounter", result.deathEncounter}}}};
        };
        J control;
        if (seed == plan.at("canarySeed").get<std::uint64_t>()) {
            writer.write({{"type", "source_control_start"}}); control = child([&] { return runSource(false); }, 200, 300000);
            writer.write({{"type", "source_control_complete"}, {"result", control}});
        }
        const auto source = runSource(true);
        check(!source.at("roots").empty(), "source has no eligible root");
        if (!control.is_null()) {
            auto x = source, y = control.at("result"); x.erase("roots"); y.erase("roots");
            check(x == y, "source control changed trajectory");
        }
        check(usage(RUSAGE_SELF) - startedParent <= 200 && usage(RUSAGE_CHILDREN) - startedChildren <= 1200, "final resource cap");
        writer.write({{"type", "source_complete"}, {"seed", seed}, {"source", source},
            {"parentCpuSeconds", usage(RUSAGE_SELF) - startedParent}, {"childCpuSeconds", usage(RUSAGE_CHILDREN) - startedChildren}});
        return 0;
    } catch (const std::exception &e) {
        writer.write({{"type", "invalid"}, {"seed", seed}, {"reason", e.what()}}); return 1;
    }
}
}
