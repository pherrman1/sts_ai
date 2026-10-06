#include "silver_vwin_pricer.h"

#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <memory>
#include <mutex>
#include <optional>
#include <random>
#include <stdexcept>
#include <unordered_map>
#include <vector>
#include <time.h>

#include <nlohmann/json.hpp>

#include "combat/BattleContext.h"
#include "game/GameContext.h"
#include "sim/search/NativeSilverBackend.h"
#include "sim/search/SilverSearcher.h"
#include "ooc_mcts_adapter.h"
#include "ooc_policy.h"
#include "run_features.h"
#include "screen_leaf_gbm.h"
#include "screen_leaf_s0.h"

namespace one_combat {
namespace {

using sts::BattleContext;
using sts::GameContext;
using sts::RelicId;

double threadSeconds() {
    timespec ts{};
    clock_gettime(CLOCK_THREAD_CPUTIME_ID, &ts);
    return double(ts.tv_sec) + 1e-9 * double(ts.tv_nsec);
}

std::mutex g_totalsMutex;
SilverVwinLeafTotals g_totals;

// What a won (or escaped) fight carries out of the battle: exactly the fields
// BattleContext::exitBattle writes into the run that v_win can see.
struct Exit {
    int curHp = 0, maxHp = 0, gold = 0, stolenGold = 0, potionCount = 0;
    std::array<sts::Potion, 5> potions{};
    bool escape = false, writhingImplant = false, omamori = false, lizardSpent = false;
    // Act 1-2 boss wins heal at the act transition after the boss chest; v_win
    // is asked about the healed run (§353: the slope shifts across the heal).
    bool actHeal = true;

    static Exit of(const BattleContext &bc) {
        Exit e;
        e.curHp = bc.player.curHp; e.maxHp = bc.player.maxHp; e.gold = bc.player.gold;
        e.potionCount = bc.potionCount; e.potions = bc.potions;
        e.escape = bc.smokeBombUsed;
        const auto &m = bc.monsters.arr[0];
        e.writhingImplant = m.id == sts::MonsterId::WRITHING_MASS && m.miscInfo;
        e.omamori = bc.player.hasRelic<RelicId::OMAMORI>();
        e.lizardSpent = !bc.player.hasRelic<RelicId::LIZARD_TAIL>();
        if (bc.requiresStolenGoldCheck()) {
            for (int i = 0; i < bc.monsters.monsterCount; ++i) {
                const auto &t = bc.monsters.arr[i];
                const bool thief = t.id == sts::MonsterId::LOOTER || t.id == sts::MonsterId::MUGGER;
                const bool escaped = t.curHp > 0 && (t.moveHistory[0] == sts::MMID::LOOTER_ESCAPE
                                                     || t.moveHistory[0] == sts::MMID::MUGGER_ESCAPE);
                if (thief && !escaped) e.stolenGold += t.miscInfo;
            }
        }
        return e;
    }
    std::string key() const {
        std::string k;
        const int ints[] = {curHp, maxHp, gold, stolenGold, potionCount,
                            escape, writhingImplant, omamori, lizardSpent, actHeal};
        k.append(reinterpret_cast<const char *>(ints), sizeof(ints));
        for (const auto p : potions) k.push_back(static_cast<char>(p));
        return k;
    }
    // Mirrors exitBattle on a victory: Parasite/Omamori, potions, HP, gold,
    // Lizard Tail, Burning/Black Blood, stolen gold, then the room's own
    // continuation (rewards, map, event, boss chest or act transition).
    void apply(GameContext &g) const {
        if (writhingImplant) {
            if (omamori) {
                auto &charges = g.relics.getRelicValueRef(RelicId::OMAMORI);
                if (charges > 0) --charges;
            } else {
                g.deck.obtain(g, sts::CardId::PARASITE);
            }
        }
        g.potionCount = potionCount;
        g.potions = potions;
        g.smokeBombUsed = escape;
        g.curHp = curHp; g.maxHp = maxHp; g.gold = gold;
        if (lizardSpent && g.relics.has(RelicId::LIZARD_TAIL))
            g.relics.getRelicValueRef(RelicId::LIZARD_TAIL) = 0;
        if (g.relics.has(RelicId::BURNING_BLOOD)) g.playerHeal(6);
        if (g.relics.has(RelicId::BLACK_BLOOD)) g.playerHeal(12);
        if (actHeal && g.curRoom == sts::Room::BOSS && g.act <= 2) {
            // GameContext::transitionToAct; Act 3 and 4 boss continuations
            // already transition (or end the run) inside regainControl.
            if (g.ascension >= 5) g.playerHeal(static_cast<int>(std::round(static_cast<float>(g.maxHp - g.curHp) * 0.75f)));
            else g.playerHeal(g.maxHp);
        }
        g.info.stolenGold = stolenGold;
        g.regainControl();
    }
};

struct Models {
    std::shared_ptr<const ScreenLeafGbm> gbm;
    int samples = 4;
    bool price = true;       // false: STS_SILVER_VWIN_LEAF_AUDIT only, Silver keeps its formula
    std::string auditPath;   // STS_SILVER_VWIN_LEAF_AUDIT: one JSON line per combat
};

class VwinTerminalPricer final : public sts::search::SilverTerminalPricer {
public:
    VwinTerminalPricer(const GameContext &gc, const BattleContext &bc, const PathHistory &path,
                       std::shared_ptr<const Models> models, std::uint64_t seed)
            : models_(std::move(models)), path_(path) {
        std::mt19937_64 rng(seed);
        for (int k = 0; k < models_->samples; ++k) {
            GameContext t = gc;
            if (gc.map) t.map = std::make_shared<sts::Map>(*gc.map);
            sampleOocNoncombatFuture(t, rng);
            templates_.push_back(std::move(t));
        }
        Stats stats;
        Exit lo = Exit::of(bc), hi = lo;
        // The HP scale is the run's pre-heal HP price, so a boss win's
        // potions and gold still trade in HP units after the heal.
        lo.escape = hi.escape = false;
        lo.actHeal = hi.actHeal = false;
        lo.curHp = 1; hi.curHp = std::max(1, bc.player.maxHp);
        vLo_ = value(lo, stats);
        const double vHi = value(hi, stats);
        flat_ = !(vHi - vLo_ > 1e-6) || hi.curHp <= 1;
        slope_ = flat_ ? 0 : std::max((vHi - vLo_) / (hi.curHp - 1), kMinSlope);
        offset_ = 1 + sts::search::SilverEvalWeights{}.potionWeight * bc.potionCount;
        cap_ = 3.0 * std::max(1, bc.player.maxHp) + offset_;
        stats.combats = 1; stats.flatCombats = flat_;
        flush(stats);
    }
    ~VwinTerminalPricer() override { flush(pending_); }

    // Diagnostic (#367 follow-up): the combat's price surface at the root,
    // next to `other`, a pricer built on independent futures (sampling noise).
    nlohmann::json audit(const BattleContext &bc, VwinTerminalPricer &other) {
        const auto ended = [&](int hp, bool escape, int dropSlot, int goldDelta) {
            BattleContext end = bc;
            end.outcome = sts::Outcome::PLAYER_VICTORY;
            end.player.curHp = hp; end.smokeBombUsed = escape; end.player.gold += goldDelta;
            if (dropSlot >= 0) { end.potions[dropSlot] = sts::Potion::EMPTY_POTION_SLOT; --end.potionCount; }
            return end;
        };
        nlohmann::json out{{"flat", flat_ || other.flat_}, {"slope", slope_}, {"vLo", vLo_}};
        if (flat_ || other.flat_) return out;
        const int hp = bc.player.curHp, maxHp = bc.player.maxHp;
        std::vector<double> sweep;
        for (int h = 1; h <= maxHp; ++h) sweep.push_back(*victoryHpEquivalent(ended(h, false, -1, 0)));
        out["hpPrices"] = sweep;
        const double base = *victoryHpEquivalent(ended(hp, false, -1, 0));
        out["base"] = base;
        out["baseOther"] = *other.victoryHpEquivalent(ended(hp, false, -1, 0));
        out["escapeGap"] = base - *victoryHpEquivalent(ended(hp, true, -1, 0));
        out["escapeGapOther"] = *other.victoryHpEquivalent(ended(hp, false, -1, 0))
            - *other.victoryHpEquivalent(ended(hp, true, -1, 0));
        out["gold25"] = *victoryHpEquivalent(ended(hp, false, -1, 25)) - base;
        nlohmann::json potions = nlohmann::json::array();
        for (int i = 0; i < bc.potionCapacity; ++i) {
            if (bc.potions[i] == sts::Potion::EMPTY_POTION_SLOT) continue;
            potions.push_back({{"potion", static_cast<int>(bc.potions[i])},
                               {"value", base - *victoryHpEquivalent(ended(hp, false, i, 0))},
                               {"valueOther", *other.victoryHpEquivalent(ended(hp, false, -1, 0))
                                    - *other.victoryHpEquivalent(ended(hp, false, i, 0))}});
        }
        out["potions"] = potions;
        return out;
    }

    std::optional<double> victoryHpEquivalent(const BattleContext &end) override {
        if (flat_) return std::nullopt;
        ++pending_.lookups;
        const Exit exit = Exit::of(end);
        auto key = exit.key();
        if (const auto it = cache_.find(key); it != cache_.end()) return it->second;
        const double v = value(exit, pending_);
        ++pending_.prices;
        const double price = std::clamp(offset_ + (v - vLo_) / slope_, 0.0, cap_);
        cache_.emplace(std::move(key), price);
        return price;
    }

private:
    using Stats = SilverVwinLeafTotals;
    // Below a quarter of the typical act-1 X2-B HP slope (§353) the HP scale
    // would magnify model noise; flatter HP pricing keeps this floor.
    static constexpr double kMinSlope = 0.0005;

    double value(const Exit &exit, Stats &stats) {
        const double start = threadSeconds();
        double sum = 0;
        for (const auto &t : templates_) {
            GameContext g = t;
            if (t.map) g.map = std::make_shared<sts::Map>(*t.map);
            if (!g.regainControlAction) throw std::runtime_error("silver vwin leaf: battle without continuation");
            exit.apply(g);
            sum += evaluate(g, stats);
        }
        stats.seconds += threadSeconds() - start;
        return sum / double(templates_.size());
    }

    double evaluate(const GameContext &g, Stats &stats) const {
        if (g.outcome == sts::GameOutcome::PLAYER_VICTORY) { ++stats.decided; return 1; }
        if (g.outcome == sts::GameOutcome::PLAYER_LOSS) { ++stats.decided; return 0; }
        auto rich = richFeatureVec(g, path_);
        if (g.screenState != sts::ScreenState::MAP_SCREEN && g.screenState != sts::ScreenState::BATTLE) {
            nlohmann::json contract;
            try { contract = screenLeafPublicContract(g); }
            catch (const std::exception &) { contract = nullptr; }
            if (!contract.is_null()) {
                static const int goldIndex = richIdxMap().at("gold");
                const auto keys = contract.at("candidateKeys").get<std::vector<std::string>>();
                const auto screen = screenGbmFeatures(contract.at("screenContents"), keys, rich.at(goldIndex));
                const double x2b = std::clamp(models_->gbm->anchor(rich), 1e-7, 1 - 1e-7);
                rich.insert(rich.end(), screen.begin(), screen.end());
                const double margin = std::log(x2b / (1 - x2b)) + models_->gbm->residual(rich);
                ++stats.screenGbm;
                return 1.0 / (1.0 + std::exp(-margin));
            }
            ++stats.fallbacks;
        }
        ++stats.anchor;
        return models_->gbm->anchor(rich);
    }

    static void flush(Stats &s) {
        std::lock_guard<std::mutex> lock(g_totalsMutex);
        g_totals.combats += s.combats; g_totals.flatCombats += s.flatCombats;
        g_totals.prices += s.prices; g_totals.lookups += s.lookups;
        g_totals.screenGbm += s.screenGbm; g_totals.anchor += s.anchor;
        g_totals.fallbacks += s.fallbacks; g_totals.decided += s.decided;
        g_totals.seconds += s.seconds;
        s = {};
    }

    std::shared_ptr<const Models> models_;
    PathHistory path_;
    std::vector<GameContext> templates_;
    std::unordered_map<std::string, double> cache_;
    Stats pending_;
    double vLo_ = 0, slope_ = 0, offset_ = 0, cap_ = 0;
    bool flat_ = true;
};

std::uint64_t mix(std::uint64_t x) {
    x += 0x9e3779b97f4a7c15ULL;
    x = (x ^ (x >> 30)) * 0xbf58476d1ce4e5b9ULL;
    x = (x ^ (x >> 27)) * 0x94d049bb133111ebULL;
    return x ^ (x >> 31);
}

} // namespace

std::string configureSilverVwinLeaf() {
    const char *raw = std::getenv("STS_SILVER_VWIN_LEAF");
    const char *audit = std::getenv("STS_SILVER_VWIN_LEAF_AUDIT");
    const bool price = raw && *raw && std::strcmp(raw, "0") != 0;
    if (price && std::strcmp(raw, "1") != 0) throw std::runtime_error("STS_SILVER_VWIN_LEAF must be 0 or 1");
    if (!price && !(audit && *audit)) return "off";
    auto models = std::make_shared<Models>();
    models->price = price;
    if (audit && *audit) models->auditPath = audit;
    if (const char *k = std::getenv("STS_SILVER_VWIN_LEAF_SAMPLES"); k && *k) {
        char *end = nullptr;
        const long samples = std::strtol(k, &end, 10);
        if (end == k || *end || samples < 1 || samples > 64)
            throw std::runtime_error("STS_SILVER_VWIN_LEAF_SAMPLES must be 1..64");
        models->samples = int(samples);
    }
    models->gbm = std::make_shared<const ScreenLeafGbm>(kDefaultScreenGbmModel, richIdxMap(),
        int(richIdxMap().size()), kScreenGbmAnchor);
    std::shared_ptr<const Models> shared = models;
    sts::search::g_nativeSilverTerminalPricerFactory = [shared](const GameContext &gc, const BattleContext &bc)
            -> std::shared_ptr<sts::search::SilverTerminalPricer> {
        static const PathHistory emptyPath;
        if (gc.screenState != sts::ScreenState::BATTLE || !gc.regainControlAction) {
            std::lock_guard<std::mutex> lock(g_totalsMutex);
            ++g_totals.unsupported;
            return nullptr;
        }
        const std::uint64_t seed = mix(gc.seed ^ mix(std::uint64_t(gc.floorNum) << 20
            ^ std::uint64_t(static_cast<int>(bc.encounter))));
        try {
            if (!shared->auditPath.empty()) {
                const auto &path = t_curPath ? *t_curPath : emptyPath;
                VwinTerminalPricer a(gc, bc, path, shared, seed), b(gc, bc, path, shared, mix(seed ^ 0x5eed));
                nlohmann::json row{{"seed", gc.seed}, {"act", gc.act}, {"floor", gc.floorNum},
                    {"room", static_cast<int>(gc.curRoom)}, {"encounter", static_cast<int>(bc.encounter)},
                    {"curHp", bc.player.curHp}, {"maxHp", bc.player.maxHp}, {"gold", bc.player.gold},
                    {"deckSize", gc.deck.size()}};
                row["audit"] = a.audit(bc, b);
                {
                    std::lock_guard<std::mutex> lock(g_totalsMutex);
                    std::ofstream(shared->auditPath, std::ios::app) << row.dump() << '\n';
                }
                if (!shared->price) return nullptr;
            }
            return std::make_shared<VwinTerminalPricer>(gc, bc, t_curPath ? *t_curPath : emptyPath, shared, seed);
        } catch (const sts::search::OocSearchUnsupported &) {
            // The run's hidden future cannot be re-drawn: keep Silver's formula.
            std::lock_guard<std::mutex> lock(g_totalsMutex);
            ++g_totals.unsupported;
            return nullptr;
        }
    };
    if (!price) return "off";  // audit only: play is unchanged
    return std::string("x2b+") + kDefaultScreenGbmModel + ";samples=" + std::to_string(models->samples);
}

SilverVwinLeafTotals silverVwinLeafTotals() {
    std::lock_guard<std::mutex> lock(g_totalsMutex);
    return g_totals;
}

namespace {
// A run state entering a fight of `room` on the first floor of `act`,
// holding a Smoke Bomb and a Block Potion. EVENT is a Dead Adventurer fight.
std::optional<GameContext> fightState(std::uint64_t seed, sts::Room room, int act) {
    GameContext gc(sts::CharacterClass::IRONCLAD, seed, 0);
    if (act > 1) gc.transitionToAct(act);
    gc.obtainPotion(sts::Potion::SMOKE_BOMB);
    gc.obtainPotion(sts::Potion::BLOCK_POTION);
    if (room == sts::Room::BOSS) {
        gc.curMapNodeX = 0; gc.curMapNodeY = 14;
        gc.transitionToMapNode(0);
    } else {
        int x = 0;
        while (x < 7 && gc.map->getNode(x, 0).edgeCount == 0) ++x;
        gc.map = std::make_shared<sts::Map>(*gc.map);
        gc.map->getNode(x, 0).room = room == sts::Room::EVENT ? sts::Room::MONSTER : room;
        gc.transitionToMapNode(x);
        if (room == sts::Room::EVENT) {
            gc.curRoom = sts::Room::EVENT;
            gc.curEvent = sts::Event::DEAD_ADVENTURER;
            gc.screenState = sts::ScreenState::EVENT_SCREEN;
            gc.setupEvent();
            gc.chooseEventOption(0);
        }
    }
    if (gc.screenState != sts::ScreenState::BATTLE || gc.curRoom != room) return std::nullopt;
    return gc;
}

BattleContext ended(const BattleContext &bc, int hp, bool escape) {
    BattleContext end = bc;
    end.outcome = sts::Outcome::PLAYER_VICTORY;
    end.player.curHp = hp;
    end.smokeBombUsed = escape;
    for (int i = 0; i < end.potionCapacity; ++i)
        if (end.potions[i] == sts::Potion::SMOKE_BOMB) { end.potions[i] = sts::Potion::EMPTY_POTION_SLOT; --end.potionCount; }
    return end;
}
} // namespace

int silverVwinLeafSelfTest() {
    setenv("STS_SILVER_VWIN_LEAF", "1", 1);
    setenv("STS_SILVER_VWIN_LEAF_SAMPLES", "4", 1);
    const auto label = configureSilverVwinLeaf();
    const auto &factory = sts::search::g_nativeSilverTerminalPricerFactory;
    if (label == "off" || !factory) throw std::runtime_error("pricer not installed");
    bool pass = true;
    nlohmann::json report = nlohmann::json::array();
    const auto check = [&](bool ok, const std::string &what) {
        if (!ok) { pass = false; std::cerr << "FAIL: " << what << '\n'; }
    };
    struct Case { const char *name; sts::Room room; int act; bool escapeForfeits; };
    const Case cases[] = {
        {"normal", sts::Room::MONSTER, 1, true}, {"elite", sts::Room::ELITE, 1, true},
        {"event_dead_adventurer", sts::Room::EVENT, 1, false}, {"boss_act1", sts::Room::BOSS, 1, false},
        {"boss_act3", sts::Room::BOSS, 3, false},
    };
    for (const auto &c : cases) {
        std::optional<GameContext> gc;
        for (std::uint64_t seed = 1; seed < 200 && !gc; ++seed) gc = fightState(seed, c.room, c.act);
        check(gc.has_value(), std::string(c.name) + ": no fight state");
        if (!gc) continue;
        BattleContext bc;
        bc.init(*gc);
        auto pricer = factory(*gc, bc);
        auto again = factory(*gc, bc);
        check(pricer && again, std::string(c.name) + ": no pricer");
        if (!pricer || !again) continue;
        const int maxHp = bc.player.maxHp;
        const auto full = pricer->victoryHpEquivalent(ended(bc, maxHp, false));
        nlohmann::json row{{"case", c.name}, {"encounter", static_cast<int>(bc.encounter)}};
        if (c.act == 3 && c.room == sts::Room::BOSS) {
            // The run ends on this win: v_win cannot rank wins, Silver keeps its formula.
            check(!full.has_value(), "boss_act3: a run-ending win must keep handcrafted pricing");
            row["flat"] = true;
            report.push_back(row);
            continue;
        }
        const auto low = pricer->victoryHpEquivalent(ended(bc, std::max(1, maxHp / 4), false));
        check(full && low, std::string(c.name) + ": no price");
        if (!full || !low) continue;
        check(*pricer->victoryHpEquivalent(ended(bc, maxHp, false)) == *full, std::string(c.name) + ": cache");
        check(*again->victoryHpEquivalent(ended(bc, maxHp, false)) == *full, std::string(c.name) + ": determinism");
        row["fullHp"] = *full; row["quarterHp"] = *low;
        if (c.room == sts::Room::BOSS)
            check(*full == *low, std::string(c.name) + ": an A0 act-boss win heals to full, so HP must not change its price");
        if (c.room != sts::Room::BOSS) {
            check(*full > *low, std::string(c.name) + ": full HP must price above quarter HP");
            const auto escape = pricer->victoryHpEquivalent(ended(bc, maxHp, true));
            check(escape.has_value(), std::string(c.name) + ": no escape price");
            if (escape) {
                row["escapeFullHp"] = *escape;
                if (c.escapeForfeits) check(*escape < *full, std::string(c.name) + ": escape must price below a win");
            }
        }
        report.push_back(row);
    }
    const auto totals = silverVwinLeafTotals();
    std::cout << nlohmann::json{{"label", label}, {"cases", report}, {"screenGbm", totals.screenGbm},
        {"anchor", totals.anchor}, {"fallbacks", totals.fallbacks}, {"decided", totals.decided},
        {"pass", pass}}.dump() << '\n';
    return pass ? 0 : 1;
}

} // namespace one_combat
