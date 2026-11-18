// Amber Eye's out-of-combat chance rule (search::oocStepRevealsHidden, stage 1 RunConfig::chanceOnReveal) is fair:
// over random-legal whole A20 runs (battles skipped), every out-of-combat step the detector calls deterministic gives
// the same public result (amberEncodeGame tokens and legal actions, screen, outcome) when the hidden state is
// resampled first (sampleNoncombatFuture, 3 samples). A deterministic step therefore cannot show the search anything
// the real hidden state decides. Checked for single steps and for simHelp steps (the action, then reward gold and
// forced single-action positions, as the run driver steps them). Also prints how many steps are chance steps per
// screen. Fixed seeds 1..N (no gameplay evaluation, outcomes unused).
//
// usage: amber_chance_rule_test [runs=60]
#include "sim/search/AmberEncoder.h"
#include "sim/search/GameAction.h"
#include "sim/search/OocHiddenFuture.h"
#include "sim/search/OocMctsPlanner.h"
#include "sim/search/OocSemanticAction.h"

#include <cstdlib>
#include <cstring>
#include <iostream>
#include <map>
#include <random>
#include <vector>

using namespace sts;
using namespace sts::search;

namespace {

    int g_fail = 0;

    std::vector<GameAction> legal(const GameContext &gc) {
        auto v = GameAction::getAllActionsInState(gc);
        std::vector<GameAction> out;
        for (const auto &a : v)
            if (isSupportedAutonomousOocAction(gc, a)) out.push_back(a);
        return out;
    }

    // The public result of a state: its tokens and legal actions as the net sees them, plus screen and outcome.
    std::vector<std::uint8_t> publicBytes(const GameContext &gc) {
        AmberTokens t;
        std::memset(&t, 0, sizeof t);
        const auto acts = legal(gc);
        amberEncodeGame(gc, acts, t);
        std::vector<std::uint8_t> b;
        const auto add = [&](const void *p, std::size_t n) {
            const auto *c = static_cast<const std::uint8_t *>(p);
            b.insert(b.end(), c, c + n);
        };
        add(t.n.data(), t.n.size());
        add(&t.nAct, sizeof t.nAct);
        for (int s = 0; s < kAmberTokenTypes; ++s)
            for (int i = 0; i < t.n[s]; ++i) add(&t.tok[kAmberOff[s] + i], sizeof(t.tok[0]));
        for (int i = 0; i < t.nAct; ++i) add(&t.act[i], sizeof(t.act[0]));
        for (const auto &a : acts) add(&a.bits, sizeof a.bits);
        const int screen = static_cast<int>(gc.screenState), outcome = static_cast<int>(gc.outcome);
        add(&screen, sizeof screen);
        add(&outcome, sizeof outcome);
        return b;
    }

    // One step: the action, and with simHelp reward gold and forced positions after it (as the run driver). Each
    // primitive step is tested on its own; returns whether any revealed hidden information.
    bool step(GameContext &gc, const GameAction &a, bool simHelp) {
        bool revealed = false;
        const auto exec = [&](const GameAction &x) {
            const auto snap = captureOocHidden(gc);
            x.execute(gc);
            revealed = revealed || oocStepRevealsHidden(snap, gc);
        };
        exec(a);
        if (!simHelp) return revealed;
        for (int guard = 0; guard < 4000 && gc.outcome == GameOutcome::UNDECIDED; ++guard) {
            if (gc.screenState == ScreenState::BATTLE) break;
            if (gc.screenState == ScreenState::REWARDS && gc.info.rewardsContainer.goldRewardCount > 0) {
                exec(GameAction(GameAction::RewardsActionType::GOLD, 0));
                continue;
            }
            const auto v = legal(gc);
            if (v.size() != 1) break;
            exec(v[0]);
        }
        return revealed;
    }

}

int main(int argc, char **argv) {
    const int runs = argc > 1 ? std::atoi(argv[1]) : 60;
    std::map<int, std::pair<long, long>> byScreen;   // screen -> (deterministic, chance)
    long checked = 0, unsupported = 0;
    for (int run = 0; run < runs; ++run) {
        const std::uint64_t seed = 1 + run;
        GameContext gc(CharacterClass::IRONCLAD, seed, 20);
        gc.skipBattles = true;
        std::mt19937 rng(static_cast<unsigned>(seed));
        std::mt19937_64 sampler(seed * 7919u);
        for (int s = 0; s < 3000 && gc.outcome == GameOutcome::UNDECIDED; ++s) {
            const auto actions = legal(gc);
            if (actions.empty()) break;
            for (const bool simHelp : {false, true}) {
                for (const auto &a : actions) {
                    GameContext real = detachedGameCopy(gc);
                    const bool chance = step(real, a, simHelp);
                    if (!simHelp) (chance ? byScreen[static_cast<int>(gc.screenState)].second
                                          : byScreen[static_cast<int>(gc.screenState)].first) += 1;
                    if (chance) continue;
                    const auto want = publicBytes(real);
                    for (int j = 0; j < 3; ++j) {
                        GameContext alt = detachedGameCopy(gc);
                        try { sampleNoncombatFuture(alt, sampler); }
                        catch (const OocSearchUnsupported &) { ++unsupported; continue; }
                        step(alt, a, simHelp);
                        ++checked;
                        if (publicBytes(alt) != want && ++g_fail <= 20)
                            std::cerr << "FAIL: deterministic step depends on hidden state (seed " << seed << " floor "
                                      << gc.floorNum << " screen " << static_cast<int>(gc.screenState) << " event "
                                      << static_cast<int>(gc.curEvent) << " action " << a.bits << " simHelp "
                                      << simHelp << ")\n";
                    }
                }
            }
            actions[rng() % actions.size()].execute(gc);
        }
    }
    long det = 0, ch = 0;
    std::cout << "screen: deterministic chance\n";
    for (const auto &[screen, c] : byScreen) {
        std::cout << "  " << screen << ": " << c.first << " " << c.second << "\n";
        det += c.first;
        ch += c.second;
    }
    std::cout << "steps " << det + ch << " deterministic " << det << " chance " << ch << " resampled checks "
              << checked << " unsupported " << unsupported << "\n";
    if (det == 0 || ch == 0 || checked == 0) { std::cerr << "FAIL: no coverage\n"; ++g_fail; }
    std::cout << (g_fail ? "FAIL" : "ok") << "\n";
    return g_fail ? 1 : 0;
}
