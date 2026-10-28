// fightreplay (AIVAT replay baseline, 2026-10-26): re-plays recorded real fights of whole runs under this
// process's real-combat configuration, so a paired A/B can subtract each fight's luck without bias
// (fight luck = V(actual post) - mean V(replay posts); /mnt/project-files/aivat-variance/README.md).
//
// Input: heartoutcomegen combat_transition_row_v2 rows (STS_HEART_OUTCOME_CTM_ROWS=1), each with a
// "replayContext" object {"keys": [ruby, emerald, sapphire], "mapX", "mapY", "secondBoss"} taken from the
// same run's trajectory (tools/fight_replay_rows.py): the rows themselves do not carry the keys, map node
// or second Act-3 boss, which the Silver leaf reads. Event fights (room class OTHER) are not supported.
//
// The fight is rebuilt on a fresh GameContext of the recorded run seed: act, floor, room, last room,
// encounter, keys, map node (the act map from the seed, its burning elite only when the row says so), the
// second boss, and the recorded pre-combat persistent state. Replicate 0 keeps the run seed and so must
// reproduce the recorded fight exactly (BattleContext::init seeds four combat streams and the Silver planner
// from seed + floor and carries misc and potion): its outcome and post state are compared with the row, and
// any difference fails the mode. Replicates 1..R redraw the seed and the carried misc/potion streams
// (counters kept), as the imagined-fight sampler does, so they are independent draws of the same fight. The
// redraw depends on (SEED_BASE, run seed, fight index, replicate) only, so both arms of a paired seed share it
// (common random numbers across arms; each arm's replays stay independent of its own recorded fight).
// Budgets come from the process environment exactly as in runFullRunOOC (fightSims at base 10000, learned stop,
// Act-4 strong): run it with the campaign's frozen environment.
#include "one_combat/driver_shared.h"
#include "one_combat/combat_predictor_input.h"
#include "one_combat/combat_transition.h"
#include "one_combat/run_driver.h"

#include <ctime>
#include <fstream>
#include <iostream>
#include <random>
#include <stdexcept>

namespace {

using J = nlohmann::json;

std::uint64_t mix64(std::uint64_t x) {
    x += 0x9e3779b97f4a7c15ULL;
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
    x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
    return x ^ (x >> 31);
}

std::uint64_t threadCpuNanos() {
    timespec ts{};
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts);
    return static_cast<std::uint64_t>(ts.tv_sec) * 1000000000ULL + static_cast<std::uint64_t>(ts.tv_nsec);
}

void need(bool ok, const std::string &message) {
    if (!ok) throw std::runtime_error("fightreplay: " + message);
}

GameContext replayContext(const J &row) {
    const auto &g = row.at("predictorInput").at("globals");
    const auto &ctx = row.at("replayContext");
    const auto seed = row.at("sourceSeed").get<std::uint64_t>();
    const int asc = g.at("ascension").get<int>();
    const int act = row.at("act").get<int>();
    need(g.at("characterClass").get<int>() == static_cast<int>(CharacterClass::IRONCLAD), "Ironclad only");
    need(row.at("roomClass").get<std::string>() != "OTHER", "event fights are not supported");
    GameContext gc(CharacterClass::IRONCLAD, seed, asc);
    const auto keys = ctx.at("keys").get<std::vector<int>>();
    need(keys.size() == 3, "keys must be [ruby, emerald, sapphire]");
    gc.redKey = keys[0] != 0;
    gc.greenKey = keys[1] != 0;
    gc.blueKey = keys[2] != 0;
    gc.act = act;
    gc.floorNum = row.at("floor").get<int>();
    gc.curRoom = static_cast<Room>(g.at("roomClass").get<int>());
    gc.lastRoom = static_cast<Room>(g.at("lastRoom").get<int>());
    gc.info.encounter = static_cast<MonsterEncounter>(row.at("encounter").get<int>());
    need(static_cast<int>(gc.info.encounter) == g.at("encounter").get<int>(), "encounter mismatch");
    // -1: the run has no recorded second Act-3 boss fight here (any boss but this one).
    const int secondBoss = ctx.at("secondBoss").get<int>();
    gc.secondBoss = secondBoss < 0 ? MonsterEncounter::INVALID : static_cast<MonsterEncounter>(secondBoss);
    gc.screenState = ScreenState::BATTLE;
    gc.outcome = GameOutcome::UNDECIDED;
    gc.skipBattles = false;
    *gc.map = act == 4 ? Map::act4Map() : Map::fromSeed(seed, asc, act, true);
    gc.curMapNodeX = ctx.at("mapX").get<int>();
    gc.curMapNodeY = ctx.at("mapY").get<int>();
    const bool burning = g.at("isBurningElite").get<bool>();
    const bool onBurning = gc.map->burningEliteX == gc.curMapNodeX && gc.map->burningEliteY == gc.curMapNodeY;
    need(!burning || onBurning, "recorded burning elite is not the seed map's burning elite");
    if (!burning) {
        gc.map->burningEliteX = -1;
        gc.map->burningEliteY = -1;
        gc.map->burningEliteBuff = -1;
    }
    one_combat::applyCombatTransitionState(
        gc, one_combat::combatTransitionStateFromJson(row.at("transition").at("pre")));
    const auto reproduced = one_combat::combatPredictorInputJson(one_combat::captureCombatPredictorInput(
        gc, gc.info.encounter, g.at("potionKeepValue").get<double>()));
    need(reproduced == row.at("predictorInput"), "rebuilt state does not reproduce the recorded predictor input");
    need(one_combat::combatTransitionStateJson(one_combat::captureCombatTransitionState(gc))
             == row.at("transition").at("pre"), "rebuilt state does not reproduce the recorded pre state");
    return gc;
}

// Replicate r > 0: a fresh battle seed (combat streams and Silver planner) and fresh carried streams.
std::uint64_t redraw(GameContext &gc, std::uint64_t seedBase, std::uint64_t sourceSeed, int fightIdx, int r) {
    std::mt19937_64 rng(mix64(seedBase ^ mix64(sourceSeed ^ mix64((static_cast<std::uint64_t>(fightIdx) << 16)
                                                                   ^ static_cast<std::uint64_t>(r)))));
    gc.seed = rng();
    for (auto stream : {&gc.aiRng, &gc.cardRandomRng, &gc.miscRng, &gc.monsterHpRng, &gc.potionRng,
                        &gc.shuffleRng}) {
        const auto counter = stream->counter;
        *stream = Random(rng());
        stream->counter = counter;
    }
    return gc.seed;
}

struct Played {
    Outcome outcome = Outcome::UNDECIDED;
    J post;
    int turns = 0;
    double cpuSeconds = 0;
    bool valid = false;
};

Played play(GameContext gc) {
    Played p;
    search::ScumSearchAgent2 agent;
    agent.simulationCountBase = fightSims(gc, 10000);
    agent.rng = std::default_random_engine(gc.seed);   // out-of-combat only; combat never draws from it
    BattleContext bc{};
    trainingRunStart();
    const auto t0 = threadCpuNanos();
    agent.playoutBattle(gc, bc);
    p.cpuSeconds = static_cast<double>(threadCpuNanos() - t0) / 1e9;
    int captures = 0;
    {
        one_combat::CombatTransitionRawObserverScope scope([&](const BattleContext &, GameContext &raw) {
            if (++captures == 1)
                p.post = one_combat::combatTransitionStateJson(one_combat::captureCombatTransitionState(raw));
        });
        gc.regainControlAction = [](GameContext &) {};   // no rewards: only the raw exit state is the label
        bc.exitBattle(gc);
    }
    p.outcome = bc.outcome;
    p.turns = bc.turn;
    p.valid = trainingRunValid(bc.outcome != Outcome::UNDECIDED) && captures == 1;
    return p;
}

}  // namespace

int fightReplay(int nRows, const std::string &rowsPath, const std::string &outPath, std::uint64_t seedBase,
                int replicates) {
    need(nRows >= 1 && replicates >= 0, "N_ROWS must be positive and REPLICATES non-negative");
    std::vector<J> rows;
    {
        std::ifstream in(rowsPath);
        need(bool(in), "cannot open " + rowsPath);
        for (std::string line; std::getline(in, line) && static_cast<int>(rows.size()) < nRows;)
            if (!line.empty()) rows.push_back(J::parse(line));
    }
    need(static_cast<int>(rows.size()) == nRows, "too few rows");
    need(!std::ifstream(outPath), "refusing to overwrite " + outPath);
    std::ofstream out(outPath);
    need(bool(out), "cannot write " + outPath);
    const int perRow = replicates + 1;
    const int jobs = nRows * perRow;
    int mismatches = 0, errors = 0;
    #pragma omp parallel for schedule(dynamic)
    for (int j = 0; j < jobs; ++j) {
        const auto &row = rows[j / perRow];
        const int r = j % perRow;
        J result = {{"sourceSeed", row.at("sourceSeed")}, {"fightIdx", row.at("fightIdx")}, {"act", row.at("act")},
                    {"floor", row.at("floor")}, {"roomClass", row.at("roomClass")},
                    {"encounter", row.at("encounter")}, {"replicate", r},
                    {"arm", row.value("replayContext", J::object()).value("arm", std::string())}};
        bool mismatch = false, error = false;
        try {
            GameContext gc = replayContext(row);
            result["battleSeed"] = r == 0 ? gc.seed
                : redraw(gc, seedBase, row.at("sourceSeed").get<std::uint64_t>(), row.at("fightIdx").get<int>(), r);
            const auto p = play(gc);
            result["valid"] = p.valid;
            result["combatOutcome"] = static_cast<int>(p.outcome);
            result["post"] = p.post;
            result["turns"] = p.turns;
            result["cpuSeconds"] = p.cpuSeconds;
            if (r == 0) {
                const auto &t = row.at("transition");
                mismatch = !p.valid || t.at("combatOutcome").get<int>() != static_cast<int>(p.outcome)
                    || t.at("post") != p.post;
                result["identity"] = !mismatch;
            }
        } catch (const std::exception &e) {
            error = true;
            result["error"] = e.what();
        }
        #pragma omp critical(fight_replay_write)
        {
            mismatches += mismatch;
            errors += error;
            out << result.dump() << '\n';
            out.flush();
        }
    }
    std::cout << "fightreplay rows=" << nRows << " replicates=" << replicates << " identity_mismatches=" << mismatches
              << " errors=" << errors << " -> " << outPath << '\n';
    return mismatches || errors ? 1 : 0;
}
