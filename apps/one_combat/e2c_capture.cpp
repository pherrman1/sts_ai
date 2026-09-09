#include "e2c_capture.h"

#include <algorithm>
#include <atomic>
#include <cctype>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <memory>
#include <sstream>
#include <unordered_map>
#include <unordered_set>
#include <vector>

#include "compact_tree.h"

extern bool g_collectKeys;

namespace one_combat {

using namespace sts;

namespace {

struct E2cFight {
    int index = -1, room = -1, encounter = -1;
    std::string raw, post, rawRelics, postRelics;
    bool rawSeen = false, postSeen = false;
    std::string screenTrace;
    std::string rewardRelics;
    int pendingCards = -1;
};

struct E2cRoomStats {
    int eligible = 0, raw = 0, post = 0, pairs = 0;
};

struct E2cCapture {
    std::uint64_t seed = 0;
    PathHistory *path = nullptr;
    std::vector<E2cFight> fights;
    E2cFight *current = nullptr;
    E2cRoomStats roomStats[3]{};
};

thread_local std::unique_ptr<E2cCapture> t_e2c;
thread_local std::string t_e2cRows;
std::atomic<long long> g_e2cCounts[3][6]{};
CompactTreeNet g_e2cRawNet;

int roomStatsIndex(int room) {
    return room == static_cast<int>(Room::MONSTER) ? 0
         : room == static_cast<int>(Room::ELITE) ? 1 : 2;
}

std::string e2cRoomName(int room) {
    switch (static_cast<Room>(room)) {
        case Room::MONSTER: return "MONSTER";
        case Room::ELITE: return "ELITE";
        case Room::BOSS: return "BOSS";
        default: return "OTHER";
    }
}

std::string e2cExplicitRelics(const GameContext &gc) {
    std::vector<int> has(kNumRelics, 0), data(kNumRelics, 0);
    for (const auto &ri : gc.relics.relics) {
        const int id = static_cast<int>(ri.id);
        if (id >= 0 && id < kNumRelics) {
            has[id] = 1;
            data[id] = ri.data;
        }
    }
    std::ostringstream out;
    for (int i = 0; i < kNumRelics; ++i) {
        if (i) out << ',';
        out << has[i];
    }
    for (int i = 0; i < kNumRelics; ++i) out << ',' << data[i];
    return out.str();
}

void e2cRawObserver(const BattleContext &bc, GameContext &gc) {
    if (t_e2c && t_e2c->current && bc.outcome == Outcome::PLAYER_VICTORY) {
        t_e2c->current->raw = richRow(gc, *t_e2c->path);
        t_e2c->current->rawRelics = e2cExplicitRelics(gc);
        t_e2c->current->rawSeen = true;
        auto &s = t_e2c->roomStats[roomStatsIndex(t_e2c->current->room)];
        ++s.eligible;
        ++s.raw;
    }
}

std::string e2cRunRows(const E2cCapture &cap, bool won, int finalFloor, int endHp) {
    std::ostringstream out;
    for (const auto &f : cap.fights) {
        if (!f.rawSeen && !f.postSeen) continue;
        const std::string meta = e2cRoomName(f.room) + ',' + std::to_string(f.encounter) + ',';
        if (f.rawSeen)
            out << cap.seed << ',' << f.index << ",RAW," << meta << f.raw << ',' << f.rawRelics
                << ',' << (won ? 1 : 0) << ',' << finalFloor << ',' << endHp << '\n';
        if (f.postSeen)
            out << cap.seed << ',' << f.index << ",POST," << meta << f.post << ',' << f.postRelics
                << ',' << (won ? 1 : 0) << ',' << finalFloor << ',' << endHp << '\n';
    }
    return out.str();
}

std::vector<std::string> splitCsvNames(const std::string &s) {
    std::vector<std::string> out;
    std::string cur;
    // std::getline removes '\n' but leaves the '\r' in a normal CRLF CSV.
    for (char c : s) {
        if (c == ',') {
            out.push_back(cur);
            cur.clear();
        } else if (c != '\r') {
            cur += c;
        }
    }
    if (!cur.empty()) out.push_back(cur);
    return out;
}

bool e2cObservableName(const std::string &n) {
    static const std::unordered_set<std::string> exact = {
        "ascension", "act", "floor", "curHp", "maxHp", "gold", "deckSize", "potionChance",
        "cardRarityFactor", "blueKey", "greenKey", "redKey", "potionCount", "potionCapacity", "bossId",
        "pvShop", "pvRest", "pvEvent", "pvElite", "pvMonster", "pvTreasure", "bottledAtkId",
        "bottledSkillId", "bottledPowId", "curMapX", "curMapY", "room_type", "encounter_id", "hpFrac"};
    if (exact.count(n)) return true;
    const auto digits = [](const std::string &v, const char *prefix) {
        const size_t p = std::strlen(prefix);
        if (v.rfind(prefix, 0) != 0 || v.size() == p) return false;
        return std::all_of(v.begin() + p, v.end(),
                           [](unsigned char c) { return std::isdigit(c); });
    };
    return digits(n, "d") || digits(n, "u") || digits(n, "pot")
        || n.rfind("fmD", 0) == 0 || n.rfind("fmC", 0) == 0
        || n.rfind("relic_has_", 0) == 0 || n.rfind("relic_data_", 0) == 0;
}

const std::vector<std::string> &e2cRawCanonicalNames() {
    static const std::vector<std::string> names = [] {
        const std::unordered_set<std::string> meta = {
            "seed", "fight_index", "boundary", "room_type", "encounter_id"};
        const std::unordered_set<std::string> hidden = {
            "nextEliteId", "nextFight0", "nextFight1", "nextFight2",
            "remElites", "remFights", "monOffset", "eliteOffset"};
        std::vector<std::string> out;
        for (const std::string &n : splitCsvNames(e2cHeader())) {
            if (n == "won" || n == "finalFloor" || n == "endHp" || hidden.count(n)) continue;
            if (meta.count(n) && n != "room_type" && n != "encounter_id") continue;
            if (!e2cObservableName(n)) continue;
            out.push_back(n);
        }
        return out;
    }();
    return names;
}

const std::unordered_map<std::string, int> &e2cRawIdxMap() {
    static const std::unordered_map<std::string, int> map = [] {
        std::unordered_map<std::string, int> out;
        const auto &names = e2cRawCanonicalNames();
        for (int i = 0; i < static_cast<int>(names.size()); ++i) out.emplace(names[i], i);
        return out;
    }();
    return map;
}

std::vector<float> e2cRawCanonicalVec(const GameContext &gc, const PathHistory &path,
                                      Room room, MonsterEncounter encounter) {
    std::unordered_map<std::string, float> values;
    const auto rNames = splitCsvNames(richStateHeader());
    const auto rValues = splitCsvNames(richRow(gc, path));
    if (rNames.size() != rValues.size()) return {};
    for (size_t i = 0; i < rNames.size(); ++i)
        values.emplace(rNames[i], std::strtof(rValues[i].c_str(), nullptr));
    values["room_type"] = room == Room::MONSTER ? 0.f
        : room == Room::ELITE ? 1.f : room == Room::BOSS ? 2.f : -1.f;
    values["encounter_id"] = static_cast<float>(static_cast<int>(encounter));
    const auto relicValues = splitCsvNames(e2cExplicitRelics(gc));
    if (relicValues.size() != static_cast<size_t>(2 * kNumRelics)) return {};
    for (int i = 0; i < kNumRelics; ++i)
        values["relic_has_" + std::to_string(i)] = std::strtof(relicValues[i].c_str(), nullptr);
    for (int i = 0; i < kNumRelics; ++i)
        values["relic_data_" + std::to_string(i)] =
            std::strtof(relicValues[kNumRelics + i].c_str(), nullptr);
    std::vector<float> out;
    out.reserve(e2cRawCanonicalNames().size());
    for (const std::string &name : e2cRawCanonicalNames()) {
        const auto it = values.find(name);
        if (it == values.end()) return {};
        out.push_back(it->second);
    }
    return out;
}

bool e2cProjectTerminalRaw(const GameContext &battleEntry, const PathHistory &path,
                           Room room, MonsterEncounter encounter,
                           const BattleContext &terminal, std::vector<float> &out) {
    if (terminal.outcome != Outcome::PLAYER_VICTORY) return false;
    GameContext post = battleEntry;
    bool captured = false;
    auto previous = g_onBattleExitPersistent;
    g_onBattleExitPersistent = [&](const BattleContext &, GameContext &atRaw) {
        out = e2cRawCanonicalVec(atRaw, path, room, encounter);
        captured = !out.empty();
    };
    terminal.exitBattle(post);
    g_onBattleExitPersistent = previous;
    return captured;
}

} // namespace

void beginE2cRun(std::uint64_t seed, PathHistory &path) {
    t_e2c = std::make_unique<E2cCapture>();
    t_e2c->seed = seed;
    t_e2c->path = &path;
    t_e2cRows.clear();
}

bool e2cCaptureActive() {
    return static_cast<bool>(t_e2c);
}

void beginE2cFight(int fightIndex, const GameContext &gc, const BattleContext &bc) {
    if (!t_e2c) return;
    t_e2c->current = nullptr;
    if (gc.curRoom != Room::MONSTER && gc.curRoom != Room::ELITE && gc.curRoom != Room::BOSS) return;
    if (gc.curRoom == Room::BOSS && gc.act > 2) return;
    E2cFight f;
    f.room = static_cast<int>(gc.curRoom);
    f.encounter = static_cast<int>(bc.encounter);
    f.index = fightIndex;
    t_e2c->fights.push_back(std::move(f));
    t_e2c->current = &t_e2c->fights.back();
}

void exitBattleWithE2cRawCapture(const BattleContext &bc, GameContext &gc) {
    if (!t_e2c) {
        bc.exitBattle(gc);
        return;
    }
    g_onBattleExitPersistent = e2cRawObserver;
    bc.exitBattle(gc);
    g_onBattleExitPersistent = nullptr;
}

void captureE2cPost(GameContext &gc) {
    if (!t_e2c || !t_e2c->current || t_e2c->current->postSeen) return;
    auto &r = gc.info.rewardsContainer;
    t_e2c->current->screenTrace += "REWARDS(" + std::to_string(r.relicCount) + ","
        + std::to_string(r.cardRewardCount) + ");";
    if (t_e2c->current->rewardRelics.empty()) {
        for (int i = 0; i < r.relicCount; ++i) {
            if (i) t_e2c->current->rewardRelics += ";";
            t_e2c->current->rewardRelics += std::to_string(static_cast<int>(r.relics[i]));
        }
    }
    t_e2c->current->pendingCards = r.cardRewardCount;
    if (gc.screenState != ScreenState::REWARDS || r.goldRewardCount || r.relicCount
        || r.potionCount || (g_collectKeys && (r.emeraldKey || r.sapphireKey))
        || r.cardRewardCount == 0) return;
    t_e2c->current->post = richRow(gc, *t_e2c->path);
    t_e2c->current->postRelics = e2cExplicitRelics(gc);
    t_e2c->current->postSeen = true;
    ++t_e2c->roomStats[roomStatsIndex(t_e2c->current->room)].post;
}

void recordE2cScreenState(ScreenState screen) {
    if (t_e2c && t_e2c->current)
        t_e2c->current->screenTrace += "S=" + std::to_string(static_cast<int>(screen)) + ";";
}

void finishE2cRun(bool validRun, bool won, int finalFloor, int endHp) {
    if (!t_e2c) return;
    if (validRun) {
        t_e2cRows = e2cRunRows(*t_e2c, won, finalFloor, endHp);
        for (int i = 0; i < 3; ++i) {
            const auto &s = t_e2c->roomStats[i];
            g_e2cCounts[i][0] += s.eligible;
            g_e2cCounts[i][1] += s.raw;
            g_e2cCounts[i][2] += s.post;
            g_e2cCounts[i][3] += std::count_if(t_e2c->fights.begin(), t_e2c->fights.end(),
                [i](const E2cFight &f) { return f.rawSeen && f.postSeen
                    && roomStatsIndex(f.room) == i; });
            g_e2cCounts[i][4] += std::count_if(t_e2c->fights.begin(), t_e2c->fights.end(),
                [i](const E2cFight &f) { return f.rawSeen && !f.postSeen
                    && roomStatsIndex(f.room) == i; });
            g_e2cCounts[i][5] += std::count_if(t_e2c->fights.begin(), t_e2c->fights.end(),
                [i](const E2cFight &f) { return !f.rawSeen && f.postSeen
                    && roomStatsIndex(f.room) == i; });
        }
        for (const auto &f : t_e2c->fights) {
            if (f.rawSeen != f.postSeen)
                std::cerr << "e2c incomplete seed=" << t_e2c->seed << " fight=" << f.index
                          << " room=" << e2cRoomName(f.room) << " encounter=" << f.encounter
                          << " raw=" << f.rawSeen << " post=" << f.postSeen
                          << " relics=" << f.rewardRelics << " pending_cards=" << f.pendingCards
                          << " trace=" << f.screenTrace << '\n';
        }
    }
    g_onBattleExitPersistent = nullptr;
    t_e2c.reset();
}

std::string takeE2cRows() {
    std::string rows = std::move(t_e2cRows);
    t_e2cRows.clear();
    return rows;
}

void resetE2cAccounting() {
    for (auto &row : g_e2cCounts)
        for (auto &value : row) value = 0;
}

E2cAccountingSnapshot e2cAccounting() {
    E2cAccountingSnapshot snapshot;
    for (int i = 0; i < 3; ++i)
        for (int j = 0; j < 6; ++j) snapshot.counts[i][j] = g_e2cCounts[i][j].load();
    return snapshot;
}

std::string e2cHeader() {
    std::ostringstream out;
    out << "seed,fight_index,boundary,room_type,encounter_id," << richStateHeader();
    for (int i = 0; i < kNumRelics; ++i) out << ",relic_has_" << i;
    for (int i = 0; i < kNumRelics; ++i) out << ",relic_data_" << i;
    out << ",won,finalFloor,endHp\n";
    return out.str();
}

bool loadE2cRawModel(const std::string &path) {
    return g_e2cRawNet.load(path, e2cRawIdxMap(), "E2cRawNet");
}

int runwinParity(const std::string &fixture) {
    if (!g_e2cRawNet.ok) {
        std::cerr << "runwinparity requires STS_RUNWIN_SHADOW_MODEL\n";
        return 2;
    }
    std::ifstream in(fixture);
    std::string header;
    if (!std::getline(in, header)) {
        std::cerr << "runwinparity: cannot read " << fixture << '\n';
        return 2;
    }
    const auto names = splitCsvNames(header);
    std::unordered_map<std::string, int> cols;
    for (int i = 0; i < static_cast<int>(names.size()); ++i) {
        if (!cols.emplace(names[i], i).second) {
            std::cerr << "runwinparity: duplicate fixture column\n";
            return 2;
        }
    }
    const auto expectedIt = cols.find("python_probability");
    if (expectedIt == cols.end()) {
        std::cerr << "runwinparity: fixture needs python_probability\n";
        return 2;
    }
    std::vector<int> modelCols;
    modelCols.reserve(g_e2cRawNet.featureNames.size());
    for (const auto &name : g_e2cRawNet.featureNames) {
        const auto it = cols.find(name);
        if (it == cols.end()) {
            std::cerr << "runwinparity: fixture missing model feature " << name << '\n';
            return 2;
        }
        modelCols.push_back(it->second);
    }
    std::string line;
    int rows = 0;
    double maxError = 0;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        const auto fields = splitCsvNames(line);
        if (fields.size() != names.size()) {
            std::cerr << "runwinparity: malformed row\n";
            return 2;
        }
        std::vector<float> raw(e2cRawCanonicalNames().size(), 0.f);
        for (int i = 0; i < static_cast<int>(g_e2cRawNet.sel.size()); ++i)
            raw[g_e2cRawNet.sel[i]] = std::strtof(fields[modelCols[i]].c_str(), nullptr);
        const double got = g_e2cRawNet.predict(raw);
        const double expected = std::strtod(fields[expectedIt->second].c_str(), nullptr);
        if (!std::isfinite(got)) {
            std::cerr << "runwinparity: invalid native probability\n";
            return 2;
        }
        maxError = std::max(maxError, std::abs(got - expected));
        ++rows;
    }
    std::cout << "runwinparity rows=" << rows << " max_abs_error="
              << std::setprecision(10) << maxError << '\n';
    return rows > 0 && maxError <= 1e-4 ? 0 : 1;
}

int e2cRawProjectionParityTest() {
    const auto fail = [](const std::string &why) {
        std::cerr << "e2c_projection_parity FAIL: " << why << '\n';
        return 1;
    };
    GameContext entry(CharacterClass::IRONCLAD, 0xE2C2026u, 0);
    entry.regainControlAction = [](GameContext &) {};
    entry.act = 2; entry.floorNum = 23; entry.curRoom = Room::ELITE;
    entry.curHp = 20; entry.maxHp = 91; entry.gold = 101; entry.potionChance = 37;
    entry.relics.add({RelicId::MEAT_ON_THE_BONE, 0});
    entry.relics.add({RelicId::HAPPY_FLOWER, 1});
    entry.relics.add({RelicId::NEOWS_LAMENT, 3});
    entry.relics.add({RelicId::LIZARD_TAIL, 1});
    entry.relics.add({RelicId::POTION_BELT, 0});
    entry.potionCapacity = 5;
    entry.potionCount = 2;
    entry.potions[0] = Potion::BLOOD_POTION;
    entry.potions[1] = Potion::DEXTERITY_POTION;
    for (int i = 2; i < 5; ++i) entry.potions[i] = Potion::EMPTY_POTION_SLOT;

    BattleContext terminal;
    terminal.init(entry, MonsterEncounter::GREMLIN_NOB);
    terminal.outcome = Outcome::PLAYER_VICTORY;
    terminal.player.curHp = 20; terminal.player.maxHp = 91; terminal.player.gold = 137;
    terminal.potionCapacity = 5; terminal.potionCount = 2;
    terminal.potions[0] = Potion::STRENGTH_POTION;
    terminal.potions[1] = Potion::FIRE_POTION;
    for (int i = 2; i < 5; ++i) terminal.potions[i] = Potion::EMPTY_POTION_SLOT;
    terminal.player.happyFlowerCounter = 2;
    terminal.player.setHasRelic<RelicId::LIZARD_TAIL>(false);

    PathHistory path;
    std::vector<float> projected;
    if (!e2cProjectTerminalRaw(entry, path, Room::ELITE, MonsterEncounter::GREMLIN_NOB,
                               terminal, projected))
        return fail("projection did not capture terminal victory");

    std::vector<float> canonical;
    GameContext actual = entry;
    const auto previous = g_onBattleExitPersistent;
    g_onBattleExitPersistent = [&](const BattleContext &, GameContext &atRaw) {
        canonical = e2cRawCanonicalVec(atRaw, path, Room::ELITE, MonsterEncounter::GREMLIN_NOB);
    };
    terminal.exitBattle(actual);
    g_onBattleExitPersistent = previous;
    if (canonical.empty() || projected.size() != canonical.size()) return fail("canonical capture shape");
    for (size_t i = 0; i < projected.size(); ++i)
        if (projected[i] != canonical[i])
            return fail("projected vector differs at feature " + e2cRawCanonicalNames()[i]);

    const auto &idx = e2cRawIdxMap();
    const auto require = [&](const std::string &name, float expected) {
        const auto it = idx.find(name);
        return it != idx.end() && projected[it->second] == expected;
    };
    if (!require("curHp", 38) || !require("maxHp", 91) || !require("gold", 137)
        || !require("potionCount", 2) || !require("potionCapacity", 5)
        || !require("potionChance", 37)
        || !require("pot" + std::to_string(static_cast<int>(Potion::STRENGTH_POTION)), 1)
        || !require("pot" + std::to_string(static_cast<int>(Potion::FIRE_POTION)), 1))
        return fail("HP, gold, or potion transfer");
    const int happy = static_cast<int>(RelicId::HAPPY_FLOWER);
    const int lizard = static_cast<int>(RelicId::LIZARD_TAIL);
    const int lament = static_cast<int>(RelicId::NEOWS_LAMENT);
    if (!require("relic_has_" + std::to_string(happy), 1)
        || !require("relic_data_" + std::to_string(happy), 2)
        || !require("relic_has_" + std::to_string(lizard), 1)
        || !require("relic_data_" + std::to_string(lizard), 0)
        || !require("relic_has_" + std::to_string(lament), 1)
        || !require("relic_data_" + std::to_string(lament), 2)
        || !require("room_type", 1)
        || !require("encounter_id", static_cast<float>(static_cast<int>(MonsterEncounter::GREMLIN_NOB))))
        return fail("relic counter, room, or encounter transfer");
    std::cout << "e2c_projection_parity PASS features=" << projected.size()
              << " max_abs_error=0\n";
    return 0;
}

} // namespace one_combat
