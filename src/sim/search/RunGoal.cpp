#include "sim/search/RunGoal.h"
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <stdexcept>
#include <string>

namespace sts::search {
namespace {
HeartKeyRules rulesFromEnv() {
    HeartKeyRules rules;
    const auto value = [](const char *name) -> std::string {
        const char *v = std::getenv(name);
        return v ? v : "";
    };
    const auto bad = [](const char *name, const std::string &v) {
        throw std::runtime_error(std::string(name) + ": unsupported value '" + v + "'");
    };
    if (const auto v = value("STS_KEY_SAPPHIRE"); v == "act3") rules.sapphire = HeartKeyRules::Sapphire::ACT3;
    else if (v == "policy") rules.sapphire = HeartKeyRules::Sapphire::POLICY;
    else if (!v.empty() && v != "first") bad("STS_KEY_SAPPHIRE", v);
    if (const auto v = value("STS_KEY_RUBY"); v == "hp") rules.ruby = HeartKeyRules::Ruby::HP;
    else if (v == "policy") rules.ruby = HeartKeyRules::Ruby::POLICY;
    else if (!v.empty() && v != "first") bad("STS_KEY_RUBY", v);
    if (const auto v = value("STS_KEY_RUBY_MIN_HP"); !v.empty()) {
        char *end = nullptr;
        rules.rubyMinHp = std::strtod(v.c_str(), &end);
        if (end == v.c_str() || *end || !(rules.rubyMinHp >= 0 && rules.rubyMinHp <= 1)) bad("STS_KEY_RUBY_MIN_HP", v);
    }
    if (const auto v = value("STS_KEY_EMERALD"); v == "mask") rules.emerald = HeartKeyRules::Emerald::MASK;
    else if (!v.empty() && v != "first") bad("STS_KEY_EMERALD", v);
    return rules;
}

bool keysActive(const GameContext &gc, bool collectKeys) {
    return collectKeys && gc.keysEnabled && gc.outcome == GameOutcome::UNDECIDED;
}

// Next-row x positions that still reach the Act-3 burning elite, or nullopt
// when the Emerald route rule does not apply to this map screen.
std::optional<std::array<bool, 7>> emeraldRouteNext(const GameContext &gc) {
    if (gc.screenState != ScreenState::MAP_SCREEN || gc.act != 3 || gc.greenKey || !gc.map)
        return std::nullopt;
    const int bx = gc.map->burningEliteX, by = gc.map->burningEliteY;
    if (bx < 0 || bx >= 7 || by < 0 || by >= 15 || gc.curMapNodeY >= by) return std::nullopt;
    std::array<std::array<bool, 7>, 15> reaches{};
    reaches[by][bx] = true;
    for (int y = by - 1; y >= 0; --y) for (int x = 0; x < 7; ++x) {
        const auto &node = gc.map->getNode(x, y);
        for (int i = 0; i < node.edgeCount; ++i) {
            const int next = node.edges[i];
            if (next >= 0 && next < 7 && reaches[y + 1][next]) reaches[y][x] = true;
        }
    }
    const int nextY = gc.curMapNodeY + 1;
    if (nextY < 0 || nextY > by) return std::nullopt;
    return reaches[nextY];
}

bool offersSapphireOnly(const GameContext &gc) {
    const auto &r = gc.info.rewardsContainer;
    return gc.screenState == ScreenState::REWARDS && r.sapphireKey && !r.emeraldKey;
}
}

HeartKeyRules &heartKeyRules() {
    static HeartKeyRules rules = [] {
        const auto r = rulesFromEnv();
        if (!r.isDefault())
            std::fprintf(stderr, "heart_key_rules sapphire=%d ruby=%d ruby_min_hp=%.3f emerald=%d\n",
                         int(r.sapphire), int(r.ruby), r.rubyMinHp, int(r.emerald));
        return r;
    }();
    return rules;
}

std::optional<GameAction> heartKeyAction(const GameContext &gc, bool collectKeys) {
    if (!keysActive(gc, collectKeys)) return std::nullopt;
    using RT = GameAction::RewardsActionType;
    const auto &rules = heartKeyRules();
    if (gc.screenState == ScreenState::REWARDS) {
        const auto &r = gc.info.rewardsContainer;
        bool take = r.emeraldKey;
        if (r.sapphireKey && !take) {
            switch (rules.sapphire) {
                case HeartKeyRules::Sapphire::FIRST: take = true; break;
                case HeartKeyRules::Sapphire::ACT3: take = gc.act >= 3; break;
                // Every act has a treasure row (Map.cpp), so the Act-3 one is the last sure chest.
                case HeartKeyRules::Sapphire::POLICY: take = gc.act >= 3 && gc.curMapNodeY >= 8; break;
            }
        }
        // Sapphire must precede its paired relic, which removes the key offer.
        if (take && GameAction(RT::KEY, 0).isValidAction(gc)) return GameAction(RT::KEY, 0);
    }
    if (gc.screenState == ScreenState::REST_ROOM && gc.act >= 3 && !gc.redKey
            && GameAction(2).isValidAction(gc)) {
        // The last map row is always a campfire (Map.cpp restRow).
        const bool lastFire = gc.curMapNodeY >= 14;
        bool take = true;
        if (rules.ruby == HeartKeyRules::Ruby::HP)
            take = lastFire || gc.curHp >= rules.rubyMinHp * gc.maxHp;
        else if (rules.ruby == HeartKeyRules::Ruby::POLICY) take = lastFire;
        if (take) return GameAction(2);
    }
    const auto next = emeraldRouteNext(gc);
    if (!next) return std::nullopt;
    std::optional<GameAction> first;
    int reaching = 0;
    for (const auto action : GameAction::getAllActionsInState(gc)) {
        const int x = action.getIdx1();
        if (x < 7 && (*next)[x] && action.isValidAction(gc)) {
            if (!first) first = action;
            ++reaching;
        }
    }
    if (rules.emerald == HeartKeyRules::Emerald::MASK && reaching > 1) return std::nullopt;
    return first;
}

bool heartKeyActionAllowed(const GameContext &gc, bool collectKeys, const GameAction &action) {
    const auto &rules = heartKeyRules();
    if (rules.isDefault() || !keysActive(gc, collectKeys)) return true;
    if (rules.sapphire == HeartKeyRules::Sapphire::ACT3 && gc.act < 3 && offersSapphireOnly(gc))
        return action.getRewardsActionType() != GameAction::RewardsActionType::KEY;
    if (rules.emerald != HeartKeyRules::Emerald::MASK) return true;
    const auto next = emeraldRouteNext(gc);
    if (!next) return true;
    bool any = false;
    for (const auto a : GameAction::getAllActionsInState(gc))
        if (a.getIdx1() < 7 && (*next)[a.getIdx1()] && a.isValidAction(gc)) any = true;
    return !any || (action.getIdx1() < 7 && (*next)[action.getIdx1()]);
}
}
