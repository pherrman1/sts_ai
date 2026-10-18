// Curl Up does not trigger on a lethal hit (Java CurlUpPower.onAttacked
// requires damageAmount < currentHealth); a non-lethal hit still curls.
#include "combat/BattleContext.h"
#include "game/GameContext.h"

#include <iostream>
#include <stdexcept>
#include <string>

using namespace sts;

static void require(bool value, const std::string &message) {
    if (!value) throw std::runtime_error(message);
}

// Fixed seed from the engine parity thread's block; no gameplay is driven.
static constexpr std::uint64_t SEED = 111194453;

int main() {
    try {
        GameContext gc(CharacterClass::IRONCLAD, SEED, 0);
        BattleContext bc;
        bc.init(gc, MonsterEncounter::TWO_LOUSE);
        Monster &lethal = bc.monsters.arr[0];
        Monster &survives = bc.monsters.arr[1];
        require(lethal.hasStatus<MS::CURL_UP>() && survives.hasStatus<MS::CURL_UP>(),
                "both lice must start with Curl Up");

        const int queued = bc.actionQueue.size;
        lethal.attacked(bc, lethal.curHp);
        require(!lethal.isAlive(), "the lethal hit must kill");
        require(bc.actionQueue.size == queued, "a lethal hit must not queue Curl Up block");

        survives.attacked(bc, survives.curHp - 1);
        require(survives.isAlive(), "the non-lethal hit must leave the louse alive");
        require(!survives.hasStatus<MS::CURL_UP>(), "a non-lethal hit must use up Curl Up");
        require(bc.actionQueue.size == queued + 1, "a non-lethal hit must queue Curl Up block");

        std::cout << "curl_up_lethal: OK\n";
        return 0;
    } catch (const std::exception &e) {
        std::cerr << "curl_up_lethal: FAIL: " << e.what() << '\n';
        return 1;
    }
}
