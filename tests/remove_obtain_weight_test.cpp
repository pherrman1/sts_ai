#include "sim/search/ScumSearchAgent2.h"
#include "sim/search/ExpertKnowledge.h"

#include <array>
#include <cstdlib>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace sts;
using namespace sts::search;

static void require(bool value, const char *message) {
    if (!value) throw std::runtime_error(message);
}

static void flag(const char *value) {
    if (value) setenv("STS_OOC_REMOVE_LOW_OBTAIN_WEIGHT", value, 1);
    else unsetenv("STS_OOC_REMOVE_LOW_OBTAIN_WEIGHT");
}

// Direct public fixtures: no generated run, map, fight or game seed.
static GameContext fixture(const std::vector<Card> &cards) {
    GameContext gc{};
    gc.cc = CharacterClass::IRONCLAD;
    gc.act = 1;
    gc.floorNum = 2;
    gc.curHp = 40;
    gc.maxHp = 80;
    gc.gold = 123;
    gc.curRoom = Room::EVENT;
    for (const auto card : cards) gc.deck.obtainRaw(card);
    gc.regainControlAction = [](GameContext &state) { state.screenState = ScreenState::MAP_SCREEN; };
    return gc;
}

static auto gameRng(const GameContext &gc) {
    return std::array{gc.aiRng, gc.cardRandomRng, gc.cardRng, gc.eventRng,
        gc.mathUtilRng, gc.merchantRng, gc.miscRng, gc.monsterHpRng, gc.monsterRng,
        gc.neowRng, gc.potionRng, gc.relicRng, gc.shuffleRng, gc.treasureRng};
}

static Card select(GameContext &gc, int expectedIndex) {
    require(GameAction(expectedIndex).isValidAction(gc), "expected selection is not legal");
    const auto selected = gc.info.toSelectCards[expectedIndex].card;
    const auto sourceRng = gameRng(gc);
    ScumSearchAgent2 agent;
    agent.recordActions = true;
    agent.rng.seed(73);
    const auto agentRng = agent.rng;
    agent.cardSelectPolicy(gc);
    require(agent.gameActionHistory == std::vector<int>{expectedIndex}, "unexpected selector action/index");
    require(agent.rng == agentRng && gameRng(gc) == sourceRng, "selector changed agent/game RNG");
    return selected;
}

static std::vector<Card> deck(const GameContext &gc) {
    return {gc.deck.cards.begin(), gc.deck.cards.end()};
}

static void ordinaryRemoval(Card wanted, const char *setting) {
    flag(setting);
    auto gc = fixture({Card(CardId::STRIKE_RED), wanted});
    gc.curEvent = Event::LIVING_WALL;
    gc.screenState = ScreenState::EVENT_SCREEN;
    require(GameAction(0).isValidAction(gc), "Living Wall Forget is not legal");
    GameAction(0).execute(gc);
    require(gc.info.selectScreenType == CardSelectScreenType::REMOVE, "Living Wall did not open REMOVE");
    const bool enabled = !setting || std::string(setting) == "1";
    const auto removed = select(gc, enabled ? 0 : 1);
    require(removed == (enabled ? Card(CardId::STRIKE_RED) : wanted), "removal polarity differs from contract");
    require(deck(gc) == std::vector<Card>{enabled ? wanted : Card(CardId::STRIKE_RED)}, "wrong actual card removed");
    require(gc.screenState == ScreenState::MAP_SCREEN && gc.curHp == 40 && gc.maxHp == 80 && gc.gold == 123,
            "ordinary removal changed unrelated public resources");
}

int main() {
    try {
        require(Expert::getObtainWeight(CardId::STRIKE_RED) == 0
            && Expert::getObtainWeight(CardId::OFFERING) == 65
            && Expert::getObtainWeight(CardId::SHRUG_IT_OFF) == 15,
            "fixture acquisition-weight semantics changed");
        for (const char *setting : {static_cast<const char *>(nullptr), "0", "1"}) {
            ordinaryRemoval(Card(CardId::OFFERING), setting);
            ordinaryRemoval(Card(CardId::SHRUG_IT_OFF), setting);
        }

        flag("1");
        auto pipe = fixture({Card(CardId::DEFEND_RED), Card(CardId::OFFERING)});
        pipe.curRoom = Room::REST;
        pipe.screenState = ScreenState::REST_ROOM;
        pipe.relics.add({RelicId::PEACE_PIPE, 0});
        require(GameAction(4).isValidAction(pipe), "Peace Pipe Toke is not legal");
        GameAction(4).execute(pipe);
        require(pipe.info.selectScreenType == CardSelectScreenType::REMOVE, "Toke did not open REMOVE");
        select(pipe, 0);
        require(deck(pipe) == std::vector<Card>{Card(CardId::OFFERING)}, "Peace Pipe bypassed removal ranking");

        // The real menu excludes unremovable/bottled cards; the policy ranks
        // existing legal indices only and must not fabricate a deck index.
        auto limited = fixture({Card(CardId::ASCENDERS_BANE), Card(CardId::STRIKE_RED),
                                Card(CardId::OFFERING), Card(CardId::DEFEND_RED)});
        limited.deck.bottleCard(1, CardType::ATTACK);
        limited.openCardSelectScreen(CardSelectScreenType::REMOVE, 1);
        require(limited.info.toSelectCards.size() == 2
            && limited.info.toSelectCards[0].deckIdx == 2 && limited.info.toSelectCards[1].deckIdx == 3,
            "real selector did not exclude protected cards");
        select(limited, 1);
        require(deck(limited) == std::vector<Card>({Card(CardId::ASCENDERS_BANE),
            Card(CardId::STRIKE_RED), Card(CardId::OFFERING)}) && limited.deck.isCardBottled(1),
            "selected index removed a protected or different card");

        auto singleton = fixture({Card(CardId::OFFERING)});
        singleton.openCardSelectScreen(CardSelectScreenType::REMOVE, 1);
        select(singleton, 0);
        require(singleton.deck.size() == 0, "forced singleton removal changed");

        auto multiple = fixture({Card(CardId::BASH), Card(CardId::STRIKE_RED), Card(CardId::OFFERING)});
        multiple.openCardSelectScreen(CardSelectScreenType::REMOVE, 2);
        select(multiple, 1);
        require(multiple.screenState == ScreenState::CARD_SELECT && multiple.deck.size() == 3,
                "multi-remove committed prematurely");
        select(multiple, 0);
        require(deck(multiple) == std::vector<Card>{Card(CardId::OFFERING)}
            && multiple.screenState == ScreenState::MAP_SCREEN, "multi-remove index tracking changed");

        // No upgrade-weight refinement: these remain equal by card-ID lookup.
        // Compare complete paired choices instead of assuming std::sort is stable.
        int tieIndex = -1;
        for (const char *setting : {static_cast<const char *>(nullptr), "0", "1"}) {
            flag(setting);
            auto tied = fixture({Card(CardId::SPOT_WEAKNESS, 1), Card(CardId::OFFERING),
                Card(CardId::OFFERING, 1), Card(CardId::FLEX)});
            tied.openCardSelectScreen(CardSelectScreenType::REMOVE, 1);
            ScumSearchAgent2 agent;
            agent.recordActions = true;
            const auto beforeRng = agent.rng;
            const auto beforeGameRng = gameRng(tied);
            const auto before = tied;
            agent.cardSelectPolicy(tied);
            require(agent.gameActionHistory.size() == 1, "tie selected multiple actions");
            const int index = agent.gameActionHistory[0];
            require(GameAction(index).isValidAction(before), "tie selected illegal action");
            if (tieIndex < 0) tieIndex = index;
            require(index == tieIndex && agent.rng == beforeRng && gameRng(tied) == beforeGameRng,
                    "all-equal tie order or RNG changed");
        }

        // Bonfire has a different sacrifice reward: preserve the rare choice
        // and its actual +10 max-HP/full-heal transition in both modes.
        for (const char *setting : {static_cast<const char *>(nullptr), "0", "1"}) {
            flag(setting);
            auto bonfire = fixture({Card(CardId::STRIKE_RED), Card(CardId::OFFERING)});
            bonfire.openCardSelectScreen(CardSelectScreenType::BONFIRE_SPIRITS, 1);
            select(bonfire, 1);
            require(bonfire.maxHp == 90 && bonfire.curHp == 90
                && deck(bonfire) == std::vector<Card>{Card(CardId::STRIKE_RED)}, "Bonfire sacrifice changed");
            for (const auto type : {CardSelectScreenType::UPGRADE, CardSelectScreenType::DUPLICATE,
                                   CardSelectScreenType::OBTAIN, CardSelectScreenType::BOTTLE}) {
                auto other = fixture({Card(CardId::STRIKE_RED), Card(CardId::OFFERING)});
                other.openCardSelectScreen(type, 1, false);
                other.info.toSelectCards.push_back({other.deck.cards[0], 0});
                other.info.toSelectCards.push_back({other.deck.cards[1], 1});
                select(other, 1);
            }
            // Stop at the first legal transform selection so this regression
            // tests ordering without sampling any transformed card.
            auto transform = fixture({Card(CardId::STRIKE_RED), Card(CardId::OFFERING)});
            transform.openCardSelectScreen(CardSelectScreenType::TRANSFORM, 2);
            select(transform, 0);
            require(transform.info.haveSelectedCards[0].card.getId() == CardId::STRIKE_RED
                && transform.screenState == ScreenState::CARD_SELECT, "transform ordering changed");
        }
        for (const char *invalid : {"", "2", "-1", "true", "01", " 1"}) {
            flag(invalid);
            bool rejected = false;
            try { (void)oocRemoveLowObtainWeightEnabled(); }
            catch (const std::runtime_error &) { rejected = true; }
            require(rejected, "malformed removal flag accepted");
        }
        flag(nullptr); require(oocRemoveLowObtainWeightEnabled(), "unset removal flag disabled");
        flag("0"); require(!oocRemoveLowObtainWeightEnabled(), "zero removal flag enabled");
        flag("1"); require(oocRemoveLowObtainWeightEnabled(), "one removal flag disabled");
        flag(nullptr);
        std::cout << "remove_obtain_weight PASS: REMOVE polarity, actual Living Wall/Peace Pipe, default RNG, legal indices, multi-remove, legacy ties/upgrades, unchanged Bonfire/other selectors\n";
        return 0;
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
