#include <iostream>
#include <stdexcept>
#include <string>

#include "combat/BattleContext.h"
#include "game/GameContext.h"

namespace {
using namespace sts;

void require(bool condition, const std::string &message) {
    if (!condition) throw std::runtime_error(message);
}

struct Fixture {
    GameContext game{CharacterClass::IRONCLAD, 0xDA663u, 0};
    BattleContext battle;

    Fixture(MonsterEncounter encounter, bool upgraded) {
        game.act = encounter == MonsterEncounter::CULTIST ? 1 : 3;
        game.floorNum = game.act == 1 ? 1 : 40;
        game.curRoom = Room::MONSTER;
        game.enterBattle(encounter);
        battle.init(game, encounter);
        while (battle.inputState != InputState::PLAYER_NORMAL && battle.outcome == Outcome::UNDECIDED)
            battle.executeActions();
        require(battle.inputState == InputState::PLAYER_NORMAL, "fixture did not reach player control");
        battle.curCardQueueItem = CardQueueItem{};
        battle.curCardQueueItem.card = CardInstance(CardId::RITUAL_DAGGER, upgraded);
        battle.curCardQueueItem.card.specialData = 15;
        for (int i = 0; i < battle.monsters.monsterCount; ++i) {
            battle.monsters.arr[i].curHp = 1;
            battle.monsters.arr[i].block = 0;
        }
    }

    void hit(int index, int expectedGrowth) {
        ActData_RitualDaggerAction{index, 15}(battle);
        require(battle.curCardQueueItem.card.specialData == 15 + expectedGrowth,
                "Ritual growth got " + std::to_string(battle.curCardQueueItem.card.specialData - 15)
                + ", expected " + std::to_string(expectedGrowth));
    }
};

void ordinary(bool upgraded) {
    Fixture fixture(MonsterEncounter::CULTIST, upgraded);
    fixture.hit(0, upgraded ? 5 : 3);
    require(fixture.battle.outcome == Outcome::PLAYER_VICTORY, "ordinary kill did not win");
}

void regrowingDarkling(bool upgraded) {
    Fixture fixture(MonsterEncounter::THREE_DARKLINGS, upgraded);
    fixture.hit(0, 0);
    const auto &monster = fixture.battle.monsters.arr[0];
    require(monster.isHalfDead() && !monster.hasStatus<MS::REGROW>(),
            "regrowing Darkling must be half-dead after clearing its powers");
    require(fixture.battle.outcome == Outcome::UNDECIDED, "regrowing Darkling ended combat");
}

void lastDarkling(bool upgraded) {
    Fixture fixture(MonsterEncounter::THREE_DARKLINGS, upgraded);
    for (int i = 1; i < fixture.battle.monsters.monsterCount; ++i) {
        auto &monster = fixture.battle.monsters.arr[i];
        monster.curHp = 0;
        monster.halfDead = true;
        monster.resetAllStatusEffects();
    }
    fixture.battle.monsters.monstersAlive = 1;
    fixture.hit(0, upgraded ? 5 : 3);
    require(!fixture.battle.monsters.arr[0].isHalfDead()
            && fixture.battle.outcome == Outcome::PLAYER_VICTORY,
            "last Darkling must die permanently");
}

void awakenedFirstPhase(bool upgraded) {
    Fixture fixture(MonsterEncounter::AWAKENED_ONE, upgraded);
    int index = -1;
    for (int i = 0; i < fixture.battle.monsters.monsterCount; ++i)
        if (fixture.battle.monsters.arr[i].id == MonsterId::AWAKENED_ONE) index = i;
    require(index >= 0, "Awakened One fixture missing boss");
    require(fixture.battle.monsters.arr[index].miscInfo == 0, "fixture is not phase one");
    fixture.hit(index, 0);
    require(fixture.battle.monsters.arr[index].isHalfDead()
            && fixture.battle.outcome == Outcome::UNDECIDED,
            "Awakened One phase one must await rebirth");
}

void awakenedFinalPhase(bool upgraded) {
    Fixture fixture(MonsterEncounter::AWAKENED_ONE, upgraded);
    int index = -1;
    for (int i = 0; i < fixture.battle.monsters.monsterCount; ++i) {
        const auto &monster = fixture.battle.monsters.arr[i];
        if (monster.id == MonsterId::AWAKENED_ONE) index = i;
        else require(monster.id == MonsterId::CULTIST && !monster.hasStatus<MS::MINION>(),
                     "Awakened One companions must be non-Minion Cultists");
    }
    require(index >= 0, "Awakened One fixture missing boss");
    auto &boss = fixture.battle.monsters.arr[index];
    boss.attacked(fixture.battle, 15);
    require(boss.isHalfDead() && fixture.battle.outcome == Outcome::UNDECIDED,
            "first phase did not enter real rebirth transition");
    boss.takeTurn(fixture.battle);
    require(!boss.isHalfDead() && boss.miscInfo != 0 && boss.hasStatus<MS::MINION_LEADER>()
            && !boss.hasStatus<MS::MINION>(), "Awakened One did not reach its final phase");
    boss.curHp = 1;
    boss.block = 0;
    fixture.hit(index, upgraded ? 5 : 3);
    require(fixture.battle.outcome == Outcome::PLAYER_VICTORY,
            "Awakened One final-phase kill did not win combat");
}

void minion(bool upgraded) {
    Fixture fixture(MonsterEncounter::CULTIST, upgraded);
    fixture.battle.monsters.arr[0].buff<MS::MINION>();
    fixture.hit(0, 0);
}
}

int main() {
    int failures = 0;
    const auto run = [&](const std::string &label, const auto &test) {
        try { test(); std::cout << label << " PASS\n"; }
        catch (const std::exception &error) {
            ++failures; std::cerr << label << " FAIL: " << error.what() << '\n';
        }
    };
    for (bool upgraded : {false, true}) {
        const std::string suffix = upgraded ? "+" : " base";
        run("ordinary kill" + suffix, [&] { ordinary(upgraded); });
        run("regrowing Darkling" + suffix, [&] { regrowingDarkling(upgraded); });
        run("last Darkling" + suffix, [&] { lastDarkling(upgraded); });
        run("Awakened One phase one" + suffix, [&] { awakenedFirstPhase(upgraded); });
        run("Awakened One final phase" + suffix, [&] { awakenedFinalPhase(upgraded); });
        run("Minion" + suffix, [&] { minion(upgraded); });
    }
    return failures ? 1 : 0;
}
