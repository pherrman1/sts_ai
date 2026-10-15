#include "sim/search/RunGoal.h"
#include <array>

namespace sts::search {
std::optional<GameAction> heartKeyAction(const GameContext &gc, bool collectKeys) {
    if (!collectKeys || !gc.keysEnabled || gc.outcome != GameOutcome::UNDECIDED) return std::nullopt;
    using RT = GameAction::RewardsActionType;
    if (gc.screenState == ScreenState::REWARDS) {
        const auto &r = gc.info.rewardsContainer;
        // Sapphire must precede its paired relic, which removes the key offer.
        if ((r.emeraldKey || r.sapphireKey) && GameAction(RT::KEY, 0).isValidAction(gc))
            return GameAction(RT::KEY, 0);
    }
    if (gc.screenState == ScreenState::REST_ROOM && gc.act >= 3 && !gc.redKey
            && GameAction(2).isValidAction(gc)) return GameAction(2);
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
    for (const auto action : GameAction::getAllActionsInState(gc)) {
        const int x = action.getIdx1();
        if (x < 7 && reaches[nextY][x] && action.isValidAction(gc)) return action;
    }
    return std::nullopt;
}
}
