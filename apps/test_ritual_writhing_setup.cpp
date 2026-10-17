#include <iostream>
#include <stdexcept>
#include <string>
#include "one_combat/ritual_writhing_setup.h"
#include "one_combat/combat_transition.h"
#include "sim/search/Action.h"

namespace {
using namespace sts;
using namespace one_combat;
void require(bool ok, const char *message) { if (!ok) throw std::runtime_error(message); }
RitualWrithingSetup setup(bool upgraded, int copies, const std::string &potion) {
    auto parsed = parseRitualWrithingSetup(std::string("ritual_writhing_v2_")
        + (upgraded ? "upgraded_" : "base_") + (copies == 1 ? "single_" : "double_") + potion);
    require(parsed.has_value(), "valid setup did not parse"); return *parsed;
}
GameContext game(int daggers = 3) {
    GameContext g(CharacterClass::IRONCLAD, 0xDA660u, 0);
    g.deck = Deck{};
    for (int i = 0; i < daggers; ++i) {
        Card c(CardId::RITUAL_DAGGER, i%2); c.misc = 42+i;
        g.deck.obtain(g, c);
    }
    g.deck.obtain(g, Card(CardId::STRIKE_RED));
    if (daggers > 2) g.deck.bottleCard(2, CardType::ATTACK);
    g.act = 3; g.floorNum = 40; g.curRoom = Room::MONSTER;
    g.enterBattle(MonsterEncounter::CULTIST);
    g.regainControlAction = [](GameContext &) {};
    return g;
}
void play(BattleContext &bc, int id) {
    int hand = -1;
    for (int i=0;i<bc.cards.cardsInHand;++i) if (bc.cards.hand[i].uniqueId == id) hand=i;
    require(hand >= 0, "physical card missing from initialized hand");
    search::Action action(search::ActionType::CARD, hand, 0);
    require(action.isValidAction(bc), "fixture action not legal"); action.execute(bc);
}
void cell(bool upgraded, int copies, const std::string &potion) {
    auto g = game();
    // Relic acquisition is outside the intervention. These prove the helper
    // neither auto-upgrades via Egg nor grants Fish gold/healing on append/reset.
    g.obtainRelic(RelicId::MOLTEN_EGG); g.obtainRelic(RelicId::CERAMIC_FISH);
    g.obtainRelic(RelicId::SOZU);
    g.potions = {Potion::FIRE_POTION, Potion::ENERGY_POTION, Potion::BLOCK_POTION,
                 Potion::EMPTY_POTION_SLOT, Potion::EMPTY_POTION_SLOT}; g.potionCount=3;
    const auto before = combatTransitionStateJson(captureCombatTransitionState(g));
    const auto s = setup(upgraded, copies, potion);
    const auto receipt = applyRitualWrithingSetup(g, s);
    require(receipt.at("rngBefore") == receipt.at("rngAfter"), "RNG changed");
    require(receipt.at("before") == before && receipt.at("assertionsPassed"), "receipt before differs");
    require(g.info.encounter == MonsterEncounter::WRITHING_MASS, "target encounter not forced");
    auto unchangedBefore = before, unchangedAfter = receipt.at("after");
    for (const char *field : {"deck", "cardTypeCounts", "bottleIdxs", "upgradeableCount", "transformableCount", "potions", "potionCount"}) {
        unchangedBefore.erase(field); unchangedAfter.erase(field);
    }
    require(unchangedBefore == unchangedAfter, "override changed undeclared persistent fields");
    require(g.gold == before.at("gold") && g.curHp == before.at("curHp"), "acquisition hooks leaked");
    require(g.deck.size() == copies+1 && g.deck.cards[copies].id == CardId::STRIKE_RED,
            "normalization removed non-Dagger or wrong copy count");
    require(g.deck.bottleIdxs[0] == -1, "removed surplus bottle remained aliased");
    require(g.deck.cardTypeCounts[0] == copies+1 && g.deck.transformableCount == copies+1
            && g.deck.upgradeableCount == (upgraded ? 1 : copies+1), "deck caches do not match actual cards");
    for (int i=0;i<copies;++i)
        require(g.deck.cards[i].misc == (i == 0 ? 15 : 30) && g.deck.cards[i].upgraded == upgraded,
                "wrong normalized damage or upgrade");
    if (potion == "natural") require(g.potions[2] == Potion::BLOCK_POTION, "natural belt changed");
    else {
        require(g.potions[2] == s.potion && g.potions[0] == Potion::FIRE_POTION
                && g.potions[1] == Potion::ENERGY_POTION && g.potionCount == 3,
                "full-belt placement failed under Sozu");
        require(receipt.at("potionOverride").at("action") == "overwrite_last_active", "overwrite receipt wrong");
    }
    const GameContext pre = g;
    const auto predictor = combatPredictorInputJson(captureCombatPredictorInput(g, g.info.encounter, 4.0));
    require(predictor.at("cards").size() == static_cast<std::size_t>(g.deck.size()), "predictor used old deck");
    for (int i=0;i<copies;++i)
        require(predictor.at("cards").at(i).at("misc") == (i==0 ? 15:30)
                && predictor.at("cards").at(i).at("upgraded") == upgraded,
                "predictor did not capture normalized ROOT");
    BattleContext bc; bc.init(g, g.info.encounter);
    while (bc.inputState != InputState::PLAYER_NORMAL && bc.outcome == Outcome::UNDECIDED) bc.executeActions();
    for (int i=0;i<copies;++i) {
        bool found=false;
        for (int k=0;k<bc.cards.cardsInHand;++k) if (bc.cards.hand[k].uniqueId == i) {
            found=true; require(bc.cards.hand[k].specialData == (i==0?15:30), "combat physical identity wrong");
        }
        require(found, "controlled master card missing from battle");
    }
    bc.monsters.arr[0].curHp=1; bc.monsters.arr[0].block=0;
    play(bc, 0);
    require(bc.outcome == Outcome::PLAYER_VICTORY, "real fixture action did not win");
    int captures=0;
    CombatTransitionRawObserverScope scope([&](const BattleContext &ended, GameContext &raw) {
        ++captures;
        const auto transition = combatTransitionRecordJson(captureCombatTransition(pre, ended, raw));
        require(transition.at("pre") == receipt.at("after"), "RAW pre differs from normalized ROOT");
        require(transition.at("post").at("deck").at(0).at("misc") == (upgraded?20:18), "RAW growth missing");
        if (copies==2) require(transition.at("post").at("deck").at(1).at("misc") == 30, "growth aliased second copy");
    });
    bc.exitBattle(g); require(captures==1, "RAW capture missing or repeated");
}
void placementAndAppend() {
    auto g=game(0); g.obtainRelic(RelicId::MOLTEN_EGG); g.obtainRelic(RelicId::CERAMIC_FISH);
    const int gold=g.gold, hp=g.curHp;
    g.potions={Potion::ENERGY_POTION,Potion::EMPTY_POTION_SLOT,Potion::BLOCK_POTION,
               Potion::EMPTY_POTION_SLOT,Potion::EMPTY_POTION_SLOT};g.potionCount=2;
    auto s=setup(false,2,"brew"); auto first=applyRitualWrithingSetup(g,s);
    require(g.deck.cards[1].misc==15 && !g.deck.cards[1].upgraded && g.deck.cards[2].misc==30,
            "append/reset failed with Egg");
    require(g.gold==gold && g.curHp==hp, "append triggered acquisition hooks");
    require(g.potions[1]==Potion::ENTROPIC_BREW && first.at("potionOverride").at("slot")==1
            && first.at("potionOverride").at("action")=="fill_lowest_free", "lowest free slot not used");
    auto second=applyRitualWrithingSetup(g,s);
    require(second.at("potionOverride").at("action")=="already_held"
            && second.at("before")==second.at("after"), "held potion was replaced or duplicated");
    g.deck.bottleCard(1,CardType::ATTACK);
    applyRitualWrithingSetup(g,setup(true,1,"natural"));
    require(g.deck.bottleIdxs[0]==1 && g.deck.transformableCount==1, "retained bottle or shifted index lost");
}
void invalidAtomic() {
    auto check=[](GameContext g) {
        const auto before=combatTransitionStateJson(captureCombatTransitionState(g));
        bool threw=false; try { applyRitualWrithingSetup(g,setup(false,2,"smoke")); }
        catch (const std::runtime_error &) {threw=true;}
        require(threw && before==combatTransitionStateJson(captureCombatTransitionState(g)), "invalid override was not atomic");
    };
    auto g=game();--g.deck.upgradeableCount;check(g);
    g=game();g.potionCount=1;check(g);
    g=game();g.act=2;check(g);
    g=game(0);while(g.deck.size()<Deck::MAX_SIZE)g.deck.obtain(g,Card(CardId::STRIKE_RED));check(g);
    require(!parseRitualWrithingSetup("ritual_writhing") && !parseRitualWrithingSetup("ritual_writhing_v2_base_single_invalid"),
            "parser accepted old/unknown setup as new variant");
}
void failureBoundary() {
    auto g=game(); std::string partial="row0\n"; nlohmann::json failures=nlohmann::json::array();
    const int fight=4; const std::string stage="normalized_root_assertion";
    const bool ok=guardRitualWrithingSource(g,0xDA660u,fight,stage,{{"probe",1}},failures,
        [&]{ partial+="row1\n"; throw std::runtime_error("probe failure"); });
    require(!ok && partial=="row0\nrow1\n" && failures.size()==1, "failure escaped or partial rows lost");
    const auto &f=failures.at(0);
    require(f.at("fightIdx")==fight && f.at("stage")==stage && f.at("error")=="probe failure"
            && f.at("terminalInvalid")==true && f.at("attempt").at("probe")==1
            && f.contains("stateAtFailure") && f.at("rngAtFailure").size()==14, "failure receipt incomplete");
    require(guardRitualWrithingSource(g,0xDA660u,fight,stage,{},failures,[]{}) && failures.size()==1,
            "successful source recorded a failure");
}
}
int main() {
    try {
        for(bool upgraded:{false,true})for(int copies:{1,2})for(const std::string potion:{"natural","brew","smoke"}) {
            cell(upgraded,copies,potion);std::cout<<setup(upgraded,copies,potion).name<<" PASS\n";
        }
        placementAndAppend(); invalidAtomic(); failureBoundary();
        std::cout<<"placement, append, bottle, invalid-atomic, failure-boundary controls PASS\n";
        return 0;
    } catch(const std::exception &e) {std::cerr<<e.what()<<'\n';return 1;}
}
