// ADR-0038: Neow "transform two cards" adds a curse only with the CURSE
// drawback (default); STS_NEOW_TRANSFORM_CURSE_FIX=0 restores the legacy curse
// on every transform pick.
#include "game/GameContext.h"
#include "sim/search/GameAction.h"

#include <cstdlib>
#include <iostream>
#include <stdexcept>

using namespace sts;
using namespace sts::search;

static void require(bool value, const char *message) {
    if (!value) throw std::runtime_error(message);
}

// Applies "transform two cards" with the given drawback, then takes the first
// legal action until the map opens.
static int cursesAfterTransform(std::uint64_t seed, Neow::Drawback drawback) {
    GameContext gc(CharacterClass::IRONCLAD, seed, 0);
    gc.chooseNeowOption(Neow::Option{Neow::Bonus::TRANSFORM_TWO_CARDS, drawback});
    for (int steps = 0; gc.screenState != ScreenState::MAP_SCREEN; ++steps) {
        require(steps < 10, "Neow transform did not reach the map");
        const auto actions = GameAction::getAllActionsInState(gc);
        require(!actions.empty(), "no legal action after the Neow pick");
        actions[0].execute(gc);
    }
    int curses = 0;
    for (const auto &card : gc.deck.cards) curses += card.getType() == CardType::CURSE;
    return curses;
}

int main() {
    try {
        const Neow::Drawback drawbacks[] = {Neow::Drawback::TEN_PERCENT_HP_LOSS, Neow::Drawback::NO_GOLD,
                                            Neow::Drawback::CURSE, Neow::Drawback::PERCENT_DAMAGE};
        int cases = 0;
        // Fixed A0 seeds from the thread's reserved smoke block; no curse in the starting deck.
        for (std::uint64_t seed = 74071650; seed < 74071660; ++seed) {
            for (const auto drawback : drawbacks) {
                const int expected = drawback == Neow::Drawback::CURSE ? 1 : 0;
                unsetenv("STS_NEOW_TRANSFORM_CURSE_FIX");
                require(cursesAfterTransform(seed, drawback) == expected,
                        "default: curse count does not follow the drawback");
                setenv("STS_NEOW_TRANSFORM_CURSE_FIX", "1", 1);
                require(cursesAfterTransform(seed, drawback) == expected, "=1 differs from the default");
                setenv("STS_NEOW_TRANSFORM_CURSE_FIX", "0", 1);
                require(cursesAfterTransform(seed, drawback) == 1, "legacy: expected exactly one curse");
                ++cases;
            }
        }
        std::cout << "neow_transform_curse: OK (" << cases << " seed/drawback cases)\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "neow_transform_curse: FAIL: " << e.what() << '\n';
        return 1;
    }
}
