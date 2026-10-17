#include "sim/search/RunGoal.h"
#include <ctime>
#include "run_profile.h"
#include "ooc_mcts_adapter.h"
#ifndef STS_LIVE_ADVISOR
#include "screen_leaf_net.h"
#include "screen_leaf_gbm.h"
#include "compact_tree.h"
#include "screen_leaf_s0.h"
#include "ooc_leaf_capture.h"
#include "ooc_selective_silver_audit.h"
#include "ooc_leaf_capture_sink.h"
#include "driver_shared.h"
#include <cerrno>
#include <csignal>
#include <dirent.h>
#include <fcntl.h>
#include <poll.h>
#include <sys/resource.h>
#include <sys/wait.h>
#endif
#include "ooc_profile.h"
#include "combat_transition_runtime.h"
#include <chrono>
#include <cstdlib>
#include <fstream>
#include <mutex>
#include <numeric>
#include <time.h>
#include <unistd.h>
#include "../ooc_strategic_tok_net.h"
#include "run_driver.h"
#include "heart1_policy.h"
#include "screen_leaf_snapshot.h"
#include "rollout_student.h"
#include "heart_leaf.h"
#include "ooc_checkpoint_policy.h"
#include "ooc_native_fallback.h"
#include "ooc_policy.h"
#include "combat/BattleContext.h"
#include "sim/search/NativeSilverBackend.h"
#include "../ooc_test_state.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <atomic>
#include <limits>
#include "sim/search/PotionRewardPolicy.h"
#include <iomanip>
#include <iostream>
#include <set>
#include <stdexcept>
#include <tuple>
#include <type_traits>
#include <unordered_map>
#include <nlohmann/json.hpp>

#ifndef STS_LIVE_ADVISOR
nlohmann::json effectiveOocPolicySpecification();
#endif

namespace one_combat {
static_assert(!std::is_constructible_v<OocGameContextModel, const GameContext &>,
              "OOC MCTS roots must require explicit PathHistory");
namespace {
std::string liveGraphPath;
std::uint64_t liveGraphDecisionIndex = 1;
std::mutex liveTraceMutex;
#ifndef STS_LIVE_ADVISOR
using ReplayJson = nlohmann::json;
constexpr std::uint64_t leafReplayOrdinal = 1025;
constexpr std::size_t leafReplayByteLimit = 64 * 1024;
struct LeafReplayMode { std::uint64_t seed; bool rootActive = false; };
// Only the explicit diagnostic command (and its synthetic test) sets this.
LeafReplayMode *leafReplayMode = nullptr;
// Intentionally not std::exception: the driver must not publish an ordinary
// failed-run/profile result for this deliberate, pre-action diagnostic stop.
struct LeafReplayComplete { ReplayJson report; };
struct StabilityLeaf {
    std::uint64_t decisionIndex, ordinal, expectedStateId;
    ReplayJson expectedInput;
    std::array<std::uint64_t, 16> repeatSeeds;
};
struct LeafStabilityMode {
    std::uint64_t seed = 0, decisionIndex = 0, expectedSimulations = 4096;
    bool rootActive = false;
    double childCpuStart = 0;
    std::string planSha256;
    std::vector<StabilityLeaf> schedule;
    ReplayJson leaves = ReplayJson::array(), roots = ReplayJson::array();
    std::function<void(ReplayJson)> progress;
};
LeafStabilityMode *leafStabilityMode = nullptr;
struct LeafStabilityComplete { ReplayJson report; };
double waitedChildCpuSeconds() {
    rusage usage{};
    if (getrusage(RUSAGE_CHILDREN, &usage) != 0)
        throw std::runtime_error("stability_child_rusage_failed");
    return usage.ru_utime.tv_sec + usage.ru_stime.tv_sec
        + (usage.ru_utime.tv_usec + usage.ru_stime.tv_usec) / 1e6;
}
ReplayJson stabilityReport(const std::string &status, const std::string &reason) {
    const auto *mode = leafStabilityMode;
    return {{"schema", "ooc-leaf-stability-v1"}, {"status", status}, {"reason", reason},
        {"runSeed", mode ? mode->seed : 0}, {"ascension", 20},
        {"planSha256", mode ? mode->planSha256 : ""},
        {"leaves", mode ? mode->leaves : ReplayJson::array()},
        {"roots", mode ? mode->roots : ReplayJson::array()},
        {"rootPrefixStopped", true}, {"gameplayResult", nullptr},
        {"targetMeaning", "conditional on full copied leaf state and the existing iterative future-redraw teacher kernel"},
        {"teacherQualification", "NOT_QUALIFIED"}, {"publicParityQualified", false},
        {"replayability", "unavailable"}, {"childCpuLimitSeconds", 10},
        {"childWallLimitMs", 10000}, {"cumulativeChildCpuLimitSeconds", 30},
        {"childCpuSeconds", mode ? waitedChildCpuSeconds() - mode->childCpuStart : 0}};
}
[[noreturn]] void failStability(const std::string &reason) {
    throw LeafStabilityComplete{stabilityReport("INVALID", reason)};
}
const StabilityLeaf *selectedStabilityLeaf(std::uint64_t ordinal) {
    if (!leafStabilityMode || !leafStabilityMode->rootActive) return nullptr;
    for (const auto &leaf : leafStabilityMode->schedule)
        if (leaf.decisionIndex == leafStabilityMode->decisionIndex && leaf.ordinal == ordinal) return &leaf;
    return nullptr;
}
std::vector<StabilityLeaf> parseStabilityPlan(const ReplayJson &plan, std::uint64_t seed, int ascension) {
    const auto keys = [](const ReplayJson &value, std::initializer_list<const char *> expected) {
        if (!value.is_object() || value.size() != expected.size()) return false;
        for (const char *key : expected) if (!value.contains(key)) return false;
        return true;
    };
    const auto uint = [](const ReplayJson &value) {
        // JSON parser stores nonnegative integral literals as unsigned; reject
        // strings, booleans, fractional/exponent numbers and negative values.
        if (!value.is_number_unsigned()) throw std::runtime_error("stability_plan_requires_uint64");
        return value.get<std::uint64_t>();
    };
    if (!keys(plan, {"schema", "runSeed", "ascension", "leaves"})
            || plan.at("schema") != "ooc-leaf-stability-v1")
        throw std::runtime_error("stability_plan_schema");
    if (uint(plan.at("runSeed")) != seed || seed != 87000000
            || uint(plan.at("ascension")) != 20 || ascension != 20)
        throw std::runtime_error("stability_plan_run_identity");
    if (!plan.at("leaves").is_array() || plan.at("leaves").size() != 4)
        throw std::runtime_error("stability_plan_requires_four_leaves");
    constexpr std::array<std::pair<std::uint64_t, std::uint64_t>, 4> schedule{{{0, 1025}, {0, 2049}, {1, 1}, {1, 513}}};
    std::set<std::uint64_t> allSeeds;
    std::vector<StabilityLeaf> output;
    std::set<std::string> inputs;
    for (std::size_t i = 0; i < schedule.size(); ++i) {
        const auto &leaf = plan.at("leaves").at(i);
        if (!keys(leaf, {"decisionIndex", "ordinal", "expectedInput", "repeatSeeds"}))
            throw std::runtime_error("stability_plan_leaf_schema");
        const auto decision = uint(leaf.at("decisionIndex")), ordinal = uint(leaf.at("ordinal"));
        if (std::make_pair(decision, ordinal) != schedule[i])
            throw std::runtime_error("stability_plan_fixed_schedule");
        if (!leaf.at("expectedInput").is_object() || leaf.at("expectedInput").empty()
                || !inputs.insert(leaf.at("expectedInput").dump()).second)
            throw std::runtime_error("stability_plan_distinct_expected_inputs");
        const auto &seeds = leaf.at("repeatSeeds");
        if (!seeds.is_array() || seeds.size() != 16)
            throw std::runtime_error("stability_plan_requires_sixteen_seeds");
        StabilityLeaf selected{decision, ordinal, ordinal, leaf.at("expectedInput"), {}};
        for (std::size_t repeat = 0; repeat < seeds.size(); ++repeat) {
            selected.repeatSeeds[repeat] = uint(seeds.at(repeat));
            if (!allSeeds.insert(selected.repeatSeeds[repeat]).second)
                throw std::runtime_error("stability_plan_duplicate_repeat_seed");
        }
        output.push_back(std::move(selected));
    }
    return output;
}
void validateStabilityRoot(const sts::search::OocMctsResult &result, const OocGameContextModel &model) {
    auto &mode = *leafStabilityMode;
    ReplayJson actions = ReplayJson::array();
    for (const auto &action : result.rootActions)
        actions.push_back({{"id", action.id}, {"prior", action.prior}, {"visits", action.visits}, {"q", action.q}});
    mode.roots.push_back({{"decisionIndex", mode.decisionIndex}, {"aborted", result.aborted},
        {"abortReason", result.abortReason}, {"completedSimulations", result.metrics.simulations},
        {"leafCalls", model.leafCalls()}, {"rootActions", std::move(actions)},
        {"selectedAction", result.selectedAction ? ReplayJson(*result.selectedAction) : ReplayJson(nullptr)},
        {"validated", false}});
    if (result.aborted) failStability("selected_root_search_aborted");
    if (!result.selectedAction || result.metrics.simulations == 0
            || result.metrics.simulations > mode.expectedSimulations
            || !model.observationError().empty())
        failStability("selected_root_incomplete_or_invalid");
    for (const auto &selected : mode.schedule) {
        if (selected.decisionIndex != mode.decisionIndex) continue;
        auto found = std::find_if(mode.leaves.begin(), mode.leaves.end(), [&](const ReplayJson &leaf) {
            return leaf.at("decisionIndex") == selected.decisionIndex && leaf.at("ordinal") == selected.ordinal;
        });
        if (found == mode.leaves.end()) failStability("scheduled_leaf_not_reached");
        if (found->at("repetitions").size() != 16 || found->at("parent").is_null()
                || !found->contains("controlComparison") || found->at("controlComparison").at("status") != "PASS")
            failStability("scheduled_leaf_incomplete_or_invalid");
    }
    mode.roots.back()["validated"] = true;
    for (auto &leaf : mode.leaves)
        if (leaf.at("decisionIndex") == mode.decisionIndex) leaf["rootValidated"] = true;
    if (mode.decisionIndex == mode.schedule.back().decisionIndex) {
        if (mode.leaves.size() != mode.schedule.size()) failStability("scheduled_leaf_count_mismatch");
        throw LeafStabilityComplete{stabilityReport("STABILITY_MEASURED", "all_scheduled_leaves_and_roots_validated")};
    }
}
ReplayJson replayReport(const std::string &status, const std::string &reason) {
    return {{"status", status}, {"reason", reason}, {"decisionIndex", 0},
        {"ordinal", leafReplayOrdinal}, {"runSeed", leafReplayMode ? leafReplayMode->seed : 0},
        {"scope", "single_same_model_id_map_leaf"}, {"rootPrefixStopped", true},
        {"gameplayResult", nullptr}, {"childWallLimitMs", 10000}, {"childCpuLimitSeconds", 10},
        {"transportByteLimit", leafReplayByteLimit}};
}
void requireReplaySingleThread() {
#ifdef __linux__
    DIR *directory = opendir("/proc/self/task");
    if (!directory) throw std::runtime_error("cannot_inspect_process_threads");
    unsigned count = 0;
    while (const auto *entry = readdir(directory)) if (entry->d_name[0] != '.') ++count;
    closedir(directory);
    if (count != 1) throw std::runtime_error("replay_requires_exactly_one_os_thread");
#else
    throw std::runtime_error("replay_requires_linux");
#endif
}
std::string replayRngString(const std::mt19937_64 &rng) {
    std::ostringstream out; out << rng; return out.str();
}
std::string replayPathString(const PathHistory &path) {
    return ReplayJson{{"roomVisits", path.roomVisits}, {"lastNodeKey", path.lastNodeKey}}.dump();
}
std::string replayStateString(const GameContext &gc) {
    // Test fingerprint is a structured exact string, not an object-byte hash.
    // Add the two newer visible fields omitted by that fixture helper.
    return sts::test::oocStateFingerprint(gc) + "|keysEnabled=" + std::to_string(gc.keysEnabled)
        + "|restRoomResolved=" + std::to_string(gc.restRoomResolved);
}
std::string replayFingerprint(const std::string &value) {
    // Compact report identity only. Source nonmutation uses full-string ==.
    std::uint64_t hash = 14695981039346656037ull;
    for (unsigned char byte : value) { hash ^= byte; hash *= 1099511628211ull; }
    std::ostringstream out; out << std::hex << std::setw(16) << std::setfill('0') << hash;
    return out.str();
}
ReplayJson replayEvaluation(std::optional<double> value, const std::string &error, bool terminal,
        const sts::search::OocEndpoint &endpoint, std::uint64_t combats, std::uint64_t steps,
        const std::mt19937_64 &rng, bool unchanged) {
    return {{"value", value ? ReplayJson(*value) : ReplayJson(nullptr)}, {"error", error},
        {"terminal", terminal}, {"endpoint", {{"hp", endpoint.hp}, {"maxHp", endpoint.maxHp},
        {"floor", endpoint.floor}}}, {"actualCombats", combats}, {"projectionSteps", steps},
        {"finalRng", replayRngString(rng)}, {"sourceUnchanged", unchanged}};
}
ReplayJson compareReplay(const ReplayJson &parent, const ReplayJson &child) {
    auto report = replayReport("PASS", "exact_same_state_rng_evaluation");
    report["parent"] = parent; report["child"] = child;
    report["differentFields"] = ReplayJson::array();
    const auto valid = [](const ReplayJson &value) {
        return value.is_object() && value.contains("error") && value.at("error") == ""
            && value.contains("value") && value.at("value").is_number()
            && std::isfinite(value.at("value").get<double>())
            && value.at("value").get<double>() >= 0 && value.at("value").get<double>() <= 1;
    };
    if (!valid(parent) || !valid(child)) {
        report["status"] = "INVALID"; report["reason"] = "unsupported_or_invalid_evaluation";
        return report;
    }
    for (const char *key : {"value", "error", "terminal", "endpoint", "actualCombats",
                            "projectionSteps", "finalRng", "sourceUnchanged"})
        if (!parent.contains(key) || !child.contains(key) || parent.at(key) != child.at(key))
            report["differentFields"].push_back(key);
    if (!parent.value("sourceUnchanged", false) || !child.value("sourceUnchanged", false)) {
        report["status"] = "INVALID"; report["reason"] = "source_mutation";
    } else if (!report["differentFields"].empty()) {
        report["status"] = "FAIL"; report["reason"] = "replay_mismatch";
    }
    return report;
}
// Fork before either evaluation. Only the child sees replay cache/metric and
// callback mutations; the parent waits before doing its scheduled evaluation.
ReplayJson forkLeafReplay(const std::function<ReplayJson()> &evaluate, int timeoutMs = 10000, int cpuSeconds = 10, std::size_t byteLimit = leafReplayByteLimit) {
    requireReplaySingleThread();
    int channel[2];
    if (pipe(channel) != 0) throw std::runtime_error("replay_pipe_failed");
    struct Channel { int read, write; ~Channel() { if (read >= 0) close(read); if (write >= 0) close(write); } }
        pipeEnds{channel[0], channel[1]};
    if (channel[0] <= 2 || channel[1] <= 2)
        throw std::runtime_error("replay_requires_standard_descriptors");
    // Enumerate in the single-threaded parent; never leave capture/model/socket
    // descriptors writable in the child. Do not flush inherited stdio buffers.
    std::vector<int> inherited;
    DIR *directory = opendir("/proc/self/fd");
    if (!directory) throw std::runtime_error("cannot_inspect_process_fds");
    const int scanFd = dirfd(directory);
    while (const auto *entry = readdir(directory)) {
        char *end = nullptr;
        const long fd = std::strtol(entry->d_name, &end, 10);
        if (*entry->d_name && end && !*end && fd > 2 && fd != channel[1] && fd != scanFd)
            inherited.push_back(static_cast<int>(fd));
    }
    closedir(directory);
    const auto started = std::chrono::steady_clock::now();
    const pid_t child = fork();
    if (child < 0) throw std::runtime_error("replay_fork_failed");
    if (child == 0) {
        for (int fd : inherited) close(fd);
        const int nullFd = open("/dev/null", O_RDWR);
        if (nullFd < 0) _exit(121);
        for (int fd = 0; fd < 3; ++fd) if (dup2(nullFd, fd) < 0) _exit(121);
        if (nullFd > 2) close(nullFd);
        const rlimit cpu{rlim_t(cpuSeconds), rlim_t(cpuSeconds)};
        if (setrlimit(RLIMIT_CPU, &cpu) != 0) _exit(122);
        try {
            const auto payload = evaluate().dump();
            if (payload.size() > byteLimit) _exit(123);
            std::size_t at = 0;
            while (at < payload.size()) {
                const ssize_t count = write(channel[1], payload.data() + at, payload.size() - at);
                if (count < 0 && errno == EINTR) continue;
                if (count <= 0) _exit(124);
                at += static_cast<std::size_t>(count);
            }
            close(channel[1]);
            _exit(0);
        } catch (...) { _exit(125); }
    }
    close(pipeEnds.write); pipeEnds.write = -1;
    struct Reap {
        pid_t pid; bool done = false;
        ~Reap() { if (!done) { kill(pid, SIGKILL); while (waitpid(pid, nullptr, 0) < 0 && errno == EINTR) {} } }
    } reap{child};
    std::string payload;
    int status = 0;
    bool eof = false, exited = false;
    while (!eof || !exited) {
        const auto elapsed = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now() - started).count();
        if (elapsed >= timeoutMs) throw std::runtime_error("replay_child_timeout");
        pollfd fd{eof ? -1 : pipeEnds.read, POLLIN | POLLHUP, 0};
        const int ready = poll(&fd, 1, std::min<int>(50, timeoutMs - elapsed));
        if (ready < 0 && errno != EINTR) throw std::runtime_error("replay_pipe_poll_failed");
        if (ready > 0 && (fd.revents & (POLLIN | POLLHUP))) {
            char buffer[4096];
            const ssize_t count = read(pipeEnds.read, buffer, sizeof(buffer));
            if (count == 0) eof = true;
            else if (count < 0 && errno != EINTR) throw std::runtime_error("replay_pipe_read_failed");
            else if (count > 0) {
                payload.append(buffer, static_cast<std::size_t>(count));
                if (payload.size() > byteLimit) throw std::runtime_error("replay_payload_limit");
            }
        }
        if (!exited) {
            const auto waited = waitpid(child, &status, WNOHANG);
            if (waited == child) { exited = true; reap.done = true; }
            else if (waited < 0 && errno != EINTR) throw std::runtime_error("replay_wait_failed");
        }
    }
    if (!WIFEXITED(status) || WEXITSTATUS(status) != 0)
        throw std::runtime_error("replay_child_failed_status_" + std::to_string(status));
    auto result = ReplayJson::parse(payload);
    if (!result.is_object()) throw std::runtime_error("replay_child_result_not_object");
    return result;
}
#endif
GameContext detachedCopy(const GameContext &parent) {
    GameContext child = parent;
    if (parent.map) child.map = std::make_shared<sts::Map>(*parent.map);
    return child;
}
// Re-determinize only a detached hypothetical state. Published offers, the
// current map/boss, selected cards, and observed encounter history stay fixed.
// A fresh seed also covers native per-floor RNG resets and next-act map setup.
void sampleNoncombatFuture(GameContext &gc, std::mt19937_64 &rng) {
    gc.seed = rng();
    for (auto stream : {&gc.aiRng, &gc.cardRandomRng, &gc.cardRng, &gc.eventRng,
            &gc.mathUtilRng, &gc.merchantRng, &gc.miscRng, &gc.monsterHpRng,
            &gc.monsterRng, &gc.neowRng, &gc.potionRng, &gc.relicRng,
            &gc.shuffleRng, &gc.treasureRng}) {
        const auto counter = stream->counter;
        *stream = sts::Random(rng());
        stream->counter = counter; // native thresholds depend on past draw counts
    }
    const auto shuffleUnknown = [&](auto &pool) {
        // Canonicalize first so the actual hidden ordering cannot affect samples.
        std::sort(pool.begin(), pool.end());
        std::shuffle(pool.begin(), pool.end(), rng);
    };
    for (auto pool : {&gc.commonRelicPool, &gc.uncommonRelicPool, &gc.rareRelicPool,
                     &gc.shopRelicPool, &gc.bossRelicPool}) shuffleUnknown(*pool);
    shuffleUnknown(gc.colorlessCardPool);
    // Event pools are eligible sets, not queues. Canonical order removes any
    // dependence on an unobserved representation without changing membership.
    std::sort(gc.eventList.begin(), gc.eventList.end());
    std::sort(gc.shrineList.begin(), gc.shrineList.end());
    std::sort(gc.specialOneTimeEventList.begin(), gc.specialOneTimeEventList.end());
    if (gc.act >= 1 && gc.act <= 3) {
        const int count = gc.monsterList.size();
        if (gc.monsterListOffset < 0 || gc.monsterListOffset > count
            || gc.eliteMonsterListOffset < 0 || gc.eliteMonsterListOffset > gc.eliteMonsterList.size())
            throw sts::search::OocSearchUnsupported("invalid_hidden_encounter_history");
        const int weakCount = gc.act == 1 ? 3 : 2;
        gc.monsterList.resize(gc.monsterListOffset);
        for (int i = gc.monsterListOffset; i < count; ++i) {
            const int act = gc.act - 1;
            if (i < weakCount)
                gc.populateMonsterList(sts::MonsterEncounterPool::weakEnemies[act],
                    sts::MonsterEncounterPool::weakWeights[act], sts::MonsterEncounterPool::weakCount[act], 1);
            else if (i == weakCount)
                gc.populateFirstStrongEnemy(sts::MonsterEncounterPool::strongEnemies[act],
                    sts::MonsterEncounterPool::strongWeights[act], sts::MonsterEncounterPool::strongCount[act]);
            else
                gc.populateMonsterList(sts::MonsterEncounterPool::strongEnemies[act],
                    sts::MonsterEncounterPool::strongWeights[act], sts::MonsterEncounterPool::strongCount[act], 1);
        }
        for (int i = gc.eliteMonsterListOffset; i < gc.eliteMonsterList.size(); ++i) {
            sts::MonsterEncounter draw;
            do { draw = sts::MonsterEncounterPool::elites[gc.act-1][gc.monsterRng.random(2)]; }
            while (i > 0 && draw == gc.eliteMonsterList[i-1]);
            gc.eliteMonsterList[i] = draw;
        }
        // The second A20 boss is hidden until the first boss falls; once its
        // fight has started (a BATTLE leaf after a sampled first-boss win) it is
        // revealed, and Silver reads gc.secondBoss to recognise the final fight.
        const bool secondBossRevealed = gc.screenState == sts::ScreenState::BATTLE
            && gc.info.encounter == gc.secondBoss;
        if (gc.act == 3 && gc.ascension >= 20 && !secondBossRevealed) {
            const sts::MonsterEncounter bosses[] = {sts::MonsterEncounter::AWAKENED_ONE,
                sts::MonsterEncounter::TIME_EATER, sts::MonsterEncounter::DONU_AND_DECA};
            do { gc.secondBoss = bosses[gc.monsterRng.random(2)]; } while (gc.secondBoss == gc.boss);
        }
    }
    if (gc.screenState == sts::ScreenState::TREASURE_ROOM) {
        // Chest size is visible; contents are not. Keep native gold/tier
        // correlation from the single roll used by setupTreasureRoom().
        const int size = int(gc.info.chestSize);
        if (size < 0 || size >= 3) throw sts::search::OocSearchUnsupported("invalid_hidden_chest");
        const int roll = gc.treasureRng.random(99);
        gc.info.haveGold = roll < sts::chestGoldChances[size];
        const auto chances = sts::chestRelicTierChances[size];
        gc.info.tier = roll < chances[0] ? sts::RelicTier::COMMON
            : roll < chances[0] + chances[1] ? sts::RelicTier::UNCOMMON : sts::RelicTier::RARE;
    }
    if (gc.screenState == sts::ScreenState::EVENT_SCREEN && gc.curEvent == sts::Event::DEAD_ADVENTURER) {
        // The description reveals the encounter, but unsearched rewards remain hidden.
        if (gc.info.phase < 0 || gc.info.phase > int(gc.info.rewards.size()))
            throw sts::search::OocSearchUnsupported("invalid_hidden_event_history");
        auto first = gc.info.rewards.begin() + gc.info.phase;
        std::sort(first, gc.info.rewards.end());
        std::shuffle(first, gc.info.rewards.end(), rng);
    }
}

// Search-equivalence of two sampled successors of one chance node (#384).
// Omits exactly what sampleNoncombatFuture re-draws before every later
// transition and leaf continuation: the run seed, every RNG stream (a counter
// only positions a re-seeded stream), pool order, unseen monster/elite queue
// entries, the A20 second Act-3 boss, hidden chest gold/tier and unsearched
// Dead Adventurer reward order. Everything copied forward is kept, including
// hidden room/potion/rarity counters. Separate parts let a diagnostic
// attribute a split to one component.
enum OutcomePart { HIDDEN, SCREEN, PLAYER, DECK, RELICS, POTIONS, MAP, PATH, OUTCOME_PARTS };
std::array<std::string, OUTCOME_PARTS> outcomeEquivalenceParts(const GameContext &g, const PathHistory &path) {
    std::array<std::string, OUTCOME_PARTS> parts;
    {
        sts::test::ooc_state_detail::Writer w;
        w.values(g.monsterChance, g.shopChance, g.treasureChance, g.potionChance, g.cardRarityFactor);
        const auto members = [&](auto pool) { std::sort(pool.begin(), pool.end()); w.sequence(pool); };
        members(g.eventList); members(g.shrineList); members(g.specialOneTimeEventList);
        members(g.commonRelicPool); members(g.uncommonRelicPool); members(g.rareRelicPool);
        members(g.shopRelicPool); members(g.bossRelicPool); members(g.colorlessCardPool);
        const auto seen = [&](const auto &list, int offset) {
            const int n = std::clamp<int>(offset, 0, list.size());
            w.value(offset);
            for (int i = 0; i < n; ++i) w.value(list[i]);
        };
        seen(g.monsterList, g.monsterListOffset);
        seen(g.eliteMonsterList, g.eliteMonsterListOffset);
        if (!(g.act == 3 && g.ascension >= 20)) w.value(g.secondBoss);
        parts[HIDDEN] = w.finish();
    }
    {
        sts::test::ooc_state_detail::Writer w;
        auto info = g.info;
        if (g.screenState == sts::ScreenState::TREASURE_ROOM) {
            info.haveGold = false;
            info.tier = sts::RelicTier::COMMON;
        }
        if (g.screenState == sts::ScreenState::EVENT_SCREEN && g.curEvent == sts::Event::DEAD_ADVENTURER
                && info.phase >= 0 && info.phase <= int(info.rewards.size()))
            std::sort(info.rewards.begin() + info.phase, info.rewards.end());
        w.values(g.outcome, g.screenState, info, g.lastRoom, g.curEvent, g.curRoom, g.boss,
                 static_cast<bool>(g.regainControlAction), g.restRoomResolved);
        parts[SCREEN] = w.finish();
    }
    {
        sts::test::ooc_state_detail::Writer w;
        w.values(g.noteForYourselfCard, g.skipBattles, g.act, g.ascension, g.floorNum, g.cc,
                 g.curHp, g.maxHp, g.gold, g.wingBootsCharges, g.shopRemoveCount, g.speedrunPace,
                 g.curMapNodeX, g.curMapNodeY, g.blueKey, g.greenKey, g.redKey, g.keysEnabled,
                 g.smokeBombUsed);
        parts[PLAYER] = w.finish();
    }
    {
        sts::test::ooc_state_detail::Writer w;
        w.sequence(g.deck.cards);
        w.sequence(g.deck.bottleIdxs);
        parts[DECK] = w.finish();
    }
    {
        sts::test::ooc_state_detail::Writer w;
        w.sequence(g.relics.relics);
        parts[RELICS] = w.finish();
    }
    {
        sts::test::ooc_state_detail::Writer w;
        w.values(g.potionCount, g.potionCapacity);
        w.sequence(g.potions);
        parts[POTIONS] = w.finish();
    }
    {
        sts::test::ooc_state_detail::Writer w;
        w.value(static_cast<bool>(g.map));
        if (g.map) {
            w.values(g.map->burningEliteX, g.map->burningEliteY, g.map->burningEliteBuff);
            for (const auto &row : g.map->nodes) w.sequence(row);
        }
        parts[MAP] = w.finish();
    }
    {
        sts::test::ooc_state_detail::Writer w;
        w.sequence(path.roomVisits);
        w.value(path.lastNodeKey);
        parts[PATH] = w.finish();
    }
    return parts;
}
std::uint64_t outcomeEquivalenceKeyOf(const GameContext &g, const PathHistory &path) {
    std::string joined;
    for (const auto &part : outcomeEquivalenceParts(g, path)) { joined += part; joined += '|'; }
    return std::hash<std::string>{}(joined);
}

void sampleLiveOocHiddenCountersImpl(GameContext &gc, std::mt19937_64 &rng,
                                     int priorEventRooms, bool questionHistoryComplete) {
    // Only '?' room transitions change these room chances. Bound increments
    // by the number of rooms already visited in this act, and reproduce the
    // native float-addition lattice (including Juzu's >1 monster chance).
    if (!questionHistoryComplete) {
        const int actStart = gc.act <= 1 ? 0 : gc.act == 2 ? 17 : gc.act == 3 ? 34 : 51;
        const int priorRooms = std::clamp(std::min(gc.floorNum - actStart, priorEventRooms), 0, 16);
        gc.monsterChance = 0.1f;
        gc.shopChance = 0.03f;
        gc.treasureChance = 0.02f;
        // Draw one latent outcome per observed '?' room, then update all three
        // counters together by the native room-outcome rule. Independent lattice
        // draws create counter triples that no room history could have produced.
        for (int i = 0; i < priorRooms; ++i) {
            const int outcome = std::uniform_int_distribution<int>(0, 3)(rng);
            gc.monsterChance = outcome == 0 ? 0.1f : gc.monsterChance + 0.1f;
            gc.shopChance = outcome == 1 ? 0.03f : gc.shopChance + 0.03f;
            gc.treasureChance = outcome == 2 ? 0.02f : gc.treasureChance + 0.02f;
        }
    }
    gc.potionChance = 10 * std::uniform_int_distribution<int>(-4, 6)(rng);
    gc.cardRarityFactor = std::uniform_int_distribution<int>(-40, 5)(rng);
}

void require(bool ok, const char *why) { if (!ok) throw std::runtime_error(why); }
// Bosses beaten so far: a boss counts once its fight is over (rewards, boss chest).
// transitionToAct keeps curRoom at BOSS_TREASURE until the first map node, with
// curMapNodeY reset to -1, so only a chest still on the old map is past-boss.
int bossesCleared(const GameContext &gc) {
    const bool past = (gc.curRoom == sts::Room::BOSS && gc.screenState != sts::ScreenState::BATTLE)
        || (gc.curRoom == sts::Room::BOSS_TREASURE && gc.curMapNodeY != -1);
    return gc.act - 1 + past;
}
double bossLeafUtility(const CombatTransitionExpectation &estimate) {
    const double survival = 1.0 - estimate.death;
    return 0.75 * survival + 0.25 * survival * estimate.winningHpFraction;
}
// Phase-0 Smoke Bomb approximation (#370). The qualified CTM excludes combats
// that start with a Smoke Bomb. Rather than abort the whole search, value such
// a combat as if the Smoke Bomb slot were empty (no escape) and return the
// Smoke Bomb unused afterwards; a potion the CTM generated into that slot is
// dropped, since the occupied slot could not have held it. Against bosses the
// Smoke Bomb cannot be used, so only slot occupancy differs there.
class InitialSmokeBombMaskingSampler final : public CombatTransitionSampler {
    std::shared_ptr<const CombatTransitionSampler> inner_;
    static constexpr int kEmpty = static_cast<int>(sts::Potion::EMPTY_POTION_SLOT);
    static constexpr int kSmoke = static_cast<int>(sts::Potion::SMOKE_BOMB);
public:
    struct Masked {
        GameContext gc;
        CombatPredictorInputV1 input;
        std::vector<int> slots;
    };
    explicit InitialSmokeBombMaskingSampler(std::shared_ptr<const CombatTransitionSampler> inner)
        : inner_(std::move(inner)) {}
    static std::optional<Masked> mask(const GameContext &gc, const CombatPredictorInputV1 &input) {
        if (gc.smokeBombUsed) return std::nullopt;
        std::vector<int> slots;
        for (int i = 0; i < static_cast<int>(gc.potions.size()); ++i)
            if (gc.potions[i] == sts::Potion::SMOKE_BOMB) slots.push_back(i);
        if (slots.empty()) return std::nullopt;
        Masked masked{gc, input, slots};
        for (int slot : slots) {
            masked.gc.potions[slot] = sts::Potion::EMPTY_POTION_SLOT;
            --masked.gc.potionCount;
            for (auto &token : masked.input.potions)
                if (token.slot == slot && token.potionId == kSmoke) token.potionId = kEmpty;
            --masked.input.globals.potionCount;
        }
        return masked;
    }
    static CombatRuntimeSample restore(CombatRuntimeSample sample, const std::vector<int> &slots) {
        if (sample.outcome != CombatRuntimeSample::Outcome::VICTORY
                && sample.outcome != CombatRuntimeSample::Outcome::ESCAPE) return sample;
        auto &post = sample.rawPost;
        for (int slot : slots) post.potions.at(slot) = kSmoke;
        post.potionCount = static_cast<int>(std::count_if(post.potions.begin(), post.potions.end(),
            [](int p) { return p > kEmpty; }));
        return sample;
    }
    std::unique_ptr<PreparedCombatTransition> prepare(const GameContext &gc,
            const CombatPredictorInputV1 &input) const override {
        auto masked = mask(gc, input);
        if (!masked) return inner_->prepare(gc, input);
        class Restoring final : public PreparedCombatTransition {
            std::unique_ptr<PreparedCombatTransition> inner_;
            std::vector<int> slots_;
        public:
            Restoring(std::unique_ptr<PreparedCombatTransition> inner, std::vector<int> slots)
                : inner_(std::move(inner)), slots_(std::move(slots)) {}
            const CombatRuntimeSupport &support() const override { return inner_->support(); }
            CombatRuntimeSample sample(std::mt19937_64 &rng) const override {
                return restore(inner_->sample(rng), slots_);
            }
        };
        return std::make_unique<Restoring>(inner_->prepare(masked->gc, masked->input), masked->slots);
    }
    CombatRuntimeSupport support(const GameContext &gc, const CombatPredictorInputV1 &input) const override {
        const auto masked = mask(gc, input);
        return masked ? inner_->support(masked->gc, masked->input) : inner_->support(gc, input);
    }
    CombatRuntimeSupport forecastSupport(const CombatPredictorInputV1 &input) const override {
        return inner_->forecastSupport(input);
    }
    CombatTransitionExpectation forecastExpectation(const CombatPredictorInputV1 &input) const override {
        return inner_->forecastExpectation(input);
    }
    CombatTransitionExpectation expectation(const GameContext &gc, const CombatPredictorInputV1 &input) const override {
        const auto masked = mask(gc, input);
        return masked ? inner_->expectation(masked->gc, masked->input) : inner_->expectation(gc, input);
    }
    CombatRuntimeSample sample(const GameContext &gc, const CombatPredictorInputV1 &input,
            std::mt19937_64 &rng) const override {
        const auto masked = mask(gc, input);
        if (!masked) return inner_->sample(gc, input, rng);
        return restore(inner_->sample(masked->gc, masked->input, rng), masked->slots);
    }
};
std::shared_ptr<const CombatTransitionSampler> maskInitialSmokeBomb(
        std::shared_ptr<const CombatTransitionSampler> sampler) {
    // An escape-capable CTM supports the Smoke Bomb itself and may sample the escape.
    if (!sampler || sampler->modelsSmokeBombEscape()) return sampler;
    return std::make_shared<InitialSmokeBombMaskingSampler>(std::move(sampler));
}
void applySampledCombatExit(GameContext &gc, const CombatRuntimeSample &sample) {
    const bool escape = sample.outcome == CombatRuntimeSample::Outcome::ESCAPE;
    if ((sample.outcome != CombatRuntimeSample::Outcome::VICTORY && !escape)
        || sample.rawPost.smokeBombUsed != escape
        || (escape && sts::isBossEncounter(gc.info.encounter)))
        throw std::runtime_error("combat outcome disagrees with RAW smokeBombUsed");
    applyCombatTransitionState(gc, sample.rawPost);
    gc.regainControl();
}
}
void sampleLiveOocHiddenCounters(GameContext &gc, std::mt19937_64 &rng,
                                 int priorEventRooms, bool questionHistoryComplete) {
    sampleLiveOocHiddenCountersImpl(gc, rng, priorEventRooms, questionHistoryComplete);
}
#ifndef STS_LIVE_ADVISOR
OocMctsDependencies defaultOocMctsDependencies() {
    OocMctsDependencies dependencies;
    dependencies.policyAvailable = [] { return g_oocStrategicTokNet.ok; };
    dependencies.policyLogits = [](const GameContext &gc, const PathHistory &path,
                                   const std::vector<GameAction> &actions) {
        if (!g_oocStrategicTokNet.ok) throw std::runtime_error("OOC MCTS V4 unavailable");
        const TokState ts = buildTokState(gc, path);
        const auto prepared = g_oocStrategicTokNet.prepareState(ts.glob, ts.nDk, ts.dk,
            ts.nRl, ts.rl, ts.nPt, ts.pt);
        const auto policyPrefix = g_oocStrategicTokNet.preparePolicyPrefix(prepared);
        std::vector<double> result;
        result.reserve(actions.size());
        for (const auto action : actions) {
            int type, c1, c2, c3, d1, d2, d3, entityType, entityId;
            float price;
            strategicCands(gc, action, type, c1, c2, c3, d1, d2, d3);
            tokEntity(gc, action, entityType, entityId, price);
            const int cats[6] = {c1, c2, c3, d1, d2, d3};
            const float entity[4] = {float(entityType == 0), float(entityType == 1),
                                     float(entityType == 2), float(entityType == 3)};
            const double logit = g_oocStrategicTokNet.predictPolicyLogit(prepared, policyPrefix, action.bits,
                cats, type, int(gc.screenState), entity, entityId, price);
            if (!std::isfinite(logit)) throw std::runtime_error("OOC MCTS nonfinite policy logit");
            result.push_back(logit);
        }
        return result;
    };
    if (winNetOk()) {
        // Features only read the state, so no detached copy or t_curPath swap.
        dependencies.leafValue = [](const GameContext &source, const PathHistory &path) {
            std::vector<float> raw;
            {
                OocProfileScope features(OocProfileBucket::LeafFeatures);
                raw = richFeatureVec(source, path);
            }
            OocProfileScope predict(OocProfileBucket::LeafPredict);
            return vStateWinNativeFeatures(raw);
        };
    }
    dependencies.continuationStep = [](GameContext &gc, PathHistory &, std::mt19937_64 &) {
        ScumSearchAgent2 agent;
        agent.simulationCountBase = 10000;
        runFullRunOocPolicyStep(gc, agent, false, true);
    };
    if (one_combat::heart1::enabled()) {
        dependencies.heart1PolicyLogits = [](const GameContext &gc, const std::vector<GameAction> &actions,
                                             std::map<std::string, std::uint64_t> *tally) {
            return one_combat::heart1::priorLogits(gc, actions, tally);
        };
    }
    dependencies.potionKeepValue = [](const GameContext &gc) { return ::potionKeepValue(gc); };
    dependencies.stopAfterAct = [] { return g_stopAfterAct; };
    return dependencies;
}
#endif
std::vector<double> oocPolicyWeights(const std::vector<double> &logits, double temperature) {
    if (!std::isfinite(temperature) || temperature <= 0)
        throw std::invalid_argument("OOC MCTS invalid policy temperature");
    for (double l : logits) if (!std::isfinite(l)) throw std::runtime_error("OOC MCTS nonfinite policy logit");
    if (logits.empty()) return {};
    double largest = *std::max_element(logits.begin(), logits.end());
    std::vector<double> weights;
    for (double l : logits) {
        double w = std::exp((l - largest) / temperature);
        if (!std::isfinite(w) || w < 0) throw std::runtime_error("OOC MCTS invalid policy weight");
        weights.push_back(w);
    }
    return weights;
}
#ifndef STS_LIVE_ADVISOR
OocGameContextModel::OocGameContextModel(const GameContext &gc, const PathHistory &path,
    std::shared_ptr<const CombatTransitionSampler> sampler, OocAdapterOptions opts)
    : OocGameContextModel(gc, path, std::move(sampler), std::move(opts),
                          defaultOocMctsDependencies()) {}
#endif

OocGameContextModel::OocGameContextModel(const GameContext &gc, const PathHistory &path,
    std::shared_ptr<const CombatTransitionSampler> sampler, OocAdapterOptions opts,
    OocMctsDependencies deps)
    : combatSampler(maskInitialSmokeBomb(std::move(sampler))), options(std::move(opts)),
      dependencies(std::move(deps)) {
    if (!std::isfinite(options.priorTemperature) || options.priorTemperature <= 0 || (options.leafCombats != 0 && options.leafCombats != 1 && options.leafCombats != 3 && options.leafCombats != 5))
        throw std::invalid_argument("OOC MCTS invalid adapter options");
    if (options.leafObserver && (!options.leafCaptureStride || !options.leafCaptureLimit))
        throw std::invalid_argument("OOC leaf observation requires positive stride and limit");
    if (!options.bossLeaf && !dependencies.leafValue)
        throw std::runtime_error("OOC MCTS requires a leaf-value dependency");
    if (!dependencies.policyAvailable || !dependencies.policyLogits
            || !dependencies.policyAvailable())
        throw std::runtime_error("OOC MCTS requires native V4 policy dependencies");
    if ((options.heart1Prior || options.heart1LeafPolicy) && !dependencies.heart1PolicyLogits)
        throw std::runtime_error("OOC MCTS heart1 prior/leaf policy requires STS_OOC_HEART1");
    if (options.heart1Coverage && !options.heart1Prior)
        throw std::invalid_argument("OOC MCTS heart1 coverage requires the heart1 prior");
    if (options.targetPrior && !options.heart1Prior)
        throw std::invalid_argument("OOC MCTS target prior requires the heart1 prior");
    if (options.heart1LeafSelects && !(options.heart1LeafPolicy && options.heart1Coverage))
        throw std::invalid_argument("OOC MCTS heart1 leaf selects require LEAF_POLICY=heart1 and heart1full");
    if (options.heart1Prior && !options.priorTracePath.empty())
        throw std::runtime_error("STS_OOC_MCTS_PRIOR_TRACE does not support STS_OOC_MCTS_PRIOR=heart1");
    if (!dependencies.potionKeepValue) dependencies.potionKeepValue = [](const GameContext &) { return 4.0; };
    if (!dependencies.stopAfterAct) dependencies.stopAfterAct = [] { return 0; };
    auto root = detachedCopy(gc);
    collectForcedRewardGold(root);
#ifndef STS_LIVE_ADVISOR
    if (options.treeRules) while (oocTreeRuleStep(root)) {}
#endif
    auto history = path;
    history.update(root);
    states.push_back({std::move(root), history, {}});
}
const GameContext &OocGameContextModel::state(sts::search::OocStateId id) const { return states.at(id).gc; }
const PathHistory &OocGameContextModel::pathHistory(sts::search::OocStateId id) const { return states.at(id).path; }
const OocGameContextModel::CombatPrediction &OocGameContextModel::prediction(sts::search::OocStateId id) const {
    return states.at(id).combatPrediction;
}
namespace {
std::string graphRoomName(sts::Room room) {
    switch (room) {
        case sts::Room::MONSTER: return "Monster";
        case sts::Room::ELITE: return "Elite";
        case sts::Room::EVENT: return "Event";
        case sts::Room::SHOP: return "Shop";
        case sts::Room::REST: return "Rest";
        case sts::Room::TREASURE: return "Treasure";
        case sts::Room::BOSS: return "Boss";
        case sts::Room::BOSS_TREASURE: return "Boss treasure";
        default: return "Unknown";
    }
}
std::string graphEntityName(const sts::search::OocEntity &entity) {
    if (const auto *card = std::get_if<sts::Card>(&entity)) return card->getName();
    if (const auto *relic = std::get_if<sts::RelicId>(&entity)) return sts::getRelicName(*relic);
    if (const auto *potion = std::get_if<sts::Potion>(&entity)) return sts::getPotionName(*potion);
    if (const auto *gold = std::get_if<int>(&entity)) return std::to_string(*gold) + " gold";
    if (std::get_if<sts::Key>(&entity)) return "key";
    return "";
}
std::string candidateLabel(const GameContext &source, const OocGameContextModel::Candidate &action) {
    if (!action.semantic) {
        if (source.screenState == sts::ScreenState::MAP_SCREEN) {
            const int x = action.primitive.getIdx1(), y = source.curMapNodeY + 1;
            const bool hasRoom = source.map && y >= 0 && y < 15 && x >= 0 && x < 7;
            const std::string room = hasRoom ? graphRoomName(source.map->nodes[y][x].room) : "Unknown";
            return "Travel to " + room + " room at (" + std::to_string(x) + "," + std::to_string(y) + ")";
        }
        return "Choose game action " + std::to_string(action.primitive.bits);
    }
    static constexpr const char *effects[] = {
        "Upgrade card", "Remove card", "Transform card", "Transform and upgrade card",
        "Duplicate card", "Take card", "Bottle card", "Sacrifice card", "Take relic",
        "Collect gold", "Take potion", "Take key", "Skip card reward", "Use Singing Bowl",
        "Leave rewards", "Open chest", "Leave treasure", "Rest", "Take Ruby Key",
        "Lift", "Dig", "Leave campfire", "Buy card", "Buy relic", "Buy potion",
        "Leave shop", "Choose event option", "Take boss relic", "Skip boss relic", "Discard potion"
    };
    const auto effect = static_cast<unsigned>(action.semantic->effect);
    std::string label = effect < std::size(effects) ? effects[effect] : "OOC action";
    std::string target;
    const auto &payload = action.semantic->target;
    if (const auto *card = std::get_if<sts::search::OocCardTarget>(&payload))
        target = sts::getCardName(card->id);
    else if (const auto *selection = std::get_if<sts::search::OocSelectorTarget>(&payload)) {
        if (const auto *card = std::get_if<sts::search::OocCardTarget>(&selection->card))
            target = sts::getCardName(card->id);
        else if (const auto *candidate = std::get_if<sts::search::OocCandidateTarget>(&selection->card))
            target = candidate->card.getName();
    } else if (const auto *reward = std::get_if<sts::search::OocRewardTarget>(&payload))
        target = graphEntityName(reward->entity);
    else if (const auto *shop = std::get_if<sts::search::OocShopTarget>(&payload))
        target = graphEntityName(shop->entity);
    else if (const auto *relic = std::get_if<sts::search::OocRelicTarget>(&payload))
        target = sts::getRelicName(relic->relic);
    else if (const auto *event = std::get_if<sts::search::OocEventTarget>(&payload))
        target = std::to_string(event->option);
    else if (const auto *transaction = std::get_if<sts::search::OocTransactionTarget>(&payload))
        target = sts::getCardName(transaction->card.id);
    if (!target.empty()) label = action.semantic->effect == sts::search::OocSemanticEffect::TAKE_GOLD
        ? "Collect " + target : label + ": " + target;
    return label;
}
std::string graphActionLabel(const OocGameContextModel &model, const sts::search::OocTreeNode &node) {
    return candidateLabel(model.state(node.state), model.candidate(node.state, node.action));
}

// Diagnostic decision log (STS_OOC_MCTS_DECISION_LOG): what one live search
// treated as a decision inside its tree, at its leaves and in its rollouts.
// Observation only; nothing here feeds back into search or play.
struct OocDecisionLog {
    std::map<std::string, std::map<std::string, std::uint64_t>> counts;
    nlohmann::json sampleRollouts = nlohmann::json::array();
    nlohmann::json *rollout = nullptr;   // sampled rollout being recorded
    bool inRollout = false;
    std::size_t sampleLimit = 3;
    void add(const std::string &section, const std::string &key) { ++counts[section][key]; }
};
thread_local OocDecisionLog *t_decisionLog = nullptr;
std::string decisionLogPath;
constexpr const char *kLogScreens[] = {"INVALID", "EVENT", "REWARDS", "BOSS_RELIC",
    "CARD_SELECT", "MAP", "TREASURE", "REST", "SHOP", "BATTLE"};
std::string logScreen(const GameContext &gc) {
    const auto screen = static_cast<unsigned>(gc.screenState);
    std::string out = screen < std::size(kLogScreens) ? kLogScreens[screen] : "UNKNOWN";
    if (gc.screenState == sts::ScreenState::EVENT_SCREEN)
        out += std::string(":") + sts::eventIdStrings[static_cast<int>(gc.curEvent)];
    if (gc.screenState == sts::ScreenState::CARD_SELECT)
        out += ":select" + std::to_string(static_cast<int>(gc.info.selectScreenType));
    if (gc.screenState != sts::ScreenState::MAP_SCREEN)
        out += std::string("@") + sts::roomStrings[static_cast<int>(gc.curRoom)];
    return out;
}
std::string logEffect(const std::string &label) {
    const auto colon = label.find(':');
    return colon == std::string::npos ? label : label.substr(0, colon);
}
// Public summary of what one rollout step changed (no RNG, no copies of hidden state).
struct LogSnapshot {
    std::multiset<std::string> deck, relics, potions;
    int gold, hp, maxHp, floor;
    sts::ScreenState screen;
    sts::Room room;
    explicit LogSnapshot(const GameContext &gc) : gold(gc.gold), hp(gc.curHp), maxHp(gc.maxHp),
            floor(gc.floorNum), screen(gc.screenState), room(gc.curRoom) {
        for (const auto &c : gc.deck.cards) deck.insert(std::string(c.getName()) + (c.isUpgraded() ? "+" : ""));
        for (const auto &r : gc.relics.relics) relics.insert(sts::getRelicName(r.id));
        for (int i = 0; i < gc.potionCapacity && i < int(gc.potions.size()); ++i)
            if (gc.potions[i] != sts::Potion::EMPTY_POTION_SLOT && gc.potions[i] != sts::Potion::INVALID)
                potions.insert(sts::getPotionName(gc.potions[i]));
    }
};
std::pair<std::string, std::string> logDiff(const LogSnapshot &a, const LogSnapshot &b) {
    std::vector<std::string> detail;
    std::set<std::string> kinds;
    const auto sets = [&](const std::multiset<std::string> &x, const std::multiset<std::string> &y, const char *kind) {
        std::vector<std::string> added, removed;
        std::set_difference(y.begin(), y.end(), x.begin(), x.end(), std::back_inserter(added));
        std::set_difference(x.begin(), x.end(), y.begin(), y.end(), std::back_inserter(removed));
        for (const auto &v : added) { detail.push_back(std::string("+") + kind + ":" + v); kinds.insert(std::string("+") + kind); }
        for (const auto &v : removed) { detail.push_back(std::string("-") + kind + ":" + v); kinds.insert(std::string("-") + kind); }
    };
    sets(a.deck, b.deck, "card");
    sets(a.relics, b.relics, "relic");
    sets(a.potions, b.potions, "potion");
    if (b.gold != a.gold) { detail.push_back("gold:" + std::to_string(b.gold - a.gold)); kinds.insert(b.gold > a.gold ? "+gold" : "-gold"); }
    if (b.hp != a.hp) { detail.push_back("hp:" + std::to_string(b.hp - a.hp)); kinds.insert(b.hp > a.hp ? "+hp" : "-hp"); }
    if (b.maxHp != a.maxHp) { detail.push_back("maxHp:" + std::to_string(b.maxHp - a.maxHp)); kinds.insert("maxHp"); }
    if (a.screen == sts::ScreenState::MAP_SCREEN && b.floor != a.floor) {
        const std::string room = sts::roomStrings[static_cast<int>(b.room)];
        detail.push_back("enter:" + room); kinds.insert("enter:" + room);
    }
    std::string d, k;
    for (const auto &x : detail) d += (d.empty() ? "" : " ") + x;
    for (const auto &x : kinds) k += (k.empty() ? "" : " ") + x;
    return {d.empty() ? "no visible change" : d, k.empty() ? "no visible change" : k};
}
}
void annotateOocTree(const OocGameContextModel &model, sts::search::OocTreeSnapshot &tree) {
    static const char *screens[] = {"invalid", "event", "rewards", "boss relic",
        "card select", "map", "treasure", "rest", "shop", "battle"};
    for (auto &node : tree.nodes) {
        const auto &state = model.state(node.state);
        node.floor = state.floorNum;
        node.mapX = state.curMapNodeX;
        node.mapY = state.curMapNodeY;
        node.hp = state.curHp;
        node.maxHp = state.maxHp;
        node.gold = state.gold;
        const auto screen = static_cast<unsigned>(state.screenState);
        node.screen = screen < std::size(screens) ? screens[screen] : "unknown";
        const auto room = static_cast<unsigned>(state.curRoom);
        node.room = room < std::size(sts::roomStrings) ? sts::roomStrings[room] : "unknown";
        if (node.chance) {
            node.key = model.candidate(node.state, node.action).key;
            node.label = graphActionLabel(model, node);
        } else {
            node.outcome = state.outcome == sts::GameOutcome::PLAYER_LOSS ? "loss"
                : state.outcome == sts::GameOutcome::PLAYER_VICTORY ? "victory" : "undecided";
            std::string place = node.screen == "map" ? "Map choice"
                : graphRoomName(state.curRoom) + " room · " + node.screen;
            if (node.mapY >= 0) place += " (" + std::to_string(node.mapX) + "," + std::to_string(node.mapY) + ")";
            node.label = "Floor " + std::to_string(node.floor) + " · " + place
                + " · HP " + std::to_string(node.hp) + "/" + std::to_string(node.maxHp)
                + " · " + std::to_string(node.gold) + " gold";
            if (node.outcome == "loss") node.label = "CTM sampled loss · entered combat at HP "
                + std::to_string(node.hp) + "/" + std::to_string(node.maxHp)
                + " · final HP unavailable · Floor " + std::to_string(node.floor);
            if (node.outcome == "victory") node.label = "Victory · " + node.label;
        }
    }
    for (auto &edge : tree.edges) {
        if (!edge.particle || !edge.childId) continue;
        const auto &node = tree.nodes.at(*edge.childId);
        const auto &prediction = model.prediction(node.state);
        if (!prediction.used) continue;
        edge.combatModelUsed = true;
        const auto encounter = static_cast<unsigned>(prediction.encounter);
        edge.combatEncounter = encounter < std::size(sts::monsterEncounterEnumNames)
            ? sts::monsterEncounterEnumNames[encounter] : "unknown encounter";
        edge.combatOutcome = prediction.outcome;
    }
}
namespace {
// Search choice key; with tree rules, copies of one card are also a single
// choice for bottle, duplicate and bonfire (as for upgrade/remove/transform).
std::string mctsChoiceKey(sts::search::OocSemanticAction action, const GameContext &gc, bool treeRules) {
    using E = sts::search::OocSemanticEffect;
    if (treeRules && (action.effect == E::BOTTLE_CARD || action.effect == E::DUPLICATE_CARD
            || action.effect == E::SACRIFICE_CARD)) {
        if (auto *card = std::get_if<sts::search::OocCardTarget>(&action.target)) card->occurrence = 0;
        else if (auto *transaction = std::get_if<sts::search::OocTransactionTarget>(&action.target))
            transaction->card.occurrence = 0;
        else if (auto *selector = std::get_if<sts::search::OocSelectorTarget>(&action.target))
            if (auto *card = std::get_if<sts::search::OocCardTarget>(&selector->card)) card->occurrence = 0;
    }
    return sts::search::canonicalOocMctsChoiceKey(action, &gc);
}
}
std::optional<double> OocGameContextModel::terminalValue(sts::search::OocStateId id) const {
    switch (state(id).outcome) {
        case sts::GameOutcome::PLAYER_LOSS: return 0;
        case sts::GameOutcome::PLAYER_VICTORY:
            return sts::search::runGoalVictory(state(id), options.collectKeys, dependencies.stopAfterAct()) ? 1 : 0;
        case sts::GameOutcome::UNDECIDED: return std::nullopt;
    }
    throw std::runtime_error("OOC MCTS invalid outcome");
}
// heart1full scores screens V4 cannot encode, except card selects other than
// UPGRADE: student C was distilled with no CARD_SELECT rows and removes the best
// card (audit-2026-10-17 heart1-distill finding 1), so those stay uniform in the
// tree and go to the chain in rollouts.
static bool heart1FullScreen(const GameContext &gc) {
    return gc.screenState != sts::ScreenState::CARD_SELECT
        || gc.info.selectScreenType == sts::CardSelectScreenType::UPGRADE;
}
OocGameContextModel::Metadata &OocGameContextModel::mutableMetadata(sts::search::OocStateId id) const {
    const auto &snapshot = states.at(id);
    if (!snapshot.metadata) {
        OocProfileScope profile(OocProfileBucket::Metadata);
        Metadata value;
        const auto &gc = snapshot.gc;
        if (gc.outcome == sts::GameOutcome::UNDECIDED && gc.screenState == sts::ScreenState::MAP_SCREEN
            && v4DecisionSupported(gc)) {
            std::set<std::uint32_t> ids;
            for (auto action : v4CandidateActions(gc)) {
                if (!ids.insert(action.bits).second) { value.candidates.clear(); break; }
                value.candidates.push_back({action.bits, "map:" + std::to_string(action.bits), {}, action});
            }
            value.sourcePriorCovered = true;
        } else if (gc.outcome == sts::GameOutcome::UNDECIDED && gc.screenState != sts::ScreenState::BATTLE
                   && gc.screenState != sts::ScreenState::MAP_SCREEN) {
            const auto enumeration = sts::search::enumerateOocSemanticPrimitiveBindings(gc);
            if (enumeration.supported && enumeration.complete) {
                std::set<std::string> keys;
                std::set<std::string> cardChoices;
                std::set<std::uint32_t> sources;
                std::map<std::string, std::vector<GameAction>> groups;
                std::set<std::uint32_t> droppedKeys;
                for (const auto &binding : enumeration.bindings) {
                    if (!GameAction(binding.primitiveBits).isValidAction(gc)) continue;
                    if ((!options.collectKeys && (binding.semantic.effect == sts::search::OocSemanticEffect::TAKE_KEY
                            || binding.semantic.effect == sts::search::OocSemanticEffect::TAKE_RUBY_KEY))
                            || !sts::search::heartKeyActionAllowed(gc, options.collectKeys, GameAction(binding.primitiveBits))) {
                        droppedKeys.insert(binding.primitiveBits);
                        continue;
                    }
                    if (id == 0 && options.rootPrimitiveBits
                            && !options.rootPrimitiveBits->count(binding.primitiveBits)) continue;
                    const auto key = sts::search::canonicalOocSemanticActionKey(binding.semantic);
                    if (!keys.insert(key).second) { value.candidates.clear(); break; }
                    const auto choiceKey = mctsChoiceKey(binding.semantic, gc, options.treeRules);
                    groups[choiceKey].push_back(GameAction(binding.primitiveBits));
                    sources.insert(binding.primitiveBits);
                    if (!cardChoices.insert(choiceKey).second) continue;
                    value.candidates.push_back({static_cast<sts::search::OocActionId>(value.candidates.size()),
                        key, binding.semantic, GameAction(binding.primitiveBits), binding.compoundSelector});
                }
                if (!value.candidates.empty())
                    for (const auto &candidate : value.candidates)
                        value.priorSourceGroups.push_back(groups.at(
                            mctsChoiceKey(*candidate.semantic, gc, options.treeRules)));
                if (v4DecisionSupported(gc)) {
                    std::set<std::uint32_t> qualified;
                    auto primitives = v4CandidateActions(gc);
                    primitives.erase(std::remove_if(primitives.begin(), primitives.end(),
                        [&](auto action) { return droppedKeys.count(action.bits) != 0; }), primitives.end());
                    for (auto action : primitives)
                        if (id != 0 || !options.rootPrimitiveBits || options.rootPrimitiveBits->count(action.bits))
                            qualified.insert(action.bits);
                    const std::size_t qualifiedCount = std::count_if(primitives.begin(), primitives.end(),
                        [&](auto action) { return id != 0 || !options.rootPrimitiveBits
                            || options.rootPrimitiveBits->count(action.bits); });
                    value.sourcePriorCovered = qualified.size() == qualifiedCount && qualified == sources;
                }
            }
        }
        if (id == 0 && options.rootPrimitiveBits && gc.screenState == sts::ScreenState::MAP_SCREEN) {
            const auto &allowed = *options.rootPrimitiveBits;
            value.candidates.erase(std::remove_if(value.candidates.begin(), value.candidates.end(),
                [&](const auto &candidate) { return !allowed.count(candidate.primitive.bits); }),
                value.candidates.end());
            if (v4DecisionSupported(gc)) {
                std::set<std::uint32_t> qualified;
                for (const auto &action : v4CandidateActions(gc))
                    if (allowed.count(action.bits)) qualified.insert(action.bits);
                std::set<std::uint32_t> sources;
                for (const auto &candidate : value.candidates) sources.insert(candidate.primitive.bits);
                value.sourcePriorCovered = qualified == sources;
            }
        }
        if (options.heart1Coverage && !value.sourcePriorCovered && value.candidates.size() > 1
                && heart1FullScreen(gc))
            value.sourcePriorCovered = value.heart1OnlyCoverage = true;
        value.boundary = value.candidates.empty();
        value.edges.resize(value.candidates.size());
        snapshot.metadata = std::move(value);
        ++continuation_.metadataBuilds;
    }
    return *snapshot.metadata;
}
const OocGameContextModel::Metadata &OocGameContextModel::metadata(sts::search::OocStateId id) const {
    return mutableMetadata(id);
}
bool OocGameContextModel::isLeafBoundary(sts::search::OocStateId id) const {
    if (id != 0 && state(id).screenState == sts::ScreenState::MAP_SCREEN
            && options.stopAtMapCheckpoint)
        return true;
    return metadata(id).boundary;
}
std::optional<sts::search::OocActionId> OocGameContextModel::soleLegalAction(sts::search::OocStateId id) const {
    if (terminalValue(id) || isLeafBoundary(id)) return std::nullopt;
    const auto &actions = metadata(id).candidates;
    if (actions.size()==1 && actions.front().primitive.isValidAction(state(id))) {
        if (options.priorTracePath.empty()) return actions.front().id;
        auto &cached = mutableMetadata(id);
        if (!cached.priors)
            cached.priors = std::vector<sts::search::OocPlannerAction>{{actions.front().id, 1.0}};
        tracePrior(id, cached, *cached.priors);
        return actions.front().id;
    }
    return std::nullopt;
}
const OocGameContextModel::Candidate &OocGameContextModel::candidate(sts::search::OocStateId id,
    sts::search::OocActionId action) const {
    const auto &candidates = metadata(id).candidates;
    const auto it = std::find_if(candidates.begin(), candidates.end(),
        [&](const auto &c) { return c.id == action; });
    if (it == candidates.end()) throw std::runtime_error("OOC MCTS illegal action ID");
    return *it;
}
std::vector<double> OocGameContextModel::policyLogits(sts::search::OocStateId id) const {
    OocProfileScope profile(OocProfileBucket::PolicyLogits);
    if (terminalValue(id) || isLeafBoundary(id)) throw std::runtime_error("OOC MCTS actions requested at leaf");
    if (!dependencies.policyAvailable()) throw std::runtime_error("OOC MCTS V4 unavailable");
    const auto &snapshot = states.at(id);
    const auto &gc = snapshot.gc;
    auto &cached = mutableMetadata(id);
    if (cached.candidates.size() == 1) ++continuation_.singletonPolicyLogitCalls;
    if (cached.logits) return *cached.logits;
    const auto &actions = cached.candidates;
    if (!cached.sourcePriorCovered) return std::vector<double>(actions.size(), 0.0);
    if (actions.size() == 1) ++continuation_.singletonPolicyInferenceCalls;
    ++continuation_.priorBuilds;
    std::vector<GameAction> sources;
    std::map<std::uint32_t, std::size_t> sourceIndexes;
    const auto addSource = [&](GameAction a) {
        if (!sourceIndexes.count(a.bits)) {
            sourceIndexes.emplace(a.bits, sources.size());
            sources.push_back(a);
        }
    };
    for (std::size_t i = 0; i < actions.size(); ++i) {
        if (cached.priorSourceGroups.empty()) addSource(actions[i].primitive);
        else for (const auto a : cached.priorSourceGroups.at(i)) addSource(a);
    }
    OocProfileScope prediction(OocProfileBucket::PolicyPredict);
    std::optional<std::vector<double>> heart1Logits;
    if (options.heart1Prior) {
        heart1Logits = dependencies.heart1PolicyLogits(gc, sources, &continuation_.heart1PriorReasons);
        ++(heart1Logits ? continuation_.heart1PriorNodes : continuation_.heart1PriorFallbacks);
    }
    if (cached.heart1OnlyCoverage && !heart1Logits) {
        // V4 cannot score these sources: the node keeps its uniform prior.
        cached.heart1OnlyFailed = true;
        cached.logits = std::vector<double>(actions.size(), 0.0);
        return *cached.logits;
    }
    const auto sourceLogits = heart1Logits ? *heart1Logits : dependencies.policyLogits(gc, snapshot.path, sources);
    if (sourceLogits.size() != sources.size())
        throw std::runtime_error("OOC MCTS policy-logit count mismatch");
    for (double logit : sourceLogits)
        if (!std::isfinite(logit)) throw std::runtime_error("OOC MCTS nonfinite policy logit");
    if (!options.priorTracePath.empty())
        cached.priorTraceSources = Metadata::PriorTraceSources{sources, sourceLogits};
    std::vector<double> logits;
    logits.reserve(actions.size());
    for (std::size_t i = 0; i < actions.size(); ++i) {
        if (cached.priorSourceGroups.empty()) {
            logits.push_back(sourceLogits.at(sourceIndexes.at(actions[i].primitive.bits)));
        } else {
            const auto &group = cached.priorSourceGroups.at(i);
            double sum = 0;
            for (const auto action : group) sum += sourceLogits.at(sourceIndexes.at(action.bits));
            logits.push_back(sum / group.size()); // mean logit: no physical-copy multiplicity bonus
        }
    }
    cached.logits = logits;
    return logits;
}
void OocGameContextModel::tracePrior(sts::search::OocStateId id, Metadata &cached,
    const std::vector<sts::search::OocPlannerAction> &actions) const {
    if (options.priorTracePath.empty() || cached.priorTraceWritten) return;
    const auto &gc = state(id);
    const auto &candidates = cached.candidates;
    if (actions.size() != candidates.size())
        throw std::runtime_error("OOC MCTS prior trace candidate count mismatch");

    const bool singleton = candidates.size() == 1;
    const bool uniform = options.uniformPrior || !cached.sourcePriorCovered;
    const bool modelPrior = cached.sourcePriorCovered && !uniform && !singleton;
    static constexpr std::array<const char *, 10> screenNames = {"invalid", "event", "card reward",
        "boss relic", "card select", "map", "treasure", "rest", "shop", "battle"};
    const int screenId = int(gc.screenState);
    const std::string screenName = screenId >= 0 && screenId < int(screenNames.size())
        ? screenNames[screenId] : "unknown";
    const int roomId = int(gc.curRoom);
    const std::string roomName = roomId >= 0 && roomId < int(std::size(sts::roomStrings))
        ? sts::roomStrings[roomId] : "unknown";
    nlohmann::json row = {
        {"schemaVersion", 1},
        {"runSeed", options.priorTraceRunSeed},
        {"decisionIndex", options.priorTraceDecisionIndex},
        {"searchSeed", options.priorTraceSearchSeed},
        {"modelStateId", id},
        {"stateRole", id == 0 ? "root" : "hypothetical"},
        {"floor", gc.floorNum},
        {"screenId", screenId}, {"screen", screenName},
        {"roomId", roomId}, {"room", roomName},
        {"priorTemperature", options.priorTemperature},
        {"candidateCount", candidates.size()},
        {"sourcePriorCovered", cached.sourcePriorCovered},
        {"singleton", singleton},
        {"uniformPrior", uniform},
        {"candidates", nlohmann::json::array()}
    };

    std::vector<double> normalizedWeights;
    if (modelPrior) {
        if (!cached.logits || cached.logits->size() != candidates.size())
            throw std::runtime_error("OOC MCTS prior trace missing production candidate logits");
        if (!cached.priorTraceSources)
            throw std::runtime_error("OOC MCTS prior trace missing native source logits");
        const auto &sources = cached.priorTraceSources->actions;
        const auto &sourceLogits = cached.priorTraceSources->logits;
        if (sources.size() != sourceLogits.size())
            throw std::runtime_error("OOC MCTS prior trace source-logit count mismatch");
        std::map<std::uint32_t, std::size_t> sourceIndexes;
        for (std::size_t i = 0; i < sources.size(); ++i) {
            if (!sourceIndexes.emplace(sources[i].bits, i).second)
                throw std::runtime_error("OOC MCTS prior trace duplicate source primitive");
            if (!std::isfinite(sourceLogits[i]))
                throw std::runtime_error("OOC MCTS prior trace nonfinite source logit");
        }
        if (cached.priorSourceGroups.empty() && sources.size() != candidates.size())
            throw std::runtime_error("OOC MCTS prior trace direct-source count mismatch");
        if (!cached.priorSourceGroups.empty() && cached.priorSourceGroups.size() != candidates.size())
            throw std::runtime_error("OOC MCTS prior trace source-group count mismatch");

        const auto tokenState = buildTokStatePure(gc, states.at(id).path);
        if (tokenState.nDk < 0 || tokenState.nDk > 96
                || tokenState.nRl < 0 || tokenState.nRl > 64
                || tokenState.nPt < 0 || tokenState.nPt > 8)
            throw std::runtime_error("OOC MCTS prior trace invalid token-state length");
        nlohmann::json tokens = {{"glob", nlohmann::json::array()},
            {"deck", {{"nDk", tokenState.nDk}, {"tokens", nlohmann::json::array()}}},
            {"relic", {{"nRl", tokenState.nRl}, {"tokens", nlohmann::json::array()}}},
            {"potion", {{"nPt", tokenState.nPt}, {"tokens", nlohmann::json::array()}}}};
        for (const float value : tokenState.glob) {
            if (!std::isfinite(value)) throw std::runtime_error("OOC MCTS prior trace nonfinite global input");
            tokens["glob"].push_back(value);
        }
        for (int i = 0; i < tokenState.nDk; ++i)
            tokens["deck"]["tokens"].push_back({tokenState.dk[i][0], tokenState.dk[i][1], tokenState.dk[i][2]});
        for (int i = 0; i < tokenState.nRl; ++i)
            tokens["relic"]["tokens"].push_back({tokenState.rl[i][0], tokenState.rl[i][1]});
        for (int i = 0; i < tokenState.nPt; ++i)
            tokens["potion"]["tokens"].push_back({tokenState.pt[i][0], tokenState.pt[i][1]});
        row["tokenState"] = std::move(tokens);

        row["sourcePrimitives"] = nlohmann::json::array();
        for (std::size_t i = 0; i < sources.size(); ++i) {
            int type, c1, c2, c3, d1, d2, d3, entityType, entityId;
            float price;
            strategicCands(gc, sources[i], type, c1, c2, c3, d1, d2, d3);
            tokEntity(gc, sources[i], entityType, entityId, price);
            if (!std::isfinite(price))
                throw std::runtime_error("OOC MCTS prior trace nonfinite source-action feature");
            row["sourcePrimitives"].push_back({
                {"primitiveBits", sources[i].bits}, {"actionType", type},
                {"cats", {c1, c2, c3, d1, d2, d3}}, {"screen", int(gc.screenState)},
                {"entityType", entityType}, {"entityId", entityId},
                {"goldGePrice", price}, {"teacherSourceLogit", sourceLogits[i]}});
        }

        std::vector<double> reproducedCandidateLogits;
        reproducedCandidateLogits.reserve(candidates.size());
        for (std::size_t i = 0; i < candidates.size(); ++i) {
            double reproduced = 0;
            if (cached.priorSourceGroups.empty()) {
                const auto found = sourceIndexes.find(candidates[i].primitive.bits);
                if (found == sourceIndexes.end())
                    throw std::runtime_error("OOC MCTS prior trace direct primitive source missing");
                reproduced = sourceLogits.at(found->second);
            } else {
                const auto &group = cached.priorSourceGroups.at(i);
                if (group.empty()) throw std::runtime_error("OOC MCTS prior trace empty semantic source group");
                for (const auto source : group) {
                    const auto found = sourceIndexes.find(source.bits);
                    if (found == sourceIndexes.end())
                        throw std::runtime_error("OOC MCTS prior trace semantic source missing");
                    reproduced += sourceLogits.at(found->second);
                }
                reproduced /= group.size();
            }
            if (!std::isfinite(reproduced) || reproduced != cached.logits->at(i))
                throw std::runtime_error("OOC MCTS prior trace candidate-logit reproduction mismatch");
            reproducedCandidateLogits.push_back(reproduced);
        }

        auto expectedWeights = oocPolicyWeights(reproducedCandidateLogits, options.priorTemperature);
        std::map<std::uint32_t, std::size_t> multiplicity;
        for (const auto &candidate : candidates) ++multiplicity[candidate.primitive.bits];
        for (std::size_t i = 0; i < expectedWeights.size(); ++i) {
            expectedWeights[i] /= multiplicity.at(candidates[i].primitive.bits);
            if (!std::isfinite(expectedWeights[i]) || actions[i].id != candidates[i].id
                    || expectedWeights[i] != actions[i].prior)
                throw std::runtime_error("OOC MCTS prior trace planner-weight reproduction mismatch");
        }
        const double totalWeight = std::accumulate(expectedWeights.begin(), expectedWeights.end(), 0.0);
        if (!std::isfinite(totalWeight) || totalWeight <= 0)
            throw std::runtime_error("OOC MCTS prior trace invalid prior normalization");
        normalizedWeights.reserve(expectedWeights.size());
        for (const double weight : expectedWeights) normalizedWeights.push_back(weight / totalWeight);

        row["teacherCandidateLogits"] = reproducedCandidateLogits;
        row["teacherRawPriorWeights"] = expectedWeights;
        row["teacherNormalizedPrior"] = normalizedWeights;
    }

    for (std::size_t i = 0; i < candidates.size(); ++i) {
        if (actions[i].id != candidates[i].id)
            throw std::runtime_error("OOC MCTS prior trace candidate ID/order mismatch");
        const auto &candidate = candidates[i];
        nlohmann::json groups = nlohmann::json::array();
        if (!cached.priorSourceGroups.empty())
            for (const auto source : cached.priorSourceGroups.at(i)) groups.push_back(source.bits);
        nlohmann::json item = {{"candidateId", candidate.id}, {"semanticKey", candidate.key},
            {"primitiveBits", candidate.primitive.bits}, {"hasSemantic", candidate.semantic.has_value()},
            {"compoundSelector", int(candidate.compoundSelector)}, {"priorSourceGroup", std::move(groups)},
            {"searchPriorWeight", actions[i].prior}};
        if (modelPrior) {
            item["teacherCandidateLogit"] = cached.logits->at(i);
            item["teacherRawPriorWeight"] = actions[i].prior;
            item["teacherNormalizedPrior"] = normalizedWeights.at(i);
        }
        row["candidates"].push_back(std::move(item));
    }

    std::lock_guard<std::mutex> lock(liveTraceMutex);
    std::ofstream out(options.priorTracePath, std::ios::app);
    if (!out) throw std::runtime_error("STS_OOC_MCTS_PRIOR_TRACE cannot open output");
    out << row.dump() << '\n';
    if (!out) throw std::runtime_error("STS_OOC_MCTS_PRIOR_TRACE write failed");
    cached.priorTraceWritten = true;
}
// STS_OOC_MCTS_TARGET_PRIOR: split a compound source's prior over its target cards by heart1's
// policy on the selector screen the source opens, instead of equally. A group heart1 cannot
// score keeps the equal split.
void OocGameContextModel::applyTargetPrior(const GameContext &gc, const std::vector<Candidate> &actions,
                                           std::vector<double> &weights) const {
    std::map<std::uint32_t, std::vector<std::size_t>> groups;
    for (std::size_t i = 0; i < actions.size(); ++i)
        if (actions[i].compoundSelector != sts::CardSelectScreenType::INVALID && actions[i].semantic)
            groups[actions[i].primitive.bits].push_back(i);
    auto &reasons = continuation_.heart1PriorReasons;
    for (const auto &[bits, members] : groups) {
        if (members.size() < 2) continue;
        auto selector = detachedCopy(gc);
        GameAction(bits).execute(selector);
        if (selector.screenState != sts::ScreenState::CARD_SELECT || selector.info.toSelectCount != 1) {
            ++reasons["target:skip_not_single_select"]; continue;
        }
        const auto selectActions = GameAction::getAllActionsInState(selector);
        const auto logits = dependencies.heart1PolicyLogits(selector, selectActions, &reasons);
        if (!logits || logits->size() != selectActions.size()) { ++reasons["target:skip_unscored"]; continue; }
        const auto probs = oocPolicyWeights(*logits, options.priorTemperature);
        std::vector<double> shares;
        for (const auto i : members) {
            auto copy = detachedCopy(gc);
            const auto executed = sts::search::executeOocSemanticAction(copy, *actions[i].semantic);
            if (!executed.ok || executed.executedPrimitiveBits.size() != 2
                    || executed.executedPrimitiveBits.front() != bits) break;
            const auto pick = std::find_if(selectActions.begin(), selectActions.end(),
                [&](const auto &a) { return a.bits == executed.executedPrimitiveBits.back(); });
            if (pick == selectActions.end()) break;
            shares.push_back(probs[pick - selectActions.begin()]);
        }
        double total = 0.0, mass = 0.0;
        for (const auto s : shares) total += s;
        if (shares.size() != members.size() || !(total > 0.0)) { ++reasons["target:skip_unmatched"]; continue; }
        for (const auto i : members) mass += weights[i];
        for (std::size_t k = 0; k < members.size(); ++k) weights[members[k]] = mass * shares[k] / total;
        ++reasons["target:scored"];
    }
}
// STS_OOC_MCTS_POTION_KEEP_PRIOR: discard candidates on a reward screen are scored relative to
// "Leave rewards" by ADR-0039 keep values. Discarding only gains the best reward potion when the
// belt is full and Sozu is absent; otherwise the gain is nothing and the discard is a pure loss.
static bool applyPotionKeepPrior(const GameContext &gc,
    const std::vector<OocGameContextModel::Candidate> &actions, std::vector<double> &logits) {
    if (gc.screenState != ScreenState::REWARDS) return false;
    std::vector<std::size_t> discards;
    std::optional<double> leave;
    double bestOther = -std::numeric_limits<double>::infinity();
    for (std::size_t i = 0; i < actions.size(); ++i) {
        const auto effect = actions[i].semantic ? std::optional(actions[i].semantic->effect) : std::nullopt;
        if (effect == sts::search::OocSemanticEffect::DISCARD_POTION) discards.push_back(i);
        else if (effect == sts::search::OocSemanticEffect::LEAVE_REWARDS) leave = logits[i];
        else bestOther = std::max(bestOther, logits[i]);
    }
    if (discards.empty()) return false;
    const double base = leave ? *leave : std::isfinite(bestOther) ? bestOther : 0.0;
    const auto &r = gc.info.rewardsContainer;
    int offered = 0;
    if (gc.potionCount >= gc.potionCapacity && !gc.hasRelic(RelicId::SOZU))
        for (int i = 0; i < r.potionCount; ++i) offered = std::max(offered, sts::search::potionKeepRank(r.potions[i]));
    for (const auto i : discards) {
        const int slot = actions[i].primitive.getIdx1();
        const int held = slot >= 0 && slot < gc.potionCapacity ? sts::search::potionKeepRank(gc.potions[slot]) : 0;
        logits[i] = base + double(offered - std::max(held, 0)) / 100.0;
    }
    return true;
}
std::vector<sts::search::OocPlannerAction> OocGameContextModel::legalActions(sts::search::OocStateId id) const {
    OocProfileScope priorBuild(OocProfileBucket::PriorBuild);
    if (terminalValue(id) || isLeafBoundary(id)) throw std::runtime_error("OOC MCTS actions requested at leaf");
    auto &cached = mutableMetadata(id);
    if (cached.priors) return *cached.priors;
    const auto &actions = cached.candidates;
    if (t_decisionLog) {
        const auto n = actions.size();
        const std::string width = n == 1 ? "1 option" : n <= 3 ? "2-3 options" : n <= 9 ? "4-9 options" : "10+ options";
        t_decisionLog->add(id == 0 ? "root_node" : "tree_node", logScreen(state(id)) + " | " + width
            + (n > 1 && (options.uniformPrior || !cached.sourcePriorCovered) ? " | uniform prior" : ""));
    }
    OocProfileScope singletonPrior(OocProfileBucket::SingletonPrior, actions.size() == 1);
    if (actions.size() == 1) {
        std::vector<sts::search::OocPlannerAction> result{{actions.front().id, 1.0}};
        cached.priors = result;
        tracePrior(id, cached, result);
        return result;
    }
    bool uniform = options.uniformPrior || !cached.sourcePriorCovered;
    std::vector<double> weights;
    std::optional<std::vector<double>> logits;
    if (!uniform) {
        logits = policyLogits(id);
        uniform = cached.heart1OnlyFailed;
        if (uniform) logits.reset();
    }
    if (options.potionKeepPrior && !options.uniformPrior) {
        // A uniform node scores its other candidates 0, so discards sit relative to that.
        auto keep = logits ? *logits : std::vector<double>(actions.size(), 0.0);
        if (applyPotionKeepPrior(state(id), actions, keep)) {
            logits = keep;
            uniform = false;
            if (t_decisionLog) t_decisionLog->add("potion_keep_prior", id == 0 ? "root" : "tree");
        }
    }
    if (!uniform) weights = oocPolicyWeights(*logits, options.priorTemperature);
    if (uniform) weights.assign(actions.size(), 1.0);
    if (!uniform) {
        std::map<std::uint32_t, std::size_t> counts;
        for (const auto &a : actions) ++counts[a.primitive.bits];
        for (std::size_t i=0; i<actions.size(); ++i) weights[i] /= counts.at(actions[i].primitive.bits);
        if (options.targetPrior) applyTargetPrior(state(id), actions, weights);
    }
    std::vector<sts::search::OocPlannerAction> result;
    result.reserve(actions.size());
    for (std::size_t i=0; i<actions.size(); ++i)
        result.push_back({actions[i].id, weights[i]});
    cached.priors = result;
    tracePrior(id, cached, result);
    return result;
}
sts::search::OocStateId OocGameContextModel::sampleSuccessor(sts::search::OocStateId id,
    sts::search::OocActionId action, std::mt19937_64 &rng) {
    OocProfileScope profile(OocProfileBucket::Successor);
    if (terminalValue(id) || isLeafBoundary(id)) throw std::runtime_error("OOC MCTS transition from leaf");
    auto &cached = mutableMetadata(id);
    const auto &actions = cached.candidates;
    auto it = std::find_if(actions.begin(), actions.end(), [&](const auto &a) { return a.id == action; });
    if (it == actions.end()) throw std::runtime_error("OOC MCTS illegal action ID");
    auto &edge = cached.edges.at(it - actions.begin());
    if (!options.sampleNoncombat && edge.deterministic) return *edge.deterministic;
    auto child = Snapshot{detachedCopy(state(id)), states.at(id).path, {}};
    // A live MAP root is searchable.  The hidden room outcome must be sampled
    // before transitionToMapNode consumes monster/shop/treasure chances.
    // Qualified successors retain their updated room counters.
    if (options.sampleNoncombat) {
        sampleNoncombatFuture(child.gc, rng);
        if (id == 0 && dependencies.sampleHiddenCounters)
            dependencies.sampleHiddenCounters(child.gc, rng);
    }
    if (it->semantic) {
        const auto executed = sts::search::executeOocSemanticAction(child.gc, *it->semantic);
        if (!executed.ok) throw sts::search::OocSearchUnsupported("semantic_execution:" + executed.error);
    } else it->primitive.execute(child.gc);
    collectForcedRewardGold(child.gc);
    child.path.update(child.gc);
    const bool enteredCombat = child.gc.screenState == sts::ScreenState::BATTLE;
    const auto encounter = enteredCombat ? child.gc.info.encounter : sts::MonsterEncounter::INVALID;
    // A sampled future can change the encounter and predictor input on every
    // visit. Never borrow a preparation from another hypothetical successor.
    std::unique_ptr<PreparedCombatTransition> sampledCombat;
    auto &preparationCache = options.sampleNoncombat ? sampledCombat : edge.combat;
    if (enteredCombat && combatSampler && !preparationCache) {
        OocProfileScope preparation(OocProfileBucket::CombatPrepare);
        const auto input = captureCombatPredictorInput(child.gc, child.gc.info.encounter,
                                                       dependencies.potionKeepValue(child.gc));
        preparationCache = combatSampler->prepare(child.gc, input);
        ++continuation_.preparedCombats;
    }
    if (enteredCombat) ++continuation_.combatEdgeSamples;
    if (options.checkpointLeaves && enteredCombat) {
        const auto outcome = resolveCombat(child, rng, preparationCache.get());
        child.combatPrediction = {true, encounter,
            outcome == CombatRuntimeSample::Outcome::DEATH ? "death"
            : outcome == CombatRuntimeSample::Outcome::ESCAPE ? "escape" : "victory"};
    }
    else if (combatSampler && enteredCombat) {
        if (preparationCache->support().supported) {
            ++combatSamples_;
            const auto sampled = preparationCache->sample(rng);
            if (sampled.outcome != CombatRuntimeSample::Outcome::UNSUPPORTED)
                child.combatPrediction = {true, encounter,
                    sampled.outcome == CombatRuntimeSample::Outcome::DEATH ? "death"
                    : sampled.outcome == CombatRuntimeSample::Outcome::ESCAPE ? "escape" : "victory"};
            switch (sampled.outcome) {
                case CombatRuntimeSample::Outcome::UNSUPPORTED: break;
                case CombatRuntimeSample::Outcome::DEATH:
                    child.gc.outcome = sts::GameOutcome::PLAYER_LOSS;
                    break;
                case CombatRuntimeSample::Outcome::VICTORY:
                case CombatRuntimeSample::Outcome::ESCAPE:
                    applySampledCombatExit(child.gc, sampled);
                    // Live runs record the entered room before combat and the
                    // continuation on the next loop, including act changes.
                    child.path.update(child.gc);
                    break;
            }
        }
    }
#ifndef STS_LIVE_ADVISOR
    if (options.treeRules && child.gc.outcome == sts::GameOutcome::UNDECIDED) {
        bool applied = false;
        while (oocTreeRuleStep(child.gc)) applied = true;
        if (applied) child.path.update(child.gc);
    }
#endif
    if (!options.sampleNoncombat && options.checkpointLeaves && !enteredCombat) edge.deterministic = states.size();
    if (t_decisionLog) {
        const auto &source = state(id);
        std::string label = logEffect(candidateLabel(source, *it));
        if (source.screenState == sts::ScreenState::MAP_SCREEN)
            label = std::string("Travel to ") + sts::roomStrings[static_cast<int>(child.gc.curRoom)];
        t_decisionLog->add("tree_action", logScreen(source) + " | " + label);
        if (enteredCombat)
            t_decisionLog->add("tree_combat", std::string(sts::monsterEncounterEnumNames[static_cast<int>(encounter)])
                + " -> " + (child.combatPrediction.used ? child.combatPrediction.outcome : "unsupported"));
        t_decisionLog->add("tree_successor", logScreen(child.gc));
    }
    if (options.siblingCapture) parents_[states.size()] = {id, action};
    states.push_back(std::move(child));
    return states.size()-1;
}
double OocGameContextModel::bossLeafValue(const GameContext &source) const {
    if (!combatSampler) throw std::runtime_error("OOC MCTS boss leaf requires combat evaluator");
    struct BossProbe { sts::MonsterEncounter encounter; int act, floor; };
    static constexpr BossProbe bosses[] = {
        {sts::MonsterEncounter::SLIME_BOSS, 1, 17},
        {sts::MonsterEncounter::THE_GUARDIAN, 1, 17},
        {sts::MonsterEncounter::HEXAGHOST, 1, 17},
        {sts::MonsterEncounter::CHAMP, 2, 34},
        {sts::MonsterEncounter::COLLECTOR, 2, 34},
        {sts::MonsterEncounter::AUTOMATON, 2, 34},
        {sts::MonsterEncounter::AWAKENED_ONE, 3, 50},
        {sts::MonsterEncounter::DONU_AND_DECA, 3, 50},
        {sts::MonsterEncounter::TIME_EATER, 3, 50},
        {sts::MonsterEncounter::THE_HEART, 4, 55}
    };
    double total = 0;
    for (const auto &boss : bosses) {
        auto probe = detachedCopy(source);
        const auto encounter = boss.encounter;
        probe.act = boss.act;
        probe.floorNum = boss.floor;
        probe.curRoom = sts::Room::BOSS;
        probe.info.encounter = encounter;
        const auto input = captureCombatPredictorInput(probe, encounter,
                                                       dependencies.potionKeepValue(probe));
        const auto estimate = combatSampler->expectation(probe, input);
        if (!estimate.supported)
            throw sts::search::OocSearchUnsupported("boss_leaf_unsupported_" + std::to_string((int)encounter));
        const double value = bossLeafUtility(estimate);
        if (!std::isfinite(value) || value < 0 || value > 1)
            throw std::runtime_error("OOC MCTS invalid boss leaf value");
        total += value;
    }
    return total / std::size(bosses);
}
double OocGameContextModel::leafValue(sts::search::OocStateId id) const {
    OocProfileScope profile(OocProfileBucket::EvaluateLeaf);
    if (options.checkpointLeaves && !terminalValue(id)
        && state(id).screenState != sts::ScreenState::MAP_SCREEN)
        throw std::runtime_error("OOC MCTS leaf requires a resolved map checkpoint");
    if (auto terminal = terminalValue(id)) return *terminal;
    if (options.checkpointLeaves && options.constantLeaf) return 0.5;
    if (options.bossLeaf) return bossLeafValue(state(id));
    OocProfileScope inference(OocProfileBucket::LeafValue);
    return anchorValue(state(id), states.at(id).path);
}
std::optional<std::uint64_t> OocGameContextModel::outcomeEquivalenceKey(sts::search::OocStateId id) const {
    // Without sampled futures a successor's concrete RNG is its future.
    if (!options.sampleNoncombat) return std::nullopt;
    return outcomeEquivalenceKeyOf(state(id), pathHistory(id));
}
bool OocGameContextModel::isDeterministicTransition(sts::search::OocStateId id,
    sts::search::OocActionId action) const {
    if (options.sampleNoncombat) return false;
    const auto &cached = metadata(id);
    const auto it = std::find_if(cached.candidates.begin(), cached.candidates.end(),
        [&](auto candidate) { return candidate.id == action; });
    return it != cached.candidates.end() && cached.edges.at(it-cached.candidates.begin()).deterministic.has_value();
}
CombatRuntimeSample::Outcome OocGameContextModel::resolveCombat(Snapshot &child, std::mt19937_64 &rng,
    const PreparedCombatTransition *prepared) {
    OocProfileScope profile(OocProfileBucket::CombatResolve);
    ++continuation_.imaginedCombats;
    const int battleAct = child.gc.act;
    const auto battleRoom = child.gc.curRoom;
    const bool firstA20Act3Boss = battleAct == 3 && child.gc.ascension >= 20
        && child.gc.info.encounter == child.gc.boss;
    bool victory = false;
    auto sampledOutcome = CombatRuntimeSample::Outcome::UNSUPPORTED;
    const auto input = prepared ? CombatPredictorInputV1{}
        : captureCombatPredictorInput(child.gc, child.gc.info.encounter,
                                      dependencies.potionKeepValue(child.gc));
    const auto support = prepared ? prepared->support()
        : combatSampler ? combatSampler->support(child.gc, input)
                        : CombatRuntimeSupport{false, "missing_sampler"};
    auto reason = support.reason;
    if (support.supported) {
        const auto sampled = prepared ? prepared->sample(rng) : combatSampler->sample(child.gc, input, rng);
        if (sampled.outcome != CombatRuntimeSample::Outcome::UNSUPPORTED) {
            sampledOutcome = sampled.outcome;
            ++combatSamples_;
            if (sampled.outcome != CombatRuntimeSample::Outcome::DEATH) {
                applySampledCombatExit(child.gc, sampled);
                victory = true;
            }
        } else reason = "sample_returned_unsupported";
    }
    if (t_decisionLog && t_decisionLog->inRollout) {
        const std::string encounter = sts::monsterEncounterEnumNames[static_cast<int>(child.gc.info.encounter)];
        const std::string outcome = sampledOutcome == CombatRuntimeSample::Outcome::DEATH ? "death"
            : sampledOutcome == CombatRuntimeSample::Outcome::ESCAPE ? "escape"
            : sampledOutcome == CombatRuntimeSample::Outcome::VICTORY ? "victory" : "unsupported:" + reason;
        t_decisionLog->add("rollout_combat", encounter + " -> " + outcome);
        if (t_decisionLog->rollout)
            t_decisionLog->rollout->at("steps").push_back({{"floor", child.gc.floorNum}, {"screen", "BATTLE"},
                {"by", "CTM sample"}, {"result", encounter + " -> " + outcome
                    + (victory ? " (HP " + std::to_string(child.gc.curHp) + "/" + std::to_string(child.gc.maxHp) + ")" : "")}});
    }
    if (sampledOutcome == CombatRuntimeSample::Outcome::DEATH) {
        child.gc.outcome = sts::GameOutcome::PLAYER_LOSS;
        return sampledOutcome;
    }
    if (!victory) {
        ++continuation_.unsupportedCombats;
        ++continuation_.supportReasons[reason.empty() ? "unspecified" : reason];
        throw sts::search::OocSearchUnsupported(reason.empty() ? "unspecified" : reason);
    }
    if (victory && dependencies.stopAfterAct() > 0 && battleAct == dependencies.stopAfterAct()
            && battleRoom == sts::Room::BOSS && !firstA20Act3Boss)
        child.gc.outcome = sts::GameOutcome::PLAYER_VICTORY;
    child.path.update(child.gc);
    return sampledOutcome;
}
namespace {
template<class Checkpoint, class Step>
double boundedContinuation(int maxSteps, Checkpoint checkpoint, Step advance) {
    for (int step=0; step<maxSteps; ++step) {
        if (const auto value=checkpoint()) return *value;
        advance();
    }
    if (const auto value=checkpoint()) return *value;
    throw sts::search::OocSearchUnsupported("continuation_step_limit_" + std::to_string(maxSteps));
}

#ifndef STS_LIVE_ADVISOR
// Preserve observers and run-local policy bookkeeping across detached work.
struct ImaginedScope {
    const PathHistory *path = t_curPath;
    std::string rows = std::move(t_oocStrategicTraceRows);
    int decision = t_oocStrategicTraceDecision;
    bool shop = t_shopV, tok = t_tokCheckPending;
    int probeDecision = t_actFightProbeDecisionIdx, probeAction = t_actFightProbeActionIdx,
        probeFuture = t_actFightProbeFutureIdx;
    decltype(sts::search::g_onGameActionExecute) observer = std::move(sts::search::g_onGameActionExecute);
    decltype(sts::search::g_onCombatDecision) combatObserver=std::move(sts::search::g_onCombatDecision);
    decltype(sts::g_onBattleExitPersistent) exitObserver=std::move(sts::g_onBattleExitPersistent);
    sts::search::NativeSilverCombatStats silver = sts::search::g_nativeSilverCombatStats;
    bool disallowed = sts::search::g_disallowImaginedCombat;
    ImaginedScope() {
        sts::search::g_disallowImaginedCombat=true;
        t_tokCheckPending=false; sts::search::g_onGameActionExecute={};
        sts::search::g_onCombatDecision={};
        sts::g_onBattleExitPersistent={};
    }
    ~ImaginedScope() {
        t_curPath=path; t_oocStrategicTraceRows=std::move(rows); t_oocStrategicTraceDecision=decision;
        t_shopV=shop; t_tokCheckPending=tok;
        t_actFightProbeDecisionIdx=probeDecision; t_actFightProbeActionIdx=probeAction; t_actFightProbeFutureIdx=probeFuture;
        sts::search::g_onGameActionExecute=std::move(observer);
        sts::search::g_onCombatDecision=std::move(combatObserver);
        sts::g_onBattleExitPersistent=std::move(exitObserver);
        sts::search::g_nativeSilverCombatStats=silver;
        sts::search::g_disallowImaginedCombat=disallowed;
    }
};
#endif
}
namespace {
sts::search::OocEndpoint endpointOf(const sts::GameContext &gc) {
    return {gc.curHp, gc.maxHp, gc.floorNum};
}
}
std::optional<sts::search::OocEndpoint> OocGameContextModel::endpoint(sts::search::OocStateId id) const {
    return endpointOf(state(id));
}
double OocGameContextModel::evaluateLeaf(sts::search::OocStateId id, std::mt19937_64 &rng) {
    bool terminal = false;
    sts::search::OocEndpoint endpoint;
    return evaluateLeafImpl(id, rng, terminal, endpoint);
}
sts::search::OocLeafEvaluation OocGameContextModel::evaluateLeafWithOutcome(
        sts::search::OocStateId id, std::mt19937_64 &rng) {
    bool terminal = false;
    sts::search::OocEndpoint endpoint;
    const double value = evaluateLeafImpl(id, rng, terminal, endpoint);
    return {value, terminal, endpoint};
}
std::optional<double> OocGameContextModel::screenLeafValue(const GameContext &gc, const PathHistory &path) {
#ifdef STS_LIVE_ADVISOR
    (void)gc; (void)path; throw std::runtime_error("screen leaf is unavailable in the live advisor");
#else
    if (!options.screenLeafNet && !options.screenLeafGbm) throw std::runtime_error("screen leaf requested without a loaded model");
    nlohmann::json contract;
    try { contract = screenLeafPublicContract(gc); }
    catch (const std::exception &) { ++continuation_.screenLeafFallbacks; return std::nullopt; }
    const auto &contents = contract.at("screenContents");
    if (options.screenLeafNet && !options.screenLeafNet->covers(contents.at("screen").get<std::string>())) {
        ++continuation_.screenLeafFallbacks; return std::nullopt;
    }
    std::vector<float> rich;
    if (options.screenLeafGbm) rich = richFeatureVec(gc, path);
    else {
        const std::string row = richRow(gc, path);
        rich.reserve(1017);
        for (const char *p = row.c_str(); *p;) {
            char *end = nullptr; rich.push_back(std::strtof(p, &end));
            if (end == p) throw std::runtime_error("screen leaf rich row parse");
            p = *end == ',' ? end + 1 : end;
        }
    }
    OocProfileScope inference(OocProfileBucket::LeafValue);
    ++continuation_.screenLeafEvaluations;
    const auto keys = contract.at("candidateKeys").get<std::vector<std::string>>();
    if (options.screenLeafGbm) {
        static const int goldIndex = richIdxMap().at("gold");
        const auto screenFeatures = screenGbmFeatures(contents, keys, rich.at(goldIndex));
        rich.insert(rich.end(), screenFeatures.begin(), screenFeatures.end());
        const double x2b = std::clamp(anchorValue(gc, path), 1e-7, 1 - 1e-7);
        const double margin = std::log(x2b / (1 - x2b)) + options.screenLeafGbm->residual(rich);
        return 1.0 / (1.0 + std::exp(-margin));
    }
    return options.screenLeafNet->predictFromRich(rich, contents, keys);
#endif
}
double OocGameContextModel::anchorValue(const GameContext &gc, const PathHistory &path) const {
#ifndef STS_LIVE_ADVISOR
    if (options.screenLeafGbm && options.screenLeafGbm->hasAnchor()) {
        OocProfileScope predict(OocProfileBucket::LeafPredict);
        return options.screenLeafGbm->anchor(richFeatureVec(gc, path));
    }
    if (options.heartLeaf) {
        OocProfileScope predict(OocProfileBucket::LeafPredict);
        return options.heartLeaf->value(gc, path);
    }
    if (options.leafWinNet) {
        OocProfileScope predict(OocProfileBucket::LeafPredict);
        const double value = options.leafWinNet->predict(richFeatureVec(gc, path));
        if (!std::isfinite(value) || value < 0 || value > 1)
            throw std::runtime_error("OOC MCTS invalid leaf win model value");
        return value;
    }
#endif
    return dependencies.leafValue(gc, path);
}
// `endpoint` receives the player state that was actually evaluated: the node
// itself, or the detached continuation where it stopped.
double OocGameContextModel::evaluateLeafImpl(sts::search::OocStateId id,
        std::mt19937_64 &rng, bool &terminal, sts::search::OocEndpoint &endpoint) {
#ifndef STS_LIVE_ADVISOR
    if (options.siblingCapture) {
        auto row = siblingLeafExtras(id);
        const double value = evaluateLeafObserved(id, rng, terminal, endpoint);
        if (row) {
            (*row)["value"] = value;
            (*row)["valueTerminal"] = terminal;
            (*row)["valueEndFloor"] = endpoint.floor;
            options.siblingCapture->write(*row);
        }
        return value;
    }
#endif
    return evaluateLeafObserved(id, rng, terminal, endpoint);
}
#ifndef STS_LIVE_ADVISOR
// Extra evaluations run in a forked child from the untouched pre-evaluation
// parent, so the scheduled leaf evaluation and the search are unchanged.
std::optional<nlohmann::json> OocGameContextModel::siblingLeafExtras(sts::search::OocStateId id) {
    auto &capture = *options.siblingCapture;
    if (id == 0 || capture.captured >= capture.maxLeaves) return std::nullopt;
    const auto parent = parents_.find(id);
    if (parent == parents_.end()) return std::nullopt;
    unsigned depth = 1;
    for (auto at = parent->second.first; at != 0; ++depth) {
        const auto up = parents_.find(at);
        if (up == parents_.end() || depth > capture.maxDepth) return std::nullopt;
        at = up->second.first;
    }
    if (depth > capture.maxDepth) return std::nullopt;
    const auto ordinal = capture.captured++;
    const auto &gc = state(id);
    const auto &from = state(parent->second.first);
    nlohmann::json row = {{"seed", capture.runSeed}, {"decision", capture.decisionIndex},
        {"searchSeed", capture.searchSeed}, {"ordinal", ordinal}, {"leaf", id},
        {"parent", parent->second.first}, {"action", parent->second.second}, {"depth", depth},
        {"parentScreen", int(from.screenState)}, {"parentFloor", from.floorNum},
        {"actionKey", candidate(parent->second.first, parent->second.second).key},
        {"screen", int(gc.screenState)}, {"act", gc.act}, {"floor", gc.floorNum},
        {"hp", gc.curHp}, {"maxHp", gc.maxHp}, {"gold", gc.gold},
        {"outcome", int(gc.outcome)}, {"boundary", isLeafBoundary(id)}};
    const auto policyBefore = captureOocPolicyThreadState();
    const unsigned seconds = 20 + 4 * (capture.repeats + 2 * capture.longRepeats);
    try { row["extra"] = forkLeafReplay([&] {
        nlohmann::json out = nlohmann::json::object();
        const auto anchorStart = std::clock();
        try { out["x2b"] = anchorValue(gc, pathHistory(id)); }
        catch (const std::exception &e) { out["x2bError"] = e.what(); }
        out["anchorCpuSeconds"] = double(std::clock() - anchorStart) / CLOCKS_PER_SEC;
        try {
            nlohmann::json publicRecord;
            std::string reason;
            if (gc.outcome == sts::GameOutcome::UNDECIDED && one_combat::heart1::buildPublicLeafRecord(gc, publicRecord, &reason)) {
                out["record"] = std::move(publicRecord);
                out["recordSchema"] = "heart1-public-record-v2";
                out["recordPublicParityQualified"] = false;
            } else out["recordError"] = reason.empty() ? "terminal_or_battle" : reason;
        } catch (const std::exception &e) { out["recordError"] = e.what(); }
        if (capture.annotate) {
            try { out["annotation"] = capture.annotate(gc); }
            catch (const std::exception &e) { out["annotationError"] = e.what(); }
        }
        const auto evaluations = [&](const char *name, unsigned count, std::uint64_t kind) {
            auto &list = out[name] = nlohmann::json::array();
            for (unsigned r = 0; r < count; ++r) {
                restoreOocPolicyThreadState(policyBefore);
                std::seed_seq seq{capture.searchSeed, capture.decisionIndex, ordinal, kind, std::uint64_t(r)};
                std::mt19937_64 stream(seq);
                bool ended = false;
                sts::search::OocEndpoint end;
                try {
                    const double value = evaluateLeafUnobserved(id, stream, ended, end);
                    list.push_back({{"value", value}, {"terminal", ended}, {"endFloor", end.floor}});
                } catch (const std::exception &e) { list.push_back({{"error", e.what()}}); }
            }
        };
        const auto rolloutStart = std::clock();
        const auto heart1StepsBefore = continuation_.heart1LeafSteps;
        const auto heart1FallbacksBefore = continuation_.heart1LeafFallbacks;
        evaluations("repeats", capture.repeats, 1);
        out["rolloutCpuSeconds"] = double(std::clock() - rolloutStart) / CLOCKS_PER_SEC;
        out["rolloutPolicy"] = options.heart1LeafPolicy ? "heart1" :
            options.uniformLeafPolicy ? "uniform" : options.priorLeafPolicy ? "prior" : "v4";
        out["heart1RolloutSteps"] = continuation_.heart1LeafSteps - heart1StepsBefore;
        out["heart1RolloutFallbacks"] = continuation_.heart1LeafFallbacks - heart1FallbacksBefore;
        if (capture.longRepeats) {
            options.leafCombats = 5;  // child process only
            evaluations("long5", capture.longRepeats, 2);
        }
        return out;
    }, int(seconds) * 1000, int(seconds), std::size_t(1) << 24); }
    catch (const std::exception &e) { row["extraError"] = e.what(); }
    return row;
}
#endif
double OocGameContextModel::evaluateLeafObserved(sts::search::OocStateId id,
        std::mt19937_64 &rng, bool &terminal, sts::search::OocEndpoint &endpoint) {
    if (!options.leafObserver)
        return evaluateLeafUnobserved(id, rng, terminal, endpoint);
    const auto ordinal = ++leafCalls_;
    if (leafObservationCount_ >= options.leafCaptureLimit
            || (ordinal - 1) % options.leafCaptureStride != 0)
        return evaluateLeafUnobserved(id, rng, terminal, endpoint);
    ++leafObservationCount_;
#ifndef STS_LIVE_ADVISOR
    if (leafReplayMode && leafReplayMode->rootActive && ordinal == leafReplayOrdinal)
        replaySelectedLeaf(id, rng);
#endif
    const auto rngBefore = rng;
    const auto combatsBefore = combatSamples_;
    const auto stepsBefore = continuation_.projectionSteps;
    const auto observe = [&](std::optional<double> value, const std::string &error) {
        try {
            options.leafObserver({state(id), pathHistory(id), id, ordinal, rngBefore, rng,
                value, terminal, endpoint, combatSamples_ - combatsBefore,
                continuation_.projectionSteps - stepsBefore, error});
        } catch (const std::exception &failure) {
            if (observationError_.empty()) observationError_ = *failure.what()
                ? failure.what() : "OOC leaf observer failure";
        } catch (...) {
            if (observationError_.empty()) observationError_ = "unknown OOC leaf observer failure";
        }
    };
    double value;
    try {
#ifndef STS_LIVE_ADVISOR
        if (selectedStabilityLeaf(ordinal))
            value = stabilitySelectedLeaf(id, ordinal, rng, terminal, endpoint);
        else
#endif
        value = evaluateLeafUnobserved(id, rng, terminal, endpoint);
    } catch (const sts::search::OocSearchUnsupported &failure) {
        observe(std::nullopt, failure.what());
        throw;
    }
    observe(value, {});
    return value;
}

#ifndef STS_LIVE_ADVISOR
double OocGameContextModel::stabilitySelectedLeaf(sts::search::OocStateId id,
        std::uint64_t ordinal, std::mt19937_64 &rng, bool &terminal,
        sts::search::OocEndpoint &endpoint) {
    auto &mode = *leafStabilityMode;
    const auto &selected = *selectedStabilityLeaf(ordinal);
    for (const auto &prior : mode.leaves)
        if (prior.at("decisionIndex") == mode.decisionIndex && prior.at("ordinal") == ordinal)
            failStability("duplicate_scheduled_leaf");
    mode.leaves.push_back({{"decisionIndex", mode.decisionIndex}, {"ordinal", ordinal},
        {"stateId", id}, {"initialScreen", int(state(id).screenState)},
        {"initialTerminal", terminalValue(id).has_value()}, {"rootValidated", false},
        {"repetitions", ReplayJson::array()}, {"control", nullptr}, {"parent", nullptr}});
    auto &report = mode.leaves.back();
    try {
        if (state(id).screenState != sts::ScreenState::MAP_SCREEN || terminalValue(id))
            failStability("scheduled_leaf_is_not_nonterminal_map");
        if (id != selected.expectedStateId) failStability("scheduled_leaf_state_id_mismatch");
        report["input"] = oocLeafCandidateInput(state(id), pathHistory(id));
        if (report.at("input") != selected.expectedInput) failStability("scheduled_leaf_input_mismatch");
        const auto rngBefore = rng;
        const auto policyBefore = captureOocPolicyThreadState();
        const auto sourceBefore = replayStateString(state(id));
        const auto pathBefore = replayPathString(pathHistory(id));
        report["plannerRngBefore"] = replayRngString(rngBefore);
        report["stateFingerprint"] = replayFingerprint(sourceBefore);
        report["pathFingerprint"] = replayFingerprint(pathBefore);
        report["fingerprintAlgorithm"] = "fnv1a64-report-only; source checks compare full structured strings";
        report["keysEnabled"] = state(id).keysEnabled;
        report["restRoomResolved"] = state(id).restRoomResolved;
        report["callbackCustody"] = "fresh fork from same parent before every evaluation; not serialized";
        const auto evaluate = [&](std::mt19937_64 &stream, bool &ended, sts::search::OocEndpoint &end) {
            const auto combatsBefore = combatSamples_;
            const auto stepsBefore = continuation_.projectionSteps;
            std::optional<double> value;
            std::string error;
            try { value = evaluateLeafUnobserved(id, stream, ended, end); }
            catch (const std::exception &e) { error = e.what(); }
            catch (...) { error = "nonstandard_leaf_failure"; }
            return replayEvaluation(value, error, ended, end,
                combatSamples_ - combatsBefore, continuation_.projectionSteps - stepsBefore,
                stream, replayStateString(state(id)) == sourceBefore
                    && replayPathString(pathHistory(id)) == pathBefore);
        };
        const auto child = [&](std::mt19937_64 initial, const char *phase,
                std::optional<std::uint64_t> repeat, std::optional<std::uint64_t> seed) {
            // Reserve one complete existing 10-second child allowance. All
            // controls and repetitions share this single 30-second budget.
            const auto used = waitedChildCpuSeconds() - mode.childCpuStart;
            if (used > 20) failStability("cumulative_child_cpu_budget_exhausted");
            ReplayJson row = {{"decisionIndex", mode.decisionIndex}, {"ordinal", ordinal},
                {"stateId", id}, {"phase", phase},
                {"repeatIndex", repeat ? ReplayJson(*repeat) : ReplayJson(nullptr)},
                {"seed", seed ? ReplayJson(*seed) : ReplayJson(nullptr)},
                {"initialRng", replayRngString(initial)}};
            row["evaluation"] = forkLeafReplay([&] {
                restoreOocPolicyThreadState(policyBefore);
                bool ended = false;
                sts::search::OocEndpoint end;
                return evaluate(initial, ended, end);
            });
            row["cumulativeChildCpuSeconds"] = waitedChildCpuSeconds() - mode.childCpuStart;
            if (repeat) report["repetitions"].push_back(row);
            else report["control"] = row;
            if (mode.progress) mode.progress(row);
            if (row.at("cumulativeChildCpuSeconds").get<double>() > 30)
                failStability("cumulative_child_cpu_budget_exceeded");
            const auto checked = compareReplay(row.at("evaluation"), row.at("evaluation"));
            if (checked.at("status") != "PASS")
                failStability("child_" + checked.at("reason").get<std::string>());
        };
        child(rngBefore, "control", std::nullopt, std::nullopt);
        for (std::size_t repeat = 0; repeat < selected.repeatSeeds.size(); ++repeat)
            child(std::mt19937_64(selected.repeatSeeds[repeat]), "repetition", repeat,
                selected.repeatSeeds[repeat]);
        // No child ever mutates this process: keep the scheduled evaluation,
        // stream, backup, policy mutations and observation exactly as before.
        report["parent"] = evaluate(rng, terminal, endpoint);
        const auto compared = compareReplay(report.at("parent"), report.at("control").at("evaluation"));
        report["controlComparison"] = {{"status", compared.at("status")},
            {"reason", compared.at("reason")}, {"differentFields", compared.at("differentFields")}};
        if (compared.at("status") != "PASS")
            failStability("same_rng_control_" + compared.at("reason").get<std::string>());
        return report.at("parent").at("value").get<double>();
    } catch (const std::exception &error) { failStability(error.what()); }
}
[[noreturn]] void OocGameContextModel::replaySelectedLeaf(sts::search::OocStateId id,
        std::mt19937_64 &rng) {
    auto report = replayReport("INVALID", "replay_not_completed");
    report["stateId"] = id;
    report["initialScreen"] = int(state(id).screenState);
    report["initialTerminal"] = terminalValue(id).has_value();
    if (state(id).screenState != sts::ScreenState::MAP_SCREEN || terminalValue(id)) {
        report["status"] = "NOT_REACHED";
        report["reason"] = "scheduled_leaf_is_not_nonterminal_map";
        throw LeafReplayComplete{std::move(report)};
    }
    try {
        const auto rngBefore = rng;
        const auto policyBefore = captureOocPolicyThreadState();
        const auto sourceBefore = replayStateString(state(id));
        const auto pathBefore = replayPathString(pathHistory(id));
        report["plannerRngBefore"] = replayRngString(rngBefore);
        report["fingerprintAlgorithm"] = "fnv1a64-report-only; source checks compare full structured strings";
        report["stateFingerprint"] = replayFingerprint(sourceBefore);
        report["pathFingerprint"] = replayFingerprint(pathBefore);
        report["keysEnabled"] = state(id).keysEnabled;
        report["restRoomResolved"] = state(id).restRoomResolved;
        report["callbackCustody"] = "fork-inherited callable and captures; not serialized";
        const auto evaluate = [&](std::mt19937_64 &stream) {
            const auto combatsBefore = combatSamples_;
            const auto stepsBefore = continuation_.projectionSteps;
            bool terminal = false;
            sts::search::OocEndpoint endpoint;
            std::optional<double> value;
            std::string error;
            try { value = evaluateLeafUnobserved(id, stream, terminal, endpoint); }
            catch (const std::exception &e) { error = e.what(); }
            catch (...) { error = "nonstandard_leaf_failure"; }
            return replayEvaluation(value, error, terminal, endpoint,
                combatSamples_ - combatsBefore, continuation_.projectionSteps - stepsBefore,
                stream, replayStateString(state(id)) == sourceBefore
                    && replayPathString(pathHistory(id)) == pathBefore);
        };
        // Fork happens at the exact pre-evaluation boundary. Policy, callbacks,
        // model id/root context and caches are copied by process isolation.
        const auto child = forkLeafReplay([&] {
            restoreOocPolicyThreadState(policyBefore);
            auto replayRng = rngBefore;
            return evaluate(replayRng);
        });
        // Child was reaped before this ordinary scheduled teacher evaluation.
        const auto parent = evaluate(rng);
        const auto compared = compareReplay(parent, child);
        report.update(compared);
        report["stateId"] = id;
    } catch (const std::exception &error) {
        report["status"] = "INVALID";
        report["reason"] = error.what();
    }
    throw LeafReplayComplete{std::move(report)};
}
#endif

double OocGameContextModel::evaluateLeafUnobserved(sts::search::OocStateId id,
        std::mt19937_64 &rng, bool &terminal, sts::search::OocEndpoint &endpoint) {
    terminal = terminalValue(id).has_value();
    endpoint = endpointOf(state(id));
    OocProfileScope profile(OocProfileBucket::EvaluateLeaf);
    struct RolloutLog {
        OocDecisionLog *log = t_decisionLog;
        ~RolloutLog() { if (log) { log->inRollout = false; log->rollout = nullptr; } }
    } rolloutLog;
    if (t_decisionLog) {
        const auto &leaf = state(id);
        std::string start = terminal ? (leaf.outcome == sts::GameOutcome::PLAYER_LOSS ? "terminal: death" : "terminal: victory")
            : logScreen(leaf);
        if (!terminal && metadata(id).boundary) {
            std::string reason = "no candidates";
            if (leaf.screenState == sts::ScreenState::MAP_SCREEN) reason = v4DecisionSupported(leaf)
                ? "map candidates not unique" : "map step without a V4 decision (boss node)";
            else {
                const auto enumeration = sts::search::enumerateOocSemanticPrimitiveBindings(leaf);
                if (!enumeration.error.empty()) reason = enumeration.error;
            }
            start += " | not searchable: " + reason;
        }
        t_decisionLog->add("leaf_start", start);
        t_decisionLog->inRollout = true;
        if (!terminal && t_decisionLog->sampleRollouts.size() < t_decisionLog->sampleLimit) {
            t_decisionLog->sampleRollouts.push_back({{"leafStateId", id}, {"start", start},
                {"floor", leaf.floorNum}, {"hp", leaf.curHp}, {"maxHp", leaf.maxHp}, {"gold", leaf.gold},
                {"steps", nlohmann::json::array()}});
            t_decisionLog->rollout = &t_decisionLog->sampleRollouts.back();
        }
    }
#ifndef STS_LIVE_ADVISOR
    if (options.rolloutStudent && !terminal) {
        // Same record and anchor as the §494 sibling capture that trained the student.
        const auto &leaf = state(id);
        std::optional<double> value;
        try {
            nlohmann::json record;
            if (leaf.outcome == sts::GameOutcome::UNDECIDED && one_combat::heart1::buildPublicLeafRecord(leaf, record)) {
                OocProfileScope inference(OocProfileBucket::LeafValue);
                value = options.rolloutStudent->predict(record, anchorValue(leaf, pathHistory(id)));
            }
        } catch (const std::exception &) {}
        if (value) { ++continuation_.studentLeafEvaluations; return *value; }
        ++continuation_.studentLeafFallbacks;
    }
#endif
    if (id != 0 && state(id).screenState == sts::ScreenState::MAP_SCREEN
            && options.stopAtMapCheckpoint)
        return leafValue(id);
    if (!options.checkpointLeaves && !options.sampleNoncombat) return leafValue(id);
    auto child = Snapshot{detachedCopy(state(id)), states.at(id).path, {}};
    struct EndpointOnExit {
        const GameContext &gc; sts::search::OocEndpoint &out;
        ~EndpointOnExit() { out = endpointOf(gc); }
    } endpointOnExit{child.gc, endpoint};
    if (options.sampleNoncombat) {
        sampleNoncombatFuture(child.gc, rng);
        if (id == 0 && dependencies.sampleHiddenCounters)
            dependencies.sampleHiddenCounters(child.gc, rng);
    }
    if (!options.checkpointLeaves) {
        if (child.gc.outcome == sts::GameOutcome::PLAYER_LOSS) { terminal = true; return 0; }
        if (child.gc.outcome == sts::GameOutcome::PLAYER_VICTORY) {
            terminal = true;
            return sts::search::runGoalVictory(child.gc, options.collectKeys, dependencies.stopAfterAct()) ? 1 : 0;
        }
        return options.bossLeaf ? bossLeafValue(child.gc)
            : anchorValue(child.gc, child.path);
    }
#ifndef STS_LIVE_ADVISOR
    ImaginedScope scope;
    t_curPath=&child.path;
#endif
    if (child.gc.screenState == sts::ScreenState::BATTLE) ++continuation_.battleLeaves;
    else if (child.gc.screenState == sts::ScreenState::MAP_SCREEN) ++continuation_.mapLeaves;
    else ++continuation_.pendingLeaves;
    // A boss rollout spans up to a whole act of decisions. Its target is the
    // next boss after the searched decision, so a leaf the tree already played
    // past that boss scores 1 instead of rolling on to a later boss.
    const int maxSteps = options.bossRollout ? 8192 : options.leafCombats ? 1024 : 256;
    const int targetBosses = bossesCleared(state(0)) + 1;
    unsigned additionalCombats = 0;
    const auto checkpoint = [&]() -> std::optional<double> {
        child.path.update(child.gc);
        if (child.gc.outcome == sts::GameOutcome::PLAYER_LOSS) { terminal = true; return 0; }
        if (child.gc.outcome == sts::GameOutcome::PLAYER_VICTORY) {
            terminal = true;
            return sts::search::runGoalVictory(child.gc, options.collectKeys, dependencies.stopAfterAct()) ? 1 : 0;
        }
        if (options.bossRollout)
            return bossesCleared(child.gc) >= targetBosses ? std::optional<double>(1.0) : std::nullopt;
        if (options.screenLeaf && child.gc.screenState != sts::ScreenState::BATTLE
                && child.gc.screenState != sts::ScreenState::MAP_SCREEN)
            if (const auto value = screenLeafValue(child.gc, child.path)) return value;
        // Direct probe: value the first non-combat state without a playout.
        if (((options.directLeaf || options.screenLeaf) && child.gc.screenState != sts::ScreenState::BATTLE)
                || (child.gc.screenState == sts::ScreenState::MAP_SCREEN
                && (additionalCombats >= options.leafCombats || options.stopAtMapCheckpoint))) {
            if (options.constantLeaf) return 0.5;
            if (options.bossLeaf) return bossLeafValue(child.gc);
            OocProfileScope inference(OocProfileBucket::LeafValue);
            return anchorValue(child.gc, child.path);
        }
        return std::nullopt;
    };
    const int startFloor = child.gc.floorNum;
    const auto loggedCheckpoint = [&]() -> std::optional<double> {
        const auto value = checkpoint();
        if (value && t_decisionLog) {
            std::string end = child.gc.outcome == sts::GameOutcome::PLAYER_LOSS ? "death"
                : child.gc.outcome == sts::GameOutcome::PLAYER_VICTORY ? "victory"
                : "value model at " + logScreen(child.gc);
            t_decisionLog->add("rollout_end", end + " | after " + std::to_string(additionalCombats) + " rollout combats");
            t_decisionLog->add("rollout_floors_advanced", std::to_string(child.gc.floorNum - startFloor));
            if (t_decisionLog->rollout) {
                (*t_decisionLog->rollout)["end"] = end;
                (*t_decisionLog->rollout)["value"] = *value;
                (*t_decisionLog->rollout)["endFloor"] = child.gc.floorNum;
            }
        }
        return value;
    };
    return boundedContinuation(maxSteps,loggedCheckpoint,[&] {
        ++continuation_.projectionSteps;
        if (child.gc.screenState == sts::ScreenState::BATTLE) {
            try { resolveCombat(child,rng); }
            catch (const sts::search::OocSearchUnsupported &) {
                // The CTM stack cannot price an active Lizard Tail at some boundaries
                // (Fairy Potion, Entropic Brew); whole-act boss rollouts reach them
                // in nearly every search. Play this rollout on with the tail spent.
                constexpr auto tail = sts::RelicId::LIZARD_TAIL;
                if (!options.bossRollout || !child.gc.relics.has(tail)
                        || child.gc.relics.getRelicValue(tail) != 1) throw;
                child.gc.relics.getRelicValueRef(tail) = 0;
                ++continuation_.supportReasons["bossrollout_lizard_spent"];
                resolveCombat(child,rng);
            }
            ++additionalCombats;
        }
        else {
            if (options.sampleNoncombat) sampleNoncombatFuture(child.gc, rng);
            bool applied = false;
            if (options.priorLeafPolicy || options.heart1LeafPolicy) {
                const std::string screen = t_decisionLog ? logScreen(child.gc) : std::string{};
#ifndef STS_LIVE_ADVISOR
                if (options.treeRules && oocTreeRuleStep(child.gc)) applied = true;
                else
#endif
                if (v4DecisionSupported(child.gc)
                        || (options.heart1LeafPolicy && options.heart1Coverage
                            && (heart1FullScreen(child.gc) || options.heart1LeafSelects))) {
                    const auto actions = v4CandidateActions(child.gc);
                    std::set<std::uint32_t> ids;
                    bool unique = !actions.empty();
                    for (auto action : actions) if (!ids.insert(action.bits).second) unique = false;
                    if (unique) {
                        std::optional<std::vector<double>> logits;
                        if (options.heart1LeafPolicy) {
                            logits = dependencies.heart1PolicyLogits(child.gc, actions, &continuation_.heart1LeafReasons);
                            if (!logits) ++continuation_.heart1LeafFallbacks;
                        } else logits = dependencies.policyLogits(child.gc, child.path, actions);
                        if (logits) {
                            if (logits->size() != actions.size())
                                throw std::runtime_error("OOC MCTS rollout policy-logit count mismatch");
                            if (!std::all_of(logits->begin(), logits->end(), [](double x) { return std::isfinite(x); }))
                                throw std::runtime_error("OOC MCTS nonfinite rollout policy logit");
                            const auto best = std::max_element(logits->begin(), logits->end()) - logits->begin();
                            actions[best].execute(child.gc); applied = true;
                            if (options.heart1LeafPolicy) ++continuation_.heart1LeafSteps;
                            else ++continuation_.priorLeafSteps;
                        }
                    }
                }
                if (applied && t_decisionLog) t_decisionLog->add("rollout_step", screen
                    + (options.heart1LeafPolicy ? " | heart1 leaf policy/rule" : " | prior leaf policy"));
            }
            if (!applied && options.uniformLeafPolicy && v4DecisionSupported(child.gc)) {
                const auto actions = v4CandidateActions(child.gc);
                std::set<std::uint32_t> ids;
                bool unique = !actions.empty();
                for (auto action : actions) if (!ids.insert(action.bits).second) unique = false;
                if (unique) {
                    const auto selected = std::uniform_int_distribution<std::size_t>(0, actions.size()-1)(rng);
                    actions[selected].execute(child.gc); applied = true;
                }
            }
            if (!applied) {
                if (!dependencies.continuationStep)
                    throw sts::search::OocSearchUnsupported("missing_continuation_step");
                // Resampled queues are public samples; skip the fallback's
                // encounter mixture there (ADR-0028).
                std::optional<NativeOocResampledQueueScope> resampled;
                if (options.sampleNoncombat) resampled.emplace();
                std::optional<NativeOocGreedyShopScope> greedyShop;
                if (options.greedyRolloutShop) greedyShop.emplace();
                std::optional<LogSnapshot> before;
                std::string screen;
                if (t_decisionLog) { before.emplace(child.gc); screen = logScreen(child.gc); }
                if (options.heart1LeafPolicy)
                    ++continuation_.heart1LeafReasons["chain:screen" + std::to_string(static_cast<int>(child.gc.screenState))];
                dependencies.continuationStep(child.gc, child.path, rng);
                if (t_decisionLog) {
                    const auto [detail, kinds] = logDiff(*before, LogSnapshot(child.gc));
#ifndef STS_LIVE_ADVISOR
                    const std::string handler = lastOocChainHandler();
#else
                    const std::string handler = "advisor";
#endif
                    t_decisionLog->add("rollout_step", screen + " | " + handler + " | " + kinds);
                    if (t_decisionLog->rollout)
                        t_decisionLog->rollout->at("steps").push_back({{"floor", before->floor},
                            {"screen", screen}, {"by", handler}, {"result", detail}});
                }
            } else if (t_decisionLog && options.uniformLeafPolicy) {
                t_decisionLog->add("rollout_step", logScreen(child.gc) + " | uniform leaf policy");
            }
        }
    });
}

}

namespace one_combat {
sts::search::OocMctsResult searchWithSoleRootShortcut(sts::search::OocGenerativeModel &model,
    const sts::search::OocMctsConfig &config, std::optional<sts::search::OocActionId> soleAction,
    std::uint64_t simulations) {
    if (!config.observeRootLock && config.rootCheckpointSimulations.empty()
        && config.maxDepth && soleAction) {
        sts::search::OocMctsResult result;
        result.selectedAction = soleAction;
        result.rootActions.push_back({*soleAction, 1.0, 0, 0.0});
        result.metrics.trivialRootBypasses = 1;
        return result;
    }
    return sts::search::OocMctsPlanner(config).search(model, 0, simulations);
}
}

#ifndef STS_LIVE_ADVISOR
namespace one_combat {

namespace {
bool liveEnabled = false;
std::uint64_t liveSimulations = 512;
sts::search::OocMctsConfig liveConfig;
OocAdapterOptions liveOptions{true};
std::shared_ptr<const CombatTransitionSampler> liveSampler;
// STS_OOC_MCTS_A20_CTM (§470; on by default with the automatic stack, ADR-0033): the bundled A20 stack, used for
// ascension-20 decisions.
std::shared_ptr<const CombatTransitionSampler> liveSamplerA20;
// STS_OOC_MCTS_UNSUPPORTED_SILVER_SIMS: liveSampler / liveSamplerA20 wrapped by the Silver fallback.
std::shared_ptr<const CombatTransitionSampler> liveFallbackSampler, liveFallbackSamplerA20;
std::shared_ptr<const CombatTransitionSampler> liveSamplerFor(const GameContext &gc) {
    if (!liveSamplerA20 || gc.ascension < 20) return liveFallbackSampler ? liveFallbackSampler : liveSampler;
    static std::atomic<bool> announced{false};
    if (!announced.exchange(true)) std::cout << "[ctm-a20] ascension-20 decisions use pathb-a20\n";
    return liveFallbackSamplerA20 ? liveFallbackSamplerA20 : liveSamplerA20;
}
std::unique_ptr<OocLeafCaptureSink> liveLeafCapture;
// STS_OOC_SIBLING_CAPTURE (research, default off): OocSiblingLeafCapture rows
// for every STS_OOC_SIBLING_EVERY-th searched decision.
struct LiveSiblingCapture {
    std::shared_ptr<std::ofstream> out;
    std::uint64_t every = 4, maxLeaves = 256;
    unsigned repeats = 1, longRepeats = 0, maxDepth = 2;
};
std::optional<LiveSiblingCapture> liveSibling;
std::string pendingLeafCapturePath;
nlohmann::json pendingLeafCaptureProvenance;
std::string liveTrace, liveRootLockTrace, liveCheckpointTrace, liveRootTrace;
// Plays one imagined combat with native Silver at a flat budget, root prior on
// or off. The hidden combat future is redrawn from the planner RNG: gc.seed,
// from which BattleContext::init re-derives four streams (seed + floor), and
// the six carried streams (counters kept), as redrawNativeFuture does for the
// selective audit. Live OOC MCTS already redraws gc.seed in
// sampleNoncombatFuture before every combat (sampleNoncombat is always on), so
// the seed redraw here is a safeguard for callers without it; it does change
// the resolver's RNG draws, so reproducing §411 needs its binary. The Silver
// planner seed comes from the same RNG. A Silver stall or failure returns
// UNSUPPORTED.
CombatRuntimeSample playImaginedCombatWithSilver(const GameContext &source, std::mt19937_64 &rng,
                                                 int simulations, bool rootPrior) {
    GameContext gc = detachedCopy(source);
    gc.seed = rng();
    for (auto stream : {&gc.aiRng, &gc.cardRandomRng, &gc.miscRng, &gc.monsterHpRng,
                        &gc.potionRng, &gc.shuffleRng}) {
        const auto counter = stream->counter;
        *stream = sts::Random(rng());
        stream->counter = counter;
    }
    const std::uint64_t plannerSeed = rng(), agentSeed = rng();
    namespace S = sts::search;
    struct Scope {
        bool disallow = S::g_disallowImaginedCombat;
        std::optional<std::uint64_t> planner = S::g_nativeSilverPlannerSeedOverride;
        std::optional<bool> prior = S::g_nativeSilverRootPriorOverride;
        std::optional<S::NativeSilverBudgetOverride> budget = S::g_nativeSilverBudgetOverride;
        std::function<void(const sts::BattleContext &, GameContext &)> raw = std::move(sts::g_onBattleExitRaw);
        std::function<void(const sts::BattleContext &)> decision = std::move(S::g_onCombatDecision);
        ~Scope() {
            S::g_disallowImaginedCombat = disallow; S::g_nativeSilverPlannerSeedOverride = planner;
            S::g_nativeSilverRootPriorOverride = prior; S::g_nativeSilverBudgetOverride = budget;
            sts::g_onBattleExitRaw = std::move(raw); S::g_onCombatDecision = std::move(decision);
        }
    } scope;
    S::g_disallowImaginedCombat = false;
    S::g_nativeSilverPlannerSeedOverride = plannerSeed;
    S::g_nativeSilverRootPriorOverride = rootPrior;
    S::g_nativeSilverBudgetOverride = S::NativeSilverBudgetOverride{};
    std::optional<CombatTransitionPersistentState> rawPost;
    sts::g_onBattleExitRaw = [&](const sts::BattleContext &, GameContext &g) {
        if (!rawPost) rawPost = captureCombatTransitionState(g);
    };
    S::ScumSearchAgent2 agent;
    agent.simulationCountBase = simulations;
    agent.rng.seed(static_cast<unsigned>(agentSeed));
    sts::BattleContext bc;
    try {
        agent.playoutBattle(gc, bc);
    } catch (const S::OocSearchUnsupported &) {
        throw;
    } catch (const std::exception &) {
        return {};
    }
    if (bc.outcome == sts::Outcome::PLAYER_LOSS) return {CombatRuntimeSample::Outcome::DEATH, {}};
    if (bc.outcome != sts::Outcome::PLAYER_VICTORY) return {};
    bc.exitBattle(gc);
    if (!rawPost) return {};
    return {rawPost->smokeBombUsed ? CombatRuntimeSample::Outcome::ESCAPE
                                   : CombatRuntimeSample::Outcome::VICTORY, *rawPost};
}
// Research only (STS_OOC_MCTS_COMBAT_RESOLVER=silver): resolves each imagined
// combat with playImaginedCombatWithSilver, root prior on. Every combat is
// supported; a Silver failure aborts that search as a CTM support miss does.
class SilverCombatTransitionSampler final : public CombatTransitionSampler {
    int simulations_;
public:
    explicit SilverCombatTransitionSampler(int simulations) : simulations_(simulations) {}
    CombatRuntimeSupport support(const GameContext &, const CombatPredictorInputV1 &) const override {
        return {true, {}};
    }
    bool modelsSmokeBombEscape() const override { return true; }
    CombatRuntimeSample sample(const GameContext &source, const CombatPredictorInputV1 &,
                               std::mt19937_64 &rng) const override {
        return playImaginedCombatWithSilver(source, rng, simulations_, true);
    }
};
// Opt-in (STS_OOC_MCTS_UNSUPPORTED_SILVER_SIMS=N): keeps the CTM for every
// combat it supports and plays only the combats it refuses with plain Silver at
// N simulations, instead of aborting the whole search to the V4 fallback.
// Opt-in (STS_OOC_MCTS_ACT4_SILVER_SIMS=M): also plays Shield and Spear and the
// Heart with plain Silver at M simulations, because no CTM was trained on them.
// Either count may be 0 (that route off). Counts per reason are reported per run
// as [ooc-silver-fallback]; Act-4 combats count as "act4_silver".
class SilverFallbackCombatTransitionSampler final : public CombatTransitionSampler {
    std::shared_ptr<const CombatTransitionSampler> inner_;
    int simulations_;
    int act4Simulations_;
    bool act4(const CombatPredictorInputV1 &input) const {
        return act4Simulations_ > 0
            && (input.globals.encounter == static_cast<int>(sts::MonsterEncounter::SHIELD_AND_SPEAR)
                || input.globals.encounter == static_cast<int>(sts::MonsterEncounter::THE_HEART));
    }
    mutable std::mutex mutex_;
    mutable std::map<std::string, std::uint64_t> reasons_;
    void count(const std::string &reason) const {
        std::lock_guard<std::mutex> lock(mutex_);
        ++reasons_[reason.empty() ? "unspecified" : reason];
    }
public:
    SilverFallbackCombatTransitionSampler(std::shared_ptr<const CombatTransitionSampler> inner, int simulations,
                                          int act4Simulations = 0)
        : inner_(std::move(inner)), simulations_(simulations), act4Simulations_(act4Simulations) {}
    std::map<std::string, std::uint64_t> takeReasons() const {
        std::lock_guard<std::mutex> lock(mutex_);
        return std::exchange(reasons_, {});
    }
    std::unique_ptr<PreparedCombatTransition> prepare(const GameContext &gc,
            const CombatPredictorInputV1 &input) const override {
        const bool act4Route = act4(input);
        std::unique_ptr<PreparedCombatTransition> prepared;
        if (!act4Route) {
            prepared = inner_->prepare(gc, input);
            if (prepared->support().supported || simulations_ == 0) return prepared;
        }
        count(act4Route ? "act4_silver" : prepared->support().reason);
        class SilverPrepared final : public PreparedCombatTransition {
            GameContext gc_;
            int simulations_;
            CombatRuntimeSupport support_{true, {}};
        public:
            SilverPrepared(const GameContext &gc, int simulations) : gc_(detachedCopy(gc)), simulations_(simulations) {}
            const CombatRuntimeSupport &support() const override { return support_; }
            CombatRuntimeSample sample(std::mt19937_64 &rng) const override {
                return playImaginedCombatWithSilver(gc_, rng, simulations_, false);
            }
        };
        return std::make_unique<SilverPrepared>(gc, act4Route ? act4Simulations_ : simulations_);
    }
    CombatRuntimeSupport support(const GameContext &gc, const CombatPredictorInputV1 &input) const override {
        if (simulations_ > 0 || act4(input)) return {true, {}};
        return inner_->support(gc, input);
    }
    CombatRuntimeSupport forecastSupport(const CombatPredictorInputV1 &input) const override {
        return inner_->forecastSupport(input);
    }
    CombatTransitionExpectation forecastExpectation(const CombatPredictorInputV1 &input) const override {
        return inner_->forecastExpectation(input);
    }
    CombatTransitionExpectation expectation(const GameContext &gc, const CombatPredictorInputV1 &input) const override {
        return inner_->expectation(gc, input);
    }
    bool modelsSmokeBombEscape() const override { return inner_->modelsSmokeBombEscape(); }
    CombatRuntimeSample sample(const GameContext &gc, const CombatPredictorInputV1 &input,
                               std::mt19937_64 &rng) const override {
        if (act4(input)) {
            count("act4_silver");
            return playImaginedCombatWithSilver(gc, rng, act4Simulations_, false);
        }
        const auto support = inner_->support(gc, input);
        if (support.supported) return inner_->sample(gc, input, rng);
        if (simulations_ == 0) return {};
        count(support.reason);
        return playImaginedCombatWithSilver(gc, rng, simulations_, false);
    }
};
int liveSilverResolverSims = 0;
int liveUnsupportedSilverSims = 0;
int liveAct4SilverSims = 0;

std::uint64_t splitMix64(std::uint64_t x) {
    x += 0x9e3779b97f4a7c15ULL;
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
    x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
    return x ^ (x >> 31);
}
// Parsing is strict: no whitespace, trailing text, nonfinite or out-of-range knobs.
void applyLiveControl(const std::string &key, const std::string &value,
                      sts::search::OocMctsConfig &config, OocAdapterOptions &opts) {
    const auto invalid = [&] { throw std::runtime_error(key + " invalid value: " + value); };
    const auto choice = [&](const char *a, const char *b) {
        if (value == a) return false;
        if (value == b) return true;
        invalid(); return false;
    };
    const auto number = [&] {
        if (value.empty() || value.find_first_not_of("0123456789.+-eE") != std::string::npos) invalid();
        std::size_t end = 0; double x = 0;
        try { x = std::stod(value, &end); } catch (...) { invalid(); }
        if (end != value.size() || !std::isfinite(x)) invalid();
        return x;
    };
    const auto integer = [&] {
        if (value.empty() || value.find_first_not_of("0123456789") != std::string::npos) invalid();
        unsigned long long x = 0;
        try { x = std::stoull(value); } catch (...) { invalid(); }
        return x;
    };
    if (key == "STS_OOC_MCTS_PRIOR") {
        if (value != "policy" && value != "uniform" && value != "heart1" && value != "heart1full") invalid();
        opts.uniformPrior = value == "uniform";
        opts.heart1Prior = value == "heart1" || value == "heart1full";
        opts.heart1Coverage = value == "heart1full";
    }
    else if (key == "STS_OOC_MCTS_LEAF_VALUE") {
        opts.constantLeaf = opts.bossLeaf = opts.bossRollout = opts.directLeaf = opts.screenLeaf = opts.screenGbm = false;
        if (value == "native") {}
        else if (value == "bossrollout") opts.bossRollout = true;
        else if (value == "constant") opts.constantLeaf = true;
        else if (value == "boss") opts.bossLeaf = true;
        else if (value == "direct") opts.directLeaf = true;
        else if (value == "screen") opts.screenLeaf = true;
        else if (value == "screengbm") opts.screenLeaf = opts.screenGbm = true;
        else invalid();
    }
    else if (key == "STS_OOC_MCTS_LEAF_POLICY") {
        if (value != "v4" && value != "uniform" && value != "prior" && value != "heart1") invalid();
        opts.uniformLeafPolicy = value == "uniform"; opts.priorLeafPolicy = value == "prior";
        opts.heart1LeafPolicy = value == "heart1";
    }
    else if (key == "STS_OOC_MCTS_TARGET_PRIOR") opts.targetPrior = choice("0", "1");
    else if (key == "STS_OOC_MCTS_POTION_KEEP_PRIOR") opts.potionKeepPrior = choice("0", "1");
    else if (key == "STS_OOC_MCTS_LEAF_SELECTS") opts.heart1LeafSelects = choice("chain", "heart1");
    else if (key == "STS_OOC_MCTS_CPU_SECONDS") {
        const double x = number(); if (x < 0 || x > 10) invalid(); opts.cpuBudgetSeconds = x;
    }
    else if (key == "STS_OOC_MCTS_ROLLOUT_SHOP") opts.greedyRolloutShop = choice("planner", "greedy");
    else if (key == "STS_OOC_MCTS_TREE_RULES") opts.treeRules = choice("0", "1");
    else if (key == "STS_OOC_MCTS_EARLY_STOP") config.allowUnqualifiedRootStop = choice("0", "1");
    else if (key == "STS_OOC_MCTS_GAP_STOP_20") config.stopAt512VisitGap20 = choice("0", "1");
    else if (key == "STS_OOC_MCTS_MERGE_OUTCOMES") config.mergeEquivalentOutcomes = choice("0", "1");
    else if (key == "STS_OOC_MCTS_ROOT_SELECTION") config.selectByMeanQ = choice("visits", "q");
    else if (key == "STS_OOC_MCTS_TEMPERATURE") { const double x = number(); if (x <= 0) invalid(); opts.priorTemperature = x; }
    else if (key == "STS_OOC_MCTS_CPUCT") { const double x = number(); if (x < 0) invalid(); config.cPuct = x; }
    else if (key == "STS_OOC_MCTS_WIDEN_K") { const double x = number(); if (x <= 0) invalid(); config.wideningK = x; }
    else if (key == "STS_OOC_MCTS_WIDEN_ALPHA") { const double x = number(); if (x <= 0 || x >= 1) invalid(); config.wideningAlpha = x; }
    else if (key == "STS_OOC_MCTS_MAX_DEPTH") { const auto x = integer(); if (!x || x > 512) invalid(); config.maxDepth = x; }
    else if (key == "STS_OOC_MCTS_LEAF_COMBATS") { const auto x = integer(); if (x != 0 && x != 1 && x != 3 && x != 5) invalid(); opts.leafCombats = x; }
    else invalid();
}
const char *const liveControlKeys[] = {
    "STS_OOC_MCTS_EARLY_STOP", "STS_OOC_MCTS_GAP_STOP_20", "STS_OOC_MCTS_PRIOR", "STS_OOC_MCTS_TEMPERATURE", "STS_OOC_MCTS_CPUCT",
    "STS_OOC_MCTS_WIDEN_K", "STS_OOC_MCTS_WIDEN_ALPHA", "STS_OOC_MCTS_MAX_DEPTH",
    "STS_OOC_MCTS_ROOT_SELECTION", "STS_OOC_MCTS_LEAF_VALUE",
    "STS_OOC_MCTS_LEAF_COMBATS", "STS_OOC_MCTS_LEAF_POLICY", "STS_OOC_MCTS_MERGE_OUTCOMES",
    "STS_OOC_MCTS_ROLLOUT_SHOP", "STS_OOC_MCTS_TREE_RULES", "STS_OOC_MCTS_CPU_SECONDS",
    "STS_OOC_MCTS_TARGET_PRIOR", "STS_OOC_MCTS_LEAF_SELECTS", "STS_OOC_MCTS_POTION_KEEP_PRIOR"
};
void recordSearchAbort(const sts::search::OocMctsResult &result, OocContinuationMetrics &continuation) {
    if (!result.aborted) return;
    if (result.abortReason.rfind("continuation_step_limit_",0) == 0
            || result.abortReason.rfind("ooc_depth_safety_cap_",0) == 0) {
        ++continuation.continuationLimitAborts;
        ++continuation.continuationReasons[result.abortReason];
    } else if (result.abortReason.rfind("semantic_execution:",0) == 0) {
        ++continuation.supportReasons[result.abortReason];
    } else if (!continuation.unsupportedCombats) {
        // A continuation policy attempted a forbidden native combat before resolveCombat.
        ++continuation.imaginedCombats; ++continuation.unsupportedCombats;
        ++continuation.supportReasons[result.abortReason];
    }
}
double threadCpuSeconds() {
    timespec t{};
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &t) != 0)
        throw std::runtime_error("OOC MCTS thread CPU clock unavailable");
    return double(t.tv_sec) + double(t.tv_nsec) * 1e-9;
}
// Reroot-opportunity measurement (issue #339): observation only. Identity is
// the state as the sampled live search treats it. Hidden stream seeds, pool
// order, unrevealed encounter suffixes and hidden chest/Dead Adventurer
// contents are re-determinized at every transition, so they are excluded.
// Public identity keeps the copied native room/potion/rarity counters; the
// RNG identity additionally keeps stream draw counters, which the search's
// own encounter re-determinization advances.
std::string liveReuseTrace;
std::uint64_t reusePublicFingerprint(const GameContext &g, const PathHistory &path, bool rngCounters) {
    sts::test::ooc_state_detail::Writer w;
    w.values(g.noteForYourselfCard, g.skipBattles);
    if (rngCounters)
        for (auto stream : {&g.aiRng, &g.cardRandomRng, &g.cardRng, &g.eventRng,
                &g.mathUtilRng, &g.merchantRng, &g.miscRng, &g.monsterHpRng,
                &g.monsterRng, &g.neowRng, &g.potionRng, &g.relicRng,
                &g.shuffleRng, &g.treasureRng}) w.value(stream->counter);
    w.values(g.monsterChance, g.shopChance, g.treasureChance,
             g.potionChance, g.cardRarityFactor);
    const auto members = [&](auto pool) {
        std::sort(pool.begin(), pool.end());
        w.sequence(pool);
    };
    members(g.eventList); members(g.shrineList); members(g.specialOneTimeEventList);
    members(g.commonRelicPool); members(g.uncommonRelicPool); members(g.rareRelicPool);
    members(g.shopRelicPool); members(g.bossRelicPool); members(g.colorlessCardPool);
    w.value(g.monsterListOffset);
    for (int i = 0; i < std::min<int>(g.monsterListOffset, g.monsterList.size()); ++i) w.value(g.monsterList[i]);
    w.value(g.eliteMonsterListOffset);
    for (int i = 0; i < std::min<int>(g.eliteMonsterListOffset, g.eliteMonsterList.size()); ++i)
        w.value(g.eliteMonsterList[i]);
    if (!(g.act == 3 && g.ascension >= 20)) w.value(g.secondBoss);
    auto info = g.info;
    if (g.screenState == sts::ScreenState::TREASURE_ROOM) {
        info.haveGold = false;
        info.tier = sts::RelicTier::COMMON;
    }
    if (g.screenState == sts::ScreenState::EVENT_SCREEN && g.curEvent == sts::Event::DEAD_ADVENTURER
            && info.phase >= 0 && info.phase <= int(info.rewards.size()))
        std::sort(info.rewards.begin() + info.phase, info.rewards.end());
    w.values(g.outcome, g.screenState, info, g.lastRoom, g.curEvent, g.curRoom, g.boss,
             g.shopRemoveCount, g.speedrunPace, g.curMapNodeX, g.curMapNodeY, static_cast<bool>(g.map));
    if (g.map) {
        w.values(g.map->burningEliteX, g.map->burningEliteY, g.map->burningEliteBuff);
        for (const auto &row : g.map->nodes) w.sequence(row);
    }
    w.values(g.act, g.ascension, g.floorNum, g.cc, g.curHp, g.maxHp, g.gold,
             g.potionCount, g.potionCapacity, g.wingBootsCharges);
    w.sequence(g.potions);
    w.sequence(g.relics.relics);
    w.values(g.relics.relicBits0, g.relics.relicBits1, g.relics.relicBits2);
    w.sequence(g.deck.cards);
    w.sequence(g.deck.cardTypeCounts);
    w.sequence(g.deck.bottleIdxs);
    w.values(g.deck.upgradeableCount, g.deck.transformableCount,
             g.blueKey, g.greenKey, g.redKey,
             static_cast<bool>(g.regainControlAction), g.smokeBombUsed);
    w.sequence(path.roomVisits);
    w.value(path.lastNodeKey);
    return std::hash<std::string>{}(w.finish());
}
struct ReuseCandidate {
    std::uint64_t visits = 0, subtreeDecisionNodes = 0;
    std::uint32_t depth = 0;
    sts::search::OocActionId rootAction = 0;
    bool combat = false, publicStochastic = false;
};
// Stored decision nodes of the most recent completed non-singleton search.
struct ReuseIndex {
    bool valid = false, truncated = false;
    std::uint64_t seed = 0, decision = 0, simulations = 0, storedDecisionNodes = 0;
    int floor = -1, screen = -1;
    sts::search::OocActionId selected = 0;
    std::unordered_multimap<std::uint64_t, ReuseCandidate> rng, publicState;
};
thread_local ReuseIndex t_reuseIndex;
ReuseIndex buildReuseIndex(const OocGameContextModel &model, const sts::search::OocTreeSnapshot &tree) {
    ReuseIndex index;
    index.truncated = tree.truncated;
    const auto n = tree.nodes.size();
    std::vector<std::optional<std::uint64_t>> parent(n);
    std::vector<std::vector<std::uint64_t>> children(n);
    for (const auto &edge : tree.edges)
        if (edge.childId) { parent[*edge.childId] = edge.parentId; children[edge.parentId].push_back(*edge.childId); }
    std::vector<std::uint64_t> rngKey(n), publicKey(n), subtree(n);
    std::vector<ReuseCandidate> info(n);
    for (std::uint64_t i = 0; i < n; ++i) {
        const auto &node = tree.nodes[i];
        if (!node.chance) {
            rngKey[i] = reusePublicFingerprint(model.state(node.state), model.pathHistory(node.state), true);
            publicKey[i] = reusePublicFingerprint(model.state(node.state), model.pathHistory(node.state), false);
        }
    }
    // Snapshot nodes are breadth-first: every parent precedes its children.
    for (std::uint64_t i = 0; i < n; ++i) {
        const auto &node = tree.nodes[i];
        if (!parent[i]) continue;
        auto &current = info[i];
        current = info[*parent[i]];
        if (node.chance) {
            if (node.depth == 0) current.rootAction = node.action;
            std::set<std::uint64_t> outcomes;
            for (auto child : children[i]) outcomes.insert(publicKey[child]);
            current.publicStochastic = current.publicStochastic || outcomes.size() > 1;
        } else {
            current.depth = node.depth;
            current.visits = node.visits;
            current.combat = current.combat || model.prediction(node.state).used;
        }
    }
    for (std::uint64_t i = n; i-- > 0;) {
        subtree[i] += tree.nodes[i].chance ? 0 : 1;
        if (parent[i]) subtree[*parent[i]] += subtree[i];
    }
    for (std::uint64_t i = 1; i < n; ++i) {
        if (tree.nodes[i].chance) continue;
        info[i].subtreeDecisionNodes = subtree[i];
        index.rng.emplace(rngKey[i], info[i]);
        index.publicState.emplace(publicKey[i], info[i]);
        ++index.storedDecisionNodes;
    }
    return index;
}
nlohmann::json reuseMatchJson(const ReuseIndex &index, const std::unordered_multimap<std::uint64_t, ReuseCandidate> &stored,
                              std::uint64_t key) {
    const auto [first, last] = stored.equal_range(key);
    std::uint64_t matches = 0, selectedMatches = 0, selectedVisits = 0;
    const ReuseCandidate *best = nullptr;
    for (auto it = first; it != last; ++it) {
        const auto &candidate = it->second;
        const bool selected = candidate.rootAction == index.selected;
        ++matches; selectedMatches += selected;
        if (selected) selectedVisits += candidate.visits;
        const bool bestSelected = best && best->rootAction == index.selected;
        if (!best || (selected && !bestSelected) || (selected == bestSelected && candidate.visits > best->visits))
            best = &candidate;
    }
    // Summed visits over publicly identical particles bound what merging them
    // could retain; direct rerooting retains only the best single particle.
    nlohmann::json row = {{"matches", matches}, {"selectedBranchMatches", selectedMatches},
        {"selectedBranchVisitsSum", selectedVisits}};
    if (best) row["best"] = {{"depth", best->depth}, {"visits", best->visits},
        {"subtreeDecisionNodes", best->subtreeDecisionNodes}, {"underSelectedAction", best->rootAction == index.selected},
        {"combatOnPath", best->combat}, {"publicStochasticOnPath", best->publicStochastic}};
    return row;
}
}
bool liveOocMctsEnabled() { return liveEnabled; }
bool liveOocMctsTreeRules() { return liveEnabled && liveOptions.treeRules; }
bool liveOocMctsHeart1Fallback(const GameContext &gc) {
    return liveEnabled && liveOptions.heart1Coverage && heart1FullScreen(gc);
}
bool liveOocMctsUsesHeart1() { return liveEnabled && liveOptions.heart1Prior; }
bool liveOocSiblingCaptureEnabled() { return liveEnabled && liveSibling.has_value(); }
nlohmann::json liveOocMctsSpecification() {
    if (!liveEnabled) return nullptr;
    // Every control the search reads, as set: STS_OOC_MCTS*, the combat
    // transition model (STS_CTM_*, incl. the research candidate manifest) and
    // the Silver root prior. Output-only trace/graph paths are left out.
    nlohmann::json environment = nlohmann::json::object();
    for (char **entry = environ; entry && *entry; ++entry) {
        const std::string pair(*entry);
        const auto eq = pair.find('=');
        const std::string key = pair.substr(0, eq);
        if (key.rfind("STS_OOC_MCTS", 0) != 0 && key.rfind("STS_CTM_", 0) != 0
                && key.rfind("STS_SILVER_ROOT_PRIOR", 0) != 0)
            continue;
        if (key.size() >= 6 && key.compare(key.size() - 6, 6, "_TRACE") == 0) continue;
        if (key.find("_GRAPH_") != std::string::npos) continue;
        if (key == "STS_OOC_MCTS_LEAF_CAPTURE") continue;
        environment[key] = eq == std::string::npos ? std::string{} : pair.substr(eq + 1);
    }
    const char *leaf = std::getenv("STS_OOC_MCTS_LEAF_VALUE");
    return {{"simulations", liveSimulations},
            {"leaf_value", leaf ? std::string(leaf) : std::string("screengbm")},
            {"environment", std::move(environment)}};
}
// Counterfactual label generation: the same hidden-future redraw OOC MCTS
// applies to its leaves, on a detached branch state.
void resampleCounterfactualFuture(GameContext &gc, std::mt19937_64 &rng) {
    sampleNoncombatFuture(gc, rng);
}
std::uint64_t oocMctsSearchSeed(std::uint64_t seed, std::uint64_t index) {
    return splitMix64(seed ^ splitMix64(index));
}
void configureLiveOocMcts() {
    liveSamplerA20.reset();
    liveFallbackSampler.reset();
    liveFallbackSamplerA20.reset();
    liveUnsupportedSilverSims = 0;
    liveAct4SilverSims = 0;
    const char *enabled = std::getenv("STS_OOC_MCTS");
    if (enabled && std::string(enabled) != "0" && std::string(enabled) != "1")
        throw std::runtime_error("STS_OOC_MCTS must be 0 or 1");
    liveEnabled = enabled && std::string(enabled) == "1";
    const char *a20Ctm = std::getenv("STS_OOC_MCTS_A20_CTM");
    if (a20Ctm && std::string(a20Ctm) != "0" && std::string(a20Ctm) != "1")
        throw std::runtime_error("STS_OOC_MCTS_A20_CTM must be 0 or 1 when set");
    if (const char *trace = std::getenv("STS_OOC_MCTS_TRACE")) liveTrace = trace;
    if (!liveTrace.empty()) {
        std::ofstream out(liveTrace, std::ios::app);
        if (!out) throw std::runtime_error("STS_OOC_MCTS_TRACE cannot open output");
    }
    liveRootLockTrace.clear();
    liveRootTrace.clear();
    liveCheckpointTrace.clear();
    liveReuseTrace.clear();
    liveSimulations = 512; liveConfig = {}; liveOptions = {true};
    liveGraphPath.clear(); liveGraphDecisionIndex = 1;
    liveLeafCapture.reset();
    pendingLeafCapturePath.clear();
    pendingLeafCaptureProvenance = nullptr;
    if (std::getenv("STS_OOC_MCTS_LEAF_CAPTURE") && !liveEnabled)
        throw std::runtime_error("STS_OOC_MCTS_LEAF_CAPTURE requires STS_OOC_MCTS=1");
    liveSibling.reset();
    if (const char *path = std::getenv("STS_OOC_SIBLING_CAPTURE")) {
        if (!liveEnabled || !*path) throw std::runtime_error("STS_OOC_SIBLING_CAPTURE requires STS_OOC_MCTS=1 and a path");
        if (std::getenv("STS_OOC_MCTS_LEAF_CAPTURE"))
            throw std::runtime_error("STS_OOC_SIBLING_CAPTURE excludes STS_OOC_MCTS_LEAF_CAPTURE");
        const auto knob = [](const char *key, std::uint64_t fallback, std::uint64_t low, std::uint64_t high) {
            const char *raw = std::getenv(key);
            if (!raw) return fallback;
            const std::string value(raw);
            if (value.empty() || value.size() > 9 || value.find_first_not_of("0123456789") != std::string::npos
                    || std::stoull(value) < low || std::stoull(value) > high)
                throw std::runtime_error(std::string(key) + " out of range");
            return std::uint64_t(std::stoull(value));
        };
        LiveSiblingCapture sibling;
        sibling.every = knob("STS_OOC_SIBLING_EVERY", 4, 1, 1000);
        sibling.repeats = unsigned(knob("STS_OOC_SIBLING_REPEATS", 1, 0, 256));
        sibling.longRepeats = unsigned(knob("STS_OOC_SIBLING_LONG", 0, 0, 16));
        sibling.maxDepth = unsigned(knob("STS_OOC_SIBLING_MAX_DEPTH", 2, 1, 64));
        sibling.maxLeaves = knob("STS_OOC_SIBLING_MAX_LEAVES", 256, 1, 100000);
        sibling.out = std::make_shared<std::ofstream>(path, std::ios::app);
        if (!*sibling.out) throw std::runtime_error("STS_OOC_SIBLING_CAPTURE cannot open output");
        // Load heart1 in the parent: forked children must not each reload it.
        if (one_combat::heart1::enabled()) (void)one_combat::heart1::net();
        liveSibling = std::move(sibling);
    }
    // =0 means off, as if unset.
    const auto silverSimsEnv = [](const char *name) -> const char * {
        const char *raw = std::getenv(name);
        return raw && std::string(raw) == "0" ? nullptr : raw;
    };
    const char *unsupportedSilver = silverSimsEnv("STS_OOC_MCTS_UNSUPPORTED_SILVER_SIMS");
    if (unsupportedSilver && !liveEnabled)
        throw std::runtime_error("STS_OOC_MCTS_UNSUPPORTED_SILVER_SIMS requires STS_OOC_MCTS=1");
    const char *act4Silver = silverSimsEnv("STS_OOC_MCTS_ACT4_SILVER_SIMS");
    if (act4Silver && !liveEnabled)
        throw std::runtime_error("STS_OOC_MCTS_ACT4_SILVER_SIMS requires STS_OOC_MCTS=1");
    if (!liveEnabled) return;
    decisionLogPath.clear();
    if (const char *path = std::getenv("STS_OOC_MCTS_DECISION_LOG"); path && *path) decisionLogPath = path;
    if (const char *path = std::getenv("STS_OOC_MCTS_GRAPH_FILE")) liveGraphPath = path;
    if (const char *index = std::getenv("STS_OOC_MCTS_GRAPH_DECISION_INDEX")) {
        const std::string value(index);
        if (value.empty() || value.find_first_not_of("0123456789") != std::string::npos)
            throw std::runtime_error("STS_OOC_MCTS_GRAPH_DECISION_INDEX must be a nonnegative integer");
        liveGraphDecisionIndex = std::stoull(value);
    }
    if (sts::search::nativeSilverReuseCap() != 32768)
        throw std::runtime_error("live OOC MCTS requires frozen Silver reuse cap 32768");
    if (!g_oocStrategicTokNet.ok) throw std::runtime_error("STS_OOC_MCTS requires native V4 policy");
    const char *leafValue = std::getenv("STS_OOC_MCTS_LEAF_VALUE");
    const bool bossLeafRequested = leafValue && std::string(leafValue) == "boss";
    if (!bossLeafRequested && !winNetOk()) throw std::runtime_error("STS_OOC_MCTS requires native v_win");
    // Legacy win loading may retry the default. An explicit failed request must
    // remain a startup failure even if that retry succeeded.
    if (const char *requested = std::getenv("STS_WIN_NET")) {
        CompactTreeNet explicitWin;
        const std::string path = std::string(requested) == "1" ? "models/v_win_trees.txt" : requested;
        if (!explicitWin.load(path, richIdxMap()))
            throw std::runtime_error("STS_OOC_MCTS explicit STS_WIN_NET failed to load");
    }
    if (const char *sims = std::getenv("STS_OOC_MCTS_SIMS")) {
        const std::string value(sims);
        if (value.empty() || value.find_first_not_of("0123456789") != std::string::npos)
            throw std::runtime_error("STS_OOC_MCTS_SIMS must be a positive integer");
        liveSimulations = std::stoull(value);
        if (!liveSimulations) throw std::runtime_error("STS_OOC_MCTS_SIMS must be positive");
    }
    liveConfig = {}; liveOptions = {true};
    liveOptions.sampleNoncombat = true;
    liveOptions.collectKeys = g_collectKeys;
    if (const char *trace = std::getenv("STS_OOC_MCTS_PRIOR_TRACE"); trace && *trace) {
        liveOptions.priorTracePath = trace;
        std::ofstream out(liveOptions.priorTracePath, std::ios::app);
        if (!out) throw std::runtime_error("STS_OOC_MCTS_PRIOR_TRACE cannot open output");
    }
    liveConfig.allowUnqualifiedRootStop = true; // May skip later aborts; provider guarantee remains false.
    // ADR-0031 (§464): live tree rules and outcome merging are the defaults;
    // STS_OOC_MCTS_TREE_RULES=0 / STS_OOC_MCTS_MERGE_OUTCOMES=0 restore the old tree.
    liveConfig.mergeEquivalentOutcomes = true;
    liveOptions.treeRules = true;
    // ADR-0032 (§459): greedy rollout shops are the default; STS_OOC_MCTS_ROLLOUT_SHOP=planner restores the bundle planner.
    liveOptions.greedyRolloutShop = true;
    for (const char *key : liveControlKeys)
        if (const char *value = std::getenv(key)) applyLiveControl(key, value, liveConfig, liveOptions);
    if (liveOptions.cpuBudgetSeconds > 0 && (liveConfig.allowUnqualifiedRootStop
            || liveConfig.stopAt512VisitGap20 || liveConfig.observeRootLock
            || std::getenv("STS_OOC_MCTS_LEAF_CAPTURE") || std::getenv("STS_OOC_SIBLING_CAPTURE")
            || std::getenv("STS_OOC_MCTS_ROOT_LOCK_TRACE") || std::getenv("STS_OOC_MCTS_CHECKPOINT_TRACE")
            || std::getenv("STS_OOC_MCTS_REUSE_TRACE") || std::getenv("STS_OOC_MCTS_GRAPH_FILE")
            || std::getenv("STS_OOC_MCTS_DECISION_LOG")
            || std::getenv("STS_OOC_MCTS_PRIOR_TRACE")))
        throw std::runtime_error("STS_OOC_MCTS_CPU_SECONDS requires EARLY_STOP=0, no gap/lock or leaf/prior capture");
    if (liveOptions.heart1LeafPolicy && !heart1::enabled())
        throw std::runtime_error("STS_OOC_MCTS_LEAF_POLICY=heart1 requires STS_OOC_HEART1");
    // Philipp 2026-10-17: with heart1 weights loaded, heart1full is the default tree prior.
    // STS_OOC_MCTS_PRIOR=heart1 restores the V4-gated heart1 prior, =policy the V4 prior.
    if (!std::getenv("STS_OOC_MCTS_PRIOR") && heart1::enabled())
        applyLiveControl("STS_OOC_MCTS_PRIOR", "heart1full", liveConfig, liveOptions);
    // ADR-TBD (Philipp 2026-10-17): weights with the select-distill inputs (x_act, e.g. student_sel.bin) default
    // to TARGET_PRIOR=1 and, under heart1full + LEAF_POLICY=heart1, LEAF_SELECTS=heart1. Student C (no x_act)
    // is unchanged; STS_OOC_MCTS_TARGET_PRIOR=0 / STS_OOC_MCTS_LEAF_SELECTS=chain restore the old behaviour.
    if (heart1::enabled() && heart1::net().extraInputs()) {
        if (!std::getenv("STS_OOC_MCTS_TARGET_PRIOR") && liveOptions.heart1Prior)
            applyLiveControl("STS_OOC_MCTS_TARGET_PRIOR", "1", liveConfig, liveOptions);
        if (!std::getenv("STS_OOC_MCTS_LEAF_SELECTS") && liveOptions.heart1LeafPolicy && liveOptions.heart1Coverage)
            applyLiveControl("STS_OOC_MCTS_LEAF_SELECTS", "heart1", liveConfig, liveOptions);
    }
    // Default leaf (ADR-0027): GBM screen leaf on a pinned X2-B anchor. STS_OOC_MCTS_LEAF_VALUE=native rolls back.
    if (!std::getenv("STS_OOC_MCTS_LEAF_VALUE")) applyLiveControl("STS_OOC_MCTS_LEAF_VALUE", "screengbm", liveConfig, liveOptions);
    if (liveOptions.screenLeaf) {
        const char *model = std::getenv("STS_OOC_MCTS_SCREEN_LEAF_MODEL");
        if (liveOptions.screenGbm && (!model || !*model)) model = kDefaultScreenGbmModel;
        if (!model || !*model) throw std::runtime_error("STS_OOC_MCTS_LEAF_VALUE=screen requires STS_OOC_MCTS_SCREEN_LEAF_MODEL");
#ifdef STS_LIVE_ADVISOR
        throw std::runtime_error("STS_OOC_MCTS_LEAF_VALUE=screen is unavailable in the live advisor");
#else
        if (liveOptions.screenGbm)
            liveOptions.screenLeafGbm = std::make_shared<const ScreenLeafGbm>(model, richIdxMap(),
                int(richIdxMap().size()), kScreenGbmAnchor);
        else liveOptions.screenLeafNet = std::make_shared<const ScreenLeafNet>(model);
#endif
    }
    if (const char *model = std::getenv("STS_OOC_MCTS_LEAF_WIN_MODEL"); model && *model) {
#ifdef STS_LIVE_ADVISOR
        throw std::runtime_error("STS_OOC_MCTS_LEAF_WIN_MODEL is unavailable in the live advisor");
#else
        // The screen leaves are residuals on the pinned X2-B anchor, and the
        // boss/constant leaves use no win model, so only native/direct qualify.
        if (liveOptions.screenLeaf || liveOptions.bossLeaf || liveOptions.bossRollout || liveOptions.constantLeaf)
            throw std::runtime_error("STS_OOC_MCTS_LEAF_WIN_MODEL requires STS_OOC_MCTS_LEAF_VALUE=native or direct");
        auto net = std::make_shared<CompactTreeNet>();
        if (!net->load(model, richIdxMap(), "STS_OOC_MCTS_LEAF_WIN_MODEL") || !net->logistic)
            throw std::runtime_error("STS_OOC_MCTS_LEAF_WIN_MODEL failed to load a logistic win model");
        liveOptions.leafWinNet = std::move(net);
        liveOptions.leafWinPath = model;
#endif
    }
    if (const char *model = std::getenv("STS_OOC_MCTS_LEAF_HEART_MODEL"); model && *model) {
#ifdef STS_LIVE_ADVISOR
        throw std::runtime_error("STS_OOC_MCTS_LEAF_HEART_MODEL is unavailable in the live advisor");
#else
        const char *leafMode = std::getenv("STS_OOC_MCTS_LEAF_VALUE");
        if (!leafMode || std::string(leafMode) != "native" || liveOptions.leafWinNet)
            throw std::runtime_error("STS_OOC_MCTS_LEAF_HEART_MODEL requires STS_OOC_MCTS_LEAF_VALUE=native and no STS_OOC_MCTS_LEAF_WIN_MODEL");
        liveOptions.heartLeaf = std::make_shared<const HeartLeafModel>(model);
        liveOptions.heartLeafPath = model;
#endif
    }
    if (const char *student = std::getenv("STS_OOC_MCTS_LEAF_STUDENT"); student && *student) {
#ifdef STS_LIVE_ADVISOR
        throw std::runtime_error("STS_OOC_MCTS_LEAF_STUDENT is unavailable in the live advisor");
#else
        // The §494 student learned rollout values on the native leaf anchor; sibling
        // capture's repeat rollouts would be replaced by the student itself.
        const char *leafMode = std::getenv("STS_OOC_MCTS_LEAF_VALUE");
        if (!liveEnabled || !leafMode || std::string(leafMode) != "native" || liveOptions.leafWinNet || liveOptions.heartLeaf)
            throw std::runtime_error("STS_OOC_MCTS_LEAF_STUDENT requires STS_OOC_MCTS=1 and STS_OOC_MCTS_LEAF_VALUE=native");
        if (std::getenv("STS_OOC_SIBLING_CAPTURE") || std::getenv("STS_OOC_MCTS_LEAF_CAPTURE"))
            throw std::runtime_error("STS_OOC_MCTS_LEAF_STUDENT excludes leaf and sibling capture");
        liveOptions.rolloutStudent = std::make_shared<const RolloutStudent>(student);
        liveOptions.rolloutStudentPath = student;
#endif
    }
    if (liveConfig.stopAt512VisitGap20
        && (liveSimulations != 2048 || liveConfig.selectByMeanQ))
        throw std::runtime_error("STS_OOC_MCTS_GAP_STOP_20 requires 2048 visit-selected simulations");
    if (const char *trace = std::getenv("STS_OOC_MCTS_ROOT_LOCK_TRACE")) liveRootLockTrace = trace;
    liveConfig.observeRootLock = !liveRootLockTrace.empty();
    // Observation only (heart outcome round 2): one row per live root with
    // candidate keys, normalized visits, public record and native snapshot.
    if (const char *trace = std::getenv("STS_OOC_MCTS_ROOT_TRACE"); trace && *trace) {
        liveRootTrace = trace;
        std::ofstream out(liveRootTrace, std::ios::app);
        if (!out) throw std::runtime_error("STS_OOC_MCTS_ROOT_TRACE cannot open output");
    }
    if (const char *trace = std::getenv("STS_OOC_MCTS_REUSE_TRACE")) liveReuseTrace = trace;
    if (!liveReuseTrace.empty()) {
        if (!liveGraphPath.empty())
            throw std::runtime_error("STS_OOC_MCTS_REUSE_TRACE cannot be combined with STS_OOC_MCTS_GRAPH_FILE");
        std::ofstream out(liveReuseTrace, std::ios::app);
        if (!out) throw std::runtime_error("STS_OOC_MCTS_REUSE_TRACE cannot open output");
        std::cout << "[ooc-reuse-observer ON live_policy_unchanged=1 tree_node_cap=100000]\n";
    }
    if (const char *trace = std::getenv("STS_OOC_MCTS_CHECKPOINT_TRACE")) liveCheckpointTrace = trace;
    if (!liveCheckpointTrace.empty()) {
        if (liveSimulations != 2048 || liveConfig.selectByMeanQ || liveConfig.observeRootLock)
            throw std::runtime_error("checkpoint shadow requires 2048 visit selection and no root-lock observer");
        std::ofstream out(liveCheckpointTrace, std::ios::app);
        if (!out) throw std::runtime_error("STS_OOC_MCTS_CHECKPOINT_TRACE cannot open output");
        std::cout << "[ooc-checkpoint-shadow ON live_policy_unchanged=1 checkpoints=128,256,512,1024,2048]\n";
    }
    if (liveConfig.observeRootLock) {
        std::ofstream out(liveRootLockTrace, std::ios::app);
        if (!out) throw std::runtime_error("STS_OOC_MCTS_ROOT_LOCK_TRACE cannot open output");
        std::cout << "[ooc-root-lock-observer ON full_budget=1 hypothetical_only=1]\n";
    }
    // Research only: STS_OOC_MCTS_COMBAT_RESOLVER=silver replaces the CTM with
    // native Silver at STS_OOC_MCTS_SILVER_SIMS per root, root prior on. Live
    // combats stay plain: STS_SILVER_ROOT_PRIOR_SCOPE=override is required.
    const char *resolver = std::getenv("STS_OOC_MCTS_COMBAT_RESOLVER");
    const bool silverResolver = resolver != nullptr;
    liveSilverResolverSims = 0;
    if (silverResolver) {
        if (std::string(resolver) != "silver")
            throw std::runtime_error("STS_OOC_MCTS_COMBAT_RESOLVER must be silver when set");
        for (const char *key : {"STS_OOC_MCTS_COMBAT_MODEL", "STS_OOC_MCTS_BREW_FALLBACK_MODEL",
                                "STS_OOC_MCTS_ACTIVE_LIZARD", "STS_CTM_RESEARCH_CANDIDATE_MANIFEST"})
            if (std::getenv(key))
                throw std::runtime_error(std::string("STS_OOC_MCTS_COMBAT_RESOLVER=silver excludes ") + key);
        const char *sims = std::getenv("STS_OOC_MCTS_SILVER_SIMS");
        const std::string value = sims ? sims : "";
        if (value.empty() || value.size() > 6 || value.find_first_not_of("0123456789") != std::string::npos
                || std::stoi(value) < 1)
            throw std::runtime_error("STS_OOC_MCTS_COMBAT_RESOLVER=silver requires STS_OOC_MCTS_SILVER_SIMS in 1..999999");
        // The Silver backend parses its options after this point; check the environment.
        const auto env = [](const char *key) { const char *v = std::getenv(key); return std::string(v ? v : ""); };
        if (env("STS_SILVER_ROOT_PRIOR").empty() || env("STS_SILVER_ROOT_PRIOR_WEIGHT").empty()
                || env("STS_SILVER_ROOT_PRIOR_SCOPE") != "override")
            throw std::runtime_error("STS_OOC_MCTS_COMBAT_RESOLVER=silver requires STS_SILVER_ROOT_PRIOR and STS_SILVER_ROOT_PRIOR_SCOPE=override");
        if (env("STS_SILVER_EXACT_ROOT_BUDGETS") != "1")
            throw std::runtime_error("STS_OOC_MCTS_COMBAT_RESOLVER=silver requires STS_SILVER_EXACT_ROOT_BUDGETS=1");
        liveSilverResolverSims = std::stoi(value);
    }
    const char *artifactOverride = std::getenv("STS_OOC_MCTS_COMBAT_MODEL");
    if (artifactOverride && !*artifactOverride)
        throw std::runtime_error("STS_OOC_MCTS_COMBAT_MODEL cannot be empty when set");
    const bool automaticDefaultStack=artifactOverride==nullptr && !silverResolver;
    const std::string artifact=silverResolver?"native_silver_root_prior":automaticDefaultStack?
        "selfplay/models/combat_transition_deepsets_pathb_r2_lizard_ritual_refit.native":artifactOverride;
    const char *brewFallbackOverride = std::getenv("STS_OOC_MCTS_BREW_FALLBACK_MODEL");
    if (brewFallbackOverride && !*brewFallbackOverride)
        throw std::runtime_error("STS_OOC_MCTS_BREW_FALLBACK_MODEL cannot be empty when set");
    const std::string brewFallbackArtifact=brewFallbackOverride?brewFallbackOverride:
        (automaticDefaultStack?"selfplay/models/combat_transition_near_full_escape_pathb_r2_ritual_refit.native":"");
    const char *activeLizardOverride=std::getenv("STS_OOC_MCTS_ACTIVE_LIZARD");
    bool activeLizardEnabled=automaticDefaultStack;
    if(activeLizardOverride) {
        if(std::string(activeLizardOverride)=="0")activeLizardEnabled=false;
        else if(std::string(activeLizardOverride)=="1")activeLizardEnabled=true;
        else throw std::runtime_error("STS_OOC_MCTS_ACTIVE_LIZARD must be 0 or 1 when set");
    }
    if(activeLizardEnabled && brewFallbackArtifact.empty())
        throw std::runtime_error("STS_OOC_MCTS_ACTIVE_LIZARD=1 requires STS_OOC_MCTS_BREW_FALLBACK_MODEL");
    std::string researchCandidate;
    if(silverResolver) {
        liveSampler = std::make_shared<SilverCombatTransitionSampler>(liveSilverResolverSims);
        std::cout << "[ooc-mcts-silver-resolver] silver_sims=" << liveSilverResolverSims
            << " root_prior=" << std::getenv("STS_SILVER_ROOT_PRIOR")
            << " root_prior_weight=" << std::getenv("STS_SILVER_ROOT_PRIOR_WEIGHT")
            << " redraw=seed_and_six_combat_streams live_root_prior=off\n";
    } else if(!brewFallbackArtifact.empty()) {
        auto hybrid = std::make_shared<EntropicBrewFallbackCombatTransitionSampler>(
            artifact,brewFallbackArtifact,activeLizardEnabled);
        if(hybrid->fastRuntime().researchCandidate())
            researchCandidate=hybrid->fastRuntime().identity().at("candidateId").get<std::string>();
        liveSampler = hybrid;
    } else {
        auto native = std::make_shared<NativeCombatTransitionSampler>(artifact);
        if(native->runtime().researchCandidate())
            researchCandidate=native->runtime().identity().at("candidateId").get<std::string>();
        liveSampler = native;
    }
    // Research candidates are named in the log; production output is unchanged.
    if(!researchCandidate.empty())
        std::cout << "[ctm-research-candidate] candidate_id=" << researchCandidate << "\n";
    // §470: the bundled A20 Lizard CTM with its boss calibration, for ascension-20 decisions only; below A20 the
    // stack above stays in use. Only beside the automatic default stack, so no override can mix into it. Unset, it
    // follows that stack (ADR-0033): on with it, off with any CTM override; 0 turns it off, 1 requires the stack.
    const bool a20Compatible = automaticDefaultStack && !brewFallbackOverride && activeLizardEnabled
        && !std::getenv("STS_CTM_RESEARCH_CANDIDATE_MANIFEST") && !std::getenv("STS_OOC_MCTS_LEAF_CAPTURE");
    const bool a20Requested = a20Ctm ? std::string(a20Ctm) == "1" : a20Compatible;
    if (a20Requested) {
        if (!a20Compatible)
            throw std::runtime_error("STS_OOC_MCTS_A20_CTM=1 requires the default CTM stack: no STS_OOC_MCTS_COMBAT_MODEL, "
                "STS_OOC_MCTS_BREW_FALLBACK_MODEL, STS_OOC_MCTS_ACTIVE_LIZARD=0, STS_OOC_MCTS_COMBAT_RESOLVER, "
                "STS_CTM_RESEARCH_CANDIDATE_MANIFEST or STS_OOC_MCTS_LEAF_CAPTURE");
        auto a20 = std::make_shared<EntropicBrewFallbackCombatTransitionSampler>(
            "selfplay/models/combat_transition_deepsets_pathb_a20_lizard.native",
            "selfplay/models/combat_transition_near_full_escape_pathb_a20.native", true);
        const auto &identity = a20->fastRuntime().identity();
        if (identity.at("candidateId") != "pathb-a20" || !identity.contains("bossSurvivalLogitShift"))
            throw std::runtime_error("STS_OOC_MCTS_A20_CTM=1 did not load the calibrated pathb-a20 stack");
        liveSamplerA20 = a20;
        std::cout << std::setprecision(17) << "[ctm-a20-stack] candidate_id=pathb-a20 scope=ascension20"
            << " boss_survival_logit_shift=" << identity.at("bossSurvivalLogitShift").get<double>()
            << " active_lizard_correction=1\n" << std::setprecision(6);
    }
    const auto silverSims = [&](const char *raw, const char *name) {
        const std::string value = raw;
        if (value.empty() || value.size() > 6 || value.find_first_not_of("0123456789") != std::string::npos
                || std::stoi(value) < 1)
            throw std::runtime_error(std::string(name) + " must be in 1..999999");
        if (silverResolver)
            throw std::runtime_error(std::string(name) + " excludes STS_OOC_MCTS_COMBAT_RESOLVER");
        if (std::getenv("STS_OOC_MCTS_LEAF_CAPTURE"))
            throw std::runtime_error(std::string(name) + " excludes STS_OOC_MCTS_LEAF_CAPTURE");
        return std::stoi(value);
    };
    if (unsupportedSilver) liveUnsupportedSilverSims = silverSims(unsupportedSilver, "STS_OOC_MCTS_UNSUPPORTED_SILVER_SIMS");
    if (act4Silver) liveAct4SilverSims = silverSims(act4Silver, "STS_OOC_MCTS_ACT4_SILVER_SIMS");
    if (unsupportedSilver || act4Silver) {
        liveFallbackSampler = std::make_shared<SilverFallbackCombatTransitionSampler>(
            liveSampler, liveUnsupportedSilverSims, liveAct4SilverSims);
        if (liveSamplerA20)
            liveFallbackSamplerA20 = std::make_shared<SilverFallbackCombatTransitionSampler>(
                liveSamplerA20, liveUnsupportedSilverSims, liveAct4SilverSims);
        std::cout << "[ooc-mcts-silver-fallback] unsupported_silver_sims=" << liveUnsupportedSilverSims
            << " act4_silver_sims=" << liveAct4SilverSims
            << " root_prior=off redraw=seed_and_six_combat_streams\n";
    }
    if (const char *capturePath = std::getenv("STS_OOC_MCTS_LEAF_CAPTURE")) {
        if (silverResolver || liveOptions.screenLeaf || liveOptions.bossLeaf
                || liveOptions.bossRollout || liveOptions.directLeaf || liveOptions.constantLeaf)
            throw std::runtime_error("leaf capture currently requires the native CTM rollout leaf");
        nlohmann::json identity;
        if (const auto hybrid = std::dynamic_pointer_cast<const EntropicBrewFallbackCombatTransitionSampler>(liveSampler))
            identity = hybrid->fastRuntime().identity();
        else if (const auto native = std::dynamic_pointer_cast<const NativeCombatTransitionSampler>(liveSampler))
            identity = native->runtime().identity();
        std::vector<std::pair<std::string, std::string>> files = {
            {"ctm", artifact}, {"brewFallbackCtm", brewFallbackArtifact},
            {"leafWinOverride", liveOptions.leafWinPath}, {"leafHeartModel", liveOptions.heartLeafPath}};
        if (const char *manifest = std::getenv("STS_CTM_RESEARCH_CANDIDATE_MANIFEST"))
            files.emplace_back("ctmManifest", manifest);
        auto provenance = oocLeafCaptureProvenance(identity, files);
        provenance["effectiveLeaf"] = {{"combats", liveOptions.leafCombats},
            {"uniformPolicy", liveOptions.uniformLeafPolicy}, {"priorPolicy", liveOptions.priorLeafPolicy},
            {"heart1Policy", liveOptions.heart1LeafPolicy},
            {"sampleNoncombat", liveOptions.sampleNoncombat},
            {"stopAtMapCheckpoint", liveOptions.stopAtMapCheckpoint}, {"collectKeys", liveOptions.collectKeys}};
        pendingLeafCapturePath = capturePath;
        if (pendingLeafCapturePath.empty())
            throw std::runtime_error("STS_OOC_MCTS_LEAF_CAPTURE cannot be empty");
        pendingLeafCaptureProvenance = std::move(provenance);
    }
    const auto precision = std::cout.precision();
    std::cout << std::setprecision(17) << "[live OOC MCTS ON sims=" << liveSimulations
        << " combat_model=" << artifact
        << (!brewFallbackArtifact.empty() ? std::string(" brew_fallback_model=")+brewFallbackArtifact+
            " dispatch=precombat_entropic_brew" : std::string{})
        << " active_lizard_correction=" << (activeLizardEnabled?"1":"0")
        << " prior=" << (liveOptions.uniformPrior ? "uniform" : liveOptions.heart1Coverage ? "heart1full" : liveOptions.heart1Prior ? "heart1" : "policy")
        << " cpu_seconds=" << liveOptions.cpuBudgetSeconds
        << " temperature=" << liveOptions.priorTemperature << " cpuct=" << liveConfig.cPuct
        << " widen_k=" << liveConfig.wideningK << " widen_alpha=" << liveConfig.wideningAlpha
        << " max_depth=" << liveConfig.maxDepth << " root_selection=" << (liveConfig.selectByMeanQ ? "q" : "visits")
        << " early_stop=" << liveConfig.allowUnqualifiedRootStop
        << " gap_stop_20=" << liveConfig.stopAt512VisitGap20
        << " merge_outcomes=" << liveConfig.mergeEquivalentOutcomes
        << " leaf_value=" << (liveOptions.bossLeaf ? "boss" : liveOptions.bossRollout ? "bossrollout" : liveOptions.constantLeaf ? "constant" : liveOptions.directLeaf ? "direct" : liveOptions.screenLeaf ? (liveOptions.screenLeafGbm ? "screengbm" : "screen") : "native")
        << " leaf_combats=" << liveOptions.leafCombats << " leaf_policy=" << (liveOptions.heart1LeafPolicy ? "heart1" : liveOptions.uniformLeafPolicy ? "uniform" : liveOptions.priorLeafPolicy ? "prior" : "v4")
        << (liveOptions.greedyRolloutShop ? " rollout_shop=greedy" : "")
        << (liveOptions.targetPrior ? " target_prior=1" : "") << (liveOptions.heart1LeafSelects ? " leaf_selects=heart1" : "")
        << (liveOptions.leafWinNet ? " leaf_win_model=" + liveOptions.leafWinPath : std::string{})
        << (liveOptions.rolloutStudent ? " leaf_student=" + liveOptions.rolloutStudentPath : std::string{})
        << (liveOptions.heartLeaf ? " leaf_heart_model=" + liveOptions.heartLeafPath : std::string{})
        << "]\n";
    std::cout << "[ooc-mcts-config] {\"noncombatOutcomes\":\""
        << (liveOptions.sampleNoncombat ? "sampled" : "exact")
        << "\",\"prior\":\"" << (liveOptions.uniformPrior ? "uniform" : liveOptions.heart1Coverage ? "heart1full" : liveOptions.heart1Prior ? "heart1" : "policy")
        << "\",\"cpuSeconds\":" << liveOptions.cpuBudgetSeconds
        << ",\"temperature\":" << liveOptions.priorTemperature << ",\"cPuct\":" << liveConfig.cPuct
        << ",\"wideningK\":" << liveConfig.wideningK << ",\"wideningAlpha\":" << liveConfig.wideningAlpha
        << ",\"maxDepth\":" << liveConfig.maxDepth << ",\"rootSelection\":\"" << (liveConfig.selectByMeanQ ? "q" : "visits")
        << "\",\"earlyStop\":" << (liveConfig.allowUnqualifiedRootStop ? "true" : "false")
        << ",\"gapStop20\":" << (liveConfig.stopAt512VisitGap20 ? "true" : "false")
        << ",\"mergeOutcomes\":" << (liveConfig.mergeEquivalentOutcomes ? "true" : "false")
        << ",\"leafValue\":\"" << (liveOptions.bossLeaf ? "boss" : liveOptions.bossRollout ? "bossrollout" : liveOptions.constantLeaf ? "constant" : liveOptions.directLeaf ? "direct" : liveOptions.screenLeaf ? (liveOptions.screenLeafGbm ? "screengbm" : "screen") : "native")
        << "\",\"leafWinModel\":" << (liveOptions.leafWinNet ? "\"" + liveOptions.leafWinPath + "\"" : std::string("null"))
        << ",\"leafCombats\":" << liveOptions.leafCombats << ",\"leafPolicy\":\"" << (liveOptions.heart1LeafPolicy ? "heart1" : liveOptions.uniformLeafPolicy ? "uniform" : liveOptions.priorLeafPolicy ? "prior" : "v4")
        << "\",\"simulations\":" << liveSimulations
        << ",\"combatModel\":\"" << artifact << "\",\"brewFallbackModel\":"
        << (!brewFallbackArtifact.empty() ? std::string("\"")+brewFallbackArtifact+"\"" : "null")
        << ",\"dispatchRule\":\""
        << (!brewFallbackArtifact.empty() ? "precombat_entropic_brew_to_standard" : "single_artifact")
        << "\",\"activeLizardCorrection\":" << (activeLizardEnabled?"true":"false")
        << ",\"priorTrace\":\"" << liveOptions.priorTracePath << "\""
        << (liveOptions.rolloutStudent ? ",\"leafStudent\":\"" + liveOptions.rolloutStudentPath + "\"" : std::string{})
        << (liveOptions.heartLeaf ? ",\"leafHeartModel\":\"" + liveOptions.heartLeafPath + "\",\"leafHeartModelSha256\":\""
            + liveOptions.heartLeaf->manifestSha256() + "\"" : std::string{})
        << "}\n";
    std::cout.precision(precision);
}
void finalizeLiveOocMctsCapture() {
    if (pendingLeafCapturePath.empty()) return;
    pendingLeafCaptureProvenance["oocPolicy"] = effectiveOocPolicySpecification();
    liveLeafCapture = std::make_unique<OocLeafCaptureSink>(pendingLeafCapturePath, pendingLeafCaptureProvenance);
    pendingLeafCapturePath.clear();
    pendingLeafCaptureProvenance = nullptr;
    std::cout << "[ooc-leaf-capture ON roots=64 leaves_per_root=8 research_only=1]\n";
}
namespace {
void requireLeafProbeTeacher(int ascension) {
    if (!liveLeafCapture || !pendingLeafCapturePath.empty())
        throw std::runtime_error("replay_requires_finalized_capture_sink");
    if (ascension != 20 || !liveEnabled || liveSimulations != 4096
            || liveOptions.leafCombats != 3 || !liveOptions.checkpointLeaves
            || !liveOptions.sampleNoncombat || liveOptions.stopAtMapCheckpoint
            || liveOptions.uniformLeafPolicy || liveOptions.priorLeafPolicy || liveOptions.uniformPrior
            || liveOptions.heart1Prior || liveOptions.heart1LeafPolicy || liveOptions.cpuBudgetSeconds > 0
            || liveOptions.constantLeaf || liveOptions.directLeaf || liveOptions.screenLeaf
            || liveOptions.bossLeaf || liveOptions.bossRollout)
        throw std::runtime_error("replay_requires_a20_native_4096_rollout3_v4_teacher");
    if (!std::dynamic_pointer_cast<const NativeCombatTransitionSampler>(liveSampler)
            && !std::dynamic_pointer_cast<const EntropicBrewFallbackCombatTransitionSampler>(liveSampler))
        throw std::runtime_error("replay_requires_native_ctm_sampler");
    if (!g_nativeOoc || !nativeFloorPolicyAvailable() || !nativeWinPolicyAvailable()
            || !g_oocStrategicTokNet.ok)
        throw std::runtime_error("replay_requires_loaded_native_floor_win_and_v4");
    // The diagnostic permits the frozen native fallback/V4 teacher only.
    // Server policy branches and experimental nested planners must not open
    // new sockets/files after inherited descriptors have been closed.
    const auto policy = effectiveOocPolicySpecification();
    for (const char *key : {"ooc_action_nn", "act_fight_probe_all_ooc", "act_fight_probe_draft",
            "act_fight_probe_predict", "ooc_map_route", "ooc_shop_beam", "boss_draft",
            "card_nn", "card_action", "boss_v", "shop_win", "path_v", "event_v",
            "boss_relic_v", "neow_v"}) {
        const auto &flag = policy.at("flags").at(key);
        if (flag.is_boolean() ? flag.get<bool>() : flag.get<int>() != 0)
            throw std::runtime_error(std::string("replay_excludes_policy_") + key);
    }
    for (const char *key : {"STS_PATH_GRAPH", "STS_PATH_ACTION", "STS_OOC_GBM_RANKER"})
        if (const char *value = std::getenv(key); value && *value && std::string(value) != "0")
            throw std::runtime_error(std::string("replay_excludes_") + key);
    if (const char *value = std::getenv("STS_OOC_MCTS_DECISION_LOG"); value && *value)
        throw std::runtime_error("replay_excludes_output_or_probe_STS_OOC_MCTS_DECISION_LOG");
    for (char **entry = environ; entry && *entry; ++entry) {
        const std::string item(*entry);
        const auto equals = item.find('=');
        const auto key = item.substr(0, equals);
        const auto value = equals == std::string::npos ? "" : item.substr(equals + 1);
        if (key.rfind("STS_", 0) == 0 && !value.empty()
                && (key.find("TRACE") != std::string::npos || key.find("PROFILE") != std::string::npos
                    || key.find("PROBE") != std::string::npos || key == "STS_OOC_MCTS_GRAPH_FILE"))
            throw std::runtime_error("replay_excludes_output_or_probe_" + key);
    }
    if (sts::search::g_onGameActionExecute || sts::search::g_onCombatDecision
            || sts::g_onBattleExitPersistent || t_bossEntryHook)
        throw std::runtime_error("replay_excludes_external_observers");
    requireReplaySingleThread();
}
}
nlohmann::json oocSelectiveSilverAuditSpec() {
    if (!liveEnabled || !liveSamplerA20) throw std::runtime_error("audit spec requires automatic A20 stack");
    const auto hybrid = std::dynamic_pointer_cast<const EntropicBrewFallbackCombatTransitionSampler>(liveSamplerA20);
    if (!hybrid) throw std::runtime_error("audit spec requires calibrated hybrid");
    const auto mcts = liveOocMctsSpecification();
    struct EnabledScope { bool saved = liveEnabled; ~EnabledScope() { liveEnabled = saved; } } scope;
    liveEnabled = false;
    return {{"sourcePolicy", selectiveAuditSourcePolicy()}, {"ctmLoadedIdentity", hybrid->fastRuntime().identity()},
        {"mcts", mcts}, {"mapScreenEnum", int(sts::ScreenState::MAP_SCREEN)}, {"silverSimulations", 2500}};
}
int oocSelectiveSilverAccountingSelfTest() {
    return selectiveSilverAccountingSelfTest([](const std::function<nlohmann::json()> &fn, int wall, int cpu) {
        return forkLeafReplay(fn, wall, cpu, 2 * 1024 * 1024);
    });
}
int oocSelectiveSilverAuditGen(std::uint64_t seed, const std::string &plan, const std::string &out) {
    requireReplaySingleThread();
    if (!liveEnabled || !liveSamplerA20 || liveLeafCapture || leafReplayMode || leafStabilityMode
            || !liveTrace.empty() || !liveRootLockTrace.empty() || !liveCheckpointTrace.empty())
        throw std::runtime_error("selective audit requires automatic calibrated A20 CTM and no observers");
    if (sts::search::g_onGameActionExecute || sts::g_onBattleExitRaw || sts::g_onBattleExitPersistent
            || sts::search::g_onCombatDecision || t_bossEntryHook || t_realRunContextObserver)
        throw std::runtime_error("selective audit excludes external callbacks");
    struct EnabledScope { bool saved = liveEnabled; ~EnabledScope() { liveEnabled = saved; } } scope;
    liveEnabled = false; // V4 source trajectory; only explicit diagnostic searches use MCTS.
    return runSelectiveSilverAudit(seed, plan, out, liveSamplerA20, liveOptions, liveConfig,
        [](const std::function<nlohmann::json()> &fn, int wall, int cpu) {
            return forkLeafReplay(fn, wall, cpu, 2 * 1024 * 1024);
        });
}
int oocLeafStabilityProbe(std::uint64_t seed, int ascension, const std::string &planPath) {
    auto report = stabilityReport("INVALID", "startup_not_validated");
    LeafStabilityMode mode;
    mode.seed = seed;
    try {
        if (leafReplayMode || leafStabilityMode)
            throw std::runtime_error("stability_probe_already_active");
        // Validate the immutable plan before any game initialization. Limit its
        // entire input, including unexpected fields, before JSON allocation.
        std::ifstream input(planPath, std::ios::binary | std::ios::ate);
        if (!input || input.tellg() <= 0 || input.tellg() > 1024 * 1024)
            throw std::runtime_error("stability_plan_unreadable_or_oversize");
        input.seekg(0);
        mode.planSha256 = fileSha256(planPath);
        if (mode.planSha256.size() != 64) throw std::runtime_error("stability_plan_hash_failed");
        std::vector<std::set<std::string>> objectKeys;
        const auto plan = ReplayJson::parse(input, [&](int, ReplayJson::parse_event_t event, ReplayJson &value) {
            if (event == ReplayJson::parse_event_t::object_start) objectKeys.emplace_back();
            else if (event == ReplayJson::parse_event_t::key) {
                if (!objectKeys.back().insert(value.get<std::string>()).second)
                    throw std::runtime_error("stability_plan_duplicate_key");
            } else if (event == ReplayJson::parse_event_t::object_end) objectKeys.pop_back();
            return true;
        });
        mode.schedule = parseStabilityPlan(plan, seed, ascension);
        if (fileSha256(planPath) != mode.planSha256)
            throw std::runtime_error("stability_plan_changed_while_reading");
        requireLeafProbeTeacher(ascension);
        mode.childCpuStart = waitedChildCpuSeconds();
        mode.progress = [](ReplayJson row) { liveLeafCapture->stabilityProgress(std::move(row)); };
        const auto previousPolicy = captureOocPolicyThreadState();
        const auto *previousPath = t_curPath;
        struct Restore {
            OocPolicyThreadState policy; const PathHistory *path;
            ~Restore() { leafStabilityMode = nullptr; restoreOocPolicyThreadState(policy); t_curPath = path; }
        } restore{previousPolicy, previousPath};
        leafStabilityMode = &mode;
        try {
            (void)runFullRunOOC(seed, 10000, ascension, false, true);
            report = stabilityReport("INVALID", "run_ended_before_scheduled_roots");
        } catch (const LeafStabilityComplete &completed) { report = completed.report; }
        catch (const std::exception &error) { report = stabilityReport("INVALID", error.what()); }
        catch (...) { report = stabilityReport("INVALID", "unexpected_nonstandard_stability_failure"); }
    } catch (const std::exception &error) {
        report["status"] = "INVALID"; report["reason"] = error.what();
    } catch (...) {
        report["status"] = "INVALID"; report["reason"] = "unexpected_nonstandard_stability_failure";
    }
    report["runSeed"] = seed;
    report["ascension"] = ascension;
    report["planSha256"] = mode.planSha256;
    try { if (liveLeafCapture) liveLeafCapture->stabilityProbe(report); }
    catch (const std::exception &error) {
        std::cerr << "ooc_leaf_stability INVALID capture_write_failed: " << error.what() << '\n';
        return 2;
    }
    std::cout << "ooc_leaf_stability " << report.at("status").get<std::string>()
        << " reason=" << report.at("reason").get<std::string>() << '\n';
    return report.at("status") == "STABILITY_MEASURED" ? 0 : 2;
}
int oocLeafReplayProbe(std::uint64_t seed, int ascension) {
    auto report = replayReport("INVALID", "startup_not_validated");
    report["runSeed"] = seed;
    report["ascension"] = ascension;
    try {
        if (leafReplayMode || leafStabilityMode) throw std::runtime_error("replay_probe_already_active");
        requireLeafProbeTeacher(ascension);
        const auto previousPolicy = captureOocPolicyThreadState();
        const auto *previousPath = t_curPath;
        LeafReplayMode mode{seed};
        struct Restore {
            OocPolicyThreadState policy; const PathHistory *path;
            ~Restore() { leafReplayMode = nullptr; restoreOocPolicyThreadState(policy); t_curPath = path; }
        } restore{previousPolicy, previousPath};
        leafReplayMode = &mode;
        try {
            // Direct call: no bestbench/OpenMP team, no root action after probe.
            (void)runFullRunOOC(seed, 10000, ascension, false, true);
            report = replayReport("NOT_REACHED", "run_ended_before_scheduled_root_leaf");
        } catch (const LeafReplayComplete &completed) { report = completed.report; }
    } catch (const std::exception &error) {
        report["status"] = "INVALID"; report["reason"] = error.what();
    } catch (...) {
        report["status"] = "INVALID"; report["reason"] = "unexpected_nonstandard_probe_failure";
    }
    report["runSeed"] = seed;
    report["ascension"] = ascension;
    try { if (liveLeafCapture) liveLeafCapture->replayProbe(report); }
    catch (const std::exception &error) {
        std::cerr << "ooc_leaf_replay INVALID capture_write_failed: " << error.what() << '\n';
        return 2;
    }
    std::cout << "ooc_leaf_replay " << report.at("status").get<std::string>()
        << " reason=" << report.at("reason").get<std::string>() << '\n';
    return report.at("status") == "PASS" ? 0 : report.at("status") == "FAIL" ? 1 : 2;
}
int oocLeafStabilitySelfTest() {
    try {
    using namespace sts::search;
    const auto require = [](bool ok, const char *why) {
        if (!ok) throw std::runtime_error(std::string("leaf stability selftest: ") + why);
    };
    const auto savedPolicy = captureOocPolicyThreadState();
    const auto *savedPath = t_curPath;
    struct Restore {
        OocPolicyThreadState policy; const PathHistory *path;
        ~Restore() { leafStabilityMode = nullptr; restoreOocPolicyThreadState(policy); t_curPath = path; }
    } restore{savedPolicy, savedPath};
    require(!leafReplayMode && !leafStabilityMode, "diagnostic modes initially off");
    struct Sampler final : CombatTransitionSampler {
        mutable unsigned calls = 0;
        bool unsupported = false;
        CombatRuntimeSupport support(const GameContext &, const CombatPredictorInputV1 &) const override {
            return {!unsupported, unsupported ? "unsupported_stability_fixture" : "supported"};
        }
        CombatRuntimeSample sample(const GameContext &gc, const CombatPredictorInputV1 &,
                std::mt19937_64 &rng) const override {
            ++calls;
            auto post = captureCombatTransitionState(gc);
            post.curHp -= 1 + rng() % 4;
            return {CombatRuntimeSample::Outcome::VICTORY, std::move(post)};
        }
    };
    GameContext gc{};
    gc.cc = sts::CharacterClass::IRONCLAD; gc.ascension = 20;
    gc.act = 1; gc.curHp = 70; gc.maxHp = 80;
    gc.screenState = sts::ScreenState::MAP_SCREEN;
    gc.curRoom = sts::Room::MONSTER; gc.info.encounter = sts::MonsterEncounter::CULTIST;
    gc.curMapNodeX = 0; gc.curMapNodeY = -1;
    gc.map = std::make_shared<sts::Map>();
    for (int y = 0; y < 15; ++y) for (int x = 0; x < 7; ++x) {
        auto &node = gc.map->nodes[y][x];
        node.x = x; node.y = y; node.room = sts::Room::MONSTER;
        node.edgeCount = y < 14 ? 1 : 0; node.edges[0] = x;
    }
    unsigned callbacks = 0, observations = 0;
    gc.regainControlAction = [&](GameContext &state) {
        ++callbacks; ++state.floorNum; state.screenState = sts::ScreenState::MAP_SCREEN;
    };
    OocMctsDependencies dependencies;
    dependencies.policyAvailable = [] { return true; };
    dependencies.policyLogits = [](const GameContext &, const PathHistory &, const std::vector<GameAction> &actions) {
        return std::vector<double>(actions.size(), 0);
    };
    dependencies.leafValue = [](const GameContext &state, const PathHistory &) { return state.curHp / 100.0; };
    dependencies.continuationStep = [](GameContext &state, PathHistory &, std::mt19937_64 &) {
        auto policy = captureOocPolicyThreadState(); ++policy.pathActionUses;
        restoreOocPolicyThreadState(policy);
        state.screenState = sts::ScreenState::BATTLE;
    };
    OocAdapterOptions options;
    options.checkpointLeaves = true; options.leafCombats = 3;
    options.leafCaptureStride = 1; options.leafCaptureLimit = 8;
    options.leafObserver = [&](const OocLeafObservation &) { ++observations; };
    // Tiny deterministic outer tree; every leaf uses the real adapter wrapper
    // and RNG-consuming three-combat continuation on a manually made MAP.
    struct Search final : OocGenerativeModel {
        OocGameContextModel adapter;
        std::vector<std::mt19937_64> streams;
        Search(const GameContext &gc, std::shared_ptr<Sampler> sampler, OocAdapterOptions options,
                OocMctsDependencies deps) : adapter(gc, {}, sampler, options, deps) {}
        std::optional<double> terminalValue(OocStateId) const override { return {}; }
        bool isLeafBoundary(OocStateId id) const override { return id != 0; }
        std::vector<OocPlannerAction> legalActions(OocStateId) const override { return {{1, .01}, {2, .99}}; }
        OocStateId sampleSuccessor(OocStateId, OocActionId action, std::mt19937_64 &rng) override {
            (void)rng(); streams.push_back(rng); return action;
        }
        double leafValue(OocStateId) const override { return adapter.leafValue(0); }
        double evaluateLeaf(OocStateId, std::mt19937_64 &rng) override {
            return evaluateLeafWithOutcome(0, rng).value;
        }
        OocLeafEvaluation evaluateLeafWithOutcome(OocStateId, std::mt19937_64 &rng) override {
            const auto value = adapter.evaluateLeafWithOutcome(0, rng);
            streams.push_back(rng); return value;
        }
    };
    LeafStabilityMode mode;
    // The planner visits both actions before PUCT. Four simulations cannot
    // reach a strict visit lock with two actions; six can stop at five.
    constexpr std::uint64_t syntheticBudget = 6;
    mode.seed = 19; mode.expectedSimulations = syntheticBudget;
    mode.childCpuStart = waitedChildCpuSeconds();
    for (std::uint64_t root = 0; root < 2; ++root) {
        StabilityLeaf selected{root, 1, 0, oocLeafCandidateInput(gc, {}), {}};
        for (std::size_t repeat = 0; repeat < 16; ++repeat) selected.repeatSeeds[repeat] = 100 + root * 16 + repeat;
        mode.schedule.push_back(std::move(selected));
    }
    std::vector<ReplayJson> progress;
    mode.progress = [&](ReplayJson row) { progress.push_back(std::move(row)); };
    ReplayJson completed;
    for (unsigned root = 0; root < 2; ++root) {
        OocMctsConfig config; config.seed = 1000 + root; config.allowUnqualifiedRootStop = true;
        const auto policyBefore = captureOocPolicyThreadState();
        const auto callbacksBefore = callbacks, observationsBefore = observations;
        auto plainSampler = std::make_shared<Sampler>();
        Search plain(gc, plainSampler, options, dependencies);
        const auto expected = OocMctsPlanner(config).search(plain, 0, syntheticBudget);
        const auto expectedPolicy = captureOocPolicyThreadState();
        const auto expectedCallbacks = callbacks, expectedObservations = observations;
        restoreOocPolicyThreadState(policyBefore);
        callbacks = callbacksBefore; observations = observationsBefore;
        auto measuredSampler = std::make_shared<Sampler>();
        Search measured(gc, measuredSampler, options, dependencies);
        mode.decisionIndex = root; mode.rootActive = true; leafStabilityMode = &mode;
        const auto actual = OocMctsPlanner(config).search(measured, 0, syntheticBudget);
        ReplayJson differences = ReplayJson::object();
        const auto compare = [&](const char *field, ReplayJson before, ReplayJson after) {
            if (before != after) differences[field] = {{"expected", std::move(before)}, {"actual", std::move(after)}};
        };
        compare("plainAborted", false, expected.aborted);
        compare("measuredAborted", false, actual.aborted);
        compare("selectedAction", expected.selectedAction ? ReplayJson(*expected.selectedAction) : ReplayJson(nullptr),
            actual.selectedAction ? ReplayJson(*actual.selectedAction) : ReplayJson(nullptr));
        compare("simulations", expected.metrics.simulations, actual.metrics.simulations);
        compare("transitionSamples", expected.metrics.transitionSamples, actual.metrics.transitionSamples);
        compare("leafEvaluations", expected.metrics.leafEvaluations, actual.metrics.leafEvaluations);
        compare("nonemptyEqualRngStreams", true, !plain.streams.empty() && plain.streams == measured.streams);
        compare("samplerCalls", plainSampler->calls, measuredSampler->calls);
        compare("combatSamples", plain.adapter.combatSamples(), measured.adapter.combatSamples());
        compare("projectionSteps", plain.adapter.continuationMetrics().projectionSteps,
            measured.adapter.continuationMetrics().projectionSteps);
        compare("callbacks", expectedCallbacks, callbacks);
        compare("observations", expectedObservations, observations);
        compare("pathActionUses", expectedPolicy.pathActionUses, captureOocPolicyThreadState().pathActionUses);
        if (!differences.empty()) throw std::runtime_error("leaf stability selftest root "
            + std::to_string(root) + " parent parity differences: " + differences.dump());
        if (!actual.metrics.earlyStopLockedRoot || actual.metrics.simulations == 0
                || actual.metrics.simulations >= syntheticBudget)
            throw std::runtime_error("leaf stability selftest expected strict visit lock: "
                + ReplayJson{{"completed", actual.metrics.simulations}, {"requested", syntheticBudget},
                    {"earlyStopLockedRoot", actual.metrics.earlyStopLockedRoot}}.dump());
        require(expected.rootActions.size() == actual.rootActions.size(), "same root action count");
        for (std::size_t i = 0; i < expected.rootActions.size(); ++i) {
            const auto &a = expected.rootActions[i], &b = actual.rootActions[i];
            require(a.id == b.id && a.prior == b.prior && a.visits == b.visits && a.q == b.q,
                "same action priors, visits and Q");
        }
        try { validateStabilityRoot(actual, measured.adapter); }
        catch (const LeafStabilityComplete &done) { completed = done.report; }
        require((root == 0 && completed.is_null()) || (root == 1 && completed.at("status") == "STABILITY_MEASURED"),
            "prefix continues between roots and stops after the final completed root");
        mode.rootActive = false; leafStabilityMode = nullptr;
    }
    require(progress.size() == 34 && mode.leaves.size() == 2 && mode.roots.size() == 2,
        "one control and sixteen repetitions at each selected leaf");
    std::set<std::string> streams;
    std::set<double> values;
    for (const auto &leaf : mode.leaves) {
        require(leaf.at("rootValidated") == true && leaf.at("controlComparison").at("status") == "PASS",
            "parent same-RNG control and final root validation");
        for (const auto &sample : leaf.at("repetitions")) {
            require(streams.insert(sample.at("initialRng").get<std::string>()).second, "distinct repeat streams");
            values.insert(sample.at("evaluation").at("value").get<double>());
        }
    }
    require(values.size() > 1, "independent samples exercise a nonconstant target");
    const auto rejects = [&](const std::function<void(LeafStabilityMode &)> &call, const char *reason) {
        LeafStabilityMode invalid;
        invalid.seed = 19; invalid.expectedSimulations = 4;
        invalid.childCpuStart = waitedChildCpuSeconds(); invalid.rootActive = true;
        invalid.schedule = {mode.schedule.front()};
        leafStabilityMode = &invalid;
        ReplayJson failure;
        try { call(invalid); }
        catch (const LeafStabilityComplete &done) { failure = done.report; }
        leafStabilityMode = nullptr;
        require(!failure.is_null() && failure.at("status") == "INVALID" && failure.at("reason") == reason,
            "scheduled failure is invalid without substitution or fallback");
    };
    rejects([&](LeafStabilityMode &) {
        auto wrong = gc; wrong.outcome = sts::GameOutcome::PLAYER_LOSS;
        OocGameContextModel model(wrong, {}, std::make_shared<Sampler>(), options, dependencies);
        std::mt19937_64 rng(1); model.evaluateLeafWithOutcome(0, rng);
    }, "scheduled_leaf_is_not_nonterminal_map");
    rejects([&](LeafStabilityMode &) {
        auto sampler = std::make_shared<Sampler>(); sampler->unsupported = true;
        OocGameContextModel model(gc, {}, sampler, options, dependencies);
        std::mt19937_64 rng(1); model.evaluateLeafWithOutcome(0, rng);
    }, "child_unsupported_or_invalid_evaluation");
    rejects([&](LeafStabilityMode &invalid) {
        invalid.childCpuStart -= 21;
        OocGameContextModel model(gc, {}, std::make_shared<Sampler>(), options, dependencies);
        std::mt19937_64 rng(1); model.evaluateLeafWithOutcome(0, rng);
    }, "cumulative_child_cpu_budget_exhausted");
    for (bool aborted : {false, true}) rejects([&](LeafStabilityMode &) {
        OocGameContextModel model(gc, {}, std::make_shared<Sampler>(), options, dependencies);
        OocMctsResult result; result.aborted = aborted; result.selectedAction = 1; result.metrics.simulations = 4;
        validateStabilityRoot(result, model);
    }, aborted ? "selected_root_search_aborted" : "scheduled_leaf_not_reached");
    std::cout << "ooc_leaf_stability_selftest PASS independent forks, parent search parity, root completion and failures\n";
    return 0;
    } catch (const LeafStabilityComplete &failure) {
        throw std::runtime_error("leaf stability selftest unexpected diagnostic stop: " + failure.report.dump());
    }
}
int oocLeafReplaySelfTest() {
    const auto require = [](bool ok, const char *why) {
        if (!ok) throw std::runtime_error(std::string("leaf replay selftest: ") + why);
    };
    const auto rejects = [&](const std::function<void()> &call, const char *why) {
        bool rejected = false;
        try { call(); } catch (const std::exception &) { rejected = true; }
        require(rejected, why);
    };
    const auto savedPolicy = captureOocPolicyThreadState();
    const auto *savedPath = t_curPath;
    struct Restore {
        OocPolicyThreadState policy; const PathHistory *path; LeafReplayMode *mode;
        ~Restore() { leafReplayMode = mode; restoreOocPolicyThreadState(policy); t_curPath = path; }
    } restore{savedPolicy, savedPath, leafReplayMode};
    require(!leafReplayMode, "diagnostic mode initially off");
    std::mt19937_64 stream(11);
    const auto expected = replayEvaluation(.625, "", false, {50, 80, 4}, 3, 6, stream, true);
    int childWrites = 0;
    const auto copied = forkLeafReplay([&] { ++childWrites; return expected; });
    require(childWrites == 0 && copied == expected, "fork isolates mutations and transports exact result");
    require(compareReplay(expected, copied).at("status") == "PASS", "exact comparator pass");
    for (const char *key : {"value", "terminal", "endpoint", "actualCombats", "projectionSteps", "finalRng"}) {
        auto altered = expected;
        if (std::string(key) == "value") altered[key] = .626;
        else if (std::string(key) == "terminal") altered[key] = true;
        else if (std::string(key) == "endpoint") altered[key]["hp"] = 49;
        else if (std::string(key) == "finalRng") altered[key] = "different";
        else altered[key] = 99;
        require(compareReplay(expected, altered).at("status") == "FAIL", "comparator catches changed field");
    }
    auto unsupported = expected; unsupported["value"] = nullptr; unsupported["error"] = "unsupported_fixture";
    require(compareReplay(expected, unsupported).at("status") == "INVALID", "unsupported is not an ordinary fallback");
    auto mutated = expected; mutated["sourceUnchanged"] = false;
    require(compareReplay(mutated, mutated).at("status") == "INVALID", "source mutation invalidates replay custody");
    rejects([&] { forkLeafReplay([] { return ReplayJson{{"large", std::string(leafReplayByteLimit + 1, 'x')}}; }); },
        "oversize child output rejected");
    rejects([&] { forkLeafReplay([]() -> ReplayJson { _exit(0); }); }, "empty child output rejected");
    rejects([&] { forkLeafReplay([]() -> ReplayJson { for (;;) pause(); }, 20); }, "child wall timeout enforced");
    const int nullFd = open("/dev/null", O_WRONLY);
    require(nullFd >= 0, "open descriptor fixture");
    const int inherited = fcntl(nullFd, F_DUPFD, 100);
    close(nullFd);
    require(inherited >= 100, "reserve inherited descriptor fixture");
    const auto fdResult = forkLeafReplay([&] {
        errno = 0;
        const bool closed = write(inherited, "x", 1) == -1 && errno == EBADF;
        return ReplayJson{{"closed", closed}};
    });
    close(inherited);
    require(fdResult.at("closed") == true, "child closes inherited output descriptors");

    // A directly constructed MAP family with genuine adapter continuation,
    // RNG-consuming combat samples, callback writes and a nonconstant target.
    // There is no generated game/run or model qualification in this fixture.
    struct ReplaySampler final : CombatTransitionSampler {
        mutable unsigned calls = 0;
        CombatRuntimeSupport support(const GameContext &, const CombatPredictorInputV1 &) const override {
            return {true, "supported"};
        }
        CombatRuntimeSample sample(const GameContext &gc, const CombatPredictorInputV1 &,
                std::mt19937_64 &rng) const override {
            ++calls;
            auto post = captureCombatTransitionState(gc);
            post.curHp -= 1 + rng() % 4;
            return {CombatRuntimeSample::Outcome::VICTORY, std::move(post)};
        }
    };
    GameContext gc{};
    gc.seed = 0; gc.cc = sts::CharacterClass::IRONCLAD;
    gc.ascension = 20; gc.curHp = 70; gc.maxHp = 80;
    gc.screenState = sts::ScreenState::MAP_SCREEN;
    gc.curRoom = sts::Room::MONSTER;
    gc.info.encounter = sts::MonsterEncounter::CULTIST;
    gc.keysEnabled = false; gc.restRoomResolved = true;
    unsigned callbacks = 0;
    gc.regainControlAction = [&](GameContext &state) {
        ++callbacks; ++state.floorNum; state.screenState = sts::ScreenState::MAP_SCREEN;
    };
    OocMctsDependencies deps;
    deps.policyAvailable = [] { return true; };
    deps.policyLogits = [](const GameContext &, const PathHistory &, const std::vector<GameAction> &actions) {
        return std::vector<double>(actions.size(), 0);
    };
    deps.leafValue = [](const GameContext &state, const PathHistory &) { return state.curHp / 100.0; };
    deps.continuationStep = [](GameContext &state, PathHistory &, std::mt19937_64 &) {
        auto policy = captureOocPolicyThreadState(); ++policy.pathActionUses;
        restoreOocPolicyThreadState(policy);
        state.screenState = sts::ScreenState::BATTLE;
    };
    OocAdapterOptions options;
    options.checkpointLeaves = true; options.leafCombats = 3;
    options.leafCaptureStride = 512; options.leafCaptureLimit = 8;
    unsigned observations = 0;
    options.leafObserver = [&](const OocLeafObservation &) { ++observations; };
    auto sampler = std::make_shared<ReplaySampler>();
    OocGameContextModel model(gc, PathHistory{}, sampler, options, deps);
    for (unsigned i = 0; i < 1024; ++i) model.evaluateLeafWithOutcome(0, stream);
    const auto parentCalls = sampler->calls;
    const auto parentCallbacks = callbacks;
    const auto parentPolicy = captureOocPolicyThreadState();
    LeafReplayMode mode{0, true}; leafReplayMode = &mode;
    ReplayJson report;
    try { model.evaluateLeafWithOutcome(0, stream); }
    catch (const LeafReplayComplete &complete) { report = complete.report; }
    leafReplayMode = nullptr;
    require(report.value("status", "") == "PASS" && report.at("ordinal") == 1025
            && report.at("stateId") == 0 && report.at("parent").at("value") != .5
            && report.at("parent").at("actualCombats") == 3
            && report.at("parent").at("projectionSteps") == 6
            && report.at("parent").at("finalRng") == replayRngString(stream),
        "actual wrapper replays selected MAP nonconstant target and final RNG");
    require(sampler->calls == parentCalls + 3 && callbacks == parentCallbacks + 3
            && captureOocPolicyThreadState().pathActionUses == parentPolicy.pathActionUses + 3
            && model.leafCalls() == 1025 && model.leafObservationCount() == 3 && observations == 2
            && report.at("keysEnabled") == false && report.at("restRoomResolved") == true,
        "child changes do not enter parent sampler, callback, policy or observation counters");
    std::cout << "ooc_leaf_replay_selftest PASS transport bounds, isolation, exact comparator, MAP target\n";
    return 0;
}
namespace {
// Policy-target capture (heartoutcomegen policy): the real driver arms one root;
// oocMctsPolicyStep hands that root's summary slot to selectOocMctsAction.
thread_local bool t_policyTargetArmed = false;
thread_local nlohmann::json *t_policyTargetRoot = nullptr;
thread_local nlohmann::json t_policyTargetRow;
}
void armOocPolicyTarget() { t_policyTargetArmed = true; t_policyTargetRow = nullptr; }
nlohmann::json takeOocPolicyTarget() {
    t_policyTargetArmed = false;
    return std::exchange(t_policyTargetRow, nullptr);
}
sts::search::OocMctsResult selectOocMctsAction(const GameContext &gc, const PathHistory &path,
    std::uint64_t seed, std::uint64_t index, std::uint64_t simulations,
    std::shared_ptr<const CombatTransitionSampler> sampler, std::uint64_t &samples,
    OocContinuationMetrics *continuation, std::optional<OocGameContextModel::Candidate> *selected,
    nlohmann::json *rootActions) {
    nlohmann::json *const policyRoot = std::exchange(t_policyTargetRoot, nullptr);
    const double cpuStart = liveOptions.cpuBudgetSeconds > 0 ? threadCpuSeconds() : 0;
    ImaginedScope scope;
    struct ReplayRootScope {
        bool active = false;
        ~ReplayRootScope() { if (active) leafReplayMode->rootActive = false; }
    } replayRoot;
    struct StabilityRootScope {
        bool active = false;
        ~StabilityRootScope() { if (active) leafStabilityMode->rootActive = false; }
    } stabilityRoot;
    if (leafStabilityMode) {
        if (leafStabilityMode->rootActive) failStability("nested_stability_root");
        if (seed != leafStabilityMode->seed || index != leafStabilityMode->roots.size()
                || index > leafStabilityMode->schedule.back().decisionIndex)
            failStability("scheduled_root_not_reached");
        leafStabilityMode->decisionIndex = index;
        leafStabilityMode->rootActive = true;
        stabilityRoot.active = true;
    }
    if (leafReplayMode) {
        if (index != 0 || seed != leafReplayMode->seed)
            throw LeafReplayComplete{replayReport("NOT_REACHED", "first_decision_root_not_searched")};
        if (leafReplayMode->rootActive)
            throw LeafReplayComplete{replayReport("INVALID", "nested_replay_root")};
        leafReplayMode->rootActive = true;
        replayRoot.active = true;
    }
    auto config = liveConfig;
    if (liveOptions.cpuBudgetSeconds > 0) {
        const double deadline = cpuStart + liveOptions.cpuBudgetSeconds;
        config.budgetExhausted = [deadline] { return threadCpuSeconds() >= deadline; };
    }
    config.seed = oocMctsSearchSeed(seed, index);
    auto options = liveOptions;
    auto capture = liveLeafCapture ? liveLeafCapture->begin(seed, index, config.seed,
        simulations, options.leafCombats) : nullptr;
    if (capture) {
        options.leafCaptureStride = capture->row.at("stride").get<std::uint64_t>();
        options.leafCaptureLimit = OocLeafCaptureSink::leavesPerRoot;
        options.leafObserver = [capture](const OocLeafObservation &observation) { capture->observe(observation); };
    }
    if (liveSibling && index % liveSibling->every == 0) {
        auto sibling = std::make_shared<OocSiblingLeafCapture>();
        const auto out = liveSibling->out;
        sibling->write = [out](const nlohmann::json &row) {
            *out << row.dump() << '\n';
            out->flush();
            if (!*out) throw std::runtime_error("STS_OOC_SIBLING_CAPTURE write failed");
        };
        if (one_combat::heart1::enabled())
            sibling->annotate = [](const GameContext &leaf) { return one_combat::heart1::leafAnnotation(leaf); };
        sibling->runSeed = seed; sibling->decisionIndex = index; sibling->searchSeed = config.seed;
        sibling->repeats = liveSibling->repeats; sibling->longRepeats = liveSibling->longRepeats;
        sibling->maxDepth = liveSibling->maxDepth; sibling->maxLeaves = liveSibling->maxLeaves;
        options.siblingCapture = std::move(sibling);
    }
    if (!options.priorTracePath.empty()) {
        options.priorTraceRunSeed = seed;
        options.priorTraceDecisionIndex = index;
        options.priorTraceSearchSeed = config.seed;
    }
    OocGameContextModel model(gc, path, std::move(sampler), std::move(options));
    samples = 0;
    if (selected) selected->reset();
    if (model.terminalValue(0) || model.isLeafBoundary(0)) {
        if (leafStabilityMode) failStability("scheduled_root_is_terminal_or_boundary");
        if (leafReplayMode)
            throw LeafReplayComplete{replayReport("NOT_REACHED", "decision0_not_searchable")};
        if (capture) liveLeafCapture->finish(*capture, {}, model);
        return {};
    }
    const bool graphCapture = !liveGraphPath.empty() && index == liveGraphDecisionIndex;
    const bool reuseObserved = !liveReuseTrace.empty();
    config.captureTree = graphCapture || reuseObserved;
    if (reuseObserved) config.treeNodeCap = 100000;
    if (!simulations) throw std::invalid_argument("OOC MCTS requires simulations > 0");
    const auto sole = model.soleLegalAction(0);
    if (!runProfilePath().empty()) {
        config.profileSearch = true;
        // Preserve the singleton shortcut and every existing stopping rule.
        if (!sole) {
            for (const std::uint64_t checkpoint : {128, 256, 512, 1024, 2048, 4096})
                if (checkpoint <= simulations) config.rootCheckpointSimulations.push_back(checkpoint);
        }
    }
    // Checkpoints only read root statistics; the singleton shortcut stays.
    if (policyRoot && !sole && config.rootCheckpointSimulations.empty())
        for (const std::uint64_t checkpoint : {128, 256, 512, 1024, 2048, 4096})
            if (checkpoint <= simulations) config.rootCheckpointSimulations.push_back(checkpoint);
    nlohmann::json reuseRow;
    if (reuseObserved) {
        if (t_reuseIndex.seed != seed || t_reuseIndex.decision >= index) t_reuseIndex = {};
        const auto &prior = t_reuseIndex;
        reuseRow = {{"schemaVersion", 1}, {"seed", seed}, {"decisionIndex", index},
            {"floor", gc.floorNum}, {"act", gc.act}, {"screen", int(gc.screenState)}, {"singleton", sole.has_value()},
            {"previousSearch", prior.valid}};
        if (prior.valid) {
            reuseRow["previous"] = {{"decisionIndex", prior.decision}, {"decisionGap", index - prior.decision},
                {"floor", prior.floor}, {"screen", prior.screen}, {"simulations", prior.simulations},
                {"storedDecisionNodes", prior.storedDecisionNodes}, {"truncated", prior.truncated}};
            reuseRow["rng"] = reuseMatchJson(prior, prior.rng, reusePublicFingerprint(gc, path, true));
            reuseRow["public"] = reuseMatchJson(prior, prior.publicState, reusePublicFingerprint(gc, path, false));
        }
    }
    std::optional<OocDecisionLog> decisionLog;
    if (!decisionLogPath.empty()) decisionLog.emplace();
    struct DecisionLogScope {
        explicit DecisionLogScope(OocDecisionLog *log) { t_decisionLog = log; }
        ~DecisionLogScope() { t_decisionLog = nullptr; }
    };
    auto result = [&] {
        DecisionLogScope logScope(decisionLog ? &*decisionLog : nullptr);
        return searchWithSoleRootShortcut(model, config, sole, simulations);
    }();
    if (leafReplayMode) {
        auto report = result.aborted ? replayReport("INVALID", "decision0_search_aborted")
            : replayReport("NOT_REACHED", "decision0_search_finished_before_scheduled_leaf");
        report["leafCalls"] = model.leafCalls();
        report["completedSimulations"] = result.metrics.simulations;
        report["rootAborted"] = result.aborted;
        report["abortReason"] = result.abortReason;
        throw LeafReplayComplete{std::move(report)};
    }
    if (capture) liveLeafCapture->finish(*capture, result, model);
    if (decisionLog) {
        nlohmann::json candidates = nlohmann::json::array();
        for (const auto &action : result.rootActions) {
            const auto &c = model.candidate(0, action.id);
            candidates.push_back({{"label", candidateLabel(gc, c)}, {"prior", action.prior},
                {"visits", action.visits}, {"q", action.q},
                {"selected", result.selectedAction && *result.selectedAction == action.id}});
        }
        if (sole) {   // the singleton bypass runs no search and reports no visits
            candidates = nlohmann::json::array({{{"label", candidateLabel(gc, model.candidate(0, *sole))},
                {"prior", 1.0}, {"visits", 0}, {"selected", true}}});
        }
        const auto &m = result.metrics;
        nlohmann::json counts = nlohmann::json::object();
        for (const auto &[section, keys] : decisionLog->counts) counts[section] = keys;
        const nlohmann::json row = {{"schema", 1}, {"seed", seed}, {"decisionIndex", index},
            {"act", gc.act}, {"floor", gc.floorNum}, {"screen", logScreen(gc)},
            {"hp", gc.curHp}, {"maxHp", gc.maxHp}, {"gold", gc.gold},
            {"singletonBypass", sole.has_value()}, {"aborted", result.aborted}, {"abortReason", result.abortReason},
            {"requestedSimulations", simulations}, {"completedSimulations", m.simulations},
            {"earlyStopLock", m.earlyStopLockedRoot}, {"maxTreeDepth", m.maxDepthReached}, {"depthSum", m.depthSum},
            {"decisionNodes", m.decisionNodes}, {"transitionSamples", m.transitionSamples},
            {"leafEvaluations", m.leafEvaluations},
            {"selected", result.selectedAction ? candidateLabel(gc, model.candidate(0, *result.selectedAction)) : ""},
            {"rootCandidates", candidates}, {"counts", counts}, {"sampleRollouts", decisionLog->sampleRollouts}};
        std::lock_guard<std::mutex> lock(liveTraceMutex);
        std::ofstream out(decisionLogPath, std::ios::app);
        if (!out || !(out << row.dump() << '\n'))
            throw std::runtime_error("STS_OOC_MCTS_DECISION_LOG write failed");
    }
    if (reuseObserved) {
        reuseRow["searched"] = !result.metrics.trivialRootBypasses;
        reuseRow["aborted"] = result.aborted;
        reuseRow["simulations"] = result.metrics.simulations;
        std::lock_guard<std::mutex> lock(liveTraceMutex);
        std::ofstream out(liveReuseTrace, std::ios::app);
        if (!out || !(out << reuseRow.dump() << '\n'))
            throw std::runtime_error("STS_OOC_MCTS_REUSE_TRACE write failed");
    }
    // A singleton bypass executes without a tree; retain the earlier index so
    // forced chains are measured against the last real search.
    if (reuseObserved && !result.metrics.trivialRootBypasses) {
        if (result.tree && result.selectedAction) {
            t_reuseIndex = buildReuseIndex(model, *result.tree);
            t_reuseIndex.valid = true;
            t_reuseIndex.selected = *result.selectedAction;
            t_reuseIndex.simulations = result.metrics.simulations;
            t_reuseIndex.floor = gc.floorNum;
            t_reuseIndex.screen = int(gc.screenState);
        } else t_reuseIndex = {};
        t_reuseIndex.seed = seed;
        t_reuseIndex.decision = index;
    }
    if (graphCapture) {
        if (result.tree) {
            annotateOocTree(model, *result.tree);
            for (auto &node : result.tree->nodes)
                node.selected = node.chance && node.depth == 0
                    && result.selectedAction && node.action == *result.selectedAction;
        }
        nlohmann::json captured = {{"accepted", result.tree.has_value()}, {"rootId", 0},
            {"truncated", result.tree && result.tree->truncated},
            {"nodes", nlohmann::json::array()}, {"edges", nlohmann::json::array()}};
        if (result.tree) {
            for (const auto &node : result.tree->nodes) {
                captured["nodes"].push_back({{"id", node.id}, {"kind", node.chance ? "chance" : "state"},
                    {"stateId", std::to_string(node.state)}, {"actionId", node.action},
                    {"label", node.label}, {"key", node.key}, {"outcome", node.outcome},
                    {"screen", node.screen}, {"room", node.room}, {"floor", node.floor},
                    {"mapX", node.mapX}, {"mapY", node.mapY}, {"hp", node.hp},
                    {"maxHp", node.maxHp}, {"gold", node.gold}, {"selected", node.selected}, {"depth", node.depth},
                    {"visits", node.visits}, {"prior", node.chance ? nlohmann::json(node.prior) : nlohmann::json(nullptr)},
                    {"q", node.chance && node.visits ? nlohmann::json(node.q) : nlohmann::json(nullptr)}});
            }
            for (const auto &edge : result.tree->edges)
                captured["edges"].push_back({{"parentId", edge.parentId},
                    {"childId", edge.childId ? nlohmann::json(*edge.childId) : nlohmann::json(nullptr)},
                    {"visits", edge.visits}, {"kind", edge.particle ? "particle" : "action"},
                    {"combatModelUsed", edge.combatModelUsed},
                    {"combatEncounter", edge.combatEncounter}, {"combatOutcome", edge.combatOutcome}});
        }
        nlohmann::json actions = nlohmann::json::array();
        for (const auto &action : result.rootActions)
            actions.push_back({{"semanticKey", model.candidate(0, action.id).key},
                {"visits", action.visits}, {"q", action.q}, {"prior", action.prior}});
        const nlohmann::json capture = {{"source", "native_sts_lightspeed_search"},
            {"seed", seed}, {"decisionIndex", index}, {"searchSeed", config.seed},
            {"floor", gc.floorNum}, {"screen", int(gc.screenState)},
            {"hp", gc.curHp}, {"maxHp", gc.maxHp},
            {"requestedSimulations", simulations}, {"completedSimulations", result.metrics.simulations},
            {"aborted", result.aborted}, {"abortReason", result.abortReason},
            {"selectedSemanticKey", result.selectedAction ? model.candidate(0, *result.selectedAction).key : ""},
            {"candidateSummaries", actions}, {"tree", captured}};
        std::ofstream out(liveGraphPath, std::ios::trunc);
        if (!out || !(out << capture.dump(2) << '\n'))
            throw std::runtime_error("STS_OOC_MCTS_GRAPH_FILE write failed");
    }
    if (!result.selectedAction && !result.aborted) throw std::runtime_error("live OOC MCTS missing selected root action");
    if (selected && result.selectedAction) *selected = model.candidate(0, *result.selectedAction);
    if (policyRoot) {
        using nlohmann::json;
        const auto actionsJson = [&](const std::vector<sts::search::OocRootActionStats> &actions) {
            auto output = json::array();
            for (const auto &a : actions) {
                const auto &c = model.candidate(0, a.id);
                output.push_back({{"id", a.id}, {"key", c.key}, {"bits", c.primitive.bits},
                    {"semantic", c.semantic.has_value()},
                    {"compound", c.compoundSelector != sts::CardSelectScreenType::INVALID},
                    {"prior", a.prior}, {"visits", a.visits}, {"q", a.q}});
            }
            return output;
        };
        auto checkpoints = json::array();   // keys and priors are on the candidates
        for (const auto &c : result.rootCheckpoints) {
            auto actions = json::array();
            for (const auto &a : c.actions) actions.push_back({{"id", a.id}, {"visits", a.visits}, {"q", a.q}});
            checkpoints.push_back({{"simulations", c.simulations}, {"actions", actions}});
        }
        // Root value estimate for completing unvisited actions offline (rollout3 has no value net).
        double visitedQ = 0;
        std::uint64_t rootVisits = 0, maxVisits = 0;
        for (const auto &a : result.rootActions) {
            visitedQ += double(a.visits) * a.q;
            rootVisits += a.visits;
            maxVisits = std::max<std::uint64_t>(maxVisits, a.visits);
        }
        const auto &m = result.metrics;
        *policyRoot = {{"searchSeed", config.seed}, {"requestedSimulations", simulations},
            {"rootVisits", rootVisits}, {"maxVisits", maxVisits},
            {"rootMeanQ", rootVisits ? json(visitedQ / double(rootVisits)) : json(nullptr)},
            {"completedSimulations", m.simulations}, {"attempts", m.simulationAttempts},
            {"singleton", sole.has_value()}, {"aborted", result.aborted}, {"abortReason", result.abortReason},
            {"earlyStopLock", m.earlyStopLockedRoot}, {"earlyStopGap20", m.earlyStopVisitGap20},
            {"earlyStopBudget", m.earlyStopBudget}, {"savedSimulations", m.savedSimulations},
            {"selectionRule", config.selectByMeanQ ? "q_visits_id" : "visits_q_id"},
            {"selectedId", result.selectedAction ? json(*result.selectedAction) : json(nullptr)},
            {"candidates", actionsJson(result.rootActions)}, {"checkpoints", checkpoints}};
    }
    if (rootActions) {
        *rootActions = nlohmann::json::array();
        for (const auto &action : result.rootActions)
            rootActions->push_back({{"id", action.id}, {"key", model.candidate(0, action.id).key},
                {"prior", action.prior}, {"visits", action.visits}, {"q", action.q}});
    }
    if (config.observeRootLock) {
        const auto &m = result.metrics;
        const bool completed = !result.aborted && m.simulations == simulations;
        if (completed && result.hypotheticalLockedAction
            && result.hypotheticalLockedAction != result.selectedAction)
            throw std::runtime_error("OOC hypothetical lock disagrees with full-budget winner");
        const nlohmann::json row = {
            {"seed",seed},{"decisionIndex",index},{"floor",gc.floorNum},{"screen",int(gc.screenState)},
            {"requestedSimulations",simulations},{"completedSimulations",m.simulations},
            {"simulationAttempts",m.simulationAttempts},{"fullBudgetCompleted",completed},
            {"aborted",result.aborted},{"abortReason",result.abortReason},
            {"hypotheticalLockSimulation",m.hypotheticalLockSimulation},
            {"hypotheticalRemainingSimulations",m.hypotheticalRemainingSimulations},
            {"hypotheticalTailWallSeconds",m.hypotheticalTailWallSeconds},
            {"hypotheticalLockedAction",result.hypotheticalLockedAction
                ? nlohmann::json(*result.hypotheticalLockedAction) : nlohmann::json(nullptr)},
            {"selectedKey",result.selectedAction ? model.candidate(0,*result.selectedAction).key : ""},
            {"selectedAction",result.selectedAction ? nlohmann::json(*result.selectedAction) : nlohmann::json(nullptr)},
            {"searchGuaranteedNonAborting",model.searchGuaranteedNonAborting()},
            {"earlyStopLockedRoot",m.earlyStopLockedRoot},{"savedSimulations",m.savedSimulations}};
        std::lock_guard<std::mutex> lock(liveTraceMutex);
        std::ofstream out(liveRootLockTrace,std::ios::app);
        if (!out || !(out << row.dump() << '\n'))
            throw std::runtime_error("STS_OOC_MCTS_ROOT_LOCK_TRACE write failed");
    }
    samples = model.combatSamples();
    if (continuation) {
        *continuation = model.continuationMetrics();
        recordSearchAbort(result,*continuation);
    }
    if (leafStabilityMode) validateStabilityRoot(result, model);
    return result;
}
#ifndef STS_LIVE_ADVISOR
nlohmann::json liveRootLeafTails(const GameContext &gc, const PathHistory &path, const OocPolicyThreadState &policy,
    std::uint64_t salt, unsigned repeats) {
    if (!liveEnabled) throw std::runtime_error("liveRootLeafTails requires STS_OOC_MCTS=1");
    // The end-state hook sits on the native leaf dependency; every other leaf skips it.
    if (liveOptions.screenLeaf || liveOptions.bossLeaf || liveOptions.bossRollout || liveOptions.constantLeaf
            || liveOptions.directLeaf || liveOptions.leafWinNet || liveOptions.heartLeaf || liveOptions.rolloutStudent
            || !liveOptions.leafCombats)
        throw std::runtime_error("liveRootLeafTails requires the native rollout leaf (STS_OOC_MCTS_LEAF_VALUE=native)");
    static const CompactTreeNet anchor = [] {
        CompactTreeNet net;
        if (fileSha256Hex(kHeartLeafAnchorPath) != kHeartLeafAnchorSha256
                || !net.load(kHeartLeafAnchorPath, richIdxMap(), "HeartLeaf tail anchor") || !net.logistic)
            throw std::runtime_error("liveRootLeafTails cannot load the pinned public X2-B");
        return net;
    }();
    ImaginedScope scope;
    restoreOocPolicyThreadState(policy);
    auto deps = defaultOocMctsDependencies();
    const auto nativeLeaf = deps.leafValue;
    std::optional<nlohmann::json> end;
    deps.leafValue = [&](const GameContext &state, const PathHistory &at) {
        const double value = nativeLeaf(state, at);
        auto raw = richFeatureVec(state, at);
        const double margin = anchor.margin(raw);
        appendHeartLeafExtras(raw, state, margin);
        nlohmann::json idx = nlohmann::json::array(), val = nlohmann::json::array();
        for (std::size_t i = 0; i < raw.size(); ++i) if (raw[i] != 0) { idx.push_back(i); val.push_back(raw[i]); }
        end = nlohmann::json{{"x2b", value}, {"floor", state.floorNum}, {"act", state.act},
            {"screen", int(state.screenState)}, {"i", std::move(idx)}, {"v", std::move(val)}};
        return value;
    };
    auto options = liveOptions;
    options.siblingCapture.reset();
    options.leafObserver = {};
    options.priorTracePath.clear();
    OocGameContextModel model(gc, path, liveSamplerFor(gc), std::move(options), std::move(deps));
    if (model.terminalValue(0)) throw std::runtime_error("liveRootLeafTails root is terminal");
    nlohmann::json rows = nlohmann::json::array();
    for (unsigned r = 0; r < repeats; ++r) {
        restoreOocPolicyThreadState(policy);
        end.reset();
        std::seed_seq seq{salt, std::uint64_t(r)};
        std::mt19937_64 stream(seq);
        try {
            const auto e = model.evaluateLeafWithOutcome(0, stream);
            nlohmann::json row = {{"value", e.value}, {"terminal", e.terminal}, {"endFloor", e.endpoint ? e.endpoint->floor : -1}};
            if (!e.terminal) {
                if (!end) throw std::runtime_error("non-terminal rollout end bypassed the native leaf");
                if (std::abs(end->at("x2b").get<double>() - e.value) > 1e-12)
                    throw std::runtime_error("rollout end value is not the native leaf value");
                row["end"] = std::move(*end);
            }
            rows.push_back(std::move(row));
        } catch (const sts::search::OocSearchUnsupported &u) {
            rows.push_back({{"error", u.what()}});
        }
    }
    restoreOocPolicyThreadState(policy);
    return rows;
}
#endif
nlohmann::json scoreLiveOocMctsDecision(const GameContext &gc, const PathHistory &path,
    std::uint64_t runSeed, std::uint64_t decisionIndex) {
    if (!liveEnabled) throw std::runtime_error("scoreLiveOocMctsDecision requires STS_OOC_MCTS=1");
    const auto wallStart = std::chrono::steady_clock::now();
    std::uint64_t samples = 0;
    OocContinuationMetrics continuation;
    std::optional<OocGameContextModel::Candidate> selected;
    const auto result = selectOocMctsAction(gc, path, runSeed, decisionIndex, liveSimulations, liveSamplerFor(gc),
                                            samples, &continuation, &selected);
    const double wall = std::chrono::duration<double>(std::chrono::steady_clock::now() - wallStart).count();
    nlohmann::json actions = nlohmann::json::array();
    if (!result.rootActions.empty()) {
        // Candidate identities are deterministic per state; a fresh model only enumerates them.
        ImaginedScope scope;
        OocGameContextModel names(gc, path, liveSamplerFor(gc), liveOptions);
        for (const auto &a : result.rootActions) {
            const auto &c = names.candidate(0, a.id);
            actions.push_back({{"id", a.id}, {"key", c.key}, {"bits", c.primitive.bits},
                {"prior", a.prior}, {"visits", a.visits}, {"q", a.q}});
        }
    }
    return {{"searchSeed", oocMctsSearchSeed(runSeed, decisionIndex)}, {"aborted", result.aborted},
        {"abortReason", result.abortReason}, {"selected", selected.has_value()},
        {"selectedKey", selected ? selected->key : ""},
        {"selectedBits", selected ? nlohmann::json(selected->primitive.bits) : nlohmann::json(nullptr)},
        {"simulations", result.metrics.simulations}, {"singletonBypass", result.metrics.trivialRootBypasses},
        {"earlyStopLock", result.metrics.earlyStopLockedRoot}, {"ctmSamples", samples},
        {"wallSeconds", wall}, {"rootActions", actions}};
}
bool oocHypotheticalCardTaken(const GameContext &gc, const PathHistory &path, const sts::Card &card,
    const std::function<void(GameContext &)> &step) {
    ImaginedScope scope;
    auto offer = detachedCopy(gc);
    sts::CardReward reward;
    reward.push_back(card);
    offer.info.rewardsContainer = sts::Rewards();
    offer.info.rewardsContainer.addCardReward(reward);
    offer.screenState = sts::ScreenState::REWARDS;
    offer.regainControlAction = [](GameContext &g) {
        g.screenState = sts::ScreenState::MAP_SCREEN;
        g.regainControlAction = nullptr;
    };
    const auto before = offer.deck.size();
    PathHistory offerPath = path;
    t_curPath = &offerPath;
    // The offer is a detached copy valued by the caller's real policy step, so
    // a combat-playing oracle (act-fight probe, boss draft) may fight on it.
    // Inside an imagined continuation the outer prohibition still holds.
    sts::search::g_disallowImaginedCombat = scope.disallowed;
    step(offer);
    return offer.deck.size() > before;
}
bool oocMctsPolicyStep(GameContext &gc, const PathHistory &path, std::uint64_t seed,
    std::uint64_t index, LiveOocMctsMetrics &metrics) {
    if (leafStabilityMode && (index != leafStabilityMode->roots.size()
            || index > leafStabilityMode->schedule.back().decisionIndex))
        failStability("scheduled_root_bypassed_mcts");
    if (leafReplayMode && index != 0)
        throw LeafReplayComplete{replayReport("NOT_REACHED", "decision0_bypassed_mcts")};
    const bool policyTarget = std::exchange(t_policyTargetArmed, false);
    ++metrics.decisions;
    if (!liveEnabled) {
        if (leafStabilityMode) failStability("mcts_disabled_during_stability_probe");
        if (leafReplayMode) throw LeafReplayComplete{replayReport("INVALID", "mcts_disabled_during_probe")};
        return false;
    }
    const auto wallStart = std::chrono::steady_clock::now();
    const double cpuStart = threadCpuSeconds();
    std::uint64_t samples = 0;
    OocContinuationMetrics continuation;
    OocProfileScope profile(OocProfileBucket::Mcts);
    if (sts::search::g_onGameActionExecute && gc.screenState != sts::ScreenState::MAP_SCREEN) {
        if (leafStabilityMode) failStability("semantic_observer_blocks_scheduled_root");
        if (leafReplayMode)
            throw LeafReplayComplete{replayReport("NOT_REACHED", "semantic_observer_blocks_decision0")};
        ++metrics.fallback; ++metrics.continuation.supportReasons["semantic_observer_active"]; return false;
    }
    collectForcedRewardGold(gc);
    // Policy targets record the state the search sees (after forced gold).
    nlohmann::json policyRoot, policyRow;
    std::optional<heart1::Choice> policyChoice;
    struct PolicyRootScope { ~PolicyRootScope() { t_policyTargetRoot = nullptr; } } policyRootScope;
    if (policyTarget) {
        heart1::Choice choice;
        std::string reason;
        const bool encoded = heart1::buildChoice(gc, choice, &reason) && choice.record.choiceCount() > 0;
        policyRow = {{"type", "decision"}, {"decisionIndex", index}, {"act", gc.act}, {"floor", gc.floorNum},
            {"screen", int(gc.screenState)}, {"searchSeed", oocMctsSearchSeed(seed, index)},
            {"heart1Record", encoded ? heart1::recordToJson(choice.record) : nlohmann::json(nullptr)}};
        if (encoded) {
            policyRow["heart1Tokens"] = choice.actions.size();
            policyChoice = std::move(choice);
        } else {
            policyRow["heart1Reason"] = reason.empty() ? "no_choice" : reason;
        }
        t_policyTargetRoot = &policyRoot;
    }
    std::optional<OocGameContextModel::Candidate> selected;
    nlohmann::json rootRow;
    if (!liveRootTrace.empty()) {
        // Taken before search and execution: the exact root state. Failures are
        // recorded, never thrown, so the observer cannot change the run.
        rootRow = {{"schema", "ooc-root-trace-v1"}, {"seed", seed}, {"decisionIndex", index},
            {"searchSeed", oocMctsSearchSeed(seed, index)}, {"act", gc.act}, {"floor", gc.floorNum},
            {"screen", int(gc.screenState)}, {"selector", int(gc.info.selectScreenType)}};
        try { rootRow["snapshot"] = screen_leaf::snapshotJson(gc, path); }
        catch (const std::exception &error) { rootRow["snapshot"] = nullptr; rootRow["snapshotError"] = error.what(); }
        nlohmann::json record;
        std::string reason;
        if (heart1::buildPublicLeafRecord(gc, record, &reason)) rootRow["record"] = std::move(record);
        else rootRow["recordError"] = reason.empty() ? "unencoded_screen" : reason;
    }
    nlohmann::json rootActions = nlohmann::json::array();
    const auto result = [&] {
        try {
            return selectOocMctsAction(gc, path, seed, index, liveSimulations, liveSamplerFor(gc),
                samples, &continuation, &selected, rootRow.is_null() ? nullptr : &rootActions);
        } catch (const std::exception &error) {
            if (leafStabilityMode) failStability(error.what());
            if (leafReplayMode) throw LeafReplayComplete{replayReport("INVALID", error.what())};
            throw;
        }
    }();
    if (leafReplayMode)
        throw LeafReplayComplete{replayReport("NOT_REACHED", "decision0_returned_without_replay")};
    if (policyTarget) {
        if (!policyRoot.is_null() && policyChoice) {
            std::vector<GameAction> primitives;
            for (const auto &c : policyRoot["candidates"]) primitives.emplace_back(c["bits"].get<std::uint32_t>());
            const auto tokens = heart1::mapChoiceTokens(*policyChoice, gc.hasRelic(RelicId::SINGING_BOWL), primitives);
            for (std::size_t i = 0; i < tokens.size(); ++i) {
                policyRoot["candidates"][i]["heart1Tokens"] = tokens[i].tokens;
                policyRoot["candidates"][i]["heart1Map"] = tokens[i].kind;
            }
        }
        policyRow["searched"] = !policyRoot.is_null();
        policyRow["root"] = std::move(policyRoot);
        policyRow["selectedKey"] = selected ? selected->key : "";
        policyRow["selectedBits"] = selected ? nlohmann::json(selected->primitive.bits) : nlohmann::json(nullptr);
    }
    profile.stop();
    const double wallElapsed = std::chrono::duration<double>(std::chrono::steady_clock::now()-wallStart).count();
    const double cpuElapsed = threadCpuSeconds()-cpuStart;
    metrics.wallSeconds += wallElapsed;
    metrics.cpuSeconds += cpuElapsed;
    nlohmann::json decisionProfile;
    if (!runProfilePath().empty()) {
        using nlohmann::json;
        const auto actionsJson = [](const std::vector<sts::search::OocRootActionStats> &actions) {
            auto output = json::array();
            for (const auto &a : actions)
                output.push_back({{"id", a.id}, {"prior", a.prior}, {"visits", a.visits}, {"q", a.q}});
            return output;
        };
        auto checkpoints = json::array();
        for (const auto &c : result.rootCheckpoints)
            checkpoints.push_back({{"simulations", c.simulations}, {"actions", actionsJson(c.actions)}});
        const auto &m = result.metrics;
        decisionProfile = {{"schema", 1}, {"kind", "ooc_decision"}, {"seed", std::to_string(seed)},
            {"decision", index}, {"act", gc.act}, {"floor", gc.floorNum},
            {"screen", int(gc.screenState)}, {"room", sts::roomStrings[int(gc.curRoom)]},
            {"wall_seconds", wallElapsed}, {"thread_cpu_seconds", cpuElapsed},
            {"configured_simulations", liveSimulations}, {"completed_simulations", m.simulations},
            {"attempts", m.simulationAttempts}, {"singleton_bypass", m.trivialRootBypasses},
            {"aborted", result.aborted}, {"abort_reason", result.abortReason},
            {"selected_action", result.selectedAction ? json(*result.selectedAction) : json(nullptr)},
            {"selected_key", selected ? selected->key : ""},
            {"selection_rule", liveConfig.selectByMeanQ ? "q_visits_id" : "visits_q_id"},
            {"actions", actionsJson(result.rootActions)}, {"checkpoints", checkpoints},
            {"expanded_action_histogram", runProfileHistogram(m.expandedActionHistogram)},
            {"expanded_nodes", m.expandedNodes0Actions + m.expandedNodes1Action
                + m.expandedNodes2Actions + m.expandedNodes3PlusActions},
            {"outcome_particles", m.outcomeParticles}, {"transition_samples", m.transitionSamples},
            {"ctm_samples", samples}, {"leaf_evaluations", m.leafEvaluations},
            {"max_depth", m.maxDepthReached}, {"depth_sum", m.depthSum},
            {"early_stop_lock", m.earlyStopLockedRoot}, {"early_stop_gap", m.earlyStopVisitGap20},
            {"cpu_budget_seconds", liveOptions.cpuBudgetSeconds}, {"early_stop_budget", m.earlyStopBudget}};
    }
    if (!liveCheckpointTrace.empty()) {
        ImaginedScope scope;
        auto shadowOptions = liveOptions;
        shadowOptions.priorTracePath.clear();
        OocGameContextModel shadow(gc, path, liveSamplerFor(gc), std::move(shadowOptions));
        if (!shadow.terminalValue(0) && !shadow.isLeafBoundary(0)) {
            auto config=liveConfig;
            config.seed=oocMctsSearchSeed(seed,index);
            config.observeRootLock=true;
            config.stopAt512VisitGap20=false;
            config.rootCheckpointSimulations={128,256,512,1024,2048};
            const auto observed=sts::search::OocMctsPlanner(config).search(shadow,0,liveSimulations);
            nlohmann::json checkpoints=nlohmann::json::array();
            for (const auto &checkpoint : observed.rootCheckpoints) {
                nlohmann::json actions=nlohmann::json::array();
                for (const auto &action : checkpoint.actions)
                    actions.push_back({{"id",action.id},{"key",shadow.candidate(0,action.id).key},{"prior",action.prior},
                        {"visits",action.visits},{"q",action.q}});
                checkpoints.push_back({{"simulations",checkpoint.simulations},{"actions",actions}});
            }
            const nlohmann::json row={
                {"schemaVersion",1},{"seed",seed},{"decisionIndex",index},
                {"floor",gc.floorNum},{"screen",int(gc.screenState)},
                {"requestedSimulations",liveSimulations},
                {"liveSimulations",result.metrics.simulations},
                {"liveAborted",result.aborted},{"liveAbortReason",result.abortReason},
                {"liveKey",selected ? selected->key : ""},
                {"liveAction",result.selectedAction ? nlohmann::json(*result.selectedAction) : nlohmann::json(nullptr)},
                {"liveGapStop20",result.metrics.earlyStopVisitGap20},
                {"liveSavedSimulations",result.metrics.savedSimulations},
                {"shadowSimulations",observed.metrics.simulations},
                {"shadowAttempts",observed.metrics.simulationAttempts},
                {"shadowAborted",observed.aborted},{"shadowAbortReason",observed.abortReason},
                {"finalAction",observed.selectedAction ? nlohmann::json(*observed.selectedAction) : nlohmann::json(nullptr)},
                {"checkpoints",checkpoints}};
            std::lock_guard<std::mutex> lock(liveTraceMutex);
            std::ofstream out(liveCheckpointTrace,std::ios::app);
            if (!out || !(out << row.dump() << '\n'))
                throw std::runtime_error("STS_OOC_MCTS_CHECKPOINT_TRACE write failed");
        }
    }
    metrics.combatSamples += samples;
    auto &c=metrics.continuation;
    c.imaginedCombats+=continuation.imaginedCombats; c.unsupportedCombats+=continuation.unsupportedCombats;
    c.pendingLeaves+=continuation.pendingLeaves; c.battleLeaves+=continuation.battleLeaves;
    c.mapLeaves+=continuation.mapLeaves; c.projectionSteps+=continuation.projectionSteps;
    c.continuationLimitAborts+=continuation.continuationLimitAborts;
    c.metadataBuilds+=continuation.metadataBuilds; c.priorBuilds+=continuation.priorBuilds;
    c.preparedCombats+=continuation.preparedCombats; c.combatEdgeSamples+=continuation.combatEdgeSamples;
    c.singletonPolicyLogitCalls+=continuation.singletonPolicyLogitCalls;
    c.singletonPolicyInferenceCalls+=continuation.singletonPolicyInferenceCalls;
    c.screenLeafEvaluations+=continuation.screenLeafEvaluations; c.screenLeafFallbacks+=continuation.screenLeafFallbacks;
    c.heart1PriorNodes+=continuation.heart1PriorNodes; c.heart1PriorFallbacks+=continuation.heart1PriorFallbacks;
    c.priorLeafSteps+=continuation.priorLeafSteps;
    c.heart1LeafSteps+=continuation.heart1LeafSteps; c.heart1LeafFallbacks+=continuation.heart1LeafFallbacks;
    c.studentLeafEvaluations+=continuation.studentLeafEvaluations; c.studentLeafFallbacks+=continuation.studentLeafFallbacks;
    for (auto &[reason,count] : continuation.heart1LeafReasons) c.heart1LeafReasons[reason]+=count;
    for (auto &[reason,count] : continuation.heart1PriorReasons) c.heart1PriorReasons[reason]+=count;
    for (auto &[reason,count] : continuation.continuationReasons) c.continuationReasons[reason]+=count;
    for (auto &[reason,count] : continuation.supportReasons) c.supportReasons[reason]+=count;
    auto &m = metrics.search;
    m.outcomeParticles+=result.metrics.outcomeParticles; m.decisionNodes+=result.metrics.decisionNodes;
    m.chanceNodes+=result.metrics.chanceNodes; m.particleRevisits+=result.metrics.particleRevisits;
    for (const auto &[actions, count] : result.metrics.expandedActionHistogram)
        m.expandedActionHistogram[actions] += count;
    m.expandedNodes0Actions+=result.metrics.expandedNodes0Actions;
    m.expandedNodes1Action+=result.metrics.expandedNodes1Action;
    m.expandedNodes2Actions+=result.metrics.expandedNodes2Actions;
    m.expandedNodes3PlusActions+=result.metrics.expandedNodes3PlusActions;
    m.deterministicRevisits+=result.metrics.deterministicRevisits; m.depthSum+=result.metrics.depthSum;
    m.trivialRootBypasses += result.metrics.trivialRootBypasses;
    m.earlyStopLockedRoot += result.metrics.earlyStopLockedRoot;
    m.earlyStopVisitGap20 += result.metrics.earlyStopVisitGap20;
    m.earlyStopBudget += result.metrics.earlyStopBudget;
    m.savedSimulations += result.metrics.savedSimulations;
    m.simulations += result.metrics.simulations;
    m.simulationAttempts += result.metrics.simulationAttempts;
    m.transitionSamples += result.metrics.transitionSamples;
    m.leafEvaluations += result.metrics.leafEvaluations;
    m.maxDepthReached = std::max(m.maxDepthReached, result.metrics.maxDepthReached);
    if (result.aborted) {
        ++metrics.supportAborts; metrics.discardedSimulations+=result.metrics.simulations;
    }
    const auto rootScreen = gc.screenState;
    const auto rootSelector = gc.info.selectScreenType;
    const auto traceDecision = [&](bool executed, const std::string &reason) {
        if (policyTarget) {
            policyRow["executed"] = executed;
            policyRow["executionReason"] = reason;
            t_policyTargetRow = std::move(policyRow);
        }
        if (!decisionProfile.is_null()) {
            decisionProfile["executed"] = executed;
            decisionProfile["execution_reason"] = reason;
            writeRunProfile(decisionProfile);
        }
        if (!rootRow.is_null()) {
            std::uint64_t visits = 0;
            for (const auto &a : rootActions) visits += a.at("visits").get<std::uint64_t>();
            for (auto &a : rootActions)
                a["visitShare"] = visits ? double(a.at("visits").get<std::uint64_t>()) / double(visits) : 0.0;
            rootRow.update({{"aborted", result.aborted}, {"abortReason", result.abortReason},
                {"requestedSimulations", liveSimulations}, {"completedSimulations", result.metrics.simulations},
                {"singletonBypass", result.metrics.trivialRootBypasses > 0},
                {"selectedId", result.selectedAction ? nlohmann::json(*result.selectedAction) : nlohmann::json(nullptr)},
                {"selectedKey", selected ? selected->key : ""}, {"rootActions", std::move(rootActions)},
                {"executed", executed}, {"reason", reason}});
            std::lock_guard<std::mutex> lock(liveTraceMutex);
            std::ofstream out(liveRootTrace, std::ios::app);
            if (!out || !(out << rootRow.dump() << '\n'))
                throw std::runtime_error("STS_OOC_MCTS_ROOT_TRACE write failed");
        }
        if (liveTrace.empty()) return;
        std::lock_guard<std::mutex> lock(liveTraceMutex);
        std::ofstream out(liveTrace + ".actions.jsonl", std::ios::app);
        out << nlohmann::json{{"seed",seed},{"decisionIndex",index},
            {"screen",int(rootScreen)},{"selector",int(rootSelector)},
            {"selectedId",result.selectedAction ? nlohmann::json(*result.selectedAction) : nlohmann::json(nullptr)},
            {"selectedKey",selected ? selected->key : ""},
            {"semantic",selected && selected->semantic.has_value()},
            {"compound",selected && selected->compoundSelector != sts::CardSelectScreenType::INVALID},
            {"executed",executed},{"reason",reason}}.dump() << '\n';
        if (!out) throw std::runtime_error("OOC MCTS action trace write failed");
    };
    if (!result.selectedAction) {
        if (leafStabilityMode) failStability("scheduled_root_has_no_selected_action");
        ++metrics.fallback;
        traceDecision(false, result.aborted ? result.abortReason : "root_boundary");
        return false;
    }
    std::string error;
    if (!selected || !executeOocMctsRoot(gc, *selected, error)) {
        if (leafStabilityMode) failStability("scheduled_root_action_failed:" + error);
        ++metrics.fallback;
        ++metrics.continuation.supportReasons[error.empty() ? "missing_root_identity" : error];
        traceDecision(false,error);
        return false;
    }
    ++metrics.owned;
    traceDecision(true, "");
    return true;
}
bool executeOocMctsRoot(GameContext &gc, const OocGameContextModel::Candidate &selected, std::string &error) {
    if (selected.semantic) {
        const auto fresh = sts::search::enumerateOocSemanticActions(gc);
        if (!fresh.supported || !fresh.complete) { error = "semantic_root_incomplete"; return false; }
        const sts::search::OocSemanticAction *match = nullptr;
        for (const auto &action : fresh.actions) {
            if (sts::search::canonicalOocSemanticActionKey(action) != selected.key) continue;
            if (match) { error = "semantic_root_ambiguous"; return false; }
            match = &action;
        }
        if (!match) { error = "semantic_root_stale"; return false; }
        const auto execution = sts::search::executeOocSemanticAction(gc, *match);
        if (!execution.ok) { error = "semantic_live_execution:" + execution.error; return false; }
        return true;
    }
    if (gc.screenState != sts::ScreenState::MAP_SCREEN) { error = "map_root_stale"; return false; }
    const auto candidates = v4CandidateActions(gc);
    const auto action = std::find_if(candidates.begin(), candidates.end(),
        [&](auto a) { return a.bits == selected.primitive.bits; });
    if (action == candidates.end()) { error = "map_root_stale"; return false; }
    action->execute(gc);
    return true;
}

void writeLiveOocMctsTrace(std::uint64_t seed, const LiveOocMctsMetrics &m, int realCombats) {
    if (liveFallbackSampler) {
        std::map<std::string, std::uint64_t> reasons;
        for (const auto &sampler : {liveFallbackSampler, liveFallbackSamplerA20})
            if (const auto fallback = std::dynamic_pointer_cast<const SilverFallbackCombatTransitionSampler>(sampler))
                for (const auto &[reason, n] : fallback->takeReasons()) reasons[reason] += n;
        std::uint64_t total = 0;
        for (const auto &entry : reasons) total += entry.second;
        std::cerr << "[ooc-silver-fallback] " << nlohmann::json{{"seed", seed},
            {"silverSims", liveUnsupportedSilverSims}, {"act4SilverSims", liveAct4SilverSims},
            {"resolvedByReason", reasons},
            {"resolved", total}}.dump() << '\n';
    }
    EntropicBrewFallbackCombatTransitionSampler::Metrics brewMetrics;
    const auto hybridSampler=std::dynamic_pointer_cast<const EntropicBrewFallbackCombatTransitionSampler>(liveSampler);
    if (hybridSampler) brewMetrics=hybridSampler->takeMetrics();
    // With STS_OOC_MCTS_A20_CTM=1 a run uses one stack (its ascension decides); report the one that prepared.
    if (const auto a20=std::dynamic_pointer_cast<const EntropicBrewFallbackCombatTransitionSampler>(liveSamplerA20)) {
        const auto a20Metrics=a20->takeMetrics();
        if (a20Metrics.preparations) brewMetrics=a20Metrics;
    }
    if (oocProfileEnabled()) {
        static const char *names[] = {"mcts", "real_combat", "metadata", "policy_logits",
            "policy_prepare", "policy_predict", "successor", "combat_prepare", "combat_resolve",
            "evaluate_leaf", "leaf_value", "leaf_features", "leaf_predict", "v4_state_network", "v4_encode_deck",
            "v4_encode_rel", "v4_encode_pot", "v4_state_fusion", "v4_action_value",
            "prior_build", "singleton_prior"};
        nlohmann::json counters = nlohmann::json::object();
        for (std::size_t index = 0; index < oocProfileCounters.size(); ++index) {
            const auto &counter = oocProfileCounters[index];
            counters[names[index]] = {{"calls", counter.calls}, {"inclusiveCpuSec", counter.inclusive},
                {"exclusiveCpuSec", counter.exclusive}};
        }
        nlohmann::json hybrid={{"preparations",brewMetrics.preparations},
            {"fastPreparations",brewMetrics.fastPreparations},
            {"standardBrewFallbackPreparations",brewMetrics.fallbackPreparations},
            {"fastSamples",brewMetrics.fastSamples},{"fallbackSamples",brewMetrics.fallbackSamples},
            {"fallbackRate",brewMetrics.fallbackRate},
            {"uniqueBrewPredictorStates",brewMetrics.uniqueBrewPredictorStates},
            {"fastSupportFailures",brewMetrics.fastSupportFailures},
            {"fallbackSupportFailures",brewMetrics.fallbackSupportFailures},
            {"activeLizardEnabled",hybridSampler && hybridSampler->activeLizardEnabled()},
            {"lizardPreparations",brewMetrics.lizardPreparations},
            {"lizardSamples",brewMetrics.lizardSamples},
            {"lizardOrdinaryWins",brewMetrics.lizardOrdinaryWins},
            {"lizardConsumedWins",brewMetrics.lizardConsumedWins},
            {"lizardConsumedLosses",brewMetrics.lizardConsumedLosses},
            {"lizardBoundaryExclusions",brewMetrics.lizardBoundaryExclusions},
            {"lizardSupportFailures",brewMetrics.lizardSupportFailures}};
        std::cerr << "[ooc-cpu-profile] " << nlohmann::json{{"seed",seed},
            {"processCpuAtReportSec",oocProfileCpu(CLOCK_PROCESS_CPUTIME_ID)},
            {"mctsCpuSec",m.cpuSeconds},{"realCombats",realCombats},{"counters",counters},
            {"expandedNodesByActionCount",{
                {"0",m.search.expandedNodes0Actions},{"1",m.search.expandedNodes1Action},
                {"2",m.search.expandedNodes2Actions},{"3+",m.search.expandedNodes3PlusActions}}},
            {"singletonPolicyLogitCalls",m.continuation.singletonPolicyLogitCalls},
            {"singletonPolicyInferenceCalls",m.continuation.singletonPolicyInferenceCalls},
            {"combatTransitionHybrid",hybrid}}.dump() << '\n';
        oocProfileCounters = {};
    }
    if(hybridSampler)
        std::cerr << "[ooc-combat-transition] " << nlohmann::json{{"seed",seed},
            {"activeLizardEnabled",hybridSampler->activeLizardEnabled()},
            {"lizardPreparations",brewMetrics.lizardPreparations},
            {"lizardSamples",brewMetrics.lizardSamples},
            {"lizardOrdinaryWins",brewMetrics.lizardOrdinaryWins},
            {"lizardConsumedWins",brewMetrics.lizardConsumedWins},
            {"lizardConsumedLosses",brewMetrics.lizardConsumedLosses},
            {"lizardBoundaryExclusions",brewMetrics.lizardBoundaryExclusions},
            {"lizardSupportFailures",brewMetrics.lizardSupportFailures},
            {"fastSupportFailures",brewMetrics.fastSupportFailures},
            {"fallbackSupportFailures",brewMetrics.fallbackSupportFailures},
            {"standardBrewFallbackPreparations",brewMetrics.fallbackPreparations}}.dump() << '\n';
    if (liveTrace.empty()) return;
    std::lock_guard<std::mutex> lock(liveTraceMutex);
    const std::string header = "seed,oocDecisions,mctsOwned,mctsFallback,simulations,transitionSamples,combatSurrogateSamples,leafEvaluations,maxDepth,mctsWallSec,mctsCpuSec,realCombats,imaginedCombats,unsupportedCombats,mctsSupportAborts,discardedSimulations,simulationAttempts,pendingLeaves,battleLeaves,mapLeaves,projectionSteps,outcomeParticles,particleRevisits,deterministicRevisits,depthSum,continuationLimitAborts,trivialRootBypasses,earlyStopLockedRoot,earlyStopVisitGap20,savedSimulations,metadataBuilds,priorBuilds,preparedCombats,combatEdgeSamples,hybridPreparations,hybridFastPreparations,hybridFallbackPreparations,hybridFastSamples,hybridFallbackSamples,hybridFallbackRate,hybridUniqueBrewStates,hybridFastSupportFailures,hybridFallbackSupportFailures\n";
    std::ifstream existing(liveTrace);
    std::string firstLine;
    if (std::getline(existing,firstLine) && firstLine+'\n' != header)
        throw std::runtime_error("STS_OOC_MCTS_TRACE incompatible header; use a fresh trace path");
    std::ofstream out(liveTrace, std::ios::app);
    if (!out) throw std::runtime_error("STS_OOC_MCTS_TRACE cannot write output");
    if (out.tellp() == 0) out << header;
    out << std::setprecision(12) << seed << ',' << m.decisions << ',' << m.owned << ',' << m.fallback
        << ',' << m.search.simulations << ',' << m.search.transitionSamples << ',' << m.combatSamples
        << ',' << m.search.leafEvaluations << ',' << m.search.maxDepthReached
        << ',' << m.wallSeconds << ',' << m.cpuSeconds << ',' << realCombats
        << ',' << m.continuation.imaginedCombats << ',' << m.continuation.unsupportedCombats
        << ',' << m.supportAborts << ',' << m.discardedSimulations << ',' << m.search.simulationAttempts
        << ',' << m.continuation.pendingLeaves << ',' << m.continuation.battleLeaves
        << ',' << m.continuation.mapLeaves << ',' << m.continuation.projectionSteps
        << ',' << m.search.outcomeParticles << ',' << m.search.particleRevisits
        << ',' << m.search.deterministicRevisits << ',' << m.search.depthSum
        << ',' << m.continuation.continuationLimitAborts
        << ',' << m.search.trivialRootBypasses << ',' << m.search.earlyStopLockedRoot
        << ',' << m.search.earlyStopVisitGap20
        << ',' << m.search.savedSimulations << ',' << m.continuation.metadataBuilds
        << ',' << m.continuation.priorBuilds << ',' << m.continuation.preparedCombats
        << ',' << m.continuation.combatEdgeSamples << ',' << brewMetrics.preparations
        << ',' << brewMetrics.fastPreparations << ',' << brewMetrics.fallbackPreparations
        << ',' << brewMetrics.fastSamples << ',' << brewMetrics.fallbackSamples
        << ',' << brewMetrics.fallbackRate << ',' << brewMetrics.uniqueBrewPredictorStates
        << ',' << brewMetrics.fastSupportFailures << ',' << brewMetrics.fallbackSupportFailures << '\n';
    std::ofstream reasons(liveTrace+".support.jsonl",std::ios::app);
    reasons << nlohmann::json{{"seed",seed},{"reasons",m.continuation.supportReasons},
        {"continuation_reasons",m.continuation.continuationReasons},
        {"continuation_limit_aborts",m.continuation.continuationLimitAborts},
        {"screen_leaf_evaluations",m.continuation.screenLeafEvaluations},
        {"screen_leaf_fallbacks",m.continuation.screenLeafFallbacks},
        {"heart1_prior_nodes",m.continuation.heart1PriorNodes},
        {"heart1_prior_fallbacks",m.continuation.heart1PriorFallbacks},
        {"heart1_prior_reasons",m.continuation.heart1PriorReasons},
        {"prior_leaf_steps",m.continuation.priorLeafSteps},
        {"cpu_budget_stops",m.search.earlyStopBudget},
        {"heart1_leaf_steps",m.continuation.heart1LeafSteps},
        {"heart1_leaf_fallbacks",m.continuation.heart1LeafFallbacks},
        {"heart1_leaf_reasons",m.continuation.heart1LeafReasons},
        {"student_leaf_evaluations",m.continuation.studentLeafEvaluations},
        {"student_leaf_fallbacks",m.continuation.studentLeafFallbacks}}.dump() << '\n';
    reasons.flush();
    if (!reasons) throw std::runtime_error("OOC MCTS support trace write failed");
    out.flush();
    if (!out) throw std::runtime_error("STS_OOC_MCTS_TRACE write failed");
}

}

#include "../../tests/data/ooc_v4_policy_fixture.h"
namespace one_combat {
double oocBossLeafUtility(const CombatTransitionExpectation &estimate) {
    return bossLeafUtility(estimate);
}
std::shared_ptr<const CombatTransitionSampler> oocMaskInitialSmokeBomb(
        std::shared_ptr<const CombatTransitionSampler> sampler) {
    return maskInitialSmokeBomb(std::move(sampler));
}
void oocMctsAdapterSelfTest() {
    runFloorProfileSelfTest();
    oocLeafCandidateInputSelfTest();
    oocLeafCaptureSinkSelfTest();
    using namespace sts;
    using namespace sts::search;
    {
        GameContext counters(CharacterClass::IRONCLAD, 1234, 0);
        counters.act = 2;
        counters.floorNum = 23;
        for (int seed = 0; seed < 128; ++seed) {
            std::mt19937_64 rng(seed);
            sampleLiveOocHiddenCounters(counters, rng, 0);
            require(counters.monsterChance == 0.1f && counters.shopChance == 0.03f
                    && counters.treasureChance == 0.02f,
                    "zero current-act event rooms must reset room-chance counters");
            sampleLiveOocHiddenCounters(counters, rng, 1);
            const bool monster = counters.monsterChance == 0.1f
                && counters.shopChance == 0.03f + 0.03f
                && counters.treasureChance == 0.02f + 0.02f;
            const bool shop = counters.monsterChance == 0.1f + 0.1f
                && counters.shopChance == 0.03f
                && counters.treasureChance == 0.02f + 0.02f;
            const bool treasure = counters.monsterChance == 0.1f + 0.1f
                && counters.shopChance == 0.03f + 0.03f
                && counters.treasureChance == 0.02f;
            const bool event = counters.monsterChance == 0.1f + 0.1f
                && counters.shopChance == 0.03f + 0.03f
                && counters.treasureChance == 0.02f + 0.02f;
            require(monster || shop || treasure || event,
                    "one event-room outcome must produce a reachable joint chance state");
        }
    }
    // Inspect the actual configured option before fixture-specific resets.
    require(!liveEnabled || liveOptions.sampleNoncombat,
        "enabled live OOC MCTS must sample noncombat outcomes after all startup resets");
    std::cout << std::setprecision(12);
    require(g_oocStrategicTokNet.path == "selfplay/models/ooc_strategic_tok_final.native"
        || g_oocStrategicTokNet.path.find("/selfplay/models/ooc_strategic_tok_final.native") != std::string::npos,
        "policy parity requires tracked final V4 artifact");
    {
        // The simulator's actual ordered driver and the advisor's shared
        // native fallback must reach identical checkpoints from the same
        // public state. Disable the optional V4 gate for this fallback seam;
        // its Q/margin gate has separate parity fixtures below.
        CompactTreeNet floor, win;
        require(floor.load("models/v_rich_trees.txt", richIdxMap(), "ParityFloor")
                && win.load("models/v_win_trees.txt", richIdxMap(), "ParityWin"),
            "checkpoint parity model artifacts unavailable");
        const bool savedV4 = g_oocStrategicTokNet.ok;
        const auto *savedPath = t_curPath;
        g_oocStrategicTokNet.ok = false;
        PathHistory parityPath;
        t_curPath = &parityPath;
        auto compare = [&](GameContext original, const std::function<void(GameContext &)> &advisorStep,
                           const char *reason) {
            original.regainControlAction = [](GameContext &state) {
                state.screenState = ScreenState::MAP_SCREEN;
                state.regainControlAction = nullptr;
            };
            auto oracle = detachedCopy(original), advisor = detachedCopy(original);
            ScumSearchAgent2 agent;
            agent.rng.seed(0);
            runFullRunOocPolicyStep(oracle, agent, false, true);
            advisorStep(advisor);
            require(test::oocStateFingerprint(oracle) == test::oocStateFingerprint(advisor), reason);
        };
        GameContext parity(CharacterClass::IRONCLAD, 0x51514Du, 0);
        parity.screenState = ScreenState::REWARDS;
        parity.curRoom = Room::MONSTER;
        parity.info.rewardsContainer.clear();
        CardReward cards;
        cards.push_back(Card(CardId::ANGER)); cards.push_back(Card(CardId::BASH));
        parity.info.rewardsContainer.addCardReward(cards);
        compare(parity, [&](GameContext &state) {
            const int pick = nativeFloorCardPick(state, parityPath, floor, 0, -0.5);
            GameAction(GameAction::RewardsActionType::CARD, 0, pick).execute(state);
        }, "card-reward simulator/advisor checkpoint mismatch");
        parity.screenState = ScreenState::REST_ROOM;
        parity.curRoom = Room::REST;
        parity.curHp = 30;
        compare(parity, [&](GameContext &state) {
            if (!nativeWinRestStep(state, parityPath, win, false)) {
                ScumSearchAgent2 agent; agent.rng.seed(0); agent.stepOutOfCombatPolicy(state);
            }
        }, "rest simulator/advisor checkpoint mismatch");
        parity.openCardSelectScreen(CardSelectScreenType::UPGRADE, 1);
        compare(parity, [&](GameContext &state) {
            nativeWinUpgradeSelectStep(state, parityPath, win);
        }, "upgrade-selector simulator/advisor checkpoint mismatch");
        parity = GameContext(CharacterClass::IRONCLAD, 0x51514Du, 0);
        parity.screenState = ScreenState::SHOP_ROOM;
        parity.curRoom = Room::SHOP;
        parity.gold = 100;
        for (int i = 0; i < 7; ++i) parity.info.shop.cardPrice(i) = -1;
        for (int i = 0; i < 3; ++i) {
            parity.info.shop.relicPrice(i) = -1;
            parity.info.shop.potionPrice(i) = -1;
        }
        parity.info.shop.cards[0] = Card(CardId::ANGER);
        parity.info.shop.cardPrice(0) = 50;
        parity.info.shop.removeCost = -1;
        compare(parity, [&](GameContext &state) {
            nativeFloorShopStep(state, parityPath, floor);
        }, "shop simulator/advisor checkpoint mismatch");
        parity.openCardSelectScreen(CardSelectScreenType::REMOVE, 1);
        compare(parity, [&](GameContext &state) {
            std::vector<int> ids;
            for (int i = 0; i < state.info.toSelectCards.size(); ++i)
                ids.push_back(static_cast<int>(state.info.toSelectCards[i].card.getId()));
            GameAction(nativeFloorRemovePick(state, parityPath, floor, ids), 0).execute(state);
        }, "shop remove-selector simulator/advisor checkpoint mismatch");
        parity = GameContext(CharacterClass::IRONCLAD, 0x51514Du, 0);
        parity.screenState = ScreenState::EVENT_SCREEN;
        parity.curRoom = Room::EVENT;
        parity.curEvent = Event::THE_WOMAN_IN_BLUE;
        parity.gold = 100;
        compare(parity, [&](GameContext &state) {
            ScumSearchAgent2 agent; agent.rng.seed(0); agent.stepOutOfCombatPolicy(state);
        }, "event simulator/advisor checkpoint mismatch");
        parity.openCardSelectScreen(CardSelectScreenType::TRANSFORM, 1);
        compare(parity, [&](GameContext &state) {
            ScumSearchAgent2 agent; agent.rng.seed(0); agent.stepOutOfCombatPolicy(state);
        }, "transform-selector simulator/advisor checkpoint mismatch");
        g_oocStrategicTokNet.ok = savedV4;
        require(savedV4, "V4 checkpoint parity requires loaded token model");
        parity = GameContext(CharacterClass::IRONCLAD, 0x51514Du, 0);
        parity.screenState = ScreenState::REWARDS;
        parity.curRoom = Room::MONSTER;
        parity.info.rewardsContainer.clear();
        parity.info.rewardsContainer.addCardReward(cards);
        compare(parity, [&](GameContext &state) {
            const double margin = g_oocStrategicMarginCard >= 0.0
                ? g_oocStrategicMarginCard : g_oocStrategicMargin;
            if (!takeQualifiedV4CardReward(state, parityPath, g_oocStrategicTokNet, margin)) {
                const int pick = nativeFloorCardPick(state, parityPath, floor, 0, -0.5);
                GameAction(GameAction::RewardsActionType::CARD, 0, pick).execute(state);
            }
        }, "V4 card-reward simulator/advisor checkpoint mismatch");
        t_curPath = savedPath;
    }
    float glob[42]; for (int i=0;i<42;++i) glob[i]=(i-20)*.125f;
    const int dk[96][3] = {{1,0,5},{42,1,2},{100,0,1}};
    const int rl[64][2] = {{1,1},{23,4}};
    const int pt[8][2] = {{2,1},{7,2}};
    const auto fixturePrepared = g_oocStrategicTokNet.prepareState(glob,3,dk,2,rl,2,pt);
    const auto fixturePolicyPrefix = g_oocStrategicTokNet.preparePolicyPrefix(fixturePrepared);
    for (auto f : v4PolicyFixtures) {
        const float et[4] = {float(f.entityType==0),float(f.entityType==1),float(f.entityType==2),float(f.entityType==3)};
        double logit = g_oocStrategicTokNet.predictPolicyLogit(glob,3,dk,2,rl,2,pt,f.bits,f.cats,
            f.type,f.screen,et,f.entityId,f.price);
        double q = g_oocStrategicTokNet.predictActionValue(glob,3,dk,2,rl,2,pt,f.bits,f.cats,
            f.type,f.screen,et,f.entityId,f.price);
        require(logit == g_oocStrategicTokNet.predictPolicyLogit(fixturePrepared,f.bits,f.cats,
                    f.type,f.screen,et,f.entityId,f.price)
            && logit == g_oocStrategicTokNet.predictPolicyLogit(fixturePrepared,fixturePolicyPrefix,
                    f.bits,f.cats,f.type,f.screen,et,f.entityId,f.price)
            && q == g_oocStrategicTokNet.predictActionValue(fixturePrepared,f.bits,f.cats,
                    f.type,f.screen,et,f.entityId,f.price),
            "prepared V4 policy/Q and shared-prefix policy exactly match legacy entry points");
        require(std::abs(logit-f.logit)<1e-4, "V4 policy parity");
        require(std::abs(q-f.q)<2e-4, "V4 Q regression parity");
        std::cout << "parity bits="<<f.bits<<" logit="<<logit<<" expected="<<f.logit
                  <<" error="<<std::abs(logit-f.logit)<<" q_error="<<std::abs(q-f.q)<<'\n';
    }
    const auto cold = oocPolicyWeights({0, 2}, .5), hot = oocPolicyWeights({0, 2}, 2);
    require(cold[0] < hot[0] && cold[1] == 1 && hot[1] == 1, "temperature changes policy concentration");
    auto extreme = oocPolicyWeights({-10000,0,10000});
    require(extreme == std::vector<double>({0,0,1}), "stable extreme softmax");
    auto rejects = [](auto fn) { bool rejected=false; try { fn(); } catch(const std::exception &) { rejected=true; }
        require(rejected,"invalid adapter input accepted"); };
    rejects([] { oocPolicyWeights({0},0); });
    rejects([] { oocPolicyWeights({NAN}); });
    rejects([] { oocPolicyWeights({0},INFINITY); });
    rejects([] { oocPolicyWeights({0},NAN); });
    // One-unit internal bound exposes the final-transition edge without a live
    // configuration knob or hundreds of artificial native decisions.
    for (double finalValue : {0.0,0.5,1.0}) {
        int transitions=0, checkpointChecks=0;
        const auto value=boundedContinuation(1,[&]() -> std::optional<double> {
            ++checkpointChecks;
            return transitions ? std::optional<double>(finalValue) : std::nullopt;
        },[&] { ++transitions; });
        require(value==finalValue && transitions==1 && checkpointChecks==2,
            "last permitted transition accepts exact terminal or resolved checkpoint value");
    }
    {
        int transitions=0;
        bool aborted=false;
        try { boundedContinuation(1,[] { return std::optional<double>{}; },[&] { ++transitions; }); }
        catch (const OocSearchUnsupported &error) { aborted=std::string(error.what())=="continuation_step_limit_1"; }
        require(aborted && transitions==1,"unresolved continuation still aborts exactly at step limit");
    }
    GameContext gc(CharacterClass::IRONCLAD,42,0);
    gc.screenState=ScreenState::MAP_SCREEN;
    gc.curEvent=Event::INVALID;
    gc.regainControlAction=[](GameContext &g) { g.screenState=ScreenState::MAP_SCREEN; };
    require(gc.map != nullptr, "real map fixture");
    PathHistory path; path.update(gc);
    OocGameContextModel model(gc,path);
    auto sourceId = [](const OocGameContextModel &provider, std::uint32_t bits) {
        for (const auto &action : provider.legalActions(0))
            if (provider.candidate(0,action.id).primitive.bits==bits) return action.id;
        throw std::runtime_error("required source primitive absent from adapter candidates");
    };
    // Prior visit counts are external to GameContext and must survive root construction.
    PathHistory nonemptyHistory;
    nonemptyHistory.roomVisits[int(Room::SHOP)]=2;
    nonemptyHistory.roomVisits[int(Room::REST)]=1;
    nonemptyHistory.roomVisits[int(Room::EVENT)]=3;
    nonemptyHistory.roomVisits[int(Room::ELITE)]=4;
    nonemptyHistory.roomVisits[int(Room::MONSTER)]=5;
    nonemptyHistory.roomVisits[int(Room::TREASURE)]=6;
    OocGameContextModel historyModel(gc,nonemptyHistory);
    const auto historyLogits=historyModel.policyLogits(0);
    const auto cachedHistoryActions=historyModel.legalActions(0);
    for (int repeat=0;repeat<3;++repeat) {
        require(historyModel.policyLogits(0)==historyLogits,"cached logits remain bit-exact");
        const auto again=historyModel.legalActions(0);
        require(again.size()==cachedHistoryActions.size(),"cached legal action count");
        for (std::size_t i=0;i<again.size();++i)
            require(again[i].id==cachedHistoryActions[i].id && again[i].prior==cachedHistoryActions[i].prior,
                "cached legal IDs/order/raw priors exact");
    }
    require(historyModel.continuationMetrics().metadataBuilds==1
        && historyModel.continuationMetrics().priorBuilds==1
        && !historyModel.searchGuaranteedNonAborting(),
        "immutable metadata/token/prior build once; live model remains abort-capable");
    const auto historyActions=v4CandidateActions(gc);
    const TokState historyTokens=buildTokState(gc,nonemptyHistory);
    double maxHistoryPolicyError=0;
    for(std::size_t i=0;i<historyActions.size();++i) {
        const auto a=historyActions[i];
        int type,c1,c2,c3,d1,d2,d3,et,ei; float price;
        strategicCands(gc,a,type,c1,c2,c3,d1,d2,d3);
        tokEntity(gc,a,et,ei,price);
        const int cats[6]={c1,c2,c3,d1,d2,d3};
        const float entity[4]={float(et==0),float(et==1),float(et==2),float(et==3)};
        const double direct=g_oocStrategicTokNet.predictPolicyLogit(historyTokens.glob,
            historyTokens.nDk,historyTokens.dk,historyTokens.nRl,historyTokens.rl,
            historyTokens.nPt,historyTokens.pt,a.bits,cats,type,int(gc.screenState),entity,ei,price);
        maxHistoryPolicyError=std::max(maxHistoryPolicyError,std::abs(direct-historyLogits[i]));
        require(std::abs(direct-historyLogits[i])<1e-12,"nonempty history V4 policy parity");
    }
    const auto previousHistory=t_curPath;
    t_curPath=&nonemptyHistory;
    const double directHistoryLeaf=vStateWinNative(gc);
    const double adapterHistoryLeaf=historyModel.leafValue(0);
    require(t_curPath==&nonemptyHistory,"leaf restores caller history");
    t_curPath=previousHistory;
    require(std::abs(directHistoryLeaf-adapterHistoryLeaf)<1e-12,"nonempty history native win parity");
    // The fixture must expose lost-history bugs, not merely exercise nonzero inputs.
    const auto emptyHistoryLogits=model.policyLogits(0);
    bool policyChanged=false;
    for(std::size_t i=0;i<historyLogits.size();++i)
        policyChanged=policyChanged || std::abs(historyLogits[i]-emptyHistoryLogits[i])>1e-6;
    require(policyChanged && std::abs(adapterHistoryLeaf-model.leafValue(0))>1e-6,
            "nonempty history fixture must affect both models");
    std::cout<<"nonempty_history_parity actions="<<historyActions.size()
        <<" policy_max_error="<<maxHistoryPolicyError
        <<" leaf_error="<<std::abs(directHistoryLeaf-adapterHistoryLeaf)
        <<" leaf_value="<<adapterHistoryLeaf<<'\n';
    auto candidates=v4CandidateActions(gc);
    auto legal=model.legalActions(0);
    auto logits=model.policyLogits(0);
    require(!legal.empty() && legal.size()==candidates.size(),"candidate parity");
    std::set<std::uint32_t> ids;
    for (std::size_t i=0;i<legal.size();++i) {
        require(legal[i].id==candidates[i].bits && ids.insert(legal[i].id).second,"primitive action identity");
    }
    std::mt19937_64 rng(42);
    rejects([&] { model.sampleSuccessor(0,0xFFFFFFFFu,rng); });
    GameContext expected=detachedCopy(gc);
    candidates.front().execute(expected);
    auto child=model.sampleSuccessor(0,legal.front().id,rng);
    require(model.state(child).screenState==expected.screenState
        && model.state(child).curMapNodeX==expected.curMapNodeX
        && model.state(child).floorNum==expected.floorNum
        && model.state(child).curHp==expected.curHp,"native copied successor");
    require(model.state(0).curMapNodeX==gc.curMapNodeX && model.state(0).floorNum==gc.floorNum
        && model.state(0).screenState==gc.screenState,"parent unchanged");
    require(model.state(child).map.get()!=model.state(0).map.get()
        && model.state(0).map.get()!=gc.map.get(),"map detached at root and successor");
    auto repeated=model.sampleSuccessor(0,legal.front().id,rng);
    require(model.state(repeated).curMapNodeX==model.state(child).curMapNodeX
        && model.state(repeated).info.encounter==model.state(child).info.encounter,"concrete RNG replay");
    // Mutate caller's map: materialized root must retain its own content.
    auto room=model.state(0).map->nodes[0][0].room;
    gc.map->nodes[0][0].room=Room::SHOP;
    require(model.state(0).map->nodes[0][0].room==room,"external map independence");
    gc.map->nodes[0][0].room=room;
    model.state(child).map->nodes[0][0].room=Room::SHOP;
    require(model.state(0).map->nodes[0][0].room==room
        && gc.map->nodes[0][0].room==room,"child map mutation cannot affect ancestors");
    model.state(child).map->nodes[0][0].room=room;
    // Compare the adapter against the complete semantic surface, independently
    // execute each semantic edge, and audit the source-level prior bridge.
    bool directTraceChecked = false, compoundTraceChecked = false;
    std::uint64_t traceFileSuffix = std::chrono::steady_clock::now().time_since_epoch().count();
    const auto newTraceFile = [&]() {
        return "/tmp/ooc_mcts_prior_selftest_" + std::to_string(traceFileSuffix++) + ".jsonl";
    };
    auto checkCandidates = [&](GameContext fixture, bool execute=true) {
        auto canonical = detachedCopy(fixture);
        collectForcedRewardGold(canonical);
        const auto before=test::oocStateFingerprint(canonical);
        const auto bindings=enumerateOocSemanticPrimitiveBindings(canonical);
        std::vector<sts::search::OocSemanticPrimitiveBinding> representatives;
        std::set<std::string> choiceKeys;
        for (const auto &binding : bindings.bindings)
            if (choiceKeys.insert(canonicalOocMctsChoiceKey(binding.semantic, &canonical)).second)
                representatives.push_back(binding);
        const bool map=canonical.screenState==ScreenState::MAP_SCREEN;
        const auto primitive=v4CandidateActions(canonical);
        const TokState tokens=buildTokState(canonical,path);
        const auto prepared=g_oocStrategicTokNet.prepareState(tokens.glob,tokens.nDk,tokens.dk,
            tokens.nRl,tokens.rl,tokens.nPt,tokens.pt);
        const auto policyPrefix=g_oocStrategicTokNet.preparePolicyPrefix(prepared);
        std::map<std::uint32_t,double> sourceLogits;
        for(const auto action:primitive) {
            int type,c1,c2,c3,d1,d2,d3,et,ei; float price;
            strategicCands(canonical,action,type,c1,c2,c3,d1,d2,d3);
            tokEntity(canonical,action,et,ei,price);
            const int cats[6]={c1,c2,c3,d1,d2,d3};
            const float entity[4]={float(et==0),float(et==1),float(et==2),float(et==3)};
            const auto reference=g_oocStrategicTokNet.predictPolicyLogit(prepared,action.bits,cats,
                type,int(canonical.screenState),entity,ei,price);
            const auto optimized=g_oocStrategicTokNet.predictPolicyLogit(prepared,policyPrefix,
                action.bits,cats,type,int(canonical.screenState),entity,ei,price);
            require(reference==optimized,"shared-prefix V4 logits are bit-identical for every source primitive");
            sourceLogits.emplace(action.bits,reference);
        }
        require(map || (bindings.supported && bindings.complete && !bindings.bindings.empty()),
            "semantic coverage fixture must be complete");
        OocGameContextModel provider(canonical,path);
        const auto actual=provider.legalActions(0);
        require(actual.size()==(map?primitive.size():representatives.size()),
            "adapter exposes one representative per equivalent card choice");
        std::set<std::string> keys;
        std::map<std::uint32_t,double> mass;
        std::map<std::uint32_t,unsigned> counts;
        for(std::size_t i=0;i<actual.size();++i) {
            const auto &candidate=provider.candidate(0,actual[i].id);
            require(keys.insert(candidate.key).second,"unique immutable semantic identities");
            require(map ? actual[i].id==primitive[i].bits : actual[i].id==i,
                "MAP preserves primitive IDs; semantic IDs are local ordinals");
            if (!map) require(candidate.semantic
                && candidate.key==canonicalOocSemanticActionKey(representatives[i].semantic)
                && candidate.primitive.bits==representatives[i].primitiveBits,
                "semantic keys and source projection match complete enumeration");
            mass[candidate.primitive.bits]+=actual[i].prior;
            ++counts[candidate.primitive.bits];
            if (execute && !map) {
                auto expected=detachedCopy(canonical);
                const auto result=executeOocSemanticAction(expected,*candidate.semantic);
                require(result.ok,"fixture semantic execution succeeds");
                collectForcedRewardGold(expected);
                const auto child=provider.sampleSuccessor(0,actual[i].id,rng);
                require(test::oocStateFingerprint(provider.state(child))==test::oocStateFingerprint(expected),
                    "adapter semantic edge reaches complete transactional successor");
                if(candidate.compoundSelector!=CardSelectScreenType::INVALID)
                    require(result.executedPrimitiveBits.size()==2 && expected.screenState!=ScreenState::CARD_SELECT,
                        "compound edge consumes both source and physical card target");
            }
        }
        bool qualified=v4DecisionSupported(canonical);
        std::set<std::uint32_t> established;
        for(auto a:primitive) qualified=established.insert(a.bits).second && qualified;
        std::set<std::uint32_t> completeSources;
        for(const auto &binding:bindings.bindings)
            if(GameAction(binding.primitiveBits).isValidAction(canonical))
                completeSources.insert(binding.primitiveBits);
        if(map) for(const auto &[bits,count]:counts) completeSources.insert(bits);
        qualified=qualified && established==completeSources;
        if(qualified) {
            std::map<std::string,std::vector<double>> grouped;
            for(const auto &binding:bindings.bindings)
                if(GameAction(binding.primitiveBits).isValidAction(canonical))
                    grouped[canonicalOocMctsChoiceKey(binding.semantic, &canonical)].push_back(sourceLogits.at(binding.primitiveBits));
            std::vector<double> classLogits;
            if(map) for(auto action:primitive) classLogits.push_back(sourceLogits.at(action.bits));
            else for(const auto &binding:representatives) {
                const auto &values=grouped.at(canonicalOocMctsChoiceKey(binding.semantic, &canonical));
                classLogits.push_back(std::accumulate(values.begin(),values.end(),0.0)/values.size());
            }
            const auto weights=oocPolicyWeights(classLogits);
            for(std::size_t i=0;i<actual.size();++i)
                require(actual[i].prior==weights[i]/counts.at(
                    provider.candidate(0,actual[i].id).primitive.bits),
                    "semantic prior preserves exact averaged V4 class logits and source split");
            for(auto action:actual) {
                const auto bits=provider.candidate(0,action.id).primitive.bits;
                require(std::abs(action.prior-mass.at(bits)/counts.at(bits))<1e-12,
                    "compound target weights split equally");
            }
        } else for(auto action:actual) require(action.prior==1,"unqualified V4 semantic roots are wholly uniform");
        const bool traceMapCase = map && !directTraceChecked;
        const bool traceCompoundCase = !map && !compoundTraceChecked
            && canonical.screenState==ScreenState::CARD_SELECT
            && canonical.info.selectScreenType==CardSelectScreenType::UPGRADE;
        if(traceMapCase || traceCompoundCase) {
            require(qualified,"trace fidelity fixture must be prior-covered");
            const auto tracePath = newTraceFile();
            OocAdapterOptions traceOptions;
            traceOptions.priorTracePath=tracePath;
            traceOptions.priorTraceRunSeed=44;
            traceOptions.priorTraceDecisionIndex=5;
            traceOptions.priorTraceSearchSeed=1234567;
            OocGameContextModel traced(canonical,path,{},traceOptions);
            const auto tracedActions=traced.legalActions(0);
            const auto tracedAgain=traced.legalActions(0);
            require(tracedActions.size()==actual.size() && tracedAgain.size()==actual.size(),
                "trace keeps production candidate count");
            for(std::size_t i=0;i<actual.size();++i)
                require(tracedActions[i].id==actual[i].id && tracedActions[i].prior==actual[i].prior
                    && tracedAgain[i].id==actual[i].id && tracedAgain[i].prior==actual[i].prior,
                    "tracing preserves candidate order and raw planner weights");
            std::ifstream traceInput(tracePath);
            std::string traceLine, extraLine;
            require(std::getline(traceInput,traceLine) && !std::getline(traceInput,extraLine),
                "first prior build writes exactly one trace row");
            const auto row=nlohmann::json::parse(traceLine);
            require(row.at("schemaVersion")==1 && row.at("runSeed")==44
                && row.at("decisionIndex")==5 && row.at("searchSeed")==1234567
                && row.at("modelStateId")==0 && row.at("stateRole")=="root"
                && row.at("floor")==canonical.floorNum && row.at("screenId")==int(canonical.screenState)
                && row.at("candidateCount")==actual.size() && row.at("sourcePriorCovered")==true
                && row.at("singleton")==false && row.at("uniformPrior")==false,
                "trace identifies the root prior context and population class");
            const auto tracedLogits=traced.policyLogits(0);
            require(row.at("teacherCandidateLogits").size()==actual.size()
                && row.at("teacherRawPriorWeights").size()==actual.size()
                && row.at("teacherNormalizedPrior").size()==actual.size(),
                "trace contains one candidate logit and prior per production candidate");
            double totalWeight=0;
            for(const auto &action:actual) totalWeight+=action.prior;
            require(std::isfinite(totalWeight) && totalWeight>0,"fixture prior mass is finite");
            for(std::size_t i=0;i<actual.size();++i) {
                const auto &candidate=provider.candidate(0,actual[i].id);
                const auto &tracedCandidate=row.at("candidates").at(i);
                require(tracedCandidate.at("candidateId")==candidate.id
                    && tracedCandidate.at("semanticKey")==candidate.key
                    && tracedCandidate.at("primitiveBits")==candidate.primitive.bits
                    && tracedCandidate.at("hasSemantic")==candidate.semantic.has_value()
                    && tracedCandidate.at("compoundSelector")==int(candidate.compoundSelector),
                    "trace candidate IDs, order and semantic metadata match production");
                std::vector<std::uint32_t> expectedGroup;
                if(!map) {
                    const auto choiceKey=canonicalOocMctsChoiceKey(*candidate.semantic, &canonical);
                    for(const auto &binding:bindings.bindings)
                        if(GameAction(binding.primitiveBits).isValidAction(canonical)
                            && canonicalOocMctsChoiceKey(binding.semantic, &canonical)==choiceKey)
                            expectedGroup.push_back(binding.primitiveBits);
                }
                require(tracedCandidate.at("priorSourceGroup").get<std::vector<std::uint32_t>>()
                    ==expectedGroup,"trace preserves current semantic source groups, including direct MAP empties");
                require(tracedLogits[i]==row.at("teacherCandidateLogits").at(i).get<double>()
                    && tracedLogits[i]==tracedCandidate.at("teacherCandidateLogit").get<double>()
                    && actual[i].prior==tracedCandidate.at("teacherRawPriorWeight").get<double>()
                    && std::abs(actual[i].prior/totalWeight
                        -tracedCandidate.at("teacherNormalizedPrior").get<double>())<1e-12,
                    "trace logits and normalized priors reproduce legalActions exactly");
            }
            std::vector<std::uint32_t> expectedSources;
            std::set<std::uint32_t> seenSources;
            if(map) {
                for(const auto action:primitive)
                    if(seenSources.insert(action.bits).second) expectedSources.push_back(action.bits);
            } else {
                for(const auto &representative:representatives) {
                    const auto choiceKey=canonicalOocMctsChoiceKey(representative.semantic, &canonical);
                    for(const auto &binding:bindings.bindings)
                        if(GameAction(binding.primitiveBits).isValidAction(canonical)
                            && canonicalOocMctsChoiceKey(binding.semantic, &canonical)==choiceKey
                            && seenSources.insert(binding.primitiveBits).second)
                            expectedSources.push_back(binding.primitiveBits);
                }
            }
            const auto &serializedSources=row.at("sourcePrimitives");
            require(serializedSources.size()==expectedSources.size()
                && sourceLogits.size()==expectedSources.size(),
                "one native source logit is captured per distinct source primitive");
            for(std::size_t i=0;i<expectedSources.size();++i) {
                const auto bits=expectedSources[i];
                const auto &source=serializedSources.at(i);
                require(source.at("primitiveBits")==bits
                    && source.at("teacherSourceLogit").get<double>()==sourceLogits.at(bits),
                    "trace source primitive order and native logits match current V4 inputs");
                int type,c1,c2,c3,d1,d2,d3,entityType,entityId; float price;
                const GameAction action(bits);
                strategicCands(canonical,action,type,c1,c2,c3,d1,d2,d3);
                tokEntity(canonical,action,entityType,entityId,price);
                require(source.at("actionType")==type
                    && source.at("cats")==nlohmann::json({c1,c2,c3,d1,d2,d3})
                    && source.at("screen")==int(canonical.screenState)
                    && source.at("entityType")==entityType && source.at("entityId")==entityId
                    && source.at("goldGePrice").get<float>()==price,
                    "trace source features match strategicCands and tokEntity");
            }
            const auto expectedTokens=buildTokState(canonical,path);
            const auto &serializedTokens=row.at("tokenState");
            require(serializedTokens.at("glob").size()==TOK_NGLOB,
                "trace captures all 42 exact state globals");
            for(int i=0;i<TOK_NGLOB;++i)
                require(serializedTokens.at("glob").at(i).get<float>()==expectedTokens.glob[i],
                    "trace globals equal buildTokState");
            for(const auto &[key,count,values,width] : std::array<std::tuple<const char *,int,const int *,int>,3>{
                    std::tuple{"deck",expectedTokens.nDk,&expectedTokens.dk[0][0],3},
                    std::tuple{"relic",expectedTokens.nRl,&expectedTokens.rl[0][0],2},
                    std::tuple{"potion",expectedTokens.nPt,&expectedTokens.pt[0][0],2}}) {
                const std::string block=key;
                const std::string countKey=block=="deck"?"nDk":block=="relic"?"nRl":"nPt";
                const auto &serialized=serializedTokens.at(block);
                require(serialized.at(countKey)==count && serialized.at("tokens").size()==count,
                    "trace token arrays use their exact valid lengths");
                for(int i=0;i<count;++i) for(int j=0;j<width;++j)
                    require(serialized.at("tokens").at(i).at(j)==values[i*width+j],
                        "trace valid token values equal buildTokState");
            }
            std::remove(tracePath.c_str());
            if(map) directTraceChecked=true; else compoundTraceChecked=true;

            if(traceCompoundCase) {
                const auto uniformTracePath=newTraceFile();
                std::size_t inferenceCalls=0;
                auto dependencies=defaultOocMctsDependencies();
                dependencies.policyLogits=[&](const GameContext &,const PathHistory &,
                                               const std::vector<GameAction> &actions) {
                    ++inferenceCalls; return std::vector<double>(actions.size(),0.0);
                };
                OocAdapterOptions uniformOptions;
                uniformOptions.uniformPrior=true;
                uniformOptions.priorTracePath=uniformTracePath;
                OocGameContextModel uniformProvider(canonical,path,{},uniformOptions,dependencies);
                const auto uniformActions=uniformProvider.legalActions(0);
                std::ifstream uniformInput(uniformTracePath);
                require(static_cast<bool>(std::getline(uniformInput,traceLine)),"uniform prior trace row exists");
                const auto uniformRow=nlohmann::json::parse(traceLine);
                require(!inferenceCalls && uniformRow.at("sourcePriorCovered")==true
                    && uniformRow.at("uniformPrior")==true
                    && !uniformRow.contains("tokenState") && !uniformRow.contains("sourcePrimitives")
                    && uniformActions.size()==actual.size(),
                    "explicit uniform trace stays compact and does not force policy inference");
                std::remove(uniformTracePath.c_str());
            }
            if(traceMapCase) {
                const auto singletonTracePath=newTraceFile();
                std::size_t inferenceCalls=0;
                auto dependencies=defaultOocMctsDependencies();
                dependencies.policyLogits=[&](const GameContext &,const PathHistory &,
                                               const std::vector<GameAction> &actions) {
                    ++inferenceCalls; return std::vector<double>(actions.size(),0.0);
                };
                OocAdapterOptions singletonOptions;
                singletonOptions.priorTracePath=singletonTracePath;
                singletonOptions.priorTraceRunSeed=44;
                singletonOptions.priorTraceDecisionIndex=5;
                singletonOptions.priorTraceSearchSeed=1234567;
                singletonOptions.rootPrimitiveBits=std::set<std::uint32_t>{primitive.front().bits};
                OocGameContextModel singletonProvider(canonical,path,{},singletonOptions,dependencies);
                const auto singletonAction=singletonProvider.soleLegalAction(0);
                sts::search::OocMctsConfig singletonConfig;
                singletonConfig.maxDepth=1;
                const auto singletonBypass=searchWithSoleRootShortcut(singletonProvider,
                    singletonConfig,singletonAction,1);
                std::ifstream singletonInput(singletonTracePath);
                require(static_cast<bool>(std::getline(singletonInput,traceLine)),
                    "singleton shortcut writes its prior trace row");
                std::string singletonExtraLine;
                const auto singletonRow=nlohmann::json::parse(traceLine);
                require(singletonAction && singletonBypass.selectedAction==singletonAction
                    && singletonBypass.metrics.trivialRootBypasses==1
                    && inferenceCalls==0 && singletonRow.at("singleton")==true
                    && singletonRow.at("candidateCount")==1
                    && singletonRow.at("runSeed")==44 && singletonRow.at("decisionIndex")==5
                    && singletonRow.at("searchSeed")==1234567
                    && singletonRow.at("candidates").at(0).at("candidateId")==*singletonAction
                    && singletonRow.at("candidates").at(0).at("searchPriorWeight")==1.0
                    && !singletonRow.contains("tokenState") && !singletonRow.contains("sourcePrimitives"),
                    "production singleton root shortcut emits exactly one compact unit-prior trace row");
                require(!std::getline(singletonInput,singletonExtraLine),
                    "singleton shortcut writes only one prior trace row");
                singletonInput.close();
                const auto singletonActions=singletonProvider.legalActions(0);
                require(singletonActions.size()==1 && singletonActions.front().id==*singletonAction
                    && singletonActions.front().prior==1.0,
                    "legalActions reuses the singleton shortcut prior");
                std::ifstream singletonPostInput(singletonTracePath);
                std::string singletonPostLine;
                singletonExtraLine.clear();
                require(static_cast<bool>(std::getline(singletonPostInput,singletonPostLine))
                    && nlohmann::json::parse(singletonPostLine)==singletonRow
                    && !std::getline(singletonPostInput,singletonExtraLine),
                    "singleton legalActions lookup does not duplicate its shortcut trace");
                std::remove(singletonTracePath.c_str());
            }
        }
        OocAdapterOptions uniform; uniform.uniformPrior=true;
        OocGameContextModel uniformProvider(canonical,path,{},uniform);
        for(auto action:uniformProvider.legalActions(0)) require(action.prior==1,"explicit uniform semantic siblings");
        require(test::oocStateFingerprint(canonical)==before
            && test::oocStateFingerprint(provider.state(0))==before,"semantic testing preserves immutable root");
        std::cout<<"semantic_adapter_coverage screen="<<int(canonical.screenState)
            <<" event="<<int(canonical.curEvent)<<" selector="<<int(canonical.info.selectScreenType)
            <<" count="<<actual.size()<<" v4_qualified="<<qualified<<'\n';
    };
    {
        auto cardsOnly = detachedCopy(gc);
        CardReward cards;
        for (auto id : {CardId::SEVER_SOUL, CardId::ANGER, CardId::FLEX}) cards.push_back(Card(id));
        cardsOnly.openCombatRewardScreen(Rewards(cards));
        checkCandidates(cardsOnly);
        cardsOnly.relics.add({RelicId::SINGING_BOWL, 0});
        checkCandidates(cardsOnly);
    }
    auto fixture=detachedCopy(gc);
    fixture.screenState=ScreenState::REST_ROOM;
    fixture.relics.add({RelicId::PEACE_PIPE,0});
    fixture.relics.add({RelicId::GIRYA,0});
    fixture.relics.add({RelicId::SHOVEL,0});
    checkCandidates(fixture);
    fixture=detachedCopy(gc); fixture.screenState=ScreenState::REST_ROOM;
    fixture.relics.add({RelicId::COFFEE_DRIPPER,0});
    fixture.relics.add({RelicId::FUSION_HAMMER,0}); fixture.obtainKey(Key::RUBY_KEY);
    checkCandidates(fixture);
    for(auto selector : {CardSelectScreenType::UPGRADE,CardSelectScreenType::REMOVE,
        CardSelectScreenType::TRANSFORM,CardSelectScreenType::TRANSFORM_UPGRADE,
        CardSelectScreenType::DUPLICATE,CardSelectScreenType::BONFIRE_SPIRITS}) {
        fixture=detachedCopy(gc); fixture.openCardSelectScreen(selector,1); checkCandidates(fixture);
        if (selector==CardSelectScreenType::UPGRADE || selector==CardSelectScreenType::REMOVE
                || selector==CardSelectScreenType::TRANSFORM
                || selector==CardSelectScreenType::TRANSFORM_UPGRADE) {
            OocGameContextModel provider(fixture,path);
            unsigned strikes=0;
            for(auto action:provider.legalActions(0)) {
                const auto &target=std::get<OocSelectorTarget>(provider.candidate(0,action.id).semantic->target);
                const auto *card=std::get_if<OocCardTarget>(&target.card);
                if(card && card->id==CardId::STRIKE_RED && !card->upgraded) {
                    ++strikes;
                    require(card->occurrence==0,"single-pick chooses first Strike occurrence");
                }
            }
            require(strikes==1 && provider.legalActions(0).size()<fixture.info.toSelectCards.size(),
                "single-pick remove/upgrade/transform collapses equivalent Strikes");
        }
    }
    {
        auto duplicates=detachedCopy(gc);
        duplicates.deck=Deck{};
        for(int i=0;i<3;++i) duplicates.deck.obtainRaw(Card(CardId::STRIKE_RED));
        for(int i=0;i<2;++i) duplicates.deck.obtainRaw(Card(CardId::DEFEND_RED));
        duplicates.deck.obtainRaw(Card(CardId::BASH));
        duplicates.openCardSelectScreen(CardSelectScreenType::UPGRADE,1);
        checkCandidates(duplicates);
        auto deps=defaultOocMctsDependencies();
        std::size_t scored=0;
        deps.policyLogits=[&](const GameContext &, const PathHistory &,
                               const std::vector<GameAction> &actions) {
            scored=actions.size();
            std::vector<double> logits;
            for(auto action:actions) {
                const auto &card=duplicates.info.toSelectCards[action.getIdx1()].card;
                const auto idx=action.getIdx1();
                logits.push_back(card.id==CardId::STRIKE_RED ? double(idx)
                    : card.id==CardId::DEFEND_RED ? double(2*idx-3) : 6.0);
            }
            return logits;
        };
        OocGameContextModel grouped(duplicates,path,{}, {},deps);
        const auto actions=grouped.legalActions(0);
        require(actions.size()==3 && scored==6,"six physical upgrades project to three scored classes");
        const auto expected=oocPolicyWeights({1.0,4.0,6.0});
        for(const auto action:actions) {
            const auto &target=std::get<OocSelectorTarget>(grouped.candidate(0,action.id).semantic->target);
            const auto &card=std::get<OocCardTarget>(target.card);
            const auto index=card.id==CardId::STRIKE_RED ? 0 : card.id==CardId::DEFEND_RED ? 1 : 2;
            require(std::abs(action.prior-expected[index])<1e-12,
                "duplicate multiplicity does not alter nonuniform upgrade priors");
        }
        OocAdapterOptions restricted;
        restricted.rootPrimitiveBits=std::set<std::uint32_t>{v4CandidateActions(duplicates)[1].bits};
        OocGameContextModel secondCopy(duplicates,path,{},restricted,deps);
        const auto restrictedActions=secondCopy.legalActions(0);
        require(restrictedActions.size()==1 && scored==6 && restrictedActions.front().prior==1.0
            && secondCopy.candidate(0,restrictedActions.front().id).primitive.bits
                ==*restricted.rootPrimitiveBits->begin(),
            "singleton root keeps its action identity and exact prior without another V4 score");
        // STS_OOC_MCTS_PRIOR=heart1: heart1's logits replace V4's where it scores every
        // source primitive (same grouping); a nullopt node keeps V4 and counts a fallback.
        bool heart1Scores=true;
        deps.heart1PolicyLogits=[&](const GameContext &state, const std::vector<GameAction> &actions,
                std::map<std::string,std::uint64_t> *) -> std::optional<std::vector<double>> {
            if(!heart1Scores) return std::nullopt;
            auto logits=deps.policyLogits(state,PathHistory{},actions);
            for(auto &l:logits) l=-l;
            return logits;
        };
        OocAdapterOptions heart1Options; heart1Options.heart1Prior=true;
        const auto priorsOf=[&](const OocGameContextModel &m) {
            std::vector<double> out(3);
            for(const auto action:m.legalActions(0)) {
                const auto &target=std::get<OocSelectorTarget>(m.candidate(0,action.id).semantic->target);
                const auto &card=std::get<OocCardTarget>(target.card);
                out[card.id==CardId::STRIKE_RED ? 0 : card.id==CardId::DEFEND_RED ? 1 : 2]=action.prior;
            }
            return out;
        };
        OocGameContextModel heart1Model(duplicates,path,{},heart1Options,deps);
        const auto heart1Priors=priorsOf(heart1Model);
        const auto heart1Expected=oocPolicyWeights({-1.0,-4.0,-6.0});
        for(int i=0;i<3;++i)
            require(std::abs(heart1Priors[i]-heart1Expected[i])<1e-12,"heart1 prior uses heart1 logits");
        require(heart1Model.continuationMetrics().heart1PriorNodes==1
            && heart1Model.continuationMetrics().heart1PriorFallbacks==0,"heart1 prior node counted");
        heart1Scores=false;
        OocGameContextModel fallbackModel(duplicates,path,{},heart1Options,deps);
        const auto fallbackPriors=priorsOf(fallbackModel);
        for(int i=0;i<3;++i)
            require(std::abs(fallbackPriors[i]-expected[i])<1e-12,"heart1 prior falls back to V4");
        require(fallbackModel.continuationMetrics().heart1PriorNodes==0
            && fallbackModel.continuationMetrics().heart1PriorFallbacks==1,"heart1 prior fallback counted");
        auto noHeart1=deps; noHeart1.heart1PolicyLogits=nullptr;
        bool threw=false;
        try { OocGameContextModel bad(duplicates,path,{},heart1Options,noHeart1); } catch(const std::runtime_error &) { threw=true; }
        require(threw,"heart1 prior without STS_OOC_HEART1 is fatal");
        one_combat::heart1::priorMappingSelfTest();
        {
            // STS_OOC_MCTS_PRIOR=heart1full: a full-belt shop adds discard sources V4 lacks,
            // so plain heart1 stays uniform there; heart1full scores it with heart1.
            auto shop=detachedCopy(gc);
            shop.screenState=ScreenState::SHOP_ROOM; shop.gold=200;
            std::fill(std::begin(shop.info.shop.prices),std::end(shop.info.shop.prices),-1);
            shop.info.shop.potions[0]=Potion::FIRE_POTION; shop.info.shop.potionPrice(0)=50;
            shop.potionCount=0;
            for(int slot=0;slot<shop.potionCapacity;++slot) { shop.potions[slot]=Potion::BLOCK_POTION; ++shop.potionCount; }
            auto shopDeps=deps; bool shopScores=true;
            shopDeps.heart1PolicyLogits=[&](const GameContext &, const std::vector<GameAction> &actions,
                    std::map<std::string,std::uint64_t> *) -> std::optional<std::vector<double>> {
                if(!shopScores) return std::nullopt;
                std::vector<double> logits;
                for(std::size_t i=0;i<actions.size();++i) logits.push_back(-double(i));
                return logits;
            };
            const auto flat=[](const std::vector<sts::search::OocPlannerAction> &actions) {
                for(const auto &a:actions) if(a.prior!=actions.front().prior) return false;
                return true;
            };
            OocGameContextModel plain(shop,path,{},heart1Options,shopDeps);
            const auto plainActions=plain.legalActions(0);
            require(plainActions.size()>2 && flat(plainActions),"heart1 keeps the uniform full-belt shop prior");
            auto fullOptions=heart1Options; fullOptions.heart1Coverage=true;
            OocGameContextModel full(shop,path,{},fullOptions,shopDeps);
            require(!flat(full.legalActions(0)) && full.continuationMetrics().heart1PriorNodes==1,
                "heart1full scores the full-belt shop with heart1");
            shopScores=false;
            OocGameContextModel unscored(shop,path,{},fullOptions,shopDeps);
            require(flat(unscored.legalActions(0)) && unscored.continuationMetrics().heart1PriorFallbacks==1,
                "heart1full without a heart1 score stays uniform");
            shopScores=true;
            auto remove=detachedCopy(duplicates);
            remove.openCardSelectScreen(CardSelectScreenType::REMOVE,1);
            OocGameContextModel removeFull(remove,path,{},fullOptions,shopDeps);
            const auto removeActions=removeFull.legalActions(0);
            require(removeActions.size()>2 && flat(removeActions)
                && removeFull.continuationMetrics().heart1PriorNodes==0,
                "heart1full keeps a REMOVE select uniform (student C has no CARD_SELECT training)");
            {
                // STS_OOC_MCTS_TARGET_PRIOR: smith targets share the smith prior by heart1's
                // logits on the UPGRADE select the smith opens, not equally.
                auto campfire=detachedCopy(duplicates); campfire.screenState=ScreenState::REST_ROOM;
                auto targetDeps=deps;
                targetDeps.heart1PolicyLogits=[](const GameContext &state, const std::vector<GameAction> &actions,
                        std::map<std::string,std::uint64_t> *) -> std::optional<std::vector<double>> {
                    std::vector<double> logits;
                    for(auto a:actions) logits.push_back(state.screenState==ScreenState::CARD_SELECT
                        && state.info.toSelectCards[a.getIdx1()].card.id==CardId::BASH ? 3.0 : 0.0);
                    return logits;
                };
                const auto smithPriors=[&](const OocAdapterOptions &o, double &smithMass, double &other) {
                    OocGameContextModel m(campfire,path,{},o,targetDeps);
                    std::map<CardId,double> out; smithMass=0; other=0;
                    for(const auto action:m.legalActions(0)) {
                        const auto &c=m.candidate(0,action.id);
                        if(c.compoundSelector!=CardSelectScreenType::UPGRADE) { other+=action.prior; continue; }
                        out[std::get<OocCardTarget>(c.semantic->target).id]=action.prior; smithMass+=action.prior;
                    }
                    const auto &reasons=m.continuationMetrics().heart1PriorReasons;
                    const auto it=reasons.find("target:scored");
                    return std::make_pair(out,it==reasons.end() ? 0ull : it->second);
                };
                double equalMass=0,equalOther=0,targetMass=0,targetOther=0;
                const auto [equal,equalScored]=smithPriors(heart1Options,equalMass,equalOther);
                auto targetOptions=heart1Options; targetOptions.targetPrior=true;
                const auto [weighted,targetScored]=smithPriors(targetOptions,targetMass,targetOther);
                require(equal.size()==3 && weighted.size()==3 && equalScored==0 && targetScored==1
                    && std::abs(equal.at(CardId::BASH)-equal.at(CardId::STRIKE_RED))<1e-12,
                    "plain heart1 splits the smith prior equally; target prior scores the group once");
                // Physical selects: 3 Strikes, 2 Defends, Bash; each card class is one candidate.
                const double z=3*1.0+2*1.0+std::exp(3.0);
                require(std::abs(targetMass-equalMass)<1e-12 && std::abs(targetOther-equalOther)<1e-12
                    && std::abs(weighted.at(CardId::BASH)-equalMass*std::exp(3.0)/z/(std::exp(3.0)/z+2.0/z))<1e-9
                    && std::abs(weighted.at(CardId::STRIKE_RED)-weighted.at(CardId::DEFEND_RED))<1e-12,
                    "target prior keeps the smith mass and splits it by heart1's select probabilities");
                OocAdapterOptions targetOnly; targetOnly.targetPrior=true;
                bool targetRejected=false;
                try { OocGameContextModel bad(campfire,path,{},targetOnly,targetDeps); }
                catch(const std::invalid_argument &) { targetRejected=true; }
                require(targetRejected,"target prior without the heart1 prior is rejected");
            }
            OocAdapterOptions coverageOnly; coverageOnly.heart1Coverage=true;
            bool rejected=false;
            try { OocGameContextModel bad(shop,path,{},coverageOnly,shopDeps); } catch(const std::invalid_argument &) { rejected=true; }
            require(rejected,"heart1 coverage without the heart1 prior is rejected");
        }
    }
    {
        // Keys off: a sapphire key must not compete with its paired relic.
        auto chest=detachedCopy(gc); chest.screenState=ScreenState::REWARDS;
        chest.info.rewardsContainer.clear();
        chest.info.rewardsContainer.addRelic(RelicId::ANCHOR);
        chest.info.rewardsContainer.sapphireKey=true;
        CardReward cards; cards.push_back(Card(CardId::ANGER)); cards.push_back(Card(CardId::BASH));
        chest.info.rewardsContainer.addCardReward(cards); // V4 scores only screens with cards
        const auto effects=[&](const OocGameContextModel &m) {
            std::vector<OocSemanticEffect> out;
            for(auto a:m.legalActions(0)) out.push_back(m.candidate(0,a.id).semantic->effect);
            return out;
        };
        const auto has=[](const std::vector<OocSemanticEffect> &v,OocSemanticEffect e) {
            return std::find(v.begin(),v.end(),e)!=v.end();
        };
        OocGameContextModel withKeys(chest,path,{},{},defaultOocMctsDependencies());
        require(has(effects(withKeys),OocSemanticEffect::TAKE_KEY),"keys-on chest offers the sapphire key");
        OocAdapterOptions noKeys; noKeys.collectKeys=false;
        auto deps=defaultOocMctsDependencies();
        bool scoredKey=false;
        deps.policyLogits=[&](const GameContext &, const PathHistory &, const std::vector<GameAction> &actions) {
            std::vector<double> logits;
            for(auto a:actions) {
                scoredKey=scoredKey || a.getRewardsActionType()==GameAction::RewardsActionType::KEY;
                logits.push_back(double(logits.size()));
            }
            return logits;
        };
        OocGameContextModel withoutKeys(chest,path,{},noKeys,deps);
        const auto filtered=effects(withoutKeys);
        const auto priors=withoutKeys.legalActions(0);
        require(!has(filtered,OocSemanticEffect::TAKE_KEY) && has(filtered,OocSemanticEffect::TAKE_RELIC)
            && has(filtered,OocSemanticEffect::LEAVE_REWARDS) && !scoredKey
            && std::any_of(priors.begin(),priors.end(),[&](auto a){return a.prior!=priors.front().prior;}),
            "keys-off chest drops only the key and keeps the policy prior");
    }
    fixture=detachedCopy(gc); fixture.screenState=ScreenState::SHOP_ROOM;
    fixture.gold=500; fixture.info.shop.setup(fixture);
    std::fill(std::begin(fixture.info.shop.prices), std::end(fixture.info.shop.prices), -1);
    fixture.info.shop.relics[0]=RelicId::PRISMATIC_SHARD; fixture.info.shop.relicPrice(0)=50;
    fixture.info.shop.relics[1]=RelicId::ANCHOR; fixture.info.shop.relicPrice(1)=50;
    checkCandidates(fixture);
    {
        const auto all = GameAction::getAllActionsInState(fixture);
        const auto v4 = v4CandidateActions(fixture);
        const auto semantic = enumerateOocSemanticPrimitiveBindings(fixture);
        const auto isShardPrimitive = [&](const GameAction primitive) {
            return primitive.getRewardsActionType() == GameAction::RewardsActionType::RELIC
                && primitive.getIdx1() >= 0 && primitive.getIdx1() < 3
                && fixture.info.shop.relics[primitive.getIdx1()] == RelicId::PRISMATIC_SHARD;
        };
        const auto hasShardPrimitive = [&](const std::vector<GameAction> &actions) {
            return std::any_of(actions.begin(), actions.end(), isShardPrimitive);
        };
        const auto hasRelicBinding = [&](RelicId relic) {
            return std::any_of(semantic.bindings.begin(), semantic.bindings.end(), [&](const auto &binding) {
                if (binding.semantic.effect != OocSemanticEffect::BUY_RELIC) return false;
                const auto &target = std::get<OocShopTarget>(binding.semantic.target);
                return std::get<RelicId>(target.entity) == relic;
            });
        };
        require(hasShardPrimitive(all), "shop fixture did not retain displayed Prismatic Shard");
        require(!hasShardPrimitive(v4), "V4 shop candidates retained Prismatic Shard");
        require(semantic.supported && semantic.complete, "semantic shop enumeration unsupported");
        require(!hasRelicBinding(RelicId::PRISMATIC_SHARD),
            "semantic shop bindings retained Prismatic Shard");
        require(hasRelicBinding(RelicId::ANCHOR), "semantic shop bindings lost ordinary relic");
        require(std::any_of(semantic.bindings.begin(), semantic.bindings.end(), [](const auto &binding) {
                    return binding.semantic.effect == OocSemanticEffect::LEAVE_SHOP;
                }), "semantic shop bindings lost Leave");

        OocGameContextModel shop(fixture,path);
        const auto legal = shop.legalActions(0);
        require(!shop.isLeafBoundary(0) && !legal.empty(),
            "Prismatic Shard made semantic shop root unsupported");
        bool mctsAnchor = false, mctsLeave = false;
        for (const auto action : legal) {
            const auto &candidate = shop.candidate(0, action.id);
            require(candidate.semantic.has_value(), "shop MCTS candidate lost semantic identity");
            if (candidate.semantic->effect == OocSemanticEffect::BUY_RELIC) {
                const auto &target = std::get<OocShopTarget>(candidate.semantic->target);
                const auto relic = std::get<RelicId>(target.entity);
                require(relic != RelicId::PRISMATIC_SHARD,
                    "semantic OOC MCTS retained Prismatic Shard");
                mctsAnchor |= relic == RelicId::ANCHOR;
            }
            mctsLeave |= candidate.semantic->effect == OocSemanticEffect::LEAVE_SHOP;
        }
        require(mctsAnchor && mctsLeave,
            "semantic OOC MCTS lost ordinary relic or Leave candidate");

        auto fallbackShop = detachedCopy(fixture);
        search::ScumSearchAgent2 fallbackAgent;
        runFullRunOocPolicyStep(fallbackShop, fallbackAgent, false, true);
        require(!fallbackShop.relics.has(RelicId::PRISMATIC_SHARD),
            "full-run OOC shop fallback bought Prismatic Shard");
    }
    {
        OocGameContextModel shop(fixture,path);
        std::set<unsigned> strikeOccurrences;
        unsigned removals=0;
        for(auto a:shop.legalActions(0)) {
            const auto &c=shop.candidate(0,a.id);
            if(c.semantic->effect!=OocSemanticEffect::REMOVE_CARD) continue;
            ++removals;
            const auto &target=std::get<OocTransactionTarget>(c.semantic->target).card;
            if(target.id==CardId::STRIKE_RED) strikeOccurrences.insert(target.occurrence);
        }
        auto selector=detachedCopy(fixture); GameAction(GameAction::RewardsActionType::CARD_REMOVE).execute(selector);
        require(removals<selector.info.toSelectCards.size() && strikeOccurrences==std::set<unsigned>{0},
            "shop removal searches one first Strike occurrence");
    }
    for(auto event : {Event::BIG_FISH,Event::THE_CLERIC,Event::LIVING_WALL,
        Event::TRANSMORGRIFIER,Event::UPGRADE_SHRINE,Event::DUPLICATOR,
        Event::OMINOUS_FORGE,Event::ANCIENT_WRITING,Event::OLD_BEGGAR,
        Event::DESIGNER_IN_SPIRE,Event::PURIFIER,Event::WING_STATUE}) {
        fixture=detachedCopy(gc); fixture.screenState=ScreenState::EVENT_SCREEN;
        fixture.curEvent=event; fixture.gold=500; fixture.info.hpAmount0=20;
        fixture.info.hpAmount1=5; fixture.info.upgradeOne=true;
        fixture.info.cleanUpIsRemoveCard=true; checkCandidates(fixture);
    }
    fixture=detachedCopy(gc); fixture.setupTreasureRoom(); checkCandidates(fixture);
    {
        OocGameContextModel chest(fixture,path);
        const auto open=sourceId(chest,0);
        const auto child=chest.sampleSuccessor(0,open,rng);
        require(chest.candidate(0,open).semantic->effect==OocSemanticEffect::OPEN_CHEST
            && chest.state(child).screenState==ScreenState::REWARDS,
            "chest opening stops at newly revealed rewards");
    }
    fixture=detachedCopy(gc); fixture.screenState=ScreenState::BOSS_RELIC_REWARDS;
    fixture.info.bossRelics[0]=RelicId::ASTROLABE;
    fixture.info.bossRelics[1]=RelicId::COFFEE_DRIPPER;
    fixture.info.bossRelics[2]=RelicId::FUSION_HAMMER; checkCandidates(fixture);
    checkCandidates(gc,false);
    {
        // Compare a fixed-work search using the original full policy head with
        // the shared-prefix path, including all root statistics, successor
        // fingerprints and the caller-owned search RNG state after each draw.
        auto legacyDependencies=defaultOocMctsDependencies();
        legacyDependencies.policyLogits=[](const GameContext &source,const PathHistory &history,
                                            const std::vector<GameAction> &actions) {
            const TokState tokens=buildTokState(source,history);
            const auto state=g_oocStrategicTokNet.prepareState(tokens.glob,tokens.nDk,tokens.dk,
                tokens.nRl,tokens.rl,tokens.nPt,tokens.pt);
            std::vector<double> logits; logits.reserve(actions.size());
            for(const auto action:actions) {
                int type,c1,c2,c3,d1,d2,d3,et,ei; float price;
                strategicCands(source,action,type,c1,c2,c3,d1,d2,d3);
                tokEntity(source,action,et,ei,price);
                const int cats[6]={c1,c2,c3,d1,d2,d3};
                const float entity[4]={float(et==0),float(et==1),float(et==2),float(et==3)};
                logits.push_back(g_oocStrategicTokNet.predictPolicyLogit(state,action.bits,cats,
                    type,int(source.screenState),entity,ei,price));
            }
            return logits;
        };
        struct PrimitiveMapRoot final : OocGenerativeModel {
            OocGameContextModel adapter;
            std::vector<OocPlannerAction> primitiveActions;
            std::vector<std::string> successorFingerprints;
            std::vector<std::uint64_t> rngAfterDraw;
            PrimitiveMapRoot(const GameContext &g,const PathHistory &p,const OocMctsDependencies &deps)
                :adapter(g,p,{}, {},deps) {
                const auto actions=v4CandidateActions(g);
                const auto weights=oocPolicyWeights(adapter.policyLogits(0));
                for(std::size_t i=0;i<actions.size();++i) primitiveActions.push_back({actions[i].bits,weights[i]});
            }
            std::optional<double> terminalValue(OocStateId id) const override { return adapter.terminalValue(id); }
            bool isLeafBoundary(OocStateId id) const override { return id != 0 || adapter.isLeafBoundary(id); }
            std::vector<OocPlannerAction> legalActions(OocStateId id) const override {
                require(id==0,"bounded MAP comparison never expands a child"); return primitiveActions;
            }
            OocStateId sampleSuccessor(OocStateId id,OocActionId a,std::mt19937_64 &r) override {
                const auto child=adapter.sampleSuccessor(id,a,r);
                auto copy=r; rngAfterDraw.push_back(copy());
                successorFingerprints.push_back(test::oocStateFingerprint(adapter.state(child)));
                return child;
            }
            double leafValue(OocStateId id) const override { return adapter.leafValue(id); }
            double evaluateLeaf(OocStateId id,std::mt19937_64 &r) override { return adapter.evaluateLeaf(id,r); }
            bool isDeterministicTransition(OocStateId id,OocActionId a) const override {
                return adapter.isDeterministicTransition(id,a);
            }
        } baseline(gc,path,legacyDependencies);
        struct CurrentPrefixRoot final : OocGenerativeModel {
            OocGameContextModel adapter;
            std::vector<std::string> successorFingerprints;
            std::vector<std::uint64_t> rngAfterDraw;
            CurrentPrefixRoot(const GameContext &g,const PathHistory &p):adapter(g,p) {}
            std::optional<double> terminalValue(OocStateId id) const override { return adapter.terminalValue(id); }
            bool isLeafBoundary(OocStateId id) const override { return id != 0 || adapter.isLeafBoundary(id); }
            std::vector<OocPlannerAction> legalActions(OocStateId id) const override { return adapter.legalActions(id); }
            OocStateId sampleSuccessor(OocStateId id,OocActionId a,std::mt19937_64 &r) override {
                const auto child=adapter.sampleSuccessor(id,a,r);
                auto copy=r; rngAfterDraw.push_back(copy());
                successorFingerprints.push_back(test::oocStateFingerprint(adapter.state(child)));
                return child;
            }
            double leafValue(OocStateId id) const override { return adapter.leafValue(id); }
            double evaluateLeaf(OocStateId id,std::mt19937_64 &r) override { return adapter.evaluateLeaf(id,r); }
            bool isDeterministicTransition(OocStateId id,OocActionId a) const override {
                return adapter.isDeterministicTransition(id,a);
            }
        } current(gc,path);
        OocMctsConfig config;
        const auto expected=OocMctsPlanner(config).search(baseline,0,32);
        const auto actual=OocMctsPlanner(config).search(current,0,32);
        require(actual.selectedAction==expected.selectedAction && actual.rootActions.size()==expected.rootActions.size()
            && actual.metrics.simulations==expected.metrics.simulations
            && actual.metrics.transitionSamples==expected.metrics.transitionSamples
            && actual.metrics.decisionNodes==expected.metrics.decisionNodes
            && actual.metrics.chanceNodes==expected.metrics.chanceNodes
            && actual.metrics.leafEvaluations==expected.metrics.leafEvaluations
            && actual.metrics.expandedNodes0Actions==expected.metrics.expandedNodes0Actions
            && actual.metrics.expandedNodes1Action==expected.metrics.expandedNodes1Action
            && actual.metrics.expandedNodes2Actions==expected.metrics.expandedNodes2Actions
            && actual.metrics.expandedNodes3PlusActions==expected.metrics.expandedNodes3PlusActions,
            "fixed-work MAP search action and expansion metrics remain exactly equivalent");
        for(std::size_t i=0;i<actual.rootActions.size();++i) {
            const auto &a=actual.rootActions[i], &b=expected.rootActions[i];
            require(a.id==b.id && a.prior==b.prior && a.visits==b.visits && a.q==b.q,
                "MAP planner statistics remain exactly equivalent");
        }
        require(current.successorFingerprints==baseline.successorFingerprints
            && current.rngAfterDraw==baseline.rngAfterDraw,
            "fixed-work successors and search RNG draw sequence remain exactly equivalent");
    }
    auto checkSequential=[&](GameContext source, std::uint32_t sourceBits,int picks) {
        checkCandidates(source);
        OocGameContextModel provider(source,path);
        const auto id=sourceId(provider,sourceBits);
        require(provider.candidate(0,id).compoundSelector==CardSelectScreenType::INVALID,
            "multi-select/random-reveal source remains a separate edge");
        auto child=provider.sampleSuccessor(0,id,rng);
        for(int pick=0;pick<picks;++pick) {
            const auto &state=provider.state(child);
            require(state.screenState==ScreenState::CARD_SELECT,"source/pick retains selector boundary");
            const auto actions=provider.legalActions(child);
            require(!actions.empty() && actions.size()<=state.info.toSelectCards.size(),
                "one current pick per equivalent card without subset cross-product");
            for(auto a:actions) {
                const auto &target=std::get<OocSelectorTarget>(provider.candidate(child,a.id).semantic->target);
                require(target.completedPicks==pick && target.requiredPicks==picks,"selector progress re-enumerated");
            }
            checkCandidates(detachedCopy(state));
            child=provider.sampleSuccessor(child,actions.front().id,rng);
        }
        require(provider.state(child).screenState!=ScreenState::CARD_SELECT,"last sequential pick completes");
    };
    checkSequential(fixture,0,3);
    {
        auto repeated=detachedCopy(gc);
        repeated.openCardSelectScreen(CardSelectScreenType::TRANSFORM_UPGRADE,3);
        OocGameContextModel provider(repeated,path);
        OocStateId current=0;
        for(unsigned pick=0;pick<3;++pick) {
            unsigned strikes=0;
            std::optional<OocActionId> selected;
            for(auto action:provider.legalActions(current)) {
                const auto &target=std::get<OocSelectorTarget>(provider.candidate(current,action.id).semantic->target);
                const auto *card=std::get_if<OocCardTarget>(&target.card);
                if(card && card->id==CardId::STRIKE_RED && !card->upgraded) {
                    ++strikes;
                    require(card->occurrence==pick,"multi-pick resolves first remaining Strike");
                    selected=action.id;
                }
            }
            require(strikes==1 && selected,"multi-pick searches one equivalent Strike");
            current=provider.sampleSuccessor(current,*selected,rng);
        }
        require(provider.state(current).screenState!=ScreenState::CARD_SELECT,
            "three equivalent picks complete the selector");
    }
    fixture=detachedCopy(gc); fixture.screenState=ScreenState::EVENT_SCREEN; fixture.curEvent=Event::AUGMENTER;
    checkSequential(fixture,1,2);
    fixture.curEvent=Event::THE_LIBRARY; checkSequential(fixture,0,1);
    fixture=detachedCopy(gc); fixture.screenState=ScreenState::REWARDS;
    Rewards visibleRewards; visibleRewards.addGold(25); visibleRewards.addRelic(RelicId::ANCHOR);
    visibleRewards.addPotion(Potion::FIRE_POTION);
    CardReward visibleCards; visibleCards.push_back(Card(CardId::INFLAME));
    visibleCards.push_back(Card(CardId::BASH)); visibleRewards.addCardReward(visibleCards);
    fixture.info.rewardsContainer=visibleRewards; checkCandidates(fixture);
    fixture.relics.add({RelicId::SINGING_BOWL,0}); checkCandidates(fixture);
    for (auto bottle : {RelicId::BOTTLED_FLAME, RelicId::BOTTLED_LIGHTNING,
                        RelicId::BOTTLED_TORNADO}) {
        fixture.info.rewardsContainer.relics[0]=bottle;
        checkCandidates(fixture);
        OocGameContextModel bottleChoices(fixture,path);
        bool canTake=false, canSkip=false;
        for (const auto &action : bottleChoices.legalActions(0)) {
            const auto &candidate=bottleChoices.candidate(0,action.id);
            if (!candidate.semantic) continue;
            canTake |= candidate.semantic->effect==OocSemanticEffect::TAKE_RELIC;
            canSkip |= candidate.semantic->effect==OocSemanticEffect::LEAVE_REWARDS;
        }
        require(canTake && canSkip && bottleChoices.state(0).info.rewardsContainer.relicCount==1,
            "Bottled relic remains optional after forced gold collection");
    }
    fixture.info.rewardsContainer.relics[0]=RelicId::BOTTLED_FLAME;
    GameAction(GameAction::RewardsActionType::RELIC).execute(fixture);
    require(fixture.info.selectScreenType==CardSelectScreenType::BOTTLE,"bottle fixture opens selector");
    checkCandidates(fixture);
    {
        auto fresh=detachedCopy(gc); fresh.openCardSelectScreen(CardSelectScreenType::REMOVE,1);
        OocGameContextModel provider(fresh,path);
        const auto chosen=provider.candidate(0,provider.legalActions(0).front().id);
        std::reverse(fresh.info.toSelectCards.begin(),fresh.info.toSelectCards.end());
        auto expected=detachedCopy(fresh);
        require(executeOocSemanticAction(expected,*chosen.semantic).ok,"fresh resolution oracle");
        std::string error;
        require(executeOocMctsRoot(fresh,chosen,error)
            && test::oocStateFingerprint(fresh)==test::oocStateFingerprint(expected),
            "fresh root resolves physical identity after selector order changes");
        const auto before=test::oocStateFingerprint(fresh);
        require(!executeOocMctsRoot(fresh,chosen,error)
            && test::oocStateFingerprint(fresh)==before,"stale root identity executes nothing");
        fresh=detachedCopy(gc); fresh.openCardSelectScreen(CardSelectScreenType::REMOVE,1);
        const auto observerBefore=test::oocStateFingerprint(fresh);
        auto savedObserver=std::move(g_onGameActionExecute); int callbacks=0;
        g_onGameActionExecute=[&](std::uint32_t,const GameContext *) { ++callbacks; };
        const bool executed=executeOocMctsRoot(fresh,chosen,error);
        g_onGameActionExecute=std::move(savedObserver);
        require(!executed && callbacks==0 && test::oocStateFingerprint(fresh)==observerBefore,
            "active observer rejects semantic live execution before mutation");
        fresh.info.toSelectCards.push_back(fresh.info.toSelectCards.front());
        const auto ambiguousBefore=test::oocStateFingerprint(fresh);
        require(!executeOocMctsRoot(fresh,chosen,error)
            && test::oocStateFingerprint(fresh)==ambiguousBefore,
            "ambiguous semantic enumeration rejects live root without mutation");
    }
    fixture=detachedCopy(gc); fixture.screenState=ScreenState::CARD_SELECT;
    fixture.info.selectScreenType=CardSelectScreenType::INVALID;
    OocGameContextModel unsupportedSelector(fixture,path);
    require(unsupportedSelector.isLeafBoundary(0),"invalid selector remains boundary");
    fixture=detachedCopy(gc); fixture.curMapNodeY=14;
    OocGameContextModel lastRow(fixture,path); require(lastRow.isLeafBoundary(0),"map row 14 boundary");
    fixture=detachedCopy(gc); fixture.map=nullptr;
    OocGameContextModel noMap(fixture,path); require(noMap.isLeafBoundary(0),"missing map boundary");
    fixture=detachedCopy(gc); fixture.screenState=ScreenState::EVENT_SCREEN; fixture.curEvent=Event::MATCH_AND_KEEP;
    OocGameContextModel match(fixture,path); require(match.isLeafBoundary(0),"match and keep boundary");
    {
        // Match and Keep valuation: a lone-card offer on a detached copy; the
        // caller's step decides, and the source state is never touched.
        const auto sourceBefore=test::oocStateFingerprint(gc);
        const auto take=[](GameContext &offer){ GameAction(GameAction::RewardsActionType::CARD,0,0).execute(offer); };
        const auto skip=[](GameContext &offer){ offer.regainControl(); };
        require(oocHypotheticalCardTaken(gc,path,sts::Card(CardId::ANGER),take),"hypothetical offer take");
        require(!oocHypotheticalCardTaken(gc,path,sts::Card(CardId::ANGER),skip),"hypothetical offer skip");
        require(test::oocStateFingerprint(gc)==sourceBefore,"hypothetical offer leaves source untouched");
    }
    // Live outcome sampling must not optimize against copied future streams or
    // freeze random successors in the deterministic-edge cache.
    {
        OocAdapterOptions sampled; sampled.sampleNoncombat=true;
        const auto visible = [](const GameContext &g) {
            std::string result=std::to_string(int(g.screenState))+":"+std::to_string(g.curHp)+":"+std::to_string(g.gold);
            for(const auto &c:g.deck.cards) result += ":"+std::to_string(int(c.id))+"/"+std::to_string(c.isUpgraded());
            for(const auto &r:g.relics.relics) result += ":r"+std::to_string(int(r.id));
            if(g.screenState==ScreenState::BATTLE) result += ":fight"+std::to_string(int(g.info.encounter));
            const auto actions=enumerateOocSemanticActions(g);
            for(const auto &a:actions.actions) result += ":"+canonicalOocSemanticActionKey(a);
            return result;
        };
        const auto varied = [&](GameContext source,OocSemanticEffect effect,OocSemanticSource origin) {
            OocGameContextModel adapter(source,path,{},sampled);
            std::optional<OocActionId> selected;
            for(auto a:adapter.legalActions(0)) {
                const auto &c=adapter.candidate(0,a.id);
                if(c.semantic && c.semantic->effect==effect && c.semantic->source==origin) { selected=a.id; break; }
            }
            require(selected.has_value(),"stochastic fixture has requested semantic edge");
            const auto before=test::oocStateFingerprint(source);
            std::set<std::string> outcomes;
            std::mt19937_64 draws(91234);
            for(int n=0;n<32;++n) {
                auto child=adapter.sampleSuccessor(0,*selected,draws);
                outcomes.insert(visible(adapter.state(child)));
                require(!adapter.isDeterministicTransition(0,*selected),"random outcome never cached as deterministic");
            }
            require(outcomes.size()>1,"unknown noncombat effect produces multiple sampled outcomes");
            require(test::oocStateFingerprint(source)==before && test::oocStateFingerprint(adapter.state(0))==before,
                "sampled outcomes preserve live and immutable parent state");
            std::cout<<"sampled_ooc effect="<<int(effect)<<" source="<<int(origin)<<" outcomes="<<outcomes.size()<<'\n';
        };
        for(auto event:{Event::LIVING_WALL,Event::TRANSMORGRIFIER}) {
            auto source=detachedCopy(gc); source.screenState=ScreenState::EVENT_SCREEN; source.curEvent=event;
            varied(source,OocSemanticEffect::TRANSFORM_CARD,OocSemanticSource::EVENT);
        }
        for(auto stream:{CARD_RNG,MISC_RNG,NEOW_RNG}) {
            auto source=detachedCopy(gc); source.openCardSelectScreen(CardSelectScreenType::TRANSFORM,1);
            source.info.transformRng=stream;
            varied(source,OocSemanticEffect::TRANSFORM_CARD,OocSemanticSource::SELECTOR);
        }
        auto source=detachedCopy(gc); source.openCardSelectScreen(CardSelectScreenType::TRANSFORM_UPGRADE,1);
        varied(source,OocSemanticEffect::TRANSFORM_UPGRADE_CARD,OocSemanticSource::SELECTOR);
        source=detachedCopy(gc); source.screenState=ScreenState::EVENT_SCREEN; source.curEvent=Event::THE_LIBRARY;
        varied(source,OocSemanticEffect::EVENT_CHOICE,OocSemanticSource::EVENT);
        source=detachedCopy(gc); source.setupTreasureRoom();
        varied(source,OocSemanticEffect::OPEN_CHEST,OocSemanticSource::TREASURE);
        source=detachedCopy(gc); source.screenState=ScreenState::EVENT_SCREEN; source.curEvent=Event::DEAD_ADVENTURER;
        source.setupEvent(); varied(source,OocSemanticEffect::EVENT_CHOICE,OocSemanticSource::EVENT);
        source=detachedCopy(gc); source.screenState=ScreenState::BOSS_RELIC_REWARDS;
        source.info.bossRelics[0]=RelicId::PANDORAS_BOX;
        source.info.bossRelics[1]=RelicId::COFFEE_DRIPPER; source.info.bossRelics[2]=RelicId::FUSION_HAMMER;
        // Select Pandora explicitly; canonical relic ordering need not put it first.
        OocGameContextModel pandora(source,path,{},sampled); std::set<std::string> pandoraOutcomes;
        std::set<std::uint64_t> pandoraKeys;
        std::mt19937_64 pandoraDraws(819);
        for(auto action:pandora.legalActions(0)) {
            const auto &c=pandora.candidate(0,action.id);
            if(c.semantic->effect!=OocSemanticEffect::TAKE_BOSS_RELIC
                || std::get<OocRelicTarget>(c.semantic->target).relic!=RelicId::PANDORAS_BOX) continue;
            for(int n=0;n<16;++n) {
                const auto child=pandora.sampleSuccessor(0,action.id,pandoraDraws);
                pandoraOutcomes.insert(visible(pandora.state(child)));
                pandoraKeys.insert(*pandora.outcomeEquivalenceKey(child));
            }
        }
        require(pandoraOutcomes.size()>1,"Pandora random transformations resampled");
        require(pandoraKeys.size()==pandoraOutcomes.size(),"distinct visible outcomes never share an equivalence key");
        source=detachedCopy(gc); source.screenState=ScreenState::REST_ROOM; source.relics.add({RelicId::SHOVEL,0});
        varied(source,OocSemanticEffect::DIG,OocSemanticSource::CAMPFIRE);
        source=detachedCopy(gc); source.screenState=ScreenState::SHOP_ROOM; source.gold=999;
        source.relics.add({RelicId::THE_COURIER,0}); source.info.shop.setup(source);
        varied(source,OocSemanticEffect::BUY_CARD,OocSemanticSource::SHOP);
        // A deterministic upgrade remains the same public effect, even though
        // its unobserved future receives a fresh particle on every draw.
        source=detachedCopy(gc); source.openCardSelectScreen(CardSelectScreenType::UPGRADE,1);
        OocGameContextModel upgrades(source,path,{},sampled);
        const auto upgrade=upgrades.legalActions(0).front().id;
        std::mt19937_64 draws(712);
        const auto first=upgrades.sampleSuccessor(0,upgrade,draws);
        const auto second=upgrades.sampleSuccessor(0,upgrade,draws);
        require(visible(upgrades.state(first))==visible(upgrades.state(second)),"deterministic public upgrade preserved");
        require(upgrades.outcomeEquivalenceKey(first) && upgrades.outcomeEquivalenceKey(first)==upgrades.outcomeEquivalenceKey(second),
            "re-sampled futures of one public upgrade are search-equivalent");
        OocGameContextModel exactUpgrades(source,path);
        require(!exactUpgrades.outcomeEquivalenceKey(0),"exact-replay futures are never merged");
        // Same planner draws, different true seed/stream states/hidden order:
        // both hypothetical futures must be exactly the same.
        source=detachedCopy(gc); source.setupTreasureRoom();
        auto altered=detachedCopy(source);
        altered.seed ^= 0xCAFEBABE;
        for(auto stream:{&altered.aiRng,&altered.cardRandomRng,&altered.cardRng,&altered.eventRng,
                &altered.mathUtilRng,&altered.merchantRng,&altered.miscRng,&altered.monsterHpRng,
                &altered.monsterRng,&altered.neowRng,&altered.potionRng,&altered.relicRng,
                &altered.shuffleRng,&altered.treasureRng}) { stream->seed0 ^= 123; stream->seed1 ^= 456; }
        for(auto pool:{&altered.commonRelicPool,&altered.uncommonRelicPool,&altered.rareRelicPool,
                &altered.shopRelicPool,&altered.bossRelicPool}) std::reverse(pool->begin(),pool->end());
        std::reverse(altered.monsterList.begin(),altered.monsterList.end());
        std::reverse(altered.eliteMonsterList.begin(),altered.eliteMonsterList.end());
        std::reverse(altered.colorlessCardPool.begin(),altered.colorlessCardPool.end());
        altered.info.haveGold=!altered.info.haveGold; altered.info.tier=RelicTier::RARE;
        require(outcomeEquivalenceKeyOf(source,path)==outcomeEquivalenceKeyOf(altered,path),
            "equivalence key omits everything the future sampler re-draws");
        {
            auto richer=detachedCopy(source); ++richer.gold;
            auto counters=detachedCopy(source); counters.potionChance+=10;
            require(outcomeEquivalenceKeyOf(source,path)!=outcomeEquivalenceKeyOf(richer,path)
                && outcomeEquivalenceKeyOf(source,path)!=outcomeEquivalenceKeyOf(counters,path),
                "equivalence key keeps visible state and copied hidden counters");
        }
        std::mt19937_64 left(19),right(19);
        sampleNoncombatFuture(source,left); sampleNoncombatFuture(altered,right);
        require(test::oocStateFingerprint(source)==test::oocStateFingerprint(altered),
            "hypothetical future independent of copied hidden seeds and queue ordering");
        require(left==right,"sampling consumes reproducible planner draws");
        // The shared simulator sampler must preserve native counters. Only
        // the live advisor injects a public-belief prior at a root particle.
        source.monsterChance=.7f; source.shopChance=.12f;
        source.treasureChance=.08f; source.potionChance=20;
        source.cardRarityFactor=-11;
        sampleNoncombatFuture(source,left);
        require(source.monsterChance==.7f && source.shopChance==.12f
                && source.treasureChance==.08f && source.potionChance==20
                && source.cardRarityFactor==-11,
            "simulator hypothetical sampling changed native counters");
        // Revealed offers/selector progress, current map and visible boss survive.
        source=detachedCopy(gc); source.openCardSelectScreen(CardSelectScreenType::TRANSFORM_UPGRADE,3);
        GameAction(0).execute(source);
        auto before=visible(source); auto map=source.map; auto boss=source.boss;
        const auto progress=source.info.haveSelectedCards.size();
        sampleNoncombatFuture(source,left);
        require(visible(source)==before && source.map==map && source.boss==boss
            && source.info.haveSelectedCards.size()==progress,"public state and sequential selector progress preserved");
        {
            // A20 Act 3: after a sampled first-boss win the leaf is the second boss
            // fight, so the revealed second boss must survive resampling.
            auto fight=detachedCopy(gc); fight.act=3; fight.ascension=20;
            fight.monsterList.clear(); fight.monsterListOffset=0;
            fight.eliteMonsterList.clear(); fight.eliteMonsterListOffset=0;
            fight.boss=MonsterEncounter::AWAKENED_ONE; fight.secondBoss=MonsterEncounter::TIME_EATER;
            fight.curRoom=Room::BOSS; fight.screenState=ScreenState::BATTLE;
            fight.info.encounter=MonsterEncounter::TIME_EATER;
            auto hidden=detachedCopy(fight); hidden.screenState=ScreenState::MAP_SCREEN;
            std::set<int> hiddenDraws;
            for(int n=0;n<16;++n) {
                auto f=detachedCopy(fight); sampleNoncombatFuture(f,left);
                require(f.secondBoss==MonsterEncounter::TIME_EATER,"revealed A20 second boss resampled");
                auto h=detachedCopy(hidden); sampleNoncombatFuture(h,left);
                hiddenDraws.insert(int(h.secondBoss));
            }
            require(hiddenDraws.size()==2 && !hiddenDraws.count(int(MonsterEncounter::AWAKENED_ONE)),
                "hidden A20 second boss is drawn from the two other bosses");
        }
        source=detachedCopy(gc); source.screenState=ScreenState::MAP_SCREEN;
        OocGameContextModel mapModel(source,path,{},sampled);
        std::set<int> encounters;
        const auto mapAction=mapModel.legalActions(0).front().id;
        for(int n=0;n<32;++n) {
            const auto child=mapModel.sampleSuccessor(0,mapAction,left);
            encounters.insert(int(mapModel.state(child).info.encounter));
        }
        require(encounters.size()>1,"MAP samples hidden encounter queue rather than copied future");
        struct CaptureSampler final : CombatTransitionSampler {
            mutable std::set<std::uint64_t> seeds;
            CombatRuntimeSupport support(const GameContext &g,const CombatPredictorInputV1 &) const override {
                seeds.insert(g.seed); return {true,"sampled fixture"};
            }
            CombatRuntimeSample sample(const GameContext &,const CombatPredictorInputV1 &,std::mt19937_64 &) const override {
                return {CombatRuntimeSample::Outcome::DEATH,{}};
            }
        };
        auto capture=std::make_shared<CaptureSampler>(); sampled.checkpointLeaves=true;
        OocGameContextModel prepared(source,path,capture,sampled);
        for(int n=0;n<8;++n) prepared.sampleSuccessor(0,mapAction,left);
        require(prepared.continuationMetrics().preparedCombats==8 && capture->seeds.size()==8,
            "each sampled combat successor prepares its own predictor context");
        auto alternate=detachedCopy(source);
        std::reverse(alternate.monsterList.begin(),alternate.monsterList.end()); alternate.seed^=812;
        OocGameContextModel leafA(source,path,{},sampled),leafB(alternate,path,{},sampled);
        std::mt19937_64 aRng(198),bRng(198);
        require(leafA.evaluateLeaf(0,aRng)==leafB.evaluateLeaf(0,bRng),
            "native leaf uses sampled future features rather than actual hidden queue");
    }
    OocAdapterOptions uniformOptions{true}; uniformOptions.uniformPrior = true;
    OocGameContextModel uniformPrior(gc,path,{},uniformOptions);
    const auto uniformActions = uniformPrior.legalActions(0);
    require(!uniformActions.empty(), "uniform prior retains legal actions");
    for (const auto &action : uniformActions) require(action.prior == 1, "uniform prior equal positive weights");
    OocAdapterOptions constantOptions{true}; constantOptions.constantLeaf = true;
    OocGameContextModel constantCheckpoint(gc,path,{},constantOptions);
    std::mt19937_64 constantRng(777);
    require(constantCheckpoint.evaluateLeaf(0,constantRng) == .5, "constant value only at resolved checkpoint");
    for (auto outcome : {GameOutcome::PLAYER_LOSS,GameOutcome::PLAYER_VICTORY}) {
        auto terminal = detachedCopy(gc); terminal.outcome = outcome; terminal.act = 4;
        OocGameContextModel exactTerminal(terminal,path,{},constantOptions);
        require(exactTerminal.evaluateLeaf(0,constantRng) == (outcome == GameOutcome::PLAYER_VICTORY ? 1 : 0),
                "constant ablation preserves terminal values");
    }
    struct BossExpectationSampler final : CombatTransitionSampler {
        mutable int expectationCalls=0;
        mutable std::vector<MonsterEncounter> encounters;
        CombatRuntimeSupport support(const GameContext &,const CombatPredictorInputV1 &) const override {
            return {true,"supported"};
        }
        CombatTransitionExpectation expectation(const GameContext &probe,
            const CombatPredictorInputV1 &) const override {
            ++expectationCalls;
            encounters.push_back(probe.info.encounter);
            return {true,0.2f,0.5f};
        }
        CombatRuntimeSample sample(const GameContext &,const CombatPredictorInputV1 &,
            std::mt19937_64 &) const override { return {}; }
    };
    auto bossSampler=std::make_shared<BossExpectationSampler>();
    OocAdapterOptions bossCheckpointOptions{true}; bossCheckpointOptions.bossLeaf=true;
    OocGameContextModel bossCheckpoint(gc,path,bossSampler,bossCheckpointOptions);
    const double nativeCheckpointValue=vStateWinNative(gc);
    const double bossCheckpointValue=bossCheckpoint.evaluateLeaf(0,constantRng);
    require(bossSampler->expectationCalls==10 && bossSampler->encounters.size()==10,
        "checkpoint boss leaf calls every all-act boss expectation");
    require(std::set<MonsterEncounter>(bossSampler->encounters.begin(),bossSampler->encounters.end()).size()==10,
        "checkpoint boss leaf probes ten distinct bosses");
    require(std::abs(bossCheckpointValue-0.7)<1e-7
        && std::abs(bossCheckpointValue-nativeCheckpointValue)>1e-6,
        "checkpoint boss leaf returns combat expectation instead of native v_win");
    {
        // Direct probe leaf: a pending non-combat screen is valued by v_win in
        // place, with no policy-chain projection step.
        auto pending=detachedCopy(gc); pending.screenState=ScreenState::REST_ROOM;
        OocAdapterOptions directOptions{true}; directOptions.directLeaf=true;
        OocGameContextModel direct(pending,path,bossSampler,directOptions);
        OocGameContextModel playout(pending,path,bossSampler,OocAdapterOptions{true});
        std::mt19937_64 directRng(20261006);
        const double expected=vStateWinNative(pending);
        require(direct.evaluateLeaf(0,directRng)==expected
            && direct.continuationMetrics().projectionSteps==0
            && direct.continuationMetrics().pendingLeaves==1,
            "direct leaf values a pending screen without projection");
        std::mt19937_64 playoutRng(20261006);
        (void)playout.evaluateLeaf(0,playoutRng);
        require(playout.continuationMetrics().projectionSteps>0,"native leaf still projects a pending screen");
        require(playout.continuationMetrics().priorLeafSteps==0,"chain leaf takes no V4 rollout step");
        // STS_OOC_MCTS_LEAF_POLICY=prior: V4's policy head decides the pending campfire in the rollout.
        OocAdapterOptions priorOptions{true}; priorOptions.priorLeafPolicy=true; priorOptions.treeRules=true;
        OocGameContextModel priorPlayout(pending,path,bossSampler,priorOptions);
        std::mt19937_64 priorRng(20261006);
        (void)priorPlayout.evaluateLeaf(0,priorRng);
        require(priorPlayout.continuationMetrics().priorLeafSteps>=1,"prior leaf policy decides the campfire");
        OocAdapterOptions heartOptions = priorOptions;
        heartOptions.priorLeafPolicy = false; heartOptions.heart1LeafPolicy = true;
        auto deps = defaultOocMctsDependencies();
        unsigned calls = 0;
        deps.heart1PolicyLogits = [&](const GameContext &, const std::vector<GameAction> &actions,
                                     std::map<std::string,std::uint64_t> *) {
            ++calls;
            std::vector<double> logits(actions.size(), -1.0);
            logits.back() = 1.0;
            return std::optional<std::vector<double>>(logits);
        };
        deps.policyLogits = [](const GameContext &, const PathHistory &, const std::vector<GameAction> &)
                -> std::vector<double> { throw std::runtime_error("unexpected V4 rollout scoring"); };
        OocGameContextModel heartPlayout(pending,path,bossSampler,heartOptions,deps);
        std::mt19937_64 heartRng(20261006);
        (void)heartPlayout.evaluateLeaf(0,heartRng);
        require(calls && heartPlayout.continuationMetrics().heart1LeafSteps == calls
            && heartPlayout.continuationMetrics().heart1LeafFallbacks == 0
            && heartPlayout.continuationMetrics().priorLeafSteps == 0,
            "heart1 rollout uses its own logits and counters, never V4 policy head");
        {
            // STS_OOC_MCTS_LEAF_SELECTS=heart1: a pending REMOVE select in the rollout goes to heart1,
            // not the chain; without it heart1full leaves it to the chain.
            auto remove=detachedCopy(pending); remove.openCardSelectScreen(CardSelectScreenType::REMOVE,1);
            auto selectOptions=heartOptions; selectOptions.heart1Coverage=true; selectOptions.heart1Prior=true;
            const auto removeSteps=[&](const OocAdapterOptions &o) {
                calls=0;
                OocGameContextModel m(remove,path,bossSampler,o,deps);
                std::mt19937_64 rng(20261006); (void)m.evaluateLeaf(0,rng);
                const auto &reasons=m.continuationMetrics().heart1LeafReasons;
                return std::make_pair(calls,reasons.count("chain:screen"+std::to_string(int(ScreenState::CARD_SELECT))));
            };
            const auto [chainCalls,chainFallback]=removeSteps(selectOptions);
            selectOptions.heart1LeafSelects=true;
            const auto [selectCalls,selectFallback]=removeSteps(selectOptions);
            require(chainFallback==1 && selectFallback==0 && selectCalls>chainCalls,
                "heart1 leaf selects hand the rollout's REMOVE select to heart1");
            auto noFull=heartOptions; noFull.heart1LeafSelects=true;
            bool rejected=false;
            try { OocGameContextModel bad(remove,path,bossSampler,noFull,deps); }
            catch(const std::invalid_argument &) { rejected=true; }
            require(rejected,"heart1 leaf selects without heart1full is rejected");
        }
        deps.heart1PolicyLogits = [](const GameContext &, const std::vector<GameAction> &,
                                   std::map<std::string,std::uint64_t> *)
                -> std::optional<std::vector<double>> { return std::nullopt; };
        OocGameContextModel fallback(pending,path,bossSampler,heartOptions,deps);
        auto chainOptions = heartOptions; chainOptions.heart1LeafPolicy = false;
        OocGameContextModel chain(pending,path,bossSampler,chainOptions,deps);
        std::mt19937_64 fallbackRng(20261006), chainRng(20261006);
        require(fallback.evaluateLeaf(0,fallbackRng) == chain.evaluateLeaf(0,chainRng)
            && fallbackRng == chainRng && fallback.continuationMetrics().heart1LeafFallbacks > 0
            && fallback.continuationMetrics().heart1LeafSteps == 0,
            "unscored heart1 rollout preserves continuation-chain result and RNG");
        for (const bool wrongSize : {false,true}) {
            deps.heart1PolicyLogits = [wrongSize](const GameContext &, const std::vector<GameAction> &actions,
                                               std::map<std::string,std::uint64_t> *) {
                return std::optional<std::vector<double>>(std::vector<double>(wrongSize ? 0 : actions.size(),
                    std::numeric_limits<double>::quiet_NaN()));
            };
            bool rejected = false;
            try {
                OocGameContextModel invalid(pending,path,bossSampler,heartOptions,deps);
                std::mt19937_64 invalidRng(20261006); (void)invalid.evaluateLeaf(0,invalidRng);
            } catch (const std::runtime_error &) { rejected = true; }
            require(rejected,"heart1 rollout rejects malformed or nonfinite scored output");
        }
        deps.heart1PolicyLogits = {};
        bool rejected = false;
        try { OocGameContextModel missing(pending,path,bossSampler,heartOptions,deps); }
        catch (const std::runtime_error &) { rejected = true; }
        require(rejected,"explicit heart1 rollout fails closed without model seam");
    }
    {
        OocMctsResult capped; capped.aborted=true;
        capped.abortReason="ooc_depth_safety_cap_512_state_513";
        OocContinuationMetrics capCounters;
        recordSearchAbort(capped,capCounters);
        require(capCounters.continuationLimitAborts==1
            && capCounters.continuationReasons.at(capped.abortReason)==1
            && capCounters.imaginedCombats==0 && capCounters.unsupportedCombats==0
            && capCounters.supportReasons.empty(),
            "tree safety cap is a continuation abort, never a combat support failure");
        OocMctsConfig parsed; OocAdapterOptions opts{true};
        applyLiveControl("STS_OOC_MCTS_EARLY_STOP","1",parsed,opts);
        require(parsed.allowUnqualifiedRootStop,"explicit early-stop enable parsed");
        for (const auto *cap : {"1", "32", "256", "512"}) {
            applyLiveControl("STS_OOC_MCTS_MAX_DEPTH",cap,parsed,opts);
            require(parsed.maxDepth == std::stoul(cap),"safety cap override parsed");
        }
        applyLiveControl("STS_OOC_MCTS_EARLY_STOP","0",parsed,opts);
        require(!parsed.allowUnqualifiedRootStop,"early-stop rollback parsed");
        applyLiveControl("STS_OOC_MCTS_ROOT_SELECTION","q",parsed,opts);
        applyLiveControl("STS_OOC_MCTS_LEAF_POLICY","prior",parsed,opts);
        require(opts.priorLeafPolicy && !opts.uniformLeafPolicy,"prior leaf policy parsed");
        applyLiveControl("STS_OOC_MCTS_LEAF_POLICY","heart1",parsed,opts);
        require(opts.heart1LeafPolicy && !opts.priorLeafPolicy && !opts.uniformLeafPolicy,"heart1 leaf parsed");
        applyLiveControl("STS_OOC_MCTS_LEAF_POLICY","uniform",parsed,opts);
        require(!opts.priorLeafPolicy && !opts.heart1LeafPolicy && opts.uniformLeafPolicy,"uniform leaf clears model policy");
        applyLiveControl("STS_OOC_MCTS_TARGET_PRIOR","1",parsed,opts);
        applyLiveControl("STS_OOC_MCTS_LEAF_SELECTS","heart1",parsed,opts);
        require(opts.targetPrior && opts.heart1LeafSelects,"target prior and heart1 leaf selects parsed");
        applyLiveControl("STS_OOC_MCTS_TARGET_PRIOR","0",parsed,opts);
        applyLiveControl("STS_OOC_MCTS_POTION_KEEP_PRIOR","1",parsed,opts);
        require(opts.potionKeepPrior,"potion keep prior parsed");
        applyLiveControl("STS_OOC_MCTS_POTION_KEEP_PRIOR","0",parsed,opts);
        require(!opts.potionKeepPrior,"potion keep prior rollback parsed");
        applyLiveControl("STS_OOC_MCTS_LEAF_SELECTS","chain",parsed,opts);
        require(!opts.targetPrior && !opts.heart1LeafSelects,"target prior and leaf selects rollback parsed");
        applyLiveControl("STS_OOC_MCTS_LEAF_POLICY","v4",parsed,opts);
        require(!opts.priorLeafPolicy && !opts.uniformLeafPolicy,"chain leaf policy parsed");
        applyLiveControl("STS_OOC_MCTS_CPU_SECONDS","0.25",parsed,opts);
        require(opts.cpuBudgetSeconds == .25,"CPU allowance parsed");
        applyLiveControl("STS_OOC_MCTS_CPU_SECONDS","0",parsed,opts);
        require(opts.cpuBudgetSeconds == 0,"CPU allowance rollback parsed");
        applyLiveControl("STS_OOC_MCTS_LEAF_COMBATS","5",parsed,opts);
        require(opts.leafCombats == 5,"five-combat rollout parsed");
        applyLiveControl("STS_OOC_MCTS_LEAF_COMBATS","3",parsed,opts);
        applyLiveControl("STS_OOC_MCTS_LEAF_VALUE","direct",parsed,opts);
        require(opts.directLeaf && !opts.bossLeaf && !opts.constantLeaf,"direct leaf parsed");
        applyLiveControl("STS_OOC_MCTS_LEAF_VALUE","screen",parsed,opts);
        require(opts.screenLeaf && !opts.directLeaf && !opts.bossLeaf,"screen leaf parsed");
        applyLiveControl("STS_OOC_MCTS_LEAF_VALUE","boss",parsed,opts);
        require(!opts.directLeaf,"boss leaf clears direct leaf");
        applyLiveControl("STS_OOC_MCTS_CPUCT","0",parsed,opts);
        require(parsed.selectByMeanQ && parsed.cPuct == 0 && opts.leafCombats == 3 && opts.bossLeaf,
            "accepted bounded knobs");
        require(std::abs(bossLeafUtility({true,0.2f,0.5f})-0.7)<1e-7
            && bossLeafUtility({true,1,1})==0 && bossLeafUtility({true,0,1})==1,
            "boss leaf survival/HP utility");
        for (const auto &invalid : std::vector<std::pair<std::string,std::string>>{
            {"STS_OOC_MCTS_CPU_SECONDS","-1"},{"STS_OOC_MCTS_CPU_SECONDS","nan"},{"STS_OOC_MCTS_CPU_SECONDS","11"},
            {"STS_OOC_MCTS_EARLY_STOP","true"},{"STS_OOC_MCTS_EARLY_STOP","2"},{"STS_OOC_MCTS_PRIOR","none"},{"STS_OOC_MCTS_TEMPERATURE","0"},
            {"STS_OOC_MCTS_CPUCT","-1"},{"STS_OOC_MCTS_WIDEN_K","nan"},
            {"STS_OOC_MCTS_WIDEN_ALPHA","1"},{"STS_OOC_MCTS_MAX_DEPTH","513"},{"STS_OOC_MCTS_MAX_DEPTH","0"},
            {"STS_OOC_MCTS_MAX_DEPTH","2.5"},{"STS_OOC_MCTS_LEAF_COMBATS","2"},{"STS_OOC_MCTS_LEAF_COMBATS","4"},
            {"STS_OOC_MCTS_LEAF_POLICY","random"},{"STS_OOC_MCTS_LEAF_POLICY","Prior"},{"STS_OOC_MCTS_LEAF_VALUE","0"},
            {"STS_OOC_MCTS_ROOT_SELECTION"," q"},{"STS_OOC_MCTS_TARGET_PRIOR","on"},{"STS_OOC_MCTS_POTION_KEEP_PRIOR","yes"},{"STS_OOC_MCTS_LEAF_SELECTS","v4"},{"STS_OOC_MCTS_TEMPERATURE","1junk"}})
            rejects([&] { applyLiveControl(invalid.first,invalid.second,parsed,opts); });
    }
    const PathHistory *saved=t_curPath; t_curPath=&path;
    for (int i=0;i<3;++i) {
        auto probe=detachedCopy(gc); probe.curHp=10+i*30; probe.gold=50+i*150;
        OocGameContextModel leaf(probe,path);
        double direct=vStateWin(probe), adapted=leaf.leafValue(0);
        require(std::abs(direct-adapted)<1e-12,"native v_win leaf parity");
        std::cout<<"leaf_parity hp="<<probe.curHp<<" gold="<<probe.gold<<" value="<<adapted<<'\n';
    }
    {
        // STS_OOC_MCTS_LEAF_WIN_MODEL replaces the process v_win at the leaf.
        auto alt=std::make_shared<CompactTreeNet>();
        require(alt->load(kScreenGbmAnchor,richIdxMap()),"leaf win model fixture loads");
        OocAdapterOptions opts{true}; opts.leafWinNet=alt;
        OocGameContextModel leaf(gc,path,{},opts);
        require(std::abs(leaf.leafValue(0)-alt->predict(richFeatureVec(gc,path)))<1e-12,"leaf win model parity");
    }
    t_curPath=saved;
    auto battle=detachedCopy(gc); battle.screenState=ScreenState::BATTLE;
    OocGameContextModel boundary(battle,path);
    require(!boundary.terminalValue(0) && boundary.isLeafBoundary(0),"battle is nonterminal boundary");
    rejects([&] { boundary.legalActions(0); });
    auto br=OocMctsPlanner().search(boundary,0,4);
    require(br.metrics.leafEvaluations==4 && br.rootActions.empty()
        && br.metrics.transitionSamples==0,"battle MCTS boundary");
    for(auto outcome : {GameOutcome::PLAYER_LOSS,GameOutcome::PLAYER_VICTORY}) {
        battle.outcome=outcome; battle.act=4;
        OocGameContextModel terminal(battle,path);
        require(terminal.terminalValue(0)==(outcome==GameOutcome::PLAYER_VICTORY?1.:0.),"exact terminal value");
        auto tr=OocMctsPlanner().search(terminal,0,3);
        require(tr.metrics.leafEvaluations==0 && tr.rootActions.empty(),"terminal precedence");
    }
    for (const bool keys : {false, true}) {
        auto act3 = detachedCopy(gc); act3.outcome = GameOutcome::PLAYER_VICTORY; act3.act = 3;
        OocAdapterOptions opts{true}; opts.collectKeys = keys;
        auto deps = defaultOocMctsDependencies(); deps.stopAfterAct = [] { return 0; };
        OocGameContextModel model(act3,path,{},opts,deps);
        std::mt19937_64 rng(123);
        require(model.terminalValue(0) == (keys ? 0.0 : 1.0)
            && model.evaluateLeafWithOutcome(0,rng).value == (keys ? 0.0 : 1.0),
            "Act-3 terminal is not a Heart victory, keys-off retains historical value");
    }
    for (auto screen : {ScreenState::INVALID,ScreenState::CARD_SELECT}) {
        auto unsupported=detachedCopy(gc); unsupported.screenState=screen;
        OocGameContextModel leaf(unsupported,path);
        require(leaf.isLeafBoundary(0),"unsupported state boundary");
    }
    auto reward=detachedCopy(gc); reward.openCombatRewardScreen(reward.createCombatReward());
    require(reward.info.rewardsContainer.cardRewardCount>0,"reward fixture");
    auto rewardActions=v4CandidateActions(reward);
    GameAction skip(GameAction::RewardsActionType::CARD,reward.info.rewardsContainer.cardRewardCount-1,5);
    require(std::count_if(rewardActions.begin(),rewardActions.end(),[&](auto a){return a.bits==skip.bits;})==1,
        "reward skip included exactly once");
    OocGameContextModel rewards(reward,path);
    auto rewardChild=rewards.sampleSuccessor(0,sourceId(rewards,skip.bits),rng);
    require(rewards.state(rewardChild).info.rewardsContainer.cardRewardCount
        ==reward.info.rewardsContainer.cardRewardCount-1,"reward skip execution");
    // Inject an equivalent RAW result from a deterministic native exit. The
    // callback dispatches the same native reward code in both branches.
    struct FakeSampler final : CombatTransitionSampler {
        bool enabled=true, death=false, stochastic=false, escape=false;
        mutable int supportCalls=0, sampleCalls=0;
        mutable std::vector<std::uint64_t> draws;
        CombatTransitionPersistentState raw;
        CombatPredictorInputV1 expectedInput;
        CombatRuntimeSupport support(const GameContext &g, const CombatPredictorInputV1 &input) const override {
            ++supportCalls;
            require(g.screenState==ScreenState::BATTLE,"sampler prebattle screen");
            require(combatPredictorInputJson(input)==combatPredictorInputJson(expectedInput),
                    "predictor must precede battle initialization");
            return {enabled, enabled?"supported":"fake unsupported"};
        }
        CombatRuntimeSample sample(const GameContext &,const CombatPredictorInputV1 &,
                                   std::mt19937_64 &r) const override {
            ++sampleCalls;
            bool loss=death;
            if(stochastic) { const auto draw=r(); draws.push_back(draw); loss=draw&1; }
            return {loss?CombatRuntimeSample::Outcome::DEATH:
                (escape?CombatRuntimeSample::Outcome::ESCAPE:CombatRuntimeSample::Outcome::VICTORY),raw};
        }
    };
    auto combatRoot=detachedCopy(gc);
    combatRoot.screenState=ScreenState::REST_ROOM;
    combatRoot.curRoom=Room::MONSTER;
    int regainCalls=0;
    combatRoot.regainControlAction=[&](GameContext &g) {
        ++regainCalls;
        if(g.screenState==ScreenState::REST_ROOM) g.enterBattle(MonsterEncounter::CULTIST);
        else g.afterBattle();
    };
    const auto restActions=v4CandidateActions(combatRoot);
    require(!restActions.empty(),"combat entry rest fixture");
    const auto restAction=restActions.front();
    auto real=detachedCopy(combatRoot);
    PathHistory realPath=path; realPath.update(real);
    restAction.execute(real); realPath.update(real);
    auto fake=std::make_shared<FakeSampler>();
    // An injected sampler is never consulted for ordinary nonbattle actions.
    auto ordinary=detachedCopy(gc); ordinary.screenState=ScreenState::REST_ROOM;
    auto ordinaryExpected=detachedCopy(ordinary);
    const auto ordinaryAction=v4CandidateActions(ordinary).front();
    ordinaryAction.execute(ordinaryExpected);
    OocGameContextModel ordinaryModel(ordinary,path,fake);
    const auto ordinaryId=ordinaryModel.sampleSuccessor(0,sourceId(ordinaryModel,ordinaryAction.bits),rng);
    require(fake->supportCalls==0 && fake->sampleCalls==0
        && test::oocStateFingerprint(ordinaryModel.state(ordinaryId))==test::oocStateFingerprint(ordinaryExpected),
        "ordinary injected successor unchanged");
    fake->expectedInput=captureCombatPredictorInput(real,real.info.encounter,potionKeepValue(real));
    const auto preFingerprint=test::oocStateFingerprint(real);
    BattleContext deterministic;
    deterministic.init(real,MonsterEncounter::CULTIST);
    deterministic.player.curHp=37;
    deterministic.outcome=Outcome::PLAYER_VICTORY;
    int rawCalls=0;
    {
        CombatTransitionRawObserverScope scope([&](const BattleContext &,GameContext &raw) {
            ++rawCalls; fake->raw=captureCombatTransitionState(raw);
        });
        deterministic.exitBattle(real);
    }
    realPath.update(real);
    require(rawCalls==1 && regainCalls==2,"native oracle continuation once");
    regainCalls=0;
    OocGameContextModel crossed(combatRoot,path,fake);
    const auto rootFingerprint=test::oocStateFingerprint(crossed.state(0));
    const auto crossedId=crossed.sampleSuccessor(0,sourceId(crossed,restAction.bits),rng);
    sts::search::OocTreeSnapshot annotated;
    annotated.nodes.push_back({0,1,0,false,0,0,0,0});
    annotated.nodes.push_back({1,1,0,true,0,sourceId(crossed,restAction.bits),1,0});
    annotated.nodes.push_back({2,1,1,false,crossedId,0,0,0});
    annotated.edges.push_back({0,1,1,false});
    annotated.edges.push_back({1,2,1,true});
    annotateOocTree(crossed,annotated);
    require(!annotated.nodes[1].label.empty()
        && annotated.nodes[1].label!=annotated.nodes[1].key
        && annotated.nodes[2].label.find("HP ")!=std::string::npos
        && annotated.edges[1].combatModelUsed
        && annotated.edges[1].combatEncounter=="CULTIST"
        && annotated.edges[1].combatOutcome=="victory"
        && !annotated.edges[0].combatModelUsed,
        "graph annotates game action/state and only CTM-sampled edge");
    require(regainCalls==2 && fake->sampleCalls==1 && fake->supportCalls==1,
            "injected reward continuation exactly once");
    require(test::oocStateFingerprint(crossed.state(crossedId))==test::oocStateFingerprint(real),
            "injected continuation OOC/reward/RNG fingerprint");
    require(combatTransitionFingerprint(crossed.state(crossedId))==combatTransitionFingerprint(real),
            "injected persistent continuation fingerprint");
    require(crossed.pathHistory(crossedId).roomVisits==realPath.roomVisits
        && crossed.pathHistory(crossedId).lastNodeKey==realPath.lastNodeKey,"native PathHistory parity");
    require(test::oocStateFingerprint(crossed.state(0))==rootFingerprint,"combat parent unchanged");
    // A custom host may omit the callback. Its CTM input must use the same
    // neutral keep value as the native simulator, not the old zero fallback.
    auto fallbackSampler=std::make_shared<FakeSampler>();
    fallbackSampler->death=true;
    auto fallbackPre=detachedCopy(combatRoot);
    restAction.execute(fallbackPre);
    fallbackSampler->expectedInput=captureCombatPredictorInput(
        fallbackPre,fallbackPre.info.encounter,4.0);
    auto fallbackDeps=defaultOocMctsDependencies();
    fallbackDeps.potionKeepValue={};
    OocGameContextModel fallback(combatRoot,path,fallbackSampler,{},std::move(fallbackDeps));
    const auto fallbackId=fallback.sampleSuccessor(0,sourceId(fallback,restAction.bits),rng);
    require(fallbackSampler->expectedInput.globals.potionKeepValue==4.0
        && fallbackSampler->supportCalls==1 && fallbackSampler->sampleCalls==1
        && fallback.state(fallbackId).outcome==GameOutcome::PLAYER_LOSS,
        "omitted potion keep callback supplies neutral CTM input");
    // Compare an actual Smoke Bomb exit with explicit ESCAPE injection from
    // the identical prebattle origin. Includes Cleric's pre-reward maxHP gain.
    for (bool cleric : {false, true}) {
        const int savedRegainCalls = regainCalls;
        auto escapeRoot=detachedCopy(combatRoot);
        escapeRoot.potions[0]=Potion::SMOKE_BOMB;
        escapeRoot.potionCount=1;
        escapeRoot.smokeBombUsed=true; // Native battle initialization resets it.
        if (cleric) escapeRoot.relics.add({RelicId::FACE_OF_CLERIC,0});
        auto oracle=detachedCopy(escapeRoot);
        PathHistory oraclePath=path; oraclePath.update(oracle);
        restAction.execute(oracle); oraclePath.update(oracle);
        auto escapeSampler=std::make_shared<FakeSampler>();
        escapeSampler->escape=true;
        escapeSampler->expectedInput=captureCombatPredictorInput(oracle,oracle.info.encounter,potionKeepValue(oracle));
        BattleContext smoke;
        smoke.init(oracle,MonsterEncounter::CULTIST);
        require(!smoke.smokeBombUsed,"native pre-used Smoke flag reset");
        smoke.player.curHp=37;
        smoke.drinkPotion(0);
        require(smoke.smokeBombUsed && smoke.outcome==Outcome::PLAYER_VICTORY
            && smoke.potionCount==0,"native Smoke Bomb consumes and exits");
        int escapeRawCalls=0;
        {
            CombatTransitionRawObserverScope scope([&](const BattleContext &,GameContext &raw) {
                ++escapeRawCalls; escapeSampler->raw=captureCombatTransitionState(raw);
            });
            smoke.exitBattle(oracle);
        }
        oraclePath.update(oracle);
        OocGameContextModel imagined(escapeRoot,path,escapeSampler);
        const auto parent=test::oocStateFingerprint(imagined.state(0));
        const auto escaped=imagined.sampleSuccessor(0,sourceId(imagined,restAction.bits),rng);
        require(escapeRawCalls==1 && escapeSampler->sampleCalls==1
            && test::oocStateFingerprint(imagined.state(escaped))==test::oocStateFingerprint(oracle)
            && combatTransitionFingerprint(imagined.state(escaped))==combatTransitionFingerprint(oracle),
            "ESCAPE exact native OOC/persistent/all-RNG continuation parity");
        require(oracle.screenState==ScreenState::MAP_SCREEN && !oracle.smokeBombUsed
            && imagined.pathHistory(escaped).roomVisits==oraclePath.roomVisits
            && imagined.pathHistory(escaped).lastNodeKey==oraclePath.lastNodeKey
            && test::oocStateFingerprint(imagined.state(0))==parent,
            "ESCAPE no rewards, native PathHistory, unchanged parent");
        escapeSampler->escape=false;
        OocGameContextModel mislabeled(escapeRoot,path,escapeSampler);
        rejects([&] { mislabeled.sampleSuccessor(0,sourceId(mislabeled,restAction.bits),rng); });
        auto boss=detachedCopy(escapeRoot);
        boss.info.encounter=MonsterEncounter::SLIME_BOSS;
        rejects([&] { applySampledCombatExit(boss,{CombatRuntimeSample::Outcome::ESCAPE,escapeSampler->raw}); });
        BattleContext blocked;
        blocked.init(boss,MonsterEncounter::SLIME_BOSS);
        blocked.drinkPotion(0);
        require(blocked.outcome==Outcome::UNDECIDED && !blocked.smokeBombUsed
            && blocked.potions[0]==Potion::SMOKE_BOMB && blocked.potionCount==1,
            "boss blocks Smoke Bomb without consuming it or accepting ESCAPE");
        blocked.init(escapeRoot,MonsterEncounter::CULTIST);
        blocked.player.buff<PS::SURROUNDED>();
        blocked.drinkPotion(0);
        require(blocked.outcome==Outcome::UNDECIDED && blocked.potionCount==1,
            "Surrounded blocks Smoke Bomb without consumption");
        blocked.player.removeStatus<PS::SURROUNDED>();
        blocked.drinkPotion(0);
        require(blocked.smokeBombUsed && blocked.potionCount==0,
            "removing Surrounded allows escape later in the same combat");
        regainCalls=savedRegainCalls;
    }
    std::cout<<"smoke_escape_oracle native_origin=identical cleric=both raw_outcome=ESCAPE parity=exact\n";
    {
        // Phase-0 Smoke Bomb masking (#370): the CTM sees an empty slot, the
        // Smoke Bomb returns unused, and a potion generated into its slot is
        // dropped. States without a Smoke Bomb pass through unchanged.
        struct RecordingSampler final : CombatTransitionSampler {
            mutable std::vector<std::array<int,5>> seenPotions;
            mutable std::vector<int> seenInputCounts;
            CombatRuntimeSupport support(const GameContext &g,const CombatPredictorInputV1 &p) const override {
                record(g,p);
                for (auto potion : g.potions)
                    if (potion==Potion::SMOKE_BOMB) return {false,"smoke_bomb"};
                return {true,"supported"};
            }
            CombatRuntimeSample sample(const GameContext &g,const CombatPredictorInputV1 &p,
                    std::mt19937_64 &) const override {
                record(g,p);
                CombatRuntimeSample result{CombatRuntimeSample::Outcome::VICTORY,
                    captureCombatTransitionState(g)};
                result.rawPost.potions[1]=static_cast<int>(Potion::FIRE_POTION); // generated
                return result;
            }
            void record(const GameContext &g,const CombatPredictorInputV1 &p) const {
                std::array<int,5> potions{};
                for (int i=0;i<5;++i) potions[i]=static_cast<int>(g.potions[i]);
                seenPotions.push_back(potions);
                seenInputCounts.push_back(p.globals.potionCount);
            }
        };
        auto recording=std::make_shared<RecordingSampler>();
        const auto wrapped=maskInitialSmokeBomb(recording);
        auto withSmoke=detachedCopy(gc);
        withSmoke.potionCapacity=3;
        withSmoke.potions={Potion::BLOCK_POTION,Potion::SMOKE_BOMB,Potion::EMPTY_POTION_SLOT,
            Potion::EMPTY_POTION_SLOT,Potion::EMPTY_POTION_SLOT};
        withSmoke.potionCount=2;
        withSmoke.info.encounter=MonsterEncounter::CULTIST;
        const auto input=captureCombatPredictorInput(withSmoke,MonsterEncounter::CULTIST,4.0);
        require(wrapped->support(withSmoke,input).supported,"masked Smoke Bomb combat is supported");
        std::mt19937_64 maskRng(5);
        const auto sampled=wrapped->sample(withSmoke,input,maskRng);
        require(recording->seenPotions.back()[1]==static_cast<int>(Potion::EMPTY_POTION_SLOT)
            && recording->seenInputCounts.back()==1,"CTM sees the Smoke Bomb slot as empty");
        require(sampled.outcome==CombatRuntimeSample::Outcome::VICTORY
            && sampled.rawPost.potions[1]==static_cast<int>(Potion::SMOKE_BOMB)
            && sampled.rawPost.potions[0]==static_cast<int>(Potion::BLOCK_POTION)
            && sampled.rawPost.potionCount==2 && !sampled.rawPost.smokeBombUsed,
            "Smoke Bomb returns unused and displaces a generated potion");
        const auto prepared=wrapped->prepare(withSmoke,input);
        require(prepared->support().supported
            && prepared->sample(maskRng).rawPost.potions[1]==static_cast<int>(Potion::SMOKE_BOMB),
            "prepared path masks and restores the Smoke Bomb");
        auto noSmoke=detachedCopy(withSmoke);
        noSmoke.potions[1]=Potion::EMPTY_POTION_SLOT; noSmoke.potionCount=1;
        const auto plain=captureCombatPredictorInput(noSmoke,MonsterEncounter::CULTIST,4.0);
        const auto passed=wrapped->sample(noSmoke,plain,maskRng);
        require(passed.rawPost.potions[1]==static_cast<int>(Potion::FIRE_POTION),
            "states without a Smoke Bomb pass through unchanged");
        std::cout<<"smoke_bomb_mask masked=empty_slot restored=unused generated=dropped\n";
        struct EscapeSampler final : CombatTransitionSampler {
            CombatRuntimeSupport support(const GameContext &,const CombatPredictorInputV1 &) const override { return {true,"supported"}; }
            CombatRuntimeSample sample(const GameContext &,const CombatPredictorInputV1 &,std::mt19937_64 &) const override { return {}; }
            bool modelsSmokeBombEscape() const override { return true; }
        };
        const std::shared_ptr<const CombatTransitionSampler> escapeCapable=std::make_shared<EscapeSampler>();
        require(maskInitialSmokeBomb(escapeCapable)==escapeCapable,"an escape-capable CTM keeps its Smoke Bomb");
        std::cout<<"smoke_bomb_mask escape_capable=unmasked\n";
    }
    {
        // Phase-0 masking (#370): the CTM sees an empty slot for an initial
        // Smoke Bomb, and the Smoke Bomb returns unused after the combat.
        struct RecordingSampler final : CombatTransitionSampler {
            mutable std::vector<int> seenPotions;
            mutable int seenCount = -1, calls = 0;
            CombatRuntimeSupport support(const GameContext &g,const CombatPredictorInputV1 &) const override {
                const bool smoke=std::any_of(g.potions.begin(),g.potions.end(),[](auto p){return p==Potion::SMOKE_BOMB;});
                return {!smoke, smoke ? "smoke_bomb" : "supported"};
            }
            CombatRuntimeSample sample(const GameContext &g,const CombatPredictorInputV1 &in,
                    std::mt19937_64 &) const override {
                ++calls; seenCount=in.globals.potionCount; seenPotions.clear();
                for (const auto &token : in.potions) seenPotions.push_back(token.potionId);
                CombatRuntimeSample result;
                result.outcome=CombatRuntimeSample::Outcome::VICTORY;
                result.rawPost=captureCombatTransitionState(g);
                result.rawPost.potions[1]=int(Potion::FIRE_POTION); // generated into the masked slot
                result.rawPost.potionCount=2;
                return result;
            }
        };
        auto recorder=std::make_shared<RecordingSampler>();
        const auto masked=maskInitialSmokeBomb(recorder);
        auto held=detachedCopy(gc);
        held.potions.fill(Potion::EMPTY_POTION_SLOT);
        held.potions[0]=Potion::BLOCK_POTION; held.potions[1]=Potion::SMOKE_BOMB; held.potionCount=2;
        held.info.encounter=MonsterEncounter::CULTIST;
        const auto input=captureCombatPredictorInput(held,MonsterEncounter::CULTIST,4.0);
        require(!recorder->support(held,input).supported && masked->support(held,input).supported,
            "Smoke Bomb masking makes the combat supported");
        std::mt19937_64 maskRng(5);
        for (const auto &draw : {masked->sample(held,input,maskRng), masked->prepare(held,input)->sample(maskRng)}) {
            require(recorder->seenCount==1 && recorder->seenPotions.at(1)==int(Potion::EMPTY_POTION_SLOT)
                && recorder->seenPotions.at(0)==int(Potion::BLOCK_POTION),
                "CTM sees the Smoke Bomb slot as empty");
            require(draw.outcome==CombatRuntimeSample::Outcome::VICTORY
                && draw.rawPost.potions[1]==int(Potion::SMOKE_BOMB) && draw.rawPost.potionCount==2
                && !draw.rawPost.smokeBombUsed,
                "Smoke Bomb returns unused and replaces a potion generated into its slot");
        }
        auto plain=detachedCopy(held); plain.potions[1]=Potion::EMPTY_POTION_SLOT; plain.potionCount=1;
        const auto plainInput=captureCombatPredictorInput(plain,MonsterEncounter::CULTIST,4.0);
        const auto passed=masked->sample(plain,plainInput,maskRng);
        require(recorder->seenCount==1 && passed.rawPost.potions[1]==int(Potion::FIRE_POTION),
            "states without a Smoke Bomb pass through unchanged");
        auto used=detachedCopy(held); used.smokeBombUsed=true;
        require(!masked->support(used,captureCombatPredictorInput(used,MonsterEncounter::CULTIST,4.0)).supported,
            "pre-used Smoke Bomb state stays unsupported");
    }
    fake->enabled=false; regainCalls=0;
    OocGameContextModel unsupportedCombat(combatRoot,path,fake);
    const auto unsupportedId=unsupportedCombat.sampleSuccessor(0,sourceId(unsupportedCombat,restAction.bits),rng);
    require(fake->sampleCalls==1 && regainCalls==1 && unsupportedCombat.isLeafBoundary(unsupportedId)
        && test::oocStateFingerprint(unsupportedCombat.state(unsupportedId))==preFingerprint,
        "unsupported combat retains exact battle leaf");
    OocGameContextModel disabledCombat(combatRoot,path);
    const auto disabledId=disabledCombat.sampleSuccessor(0,sourceId(disabledCombat,restAction.bits),rng);
    require(test::oocStateFingerprint(disabledCombat.state(disabledId))==preFingerprint
        && disabledCombat.pathHistory(disabledId).roomVisits==unsupportedCombat.pathHistory(unsupportedId).roomVisits,
        "no sampler combat behavior unchanged");
    fake->enabled=true; fake->death=true; regainCalls=0;
    OocGameContextModel deathCombat(combatRoot,path,fake);
    const auto deathId=deathCombat.sampleSuccessor(0,sourceId(deathCombat,restAction.bits),rng);
    require(regainCalls==1 && deathCombat.terminalValue(deathId)==0
        && deathCombat.state(deathId).screenState==ScreenState::BATTLE,
        "death terminal without reward continuation");
    fake->death=false; fake->stochastic=true;
    std::mt19937_64 plannerRng(991), expectedRng(991);
    OocGameContextModel chanceCombat(combatRoot,path,fake);
    for(int i=0;i<8;++i) {
        const auto expectedDraw=expectedRng();
        const auto sampleId=chanceCombat.sampleSuccessor(0,sourceId(chanceCombat,restAction.bits),plannerRng);
        require(fake->draws.back()==expectedDraw,"independent supplied planner RNG draw");
        require(bool(chanceCombat.terminalValue(sampleId))==bool(expectedDraw&1),
                "chance outcome not value selected");
    }
    // Restrict the test root to the entry action so every planner chance
    // expansion exercises combat without unrelated rest/select decisions.
    struct SingleEntryModel final : OocGenerativeModel {
        OocGameContextModel &adapter;
        OocActionId entry;
        SingleEntryModel(OocGameContextModel &a,OocActionId e):adapter(a),entry(e) {}
        std::optional<double> terminalValue(OocStateId id) const override { return adapter.terminalValue(id); }
        bool isLeafBoundary(OocStateId id) const override { return id != 0 || adapter.isLeafBoundary(id); }
        std::vector<OocPlannerAction> legalActions(OocStateId id) const override {
            require(id==0,"single-entry planner must stop at depth one"); return {{entry,1.0}};
        }
        OocStateId sampleSuccessor(OocStateId id,OocActionId a,std::mt19937_64 &r) override {
            return adapter.sampleSuccessor(id,a,r);
        }
        double leafValue(OocStateId id) const override { return adapter.leafValue(id); }
    };
    fake->draws.clear();
    const auto samplesBefore=fake->sampleCalls;
    OocGameContextModel plannerCombat(combatRoot,path,fake);
    SingleEntryModel entryModel(plannerCombat,sourceId(plannerCombat,restAction.bits));
    OocMctsConfig chanceConfig; chanceConfig.seed=12345;
    OocMctsPlanner chancePlanner(chanceConfig);
    const auto chanceResult=chancePlanner.search(entryModel,0,32);
    std::mt19937_64 expectedChanceRng(chanceConfig.seed);
    std::vector<std::uint64_t> expectedChanceDraws;
    for(std::uint64_t visit=1;visit<=32;++visit) {
        if(expectedChanceDraws.size()<chancePlanner.chanceWideningLimit(visit))
            expectedChanceDraws.push_back(expectedChanceRng());
        else {
            std::uniform_int_distribution<std::size_t> choose(0,expectedChanceDraws.size()-1);
            (void)choose(expectedChanceRng);
        }
    }
    require(fake->draws==expectedChanceDraws && std::set<std::uint64_t>(fake->draws.begin(),fake->draws.end()).size()==fake->draws.size(),
            "planner expansions receive independent RNG draws with unbiased particle reuse");
    const auto &chanceMetrics=chanceResult.metrics;
    require(chanceMetrics.simulations==32 && chanceMetrics.chanceNodes==1
        && chanceMetrics.transitionSamples==expectedChanceDraws.size()
        && chanceMetrics.outcomeParticles==chanceMetrics.transitionSamples
        && chanceMetrics.decisionNodes==chanceMetrics.outcomeParticles+1
        && chanceMetrics.maxDepthReached==1
        && fake->sampleCalls-samplesBefore==int(chanceMetrics.transitionSamples)
        && chanceResult.rootActions.size()==1 && chanceResult.rootActions.front().visits==32,
        "combat planner progressive widening particle metrics preserved");
    // Native continuation may enter another battle (e.g. chained battles).
    // The adapter crosses one combat boundary per primitive transition.
    fake->stochastic=false;
    auto chainedRoot=detachedCopy(combatRoot);
    int chainContinuations=0;
    chainedRoot.regainControlAction=[&](GameContext &g) {
        if(g.screenState==ScreenState::REST_ROOM) g.enterBattle(MonsterEncounter::CULTIST);
        else { ++chainContinuations; g.enterBattle(MonsterEncounter::CULTIST); }
    };
    const auto chainSamplesBefore=fake->sampleCalls;
    OocGameContextModel chainedCombat(chainedRoot,path,fake);
    const auto chainedId=chainedCombat.sampleSuccessor(0,sourceId(chainedCombat,restAction.bits),rng);
    require(chainContinuations==1 && fake->sampleCalls==chainSamplesBefore+1
        && chainedCombat.state(chainedId).screenState==ScreenState::BATTLE
        && chainedCombat.isLeafBoundary(chainedId) && !chainedCombat.terminalValue(chainedId),
        "second battle continuation remains leaf without recursive sampling");
    const auto chainedResult=OocMctsPlanner().search(chainedCombat,chainedId,4);
    require(chainedResult.metrics.transitionSamples==0 && chainedResult.metrics.leafEvaluations==4
        && fake->sampleCalls==chainSamplesBefore+1,"chained battle planner retains leaf seam");
    std::cout<<"combat_planner_chance simulations="<<chanceMetrics.simulations
        <<" particles="<<chanceMetrics.outcomeParticles<<" samples="<<chanceMetrics.transitionSamples
        <<" depth="<<chanceMetrics.maxDepthReached<<" chained_battle=leaf"<<'\n';
    std::cout<<"combat_adapter_oracle raw_calls="<<rawCalls
        <<" fingerprint=exact path_history=exact stochastic_draws="<<fake->draws.size()<<'\n';
    auto result=OocMctsPlanner().search(model,0,32);
    double sum=0; for(auto a:result.rootActions) sum+=a.prior;
    require(std::abs(sum-1)<1e-12,"normalized priors");
    auto best=std::max_element(logits.begin(),logits.end());
    auto priorBest=std::max_element(result.rootActions.begin(),result.rootActions.end(),[](auto a,auto b){return a.prior<b.prior;});
    require(priorBest->id==legal[best-logits.begin()].id,"policy prior ordering");
    for(auto a:result.rootActions) {
        auto it=std::find_if(legal.begin(),legal.end(),[&](auto l){return l.id==a.id;});
        require(std::isfinite(a.prior) && a.prior>=0,"finite nonnegative priors");
        std::cout << "MAP(x=" << GameAction(a.id).getIdx1() << ")";
        std::cout<<" bits="<<a.id<<" logit="<<logits[it-legal.begin()]<<" prior="<<a.prior
            <<" visits="<<a.visits<<" Q="<<a.q<<'\n';
    }
    auto m=result.metrics;
    std::cout<<"selected="<<result.selectedAction.value_or(0xFFFFFFFFu)<<" simulations="<<m.simulations
        <<" decision_nodes="<<m.decisionNodes<<" chance_nodes="<<m.chanceNodes
        <<" particles="<<m.outcomeParticles<<" samples="<<m.transitionSamples
        <<" leaf_evaluations="<<m.leafEvaluations<<" max_depth="<<m.maxDepthReached<<'\n';
    // Rich features cannot see pending gold. Checkpoint projection must collect
    // it on a detached copy, and match the existing policy's completed oracle.
    std::vector<float> pendingFeatures;
    for (int amount : {1}) {
        auto pendingGold=detachedCopy(reward);
        auto &container=pendingGold.info.rewardsContainer;
        container.goldRewardCount=1; container.gold[0]=amount;
        container.cardRewardCount=container.relicCount=container.potionCount=0;
        container.emeraldKey=container.sapphireKey=false;
        collectForcedRewardGold(pendingGold);
        const auto fingerprint=test::oocStateFingerprint(pendingGold);
        const auto features=richFeatureVec(pendingGold);
        if (pendingFeatures.empty()) pendingFeatures=features;
        else require(features==pendingFeatures,"rich model cannot see pending reward contents fixture");
        auto completed=detachedCopy(pendingGold);
        ScumSearchAgent2 oracleAgent;
        for (int step=0;step<16 && completed.screenState!=ScreenState::MAP_SCREEN;++step)
            runFullRunOocPolicyStep(completed,oracleAgent,false,true);
        require(completed.screenState==ScreenState::MAP_SCREEN && completed.gold==pendingGold.gold,
            "pending gold oracle reaches checkpoint after collection");
        OocGameContextModel projected(pendingGold,path,{}, {true});
        rejects([&] { projected.leafValue(0); });
        std::mt19937_64 projectionRng(543);
        const auto savedPath=t_curPath;
        t_curPath=&projected.pathHistory(0);
        const auto oracleValue=vStateWinNative(completed);
        t_curPath=savedPath;
        const auto projectedValue=projected.evaluateLeaf(0,projectionRng);
        require(projectedValue==oracleValue,
            "pending reward projection value differs from resolved oracle");
        require(projected.continuationMetrics().pendingLeaves==1
            && projected.continuationMetrics().projectionSteps>=1,
            "pending reward projection did not retain continuation accounting");
        require(test::oocStateFingerprint(projected.state(0))==fingerprint
            && test::oocStateFingerprint(pendingGold)==fingerprint && t_curPath==savedPath,
            "pending reward projection mutated canonical root or caller path");
    }
    // All pending screen families are evaluated only after the same policy
    // continuation. This also covers selectors outside MCTS-owned decisions.
    for (int family=0;family<5;++family) {
        auto pending=detachedCopy(gc);
        if (family==0) { pending.screenState=ScreenState::SHOP_ROOM; pending.info.shop.setup(pending); }
        if (family==1) { pending.screenState=ScreenState::EVENT_SCREEN; pending.curEvent=Event::BIG_FISH;
            pending.info.hpAmount0=20; pending.info.hpAmount1=5; }
        if (family==2) pending.openCardSelectScreen(CardSelectScreenType::UPGRADE,1);
        if (family==3) pending.openCardSelectScreen(CardSelectScreenType::REMOVE,1);
        if (family==4) pending=detachedCopy(reward);
        const auto beforePending=test::oocStateFingerprint(pending);
        auto completed=detachedCopy(pending);
        PathHistory completedPath=path; completedPath.update(completed);
        const auto previousPath=t_curPath; t_curPath=&completedPath;
        ScumSearchAgent2 oracleAgent;
        for (int step=0;step<64 && completed.screenState!=ScreenState::MAP_SCREEN;++step) {
            runFullRunOocPolicyStep(completed,oracleAgent,false,true); completedPath.update(completed);
        }
        require(completed.screenState==ScreenState::MAP_SCREEN,"pending screen oracle reaches checkpoint");
        const double expectedValue=vStateWinNative(completed); t_curPath=previousPath;
        OocGameContextModel projected(pending,path,{}, {true});
        int observerCalls=0;
        auto savedObserver=std::move(sts::search::g_onGameActionExecute);
        sts::search::g_onGameActionExecute=[&](std::uint32_t,const GameContext *) { ++observerCalls; };
        t_oocStrategicTraceRows="live trace sentinel";
        const auto savedRows=t_oocStrategicTraceRows;
        std::mt19937_64 projectionRng(543);
        require(projected.evaluateLeaf(0,projectionRng)==expectedValue
            && test::oocStateFingerprint(pending)==beforePending && observerCalls==0
            && t_oocStrategicTraceRows==savedRows && t_curPath==previousPath,
            "pending screen projection matches oracle without live observer or bookkeeping mutation");
        sts::search::g_onGameActionExecute=std::move(savedObserver);
        t_oocStrategicTraceRows.clear();
    }
    // Controlled map fixtures prove horizon counting without native combat/search.
    struct HorizonSampler final : CombatTransitionSampler {
        mutable unsigned calls = 0;
        CombatRuntimeSupport support(const GameContext &, const CombatPredictorInputV1 &) const override { return {true,"supported"}; }
        CombatRuntimeSample sample(const GameContext &g,const CombatPredictorInputV1 &,std::mt19937_64 &) const override {
            ++calls;
            return {CombatRuntimeSample::Outcome::VICTORY,captureCombatTransitionState(g)};
        }
    };
    for (unsigned horizon : {1u,3u,5u}) {
        auto horizonRoot = detachedCopy(gc);
        for (auto &row : horizonRoot.map->nodes) for (auto &node : row) node.room = Room::MONSTER;
        auto sampler = std::make_shared<HorizonSampler>();
        OocAdapterOptions opts{true}; opts.leafCombats = horizon; opts.constantLeaf = true; opts.uniformLeafPolicy = true;
        OocGameContextModel projected(horizonRoot,path,sampler,opts);
        std::mt19937_64 projectionRng(912);
        const auto before = test::oocStateFingerprint(horizonRoot);
        require(projected.evaluateLeaf(0,projectionRng) == .5 && sampler->calls == horizon
            && projected.continuationMetrics().imaginedCombats == horizon
            && projected.continuationMetrics().projectionSteps >= horizon*2
            && test::oocStateFingerprint(horizonRoot) == before,
            "uniform continuation completes exact additional combat horizon and preserves root");
        require(projected.leafCalls() == 0 && projected.leafObservationCount() == 0,
            "unset leaf observer does not retain diagnostic counters");
        auto observedSampler = std::make_shared<HorizonSampler>();
        std::vector<std::uint64_t> ordinals;
        opts.leafCaptureStride = 2;
        opts.leafCaptureLimit = 2;
        opts.leafObserver = [&](const OocLeafObservation &observation) {
            ordinals.push_back(observation.ordinal);
            require(observation.value == .5 && !observation.terminal && observation.error.empty()
                && observation.actualCombats == horizon && observation.projectionSteps >= horizon*2
                && observation.stateId == 0
                && test::oocStateFingerprint(observation.initialState) == before
                && observation.initialPath.roomVisits == projected.pathHistory(0).roomVisits
                && observation.initialPath.lastNodeKey == projected.pathHistory(0).lastNodeKey,
                "leaf observation records original input and exact rollout target/counters");
            if (observation.ordinal == 1)
                require(observation.rngBefore == std::mt19937_64(912)
                    && observation.rngAfter == projectionRng,
                    "leaf observation preserves exact before/after planner RNG");
        };
        OocGameContextModel observed(horizonRoot,path,observedSampler,opts);
        std::mt19937_64 observedRng(912), controlRng(912);
        auto controlSampler = std::make_shared<HorizonSampler>();
        auto controlOpts = opts; controlOpts.leafObserver = {};
        OocGameContextModel control(horizonRoot,path,controlSampler,controlOpts);
        for (int repeat = 0; repeat < 5; ++repeat) {
            const auto expected = control.evaluateLeafWithOutcome(0,controlRng);
            const auto actual = observed.evaluateLeafWithOutcome(0,observedRng);
            require(actual.value == expected.value && actual.terminal == expected.terminal
                && actual.endpoint->hp == expected.endpoint->hp
                && actual.endpoint->floor == expected.endpoint->floor && observedRng == controlRng,
                "bounded leaf capture leaves evaluations and RNG identical");
        }
        require(observed.observationError().empty() && ordinals == std::vector<std::uint64_t>{1,3}
            && observed.leafCalls() == 5 && observed.leafObservationCount() == 2
            && observedSampler->calls == controlSampler->calls
            && observedSampler->calls == 5*horizon
            && observed.continuationMetrics().projectionSteps == control.continuationMetrics().projectionSteps,
            "leaf capture stride and cap never skip or repeat teacher evaluation");

        opts.leafObserver = [](const OocLeafObservation &) { throw std::runtime_error("observer sentinel"); };
        auto throwingSampler = std::make_shared<HorizonSampler>();
        OocGameContextModel throwing(horizonRoot,path,throwingSampler,opts);
        std::mt19937_64 throwingRng(912);
        require(throwing.evaluateLeaf(0,throwingRng) == .5 && throwingRng == projectionRng
            && throwingSampler->calls == horizon && throwing.observationError() == "observer sentinel",
            "observer exception is retained without changing the leaf or planner RNG");
    }
    {
        // Observe RNG after every transition/evaluation without changing the
        // model contract, so full-search parity also covers the final stream.
        struct ObservedSearch final : OocGenerativeModel {
            OocGameContextModel adapter;
            std::vector<std::mt19937_64> rngStates;
            ObservedSearch(const GameContext &g, const PathHistory &p,
                    std::shared_ptr<const CombatTransitionSampler> sampler, OocAdapterOptions opts)
                : adapter(g,p,std::move(sampler),std::move(opts)) {}
            std::optional<double> terminalValue(OocStateId id) const override { return adapter.terminalValue(id); }
            bool isLeafBoundary(OocStateId id) const override { return adapter.isLeafBoundary(id); }
            std::vector<OocPlannerAction> legalActions(OocStateId id) const override { return adapter.legalActions(id); }
            OocStateId sampleSuccessor(OocStateId id,OocActionId action,std::mt19937_64 &rng) override {
                const auto child=adapter.sampleSuccessor(id,action,rng); rngStates.push_back(rng); return child;
            }
            double leafValue(OocStateId id) const override { return adapter.leafValue(id); }
            double evaluateLeaf(OocStateId id,std::mt19937_64 &rng) override {
                const auto value=adapter.evaluateLeaf(id,rng); rngStates.push_back(rng); return value;
            }
            OocLeafEvaluation evaluateLeafWithOutcome(OocStateId id,std::mt19937_64 &rng) override {
                const auto value=adapter.evaluateLeafWithOutcome(id,rng); rngStates.push_back(rng); return value;
            }
        };
        auto root=detachedCopy(gc);
        for (auto &row:root.map->nodes) for(auto &node:row) node.room=Room::MONSTER;
        OocAdapterOptions opts{true}; opts.leafCombats=3; opts.constantLeaf=true;
        opts.uniformLeafPolicy=true; opts.uniformPrior=true; opts.sampleNoncombat=true;
        auto plainSampler=std::make_shared<HorizonSampler>();
        auto capturedSampler=std::make_shared<HorizonSampler>();
        ObservedSearch plain(root,path,plainSampler,opts);
        std::uint64_t observations=0;
        opts.leafCaptureLimit=2;
        opts.leafObserver=[&](const OocLeafObservation &o) {
            ++observations;
            require(o.value == .5 && o.error.empty(),"controlled search leaf target");
        };
        ObservedSearch captured(root,path,capturedSampler,opts);
        OocMctsConfig config; config.seed=912;
        const auto control=OocMctsPlanner(config).search(plain,0,16);
        const auto treatment=OocMctsPlanner(config).search(captured,0,16);
        require(!control.aborted && !treatment.aborted && control.selectedAction == treatment.selectedAction
            && control.rootActions.size() == treatment.rootActions.size()
            && control.metrics.simulations == treatment.metrics.simulations
            && control.metrics.leafEvaluations == treatment.metrics.leafEvaluations
            && control.metrics.transitionSamples == treatment.metrics.transitionSamples
            && plain.rngStates == captured.rngStates && !plain.rngStates.empty()
            && plainSampler->calls == capturedSampler->calls
            && plain.adapter.combatSamples() == captured.adapter.combatSamples()
            && plain.adapter.continuationMetrics().imaginedCombats == captured.adapter.continuationMetrics().imaginedCombats
            && plain.adapter.continuationMetrics().projectionSteps == captured.adapter.continuationMetrics().projectionSteps
            && captured.adapter.observationError().empty() && observations == 2,
            "leaf observation preserves full search decisions, metrics, combat work and RNG");
        for(std::size_t i=0;i<control.rootActions.size();++i) {
            const auto &a=control.rootActions[i], &b=treatment.rootActions[i];
            require(a.id==b.id && a.prior==b.prior && a.visits==b.visits && a.q==b.q,
                "leaf observation preserves every root prior, visit count and Q exactly");
        }
        {
            // Exercise production selection and sink wiring together, using
            // the same bounded synthetic teacher as the model parity fixture.
            char directory[]="/tmp/sts-leaf-select-XXXXXX";
            require(mkdtemp(directory)!=nullptr,"leaf selection temp directory");
            const std::string capturePath=std::string(directory)+"/capture.jsonl";
            struct RestoreCapture {
                OocAdapterOptions options=liveOptions;
                OocMctsConfig config=liveConfig;
                std::unique_ptr<OocLeafCaptureSink> sink=std::move(liveLeafCapture);
                std::string path, directory;
                ~RestoreCapture() {
                    liveLeafCapture=std::move(sink);
                    liveOptions=std::move(options); liveConfig=std::move(config);
                    std::remove(path.c_str()); rmdir(directory.c_str());
                }
            } restore{liveOptions,liveConfig,std::move(liveLeafCapture),capturePath,directory};
            liveOptions=opts; liveOptions.leafObserver={}; liveConfig={};
            std::uint64_t plainSamples=0,capturedSamples=0;
            OocContinuationMetrics plainContinuation,capturedContinuation;
            auto plainTeacher=std::make_shared<HorizonSampler>();
            auto capturedTeacher=std::make_shared<HorizonSampler>();
            const auto plainResult=selectOocMctsAction(root,path,42,7,16,plainTeacher,
                plainSamples,&plainContinuation,nullptr);
            liveLeafCapture=std::make_unique<OocLeafCaptureSink>(capturePath,
                nlohmann::json{{"fixture","synthetic_horizon_sampler"}});
            const auto capturedResult=selectOocMctsAction(root,path,42,7,16,capturedTeacher,
                capturedSamples,&capturedContinuation,nullptr);
            require(!plainResult.aborted && !capturedResult.aborted
                && capturedResult.selectedAction.has_value()
                && plainResult.selectedAction==capturedResult.selectedAction
                && plainResult.metrics.simulations==capturedResult.metrics.simulations
                && plainSamples==capturedSamples && plainTeacher->calls==capturedTeacher->calls
                && plainContinuation.projectionSteps==capturedContinuation.projectionSteps,
                "production selection capture preserves result and teacher work");
            std::ifstream input(capturePath);
            std::string line;
            require(bool(std::getline(input,line)) && nlohmann::json::parse(line).at("type")=="header",
                "production selection capture header");
            require(bool(std::getline(input,line)),"production selection capture root row");
            const auto saved=nlohmann::json::parse(line);
            const auto &leaves=saved.at("leaves");
            const auto stride=saved.at("stride").get<std::uint64_t>();
            const auto calls=saved.at("leafCalls").get<std::uint64_t>();
            require(saved.at("runSeed")==42 && saved.at("decisionIndex")==7
                && saved.at("searchSeed")==oocMctsSearchSeed(42,7)
                && saved.at("aborted")==false && saved.at("observationError")==""
                && saved.at("selectedAction")==*capturedResult.selectedAction
                && saved.at("completedSimulations")==capturedResult.metrics.simulations
                && saved.at("requestedLeafCombats")==3 && stride==2 && calls>0
                && !leaves.empty() && leaves.size()==std::min<std::uint64_t>(8,1+(calls-1)/stride)
                && saved.at("sampledCalls")==leaves.size() && saved.at("validSamples")==leaves.size(),
                "production selection binds bounded sampled leaves to final successful root");
            for(std::size_t i=0;i<leaves.size();++i) {
                const auto &leaf=leaves[i];
                require(leaf.at("ordinal")==1+i*stride && leaf.at("target")==.5
                    && leaf.at("actualCombats")==3 && leaf.at("structurallyValidSample")==true
                    && leaf.at("inputError")=="" && leaf.at("evaluationError")==""
                    && leaf.at("input").at("schema")=="candidate-public-leaf-v1"
                    && leaf.at("input").at("ascension")==root.ascension
                    && !leaf.at("diagnostics").at("plannerRngBefore").get<std::string>().empty(),
                    "production selection captures exact target, candidate input and ordinal schedule");
            }
            require(!std::getline(input,line),"production selection emits one root row");
        }
        for(const auto outcome:{GameOutcome::PLAYER_LOSS,GameOutcome::PLAYER_VICTORY}) {
            auto terminalRoot=detachedCopy(root); terminalRoot.outcome=outcome; terminalRoot.act=4;
            bool seen=false;
            opts.leafObserver=[&](const OocLeafObservation &o) {
                seen=true;
                require(o.terminal && o.value == (outcome==GameOutcome::PLAYER_VICTORY ? 1.0 : 0.0)
                    && o.actualCombats==0 && o.projectionSteps==0 && o.error.empty(),
                    "terminal leaf has exact target without a fabricated continuation");
            };
            OocGameContextModel terminal(terminalRoot,path,{},opts);
            std::mt19937_64 terminalRng(912);
            terminal.evaluateLeafWithOutcome(0,terminalRng);
            require(seen && terminal.observationError().empty(),"terminal leaf observation succeeds");
        }
        bool sawUnsupported=false;
        opts.leafObserver=[&](const OocLeafObservation &o) {
            sawUnsupported=true;
            require(!o.value && o.error=="missing_sampler" && o.actualCombats==0,
                "unsupported leaf records a reason without a scalar target");
            throw std::runtime_error("abort observer sentinel");
        };
        OocGameContextModel unsupported(root,path,{},opts);
        std::mt19937_64 unsupportedRng(912);
        bool rethrown=false;
        try { unsupported.evaluateLeaf(0,unsupportedRng); }
        catch(const OocSearchUnsupported &error) { rethrown=std::string(error.what())=="missing_sampler"; }
        require(sawUnsupported && rethrown && unsupported.observationError()=="abort observer sentinel",
            "observer failure does not replace the original unsupported exception");
    }
    // Boss rollout: continue past map checkpoints to the act boss; win 1, death 0.
    struct BossOutcomeSampler final : CombatTransitionSampler {
        bool bossDies = false;
        mutable unsigned calls = 0, bossCalls = 0;
        CombatRuntimeSupport support(const GameContext &g, const CombatPredictorInputV1 &) const override {
            if (g.relics.has(RelicId::LIZARD_TAIL) && g.relics.getRelicValue(RelicId::LIZARD_TAIL) == 1)
                return {false,"active_unqualified_lizard"};
            return {true,"supported"};
        }
        CombatRuntimeSample sample(const GameContext &g,const CombatPredictorInputV1 &,std::mt19937_64 &) const override {
            ++calls;
            if (g.curRoom != Room::BOSS) return {CombatRuntimeSample::Outcome::VICTORY,captureCombatTransitionState(g)};
            ++bossCalls;
            return {bossDies ? CombatRuntimeSample::Outcome::DEATH : CombatRuntimeSample::Outcome::VICTORY,
                captureCombatTransitionState(g)};
        }
    };
    // Controlled A20 horizon: never stop at boss one, regardless of boss two's outcome.
    struct DoubleBossSampler final : CombatTransitionSampler {
        bool secondDies = false;
        mutable unsigned calls = 0;
        CombatRuntimeSupport support(const GameContext &, const CombatPredictorInputV1 &) const override {
            return {true,"supported"};
        }
        CombatRuntimeSample sample(const GameContext &g,const CombatPredictorInputV1 &,std::mt19937_64 &) const override {
            ++calls;
            return {secondDies && calls == 2 ? CombatRuntimeSample::Outcome::DEATH
                : CombatRuntimeSample::Outcome::VICTORY, captureCombatTransitionState(g)};
        }
    };
    for (const bool secondDies : {false,true}) {
        auto root = detachedCopy(gc);
        root.act = 3; root.ascension = 20; root.curRoom = Room::BOSS;
        root.screenState = ScreenState::BATTLE;
        root.boss = MonsterEncounter::TIME_EATER; root.secondBoss = MonsterEncounter::AWAKENED_ONE;
        root.info.encounter = root.boss;
        auto sampler = std::make_shared<DoubleBossSampler>(); sampler->secondDies = secondDies;
        root.regainControlAction = [sampler](GameContext &state) {
            if (sampler->calls == 1) {
                state.info.encounter = state.secondBoss; state.screenState = ScreenState::BATTLE;
            } else state.outcome = GameOutcome::PLAYER_VICTORY;
        };
        auto deps = defaultOocMctsDependencies(); deps.stopAfterAct = [] { return 3; };
        OocAdapterOptions opts{true}; opts.leafCombats = 3;
        OocGameContextModel projected(root,path,sampler,opts,deps);
        std::mt19937_64 rng(913);
        const auto result = projected.evaluateLeafWithOutcome(0,rng);
        require(result.terminal && result.value == (secondDies ? 0.0 : 1.0) && sampler->calls == 2,
            "A20 Act-3 horizon waits through the second boss death or victory");
    }
    for (int variant : {0,1,2}) {
        const bool bossDies = variant == 1, activeTail = variant == 2;
        auto bossRoot = detachedCopy(gc);
        for (auto &row : bossRoot.map->nodes) for (auto &node : row) node.room = Room::MONSTER;
        if (activeTail) { bossRoot.relics.remove(RelicId::LIZARD_TAIL); bossRoot.relics.add({RelicId::LIZARD_TAIL,1}); }
        auto sampler = std::make_shared<BossOutcomeSampler>(); sampler->bossDies = bossDies;
        OocAdapterOptions opts{true}; opts.bossRollout = true; opts.uniformLeafPolicy = true;
        OocGameContextModel projected(bossRoot,path,sampler,opts);
        std::mt19937_64 projectionRng(913);
        const auto before = test::oocStateFingerprint(bossRoot);
        const auto leaf = projected.evaluateLeafWithOutcome(0,projectionRng);
        require(leaf.value == (bossDies ? 0.0 : 1.0) && (!bossDies || leaf.terminal)
            && sampler->bossCalls == 1 && sampler->calls > 3
            && projected.continuationMetrics().imaginedCombats == sampler->calls + activeTail
            && test::oocStateFingerprint(bossRoot) == before
            && projected.continuationMetrics().supportReasons.count("bossrollout_lizard_spent") == activeTail,
            "boss rollout continues to the act boss and scores its outcome");
    }
    {
        // Boss-rollout target: a boss counts as beaten only after its fight.
        auto probe = detachedCopy(gc);
        const auto cleared = [&](int act, Room room, ScreenState screen, int y = 15) {
            probe.act = act; probe.curRoom = room; probe.screenState = screen; probe.curMapNodeY = y;
            return bossesCleared(probe);
        };
        require(cleared(1,Room::MONSTER,ScreenState::MAP_SCREEN) == 0
            && cleared(1,Room::BOSS,ScreenState::BATTLE) == 0
            && cleared(1,Room::BOSS,ScreenState::REWARDS) == 1
            && cleared(1,Room::BOSS_TREASURE,ScreenState::BOSS_RELIC_REWARDS) == 1
            && cleared(1,Room::BOSS_TREASURE,ScreenState::CARD_SELECT) == 1
            && cleared(2,Room::BOSS_TREASURE,ScreenState::MAP_SCREEN,-1) == 1
            && cleared(3,Room::BOSS_TREASURE,ScreenState::MAP_SCREEN,-1) == 2
            && cleared(2,Room::MONSTER,ScreenState::MAP_SCREEN) == 1
            && cleared(2,Room::BOSS,ScreenState::BATTLE) == 1
            && cleared(3,Room::BOSS,ScreenState::REWARDS) == 3,
            "boss rollout counts bosses beaten");
        auto nextAct = detachedCopy(gc);
        nextAct.curRoom = Room::BOSS_TREASURE; nextAct.curMapNodeY = 15; nextAct.transitionToAct(2);
        require(bossesCleared(nextAct) == 1 && nextAct.curRoom == Room::BOSS_TREASURE,
            "act start after a real transition counts only the previous boss");
    }
    {
        OocMctsConfig parsed; OocAdapterOptions opts{true};
        applyLiveControl("STS_OOC_MCTS_LEAF_VALUE","bossrollout",parsed,opts);
        require(opts.bossRollout && !opts.bossLeaf && !opts.screenLeaf,"boss rollout leaf parsed");
        applyLiveControl("STS_OOC_MCTS_LEAF_VALUE","native",parsed,opts);
        require(!opts.bossRollout,"native leaf clears boss rollout");
    }
    {
        // Inject the bounded-continuation exception after a genuine successful
        // adapter surrogate draw; isolate root-abort accounting from native exits.
        auto root=detachedCopy(gc);
        for (auto &row : root.map->nodes) for (auto &node : row) node.room=Room::MONSTER;
        auto sampler=std::make_shared<HorizonSampler>();
        OocGameContextModel adapter(root,path,sampler,{true});
        struct BoundModel final : OocGenerativeModel {
            OocGameContextModel &adapter;
            explicit BoundModel(OocGameContextModel &a):adapter(a) {}
            std::optional<double> terminalValue(OocStateId id) const override { return adapter.terminalValue(id); }
            bool isLeafBoundary(OocStateId id) const override { return id != 0 || adapter.isLeafBoundary(id); }
            std::vector<OocPlannerAction> legalActions(OocStateId id) const override { return adapter.legalActions(id); }
            OocStateId sampleSuccessor(OocStateId id,OocActionId a,std::mt19937_64 &r) override { return adapter.sampleSuccessor(id,a,r); }
            double leafValue(OocStateId) const override { throw OocSearchUnsupported("continuation_step_limit_1024"); }
        } bounded(adapter);
        OocMctsConfig config;
        const auto result=OocMctsPlanner(config).search(bounded,0,1);
        auto counters=adapter.continuationMetrics();
        recordSearchAbort(result,counters);
        const auto samples=adapter.combatSamples();
        require(result.aborted && !result.selectedAction && result.rootActions.empty()
            && result.abortReason=="continuation_step_limit_1024"
            && counters.continuationLimitAborts==1
            && counters.continuationReasons.at(result.abortReason)==1
            && counters.unsupportedCombats==0 && counters.supportReasons.empty()
            && counters.imaginedCombats==samples && samples==1 && sampler->calls==1,
            "continuation limit abort preserves honest successful combat and separate reason accounting");
    }
    {
        auto pending = detachedCopy(gc); pending.screenState = ScreenState::EVENT_SCREEN;
        pending.curEvent = Event::BIG_FISH; pending.info.hpAmount0 = 20; pending.info.hpAmount1 = 5;
        auto oracle = detachedCopy(pending);
        std::mt19937_64 oracleRng(919), projectionRng(919);
        oracleRng(); // Existing continuation agent seeding consumes one search draw.
        const auto actions = v4CandidateActions(oracle);
        require(v4DecisionSupported(oracle) && actions.size() > 1, "uniform event fixture legal alternatives");
        actions[std::uniform_int_distribution<std::size_t>(0,actions.size()-1)(oracleRng)].execute(oracle);
        ScumSearchAgent2 oracleAgent;
        for (int step=0; step<64 && oracle.screenState != ScreenState::MAP_SCREEN; ++step)
            runFullRunOocPolicyStep(oracle,oracleAgent,false,true);
        PathHistory oraclePath=path; oraclePath.update(oracle);
        const auto previousPath=t_curPath; t_curPath=&oraclePath;
        const double expected=vStateWinNative(oracle); t_curPath=previousPath;
        OocAdapterOptions opts{true}; opts.uniformLeafPolicy=true;
        OocGameContextModel projected(pending,path,{},opts);
        require(projected.evaluateLeaf(0,projectionRng)==expected,
            "uniform supported decision executes correct primitive and resolves checkpoint");
    }
    // A single unsupported combat invalidates the entire root; never choose
    // from partial Q, assign a scalar penalty, or call a real combat backend.
    fake->enabled=false;
    OocGameContextModel unsupportedRoot(combatRoot,path,fake,{true});
    const auto unsupportedBefore=test::oocStateFingerprint(unsupportedRoot.state(0));
    const auto samplesBeforeAbort=fake->sampleCalls;
    std::mt19937_64 adapterRng(77), untouchedRng(77);
    rejects([&] { unsupportedRoot.sampleSuccessor(0,sourceId(unsupportedRoot,restAction.bits),adapterRng); });
    require(unsupportedRoot.continuationMetrics().imaginedCombats==1
        && unsupportedRoot.continuationMetrics().unsupportedCombats==1
        && unsupportedRoot.continuationMetrics().supportReasons.at("fake unsupported")==1
        && fake->sampleCalls==samplesBeforeAbort && adapterRng==untouchedRng
        && test::oocStateFingerprint(unsupportedRoot.state(0))==unsupportedBefore,
        "unsupported input aborts before any draw/combat/value and preserves root");
    OocGameContextModel unsupportedPlanner(combatRoot,path,fake,{true});
    SingleEntryModel unsupportedEntry(unsupportedPlanner,sourceId(unsupportedPlanner,restAction.bits));
    const auto aborted=OocMctsPlanner().search(unsupportedEntry,0,128);
    require(aborted.aborted && !aborted.selectedAction && aborted.rootActions.empty()
        && aborted.metrics.simulations==0 && aborted.metrics.simulationAttempts==1
        && aborted.abortReason=="fake unsupported","unsupported root returns no partial action with counted attempt");
    // A surprise UNSUPPORTED sample uses the same whole-root contract.
    struct UnsupportedDraw final : CombatTransitionSampler {
        CombatRuntimeSupport support(const GameContext &,const CombatPredictorInputV1 &) const override { return {true,"supported"}; }
        CombatRuntimeSample sample(const GameContext &,const CombatPredictorInputV1 &,std::mt19937_64 &) const override { return {}; }
    };
    OocGameContextModel unsupportedDraw(combatRoot,path,std::make_shared<UnsupportedDraw>(),{true});
    SingleEntryModel unsupportedDrawEntry(unsupportedDraw,sourceId(unsupportedDraw,restAction.bits));
    const auto abortedDraw=OocMctsPlanner().search(unsupportedDrawEntry,0,128);
    require(abortedDraw.aborted && !abortedDraw.selectedAction
        && unsupportedDraw.continuationMetrics().supportReasons.at("sample_returned_unsupported")==1,
        "unsupported sample cannot escape into a BATTLE scalar leaf");
    // Even an optional configured leaf policy cannot bypass the surrogate.
    const bool beforeDisallow=sts::search::g_disallowImaginedCombat;
    {
        ImaginedScope scope;
        ScumSearchAgent2 forbiddenAgent; BattleContext forbiddenBattle;
        auto detachedBattle=detachedCopy(battle);
        rejects([&] { forbiddenAgent.playoutBattle(detachedBattle,forbiddenBattle); });
    }
    require(sts::search::g_disallowImaginedCombat==beforeDisallow,"surrogate-only guard restores real combat permission");
    OocGameContextModel deterministicOoc(ordinary,path,{}, {true});
    const auto deterministicId=deterministicOoc.sampleSuccessor(0,sourceId(deterministicOoc,ordinaryAction.bits),adapterRng);
    const auto rngBeforeCache=adapterRng;
    require(deterministicOoc.isDeterministicTransition(0,sourceId(deterministicOoc,ordinaryAction.bits))
        && deterministicOoc.sampleSuccessor(0,sourceId(deterministicOoc,ordinaryAction.bits),adapterRng)==deterministicId
        && adapterRng==rngBeforeCache,"deterministic OOC child reused without RNG draw");
    std::cout << "corrected_continuations reward_oracle=exact unsupported_root=V4 unsupported_sample=V4 native_imagination=forbidden deterministic_reuse=exact\n";
    // No fallback even if availability changes after construction.
    bool policyOk=g_oocStrategicTokNet.ok; g_oocStrategicTokNet.ok=false;
    rejects([&] { OocGameContextModel unavailable(gc,path); });
    g_oocStrategicTokNet.ok=policyOk;
    // Exercise the same live dispatch seam with a stateless lethal imagined
    // sampler. Every selected first-row map action must leave live combat pending.
    struct ImaginedDeath final : CombatTransitionSampler {
        CombatRuntimeSupport support(const GameContext &, const CombatPredictorInputV1 &) const override {
            return {true, "test supported"};
        }
        CombatRuntimeSample sample(const GameContext &, const CombatPredictorInputV1 &,
                                   std::mt19937_64 &) const override {
            return {CombatRuntimeSample::Outcome::DEATH, {}};
        }
    };
    struct LiveConfigScope {
        bool enabled = liveEnabled;
        std::uint64_t simulations = liveSimulations;
        std::shared_ptr<const CombatTransitionSampler> sampler = liveSampler;
        std::shared_ptr<const CombatTransitionSampler> samplerA20 = liveSamplerA20;
        sts::search::OocMctsConfig config = liveConfig;
        OocAdapterOptions options = liveOptions;
        ~LiveConfigScope() { liveEnabled=enabled; liveSimulations=simulations; liveSampler=sampler;
            liveSamplerA20=samplerA20; liveConfig=config; liveOptions=options; }
    } liveScope;
    liveSamplerA20.reset();
    auto live=GameContext(CharacterClass::IRONCLAD, 42, 0);
    live.screenState=ScreenState::MAP_SCREEN;
    live.curEvent=Event::INVALID;
    live.regainControlAction=[](GameContext &g) { g.screenState=ScreenState::MAP_SCREEN; };
    for (auto &node : live.map->nodes[0]) node.room=Room::MONSTER;
    PathHistory livePath; livePath.update(live);
    const auto before=test::oocStateFingerprint(live);
    const auto beforePath=livePath;
    LiveOocMctsMetrics offMetrics;
    liveEnabled=false; liveSampler.reset();
    require(!oocMctsPolicyStep(live,livePath,42,7,offMetrics)
        && offMetrics.decisions==1 && offMetrics.search.simulations==0
        && test::oocStateFingerprint(live)==before, "OFF dispatch has no search/model/RNG use");
    struct AlwaysUnsupported final : CombatTransitionSampler {
        CombatRuntimeSupport support(const GameContext &,const CombatPredictorInputV1 &) const override { return {false,"test unsupported"}; }
        CombatRuntimeSample sample(const GameContext &,const CombatPredictorInputV1 &,std::mt19937_64 &) const override {
            throw std::runtime_error("unsupported sampler must not draw");
        }
    };
    liveEnabled=true; liveSimulations=128; liveSampler=std::make_shared<AlwaysUnsupported>();
    LiveOocMctsMetrics unsupportedMetrics;
    require(!oocMctsPolicyStep(live,livePath,42,7,unsupportedMetrics)
        && unsupportedMetrics.fallback==1 && unsupportedMetrics.supportAborts==1
        && unsupportedMetrics.owned==0 && unsupportedMetrics.search.trivialRootBypasses==0
        && unsupportedMetrics.search.simulationAttempts==1
        && unsupportedMetrics.search.simulations==0 && unsupportedMetrics.continuation.unsupportedCombats==1
        && unsupportedMetrics.continuation.supportReasons.at("test unsupported")==1
        && test::oocStateFingerprint(live)==before && !sts::search::g_disallowImaginedCombat,
        "unsupported live search returns untouched decision to existing V4 with reconciled abort metrics");
    {
        // STS_OOC_MCTS_UNSUPPORTED_SILVER_SIMS: a refused combat is played by Silver, counted by reason,
        // on a redrawn future; the source state is untouched.
        auto fight=detachedCopy(live);
        fight.curRoom=Room::MONSTER;
        fight.enterBattle(MonsterEncounter::CULTIST);
        const auto fightBefore=test::oocStateFingerprint(fight);
        const auto input=captureCombatPredictorInput(fight,MonsterEncounter::CULTIST,0.0);
        const SilverFallbackCombatTransitionSampler fallback(std::make_shared<AlwaysUnsupported>(),64);
        const auto prepared=fallback.prepare(fight,input);
        std::mt19937_64 first(1),second(1);
        const auto a=prepared->sample(first), b=fallback.sample(fight,input,second);
        const auto reasons=fallback.takeReasons();
        require(prepared->support().supported && fallback.support(fight,input).supported
            && a.outcome!=CombatRuntimeSample::Outcome::UNSUPPORTED && a.outcome==b.outcome
            && a.rawPost.curHp==b.rawPost.curHp && reasons.size()==1 && reasons.at("test unsupported")==2
            && fallback.takeReasons().empty() && test::oocStateFingerprint(fight)==fightBefore
            && !sts::search::g_disallowImaginedCombat,
            "Silver fallback resolves refused combats deterministically per planner RNG and counts them");
        // STS_OOC_MCTS_ACT4_SILVER_SIMS alone: other refusals still abort; Act-4 combats skip the CTM.
        const SilverFallbackCombatTransitionSampler act4Only(std::make_shared<AlwaysUnsupported>(),0,16);
        require(!act4Only.support(fight,input).supported && !act4Only.prepare(fight,input)->support().supported
            && act4Only.sample(fight,input,first).outcome==CombatRuntimeSample::Outcome::UNSUPPORTED
            && act4Only.takeReasons().empty(), "Act-4 route leaves other refused combats to the abort path");
        auto heart=detachedCopy(live);
        heart.act=4; heart.floorNum=55;
        heart.curRoom=Room::BOSS;
        heart.enterBattle(MonsterEncounter::THE_HEART);
        const auto heartBefore=test::oocStateFingerprint(heart);
        const auto heartInput=captureCombatPredictorInput(heart,MonsterEncounter::THE_HEART,0.0);
        std::mt19937_64 third(2),fourth(2);
        const auto preparedHeart=act4Only.prepare(heart,heartInput);
        const auto h1=preparedHeart->sample(third), h2=act4Only.sample(heart,heartInput,fourth);
        const auto heartReasons=act4Only.takeReasons();
        require(preparedHeart->support().supported && act4Only.support(heart,heartInput).supported
            && h1.outcome!=CombatRuntimeSample::Outcome::UNSUPPORTED && h1.outcome==h2.outcome
            && h1.rawPost.curHp==h2.rawPost.curHp && heartReasons.size()==1 && heartReasons.at("act4_silver")==2
            && test::oocStateFingerprint(heart)==heartBefore && !sts::search::g_disallowImaginedCombat,
            "Act-4 route plays the Heart with Silver and never asks the CTM");
    }
    auto sole=detachedCopy(live);
    int firstNode=-1;
    for (auto &node : sole.map->nodes[0]) {
        if (firstNode < 0 && node.edgeCount > 0) firstNode=node.x;
        else node.edgeCount=0;
    }
    PathHistory solePath; solePath.update(sole);
    const auto soleCandidates=v4CandidateActions(sole);
    require(soleCandidates.size()==1,"sole map candidate fixture");
    OocGameContextModel soleModel(sole,solePath,liveSampler,liveOptions);
    const auto soleAction=soleModel.soleLegalAction(0);
    const auto soleBypass=searchWithSoleRootShortcut(soleModel,liveConfig,soleAction,128);
    require(soleAction && soleBypass.selectedAction==soleAction && !soleBypass.aborted
        && soleBypass.metrics.trivialRootBypasses==1 && soleBypass.metrics.simulations==0
        && soleBypass.metrics.simulationAttempts==0 && soleBypass.metrics.transitionSamples==0
        && soleBypass.metrics.leafEvaluations==0 && soleModel.combatSamples()==0
        && soleBypass.rootActions.size()==1 && soleBypass.rootActions[0].prior==1.0
        && soleBypass.rootActions[0].visits==0,
        "sole map root bypasses unsupported hypothetical continuation");
    auto profileConfig = liveConfig;
    profileConfig.profileSearch = true;
    const auto profiledSole = searchWithSoleRootShortcut(soleModel, profileConfig, soleAction, 128);
    require(profiledSole.selectedAction == soleBypass.selectedAction
        && profiledSole.metrics.trivialRootBypasses == 1
        && profiledSole.metrics.simulationAttempts == 0
        && profiledSole.metrics.expandedActionHistogram.empty(),
        "branch profiling preserves sole-root bypass and zero work");
    auto soleWithPotions=detachedCopy(sole);
    soleWithPotions.potions[0]=Potion::FIRE_POTION;
    soleWithPotions.potionCount=1;
    OocGameContextModel potionModel(soleWithPotions,solePath,liveSampler,liveOptions);
    const auto potionAction=potionModel.soleLegalAction(0);
    const auto potionBypass=searchWithSoleRootShortcut(potionModel,liveConfig,potionAction,128);
    require(potionAction && potionBypass.selectedAction==potionAction
        && potionBypass.metrics.trivialRootBypasses==1
        && potionBypass.metrics.simulationAttempts==0 && potionModel.combatSamples()==0,
        "held potion does not create a competing standalone discard action");
    auto observedConfig=liveConfig;
    observedConfig.observeRootLock=true;
    OocGameContextModel observedSole(sole,solePath,liveSampler,liveOptions);
    const auto observedSearch=searchWithSoleRootShortcut(observedSole,observedConfig,
        observedSole.soleLegalAction(0),128);
    require(observedSearch.metrics.trivialRootBypasses==0
        && observedSearch.metrics.simulationAttempts>0,
        "root-lock observer searches a forced root");
    auto checkpointConfig=liveConfig;
    checkpointConfig.rootCheckpointSimulations={1};
    OocGameContextModel checkpointSole(sole,solePath,liveSampler,liveOptions);
    const auto checkpointSearch=searchWithSoleRootShortcut(checkpointSole,checkpointConfig,
        checkpointSole.soleLegalAction(0),128);
    require(checkpointSearch.metrics.trivialRootBypasses==0
        && checkpointSearch.metrics.simulationAttempts>0,
        "explicit root checkpoint searches a forced root");
    const auto soleSearch=OocMctsPlanner(liveConfig).search(soleModel,0,128);
    require(soleSearch.aborted && soleSearch.metrics.simulationAttempts==1,
        "normal sole-action search aborts after entering unsupported combat");
    auto solePrimitive=detachedCopy(sole), soleFallback=detachedCopy(sole);
    soleCandidates.front().execute(solePrimitive);
    ScumSearchAgent2 soleAgent;
    runFullRunOocPolicyStep(soleFallback,soleAgent,false,true);
    require(test::oocStateFingerprint(soleFallback)==test::oocStateFingerprint(solePrimitive),
        "sole candidate equals original whole-root fallback primitive including live RNG");
    LiveOocMctsMetrics soleMetrics;
    const auto soleBefore=test::oocStateFingerprint(sole);
    require(oocMctsPolicyStep(sole,solePath,42,7,soleMetrics)
        && soleMetrics.search.trivialRootBypasses==1 && soleMetrics.search.simulations==0
        && soleMetrics.search.simulationAttempts==0 && soleMetrics.search.transitionSamples==0
        && soleMetrics.search.leafEvaluations==0 && soleMetrics.combatSamples==0
        && soleMetrics.supportAborts==0 && soleMetrics.fallback==0 && soleMetrics.owned==1
        && test::oocStateFingerprint(sole)==test::oocStateFingerprint(solePrimitive)
        && test::oocStateFingerprint(sole)!=soleBefore,
        "sole map root executes its exact primitive without search or fallback");

    auto makeRewardRoot = [] {
        auto root = GameContext(CharacterClass::IRONCLAD, 84321, 0);
        root.screenState = ScreenState::REWARDS;
        root.info.rewardsContainer.clear();
        root.info.rewardsContainer.addGold(25);
        root.regainControlAction = [](GameContext &g) {
            g.screenState = ScreenState::MAP_SCREEN;
            g.regainControlAction = nullptr;
        };
        return root;
    };
    liveEnabled = true;
    liveSimulations = 128;
    liveSampler = std::make_shared<AlwaysUnsupported>();
    const auto optionsBeforeGoldRoots = liveOptions;
    liveOptions = {};
    auto goldOnly = makeRewardRoot();
    const int goldOnlyBefore = goldOnly.gold;
    PathHistory goldOnlyPath;
    goldOnlyPath.update(goldOnly);
    LiveOocMctsMetrics goldOnlyMetrics;
    const bool goldOnlyHandled = oocMctsPolicyStep(goldOnly, goldOnlyPath, 42, 9, goldOnlyMetrics);
    if (!(goldOnlyHandled && goldOnly.gold == goldOnlyBefore + 25
            && goldOnly.info.rewardsContainer.goldRewardCount == 0
            && goldOnly.screenState == ScreenState::MAP_SCREEN
            && goldOnlyMetrics.search.trivialRootBypasses == 1
            && goldOnlyMetrics.search.simulations == 0
            && goldOnlyMetrics.search.simulationAttempts == 0))
        throw std::runtime_error("live native gold-only root: handled=" + std::to_string(goldOnlyHandled)
            + " gold=" + std::to_string(goldOnly.gold)
            + " remaining=" + std::to_string(goldOnly.info.rewardsContainer.goldRewardCount)
            + " screen=" + std::to_string(int(goldOnly.screenState))
            + " bypass=" + std::to_string(goldOnlyMetrics.search.trivialRootBypasses)
            + " simulations=" + std::to_string(goldOnlyMetrics.search.simulations)
            + " fallback=" + std::to_string(goldOnlyMetrics.fallback));

    auto goldAndCard = makeRewardRoot();
    const int goldAndCardBefore = goldAndCard.gold;
    const int goldAndCardDeckBefore = goldAndCard.deck.size();
    CardReward meaningful;
    meaningful.push_back(Card(CardId::BASH));
    goldAndCard.info.rewardsContainer.addCardReward(meaningful);
    const auto goldAndCardActions = enumerateOocSemanticPrimitiveBindings(goldAndCard);
    const auto cardAction = std::find_if(goldAndCardActions.bindings.begin(), goldAndCardActions.bindings.end(),
        [](const auto &binding) {
            return binding.semantic.effect == OocSemanticEffect::TAKE_CARD;
        });
    require(cardAction != goldAndCardActions.bindings.end(), "gold plus card fixture lacks card action");
    liveOptions.rootPrimitiveBits = std::set<std::uint32_t>{cardAction->primitiveBits};
    PathHistory goldAndCardPath;
    goldAndCardPath.update(goldAndCard);
    LiveOocMctsMetrics goldAndCardMetrics;
    const bool goldAndCardHandled = oocMctsPolicyStep(goldAndCard, goldAndCardPath, 42, 10, goldAndCardMetrics);
    const bool cardAdded = goldAndCard.deck.size() == goldAndCardDeckBefore + 1;
    const auto remainingSemantic = enumerateOocSemanticActions(goldAndCard);
    const bool goldCandidateRemains = std::any_of(remainingSemantic.actions.begin(),
        remainingSemantic.actions.end(), [](const auto &action) {
            return action.effect == OocSemanticEffect::TAKE_GOLD;
        });
    if (!(goldAndCardHandled && goldAndCard.gold == goldAndCardBefore + 25
            && goldAndCard.info.rewardsContainer.goldRewardCount == 0
            && goldAndCard.screenState == ScreenState::MAP_SCREEN && cardAdded
            && goldAndCard.info.rewardsContainer.cardRewardCount == 0 && !goldCandidateRemains
            && goldAndCardMetrics.search.trivialRootBypasses == 1
            && goldAndCardMetrics.search.simulations == 0))
        throw std::runtime_error("live native gold plus card root: handled=" + std::to_string(goldAndCardHandled)
            + " gold=" + std::to_string(goldAndCard.gold)
            + " before=" + std::to_string(goldAndCardBefore)
            + " goldLeft=" + std::to_string(goldAndCard.info.rewardsContainer.goldRewardCount)
            + " screen=" + std::to_string(int(goldAndCard.screenState))
            + " cardAdded=" + std::to_string(cardAdded)
            + " bypass=" + std::to_string(goldAndCardMetrics.search.trivialRootBypasses)
            + " sims=" + std::to_string(goldAndCardMetrics.search.simulations)
            + " fallback=" + std::to_string(goldAndCardMetrics.fallback));

    // STS_OOC_MCTS_TREE_RULES: gold and a potion with belt space are taken
    // before the root, so only the card choice remains; off keeps both.
    for (const bool rules : {false, true}) {
        auto rewardRoot = makeRewardRoot();
        rewardRoot.info.rewardsContainer.addPotion(Potion::FIRE_POTION);
        CardReward cards;
        cards.push_back(Card(CardId::BASH));
        cards.push_back(Card(CardId::CLEAVE));
        rewardRoot.info.rewardsContainer.addCardReward(cards);
        PathHistory rewardPath;
        rewardPath.update(rewardRoot);
        OocAdapterOptions ruleOptions;
        ruleOptions.treeRules = rules;
        OocGameContextModel rewardModel(rewardRoot, rewardPath, {}, ruleOptions);
        bool goldOrPotion = false;
        for (const auto &a : rewardModel.legalActions(0)) {
            const auto effect = rewardModel.candidate(0, a.id).semantic->effect;
            goldOrPotion |= effect == OocSemanticEffect::TAKE_GOLD || effect == OocSemanticEffect::TAKE_POTION;
        }
        require(goldOrPotion != rules && (rewardModel.state(0).potionCount == (rules ? 1 : 0)),
            "tree rules take gold and a potion with belt space before the root");
    }
    // STS_OOC_MCTS_POTION_KEEP_PRIOR: a full belt whose potions all outrank the reward (the rule
    // declines) gives the uniform root discard candidates; the option ranks them by keep value,
    // all below "Leave rewards", and leaves other candidates flat.
    for (const bool keepPrior : {false, true}) {
        auto rewardRoot = makeRewardRoot();
        rewardRoot.info.rewardsContainer.addPotion(Potion::ELIXIR_POTION);
        const Potion held[] = {Potion::BLOOD_POTION, Potion::HEART_OF_IRON, Potion::FRUIT_JUICE};
        rewardRoot.potionCount = 0;
        for (int slot = 0; slot < rewardRoot.potionCapacity; ++slot) {
            rewardRoot.potions[slot] = held[slot % 3]; ++rewardRoot.potionCount;
        }
        PathHistory rewardPath;
        rewardPath.update(rewardRoot);
        OocAdapterOptions keepOptions;
        keepOptions.potionKeepPrior = keepPrior;
        OocGameContextModel rewardModel(rewardRoot, rewardPath, {}, keepOptions);
        std::map<Potion, double> discard;
        double leave = -1, other = -1;
        bool otherFlat = true;
        for (const auto &a : rewardModel.legalActions(0)) {
            const auto &c = rewardModel.candidate(0, a.id);
            if (c.semantic->effect == OocSemanticEffect::DISCARD_POTION)
                discard[rewardRoot.potions[c.primitive.getIdx1()]] = a.prior;
            else if (c.semantic->effect == OocSemanticEffect::LEAVE_REWARDS) leave = a.prior;
            else { otherFlat &= other < 0 || std::abs(other - a.prior) < 1e-12; other = a.prior; }
        }
        require(discard.size() == 3 && leave > 0 && otherFlat, "potion keep prior fixture");
        const double ratio = discard.at(Potion::HEART_OF_IRON) / leave;
        if (!keepPrior)
            require(std::abs(ratio - 1) < 1e-12 && std::abs(discard.at(Potion::BLOOD_POTION) - leave) < 1e-12,
                "without the potion keep prior the discard root stays uniform");
        else
            require(std::abs(ratio - std::exp((47.0 - 666.0) / 100.0)) < 1e-9
                && discard.at(Potion::BLOOD_POTION) < discard.at(Potion::FRUIT_JUICE)
                && discard.at(Potion::FRUIT_JUICE) < discard.at(Potion::HEART_OF_IRON)
                && (other < 0 || std::abs(other - leave) < 1e-12),
                "potion keep prior ranks discards by keep value below leave");
    }
    {
        OocSemanticAction first{OocSemanticEffect::BOTTLE_CARD, OocSemanticSource::SELECTOR,
            OocSelectorTarget{CardSelectScreenType::BOTTLE, 1, 0, OocCardTarget{CardId::DEFEND_RED, 0, false, -1, 0}}};
        auto second = first;
        std::get<OocCardTarget>(std::get<OocSelectorTarget>(second.target).card).occurrence = 1;
        const auto probe = makeRewardRoot();
        require(mctsChoiceKey(first, probe, false) != mctsChoiceKey(second, probe, false)
            && mctsChoiceKey(first, probe, true) == mctsChoiceKey(second, probe, true),
            "tree rules make copies of one card a single bottle choice");
    }
    // A reward screen holding only a key is left by the rule step unless keys
    // are collected; then the key stays for the chain's free-reward step.
    for (const bool keys : {false, true}) {
        auto keyRoot = makeRewardRoot();
        keyRoot.info.rewardsContainer.clear();
        keyRoot.info.rewardsContainer.emeraldKey = true;
        const bool savedKeys = g_collectKeys;
        g_collectKeys = keys;
        const bool stepped = oocTreeRuleStep(keyRoot);
        g_collectKeys = savedKeys;
        require(stepped && (!keys || keyRoot.greenKey),
            "tree rules collect a required key, or leave it when keys are off");
    }
    liveOptions = optionsBeforeGoldRoots;

    // Wheel has one legal primitive, but its existing fallback calls stepRandom:
    // choosing from a singleton still advances ScumSearchAgent2::rng.
    auto wheel=detachedCopy(sole);
    wheel.screenState=ScreenState::EVENT_SCREEN; wheel.curEvent=Event::WHEEL_OF_CHANGE;
    for (unsigned wheelSeed=0;wheelSeed<128;++wheelSeed) {
        wheel.miscRng=Random(wheelSeed);
        auto probe=wheel.miscRng;
        if (probe.random(5)==0) break; // gold, then the normal map callback
    }
    auto wheelRoll=wheel.miscRng;
    require(wheelRoll.random(5)==0,"wheel fixture deterministic gold outcome");
    PathHistory wheelPath; wheelPath.update(wheel);
    const auto wheelCandidates=v4CandidateActions(wheel);
    require(wheelCandidates.size()==1,"sole wheel candidate fixture");
    const auto savedEarlyStop=liveConfig.allowUnqualifiedRootStop;
    liveConfig.allowUnqualifiedRootStop=false;
    OocGameContextModel wheelModel(wheel,wheelPath,liveSampler,liveOptions);
    const auto wheelAction=wheelModel.soleLegalAction(0);
    const auto wheelBypass=searchWithSoleRootShortcut(wheelModel,liveConfig,wheelAction,128);
    require(wheelAction && wheelBypass.selectedAction==wheelAction
        && wheelBypass.metrics.trivialRootBypasses==1
        && wheelBypass.metrics.simulations==0 && wheelBypass.metrics.simulationAttempts==0
        && wheelBypass.metrics.transitionSamples==0 && wheelBypass.metrics.leafEvaluations==0
        && wheelModel.combatSamples()==0,
        "sole wheel semantic action bypasses unsupported hypothetical continuation");
    const auto wheelSearch=OocMctsPlanner(liveConfig).search(wheelModel,0,128);
    require(!wheelModel.searchGuaranteedNonAborting() && wheelSearch.aborted
        && wheelSearch.metrics.simulationAttempts>0,
        "old sole wheel search reaches unsupported combat and aborts");
    auto wheelPrimitive=detachedCopy(wheel), wheelOracle=detachedCopy(wheel);
    wheelCandidates.front().execute(wheelPrimitive);
    ScumSearchAgent2 wheelAgent, wheelOracleAgent;
    wheelAgent.rng.seed(20260914); wheelOracleAgent.rng=wheelAgent.rng;
    const auto agentBefore=wheelAgent.rng;
    runFullRunOocPolicyStep(wheelOracle,wheelOracleAgent,false,true);
    require(wheelOracleAgent.rng!=agentBefore
        && test::oocStateFingerprint(wheelOracle)==test::oocStateFingerprint(wheelPrimitive),
        "same sole wheel primitive hides a fallback agent RNG draw");
    const auto wheelBefore=test::oocStateFingerprint(wheel);
    LiveOocMctsMetrics wheelMetrics;
    require(oocMctsPolicyStep(wheel,wheelPath,42,7,wheelMetrics)
        && wheelMetrics.search.trivialRootBypasses==1 && wheelMetrics.supportAborts==0
        && wheelMetrics.fallback==0 && wheelMetrics.owned==1
        && wheelMetrics.search.simulations==0 && wheelMetrics.search.simulationAttempts==0
        && wheelMetrics.search.transitionSamples==0 && wheelMetrics.search.leafEvaluations==0
        && wheelMetrics.combatSamples==0 && wheelAgent.rng==agentBefore
        && test::oocStateFingerprint(wheel)==test::oocStateFingerprint(wheelPrimitive)
        && test::oocStateFingerprint(wheel)!=wheelBefore,
        "sole wheel root executes its exact action without hypothetical fallback");
    liveConfig.allowUnqualifiedRootStop=savedEarlyStop;
    struct QualifiedSoleRoot final : OocGenerativeModel {
        bool searchGuaranteedNonAborting() const override { return true; }
        std::optional<double> terminalValue(OocStateId) const override { return {}; }
        std::vector<OocPlannerAction> legalActions(OocStateId) const override { return {{7,1}}; }
        OocStateId sampleSuccessor(OocStateId,OocActionId,std::mt19937_64 &) override { ++draws; return 1; }
        double leafValue(OocStateId) const override { return .5; }
        unsigned draws=0;
    } qualifiedSole;
    const auto qualifiedBypass=searchWithSoleRootShortcut(qualifiedSole,liveConfig,7,128);
    require(qualifiedSole.searchGuaranteedNonAborting() && qualifiedBypass.selectedAction==7
        && qualifiedBypass.metrics.trivialRootBypasses==1 && qualifiedBypass.metrics.simulations==0
        && qualifiedBypass.metrics.simulationAttempts==0 && qualifiedSole.draws==0,
        "explicitly non-aborting sole model remains eligible for zero-simulation bypass");
    auto fallbackLive=detachedCopy(live), fallbackOracle=detachedCopy(live);
    ScumSearchAgent2 fallbackLiveAgent,fallbackOracleAgent;
    runFullRunOocPolicyStep(fallbackLive,fallbackLiveAgent,false,true);
    runFullRunOocPolicyStep(fallbackOracle,fallbackOracleAgent,false,true);
    require(test::oocStateFingerprint(fallbackLive)==test::oocStateFingerprint(fallbackOracle),
        "unsupported combat root uses unchanged V4 fallback primitive");
    auto lethal=std::make_shared<ImaginedDeath>();
    std::uint64_t firstSamples=0, repeatedSamples=0;
    const auto first=selectOocMctsAction(live,livePath,42,7,128,lethal,firstSamples);
    const auto second=selectOocMctsAction(live,livePath,42,7,128,lethal,repeatedSamples);
    require(test::oocStateFingerprint(live)==before
        && livePath.roomVisits==beforePath.roomVisits && livePath.lastNodeKey==beforePath.lastNodeKey,
        "live search isolates whole GameContext/map/RNG/PathHistory");
    require(first.selectedAction && first.selectedAction==second.selectedAction
        && firstSamples>0 && firstSamples==repeatedSamples
        && first.rootActions.size()==second.rootActions.size(), "deterministic live selection/samples");
    for (std::size_t i=0;i<first.rootActions.size();++i) {
        const auto &a=first.rootActions[i], &b=second.rootActions[i];
        require(a.id==b.id && a.prior==b.prior && a.visits==b.visits && a.q==b.q,
            "deterministic live root statistics");
    }
    require(oocMctsSearchSeed(42,7)==oocMctsSearchSeed(42,7)
        && oocMctsSearchSeed(42,7)!=oocMctsSearchSeed(42,8), "stable indexed search RNG");
    auto liveExpected=detachedCopy(live);
    const auto liveCandidates=v4CandidateActions(liveExpected);
    const auto selected=std::find_if(liveCandidates.begin(),liveCandidates.end(),
        [&](auto a) { return a.bits==*first.selectedAction; });
    require(selected!=liveCandidates.end(), "selected live candidate exists");
    selected->execute(liveExpected);
    liveEnabled=true; liveSimulations=128; liveSampler=lethal;
    LiveOocMctsMetrics liveMetrics;
    require(oocMctsPolicyStep(live,livePath,42,7,liveMetrics)
        && test::oocStateFingerprint(live)==test::oocStateFingerprint(liveExpected),
        "live execution exactly one primitive, no imagined successor transfer");
    require(live.screenState==ScreenState::BATTLE && live.outcome==GameOutcome::UNDECIDED
        && liveMetrics.combatSamples>0 && liveMetrics.owned==1
        && liveMetrics.decisions==1 && liveMetrics.fallback==0
        && liveMetrics.search.simulations>0
        && liveMetrics.search.simulations+liveMetrics.search.savedSimulations==128,
        "real combat remains pending despite imagined death and visit-lock stopping");
    // Real battle entry dispatches ordinary BattleContext initialization.
    BattleContext pending; pending.init(live);
    require(pending.outcome==Outcome::UNDECIDED && pending.player.curHp==live.curHp,
        "ordinary real battle initializes after selected action");
    auto uncovered=GameContext(CharacterClass::IRONCLAD,42,0);
    uncovered.regainControlAction=[](GameContext &g) { g.screenState=ScreenState::MAP_SCREEN; };
    uncovered.openCardSelectScreen(CardSelectScreenType::REMOVE,1);
    uncovered.info.toSelectCount=0; // Deliberately incomplete semantic enumeration.
    const auto uncoveredBefore=test::oocStateFingerprint(uncovered);
    auto fallbackExpected=detachedCopy(uncovered);
    LiveOocMctsMetrics fallbackMetrics;
    require(!oocMctsPolicyStep(uncovered,livePath,42,8,fallbackMetrics)
        && fallbackMetrics.fallback==1 && fallbackMetrics.owned==0
        && fallbackMetrics.search.simulations==0
        && test::oocStateFingerprint(uncovered)==uncoveredBefore, "unsupported live root falls back unchanged");
    ScumSearchAgent2 fallbackAgent, expectedAgent;
    runFullRunOocPolicyStep(uncovered,fallbackAgent,false,true);
    runFullRunOocPolicyStep(fallbackExpected,expectedAgent,false,true);
    require(test::oocStateFingerprint(uncovered)==test::oocStateFingerprint(fallbackExpected),
        "unsupported root uses identical existing policy chain");
    auto multipleGold=detachedCopy(reward);
    multipleGold.info.rewardsContainer.goldRewardCount=2;
    multipleGold.info.rewardsContainer.gold[0]=12;
    multipleGold.info.rewardsContainer.gold[1]=13;
    OocGameContextModel duplicateRoot(multipleGold,livePath,lethal);
    require(!duplicateRoot.isLeafBoundary(0), "multiple-gold normalization must retain reward continuation");
    const auto duplicateActions=duplicateRoot.legalActions(0);
    for (const auto action : duplicateActions) {
        const auto &candidate=duplicateRoot.candidate(0,action.id);
        require(!candidate.semantic || candidate.semantic->effect!=OocSemanticEffect::TAKE_GOLD,
            "multiple-gold normalization left TAKE_GOLD in the candidate set");
    }
    auto goldOnlyFixture=multipleGold;
    goldOnlyFixture.info.rewardsContainer.cardRewardCount=0;
    goldOnlyFixture.info.rewardsContainer.relicCount=0;
    goldOnlyFixture.info.rewardsContainer.potionCount=0;
    OocGameContextModel goldOnlyRoot(goldOnlyFixture,livePath,lethal);
    const auto goldOnlyActions=goldOnlyRoot.legalActions(0);
    require(goldOnlyActions.size()==1 && goldOnlyActions.front().prior==1,
        "gold-only normalization must expose one leave-rewards action");
    const auto &goldOnlyCandidate=goldOnlyRoot.candidate(0,goldOnlyActions.front().id);
    require(goldOnlyCandidate.semantic
            && goldOnlyCandidate.semantic->effect==OocSemanticEffect::LEAVE_REWARDS,
        "gold-only normalization exposed a non-leave reward action");
    std::cout<<"PASS live OOC MCTS OFF/isolation/execution/real-combat/fallback/determinism\n";
    // Opt-in captured-model microbenchmark. Runs only detached search states;
    // this is not a gameplay cohort or a decision-quality experiment.
    if (const char *modelPath=std::getenv("STS_OOC_MCTS_MICROBENCH_MODEL")) {
        auto native=std::make_shared<NativeCombatTransitionSampler>(modelPath);
        struct ReferenceSampler final : CombatTransitionSampler {
            std::shared_ptr<const NativeCombatTransitionSampler> native;
            mutable std::uint64_t encoderCalls=0;
            explicit ReferenceSampler(std::shared_ptr<const NativeCombatTransitionSampler> n):native(std::move(n)) {}
            CombatRuntimeSupport support(const GameContext &g,const CombatPredictorInputV1 &p) const override {
                return native->support(g,p);
            }
            CombatRuntimeSample sample(const GameContext &g,const CombatPredictorInputV1 &p,std::mt19937_64 &r) const override {
                auto result=native->sample(g,p,r);
                if (result.outcome!=CombatRuntimeSample::Outcome::UNSUPPORTED)
                    encoderCalls+=result.outcome==CombatRuntimeSample::Outcome::VICTORY ? 4 : 1;
                return result;
            }
        };
        auto reference=std::make_shared<ReferenceSampler>(native);
        GameContext fixed(CharacterClass::IRONCLAD,42,0);
        fixed.screenState=ScreenState::MAP_SCREEN; fixed.curEvent=Event::INVALID;
        for (auto &node : fixed.map->nodes[0]) node.room=Room::MONSTER;
        // Isolate one searched combat edge from native reward/projection work.
        fixed.regainControlAction=[](GameContext &g) { g.screenState=ScreenState::MAP_SCREEN; };
        PathHistory fixedPath;fixedPath.update(fixed);
        OocAdapterOptions opts; opts.checkpointLeaves=true; opts.stopAtMapCheckpoint=true;
        OocGameContextModel before(fixed,fixedPath,reference,opts),after(fixed,fixedPath,native,opts);
        auto cfg=OocMctsConfig{}; cfg.seed=20260914;
        const auto start=std::chrono::steady_clock::now();
        const auto oldResult=OocMctsPlanner(cfg).search(before,0,512);
        const double oldSeconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();
        const auto next=std::chrono::steady_clock::now();
        const auto newResult=OocMctsPlanner(cfg).search(after,0,512);
        const double newSeconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-next).count();
        require(!oldResult.aborted && !newResult.aborted,"fixed native microbenchmark support");
        require(oldResult.selectedAction==newResult.selectedAction && before.storedStates()==after.storedStates()
            && before.combatSamples()==after.combatSamples(),"prepared search action/state/sample parity");
        const auto &a=oldResult.metrics,&b=newResult.metrics;
        require(a.simulations==b.simulations && a.simulationAttempts==b.simulationAttempts
            && a.decisionNodes==b.decisionNodes && a.chanceNodes==b.chanceNodes
            && a.outcomeParticles==b.outcomeParticles && a.transitionSamples==b.transitionSamples
            && a.leafEvaluations==b.leafEvaluations && a.particleRevisits==b.particleRevisits
            && a.deterministicRevisits==b.deterministicRevisits && a.depthSum==b.depthSum
            && a.maxDepthReached==b.maxDepthReached,"prepared complete tree metrics parity");
        for (std::size_t i=0;i<oldResult.rootActions.size();++i) {
            const auto &x=oldResult.rootActions[i],&y=newResult.rootActions.at(i);
            require(x.id==y.id && x.prior==y.prior && x.visits==y.visits && x.q==y.q,
                "prepared root IDs/order/priors/visits/Q parity");
        }
        for (std::size_t i=0;i<before.storedStates();++i)
            require(test::oocStateFingerprint(before.state(i))==test::oocStateFingerprint(after.state(i))
                && before.pathHistory(i).roomVisits==after.pathHistory(i).roomVisits
                && before.pathHistory(i).lastNodeKey==after.pathHistory(i).lastNodeKey,
                "every prepared search snapshot and PathHistory exact");
        nlohmann::json exact={{"selectedAction",*newResult.selectedAction},
            {"simulations",b.simulations},{"simulationAttempts",b.simulationAttempts},
            {"decisionNodes",b.decisionNodes},{"chanceNodes",b.chanceNodes},
            {"outcomeParticles",b.outcomeParticles},{"transitionSamples",b.transitionSamples},
            {"leafEvaluations",b.leafEvaluations},{"particleRevisits",b.particleRevisits},
            {"deterministicRevisits",b.deterministicRevisits},{"depthSum",b.depthSum},
            {"maxDepthReached",b.maxDepthReached}};
        for (auto action:newResult.rootActions)
            exact["rootActions"].push_back({action.id,action.prior,action.visits,action.q});
        for (std::size_t i=0;i<after.storedStates();++i)
            exact["states"].push_back({test::oocStateFingerprint(after.state(i)),
                after.pathHistory(i).roomVisits,after.pathHistory(i).lastNodeKey});
        std::cout<<"MICROBENCH_PARITY "<<exact.dump()<<'\n';
        std::cout<<"MICROBENCH "<<nlohmann::json{{"simulations",512},{"referenceSeconds",oldSeconds},
            {"preparedSeconds",newSeconds},{"referenceSimulationsPerSecond",512/oldSeconds},
            {"preparedSimulationsPerSecond",512/newSeconds},{"combatSamples",after.combatSamples()},
            {"referenceCombatSamplesPerSecond",before.combatSamples()/oldSeconds},
            {"preparedCombatSamplesPerSecond",after.combatSamples()/newSeconds},
            {"referenceEncoderCalls",reference->encoderCalls},
            {"preparedEncoderCalls",4*after.continuationMetrics().preparedCombats},
            {"uniqueCombatEdges",after.continuationMetrics().preparedCombats},
            {"generatedStates",after.storedStates()},{"decisionNodes",b.decisionNodes},
            {"metadataBuilds",after.continuationMetrics().metadataBuilds},
            {"priorBuilds",after.continuationMetrics().priorBuilds},{"parity",true}}.dump()<<'\n';
    }
    // Opt-in mechanism gate for experimental leaf evaluators. This compares
    // identical detached states and identical planner seeds before gameplay.
    if (const char *modelPath=std::getenv("STS_OOC_MCTS_BOSS_MECHANISM_MODEL")) {
        auto sampler=std::make_shared<NativeCombatTransitionSampler>(modelPath);
        OocAdapterOptions nativeOptions{true};
        OocAdapterOptions bossOptions{true}; bossOptions.bossLeaf=true;
        nlohmann::json mechanism;
        bool everyLeafDiffers=true;
        for (int hp : {20,40,60}) {
            auto probe=detachedCopy(gc); probe.curHp=hp; probe.maxHp=80;
            OocGameContextModel nativeLeaf(probe,path,sampler,nativeOptions);
            OocGameContextModel bossLeaf(probe,path,sampler,bossOptions);
            std::mt19937_64 nativeRng(20260915),bossRng(20260915);
            const double nativeValue=nativeLeaf.evaluateLeaf(0,nativeRng);
            const double bossValue=bossLeaf.evaluateLeaf(0,bossRng);
            everyLeafDiffers=everyLeafDiffers && std::abs(nativeValue-bossValue)>1e-6;
            mechanism["leaves"].push_back({{"hp",hp},{"native",nativeValue},{"boss",bossValue},
                {"bossExpectationCalls",10}});
        }
        require(everyLeafDiffers,"real boss mechanism leaf values must differ from native v_win");
        auto root=detachedCopy(gc);
        PathHistory rootPath; rootPath.update(root);
        OocGameContextModel nativeSearch(root,rootPath,sampler,nativeOptions);
        OocGameContextModel bossSearch(root,rootPath,sampler,bossOptions);
        OocMctsConfig cfg; cfg.seed=20260915;
        const auto nativeResult=OocMctsPlanner(cfg).search(nativeSearch,0,64);
        const auto bossResult=OocMctsPlanner(cfg).search(bossSearch,0,64);
        require(!nativeResult.aborted && !bossResult.aborted
            && nativeResult.rootActions.size()==bossResult.rootActions.size(),
            "real boss mechanism searches must complete on identical roots");
        bool qChanged=false;
        for (std::size_t i=0;i<nativeResult.rootActions.size();++i) {
            const auto &nativeAction=nativeResult.rootActions[i];
            const auto &bossAction=bossResult.rootActions[i];
            require(nativeAction.id==bossAction.id,"real boss mechanism root action identity");
            qChanged=qChanged || std::abs(nativeAction.q-bossAction.q)>1e-6;
            mechanism["rootActions"].push_back({{"id",nativeAction.id},
                {"nativeQ",nativeAction.q},{"bossQ",bossAction.q},
                {"nativeVisits",nativeAction.visits},{"bossVisits",bossAction.visits}});
        }
        require(qChanged,"real boss mechanism must change at least one MCTS root Q");
        mechanism["nativeSelectedAction"]=*nativeResult.selectedAction;
        mechanism["bossSelectedAction"]=*bossResult.selectedAction;
        mechanism["simulations"]=64;
        mechanism["leafValuesDiffer"]=everyLeafDiffers;
        mechanism["rootQChanged"]=qChanged;
        std::cout<<"BOSS_LEAF_MECHANISM "<<mechanism.dump()<<'\n';
    }
    std::cout<<"PASS OOC MCTS adapter (offline native integration only)\n";
}
int oocSelectiveSilverHorizonSelfTest() {
    try {
        const auto require = [](bool ok, const char *why) {
            if (!ok) throw std::runtime_error(std::string("selective Silver horizon selftest: ") + why);
        };
        struct Sampler final : CombatTransitionSampler {
            mutable unsigned calls = 0;
            bool dieOnSecond = false;
            CombatRuntimeSupport support(const GameContext &, const CombatPredictorInputV1 &) const override {
                return {true, "supported"};
            }
            CombatRuntimeSample sample(const GameContext &gc, const CombatPredictorInputV1 &,
                    std::mt19937_64 &) const override {
                ++calls;
                auto post = captureCombatTransitionState(gc);
                --post.curHp;
                return {dieOnSecond && calls == 2 ? CombatRuntimeSample::Outcome::DEATH
                    : CombatRuntimeSample::Outcome::VICTORY, std::move(post)};
            }
        };
        // BATTLE is the audit's boundary after executing the retained MAP
        // candidate; MAP also checks the ordinary continuation entry point.
        for (const auto initialScreen : {sts::ScreenState::BATTLE, sts::ScreenState::MAP_SCREEN}) {
            for (int terminalCase : {0, 1, 2}) {
                auto sampler = std::make_shared<Sampler>();
                sampler->dieOnSecond = terminalCase == 1;
                GameContext gc{};
                gc.cc = sts::CharacterClass::IRONCLAD; gc.ascension = 20;
                gc.act = 1; gc.floorNum = 3; gc.curHp = 70; gc.maxHp = 80;
                gc.screenState = initialScreen;
                gc.curRoom = sts::Room::MONSTER; gc.info.encounter = sts::MonsterEncounter::CULTIST;
                gc.curMapNodeX = 0; gc.curMapNodeY = -1;
                unsigned callbacks = 0, pendingSteps = 0, anchors = 0;
                gc.regainControlAction = [&](GameContext &state) {
                    ++callbacks; ++state.floorNum;
                    if (terminalCase == 2 && sampler->calls == 2) {
                        state.act = 4; state.outcome = sts::GameOutcome::PLAYER_VICTORY;
                    }
                    // A chained fight may leave a pending native decision
                    // after the requested third combat, before any MAP.
                    state.screenState = sampler->calls == 3
                        ? sts::ScreenState::EVENT_SCREEN : sts::ScreenState::MAP_SCREEN;
                    if (sampler->calls == 3) state.curEvent = sts::Event::COLOSSEUM;
                };
                OocMctsDependencies dependencies;
                dependencies.policyAvailable = [] { return true; };
                dependencies.policyLogits = [](const GameContext &, const PathHistory &,
                        const std::vector<GameAction> &actions) { return std::vector<double>(actions.size(), 0); };
                dependencies.leafValue = [&](const GameContext &state, const PathHistory &) {
                    ++anchors;
                    require(state.screenState == sts::ScreenState::MAP_SCREEN && sampler->calls == 4,
                        "anchor runs only at the first MAP after the mandatory fourth fight");
                    return state.curHp / 100.0;
                };
                dependencies.continuationStep = [&](GameContext &state, PathHistory &, std::mt19937_64 &) {
                    require(state.screenState == sts::ScreenState::MAP_SCREEN
                        || state.screenState == sts::ScreenState::EVENT_SCREEN, "expected synthetic pending screen");
                    if (state.screenState == sts::ScreenState::EVENT_SCREEN) {
                        require(sampler->calls == 3, "pending event follows the third combat");
                        ++pendingSteps;
                    }
                    state.screenState = sts::ScreenState::BATTLE;
                };
                OocAdapterOptions options;
                options.checkpointLeaves = true; options.leafCombats = 3;
                const PathHistory path;
                OocGameContextModel model(gc, path, sampler, options, dependencies);
                const auto before = sts::test::oocStateFingerprint(model.state(0));
                const auto *previousPath = t_curPath;
                std::mt19937_64 rng(17);
                const auto result = model.evaluateLeafWithOutcome(0, rng);
                const unsigned expectedCombats = terminalCase ? 2 : 4;
                require(sampler->calls == expectedCombats && model.combatSamples() == expectedCombats
                    && model.continuationMetrics().imaginedCombats == expectedCombats,
                    "all fights, including an entered BATTLE and mandatory chain, are counted");
                require(sts::test::oocStateFingerprint(model.state(0)) == before
                    && sts::test::oocStateFingerprint(gc) == before && t_curPath == previousPath
                    && rng == std::mt19937_64(17), "synthetic rollout preserves source, path binding and unused RNG");
                if (!terminalCase) {
                    require(!result.terminal && result.value == .66 && result.endpoint
                        && result.endpoint->hp == 66 && result.endpoint->floor == 7
                        && callbacks == 4 && pendingSteps == 1 && anchors == 1,
                        "third combat -> pending event -> fourth combat -> MAP completes before scoring");
                } else {
                    require(result.terminal && result.value == (terminalCase == 1 ? 0.0 : 1.0)
                        && callbacks == (terminalCase == 1 ? 1u : 2u) && pendingSteps == 0 && anchors == 0,
                        "death or victory before three combats returns its exact terminal value");
                }
            }
        }
        std::cout << "PASS selective Silver checkpoint horizon (synthetic only)\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
}
#endif
