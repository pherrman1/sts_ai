// ADR-0039: with full potion slots, the reward pickup discards the worst held
// potion when the best reward potion outranks it (default);
// STS_POTION_REWARD_SWAP=0 restores the legacy pickup (free slot only, index 0).
#include "game/GameContext.h"
#include "sim/search/GameAction.h"
#include "sim/search/PotionRewardPolicy.h"

#include <cstdlib>
#include <iostream>
#include <stdexcept>

using namespace sts;
using namespace sts::search;
using RT = GameAction::RewardsActionType;

static void require(bool value, const char *message) {
    if (!value) throw std::runtime_error(message);
}

// A reward screen built directly: no generated run, map or game seed.
static GameContext rewardFixture(std::initializer_list<Potion> held, std::initializer_list<Potion> offered) {
    GameContext gc{};
    gc.cc = CharacterClass::IRONCLAD;
    gc.screenState = ScreenState::REWARDS;
    gc.potionCapacity = 2;
    int slot = 0;
    for (const auto p : held) { gc.potions[slot++] = p; ++gc.potionCount; }
    for (const auto p : offered) gc.info.rewardsContainer.addPotion(p);
    gc.regainControlAction = [](GameContext &state) { state.screenState = ScreenState::MAP_SCREEN; };
    return gc;
}

// Runs the pickup until it stops; returns the held potions afterwards.
static std::array<Potion, 5> pickUp(GameContext gc) {
    for (int steps = 0; const auto action = potionRewardAction(gc); ++steps) {
        require(steps < 6, "potion pickup does not terminate");
        require(action->isValidAction(gc), "pickup action is not simulator-legal");
        action->execute(gc);
    }
    return gc.potions;
}

int main() {
    try {
        unsetenv("STS_POTION_REWARD_SWAP");
        // Full slots, better reward: the worst held potion (Block) is replaced.
        auto held = pickUp(rewardFixture({Potion::FAIRY_POTION, Potion::BLOCK_POTION}, {Potion::BLOOD_POTION}));
        require(held[0] == Potion::FAIRY_POTION && held[1] == Potion::BLOOD_POTION, "swap did not replace the worst potion");
        // Full slots, worse reward: nothing changes.
        held = pickUp(rewardFixture({Potion::FAIRY_POTION, Potion::BLOOD_POTION}, {Potion::BLOCK_POTION}));
        require(held[0] == Potion::FAIRY_POTION && held[1] == Potion::BLOOD_POTION, "swap dropped a better potion");
        // Free slot, two rewards: the better one is taken first; the other ranks below both held.
        held = pickUp(rewardFixture({Potion::FIRE_POTION}, {Potion::SPEED_POTION, Potion::FAIRY_POTION}));
        require(held[0] == Potion::FIRE_POTION && held[1] == Potion::FAIRY_POTION, "free slot did not take the best reward");

        setenv("STS_POTION_REWARD_SWAP", "0", 1);
        held = pickUp(rewardFixture({Potion::FAIRY_POTION, Potion::BLOCK_POTION}, {Potion::BLOOD_POTION}));
        require(held[0] == Potion::FAIRY_POTION && held[1] == Potion::BLOCK_POTION, "legacy: full slots must not change");
        held = pickUp(rewardFixture({Potion::FIRE_POTION}, {Potion::SPEED_POTION, Potion::FAIRY_POTION}));
        require(held[0] == Potion::FIRE_POTION && held[1] == Potion::SPEED_POTION, "legacy: free slot takes index 0");

        std::cout << "potion_reward_swap: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "potion_reward_swap: FAIL: " << e.what() << '\n';
        return 1;
    }
}
