// Fair-play test of the stage 1 self-play driver's combat view (az_run_driver.h, ADR-0002): two live fights that
// differ only in hidden information (the draw pile's order; under Runic Dome also the rolled intents) must give
// identical net inputs at the public root and identical searches from it (the same actions under the same search
// seed reach identically encoded states). Also checks that the test is sensitive: the raw live states encode
// differently when the draw order differs.
//
// usage: az-fair-view-test [--fights 40]
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <random>
#include <string>
#include <vector>

#include "az_run_driver.h"
#include "sim/search/AmberEncoder.h"
#include "sim/search/SearchRng.h"

using namespace sts;

using search::GameAction;

namespace {
    search::SilverSearchContext ctxOf(const GameContext &gc) {
        search::SilverSearchContext c;
        c.act = gc.act;
        c.actBossRoom = gc.curRoom == Room::BOSS;
        c.eliteRewards = gc.isEliteTriggerCombat();
        return c;
    }

    std::vector<search::Action> actionsOf(const BattleContext &bc) {
        search::SilverSearcher s(bc, search::SilverSearchContext{});
        return s.enumerateActions(bc);
    }

    bool sameTokens(const search::AmberTokens &a, const search::AmberTokens &b) {
        if (a.n != b.n || a.nAct != b.nAct || a.cut != b.cut) return false;
        for (int t = 0; t < search::kAmberTokenTypes; ++t)
            for (int i = 0; i < a.n[t]; ++i) {
                const auto &x = a.tok[search::kAmberOff[t] + i], &y = b.tok[search::kAmberOff[t] + i];
                if (x.ids != y.ids || x.f != y.f) return false;
            }
        for (int i = 0; i < a.nAct; ++i) {
            const auto &x = a.act[i], &y = b.act[i];
            if (x.type != y.type || x.srcSeg != y.srcSeg || x.tgtSeg != y.tgtSeg || x.srcIdx != y.srcIdx
                || x.tgtIdx != y.tgtIdx || x.f != y.f) return false;
        }
        return true;
    }

    std::vector<std::uint32_t> bitsOf(const std::vector<search::Action> &a) {
        std::vector<std::uint32_t> b;
        for (const auto &x : a) b.push_back(x.bits);
        return b;
    }
}

int main(int argc, char **argv) {
    int fights = 40;
    for (int i = 1; i < argc; ++i)
        if (!std::strcmp(argv[i], "--fights") && i + 1 < argc) fights = std::atoi(argv[++i]);
    int checked = 0, checkedDome = 0, sensitive = 0, failures = 0, steps = 0, skipped = 0;
    auto encode = [](const BattleContext &bc, const search::SilverSearchContext &c, search::AmberTokens &t) {
        amberEncodeCombat(bc, c, actionsOf(bc), t);
    };
    search::AmberTokens t1, t2;
    for (int f = 0; f < fights; ++f) {
        const bool dome = f % 2 == 1;
        const std::uint64_t seed = 7000 + f;
        std::mt19937_64 rng(seed);
        GameContext gc(CharacterClass::IRONCLAD, seed, 20);
        gc.curHp = gc.maxHp = 5000;   // survive random play into later fights
        if (dome) gc.relics.add({RelicId::RUNIC_DOME, 0});
        // Random out-of-combat play into the first (f / 2 % 3 + 1)-th fight; random combat moves before it.
        const int want = f / 2 % 3 + 1;
        int fightsSeen = 0, guard = 0;
        BattleContext live;
        search::CombatKnowledgeState k;
        bool ready = false;
        while (gc.outcome == GameOutcome::UNDECIDED && ++guard < 4000 && !ready) {
            if (gc.screenState == ScreenState::BATTLE) {
                azbench::initObservedBattle(gc, live, k);
                ++fightsSeen;
                const int pre = static_cast<int>(rng() % 12);
                for (int m = 0; live.outcome == Outcome::UNDECIDED; ++m) {
                    const auto acts = actionsOf(live);
                    if (acts.empty()) break;
                    if (fightsSeen == want && m >= pre && live.cards.drawPile.size() >= 3) { ready = true; break; }
                    azbench::executeObserved(live, acts[rng() % acts.size()].bits, k);
                }
                if (ready) break;
                if (live.outcome == Outcome::UNDECIDED) break;   // dead end
                live.exitBattle(gc);
                continue;
            }
            const auto acts = GameAction::getAllActionsInState(gc);
            if (acts.empty()) break;
            acts[rng() % acts.size()].execute(gc);
        }
        if (!ready) { ++skipped; continue; }
        const auto ctx = ctxOf(gc);
        // The other world: the same fight with the draw pile in reverse order; under Dome also another rolled move.
        BattleContext other = live;
        auto &cards = other.cards.drawPile.concreteCards();
        std::reverse(cards.begin(), cards.end());
        if (dome)
            for (int i = 0; i < other.monsters.monsterCount; ++i) {
                auto &m = other.monsters.arr[i];
                m.moveHistory[0] = m.moveHistory[1];
            }
        encode(live, ctx, t1);
        encode(other, ctx, t2);
        if (!sameTokens(t1, t2)) ++sensitive;
        search::CombatKnowledgeState k2 = k;
        BattleContext r1, r2;
        const auto e1 = azbench::publicCombatRoot(live, k, r1);
        const auto e2 = azbench::publicCombatRoot(other, k2, r2);
        if (!e1.empty() || !e2.empty()) {
            std::printf("fight %d: no public view (%s / %s)\n", f, e1.c_str(), e2.c_str());
            ++skipped;
            continue;
        }
        bool ok = true;
        if (dome && !r1.intentsHidden) { std::printf("fight %d: Dome root shows intents\n", f); ok = false; }
        // A short deterministic search path: the same actions under the same search seeds.
        std::mt19937_64 pick(seed * 31 + 1);
        for (int s = 0; s < 60 && ok; ++s) {
            encode(r1, ctx, t1);
            encode(r2, ctx, t2);
            if (!sameTokens(t1, t2)) { std::printf("fight %d step %d: public views encode differently\n", f, s); ok = false; break; }
            if (r1.outcome != Outcome::UNDECIDED || r2.outcome != Outcome::UNDECIDED) {
                if (r1.outcome != r2.outcome) { std::printf("fight %d step %d: outcomes differ\n", f, s); ok = false; }
                break;
            }
            const auto a1 = actionsOf(r1), a2 = actionsOf(r2);
            if (bitsOf(a1) != bitsOf(a2)) { std::printf("fight %d step %d: actions differ\n", f, s); ok = false; break; }
            if (a1.empty()) break;
            const auto bits = a1[pick() % a1.size()].bits;
            const std::uint64_t sseed = search::searchRandomnessBase(r1);
            if (sseed != search::searchRandomnessBase(r2)) { std::printf("fight %d step %d: search seeds differ\n", f, s); ok = false; break; }
            search::seedSearchRng(r1, sseed + s);
            search::seedSearchRng(r2, sseed + s);
            search::Action(bits).execute(r1);
            search::Action(bits).execute(r2);
            ++steps;
        }
        ++checked;
        if (dome) ++checkedDome;
        if (!ok) ++failures;
    }
    std::printf("{\"fights_checked\": %d, \"dome\": %d, \"search_steps\": %d, \"raw_differs\": %d, \"skipped\": %d, "
                "\"failures\": %d}\n", checked, checkedDome, steps, sensitive, skipped, failures);
    const bool pass = failures == 0 && checked >= fights / 2 && checkedDome >= 1 && sensitive >= 1;
    std::printf(pass ? "PASS\n" : "FAIL\n");
    return pass ? 0 : 1;
}
